"""Reconcile the electricity bills in the utilities spreadsheet against Octopus's billing API.

Each spreadsheet bill row (on the Electricity sheet, rows with a cost) is matched to the
Octopus charges whose consumption period ends after the previous bill row and on or before
this one. kWh, cost inc VAT and standing charge ex VAT are compared; reversed (rebilled)
charges are ignored. Rows before Octopus's first charge are skipped.

It then runs the tariff model check on bills from the current time-of-use agreement: pricing
the half-hourly import with night-window and completed-dispatch half hours at the night rate
and everything else at the day rate, which is what octopus-tesla-sync.py assumes, and
comparing that with what Octopus billed. octopus-tesla-sync.py runs the same check daily.

Usage, from the directory containing config.yaml:

    uv run python octopus-bill-rec.py path/to/utilities.ods
    uv run python octopus-bill-rec.py utilities.ods --mismatches-only
"""
from argparse import ArgumentParser
from pathlib import Path

import pandas as pd
from configurator import Config

from billcheck import model_checks
from billrec import HEADER, charges_from_transactions, format_rec, reconcile, sheet_bills, status
from common import root_from
from octopus import OctopusGraphQLClient, OctopusRESTClient


def main():
    parser = ArgumentParser()
    parser.add_argument('spreadsheet', type=Path)
    parser.add_argument('--mismatches-only', action='store_true')
    args = parser.parse_args()

    config = Config.from_path('config.yaml')
    client = OctopusGraphQLClient(config.octopus.api_key)
    charges = charges_from_transactions(client.transactions(config.octopus.account))
    sheet = pd.read_excel(args.spreadsheet.expanduser(), sheet_name='Electricity', engine='odf')

    print(HEADER)
    for rec in reconcile(sheet_bills(sheet), charges):
        if not (args.mismatches_only and status(rec) == 'ok'):
            print(format_rec(rec))

    print('\nTariff model check (current agreement):')
    rest = OctopusRESTClient(config.octopus.api_key)
    for check in model_checks(client, rest, config.octopus.account, root_from(config)):
        print(check)


if __name__ == '__main__':
    main()
