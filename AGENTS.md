# Agent Instructions

## Principles

- **Done means green**: a change is only complete when `./happy.sh` exits 0; do not commit until it does.
- **No unrelated failures**: if `./happy.sh` fails on something unrelated to your changes, do NOT assume it is a pre-existing problem and proceed anyway. Stop immediately and ask the user how to proceed.
- **Use `compare()` in tests**: never use bare `assert` statements; always use `compare(actual, expected=...)` from `testfixtures` for assertions.
- **All new code must be tested**: no untested functionality, ever.
- **Stub HTTP with `pook`**: in tests, intercept HTTP calls with `pook` (a dev dependency) rather than injecting callables or `Mock`s into production code just to make it testable.
- **Reproduce before fixing**: when fixing a bug, add a failing test and watch it fail before changing any code.
- **Succinct, high-signal prose**: in docs, comments, and messages to the user, say only what adds information; cut filler.
- **Commit messages explain why, succinctly**: the diff already shows what changed; the message states the reason, briefly.
- **The why goes in the commit message, not a comment**: don't add a code comment restating the reasoning already captured in the commit message; if the reasoning genuinely needs to live in the code (surprising invariant a reader would hit without it), that's the exception, not the default.
- **Ignore Pyright diagnostics**: this project doesn't use Pyright; any diagnostics shown are just the editor's LSP and are not a signal about this codebase.

## Project Overview

Personal energy-data tooling: downloads and reconciles half-hourly electricity usage from
Octopus and Tesla, and calculates bills. A flat collection of scripts and notebooks rather
than an installable package; there is no `src/` layout.

The most important script is `octopus-tesla-sync.py`. It runs continuously in production
(`--run-every 2`, i.e. every 2 minutes) and keeps the Tesla Powerwall's tariff config in
sync with Octopus: it fetches the current Octopus agreement's unit rates and any planned
dispatches (smart/EV charge slots) via GraphQL, turns them into a Tesla time-of-use tariff
via `schedule.make_seasons_and_energy_charges`, and pushes it to the battery with
`Battery.set_tariff` whenever it differs from what's currently set. This is how off-peak
dispatch windows actually translate into cheap EV charging, so correctness and robustness
here (timezones, rate parsing, dispatch handling, the diffing that avoids redundant Tesla
API writes) matter more than anywhere else in the repo. It runs unattended, so failures
are logged and can trigger email alerts (see `common.configure_logging`); treat exceptions
raised from inside the sync loop as something a human needs to know about, not something
to swallow silently.

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

## Data downloads

Run from a directory containing `config.yaml`; files land in `directories.storage`.

```bash
uv run python octopus-download.py --start 2025-09-05 --end 2026-09-09   # octopus-DATE.csv
uv run python myenergi.py download --start 2026-04-15 --end 2026-09-09  # zappi-DATE.json
uv run python myenergi.py json_to_csv --start 2026-04-15 --end 2026-09-09
uv run python tesla.py download --start 2026-04-15 --end 2026-09-09     # tesla-DATE.json
uv run python tesla.py json_to_csv --start 2026-04-15 --end 2026-09-09
uv run python tesla.py check --start min --end max                      # report missing samples
```

- `myenergi.py` and `tesla.py` take `--start`/`--end` as `YYYY-MM-DD`, `now`, or `min`/`max`
  (earliest/latest existing file of that kind); `octopus-download.py` takes dates only.
- `octopus-DATE.csv`: half-hourly grid import (kWh). Days with the wrong number of readings
  are saved as `octopus-DATE-suspect.csv`.
- `zappi-DATE.csv`: per-minute; `imp`/`exp` grid import/export and `h1b`/`h1d` zappi charge
  from grid/diverted, in joules, with `_kw` columns in kW.
- `tesla-DATE.csv`: 5-minute average power in W: `grid_power` (+ import), `battery_power`
  (− charging), `solar_power`. Home load = solar + battery + grid.
- `tesla.py` authenticates through TeslaPy's `cache.json` in the working directory and
  refreshes its token. On 2026-09-10 `download` failed with `403 ... see
  https://developer.tesla.com/docs/fleet-api` at `battery_list`; Tesla data stops at 2026-04-15.
- `tesla-incoming.py` is legacy: it watched for Tesla app `data.csv` exports.
- `octopus-tesla-sync.py` writes `octopus-dispatches-DATETIME.json` (dispatches, unit rates,
  agreement) whenever they change.
- `octopus-gsp.py` prints the account's GSP region; `tariff-regions.py` compares a Kraken
  product's rates across regions (Octopus, EDF, E.ON Next).
- `octopus-bill-rec.py SPREADSHEET` reconciles the Electricity sheet of the owner's
  `utilities.ods` against Octopus's billed charges (GraphQL `account.transactions`).

## Architecture

Top-level, no package structure:

- `common.py`: shared config loading, logging, CLI argument helpers
- `octopus-tesla-sync.py`: **the critical always-on script**, see Project Overview above
- `octopus.py` / other `octopus-*.py`: Octopus Energy API client, download and billing scripts
- `tesla.py` / other `tesla-*.py`: Tesla API client, backup/incoming/schedule scripts
- `myenergi.py`: myenergi (Harvi/Zappi) API client
- `kraken.py`: public Kraken product API (Octopus, EDF, E.ON Next) regional rates
- `billrec.py`: spreadsheet-vs-Octopus bill reconciliation; `billcheck.py`: checks billed
  usage against the sync's tariff model (run by `octopus-bill-rec.py` and daily by the sync)
- `fitmodel.py` / `fit-export-model.py`: FiT deemed export vs metered export, from Tesla and
  zappi data plus the spreadsheet's Solar sheet
- `loaders.py`: pandas loaders for downloaded Octopus/Tesla CSVs
- `schedule.py`: charge scheduling logic
- `usage.py`, `show-changes.py`, `pretty.py`: reporting/inspection utilities
- `*.ipynb`: exploratory notebooks, not covered by tests
- `test_*.py`: the test suite, using `testfixtures`

Config: `config.sample.yaml` is the template; a user's own `config.yaml` is gitignored.
