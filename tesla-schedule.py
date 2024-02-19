import logging
from argparse import ArgumentParser
from pathlib import Path

from configurator import Config
from gql.transport.aiohttp import log as gql_logger
from teslapy import Tesla

from common import DiffDumper, add_log_level, configure_logging

gql_logger.setLevel(logging.WARNING)


def main():
    parser = ArgumentParser()
    add_log_level(parser)

    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    tesla = Tesla(config.tesla.email)
    battery, = tesla.battery_list()
    dumper = DiffDumper(Path(config.directories.storage).expanduser(), prefix='tesla-schedule')
    tariff = battery.get_tariff()
    logging.info(tariff)
    dumper.update(tariff)


if __name__ == '__main__':
    main()
