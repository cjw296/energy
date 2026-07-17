import logging
import subprocess
from argparse import ArgumentParser
from pathlib import Path

from configurator import Config
from teslapy import Tesla

from common import add_log_level, configure_logging
from tesla import parse_tesla_auth_output

TESLA_AUTH_URL = 'https://github.com/adriankumpf/tesla_auth'
TESLA_AUTH_PATH = Path('tesla_auth')


def main():
    parser = ArgumentParser()
    add_log_level(parser)
    args = parser.parse_args()
    configure_logging(args.log_level)

    if not TESLA_AUTH_PATH.exists():
        raise SystemExit(f'{TESLA_AUTH_PATH} not found, download it from {TESLA_AUTH_URL}')

    logging.info('Launching tesla_auth, log in when the window appears.')
    # a bare filename is looked up on PATH by execvp, not resolved against cwd
    result = subprocess.run(
        [TESLA_AUTH_PATH.resolve()], check=True, capture_output=True, text=True
    )
    token = parse_tesla_auth_output(result.stdout)

    config = Config.from_path('config.yaml')
    tesla = Tesla(config.tesla.email)
    # An immediate refresh_token() call gets 403'd by the Owner API even over
    # HTTP/2; tesla_auth's freshly issued access token works, so use it as-is
    # and let teslapy refresh only once it's actually near expiry:
    # https://github.com/tdorssers/TeslaPy/issues/175
    tesla.token = token
    tesla._token_updater()
    battery, = tesla.battery_list()
    logging.info(f'Login OK, found: {battery}')


if __name__ == '__main__':
    main()
