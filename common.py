import json
import logging
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Callable, Iterator

from configurator import Config
from pandas import Timestamp, date_range

Action = Callable[[Config, Timestamp, Timestamp, Path], None]
ActionMapping = dict[str, Action]


def collect(*actions: Action) -> ActionMapping:
    mapping = {}
    for action in actions:
        mapping[action.__name__.replace('_', '-')] =  action
        mapping[action.__name__] = action
    return mapping


def main(actions: ActionMapping) -> None:
    log_levels = logging.getLevelNamesMapping()
    parser = ArgumentParser()
    parser.add_argument('action', choices=actions.keys())
    parser.add_argument('--log-level',
                        choices=[name.lower() for name in log_levels],
                        default='info')
    parser.add_argument('--start', type=Timestamp, help='YY-mm-dd', required=True)
    parser.add_argument('--end', type=Timestamp, help='YY-mm-dd', required=True)
    args = parser.parse_args()

    logging.basicConfig(level=log_levels[args.log_level.upper()], stream=sys.stdout)
    logging.raiseExceptions = False

    config = Config.from_path('config.yaml')
    start = min(args.start, args.end)
    end = max(args.start, args.end)
    root = Path(config.directories.storage).expanduser()
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
