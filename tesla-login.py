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
    # `authorized` is just `bool(access_token)`, true even for a stale cached
    # token, so it won't trigger the interactive flow on its own.
    tesla.token = {}
    del tesla.access_token
    tesla.fetch_token()
    battery, = tesla.battery_list()
    logging.info(f'Login OK, found: {battery}')


if __name__ == '__main__':
    main()
