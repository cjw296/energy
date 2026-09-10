import logging
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pandas import Timestamp, Timedelta

from octopus import Schedule

CHEAP_KEY = "SUPER_OFF_PEAK"
EXPENSIVE_KEY = "ON_PEAK"
NEW_CHEAP_KEY = "NEW_SUPER_OFF_PEAK"
NEW_EXPENSIVE_KEY = "NEW_ON_PEAK"
MAX_ALLOWABLE_MISSING_STANDARD_UNIT_RATES = Timedelta(hours=4)
DAY, NIGHT = 'ECO7_DAY', 'ECO7_NIGHT'
EV_RATE_TYPES = {'EV_DEVICE_PEAK': DAY, 'EV_DEVICE_OFF_PEAK': NIGHT}
TIME_OF_USE_RATE_TYPES = {DAY, NIGHT, *EV_RATE_TYPES}


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


def valid_to(rate: dict, schedule: Schedule) -> Timestamp:
    return schedule.end if rate['validTo'] is None else Timestamp(rate['validTo'])


def time_of_use_slots(time_of_use_scheme: dict) -> dict[str, tuple[time, time]]:
    slots = {
        slot['timeslot']: (time.fromisoformat(slot['activeFrom']), time.fromisoformat(slot['activeTo']))
        for slot in time_of_use_scheme['timeslots']
    }
    if (len(time_of_use_scheme['timeslots']) != 2 or set(slots) != {DAY, NIGHT}
            or slots[DAY] != slots[NIGHT][::-1]):
        raise ValueError(f'Unexpected time of use scheme: {time_of_use_scheme}')
    return slots


def add_time_of_use_rates(
        schedule: Schedule, unit_rates_schedule: list[dict], time_of_use_scheme: dict | None
) -> dict[float, Timestamp]:
    if time_of_use_scheme is None:
        raise ValueError('Unit rates have rate types but no time of use scheme')
    rate_types = sorted({rate['rateType'] for rate in unit_rates_schedule})
    if set(rate_types) != TIME_OF_USE_RATE_TYPES:
        raise ValueError(f'Unexpected rate types: {rate_types}')
    by_period: dict[tuple, dict[str, float]] = defaultdict(dict)
    for rate in unit_rates_schedule:
        by_period[rate['validFrom'], rate['validTo']][rate['rateType']] = rate['value']
    for rates in by_period.values():
        if any(rates.get(ev) != rates.get(base) for ev, base in EV_RATE_TYPES.items()):
            raise ValueError(f'EV rates differ from day/night rates: {dict(sorted(rates.items()))}')

    slots = time_of_use_slots(time_of_use_scheme)
    tz = ZoneInfo(time_of_use_scheme['timezone'])
    first_day = schedule.start.astimezone(tz).date() - timedelta(days=1)
    unit_rates_with_max_valid_to: dict[float, Timestamp] = {}
    for rate in sorted(unit_rates_schedule, key=unit_rates_sort_key):
        if rate['rateType'] not in slots:
            continue
        rate_from, rate_to = Timestamp(rate['validFrom']), valid_to(rate, schedule)
        value = rate['value']
        unit_rates_with_max_valid_to[value] = max(rate_to, unit_rates_with_max_valid_to.get(value, rate_to))
        active_from, active_to = slots[rate['rateType']]
        for offset in range(3):
            day = first_day + timedelta(days=offset)
            end_day = day + timedelta(days=1) if active_to <= active_from else day
            start = max(Timestamp(datetime.combine(day, active_from), tz=tz), rate_from)
            end = min(Timestamp(datetime.combine(end_day, active_to), tz=tz), rate_to)
            if start < end:
                schedule.add(start, end, value)
    return unit_rates_with_max_valid_to


def make_labels(unit_rates_with_max_valid_to: dict[float, Timestamp]) -> tuple[float, float, dict[float, str]]:
    if len(unit_rates_with_max_valid_to) == 2:
        cheap, expensive = sorted(unit_rates_with_max_valid_to.keys())
        return cheap, expensive, {
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
        return cheap, expensive, {
            cheap: CHEAP_KEY,
            expensive: EXPENSIVE_KEY,
            newer_cheap: NEW_CHEAP_KEY,
            newer_expensive: NEW_EXPENSIVE_KEY,
        }
    raise ValueError(f'Unexpected number of rates: {unit_rates_with_max_valid_to}')


def make_seasons_and_energy_charges(
        now: Timestamp,
        unit_rates_schedule: list[dict],
        dispatches: dict,
        timezone: ZoneInfo,
        time_of_use_scheme: dict | None = None,
) -> dict:

    schedule = Schedule(now)
    max_valid_to = None

    if any(rate.get('rateType') for rate in unit_rates_schedule):
        # rates without their own time windows, e.g. the four-rate Intelligent Octopus Go:
        unit_rates_with_max_valid_to = add_time_of_use_rates(schedule, unit_rates_schedule, time_of_use_scheme)
    else:
        # add the standard unit rates to the schedule:
        unit_rates_with_max_valid_to = {}
        for rate in sorted(unit_rates_schedule, key=unit_rates_sort_key):
            rate_valid_to = valid_to(rate, schedule)
            max_valid_to = rate_valid_to if max_valid_to is None else max(max_valid_to, rate_valid_to)
            unit_rates_with_max_valid_to[rate['value']] = rate_valid_to
            schedule.add(Timestamp(rate['validFrom']), rate_valid_to, rate['value'])
        assert max_valid_to is not None, 'empty unit rates?'

    cheap, expensive, labels = make_labels(unit_rates_with_max_valid_to)

    # fill in any future, expected gaps in the standard unit rate schedule:
    if max_valid_to is not None and max_valid_to < schedule.end:
        missing = schedule.end - max_valid_to
        hours = missing.total_seconds() / (60*60)
        if hours >= 5.1:
            logging.warning(
                f'Missing standard unit rates for {hours:.1f} hours from {max_valid_to}'
            )
        for start, existing_value in schedule.entries.items():
            if existing_value is None and start >= max_valid_to:
                schedule.entries[start] = expensive

    # Add any upcoming planned dispatches that are definitely marked as "smart charge"
    for dispatch in dispatches.get('plannedDispatches', ()):
        if dispatch['meta']['source'] == 'smart-charge':
            schedule.add(Timestamp(dispatch["startDtUtc"]), Timestamp(dispatch["endDtUtc"]), cheap)

    slots = schedule.final_times(timezone)
    used = sorted({labels[slot.cost] for slot in slots})
    if len(used) < 2:
        raise ValueError(f'Schedule uses only {used} of {sorted(set(labels.values()))}')

    # Build the final Tesla-compatible schedule
    summer_tou_periods = defaultdict(list)
    for slot in slots:
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
