from argparse import ArgumentParser
from pathlib import Path

import pandas as pd
import pendulum
from configurator import Config
from pendulum import DateTime, Date


def date(text):
    return pendulum.parse(text, tz='Europe/London')


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--date', type=date)
    parser.add_argument('--threshold', type=float, default=0.11)
    return parser.parse_args()


def find_dates(storage: Path):
    # less likely to have Telsa days, since they have to be manually downloaded
    for path in storage.glob('tesla-*.csv'):
        date = DateTime.strptime(path.name, 'tesla-%Y-%m-%d.csv').date()
        octopus = storage / f'octopus-{date}.csv'
        if octopus.exists():
            yield date


def reconcile(storage: Path, date: Date, threshold: float):
    tesla = pd.read_csv(storage / f'tesla-{date}.csv',
                        index_col='Date time',
                        parse_dates=['Date time'],
                        date_parser=lambda col: pd.to_datetime(col, utc=True))
    # blank out any energy sent back to the grid, octopus is consumption only:
    tesla[tesla['Grid (kW)']<0] = 0
    # Tesla provide power flow every 5 mins, let's assume that represents the continous
    # consumption for the next 5 mins, and then resample to half-hours to match Octopus:
    tesla = (tesla*5/60).resample('30T').sum()

    octopus = pd.read_csv(storage / f'octopus-{date}.csv',
                          index_col='interval_start', parse_dates=['interval_start'])

    diff = (octopus['consumption'] - tesla['Grid (kW)'])
    bad = diff[diff.abs() > threshold]
    if not bad.empty:
        print(bad, end='\n\n')


if __name__ == '__main__':
    config = Config.from_path('config.yaml')
    storage = Path(config.directories.storage).expanduser()
    args = parse_args()
    if args.date:
        dates = [args.date.date()]
    else:
        dates = find_dates(storage)
    for date in sorted(dates):
        reconcile(storage, date, args.threshold)
