from argparse import ArgumentParser
from pathlib import Path

import pandas as pd
import pendulum
from configurator import Config
from pendulum import DateTime, Date

from loaders import load_octopus, load_tesla


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
    print(date)
    tesla = load_tesla(storage, date)
    octopus = load_octopus(storage, date)
    diff = (octopus['consumption'] - tesla['consumption'])
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
