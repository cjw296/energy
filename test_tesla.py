import json
from functools import partial
from zoneinfo import ZoneInfo

from pandas import Timestamp, date_range
from testfixtures import LogCapture, Replace, compare as compare_, ShouldRaise, mock_time

compare = partial(compare_, strict=True)

from tesla import check, check_measurement_count, tesla_end_dates, parse_tesla_auth_output, parse_tesla_auth_section, seed_tesla_token

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


def power_day(day: str, *skip: str) -> dict:
    moments = date_range(day, periods=2, freq='D', tz='Europe/London')
    stamps = date_range(moments[0], moments[1], freq='5min', inclusive='left')
    return {'time_series': [
        {'timestamp': stamp.isoformat().replace('+00:00', 'Z')}
        for stamp in stamps if stamp.isoformat() not in skip
    ]}


def end_of(day: str) -> Timestamp:
    return Timestamp(f'{day} 23:59:59', tz='Europe/London')


def test_check_measurement_count_full_day():
    with LogCapture() as logs:
        check_measurement_count(power_day('2026-10-24'), end_date=end_of('2026-10-24'))
    logs.check()


def test_check_measurement_count_clocks_go_back():
    with LogCapture() as logs:
        check_measurement_count(power_day('2026-10-25'), end_date=end_of('2026-10-25'))
    logs.check()


def test_check_measurement_count_missing_on_clock_change_day():
    with LogCapture() as logs:
        check_measurement_count(power_day('2026-10-25', '2026-10-25T23:30:00+00:00'),
                                end_date=end_of('2026-10-25'))
    logs.check(
        ('root', 'WARNING', 'Expected 300, got 299 (5 mins missing), earliest found: 2026-10-25T00:00:00+01:00, '
                            'latest found: 2026-10-25T23:55:00Z, end_date=2026-10-25 23:59:59+00:00'),
        ('root', 'WARNING', 'Missing: 2026-10-25 23:30:00+00:00'),
    )


def test_check_uses_local_zone_for_saved_days(tmp_path):
    day = power_day('2026-10-25', '2026-10-25T23:30:00+00:00')
    (tmp_path / 'tesla-2026-10-25.json').write_text(json.dumps({'battery': {}, 'data': day}))
    with Replace('tesla.tzlocal', lambda: ZoneInfo('Europe/London')), LogCapture() as logs:
        check(None, Timestamp('2026-10-25'), Timestamp('2026-10-25'), tmp_path)
    logs.check(
        ('root', 'WARNING', 'Expected 300, got 299 (5 mins missing), earliest found: 2026-10-25T00:00:00+01:00, '
                            'latest found: 2026-10-25T23:55:00Z, end_date=2026-10-25 23:59:59+00:00'),
        ('root', 'WARNING', 'Missing: 2026-10-25 23:30:00+00:00'),
    )


def test_tesla_end_dates_across_clock_change():
    london = ZoneInfo('Europe/London')
    compare([(day.isoformat(), end.isoformat()) for day, end in tesla_end_dates(
        Timestamp('2026-10-24 09:00', tz=london), Timestamp('2026-10-26 21:00', tz=london), london
    )], expected=[
        ('2026-10-24T00:00:00+01:00', '2026-10-24T23:59:59+01:00'),
        ('2026-10-25T00:00:00+01:00', '2026-10-25T23:59:59+00:00'),
        ('2026-10-26T00:00:00+00:00', '2026-10-26T23:59:59+00:00'),
    ])
