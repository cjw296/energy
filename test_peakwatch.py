import logging
import re
from functools import partial
from unittest.mock import Mock, call

import pook
from pandas import Timedelta, Timestamp
from testfixtures import LogCapture, compare as compare_

from octopus import OctopusGraphQLClient
from peakwatch import PeakImportWatch, peak_watch

compare = partial(compare_, strict=True)

SCHEME = {
    'name': 'IOG_ECO7_TOU', 'timezone': 'Europe/London',
    'timeslots': [
        {'timeslot': 'ECO7_DAY', 'activeFrom': '05:30:00', 'activeTo': '23:30:00'},
        {'timeslot': 'ECO7_NIGHT', 'activeFrom': '23:30:00', 'activeTo': '05:30:00'},
    ],
}
NO_DISPATCHES = {'plannedDispatches': [], 'completedDispatches': []}


def utc(text: str) -> Timestamp:
    return Timestamp(text, tz='UTC')


def readings(start: str, end: str, demand: float) -> list[dict]:
    moments = []
    moment = utc(start)
    while moment <= utc(end):
        moments.append({'readAt': moment.isoformat(), 'demand': str(demand)})
        moment += Timedelta(seconds=10)
    return moments


def dispatch(start: str, end: str) -> dict:
    return {'startDtUtc': f'{start}+00:00', 'endDtUtc': f'{end}+00:00'}


def watch(*telemetry: dict) -> tuple[PeakImportWatch, Mock]:
    source = Mock(return_value=list(telemetry))
    return PeakImportWatch(source, threshold_w=500), source


def test_peak_import():
    check, source = watch(*readings('2026-10-29T20:48', '2026-10-29T20:53', demand=1900))
    with LogCapture() as logs:
        check(utc('2026-10-29T20:53'), SCHEME, NO_DISPATCHES)
    compare(list(source.mock_calls), expected=[call(utc('2026-10-29T20:48'), utc('2026-10-29T20:53'))])
    logs.check(('root', 'ERROR', 'Importing 1.9 kW from the grid at peak rate (last 5 minutes)'))


def test_under_threshold():
    check, _ = watch(*readings('2026-10-29T20:48', '2026-10-29T20:53', demand=300))
    with LogCapture() as logs:
        check(utc('2026-10-29T20:53'), SCHEME, NO_DISPATCHES)
    logs.check()


def test_night_window():
    check, source = watch()
    with LogCapture() as logs:
        check(utc('2026-10-30T01:00'), SCHEME, NO_DISPATCHES)
    compare(list(source.mock_calls), expected=[])
    logs.check()


def test_planned_dispatch():
    check, source = watch()
    with LogCapture() as logs:
        check(utc('2026-10-29T21:10'), SCHEME, {'plannedDispatches': [dispatch('2026-10-29 21:00:00', '2026-10-30 02:30:00')],
                                                'completedDispatches': []})
    compare(list(source.mock_calls), expected=[])
    logs.check()


def test_completed_dispatch_covers_its_whole_half_hour():
    check, source = watch()
    with LogCapture() as logs:
        check(utc('2026-10-29T18:25'), SCHEME, {'plannedDispatches': [],
                                                'completedDispatches': [dispatch('2026-10-29 18:05:00',
                                                                                 '2026-10-29 18:10:00')]})
    compare(list(source.mock_calls), expected=[])
    logs.check()


def test_readings_from_cheap_times_are_ignored():
    charging = readings('2026-10-30T05:27', '2026-10-30T05:29:50', demand=10000)
    check, _ = watch(*charging, *readings('2026-10-30T05:30', '2026-10-30T05:32', demand=2000))
    with LogCapture() as logs:
        check(utc('2026-10-30T05:32'), SCHEME, NO_DISPATCHES)
    logs.check(('root', 'ERROR', 'Importing 2.0 kW from the grid at peak rate (last 5 minutes)'))


def test_too_few_peak_readings():
    check, _ = watch(*readings('2026-10-30T05:27', '2026-10-30T05:29:50', demand=10000),
                     *readings('2026-10-30T05:30', '2026-10-30T05:30:40', demand=2000))
    with LogCapture() as logs:
        check(utc('2026-10-30T05:30:40'), SCHEME, NO_DISPATCHES)
    logs.check()


def test_no_readings():
    check, _ = watch()
    with LogCapture() as logs:
        check(utc('2026-10-29T20:53'), SCHEME, NO_DISPATCHES)
    logs.check(('root', 'ERROR', 'No smart meter readings between 2026-10-29 20:48:00+00:00 and '
                                   '2026-10-29 20:53:00+00:00'))


def test_no_time_of_use_scheme():
    check, source = watch()
    with LogCapture() as logs:
        check(utc('2026-10-29T20:53'), None, NO_DISPATCHES)
    compare(list(source.mock_calls), expected=[])
    logs.check()


GRAPHQL = 'https://api.octopus.energy/v1/graphql/'


def stub_devices(*device_ids: str) -> None:
    pook.post(GRAPHQL).body(re.compile('"operationName": "krakenTokenAuthentication"')).reply(200).json(
        {'data': {'obtainKrakenToken': {'token': 'tok'}}})
    pook.post(GRAPHQL).body(re.compile('"operationName": "getSmartDevices"')).reply(200).json(
        {'data': {'account': {'electricityAgreements': [{'meterPoint': {'meters': [
            {'smartDevices': [{'deviceId': device_id} for device_id in device_ids]},
        ]}}]}}})


def test_peak_watch_for_the_account_device():
    with pook.use():
        stub_devices('D1')
        watch_ = peak_watch(OctopusGraphQLClient('key'), 'A-123', threshold_w=750)
        compare(pook.isdone(), expected=True)
    compare((watch_.telemetry.args, watch_.threshold_w), expected=(('D1',), 750))


def test_peak_watch_disabled():
    compare(peak_watch(OctopusGraphQLClient('key'), 'A-123', threshold_w=0), expected=None)


def test_peak_watch_no_device():
    with pook.use(), LogCapture(level=logging.WARNING) as logs:
        stub_devices()
        compare(peak_watch(OctopusGraphQLClient('key'), 'A-123', threshold_w=500), expected=None)
    logs.check(('root', 'ERROR', 'No smart meter device found, so no peak import alerts'))
