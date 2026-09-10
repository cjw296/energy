import json
from datetime import date, time
from decimal import Decimal
from functools import partial
from unittest.mock import Mock, call
from zoneinfo import ZoneInfo

from pandas import Timestamp
from testfixtures import LogCapture, ShouldRaise, compare as compare_

from billcheck import (
    DailyModelCheck, ModelCheck, RatePeriod, dispatch_half_hours, expected_usage_cost, in_window,
    load_dumps, model_checks, rate_periods,
)
from billrec import Charge

compare = partial(compare_, strict=True)

London = ZoneInfo('Europe/London')
NIGHT = (time(23, 30), time(5, 30))


def utc(text: str) -> Timestamp:
    return Timestamp(text, tz='UTC')


def unit_rate(rate_type: str, value: float, pre_vat: float, valid_from='2026-07-05T23:00:00+00:00', valid_to=None):
    return {'value': value, 'preVatValue': pre_vat, 'validFrom': valid_from, 'validTo': valid_to,
            'rateType': rate_type}


UNIT_RATES = [
    unit_rate('EV_DEVICE_PEAK', value=30.371355, pre_vat=28.9251),
    unit_rate('EV_DEVICE_OFF_PEAK', value=6.89997, pre_vat=6.5714),
    unit_rate('ECO7_NIGHT', value=6.89997, pre_vat=6.5714),
    unit_rate('ECO7_DAY', value=30.371355, pre_vat=28.9251),
]

RATES = [RatePeriod(start=utc('2026-07-05T23:00'), end=None, day=Decimal('28.9251'), night=Decimal('6.5714'))]

SCHEME = {
    'name': 'IOG_ECO7_TOU', 'timezone': 'Europe/London',
    'timeslots': [
        {'timeslot': 'ECO7_DAY', 'activeFrom': '05:30:00', 'activeTo': '23:30:00'},
        {'timeslot': 'ECO7_NIGHT', 'activeFrom': '23:30:00', 'activeTo': '05:30:00'},
    ],
}


def charge(start='2026-07-15', end='2026-08-31', usage_ex_vat='12.34') -> Charge:
    return Charge(start=date.fromisoformat(start), end=date.fromisoformat(end), kwh=Decimal('123.456'),
                  cost_inc_vat=Decimal('43.21'), standing_ex_vat=Decimal('12.35'),
                  usage_ex_vat=Decimal(usage_ex_vat))


def test_rate_periods():
    later = [unit_rate(t, value=1, pre_vat=2 if t == 'ECO7_DAY' else 1, valid_from='2026-10-01T00:00:00+01:00')
             for t in ('ECO7_DAY', 'ECO7_NIGHT')]
    compare(rate_periods(later + UNIT_RATES), expected=RATES + [
        RatePeriod(start=Timestamp('2026-10-01T00:00:00+01:00'), end=None, day=Decimal('2'), night=Decimal('1')),
    ])


def test_in_window():
    compare([in_window(time(h, m), NIGHT) for h, m in ((23, 29), (23, 30), (2, 0), (5, 29), (5, 30))],
            expected=[False, True, True, True, False])
    compare([in_window(time(h, m), (time(2), time(5))) for h, m in ((1, 59), (2, 0), (4, 59), (5, 0))],
            expected=[False, True, True, False])


def test_dispatch_half_hours():
    dumps = [
        {'dispatches': {'completedDispatches': [
            {'startDtUtc': '2026-08-10 11:00:00+00:00', 'endDtUtc': '2026-08-10 12:00:00+00:00'},
        ]}},
        {'dispatches': {'plannedDispatches': [], 'completedDispatches': [
            {'startDtUtc': '2026-08-10 11:30:00+00:00', 'endDtUtc': '2026-08-10 12:00:00+00:00'},
            {'startDtUtc': '2026-08-10 21:23:00+00:00', 'endDtUtc': '2026-08-10 22:00:00+00:00'},
        ]}},
        {'dispatches': {'plannedDispatches': []}},
        {},
    ]
    compare(dispatch_half_hours(dumps), expected={
        utc('2026-08-10T11:00'), utc('2026-08-10T11:30'), utc('2026-08-10T21:00'), utc('2026-08-10T21:30'),
    })


def test_load_dumps(tmp_path):
    for name, content in (('octopus-dispatches-2026-08-09-10-00-00.json', {'n': 1}),
                          ('octopus-dispatches-2026-08-11-23-59-59.json', {'n': 2}),
                          ('octopus-dispatches-2026-08-12-00-00-00.json', {'n': 3}),
                          ('other-2026-08-10.json', {'n': 4})):
        (tmp_path / name).write_text(json.dumps(content))
    compare(load_dumps(tmp_path, date(2026, 8, 9), date(2026, 8, 11)), expected=[{'n': 1}, {'n': 2}])


def test_expected_usage_cost():
    consumption = {
        utc('2026-08-10T00:00'): 1.0,   # 01:00 BST, night
        Timestamp('2026-08-10T12:00:00+01:00'): 2.0,  # dispatch
        utc('2026-08-10T12:00'): 0.5,   # 13:00 BST, day
        utc('2026-08-10T22:30'): 1.0,   # 23:30 BST, night starts
        utc('2026-08-10T04:30'): 1.0,   # 05:30 BST, day starts
    }
    compare(expected_usage_cost(consumption, {utc('2026-08-10T11:00')}, NIGHT, London, RATES),
            expected=Decimal('69.67325'))


def test_expected_usage_cost_rate_change():
    rates = [
        RatePeriod(start=utc('2026-07-05T23:00'), end=utc('2026-08-01T00:00'), day=Decimal('30'), night=Decimal('7')),
        RatePeriod(start=utc('2026-08-01T00:00'), end=None, day=Decimal('20'), night=Decimal('5')),
    ]
    consumption = {utc('2026-07-31T23:30'): 1.0, utc('2026-08-01T00:00'): 1.0}
    compare(expected_usage_cost(consumption, set(), NIGHT, London, rates), expected=Decimal('12'))


def test_expected_usage_cost_no_rates():
    with ShouldRaise(ValueError('No unit rates for 2026-07-01 00:00:00+00:00')):
        expected_usage_cost({utc('2026-07-01T00:00'): 1.0}, set(), NIGHT, London, RATES)


def test_model_check_ok():
    check = ModelCheck(charge=charge(), expected_ex_vat=Decimal('12.336'))
    compare((check.ok, str(check)), expected=(
        True, '2026-07-15..2026-08-31: billed £12.34 ex VAT, tariff model £12.34: ok'
    ))


def test_model_check_mismatch():
    check = ModelCheck(charge=charge(), expected_ex_vat=Decimal('25'))
    compare((check.ok, str(check)), expected=(
        False, '2026-07-15..2026-08-31: billed £12.34 ex VAT, tariff model £25.00: MISMATCH (-12.66)'
    ))


def transaction(start, end, usage_cost, gross, net):
    return {
        '__typename': 'Charge', 'postedDate': end, 'title': 'Electricity', 'isReversed': False,
        'isExport': False, 'amounts': {'net': net, 'tax': gross - net, 'gross': gross},
        'consumption': {'startDate': start, 'endDate': end, 'quantity': '3.0', 'unit': 'kWh',
                        'usageCost': usage_cost, 'supplyCharge': 0},
    }


def test_model_checks(tmp_path):
    (tmp_path / 'octopus-dispatches-2026-07-15-12-00-00.json').write_text(json.dumps({
        'dispatches': {'completedDispatches': [
            {'startDtUtc': '2026-07-15 11:00:00+00:00', 'endDtUtc': '2026-07-15 11:30:00+00:00'},
        ]},
    }))
    graphql = Mock()
    graphql.tariff.return_value = {
        'unitRates': UNIT_RATES, 'timeOfUseScheme': SCHEME, 'agreementValidFrom': '2026-07-14T23:00:00+00:00',
    }
    graphql.transactions.return_value = [
        transaction('2026-07-01', '2026-07-14', 100, 100, 95),
        transaction('2026-07-15', '2026-07-15', 21, 21, 20),
    ]
    rest = Mock()
    rest.meter_point.return_value = {'mpan': '200', 'meters': [{'serial_number': 'S1'}]}
    rest.consumption.return_value = {utc('2026-07-15T00:00'): 1.0, utc('2026-07-15T11:00'): 2.0}

    compare(model_checks(graphql, rest, 'A-123', tmp_path), expected=[
        ModelCheck(Charge(date(2026, 7, 15), date(2026, 7, 15), Decimal('3.0'), Decimal('0.21'),
                          Decimal('0'), Decimal('0.2')), Decimal('0.197142')),
    ])
    compare(list(rest.mock_calls), expected=[
        call.meter_point('A-123', 'electricity_meter_points'),
        call.consumption('200', ['S1'], Timestamp('2026-07-15', tz=London), Timestamp('2026-07-16', tz=London)),
    ])


def test_model_checks_since(tmp_path):
    graphql = Mock()
    graphql.tariff.return_value = {
        'unitRates': UNIT_RATES, 'timeOfUseScheme': SCHEME, 'agreementValidFrom': '2026-07-14T23:00:00+00:00',
    }
    graphql.transactions.return_value = [transaction('2026-07-15', '2026-08-31', 21, 21, 20)]
    rest = Mock()
    rest.meter_point.return_value = {'mpan': '200', 'meters': []}
    compare(model_checks(graphql, rest, 'A-123', tmp_path, since=date(2026, 8, 31)), expected=[])


def test_model_checks_no_time_of_use_scheme(tmp_path):
    graphql = Mock()
    graphql.tariff.return_value = {'unitRates': [], 'timeOfUseScheme': None, 'agreementValidFrom': None}
    compare(model_checks(graphql, Mock(), 'A-123', tmp_path), expected=[])


def test_daily_model_check():
    ok = ModelCheck(charge=charge(), expected_ex_vat=Decimal('12.34'))
    mismatch = ModelCheck(charge=charge('2026-09-01', '2026-09-30'), expected_ex_vat=Decimal('20'))
    run = Mock(side_effect=[[ok], [mismatch]])
    check = DailyModelCheck(run)
    with LogCapture() as logs:
        check(date(2026, 9, 10))
        check(date(2026, 9, 10))
        check(date(2026, 10, 2))
    compare(list(run.mock_calls), expected=[call(None), call(date(2026, 8, 31))])
    compare(check.last_checked_end, expected=date(2026, 9, 30))
    logs.check(
        ('root', 'INFO', 'Tariff model check 2026-07-15..2026-08-31: billed £12.34 ex VAT, '
                         'tariff model £12.34: ok'),
        ('root', 'ERROR', 'Tariff model check 2026-09-01..2026-09-30: billed £12.34 ex VAT, '
                          'tariff model £20.00: MISMATCH (-7.66)'),
    )
