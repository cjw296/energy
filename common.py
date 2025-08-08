import difflib
import json
import logging
import re
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import timedelta, datetime
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from time import sleep
from typing import Callable, Iterator, ParamSpec, Self, Any, TypeVar

from configurator import Config
from mailinglogger import MailingLogger
from pandas import Timestamp, date_range, to_datetime

Action = Callable[[Config, Timestamp, Timestamp, Path], None]
ActionMapping = dict[str, Action]

# Average Gregorian year = 365.2425 days (400 year cycle: 97 leap years + 303 regular years)
DAYS_PER_YEAR = 365.2425

# Average month = 30.4369 days (DAYS_PER_YEAR / 12)
DAYS_PER_MONTH = 30.4369


def collect(*actions: Action) -> ActionMapping:
    mapping = {}
    for action in actions:
        mapping[action.__name__.replace('_', '-')] =  action
        mapping[action.__name__] = action
    return mapping


@dataclass(unsafe_hash=True)
class TimestampArg:
    root: Path
    pattern: str

    name_to_index = {
        'max': -1,
        'min': 0
    }

    def __call__(self, text: str) -> Timestamp:
        if text == 'now':
            return Timestamp.now()
        index = self.name_to_index.get(text)
        if index is not None:
            pattern = re.sub(r'%.', '*', self.pattern)
            paths = self.root.glob(pattern)
            if not paths:
                raise ValueError(f'No paths found matching {pattern} at {self.root}')
            possible = []
            for p in paths:
                try:
                    dt = to_datetime(p.name, format=self.pattern)
                except ValueError:
                    pass
                else:
                    possible.append(dt)
            possible.sort()
            return possible[index]
        return to_datetime(text, format="%y-%m-%d")

    def add_argument(self, parser, name):
        parser.add_argument('--'+name, type=self, help='YY-mm-dd, max, min or now', required=True)


LOG_LEVELS = logging.getLevelNamesMapping()


def add_log_level(parser):
    parser.add_argument('--log-level',
                        choices=[name.lower() for name in LOG_LEVELS],
                        default='info')
    parser.add_argument('--unattended', action='store_true')


def configure_logging(log_level: str, unattended: bool = False) -> None:
    line_format = "%(asctime)s %(levelname)s:%(name)s:%(message)s"
    date_format = '%Y-%m-%d %H:%M:%S'
    stdout_level = LOG_LEVELS[log_level.upper()]
    logging.basicConfig(
        format=line_format,
        datefmt=date_format,
        level=stdout_level,
        stream=sys.stdout,
        force=True
    )
    logging.raiseExceptions = False
    if unattended:
        script_name = sys.argv[0]
        root = logging.getLogger()
        root.handlers[0].setLevel(stdout_level)
        root.setLevel(logging.DEBUG)
        # file logging
        handler = TimedRotatingFileHandler(
            Path(script_name).with_suffix('.log'),
            backupCount=7,
            when='midnight',
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(line_format, date_format))
        root.addHandler(handler)
        # email alerts
        handler = MailingLogger(
            'support@simplistix.co.uk',
            ['chris@withers.org'],
            subject=f'[{script_name}] %(levelname)s: %(line)s',
            flood_level=1,
        )
        handler.setLevel(logging.ERROR)
        root.addHandler(handler)
        # quieten down some debug logging:
        logging.getLogger('requests_oauthlib').setLevel(logging.WARNING)


def root_from(config: Config) -> Path:
    return Path(config.directories.storage).expanduser()


def main(actions: ActionMapping, pattern) -> None:
    config = Config.from_path('config.yaml')
    root = root_from(config)

    parser = ArgumentParser()
    parser.add_argument('action', choices=actions.keys())
    add_log_level(parser)
    timestamp = TimestampArg(root, pattern)
    timestamp.add_argument(parser, 'start')
    timestamp.add_argument(parser, 'end')
    args = parser.parse_args()

    configure_logging(args.log_level)

    start = min(args.start, args.end)
    end = max(args.start, args.end)
    actions[args.action](config, start, end, root)


def file_paths(root: Path, pattern: str, start: Timestamp, end: Timestamp) -> Iterator[Path]:
    for ts in date_range(start=end, end=start, freq='-1D'):
        path = root / ts.strftime(pattern)
        if not path.exists():
            logging.warning(f'{path} does not exist')
            continue
        yield path


def json_from_paths(root: Path, pattern: str, start: Timestamp, end: Timestamp) -> Iterator[tuple[Path, dict]]:
    for path in file_paths(root, pattern, start, end):
        yield path, json.loads(path.read_bytes())


class DiffDumper:

    def __init__(self, target: Path, prefix: str):
        self.target = target
        self.prefix = prefix
        self.state = self.load_latest()

    def load_latest(self):
        sources = sorted(self.target.glob(f"{self.prefix}*.json"))
        if sources:
            latest = sources[-1]
            logging.info(f'{latest=}')
            return json.loads(latest.read_text())

    def update(self, state, force: bool = False):
        if force or self.state != state:
            logging.debug(f"state changed for {self.prefix}")
            dest = self.target / f"{self.prefix}-{datetime.now():%Y-%m-%d-%H-%M-%S}.json"
            dest.write_text(json.dumps(state, indent=4))
            logging.info(f'wrote {dest}')
            self.state = state


P = ParamSpec('P')
T = TypeVar('T')
timedelta_P = ParamSpec('timedelta_P', bound=timedelta)


class Run:

    def __init__(self, callable_: Callable[P, None]):
        self.callable_ = callable_
        self.args = ()
        self.kw = {}

    def __call__(self, *args: P.args, **kw: P.kwargs) -> Self:
        self.args = args
        self.kw = kw
        return self

    def once(self) -> None:
        self.callable_(*self.args, **self.kw)

    def every(self, **kwargs: timedelta_P.kwargs) -> None:
        delay = timedelta(**kwargs).total_seconds()
        try:
            while True:
                try:
                    self.callable_(*self.args, **self.kw)
                except Exception:
                    logging.exception(f'{self.callable_} failed')
                sleep(delay)
        except KeyboardInterrupt:
            pass


def diff(a: Any, b: Any, a_label: str = '', b_label: str = ''):
    return ''.join(difflib.unified_diff(
        str(a).splitlines(keepends=True),
        str(b).splitlines(keepends=True),
        a_label,
        b_label
    ))


def log_timeouts_and_return_none(c: Callable[P, T]) -> Callable[P, T | None]:

    @wraps(c)
    def _run(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return c(*args, **kwargs)
        except TimeoutError:
            message = f'Timeout getting {c.__name__}'
            logging.warning(message)
            logging.debug(message, exc_info=True)
            return

    return _run
