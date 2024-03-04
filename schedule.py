from collections import defaultdict
from zoneinfo import ZoneInfo

from pandas import Timestamp

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


def make_seasons_and_energy_charges(
        now: Timestamp, unit_rates_schedule: list[dict], dispatches: dict, timezone: ZoneInfo
) -> dict:

    unit_rates = set()
    schedule = Schedule(now)
    for rate in unit_rates_schedule:
        value = rate['value']
        unit_rates.add(value)
        schedule.add(Timestamp(rate['validFrom']), Timestamp(rate['validTo']), value)

    assert len(unit_rates) == 2, f'Unexpected number of rates: {unit_rates}'
    cheap, expensive = sorted(unit_rates)
    labels = {
        cheap: CHEAP_KEY,
        expensive: EXPENSIVE_KEY
    }

    for dispatch in dispatches.get('plannedDispatches', ()):
        if dispatch['meta']['source'] == 'smart-charge':
            schedule.add(Timestamp(dispatch["startDtUtc"]), Timestamp(dispatch["endDtUtc"]), cheap)

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
