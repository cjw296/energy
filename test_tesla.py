from functools import partial

from testfixtures import compare as compare_, ShouldRaise

compare = partial(compare_, strict=True)

from tesla import parse_tesla_auth_output, parse_tesla_auth_section

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
    compare(parse_tesla_auth_output(OUTPUT), expected={
        'access_token': 'fake-access-token',
        'refresh_token': 'fake-refresh-token',
        'expires_in': 28800,
        'token_type': 'Bearer',
    })


def test_parse_tesla_auth_output_minutes():
    output = OUTPUT.replace('8 hours', '45 minutes')
    compare(parse_tesla_auth_output(output)['expires_in'], expected=2700)
