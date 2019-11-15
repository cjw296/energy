import csv
from argparse import ArgumentParser
from itertools import groupby
from pathlib import Path

import pendulum
import requests
from configurator import Config
from pendulum import DateTime


def from_octopus(mpan, meter_serial, api_key, start=None, end=None):
    params = {'order_by': 'period'}
    for name, value in (('period_from', start), ('period_to', end)):
        if value is not None:
            params[name] = str(value)

    def get(url, **params):
        response = requests.get(url, auth=(api_key, ''), params=params)
        data = response.json()
        if response.status_code != 200:
            raise Exception(repr(data))
        return data

    data = get(
        f"https://api.octopus.energy/v1/electricity-meter-points/{mpan}/meters/{meter_serial}/consumption/",
        **params
    )
    while True:
        for reading in data['results']:
            yield reading
        if data['next']:
            data = get(data['next'])
        else:
            break


READINGS_PER_DAY = int(24*60/30)


def download(mpan, meter_serial, api_key, target, start: DateTime = None, end: DateTime = None):
    for date, group in groupby(from_octopus(mpan, meter_serial, api_key, start, end),
                               lambda row: pendulum.parse(row['interval_start']).date()):
        readings = tuple(group)
        suffix = ''
        if len(readings) != READINGS_PER_DAY:
            print(f'{date} is suspect as {len(readings)} readings instead of {READINGS_PER_DAY}')
            suffix = '-suspect'

        target_path = Path(target).expanduser() / f'octopus-{date}{suffix}.csv'
        with target_path.open('w') as target_file:
            headers = ['interval_start', 'interval_end', 'consumption']
            writer = csv.DictWriter(target_file, headers)
            writer.writerow({h: h for h in headers})
            for reading in readings:
                writer.writerow(reading)

        print(f'Downloaded {target_path}')


def date(text):
    return pendulum.parse(text, tz='Europe/London')


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--start', type=date)
    parser.add_argument('--end', type=date)
    return parser.parse_args()


if __name__ == '__main__':
    config = Config.from_path('config.yaml')
    args = parse_args()
    download(start=args.start.start_of('day') if args.start else None,
             end=args.end.end_of('day') if args.end else None,
             target=config.directories.storage,
             **config.octopus.api.data)
