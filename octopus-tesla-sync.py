import logging
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from pprint import pformat

from configurator import Config
from gql.transport.aiohttp import log as gql_logger

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
    parser.add_argument('--run-every', type=int)

    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    api_key = config.octopus.api_key
    account = config.octopus.account

    graphql_client = OctopusGraphQLClient(api_key)
    dumper = DiffDumper(Path(config.directories.storage).expanduser(), prefix='octopus-dispatches')

    run = Run(record_octopus_dispatches)(graphql_client, account, dumper)

    if args.run_every:
        run.every(minutes=args.run_every)
    else:
        run.once()


if __name__ == '__main__':
    main()
