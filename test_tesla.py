from functools import partial

from testfixtures import compare as compare_, ShouldRaise

compare = partial(compare_, strict=True)

from tesla import parse_refresh_token


def test_parse_refresh_token():
    output = """
--------------------------------- ACCESS TOKEN ---------------------------------

fake-access-token

--------------------------------- REFRESH TOKEN --------------------------------

fake-refresh-token

----------------------------------- VALID FOR ----------------------------------

8 hours
"""
    compare(parse_refresh_token(output), expected='fake-refresh-token')


def test_parse_refresh_token_missing():
    with ShouldRaise(ValueError('No REFRESH TOKEN section found in tesla_auth output')):
        parse_refresh_token('nothing useful here')
