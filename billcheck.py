import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pandas import Timedelta, Timestamp

from billrec import Charge, charges_from_transactions
from schedule import DAY, NIGHT, time_of_use_slots

TOLERANCE = Decimal('0.05')
DISPATCH_DUMP_PREFIX = 'octopus-dispatches'
HALF_HOUR = Timedelta(minutes=30)


@dataclass(frozen=True)
class RatePeriod:
    start: Timestamp
    end: Timestamp | None
    day: Decimal
    night: Decimal


def rate_periods(unit_rates: list[dict[str, Any]]) -> list[RatePeriod]:
    by_period: dict[tuple, dict[str, Decimal]] = {}
    for rate in unit_rates:
        key = rate['validFrom'], rate['validTo']
        by_period.setdefault(key, {})[rate['rateType']] = Decimal(str(rate['preVatValue']))
    return sorted(
        (RatePeriod(Timestamp(start), None if end is None else Timestamp(end), rates[DAY], rates[NIGHT])
         for (start, end), rates in by_period.items()),
        key=lambda period: period.start,
    )


def in_window(moment: time, window: tuple[time, time]) -> bool:
    start, end = window
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def dispatch_half_hours(dumps: Iterable[dict[str, Any]]) -> set[Timestamp]:
    """UTC starts of every half hour touched by a completed dispatch."""
    starts = set()
    for dump in dumps:
        for dispatch in (dump.get('dispatches') or {}).get('completedDispatches') or ():
            current = Timestamp(dispatch['startDtUtc']).tz_convert('UTC').floor('30min')
            end = Timestamp(dispatch['endDtUtc'])
            while current < end:
                starts.add(current)
                current += HALF_HOUR
    return starts


def load_dumps(root: Path, first: date, last: date) -> list[dict[str, Any]]:
    dumps = []
    for path in sorted(root.glob(f'{DISPATCH_DUMP_PREFIX}-*.json')):
        dumped = path.name[len(DISPATCH_DUMP_PREFIX) + 1:][:10]
        if first.isoformat() <= dumped <= last.isoformat():
            dumps.append(json.loads(path.read_text()))
    return dumps


def expected_usage_cost(
        consumption: Mapping[Timestamp, float],
        dispatches: set[Timestamp],
        night: tuple[time, time],
        tz: ZoneInfo,
        rates: list[RatePeriod],
) -> Decimal:
    """Pence ex VAT if night-window and dispatch half hours are cheap and the rest is day rate."""
    total = Decimal(0)
    for start, kwh in consumption.items():
        start = start.tz_convert('UTC')
        period = next((p for p in rates if p.start <= start and (p.end is None or start < p.end)), None)
        if period is None:
            raise ValueError(f'No unit rates for {start}')
        cheap = start in dispatches or in_window(start.astimezone(tz).time(), night)
        total += Decimal(str(kwh)) * (period.night if cheap else period.day)
    return total


@dataclass(frozen=True)
class ModelCheck:
    charge: Charge
    expected_ex_vat: Decimal

    @property
    def difference(self) -> Decimal:
        return self.charge.usage_ex_vat - self.expected_ex_vat

    @property
    def ok(self) -> bool:
        return abs(self.difference) <= TOLERANCE

    def __str__(self) -> str:
        outcome = 'ok' if self.ok else f'MISMATCH ({self.difference:+.2f})'
        return (f'{self.charge.start}..{self.charge.end}: billed £{self.charge.usage_ex_vat:.2f} ex VAT, '
                f'tariff model £{self.expected_ex_vat:.2f}: {outcome}')


def local_midnight(day: date, tz: ZoneInfo) -> Timestamp:
    return Timestamp(datetime.combine(day, time()), tz=tz)


def model_checks(graphql, rest, account: str, dumps_root: Path, since: date | None = None) -> list[ModelCheck]:
    """Check bills on the current time-of-use agreement, optionally only those ending after `since`."""
    tariff = graphql.tariff(account)
    scheme = tariff['timeOfUseScheme']
    if scheme is None:
        return []
    tz = ZoneInfo(scheme['timezone'])
    night = time_of_use_slots(scheme)[NIGHT]
    rates = rate_periods(tariff['unitRates'])
    agreement_start = Timestamp(tariff['agreementValidFrom'])
    charges = [
        charge for charge in charges_from_transactions(graphql.transactions(account))
        if local_midnight(charge.start, tz) >= agreement_start and (since is None or charge.end > since)
    ]
    point = rest.meter_point(account, 'electricity_meter_points')
    serials = [meter['serial_number'] for meter in point['meters']]
    checks = []
    for charge in charges:
        consumption = rest.consumption(
            point['mpan'], serials,
            local_midnight(charge.start, tz), local_midnight(charge.end + timedelta(days=1), tz),
        )
        dumps = load_dumps(dumps_root, charge.start - timedelta(days=1), charge.end + timedelta(days=1))
        expected = expected_usage_cost(consumption, dispatch_half_hours(dumps), night, tz, rates)
        checks.append(ModelCheck(charge, expected / 100))
    return checks


@dataclass
class DailyModelCheck:
    run: Callable[[date | None], list[ModelCheck]]
    last_run: date | None = None
    last_checked_end: date | None = None

    def __call__(self, today: date) -> None:
        if today == self.last_run:
            return
        self.last_run = today
        for check in self.run(self.last_checked_end):
            (logging.info if check.ok else logging.error)(f'Tariff model check {check}')
            if self.last_checked_end is None or check.charge.end > self.last_checked_end:
                self.last_checked_end = check.charge.end
