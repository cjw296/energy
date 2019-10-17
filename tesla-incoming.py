import time
from csv import DictReader
from pathlib import Path

import pendulum
from configurator import Config
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

FILENAME = 'data.csv'  # yeah, thanks Tesla...


def move(source_path: Path, dest: Path):
    dates = set()
    with source_path.open() as source:
        reader = DictReader(source)
        for row in reader:
            dates.add(pendulum.parse(row['Date time']).date())
    assert len(dates) == 1, dates
    dest_path = dest / f'tesla-{next(iter(dates))}.csv'
    print(f'Moving {source_path} to {dest_path}')
    source_path.rename(dest_path)


class IncomingEventHandler(FileSystemEventHandler):

    def __init__(self, dest: Path):
        self.dest = dest

    def on_created(self, event):
        source_path = Path(event.src_path)
        if source_path.name == FILENAME:
            move(source_path, self.dest)


if __name__ == "__main__":
    config = Config.from_path('config.yaml')
    source_dir = Path(config.directories.incoming).expanduser()
    dest = Path(config.directories.storage).expanduser()

    path = source_dir / FILENAME
    if path.exists():
        move(path, dest)

    event_handler = IncomingEventHandler(dest)
    observer = Observer()
    observer.schedule(event_handler, str(source_dir))
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
