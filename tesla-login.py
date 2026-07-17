import logging
import subprocess
from argparse import ArgumentParser
from pathlib import Path

from configurator import Config
from teslapy import Tesla

from common import add_log_level, configure_logging

TESLA_AUTH_URL = 'https://github.com/adriankumpf/tesla_auth'
TESLA_AUTH_PATH = Path('tesla_auth')


def main():
    parser = ArgumentParser()
    add_log_level(parser)
    args = parser.parse_args()
    configure_logging(args.log_level)

    if not TESLA_AUTH_PATH.exists():
        raise SystemExit(f'{TESLA_AUTH_PATH} not found, download it from {TESLA_AUTH_URL}')

    logging.info('Launching tesla_auth; log in, then copy the refresh token from its window.')
    subprocess.run([TESLA_AUTH_PATH], check=True)
    refresh_token = input('Enter SSO refresh token: ').strip()

    config = Config.from_path('config.yaml')
    tesla = Tesla(config.tesla.email)
    tesla.refresh_token(refresh_token=refresh_token)
    battery, = tesla.battery_list()
    logging.info(f'Login OK, found: {battery}')


if __name__ == '__main__':
    main()
