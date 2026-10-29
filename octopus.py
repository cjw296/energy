import logging
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from itertools import chain
from pprint import pformat
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from gql.transport.exceptions import TransportQueryError
from pandas import Timestamp, date_range, Timedelta
from requests import JSONDecodeError

from common import log_timeouts_and_return_none


@dataclass
class Rates:
    low: float
    high: float


BASE_URL = "https://api.octopus.energy/v1/"
GRAPHQL_TIMEOUT = 30


def readings_by_day(readings: list[dict], tz: ZoneInfo) -> dict[date, list[dict]]:
    """
    Readings in time order, grouped by local date.
    """
    by_day: dict[date, list[dict]] = {}
    for reading in sorted(readings, key=lambda reading: Timestamp(reading['interval_start'])):
        day = Timestamp(reading['interval_start']).tz_convert(tz).date()
        by_day.setdefault(day, []).append(reading)
    return by_day


class OctopusRESTClient:

    def __init__(self, api_key, base_url=BASE_URL):
        self.session = requests.Session()
        self.session.auth = (api_key, '')
        self.base_url = base_url.rstrip('/')

    def get(self, url, **params):
        if not url.startswith(self.base_url):
            url = self.base_url + url
        response = self.session.get(url, params=params)
        try:
            data = response.json()
        except JSONDecodeError:
            raise Exception(response.text or response.status_code)
        else:
            if response.status_code != 200:
                raise Exception(repr(data))
            return data

    def meter_point(self, account, point_type):
        data = self.get(f'/accounts/{account}/')
        properties = data['properties']
        assert len(properties) == 1, f'multiple properties found {properties}'
        points = properties[0][point_type]
        if not points:
            return None
        assert len(points) == 1, f'more than one point found: {points}'
        return points[0]

    def consumption(
            self, mpan: str, serials: list[str], start: Timestamp, end: Timestamp
    ) -> dict[Timestamp, float]:
        """Half-hourly import in kWh keyed by UTC interval start, summed across meters."""
        totals: dict[Timestamp, float] = {}
        for serial in serials:
            for reading in self.readings(
                    'electricity-meter-points', mpan, serial, start.isoformat(), end.isoformat()
            ):
                interval = Timestamp(reading['interval_start']).tz_convert('UTC')
                totals[interval] = totals.get(interval, 0.0) + reading['consumption']
        return totals

    def readings(
            self, endpoint: str, mpxn: str, serial: str,
            period_from: str | None = None, period_to: str | None = None,
    ) -> list[dict]:
        """
        One meter's half-hourly readings, fetched as a single page: when Octopus paginates
        these, its pages overlap and skip readings.
        """
        params: dict[str, Any] = {'order_by': 'period', 'page_size': 25000}
        for name, value in (('period_from', period_from), ('period_to', period_to)):
            if value is not None:
                params[name] = value
        data = self.get(f'/{endpoint}/{mpxn}/meters/{serial}/consumption/', **params)
        readings = []
        while True:
            readings.extend(data['results'])
            if not data['next']:
                break
            data = self.get(data['next'])
        seen = set()
        for reading in readings:
            start = Timestamp(reading['interval_start']).tz_convert('UTC')
            if start in seen:
                raise ValueError(f'Duplicate readings from {serial} for {start}')
            seen.add(start)
        return readings

    def unit_rates(self, product: str, tariff: str, kind: str, period_from: Timestamp) -> list[dict]:
        """
        Direct-debit unit rates of `kind` (day, night, standard...) in force since `period_from`.
        """
        data = self.get(
            f'/products/{product}/electricity-tariffs/{tariff}/{kind}-unit-rates/',
            period_from=period_from.isoformat(), page_size=1500,
        )
        rates = []
        while True:
            rates.extend(rate for rate in data['results']
                         if rate.get('payment_method') in (None, 'DIRECT_DEBIT'))
            if not data['next']:
                return rates
            data = self.get(data['next'])

    def gsp(self, mpan: str) -> str:
        return self.get(f'/electricity-meter-points/{mpan}/')['gsp']

    def current_tariff_code(self, account, point_type):
        agreements = self.meter_point(account, point_type)['agreements']
        logging.debug(f'agreements: {pformat(agreements)}')
        current = [a for a in agreements if a['valid_to'] is None]
        assert len(current) == 1, f'multiple current agreements found: {current}'
        return current[0]['tariff_code']

    def current_gas_tariff_code(self, account):
        return self.current_tariff_code(account, 'gas_meter_points')

    def current_electricity_tariff_code(self, account):
        return self.current_tariff_code(account, 'electricity_meter_points')


class OctopusGraphQLClient:

    def __init__(self, api_key):
        self._api_key = api_key
        self._transport = RequestsHTTPTransport(BASE_URL + 'graphql/', headers={}, timeout=GRAPHQL_TIMEOUT)
        self._client = Client(transport=self._transport)

    def _query(self, operation_name: str, query: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._client.execute(
            gql(query), variable_values=params, operation_name=operation_name
        )

    def obtain_token(self) -> str:
        result = self._query(
            "krakenTokenAuthentication",
            query=(
                '''
                  mutation krakenTokenAuthentication($apiKey: String!) {
                    obtainKrakenToken(input: { APIKey: $apiKey })
                    {
                      token
                    }
                  }
                '''),
            params={"apiKey": self._api_key},
        )
        return result['obtainKrakenToken']['token']

    def set_token(self):
        logging.debug('setting token')
        headers = self._transport.headers
        headers.pop('Authorization', None)
        headers['Authorization'] = self.obtain_token()

    def query(self, operation_name: str, query: str, params: dict[str, Any]) -> dict[str, Any]:
        if 'Authorization' not in self._transport.headers:
            self.set_token()
        try:
            return self._query(operation_name, query, params)
        except TransportQueryError as e:
            message = e.errors[0]['message']
            if message == 'Signature of the JWT has expired.':
                self.set_token()
                return self._query(operation_name, query, params)
            else:
                e.add_note(f'message was: {message!r}')
                raise

    def smart_device_ids(self, account: str) -> list[str]:
        data = self.query(
            'getSmartDevices',
            query='''
                query getSmartDevices($accountNumber: String!) {
                  account(accountNumber: $accountNumber) {
                    electricityAgreements(active: true) {
                      meterPoint { meters(includeInactive: false) { smartDevices { deviceId } } }
                    }
                  }
                }
            ''',
            params={'accountNumber': account},
        )
        return [
            device['deviceId']
            for agreement in data['account']['electricityAgreements']
            for meter in agreement['meterPoint']['meters']
            for device in meter['smartDevices']
        ]

    def telemetry(self, device_id: str, start: Timestamp, end: Timestamp) -> list[dict[str, Any]]:
        """
        Live readings from the Home Mini, every ten seconds; `demand` is import in watts.
        """
        data = self.query(
            'getTelemetry',
            query='''
                query getTelemetry($deviceId: String!, $start: DateTime!, $end: DateTime!) {
                  smartMeterTelemetry(deviceId: $deviceId, grouping: TEN_SECONDS, start: $start, end: $end) {
                    readAt demand
                  }
                }
            ''',
            params={'deviceId': device_id, 'start': start.isoformat(), 'end': end.isoformat()},
        )
        return data['smartMeterTelemetry'] or []

    def transactions(self, account: str) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        after = None
        while True:
            data = self.query(
                'getTransactions',
                query='''
                    query getTransactions($accountNumber: String!, $after: String) {
                      account(accountNumber: $accountNumber) {
                        transactions(first: 100, after: $after) {
                          pageInfo { hasNextPage endCursor }
                          edges { node {
                            __typename postedDate title isReversed
                            amounts { net tax gross }
                            ... on Charge {
                              isExport
                              consumption { startDate endDate quantity unit usageCost supplyCharge }
                            }
                          } }
                        }
                      }
                    }
                ''',
                params={'accountNumber': account, 'after': after},
            )
            page = data['account']['transactions']
            nodes.extend(edge['node'] for edge in page['edges'])
            if not page['pageInfo']['hasNextPage']:
                return nodes
            after = page['pageInfo']['endCursor']

    @log_timeouts_and_return_none
    def dispatches(self, account: str) -> dict[str, list[dict[str, Any]]]:
        return self.query(
            "getCombinedData",
            query='''
                query getCombinedData($accountNumber: String!) {
                    plannedDispatches(accountNumber: $accountNumber) {
                        startDtUtc: startDt
                        endDtUtc: endDt
                        chargeKwh: delta
                        meta {
                            source
                            location
                        }
                    }
                    completedDispatches(accountNumber: $accountNumber) {
                        startDtUtc: startDt
                        endDtUtc: endDt
                        chargeKwh: delta
                        meta {
                            source
                            location
                        }
                    }
                }
                ''',
            params={"accountNumber": account},
        )

    @log_timeouts_and_return_none
    def tariff(self, account: str) -> dict:
        data = self.query(
            'getProperties',
            query="""
                query getProperties($accountNumber: String!) {
                  account(accountNumber: $accountNumber) {
                      electricityAgreements(active: true) {
                         validFrom
                         validTo
                         tariff {
                            ... on HalfHourlyTariff {
                              productCode
                              tariffCode
                              fullName
                              displayName
                              unitRates {
                                value
                                preVatValue
                                validTo
                                validFrom
                                rateType
                              }
                            }
                        }
                         timeOfUseScheme {
                           name
                           timezone
                           timeslots { timeslot activeFrom activeTo }
                         }
                      }
                  }
                }
            """,
            params={'accountNumber': account}
        )
        agreement, = data['account']['electricityAgreements']
        return {
            **agreement['tariff'],
            'timeOfUseScheme': agreement['timeOfUseScheme'],
            'agreementValidFrom': agreement['validFrom'],
        }


@dataclass
class ScheduleEntry:
    start: Timestamp
    end: Timestamp
    cost: float


@dataclass
class TimeSlot:
    start: time
    end: time
    cost: float


SLOT_SIZE = Timedelta(minutes=30)


def timestamp_on_different_day(initial: Timestamp, offset: int) -> Timestamp:
    return Timestamp.combine(
        initial.date() + Timedelta(days=offset), initial.time()
    ).replace(tzinfo=initial.tzinfo)


class Schedule:

    def __init__(self, now: Timestamp):
        assert now.tzinfo is not None
        self.start = now.floor('30min', ambiguous=bool(now.fold))
        self.end = timestamp_on_different_day(self.start, offset=1)
        self.entries: dict[Timestamp, float | None] = {
            d: None for d in date_range(
                start=self.start,
                end=self.end,
                freq=SLOT_SIZE,
                inclusive='left',
            )
        }

    def add(self, start: Timestamp, end: Timestamp, cost: float) -> None:
        assert start.tzinfo is not None
        assert end.tzinfo is not None
        assert end > start, f'{end} <= {start}'

        if end < self.start or start > self.end:
            return

        current = max(start.floor('30min', ambiguous=bool(start)), self.start)
        while current < min(end.ceil('30min', ambiguous=bool(end.fold)), self.end):
            assert current in self.entries, current
            self.entries[current] = cost
            current += SLOT_SIZE

    @staticmethod
    def _compress(items: Iterable[tuple[Timestamp, float]]) -> list[ScheduleEntry]:
        missing = []
        current: ScheduleEntry | None = None
        for start, cost in items:
            if cost is None:
                missing.append(start)
            elif current is None or cost != current.cost:
                # Needed for DST transition days:
                if current is not None:
                    current.end = start
                current = ScheduleEntry(start, start+SLOT_SIZE, cost)
                yield current
            else:
                current.end = start + SLOT_SIZE
        if missing:
            raise ValueError(f'Gaps in schedule: {[str(m) for m in missing]}')

    def final(self) -> list[ScheduleEntry]:
        return list(self._compress(self.entries.items()))

    def final_times(self, tz: ZoneInfo | None = None) -> list[TimeSlot]:
        midnight = (self.start if tz is None else self.start.astimezone(tz)).ceil('1D')
        before = []
        after = []
        for start, cost in self.entries.items():
            start = start.astimezone(tz) if tz is not None else start
            if start >= midnight:
                start = timestamp_on_different_day(start, offset=-1)
                before.append((start, cost))
            else:
                after.append((start, cost))
        schedule = list(self._compress(chain(before, after)))
        return [TimeSlot(e.start.time(), e.end.time(), e.cost) for e in schedule]
