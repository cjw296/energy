import re
from functools import partial

import pook
from gql.transport.exceptions import TransportQueryError
from pandas import Timestamp
from testfixtures import ShouldRaise, compare as compare_

from octopus import OctopusGraphQLClient

compare = partial(compare_, strict=True)

GRAPHQL = 'https://api.octopus.energy/v1/graphql/'

# fields downstream code relies on; a query that stops asking for one should fail its test
TARIFF_FIELDS = ('rateType', 'preVatValue', 'timeOfUseScheme', 'activeFrom', 'activeTo')
DISPATCH_FIELDS = ('plannedDispatches', 'completedDispatches', 'startDt', 'endDt', 'source')
TRANSACTION_FIELDS = ('isReversed', 'isExport', 'usageCost', 'supplyCharge', 'quantity', 'endCursor')
DEVICE_FIELDS = ('electricityAgreements', 'smartDevices', 'deviceId')
TELEMETRY_FIELDS = ('smartMeterTelemetry', 'TEN_SECONDS', 'readAt', 'demand')


def stub_token(token: str = 'tok') -> None:
    pook.post(GRAPHQL).body(re.compile(r'"operationName": "krakenTokenAuthentication"')).reply(200).json(
        {'data': {'obtainKrakenToken': {'token': token}}})


def stub_query(operation: str, response: dict, token: str = 'tok', *also: str) -> None:
    pattern = ''.join(f'(?=.*{re.escape(text)})' for text in (f'"operationName": "{operation}"', *also))
    pook.post(GRAPHQL).header('Authorization', token).body(re.compile(pattern, re.S)).reply(200).json(response)


def page(nodes, cursor=None):
    return {'data': {'account': {'transactions': {
        'pageInfo': {'hasNextPage': cursor is not None, 'endCursor': cursor},
        'edges': [{'node': node} for node in nodes],
    }}}}


def test_tariff_includes_time_of_use_scheme():
    scheme = {'name': 'IOG_ECO7_TOU', 'timezone': 'Europe/London', 'timeslots': []}
    with pook.use():
        stub_token()
        stub_query('getProperties', {'data': {'account': {'electricityAgreements': [{
            'validFrom': '2026-07-14T23:00:00+00:00', 'validTo': None,
            'tariff': {'tariffCode': 'E-1R-IOG-SMB-VAR-24-10-29-C', 'unitRates': []},
            'timeOfUseScheme': scheme,
        }]}}}, 'tok', *TARIFF_FIELDS)
        compare(OctopusGraphQLClient('key').tariff('A-123'), expected={
            'tariffCode': 'E-1R-IOG-SMB-VAR-24-10-29-C', 'unitRates': [], 'timeOfUseScheme': scheme,
            'agreementValidFrom': '2026-07-14T23:00:00+00:00',
        })
        compare(pook.isdone(), expected=True)


def test_dispatches():
    dispatches = {'plannedDispatches': [], 'completedDispatches': []}
    with pook.use():
        stub_token()
        stub_query('getCombinedData', {'data': dispatches}, 'tok', *DISPATCH_FIELDS)
        compare(OctopusGraphQLClient('key').dispatches('A-123'), expected=dispatches)
        compare(pook.isdone(), expected=True)


def test_transactions_paginates():
    with pook.use():
        stub_token()
        stub_query('getTransactions', page([{'id': 1}, {'id': 2}], cursor='c1'), 'tok', '"after": null',
                   *TRANSACTION_FIELDS)
        stub_query('getTransactions', page([{'id': 3}]), 'tok', '"after": "c1"')
        compare(OctopusGraphQLClient('key').transactions('A-123'), expected=[{'id': 1}, {'id': 2}, {'id': 3}])
        compare(pook.isdone(), expected=True)


def test_expired_token_is_refreshed():
    with pook.use():
        stub_token('old')
        stub_query('getTransactions', {'data': None, 'errors': [{'message': 'Signature of the JWT has expired.'}]},
                   'old')
        stub_token('new')
        stub_query('getTransactions', page([{'id': 1}]), 'new')
        compare(OctopusGraphQLClient('key').transactions('A-123'), expected=[{'id': 1}])
        compare(pook.isdone(), expected=True)


def test_other_query_error_raises_with_note():
    with pook.use():
        stub_token()
        stub_query('getTransactions', {'data': None, 'errors': [{'message': 'Unauthorized.'}]})
        with ShouldRaise(TransportQueryError) as s:
            OctopusGraphQLClient('key').transactions('A-123')
    compare(s.raised.__notes__, expected=["message was: 'Unauthorized.'"])


def test_smart_device_ids():
    with pook.use():
        stub_token()
        stub_query('getSmartDevices', {'data': {'account': {'electricityAgreements': [{'meterPoint': {'meters': [
            {'smartDevices': [{'deviceId': 'D1'}]}, {'smartDevices': []},
        ]}}]}}}, 'tok', *DEVICE_FIELDS)
        compare(OctopusGraphQLClient('key').smart_device_ids('A-123'), expected=['D1'])
        compare(pook.isdone(), expected=True)


def test_telemetry():
    readings = [{'readAt': '2026-10-29T20:53:00+00:00', 'demand': '1860.0'}]
    with pook.use():
        stub_token()
        stub_query('getTelemetry', {'data': {'smartMeterTelemetry': readings}}, 'tok', *TELEMETRY_FIELDS,
                   '"deviceId": "D1"', '"start": "2026-10-29T20:48:00+00:00"',
                   '"end": "2026-10-29T20:53:00+00:00"')
        compare(OctopusGraphQLClient('key').telemetry(
            'D1', Timestamp('2026-10-29T20:48', tz='UTC'), Timestamp('2026-10-29T20:53', tz='UTC')
        ), expected=readings)
        compare(pook.isdone(), expected=True)


def test_telemetry_none():
    with pook.use():
        stub_token()
        stub_query('getTelemetry', {'data': {'smartMeterTelemetry': None}})
        compare(OctopusGraphQLClient('key').telemetry(
            'D1', Timestamp('2026-10-29T20:48', tz='UTC'), Timestamp('2026-10-29T20:53', tz='UTC')
        ), expected=[])
        compare(pook.isdone(), expected=True)
