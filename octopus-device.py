from pprint import pprint

from configurator import Config
from octopus import OctopusGraphQLClient

config = Config.from_path('config.yaml')
api_key = config.octopus.api_key
account = config.octopus.account

graphql_client = OctopusGraphQLClient(api_key)


pprint(graphql_client.query(
    "RegisteredKrakenflexDevice",
    query='''
        query RegisteredKrakenflexDevice($accountNumber: String!) {
              registeredKrakenflexDevice(accountNumber: $accountNumber) {
                krakenflexDeviceId
                provider
                vehicleMake
                vehicleModel
                vehicleBatterySizeInKwh
                chargePointMake
                chargePointModel
                chargePointPowerInKw
                status
                suspended
                hasToken
                createdAt
                testDispatchFailureReason
              }
        }
        ''',
    params={"accountNumber": account},
))
