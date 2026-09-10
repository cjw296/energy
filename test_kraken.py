from argparse import ArgumentTypeError
from functools import partial

import pook
from requests import HTTPError
from testfixtures import ShouldRaise, compare as compare_

from kraken import parse_product, product, regional_rates

compare = partial(compare_, strict=True)

PRODUCT = {
    'code': 'IOG-SMB-FIX-12M-26-09-02',
    'display_name': 'Intelligent Octopus Go 12M Fixed',
    'single_register_electricity_tariffs': {},
    'dual_register_electricity_tariffs': {},
    'four_rate_ev_electricity_tariffs': {
        '_A': {'direct_debit_monthly': {
            'code': 'E-1R-IOG-SMB-FIX-12M-26-09-02-A',
            'standing_charge_exc_vat': 51.3257,
            'standing_charge_inc_vat': 53.892,
            'night_unit_rate_inc_vat': 8.0,
            'exit_fees_inc_vat': 0,
            'links': [],
        }},
        '_C': {'direct_debit_monthly': {
            'code': 'E-1R-IOG-SMB-FIX-12M-26-09-02-C',
            'standing_charge_inc_vat': 49.407,
            'night_unit_rate_inc_vat': 8.0,
            'day_unit_rate_inc_vat': 34.72,
        }},
    },
    'single_register_gas_tariffs': {'_C': {'direct_debit_monthly': {'standard_unit_rate_inc_vat': 6.0}}},
}


def test_regional_rates_all_regions():
    compare(regional_rates(PRODUCT), expected={
        '_A': {'standing_charge': 53.892, 'night_unit_rate': 8.0},
        '_C': {'standing_charge': 49.407, 'night_unit_rate': 8.0, 'day_unit_rate': 34.72},
    })


def test_regional_rates_chosen_regions_skips_missing():
    compare(regional_rates(PRODUCT, ['_C', '_Z']), expected={
        '_C': {'standing_charge': 49.407, 'night_unit_rate': 8.0, 'day_unit_rate': 34.72},
    })


def test_regional_rates_varying():
    data = {'single_register_electricity_tariffs': {
        '_C': {'varying': {'standard_unit_rate_inc_vat': 26.47}},
    }}
    compare(regional_rates(data), expected={'_C': {'standard_unit_rate': 26.47}})


def test_parse_product():
    compare(parse_product('eon:NEXT_DRIVE_SMART_V7_3'), expected=('eon', 'NEXT_DRIVE_SMART_V7_3'))


def test_parse_product_unknown_supplier():
    with ShouldRaise(ArgumentTypeError(
        "expected SUPPLIER:CODE with SUPPLIER one of octopus, edf, eon, got 'bg:EV_POWER'"
    )):
        parse_product('bg:EV_POWER')


def test_parse_product_missing_code():
    with ShouldRaise(ArgumentTypeError(
        "expected SUPPLIER:CODE with SUPPLIER one of octopus, edf, eon, got 'edf'"
    )):
        parse_product('edf')


def test_product():
    with pook.use():
        pook.get('https://api.edfgb-kraken.energy/v1/products/EDF_EV_FIX_GOELEC_12M_V2_HH/').reply(200).json(PRODUCT)
        compare(product('edf', 'EDF_EV_FIX_GOELEC_12M_V2_HH'), expected=PRODUCT)
        compare(pook.isdone(), expected=True)


def test_product_not_found():
    with pook.use():
        pook.get('https://api.octopus.energy/v1/products/NOPE/').reply(404).json({'detail': 'Not found.'})
        with ShouldRaise(HTTPError):
            product('octopus', 'NOPE')
