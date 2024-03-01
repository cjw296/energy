import logging
from argparse import ArgumentParser
from pathlib import Path

from configurator import Config
from gql.transport.aiohttp import log as gql_logger
from teslapy import Tesla

from common import DiffDumper, add_log_level, configure_logging, root_from

gql_logger.setLevel(logging.WARNING)


def main():
    parser = ArgumentParser()
    add_log_level(parser)

    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    tesla = Tesla(config.tesla.email)
    battery, = tesla.battery_list()
    dumper = DiffDumper(root_from(config), prefix='tesla-schedule')
    tariff = battery.get_tariff()
    logging.info(tariff)
    dumper.update(tariff)


if __name__ == '__main__':
    main()
