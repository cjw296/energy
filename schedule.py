import logging
from datetime import UTC
from zoneinfo import ZoneInfo

from pandas import Timestamp, Timedelta

from octopus import Schedule

CHEAP_KEY = "SUPER_OFF_PEAK"
EXPENSIVE_KEY = "ON_PEAK"


def price_in_pounds(price_in_pence: float) -> float:
    return round(price_in_pence/100, 2)


def make_energy_charges(cheap: float, expensive: float):
    return {
        "ALL": {
            "ALL": 0
        },
        "Summer": {
            EXPENSIVE_KEY: price_in_pounds(expensive),
            CHEAP_KEY: price_in_pounds(cheap),
        },
        "Winter": {}
    }


def unit_rates_sort_key(rate: dict[str, str | float]) -> Timestamp:
    return Timestamp(rate['validFrom']).astimezone(UTC)


def make_seasons_and_energy_charges(
        now: Timestamp, unit_rates_schedule: list[dict], dispatches: dict, timezone: ZoneInfo
) -> dict:

    unit_rates = set()
    schedule = Schedule(now)

    # add the standard unit rates to the schedule:
    max_valid_to = None
    value = None
    for rate in sorted(unit_rates_schedule, key=unit_rates_sort_key):
        valid_to = Timestamp(rate['validTo'])
        max_valid_to = valid_to if max_valid_to is None else max(max_valid_to, valid_to)
        value = rate['value']
        unit_rates.add(value)
        schedule.add(Timestamp(rate['validFrom']), valid_to, value)
    assert max_valid_to is not None, 'empty unit rates?'

    # figure out what the cheap and expensive rates are:
    assert len(unit_rates) == 2, f'Unexpected number of rates: {unit_rates}'
    cheap, expensive = sorted(unit_rates)
    labels = {
        cheap: CHEAP_KEY,
        expensive: EXPENSIVE_KEY
    }

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
    summer_tou_periods = {
        EXPENSIVE_KEY: [],
        CHEAP_KEY: [],
    }
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
        'energy_charges': make_energy_charges(cheap, expensive),
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
