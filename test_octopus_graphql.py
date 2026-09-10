from functools import partial
from unittest.mock import ANY, Mock, call

from testfixtures import compare as compare_

from octopus import OctopusGraphQLClient

compare = partial(compare_, strict=True)


def page(nodes, cursor=None):
    return {'account': {'transactions': {
        'pageInfo': {'hasNextPage': cursor is not None, 'endCursor': cursor},
        'edges': [{'node': node} for node in nodes],
    }}}


def test_tariff_includes_time_of_use_scheme():
    scheme = {'name': 'IOG_ECO7_TOU', 'timezone': 'Europe/London', 'timeslots': []}
    client = OctopusGraphQLClient('key')
    client.query = Mock(return_value={'account': {'electricityAgreements': [{
        'validFrom': '2026-07-14T23:00:00+00:00', 'validTo': None,
        'tariff': {'tariffCode': 'E-1R-IOG-SMB-VAR-24-10-29-C', 'unitRates': []},
        'timeOfUseScheme': scheme,
    }]}})
    compare(client.tariff('A-123'), expected={
        'tariffCode': 'E-1R-IOG-SMB-VAR-24-10-29-C', 'unitRates': [], 'timeOfUseScheme': scheme,
    })


def test_transactions_paginates():
    client = OctopusGraphQLClient('key')
    client.query = Mock(side_effect=[page([{'id': 1}, {'id': 2}], cursor='c1'), page([{'id': 3}])])
    compare(client.transactions('A-123'), expected=[{'id': 1}, {'id': 2}, {'id': 3}])
    compare(list(client.query.mock_calls), expected=[
        call('getTransactions', query=ANY, params={'accountNumber': 'A-123', 'after': None}),
        call('getTransactions', query=ANY, params={'accountNumber': 'A-123', 'after': 'c1'}),
    ])
