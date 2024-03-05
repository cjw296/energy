import logging
from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pprint import pformat
from zoneinfo import ZoneInfo

from configurator import Config
from gql.transport.aiohttp import log as gql_logger
from pandas import Timestamp
from teslapy import Tesla, Battery

from common import DiffDumper, add_log_level, configure_logging, Run, diff, root_from
from octopus import OctopusGraphQLClient
from tesla import installation_time_zone
from schedule import make_seasons_and_energy_charges

gql_logger.setLevel(logging.WARNING)


def make_demand_charges() -> dict:
    return {
        "ALL": {
            "ALL": 0
        },
        "Summer": {},
        "Winter": {}
    }


@dataclass(repr=False)
class Syncer:
    graphql_client: OctopusGraphQLClient
    account: str
    dumper: DiffDumper | None
    battery: Battery
    timezone: ZoneInfo
    sync: bool
    force: bool
    tesla_tariff: dict | None = None

    def __call__(self):
        now = Timestamp(datetime.now().astimezone())
        dispatches = self.graphql_client.dispatches(self.account)

        # get the octopus tariff
        tariff = self.graphql_client.tariff(self.account)
        logging.debug(pformat(tariff))
        unit_rates_schedule = tariff.pop('unitRates')

        # dump to json if things have changed:
        if self.dumper is not None:
            self.dumper.update(
                {'dispatches': dispatches, 'unit_rates': unit_rates_schedule, 'agreement': tariff},
                force=self.force
            )

        if not self.sync:
            logging.warning('not updating Tesla schedule!')
            return

        # get the current tesla tariff config:
        if not self.tesla_tariff:
            self.tesla_tariff = self.battery.get_tariff()

        # build the tariff we think we need:
        required_tariff = deepcopy(self.tesla_tariff)
        required_tariff['code'] = tariff['tariffCode']
        required_tariff['utility'] = 'Octopus'
        required_tariff['name'] = tariff['fullName']
        required_tariff['demand_charges'] = make_demand_charges()
        required_tariff.update(
            make_seasons_and_energy_charges(now, unit_rates_schedule, dispatches, self.timezone)
        )
        # update the tariff via the tesla API if it's changed:
        if self.tesla_tariff != required_tariff or self.force:
            planned_dispatches = dispatches['plannedDispatches']
            logging.info(f'Planned dispatches:\n{pformat(planned_dispatches, sort_dicts=False)}')
            self.battery.set_tariff(required_tariff)
            diff_text = diff(self.tesla_tariff, required_tariff, )
            logging.info(f'Tesla tariff updated:\n{diff_text}')
            self.tesla_tariff = self.battery.get_tariff()


def main():
    parser = ArgumentParser()
    add_log_level(parser)
    parser.add_argument('--run-every', type=int)
    parser.add_argument('--no-dump', action='store_false', dest='dump')
    parser.add_argument('--no-sync', action='store_false', dest='sync', help='never sync')
    parser.add_argument('--force', action='store_true', help='force dump and sync')

    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    storage = root_from(config)
    api_key = config.octopus.api_key
    account = config.octopus.account

    graphql_client = OctopusGraphQLClient(api_key)
    dumper = DiffDumper(storage, prefix='octopus-dispatches') if args.dump else None

    tesla = Tesla(config.tesla.email)
    battery, = tesla.battery_list()

    syncer = Syncer(
        graphql_client,
        account,
        dumper,
        battery,
        installation_time_zone(battery),
        args.sync,
        args.force,
    )

    run = Run(syncer)

    if args.run_every:
        run.every(minutes=args.run_every)
    else:
        run.once()


if __name__ == '__main__':
    main()
