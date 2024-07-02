import logging
from datetime import UTC
from collections import defaultdict
from zoneinfo import ZoneInfo

from pandas import Timestamp, Timedelta

from octopus import Schedule

CHEAP_KEY = "SUPER_OFF_PEAK"
EXPENSIVE_KEY = "ON_PEAK"
NEW_CHEAP_KEY = "NEW_SUPER_OFF_PEAK"
NEW_EXPENSIVE_KEY = "NEW_ON_PEAK"
MAX_ALLOWABLE_MISSING_STANDARD_UNIT_RATES = Timedelta(hours=4)


def price_in_pounds(price_in_pence: float) -> float:
    return round(price_in_pence/100, 2)


def make_energy_charges(rates: dict[float, str]):
    return {
        "ALL": {
            "ALL": 0
        },
        "Summer": {name: price_in_pounds(rate) for (rate, name) in rates.items()},
        "Winter": {}
    }


def unit_rates_sort_key(rate: dict[str, str | float]) -> Timestamp:
    return Timestamp(rate['validFrom']).astimezone(UTC)


def make_seasons_and_energy_charges(
        now: Timestamp, unit_rates_schedule: list[dict], dispatches: dict, timezone: ZoneInfo
) -> dict:

    unit_rates_with_max_valid_to: dict[float, Timestamp] = {}
    schedule = Schedule(now)

    # add the standard unit rates to the schedule:
    max_valid_to = None
    value = None
    for rate in sorted(unit_rates_schedule, key=unit_rates_sort_key):
        valid_to = Timestamp(rate['validTo'])
        max_valid_to = valid_to if max_valid_to is None else max(max_valid_to, valid_to)
        value = rate['value']
        unit_rates_with_max_valid_to[value] = valid_to
        schedule.add(Timestamp(rate['validFrom']), valid_to, value)
    assert max_valid_to is not None, 'empty unit rates?'

    # figure out what the cheap and expensive rates are:
    if len(unit_rates_with_max_valid_to) == 2:
        cheap, expensive = sorted(unit_rates_with_max_valid_to.keys())
        labels = {
            cheap: CHEAP_KEY,
            expensive: EXPENSIVE_KEY
        }
    elif len(unit_rates_with_max_valid_to) == 4:
        rates_sorted_by_date = [
            rate for (date, rate) in
            sorted((date, rate) for (rate, date) in unit_rates_with_max_valid_to.items())
        ]
        older, newer = rates_sorted_by_date[:2], rates_sorted_by_date[2:]
        cheap, expensive = sorted(older)
        newer_cheap, newer_expensive = sorted(newer)
        labels = {
            cheap: CHEAP_KEY,
            expensive: EXPENSIVE_KEY,
            newer_cheap: NEW_CHEAP_KEY,
            newer_expensive: NEW_EXPENSIVE_KEY,
        }
    else:
        raise ValueError(f'Unexpected number of rates: {unit_rates_with_max_valid_to}')

    # fill in any future, expected gaps in the standard unit rate schedule:
    if max_valid_to < schedule.end:
        missing = schedule.end - max_valid_to
        hours = missing.total_seconds() / (60*60)
        logging.warning(
            f'Missing standard unit rates for {hours:.1f} hours from {max_valid_to}'
        )
        fill_value = expensive if value == cheap else expensive
        for start, existing_value in schedule.entries.items():
            if existing_value is None and start >= max_valid_to:
                schedule.entries[start] = fill_value

    # Add any upcoming planned dispatches that are definitely marked as "smart charge"
    for dispatch in dispatches.get('plannedDispatches', ()):
        if dispatch['meta']['source'] == 'smart-charge':
            schedule.add(Timestamp(dispatch["startDtUtc"]), Timestamp(dispatch["endDtUtc"]), cheap)

    # Build the final Tesla-compatible schedule
    summer_tou_periods = defaultdict(list)
    for slot in schedule.final_times(timezone):
        summer_tou_periods[labels[slot.cost]].append({
            'fromDayOfWeek': 0,
            'toDayOfWeek': 6,
            'fromHour': slot.start.hour,
            'fromMinute': slot.start.minute,
            'toHour': slot.end.hour,
            'toMinute': slot.end.minute,
        })

    return {
        'energy_charges': make_energy_charges(labels),
        'seasons': {
            "Summer": {
                "fromDay": 1,
                "toDay": 31,
                "fromMonth": 1,
                "toMonth": 12,
                "tou_periods": summer_tou_periods
            },
            "Winter": {
                "fromDay": 0,
                "toDay": 0,
                "fromMonth": 0,
                "toMonth": 0,
                "tou_periods": {}
            }
        }
    }
