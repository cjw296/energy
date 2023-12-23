import csv
import json
import logging
import sys
from argparse import ArgumentParser
from pathlib import Path
from pprint import pprint, pformat

import requests
from configurator import Config
from pandas import date_range, Timestamp
from requests.auth import HTTPDigestAuth


# lifted from https://github.com/ashleypittman/mec/blob/master/get_zappi_history.py
# in combination with https://github.com/twonk/MyEnergi-App-Api
FIELD_NAMES = {'gep': 'Generation',
               'gen': 'Generated Negative',
               'h1d': 'Phase 1, Zappi diverted',
               'h1b': 'Phase 1, Zappi imported',
               'h2d': 'Phase 2, Zappi diverted',
               'h2b': 'Phase 2, Zappi imported',
               'h3d': 'Phase 3, Zappi diverted',
               'h3b': 'Phase 3, Zappi imported',
               'imp': 'Imported',
               'exp': 'Exported'}


def path_for_date(root: Path, ts: Timestamp) -> Path:
    return root / ts.strftime('zappi-%Y-%m-%d.json')


def download(config: Config, start: Timestamp, end: Timestamp, root: Path) -> None:
    myenergi_config = config.myenergi
    session = requests.Session()
    session.auth = HTTPDigestAuth(myenergi_config.hub_serial, myenergi_config.api_key)
    session.headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}

    response = session.get(f'https://director.myenergi.net/cgi-jstatus-*')
    response.raise_for_status()
    server = response.headers['x_myenergi-asn']
    logging.debug(pformat(response.json()))

    url_template = f'https://{server}/cgi-jday-Z{myenergi_config.zappi_serial}-%Y-%m-%d'

    for ts in date_range(start=end, end=start, freq='-1D'):
        response = session.get(ts.strftime(url_template))
        response.raise_for_status()
        path = path_for_date(root, ts)
        path.write_text(response.text)
        logging.info(f'Downloaded {path}')


def json_to_csv(config: Config, start: Timestamp, end: Timestamp, root: Path) -> None:
    myenergi_config = config.myenergi
    zappi_key = f'U{myenergi_config.zappi_serial}'
    for ts in date_range(start=end, end=start, freq='-1D'):
        json_path = path_for_date(root, ts)
        if not json_path.exists():
            logging.warning(f'{json_path} does not exist')
            continue
        data = json.loads(json_path.read_bytes())

        fieldnames = {'datetime': True}
        rows = []

        for row in data[zappi_key]:
            date = Timestamp(
                year=row.pop('yr'),
                month=row.pop('mon'),
                day=row.pop('dom'),
                hour=row.pop('hr', 0),
                minute=row.pop('min', 0)
            )
            assert date.strftime('%a') == row.pop('dow')
            row['datetime'] = date.isoformat()
            row['volts'] = row.get('v1', 0) / 10
            for key in ('imp', 'h1b', 'exp'):
                joules = row.get(key, 0)
                row[f'{key}_kw'] = (joules / 60) / 1000

            logging.debug(f'{row}')
            fieldnames.update({name: True for name in row.keys()})
            rows.append(row)

        csv_path = json_path.with_suffix('.csv')
        with csv_path.open('w') as target:
            writer = csv.DictWriter(target, fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        logging.info(f'Wrote {csv_path}')


actions = {action.__name__.replace('_', '-'): action
           for action in (download, json_to_csv)}


if __name__ == '__main__':
    log_levels = logging.getLevelNamesMapping()
    parser = ArgumentParser()
    parser.add_argument('action', choices=actions.keys())
    parser.add_argument('--log-level',
                        choices=[name.lower() for name in log_levels],
                        default='info')
    parser.add_argument('--start', type=Timestamp, help='YY-mm-dd', required=True)
    parser.add_argument('--end', type=Timestamp, help='YY-mm-dd', required=True)
    args = parser.parse_args()

    logging.basicConfig(level=log_levels[args.log_level.upper()], stream=sys.stdout)
    logging.raiseExceptions = False

    config = Config.from_path('config.yaml')
    start = min(args.start, args.end)
    end = max(args.start, args.end)
    root = Path(config.directories.storage).expanduser()
    actions[args.action](config, start, end, root)
