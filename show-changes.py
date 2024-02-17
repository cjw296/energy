import difflib
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from colorama import Fore
from configurator import Config

from common import add_log_level, configure_logging


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


def extract(path: Path) -> DiffData:
    parts = path.name.rsplit('-', DASH_COUNT)
    d = datetime.strptime('-'.join(parts[1:]), "%Y-%m-%d-%H-%M-%S.json")
    return DiffData(
        f'{path.name} ({d:%a %d %b %y %H:%M:%S})',
        path.read_text().splitlines(keepends=True)
    )


def main():
    parser = ArgumentParser()
    parser.add_argument('prefix')
    parser.add_argument('query', nargs='?')
    add_log_level(parser)

    args = parser.parse_args()
    configure_logging(args.log_level)

    config = Config.from_path('config.yaml')
    paths = sorted(Path(config.directories.storage).expanduser().glob(f'{args.prefix}*'))
    for path1, path2 in zip(paths, paths[1:]):
        print(diff(extract(path1), extract(path2)))
        print()

    print(paths[-2:])

if __name__ == '__main__':
    main()
