#!/bin/bash
set -ex

echo "=== Syncing dependencies ==="
uv sync

echo "=== Tests ==="
uv run pytest

echo "=== All checks passed! ==="
