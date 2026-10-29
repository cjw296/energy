from datetime import date
from functools import partial
from zoneinfo import ZoneInfo

import pook
from pandas import Timestamp
from testfixtures import ShouldRaise, compare as compare_

from octopus import OctopusRESTClient, readings_by_day

compare = partial(compare_, strict=True)


def test_consumption_paginates_and_sums_meters():
    params = {'period_from': '2026-07-15T00:00:00+01:00', 'period_to': '2026-07-16T00:00:00+01:00',
              'order_by': 'period', 'page_size': '25000'}
    meters = 'https://api.octopus.energy/v1/electricity-meter-points/200/meters/'
    with pook.use():
        pook.get(meters + 'S1/consumption/').params(params).reply(200).json(
            {'next': 'https://api.octopus.energy/v1/page2', 'results': [
                {'consumption': 0.5, 'interval_start': '2026-07-15T00:00:00+01:00'},
            ]})
        pook.get('https://api.octopus.energy/v1/page2').reply(200).json({'next': None, 'results': [
            {'consumption': 0.25, 'interval_start': '2026-07-15T00:30:00+01:00'},
        ]})
        pook.get(meters + 'S2/consumption/').params(params).reply(200).json({'next': None, 'results': [
            {'consumption': 1.0, 'interval_start': '2026-07-15T00:00:00+01:00'},
        ]})
        start = Timestamp('2026-07-15', tz='Europe/London')
        end = Timestamp('2026-07-16', tz='Europe/London')
        compare(OctopusRESTClient('key').consumption('200', ['S1', 'S2'], start, end), expected={
            Timestamp('2026-07-14T23:00', tz='UTC'): 1.5,
            Timestamp('2026-07-14T23:30', tz='UTC'): 0.25,
        })
        compare(pook.isdone(), expected=True)


def test_gsp():
    with pook.use():
        (pook.get('https://api.octopus.energy/v1/electricity-meter-points/1000000000000/')
         .header('Authorization', 'Basic a2V5Og==')
         .reply(200).json({'gsp': '_C', 'mpan': '1000000000000', 'profile_class': 1}))
        compare(OctopusRESTClient('key').gsp('1000000000000'), expected='_C')
        compare(pook.isdone(), expected=True)


def test_unit_rates_paginates_and_keeps_direct_debit():
    tariff = 'https://api.octopus.energy/v1/products/P/electricity-tariffs/E-1R-P-H/'

    def rate(value: float, payment_method: str | None) -> dict:
        return {'value_exc_vat': value, 'valid_from': '2026-07-05T23:00:00Z', 'valid_to': None,
                'payment_method': payment_method}

    with pook.use():
        pook.get(tariff + 'day-unit-rates/').params(
            {'period_from': '2026-07-14T23:00:00+00:00', 'page_size': '1500'}
        ).reply(200).json({'next': 'https://api.octopus.energy/v1/page2', 'results': [
            rate(28.9, 'DIRECT_DEBIT'), rate(30.1, 'NON_DIRECT_DEBIT'),
        ]})
        pook.get('https://api.octopus.energy/v1/page2').reply(200).json({'next': None, 'results': [
            rate(25.0, None),
        ]})
        rates = OctopusRESTClient('key').unit_rates('P', 'E-1R-P-H', 'day', Timestamp('2026-07-14T23:00', tz='UTC'))
        compare(rates, expected=[rate(28.9, 'DIRECT_DEBIT'), rate(25.0, None)])
        compare(pook.isdone(), expected=True)


METER = 'https://api.octopus.energy/v1/electricity-meter-points/200/meters/S1/consumption/'


def reading(start: str, consumption: float = 0.5) -> dict:
    return {'consumption': consumption, 'interval_start': start, 'interval_end': start}


def test_readings_asks_for_one_page():
    with pook.use():
        pook.get(METER).params({'order_by': 'period', 'page_size': '25000', 'period_from': 'from',
                                'period_to': 'to'}).reply(200).json({'next': None, 'results': [
            reading('2026-10-24T23:30:00+01:00'),
        ]})
        compare(OctopusRESTClient('key').readings('electricity-meter-points', '200', 'S1', 'from', 'to'),
                expected=[reading('2026-10-24T23:30:00+01:00')])
        compare(pook.isdone(), expected=True)


def test_readings_without_period():
    with pook.use():
        pook.get(METER).params({'order_by': 'period', 'page_size': '25000'}).reply(200).json(
            {'next': None, 'results': []})
        compare(OctopusRESTClient('key').readings('electricity-meter-points', '200', 'S1'), expected=[])
        compare(pook.isdone(), expected=True)


def test_readings_paginates():
    with pook.use():
        pook.get(METER).reply(200).json({'next': 'https://api.octopus.energy/v1/page2', 'results': [
            reading('2026-10-24T23:00:00+01:00'),
        ]})
        pook.get('https://api.octopus.energy/v1/page2').reply(200).json({'next': None, 'results': [
            reading('2026-10-24T23:30:00+01:00'),
        ]})
        compare(OctopusRESTClient('key').readings('electricity-meter-points', '200', 'S1'), expected=[
            reading('2026-10-24T23:00:00+01:00'), reading('2026-10-24T23:30:00+01:00'),
        ])
        compare(pook.isdone(), expected=True)


def test_readings_duplicate_half_hour():
    with pook.use():
        pook.get(METER).reply(200).json({'next': None, 'results': [
            reading('2026-10-26T10:00:00Z'), reading('2026-10-26T10:00:00+00:00', consumption=0.7),
        ]})
        with ShouldRaise(ValueError('Duplicate readings from S1 for 2026-10-26 10:00:00+00:00')):
            OctopusRESTClient('key').readings('electricity-meter-points', '200', 'S1')


def test_readings_by_day():
    readings = [
        reading('2026-10-26T00:00:00Z'),
        reading('2026-10-25T00:30:00+01:00'),
        reading('2026-10-24T23:30:00+01:00'),
        reading('2026-10-25T00:00:00+01:00'),
        reading('2026-10-25T23:30:00Z'),
    ]
    compare(readings_by_day(readings, ZoneInfo('Europe/London')), expected={
        date(2026, 10, 24): [reading('2026-10-24T23:30:00+01:00')],
        date(2026, 10, 25): [reading('2026-10-25T00:00:00+01:00'), reading('2026-10-25T00:30:00+01:00'),
                             reading('2026-10-25T23:30:00Z')],
        date(2026, 10, 26): [reading('2026-10-26T00:00:00Z')],
    })
