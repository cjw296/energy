import csv
import logging
from pathlib import Path
from pprint import pformat

import requests
from configurator import Config
from pandas import date_range, Timestamp
from requests.auth import HTTPDigestAuth

from common import main, collect, json_from_paths

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


PATTERN = 'zappi-%Y-%m-%d.json'


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
        path = root / ts.strftime(PATTERN)
        path.write_text(response.text)
        logging.info(f'Downloaded {path}')


def json_to_csv(config: Config, start: Timestamp, end: Timestamp, root: Path) -> None:
    myenergi_config = config.myenergi
    zappi_key = f'U{myenergi_config.zappi_serial}'
    for json_path, data in json_from_paths(root, PATTERN, start, end):

        fieldnames = {'datetime': True}
        rows = []

        for row in data[zappi_key]:
            date = Timestamp(
                year=row.pop('yr'),
                month=row.pop('mon'),
                day=row.pop('dom'),
                hour=row.pop('hr', 0),
                minute=row.pop('min', 0),
                tz='UTC',
            )
            assert date.strftime('%a') == row.pop('dow')
            row['datetime'] = date.isoformat()
            row['volts'] = row.get('v1', 0) / 10
            for key in ('imp', 'h1b', 'h1d', 'exp'):
                joules = row.setdefault(key, 0)
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


if __name__ == '__main__':
    main(collect(download, json_to_csv), PATTERN)
