import logging
from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from pprint import pformat

from configurator import Config
from gql.transport.aiohttp import log as gql_logger
from teslapy import Tesla, Battery

from common import DiffDumper, add_log_level, configure_logging, Run, diff
from octopus import OctopusGraphQLClient

gql_logger.setLevel(logging.WARNING)


CHEAP_KEY = "SUPER_OFF_PEAK"
EXPENSIVE_KEY = "ON_PEAK"


def price_in_pounds(price_in_pence: float) -> float:
    return round(price_in_pence/100, 2)


def make_demand_charges() -> dict:
    return {
        "ALL": {
            "ALL": 0
        },
        "Summer": {},
        "Winter": {}
    }


def make_energy_charges(cheap: float, expensive: float):
    return {
        "ALL": {
            "ALL": 0
        },
        "Summer": {
            EXPENSIVE_KEY: price_in_pounds(expensive),
            CHEAP_KEY: price_in_pounds(cheap),
        },
        "Winter": {}
    }


@dataclass
class Syncer:
    graphql_client: OctopusGraphQLClient
    account: str
    dumper: DiffDumper | None
    battery: Battery
    tesla_tariff: dict | None = None

    def __call__(self):
        dispatches = self.graphql_client.dispatches(self.account)

        # get the octopus tariff
        tariff = self.graphql_client.tariff(self.account)
        logging.info(pformat(tariff))
        unit_rates_schedule = tariff.pop('unitRates')

        # figure out what the prices are:
        unit_rates = sorted({float(r['value']) for r in unit_rates_schedule})
        assert len(unit_rates) == 2, f'Unexpected number of rates: {unit_rates}'
        cheap, expensive = unit_rates

        # dump to json if things have changed:
        if self.dumper is not None:
            self.dumper.update(
                {'dispatches': dispatches, 'unit_rates': unit_rates_schedule, 'agreement': tariff}
            )

        # get the current tesla tariff config:
        if not self.tesla_tariff:
            self.tesla_tariff = self.battery.get_tariff()

        # build the tariff we think we need:
        required_tariff = deepcopy(self.tesla_tariff)
        required_tariff['code'] = tariff['tariffCode']
        required_tariff['utility'] = 'Octopus'
        required_tariff['name'] = tariff['fullName']
        required_tariff['demand_charges'] = make_demand_charges()
        required_tariff['energy_charges'] = make_energy_charges(cheap, expensive)

        # update the tariff via the tesla API if it's changed:
        if self.tesla_tariff != required_tariff:
            self.battery.set_tariff(required_tariff)
            diff_text = diff(self.tesla_tariff, required_tariff, )
            logging.info(f'Tesla tariff updated:\n{diff_text}')
            self.tesla_tariff = self.battery.get_tariff()


def main():
    parser = ArgumentParser()
    add_log_level(parser)
    parser.add_argument('--run-every', type=int)
    parser.add_argument('--no-dump', action='store_false', dest='dump')

    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    storage = Path(config.directories.storage).expanduser()
    api_key = config.octopus.api_key
    account = config.octopus.account

    graphql_client = OctopusGraphQLClient(api_key)
    dumper = DiffDumper(storage, prefix='octopus-dispatches') if args.dump else None

    tesla = Tesla(config.tesla.email)
    battery, = tesla.battery_list()

    syncer = Syncer(graphql_client, account, dumper, battery)

    run = Run(syncer)

    if args.run_every:
        run.every(minutes=args.run_every)
    else:
        run.once()


if __name__ == '__main__':
    main()
