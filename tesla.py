import csv
import json
import logging
from datetime import timedelta
from pathlib import Path
from time import sleep
from typing import Iterator
from zoneinfo import ZoneInfo

from configurator import Config
from pandas import Timestamp, Timedelta, date_range
from requests import HTTPError
from teslapy import Tesla, Battery

from common import main, collect, json_from_paths


def with_tz(dt: Timestamp, tz: ZoneInfo) -> Timestamp:
    return Timestamp(year=dt.year, month=dt.month, day=dt.day, unit='m', tz=tz)


def tesla_formatted_dt(dt: Timestamp) -> str:
    return dt.isoformat()


def tesla_end_dates(
        start: Timestamp, end: Timestamp, tz: ZoneInfo
) -> Iterator[tuple[Timestamp, Timestamp]]:
    current = with_tz(min(start, end), tz)
    end = with_tz(max(start, end), tz)
    while current <= end:
        yield current, current.replace(hour=23, minute=59, second=59)
        current += timedelta(days=1)


def call_with_retry(c, *args, **kw):
    while True:
        try:
            return c(*args, **kw)
        except HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers['retry-after'])
                logging.warning(f'HTTP 429, sleeping for {retry_after}s')
                sleep(retry_after)
            else:
                raise


PATTERN = 'tesla-%Y-%m-%d.json'
EXPECTED_MEASUREMENTS = 24*60/5


def check_measurement_count(data, end_date):
    time_series = data['time_series']
    actual = len(time_series)
    if actual != EXPECTED_MEASUREMENTS:
        earliest = time_series[0]['timestamp']
        latest = time_series[-1]['timestamp']
        missing = EXPECTED_MEASUREMENTS - actual
        logging.warning(
            f'Expected {EXPECTED_MEASUREMENTS}, '
            f'got {actual} ({missing * 5} mins missing), '
            f'earliest found: {earliest}, '
            f'latest found: {latest}, '
            f'end_date={end_date}'
        )
        if missing < 10:
            earliest_ts = Timestamp(earliest)
            current = Timestamp(year=earliest_ts.year, month=earliest_ts.month, day=earliest_ts.day, tz=earliest_ts.tz)
            bad = set(date_range(current, current+Timedelta(days=1), freq='5min', inclusive='left'))
            for row in time_series:
                bad.remove(Timestamp(row['timestamp']))
            if bad:
                logging.warning('Missing: ' + ', '.join(str(b) for b in sorted(bad)))


def download(config: Config, start: Timestamp, end: Timestamp, root: Path) -> None:
    tesla = Tesla(config.tesla.email)
    for i, battery in enumerate(call_with_retry(tesla.battery_list)):
        assert i == 0, 'more than one battery found!'
        installation_time_zone_ = installation_time_zone(battery)
        for date, end_date in tesla_end_dates(start, end, installation_time_zone_):
            data = call_with_retry(
                battery.get_calendar_history_data,
                kind='power',
                end_date=tesla_formatted_dt(end_date),
                period='day'
            )
            if not data:
                raise ValueError(f'No data for {end_date=}')
            path = root / date.strftime(PATTERN)
            path.write_text(json.dumps({'battery': battery, 'data': data}))
            logging.info(f'Downloaded {path}')
            check_measurement_count(data, end_date)


def check(config: Config, start: Timestamp, end: Timestamp, root: Path) -> None:
    for json_path, data in json_from_paths(root, PATTERN, start, end):
        check_measurement_count(data['data'], end_date=json_path)


def json_to_csv(config: Config, start: Timestamp, end: Timestamp, root: Path) -> None:
    for json_path, all_data in json_from_paths(root, PATTERN, start, end):
        data = all_data['data']
        rows = []
        fieldnames = ['timestamp']
        for row in data['time_series']:
            fieldnames.extend(name for name in row if name not in fieldnames)
            logging.debug(f'{row}')
            rows.append(row)

        csv_path = json_path.with_suffix('.csv')
        with csv_path.open('w') as target:
            writer = csv.DictWriter(target, fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        logging.info(f'Wrote {csv_path}')


def battery_site_config(battery: Battery) -> dict:
    return battery.api('SITE_CONFIG')['response']


def installation_time_zone(battery: Battery) -> ZoneInfo:
    return ZoneInfo(battery_site_config(battery)['installation_time_zone'])


if __name__ == '__main__':
    main(collect(download, check, json_to_csv), PATTERN)
