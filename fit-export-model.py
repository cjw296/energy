"""Compare FiT deemed export payments with what metered (SEG) export would have paid.

Deemed export pays 50% of generation at the FiT export rate. Metered export would pay only
the kWh actually sent to the grid, at the SEG price, with everything else (self-consumption,
Powerwalls, zappi) unchanged. Measured export comes from the Tesla gateway's 5-minute data
(tesla-DATE.csv), cross-checked against the zappi's clamps (zappi-DATE.csv); FiT generation
and deemed payments come from the Solar sheet of the utilities spreadsheet. Download the data
first; see "Data downloads" in AGENTS.md. Years without a full year of Tesla data are partial.

Usage, from the directory containing config.yaml:

    uv run python fit-export-model.py path/to/utilities.ods
    uv run python fit-export-model.py utilities.ods --price 13 --price 20
"""
from argparse import ArgumentParser
from pathlib import Path

import pandas as pd
from configurator import Config

from common import root_from
from fitmodel import fit_payments, load_tesla, load_zappi, yearly

ENERGY = ['tesla_days', 'zappi_days', 'generated', 'solar_tesla', 'solar_zappi', 'export', 'export_zappi',
          'imported', 'ev_solar', 'ev_grid', 'batt_from_solar', 'batt_charge']


def main():
    parser = ArgumentParser()
    parser.add_argument('spreadsheet', type=Path)
    parser.add_argument('--price', type=float, action='append', dest='prices',
                        help='SEG price in p/kWh; repeatable; default: 12, 13, 15 and 16')
    args = parser.parse_args()

    root = root_from(Config.from_path('config.yaml'))
    fit = fit_payments(pd.read_excel(args.spreadsheet.expanduser(), sheet_name='Solar', engine='odf'))
    out = yearly(load_tesla(root), load_zappi(root), fit, args.prices or [12, 13, 15, 16])

    pd.set_option('display.width', 250)
    print('Energy (kWh) by FiT year (April to March):')
    print(out[ENERGY].round(0).to_string())
    print('\nExport value (£) by FiT year:')
    metered = [column for column in out.columns if column.startswith('metered_')]
    print(out[['export_pct', 'deemed_rate', 'deemed_paid', *metered]].round(1).to_string())


if __name__ == '__main__':
    main()
