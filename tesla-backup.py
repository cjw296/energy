import logging
import sys
from argparse import ArgumentParser

from configurator import Config
from teslapy import Tesla

from common import add_log_level, configure_logging


def main():
    parser = ArgumentParser()
    parser.add_argument('set_backup_reserve_percent', nargs='?')

    add_log_level(parser)
    args = parser.parse_args()

    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    tesla = Tesla(config.tesla.email)
    battery, = tesla.battery_list()

    info = battery.api('SITE_CONFIG')['response']
    logging.debug(f'{info=}')
    backup_reserve_percent = info['backup_reserve_percent']

    live_data = battery.api('SITE_DATA')['response']
    logging.debug(f'{live_data=}')
    current = live_data['percentage_charged']
    load = live_data['load_power']

    remaining = battery.api('ENERGY_SITE_BACKUP_TIME_REMAINING')['response']['time_remaining_hours']

    logging.info(
        f'{current=:.0f}%, {remaining:.1f}hrs, {load/1000:.1f}kW, {backup_reserve_percent=:.0f}%'
    )

    if args.set_backup_reserve_percent is not None:
        try:
            to_set = int(args.set_backup_reserve_percent)
        except ValueError:
            assert args.set_backup_reserve_percent.lower() == 'current', 'must be int or current'
            to_set = current
        logging.info(f'setting to {to_set:.0f}%')
        battery.set_backup_reserve_percent(to_set)


if __name__ == '__main__':
    main()

