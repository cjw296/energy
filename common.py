import json
import logging
import re
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from configurator import Config
from pandas import Timestamp, date_range, to_datetime

Action = Callable[[Config, Timestamp, Timestamp, Path], None]
ActionMapping = dict[str, Action]


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
        if text=='now':
            return Timestamp.now()
        index = self.name_to_index.get(text)
        if index is not None:
            paths = self.root.glob(re.sub(r'%.', '*', self.pattern))
            possible = sorted(to_datetime(p.name, format=self.pattern) for p in paths)
            return possible[index]
        return Timestamp(text)

    def add_argument(self, parser, name):
        parser.add_argument('--'+name, type=self, help='YY-mm-dd, max, min or now', required=True)


LOG_LEVELS = logging.getLevelNamesMapping()


def add_log_level(parser):
    parser.add_argument('--log-level',
                        choices=[name.lower() for name in LOG_LEVELS],
                        default='info')


def configure_logging(log_level: str) -> None:
    logging.basicConfig(level=LOG_LEVELS[log_level.upper()], stream=sys.stdout, force=True)
    logging.raiseExceptions = False


def main(actions: ActionMapping, pattern) -> None:
    config = Config.from_path('config.yaml')
    root = Path(config.directories.storage).expanduser()

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
