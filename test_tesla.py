import json
from functools import partial

from testfixtures import Replace, compare as compare_, ShouldRaise, mock_time

compare = partial(compare_, strict=True)

from tesla import parse_tesla_auth_output, parse_tesla_auth_section, seed_tesla_token

OUTPUT = """
--------------------------------- ACCESS TOKEN ---------------------------------

fake-access-token

--------------------------------- REFRESH TOKEN --------------------------------

fake-refresh-token

----------------------------------- VALID FOR ----------------------------------

8 hours
"""


def test_parse_tesla_auth_section():
    compare(parse_tesla_auth_section(OUTPUT, 'REFRESH TOKEN'), expected='fake-refresh-token')


def test_parse_tesla_auth_section_missing():
    with ShouldRaise(ValueError('No REFRESH TOKEN section found in tesla_auth output')):
        parse_tesla_auth_section('nothing useful here', 'REFRESH TOKEN')


def test_parse_tesla_auth_output():
    t = mock_time(2026, 7, 17, delta=0)
    with Replace('tesla.time', t):
        compare(parse_tesla_auth_output(OUTPUT), expected={
            'access_token': 'fake-access-token',
            'refresh_token': 'fake-refresh-token',
            'expires_in': 28800,
            'expires_at': t() + 28800,
            'token_type': 'Bearer',
        })


def test_parse_tesla_auth_output_minutes():
    output = OUTPUT.replace('8 hours', '45 minutes')
    compare(parse_tesla_auth_output(output)['expires_in'], expected=2700)


def test_seed_tesla_token_ignores_stale_cache_missing_expires_at(tmp_path):
    # reproduces a cache.json written before expires_at was seeded (see
    # parse_tesla_auth_output): Tesla.__init__ used to crash reading this,
    # before the fresh token below was ever assigned.
    cache_file = tmp_path / 'cache.json'
    cache_file.write_text(json.dumps({
        'person@example.com': {
            'url': 'https://auth.tesla.com/',
            'sso': {
                'access_token': 'stale-access-token',
                'refresh_token': 'stale-refresh-token',
                'expires_in': 28800,
                'token_type': 'Bearer',
            },
        },
    }))
    token = {
        'access_token': 'fresh-access-token',
        'refresh_token': 'fresh-refresh-token',
        'expires_in': 28800,
        'expires_at': 9999999999,
        'token_type': 'Bearer',
    }
    tesla = seed_tesla_token('person@example.com', token, cache_file=str(cache_file))
    compare(tesla.token, expected=token)
    compare(
        json.loads(cache_file.read_text())['person@example.com']['sso'],
        expected=token,
    )
