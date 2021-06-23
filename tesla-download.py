import os
from argparse import ArgumentParser, FileType
from csv import DictWriter
from datetime import datetime, date, timedelta
from getpass import getpass


from teslapy import Tesla


def parse_date(text):
    return datetime.strptime(text, '%Y-%m-%d').date()


def tesla_end_dates(start, end):
    start = start or end or date.today()
    end = end or start or date.today()
    current = min(start, end)
    end = max(start, end)
    while current <= end:
        # This appears to need to match up with the installation timezone...
        yield str(current)+'T23:59:00+01:00'
        current += timedelta(days=1)


def main():
    parser = ArgumentParser()
    parser.add_argument('username', help='Tesla username, usually an email address')
    parser.add_argument('--output', type=FileType('w'), default='-')
    parser.add_argument('--start', type=parse_date)
    parser.add_argument('--end', type=parse_date)
    args = parser.parse_args()

    password = os.environ.get('TESLA_PASSWORD')
    if not password:
        password = getpass(f'Password for {args.username}:')

    tesla = Tesla(args.username, password)

    writer = DictWriter(args.output,
                        fieldnames=['battery_id', 'serial_number', 'timestamp', 'solar_power'])
    writer.writeheader()

    for battery in tesla.battery_list():
        battery_id = battery['id']
        for end_date in tesla_end_dates(args.start, args.end):
            data = battery.get_calendar_history_data(kind='power',
                                                     end_date=end_date)

            assert data["installation_time_zone"] == "Europe/London"

            serial_number = data['serial_number']
            for row in data['time_series']:
                writer.writerow(dict(battery_id=battery_id,
                                     serial_number=serial_number,
                                     timestamp=row['timestamp'],
                                     solar_power=row['solar_power']))

if __name__ == '__main__':
    main()
