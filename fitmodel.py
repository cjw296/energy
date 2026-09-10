from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from pandas import DataFrame, Series

LONDON = 'Europe/London'
TESLA_POWER = ['solar_power', 'battery_power', 'grid_power']
KWH_PER_WATT_5_MIN = 5 / 60 / 1000
JOULES_PER_KWH = 3.6e6
ZAPPI_ENERGY = {'gep': 'solar', 'exp': 'export', 'imp': 'import', 'h1d': 'ev_solar', 'h1b': 'ev_grid'}


def fit_year(local: Series) -> Series:
    """FiT years run April to March and are named by the year they start in."""
    return local.dt.year - (local.dt.month < 4).astype(int)


def _with_period(flows: DataFrame) -> DataFrame:
    local = flows.ts.dt.tz_convert(LONDON)
    return flows.assign(fit_year=fit_year(local), day=local.dt.date).reset_index(drop=True)


def tesla_flows(power: DataFrame) -> DataFrame:
    """kWh per 5-minute sample from Tesla's average W: grid + is import, battery + is discharge."""
    power = power.assign(ts=pd.to_datetime(power.timestamp, utc=True, format='ISO8601')).drop_duplicates('ts')
    solar = power.solar_power.clip(lower=0)
    charge = (-power.battery_power).clip(lower=0)
    return _with_period(DataFrame({
        'ts': power.ts,
        'solar': solar * KWH_PER_WATT_5_MIN,
        'export': (-power.grid_power).clip(lower=0) * KWH_PER_WATT_5_MIN,
        'import': power.grid_power.clip(lower=0) * KWH_PER_WATT_5_MIN,
        'batt_charge': charge * KWH_PER_WATT_5_MIN,
        # an estimate: solar can't be told apart from grid while both charge the Powerwalls
        'batt_from_solar': pd.concat([charge, solar], axis=1).min(axis=1) * KWH_PER_WATT_5_MIN,
    }))


def zappi_flows(minutes: DataFrame) -> DataFrame:
    """kWh per minute from the zappi's joule counters."""
    minutes = minutes.assign(ts=pd.to_datetime(minutes.datetime, utc=True, format='ISO8601')).drop_duplicates('ts')
    flows = DataFrame({'ts': minutes.ts})
    for column, name in ZAPPI_ENERGY.items():
        flows[name] = minutes[column].fillna(0) / JOULES_PER_KWH if column in minutes else 0.0
    return _with_period(flows)


def load_tesla(root: Path) -> DataFrame:
    frames = []
    for path in sorted(root.glob('tesla-20*.csv')):
        frame = pd.read_csv(path)
        if set(TESLA_POWER) <= set(frame.columns):
            frames.append(frame[['timestamp', *TESLA_POWER]])
    return tesla_flows(pd.concat(frames, ignore_index=True))


def load_zappi(root: Path) -> DataFrame:
    wanted = {'datetime', *ZAPPI_ENERGY}
    frames = [pd.read_csv(path, usecols=lambda column: column in wanted)
              for path in sorted(root.glob('zappi-20*.csv'))]
    return zappi_flows(pd.concat(frames, ignore_index=True))


def fit_payments(solar: DataFrame) -> DataFrame:
    """FiT meter generation and deemed export paid per FiT year; a 1 April reading closes the year before."""
    solar = solar.dropna(subset=['Date'])
    dates = pd.to_datetime(solar.Date)
    closes_previous = (dates.dt.month < 4) | ((dates.dt.month == 4) & (dates.dt.day == 1))
    return solar.assign(fit_year=dates.dt.year - closes_previous.astype(int)).groupby('fit_year').agg(
        generated=('Generated', 'sum'), deemed_paid=('Deemed Due', 'sum'), deemed_rate=('Deemed Rate', 'max'),
    )


def yearly(tesla: DataFrame, zappi: DataFrame, fit: DataFrame, prices: Iterable[float]) -> DataFrame:
    """Per FiT year: measured flows, and what the measured export would have earned at each price (p/kWh)."""
    t = tesla.groupby('fit_year').agg(
        tesla_days=('day', 'nunique'), solar_tesla=('solar', 'sum'), export=('export', 'sum'),
        imported=('import', 'sum'), batt_from_solar=('batt_from_solar', 'sum'), batt_charge=('batt_charge', 'sum'),
    )
    z = zappi.groupby('fit_year').agg(
        zappi_days=('day', 'nunique'), solar_zappi=('solar', 'sum'), export_zappi=('export', 'sum'),
        ev_solar=('ev_solar', 'sum'), ev_grid=('ev_grid', 'sum'),
    )
    out = fit.join(t, how='left').join(z, how='left')
    out['export_pct'] = 100 * out.export / out.generated
    for price in prices:
        out[f'metered_{price:g}p'] = out.export * price / 100
    return out
