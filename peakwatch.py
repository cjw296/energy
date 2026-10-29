import logging
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from pandas import Timedelta, Timestamp

from billcheck import in_window
from schedule import NIGHT, time_of_use_slots

MIN_READINGS = 6


def dispatch_spans(dispatches: dict[str, Any]) -> list[tuple[Timestamp, Timestamp]]:
    """
    Every half hour a dispatch touches is billed cheap, so spans round out to half hours.
    """
    return [
        (Timestamp(dispatch['startDtUtc']).floor('30min'), Timestamp(dispatch['endDtUtc']).ceil('30min'))
        for kind in ('plannedDispatches', 'completedDispatches')
        for dispatch in dispatches.get(kind) or ()
    ]


@dataclass
class PeakImportWatch:
    telemetry: Callable[[Timestamp, Timestamp], list[dict[str, Any]]]
    threshold_w: float = 500
    window: Timedelta = Timedelta(minutes=5)

    def __call__(self, now: Timestamp, scheme: dict[str, Any] | None, dispatches: dict[str, Any]) -> None:
        if scheme is None:
            return
        tz = ZoneInfo(scheme['timezone'])
        night = time_of_use_slots(scheme)[NIGHT]
        spans = dispatch_spans(dispatches)

        def cheap(moment: Timestamp) -> bool:
            return in_window(moment.tz_convert(tz).time(), night) or any(
                start <= moment < end for start, end in spans
            )

        if cheap(now):
            return
        start = now - self.window
        readings = self.telemetry(start, now)
        if not readings:
            logging.warning(f'No smart meter readings between {start} and {now}')
            return
        demand = [float(reading['demand']) for reading in readings if not cheap(Timestamp(reading['readAt']))]
        if len(demand) < MIN_READINGS:
            return
        average = mean(demand)
        if average > self.threshold_w:
            minutes = int(self.window.total_seconds() // 60)
            logging.error(f'Importing {average / 1000:.1f} kW from the grid at peak rate (last {minutes} minutes)')
