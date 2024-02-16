import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from pprint import pprint, pformat

from configurator import Config
from gql import gql

from common import DiffDumper, add_log_level, configure_logging, Run
from octopus import OctopusRESTClient, OctopusGraphQLClient

from gql.transport.aiohttp import log as gql_logger
gql_logger.setLevel(logging.WARNING)


def get_octopus_dispatches(
        graphql_client: OctopusGraphQLClient,
        account: str,
        dumper: DiffDumper,
):
    dispatches = graphql_client.query(
        "getCombinedData",
        query = '''
                query getCombinedData($accountNumber: String!) {
                    plannedDispatches(accountNumber: $accountNumber) {
                        startDtUtc: startDt
                        endDtUtc: endDt
                        chargeKwh: delta
                        meta {
                            source
                            location
                        }
                    }
                    completedDispatches(accountNumber: $accountNumber) {
                        startDtUtc: startDt
                        endDtUtc: endDt
                        chargeKwh: delta
                        meta {
                            source
                            location
                        }
                    }
                }
            ''',
        params = {"accountNumber": account},
    )
    logging.info(pformat(dispatches))
    dumper.update(dispatches)


def main():
    parser = ArgumentParser()
    add_log_level(parser)
    parser.add_argument('--run-every', type=int)

    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    api_key = config.octopus.api_key
    account = config.octopus.account

    rest_client = OctopusRESTClient(api_key)
    graphql_client = OctopusGraphQLClient(api_key)
    dumper = DiffDumper(Path(config.directories.storage).expanduser(), prefix='octopus-dispatches')

    run = Run(get_octopus_dispatches)(graphql_client, account, dumper)

    if args.run_every:
        run.every(minutes=args.run_every)
    else:
        run.once()


if __name__ == '__main__':
    main()
