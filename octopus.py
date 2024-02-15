from dataclasses import dataclass
from typing import Any

import requests
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
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
        current = [a for a in agreements if a['valid_to'] is None]
        assert len(current) == 1, f'multiple current agreements found: {current}'
        return current[0]['tariff_code']

    def current_gas_tariff_code(self, account):
        return self.current_tariff_code(account, 'gas_meter_points')

    def current_electricity_tariff_code(self, account):
        return self.current_tariff_code(account, 'electricity_meter_points')

    def current_unit_rates(self, account, point_type, key):
        tariff_code = self.current_tariff_code(account, point_type)
        product_code = '-'.join(tariff_code.split('-')[2:-1])
        uri = f'/products/{product_code}/electricity-tariffs/{tariff_code}'
        data = self.get(uri + '/standard-unit-rates/?page_size=2')
        prices = [round(d[key], 1) for d in data['results']]
        return Rates(min(prices), max(prices))

    def current_gas_rates(self, account, key='value_inc_vat'):
        return self.current_unit_rates(account, 'gas_meter_points', key)

    def current_electricity_rates(self, account, key='value_inc_vat'):
        return self.current_unit_rates(account, 'electricity_meter_points', key)


class OctopusGraphQLClient:

    def __init__(self, api_key):
        self._api_key = api_key
        self._transport = AIOHTTPTransport(BASE_URL + "/graphql/", headers={})
        self._client = Client(transport=self._transport, fetch_schema_from_transport=True)

    def _query(self, operation_name: str, query: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._client.execute(
            gql(query), variable_values=params, operation_name=operation_name
        )

    def obtain_token(self) -> str:
        result = self._query(
            "krakenTokenAuthentication",
            query = (
                '''
                  mutation krakenTokenAuthentication($apiKey: String!) {
                    obtainKrakenToken(input: { APIKey: $apiKey })
                    {
                      token
                    }
                  }
                '''),
            params = {"apiKey": self._api_key},
        )
        return result['obtainKrakenToken']['token']

    def query(self, operation_name: str, query: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._transport.headers.get('Authorization') is None:
            self._transport.headers['Authorization'] = self.obtain_token()
        return self._query(operation_name, query, params)
