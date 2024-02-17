import logging
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from pprint import pformat

from configurator import Config
from gql.transport.aiohttp import log as gql_logger
from teslapy import Tesla

from common import DiffDumper, add_log_level, configure_logging, Run
from octopus import OctopusGraphQLClient

gql_logger.setLevel(logging.WARNING)


def record_octopus_dispatches(
        graphql_client: OctopusGraphQLClient,
        account: str,
        dumper: DiffDumper,
):
    dispatches = graphql_client.dispatches(account)
    unit_rates = graphql_client.unit_rates(account)
    logging.info(pformat(dispatches))
    dumper.update(
        {'now': datetime.now().isoformat(), 'dispatches': dispatches, 'unit_rates': unit_rates}
    )


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
