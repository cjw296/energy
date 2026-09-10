from datetime import date
from functools import partial

import pandas as pd
from pandas import DataFrame, NaT, Timestamp
from testfixtures import compare as compare_

from fitmodel import fit_payments, fit_year, load_tesla, load_zappi, tesla_flows, yearly, zappi_flows

compare = partial(compare_, strict=True)

NAN = float('nan')


def values(flows: DataFrame) -> dict:
    return flows.drop(columns='ts').round(6).to_dict('list')


def test_fit_year():
    local = pd.Series([Timestamp('2026-03-31 23:59', tz='Europe/London'),
                       Timestamp('2026-04-01 00:00', tz='Europe/London')])
    compare(fit_year(local).tolist(), expected=[2025, 2026])


def test_tesla_flows():
    power = DataFrame({
        'timestamp': ['2026-03-31T23:55:00+01:00', '2026-04-01T00:00:00+01:00', '2026-04-01T00:00:00+01:00'],
        'solar_power': [1200, 0, 0],
        'battery_power': [-600, 0, 0],
        'grid_power': [-300, 2400, 2400],
    })
    compare(values(tesla_flows(power)), expected={
        'solar': [0.1, 0.0], 'export': [0.025, 0.0], 'import': [0.0, 0.2],
        'batt_charge': [0.05, 0.0], 'batt_from_solar': [0.05, 0.0],
        'fit_year': [2025, 2026], 'day': [date(2026, 3, 31), date(2026, 4, 1)],
    })


def test_zappi_flows():
    minutes = DataFrame({
        'datetime': ['2026-04-01T00:00:00+00:00', '2026-04-01T00:01:00+00:00'],
        'imp': [3.6e6, 0], 'exp': [0, 7.2e6], 'h1d': [0, 1.8e6], 'h1b': [3.6e6, NAN],
    })
    compare(values(zappi_flows(minutes)), expected={
        'solar': [0.0, 0.0], 'export': [0.0, 2.0], 'import': [1.0, 0.0],
        'ev_solar': [0.0, 0.5], 'ev_grid': [1.0, 0.0],
        'fit_year': [2026, 2026], 'day': [date(2026, 4, 1), date(2026, 4, 1)],
    })


def test_load_tesla(tmp_path):
    (tmp_path / 'tesla-2026-04-01.csv').write_text(
        'timestamp,solar_power,battery_power,grid_power,grid_services_power,generator_power\n'
        '2026-04-01T00:00:00+01:00,0,0,1200,0,0\n'
    )
    (tmp_path / 'tesla-2019-10-01.csv').write_text('Date time,Home (kW)\n2019-10-01 00:00,1.0\n')
    compare(values(load_tesla(tmp_path)), expected={
        'solar': [0.0], 'export': [0.0], 'import': [0.1], 'batt_charge': [0.0], 'batt_from_solar': [0.0],
        'fit_year': [2026], 'day': [date(2026, 4, 1)],
    })


def test_load_zappi(tmp_path):
    (tmp_path / 'zappi-2026-04-01.csv').write_text(
        'datetime,imp,nect1,exp,h1d,h1b,gep\n2026-04-01T00:00:00+00:00,3600000,5,0,0,0,7200000\n'
    )
    compare(values(load_zappi(tmp_path)), expected={
        'solar': [2.0], 'export': [0.0], 'import': [1.0], 'ev_solar': [0.0], 'ev_grid': [0.0],
        'fit_year': [2026], 'day': [date(2026, 4, 1)],
    })


def test_fit_payments():
    solar = DataFrame({
        'Date': [Timestamp('2025-03-20'), Timestamp('2025-04-01'), Timestamp('2025-09-20'), NaT],
        'Generated': [1000.5, 500.5, 4000.25, NAN],
        'Deemed Due': [40.75, 20.25, 150.5, NAN],
        'Deemed Rate': [7.14, 7.14, 7.39, NAN],
    })
    compare(fit_payments(solar).to_dict('index'), expected={
        2024: {'generated': 1501.0, 'deemed_paid': 61.0, 'deemed_rate': 7.14},
        2025: {'generated': 4000.25, 'deemed_paid': 150.5, 'deemed_rate': 7.39},
    })


def test_yearly():
    tesla = DataFrame({
        'fit_year': [2025, 2025, 2026], 'day': [date(2025, 5, 1), date(2025, 5, 2), date(2026, 4, 1)],
        'solar': [3.0, 2.0, 1.0], 'export': [1.0, 0.5, 0.25], 'import': [0.125, 0.125, 0.125],
        'batt_charge': [1.0, 1.0, 1.0], 'batt_from_solar': [0.5, 0.5, 0.5],
    })
    zappi = DataFrame({
        'fit_year': [2025], 'day': [date(2025, 5, 1)], 'solar': [4.75], 'export': [1.25], 'import': [0.25],
        'ev_solar': [0.25], 'ev_grid': [0.75],
    })
    fit = DataFrame({'generated': [5.0], 'deemed_paid': [0.25], 'deemed_rate': [7.64]},
                    index=pd.Index([2025], name='fit_year'))
    compare(yearly(tesla, zappi, fit, prices=[12, 15.5]).round(6).to_dict('index'), expected={2025: {
        'generated': 5.0, 'deemed_paid': 0.25, 'deemed_rate': 7.64,
        'tesla_days': 2, 'solar_tesla': 5.0, 'export': 1.5, 'imported': 0.25,
        'batt_from_solar': 1.0, 'batt_charge': 2.0,
        'zappi_days': 1, 'solar_zappi': 4.75, 'export_zappi': 1.25, 'ev_solar': 0.25, 'ev_grid': 0.75,
        'export_pct': 30.0, 'metered_12p': 0.18, 'metered_15.5p': 0.2325,
    }})
