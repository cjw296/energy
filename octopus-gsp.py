"""Show the GSP region of the electricity meter point on the Octopus account.

Regional tariff prices are published per GSP group (_A.._P); tariff codes end in it
(e.g. E-1R-...-A). Only the MPAN's first two digits (the distributor ID) are printed.

Usage, from the directory containing config.yaml:

    uv run python octopus-gsp.py
"""
from configurator import Config

from octopus import OctopusRESTClient


def main():
    config = Config.from_path('config.yaml')
    client = OctopusRESTClient(config.octopus.api_key)
    point = client.meter_point(config.octopus.account, 'electricity_meter_points')
    print(f"MPAN {point['mpan'][:2]}…: GSP {client.gsp(point['mpan'])}")


if __name__ == '__main__':
    main()
