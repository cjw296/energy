import json
from argparse import ArgumentParser
from pathlib import Path
from pprint import pprint


def main():
    parser = ArgumentParser()
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    pprint(json.loads(args.path.read_text()))


if __name__ == '__main__':
    main()
