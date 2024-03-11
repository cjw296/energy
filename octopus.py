import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from decimal import Decimal
from itertools import chain
from pprint import pformat
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError
from pandas import Timestamp, date_range, Timedelta
from requests import JSONDecodeError


@dataclass
class Rates:
    low: float
    high: float


BASE_URL = "https://api.octopus.energy/v1/"


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
        self._transport = AIOHTTPTransport(BASE_URL + "/graphql/", headers={})
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
                e.add_node(f'message was: {message!r}')
                raise

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
                                validTo
                                validFrom
                              }
                            }
                        }
                      }
                  }
                }
            """,
            params={'accountNumber': account}
        )
        agreement, = data['account']['electricityAgreements']
        return agreement['tariff']


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
        print()
        for start, cost in self.entries.items():
            start = start.astimezone(tz) if tz is not None else start
            if start >= midnight:
                start = timestamp_on_different_day(start, offset=-1)
                before.append((start, cost))
            else:
                after.append((start, cost))
        schedule = list(self._compress(chain(before, after)))
        return [TimeSlot(e.start.time(), e.end.time(), e.cost) for e in schedule]
