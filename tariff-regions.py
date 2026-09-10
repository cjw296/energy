"""Compare a Kraken-platform tariff's rates across GSP regions.

Octopus, EDF and E.ON Next all run on Kraken, which publishes each product at
/v1/products/{code}/ with a tariff per GSP region (_A.._P). Prints direct-debit, inc-VAT
unit rates and standing charges in pence. No auth needed.

Field names are the supplier's own: for two-rate EV tariffs, `standard_unit_rate` is the
peak rate on E.ON Next but the off-peak rate on EDF.

Usage:

    uv run python tariff-regions.py octopus:IOG-SMB-FIX-12M-26-09-02 eon:NEXT_DRIVE_SMART_V7_3
    uv run python tariff-regions.py --region _A --region _C edf:EDF_EV_FIX_GOELEC_12M_V2_HH
"""
from argparse import ArgumentParser

from kraken import parse_product, product, regional_rates


def main():
    parser = ArgumentParser()
    parser.add_argument('products', nargs='+', type=parse_product, metavar='SUPPLIER:CODE')
    parser.add_argument('--region', action='append', dest='regions',
                        help='GSP region such as _H; repeatable; default: all')
    args = parser.parse_args()
    for supplier, code in args.products:
        data = product(supplier, code)
        print(f'== {supplier} {code}: {data.get("display_name")}')
        for region, rates in regional_rates(data, args.regions).items():
            print(f'  {region} ' + '  '.join(f'{name}={value:.3f}' for name, value in rates.items()))


if __name__ == '__main__':
    main()
