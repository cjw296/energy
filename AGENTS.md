# Agent Instructions

## Principles

- **Done means green**: a change is only complete when `./happy.sh` exits 0; do not commit until it does.
- **No unrelated failures**: if `./happy.sh` fails on something unrelated to your changes, do NOT assume it is a pre-existing problem and proceed anyway. Stop immediately and ask the user how to proceed.
- **Use `compare()` in tests**: never use bare `assert` statements; always use `compare(actual, expected=...)` from `testfixtures` for assertions.

## Project Overview

Personal energy-data tooling: downloads and reconciles half-hourly electricity usage from
Octopus and Tesla, and calculates bills. A flat collection of scripts and notebooks rather
than an installable package; there is no `src/` layout.

## Environment

```bash
uv sync                    # setup or after pulling
rm -rf .venv && uv sync    # full reset
```

## Commands

```bash
./happy.sh                        # all checks: required before commit
uv run pytest                     # all tests
uv run pytest test_octopus.py     # single file
```

## Architecture

Top-level, no package structure:

- `common.py`: shared config loading, logging, CLI argument helpers
- `octopus.py` / `octopus-*.py`: Octopus Energy API client, download and billing scripts
- `tesla.py` / `tesla-*.py`: Tesla API client, backup/incoming/schedule scripts
- `myenergi.py`: myenergi (Harvi/Zappi) API client
- `loaders.py`: pandas loaders for downloaded Octopus/Tesla CSVs
- `schedule.py`: charge scheduling logic
- `usage.py`, `show-changes.py`, `pretty.py`: reporting/inspection utilities
- `*.ipynb`: exploratory notebooks, not covered by tests
- `test_octopus.py`, `test_make_seasons.py`: the test suite, using `testfixtures`

Config: `config.sample.yaml` is the template; a user's own `config.yaml` is gitignored.
