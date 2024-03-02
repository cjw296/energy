import difflib
import shlex
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from colorama import Fore
from configurator import Config
from pandas import Timestamp

from common import add_log_level, configure_logging, root_from


def color_diff(diff):
    for line in diff:
        if line.startswith('+'):
            yield Fore.GREEN + line + Fore.RESET
        elif line.startswith('-'):
            yield Fore.RED + line + Fore.RESET
        elif line.startswith('^'):
            yield Fore.BLUE + line + Fore.RESET
        else:
            yield line


@dataclass
class DiffData:
    name: str
    lines: list[str]


def diff(a: DiffData, b: DiffData):
    raw_diff = difflib.unified_diff(a.lines, b.lines, a.name, b.name)
    return ''.join(color_diff(raw_diff))


PATTERN = "%Y-%m-%d-%H-%M-%S.json"
DASH_COUNT = PATTERN.count('-')+1


def datetime_from_path(path: Path) -> datetime:
    parts = path.name.rsplit('-', DASH_COUNT)
    return datetime.strptime('-'.join(parts[1:]), "%Y-%m-%d-%H-%M-%S.json")


def extract(path: Path) -> DiffData:
    d = datetime_from_path(path)
    return DiffData(
        f'{shlex.quote(str(path))} ({d:%a %d %b %y %H:%M:%S})',
        path.read_text().splitlines(keepends=True)
    )


def main():
    config = Config.from_path('config.yaml')
    root = root_from(config)

    parser = ArgumentParser()
    parser.add_argument('prefix')
    parser.add_argument('--start', type=Timestamp)
    parser.add_argument('--end', type=Timestamp)
    add_log_level(parser)

    args = parser.parse_args()
    configure_logging(args.log_level)

    paths = sorted(root.glob(f'{args.prefix}*'))
    for path1, path2 in zip(paths, paths[1:]):
        if all((
            args.start is None or datetime_from_path(path1) > args.start,
            args.end is None or datetime_from_path(path2) < args.end,
        )):
            print(diff(extract(path1), extract(path2)))
            print()


if __name__ == '__main__':
    main()
