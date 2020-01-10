from argparse import ArgumentParser, FileType
from datetime import time
from pathlib import Path

import pandas as pd
import pendulum
from configurator import Config
from pandas import DataFrame

from loaders import load_octopus, load_tesla

loaders = {
    'octopus': load_octopus,
    'tesla': load_tesla,
}


def date(text):
    return pendulum.parse(text, tz='Europe/London').date()


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('start', type=date)
    parser.add_argument('end', type=date)
    parser.add_argument('--source', choices=loaders.keys(), default='octopus')
    parser.add_argument('--csv', type=FileType(mode='w'),
                        help='path to dump concatenated data to')
    return parser.parse_args()


def load_data(start, end, storage: Path, load_source) -> DataFrame:
    frames = []
    for date in list(end-start)[:-1]:
        frames.append(load_source(storage, date))
    data = pd.concat(frames)
    return data


def bill(start, end, df, standing, normal, cheap, vat=1.05):
    df['cheap'] = [time(0, 30) <= index.time() <= time(4) for index, row in df.iterrows()]

    print(f'from {df.index.min()} to {df.index.max()}')
    print(f'total: {df.consumption.sum():.1f}')

    night = df[df.cheap==True].consumption.sum()
    night_total = night * cheap
    print(f'night: {night:.1f} @ {cheap} = {night_total:.2f} ({night_total/vat:.2f} ex vat)')

    day = df[df.cheap==False].consumption.sum()
    day_total = day * normal
    print(f'day: {day:.1f} @ {normal} = {day_total:.2f} ({day_total/vat:.2f} ex vat)')

    days = (end-start).days
    standing_total = days * standing
    print(f'standing: {days} @ {standing} = {standing_total:.2f} ({standing_total/vat:.2f} ex vat)')

    print(f'total: {night_total+day_total+standing_total:.2f}')


if __name__ == '__main__':
    config = Config.from_path('config.yaml')
    storage = Path(config.directories.storage).expanduser()
    args = parse_args()
    data = load_data(args.start, args.end, storage, loaders[args.source])
    if args.csv:
        data.to_csv(args.csv)
    bill(args.start, args.end, data, **config.octopus.charges.data)

