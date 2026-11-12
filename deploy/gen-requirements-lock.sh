#!/usr/bin/env bash
set -euo pipefail

# Regenerates deploy/requirements.lock (pinned, hashed runtime deps of backend/pyproject.toml) for the release venv install `pip install --require-hashes -r`. Run on a Linux box or CI with the same Python minor as the container (3.13 on Debian 13), then commit the result.

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${PEARLIE_LOCK_PY:-python3}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

"$PY" -m venv "$tmp/v"

BIN="$tmp/v/bin"
if [[ -d "$tmp/v/Scripts" ]]; then
  BIN="$tmp/v/Scripts"
fi

"$BIN/pip" install --quiet pip-tools
"$BIN/pip-compile" --quiet --generate-hashes --allow-unsafe --strip-extras \
  --output-file deploy/requirements.lock backend/pyproject.toml

echo "wrote deploy/requirements.lock"
