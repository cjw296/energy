from functools import partial

import requests
from gql.transport.exceptions import TransportConnectionFailed
from testfixtures import LogCapture, ShouldRaise, compare as compare_

from common import log_timeouts_and_return_none

compare = partial(compare_, strict=True)


def raising(exception: Exception):
    @log_timeouts_and_return_none
    def fetch():
        raise exception
    return fetch


def connection_failed(cause: Exception) -> TransportConnectionFailed:
    try:
        raise TransportConnectionFailed('failed') from cause
    except TransportConnectionFailed as failure:
        return failure


def test_timeout_error():
    with LogCapture() as logs:
        compare(raising(TimeoutError())(), expected=None)
    logs.check(('root', 'WARNING', 'Timeout getting fetch'), ('root', 'DEBUG', 'Timeout getting fetch'))


def test_requests_timeout():
    with LogCapture() as logs:
        compare(raising(connection_failed(requests.exceptions.ReadTimeout()))(), expected=None)
    logs.check(('root', 'WARNING', 'Timeout getting fetch'), ('root', 'DEBUG', 'Timeout getting fetch'))


def test_other_connection_failure_raises():
    failure = connection_failed(requests.exceptions.ConnectionError('refused'))
    with ShouldRaise(failure):
        raising(failure)()
