import logging
from argparse import ArgumentParser

from configurator import Config
from teslapy import Tesla

from common import add_log_level, configure_logging


def main():
    parser = ArgumentParser()
    add_log_level(parser)
    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    tesla = Tesla(config.tesla.email)
    battery, = tesla.battery_list()
    logging.info(f'Login OK, found: {battery}')


if __name__ == '__main__':
    main()
