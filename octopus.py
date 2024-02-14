import json

import requests
from requests import JSONDecodeError


class OctopusRESTClient:

    def __init__(self, api_key, base_url="https://api.octopus.energy/v1/"):
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
