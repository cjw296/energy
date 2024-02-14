import csv
import logging
from argparse import ArgumentParser
from itertools import groupby
from pathlib import Path

import pendulum
from configurator import Config
from pendulum import DateTime

from common import add_log_level, configure_logging
from octopus import OctopusRESTClient


def from_octopus(
        client,
        mpan,
        meter_serials,
        endpoint: str,
        start=None,
        end=None,
):
    params = {'order_by': 'period'}
    for name, value in (('period_from', start), ('period_to', end)):
        if value is not None:
            params[name] = str(value)
    for meter_serial in meter_serials:
        data = client.get(f"/{endpoint}/{mpan}/meters/{meter_serial}/consumption/", **params)
        while True:
            for reading in data['results']:
                reading['meter_serial'] = meter_serial
                yield reading
            if data['next']:
                data = client.get(data['next'])
            else:
                break


READINGS_PER_DAY = int(24*60/30)


def extract_tz_offset(row):
    return pendulum.parse(row['interval_start']).utcoffset().total_seconds()


def expected_readings_per_day(readings):
    first_offset = extract_tz_offset(readings[0])
    last_offset = extract_tz_offset(readings[-1])
    # take DST changes into account:
    return READINGS_PER_DAY - (last_offset - first_offset)/60/30


def download(
        account,
        api_key,
        target,
        start: DateTime = None,
        end: DateTime = None,
        endpoint: str = 'electricity-meter-points',
        meter_serial: str = None,
):

    client = OctopusRESTClient(api_key)
    mpxn_type = 'mpan' if endpoint.startswith('electricity') else 'mprn'
    meter_point = client.meter_point(account, endpoint.replace('-', '_'))
    if meter_point is None:
        logging.error(f'No {endpoint} in account {account}')
        return
    mpxn = meter_point[mpxn_type]

    if meter_serial:
        serial_numbers = [meter_serial]
    else:
        serial_numbers = [m['serial_number'] for m in meter_point['meters']]

    for date, group in groupby(
            from_octopus(
                client,
                mpxn,
                serial_numbers,
                endpoint,
                start,
                end
            ),
            lambda row: pendulum.parse(row['interval_start']).date()
    ):
        readings = sorted(group, key=lambda row: pendulum.parse(row['interval_start']))
        suffix = ''
        if len(readings) != expected_readings_per_day(readings):
            logging.warning(
                f'{date} is suspect as {len(readings)} readings instead of {READINGS_PER_DAY}'
            )
            suffix = '-suspect'

        target_path = Path(target).expanduser() / f'octopus-{date}{suffix}.csv'
        with target_path.open('w') as target_file:
            headers = [
                mpxn_type, 'meter_serial', 'interval_start', 'interval_end', 'consumption'
            ]
            writer = csv.DictWriter(target_file, headers)
            writer.writerow({h: h for h in headers})
            for reading in readings:
                reading[mpxn_type] = mpxn
                writer.writerow(reading)

        logging.info(f'Downloaded {target_path}')


def date(text):
    return pendulum.parse(text, tz='Europe/London')


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--start', type=date)
    parser.add_argument('--end', type=date)
    add_log_level(parser)
    return parser.parse_args()


if __name__ == '__main__':
    config = Config.from_path('config.yaml')
    args = parse_args()
    configure_logging(args.log_level)
    download(start=args.start.start_of('day') if args.start else None,
             end=args.end.end_of('day') if args.end else None,
             target=config.directories.storage,
             **config.octopus.data)
