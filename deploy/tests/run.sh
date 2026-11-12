#!/usr/bin/env bash
set -uo pipefail

TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$TESTS/../.." && pwd)"

mp() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}

pp() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$1"
  else
    printf '%s
' "$1"
  fi
}

PY=""
if command -v python >/dev/null 2>&1; then
  PY="python"
else
  PY="python3"
fi

ORIG_PATH="$PATH"
WORK="$(mktemp -d)"

SERVER_PID=""
PASS=0
FAIL=0

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

export MSYS="winsymlinks:nativestrict"

# ---- stub binaries ----------------------------------------------------------
mkdir -p "$WORK/bin"

cat > "$WORK/bin/venvpy" <<'VENV'
#!/usr/bin/env bash
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  DIR="$3"
  mkdir -p "$DIR/bin"
  cat > "$DIR/bin/pip" <<'PIP'
#!/usr/bin/env bash
echo "pip $*" >> "$STUB_LOG"
[[ -e "$STUB_STATE/pip_fail" ]] && exit 1
exit 0
PIP
  chmod +x "$DIR/bin/pip"
  echo "venv $DIR" >> "$STUB_LOG"
  exit 0
fi
exit 2
VENV
chmod +x "$WORK/bin/venvpy"

cat > "$WORK/bin/npm" <<'NPM'
#!/usr/bin/env bash
echo "npm $*" >> "$STUB_LOG"
if [[ "${1:-}" == "ci" ]]; then
  exit 0
elif [[ "${1:-}" == "run" && "${2:-}" == "build" ]]; then
  if [[ -e "$STUB_STATE/npm_fail" ]]; then
    exit 1
  fi
  mkdir -p dist
  echo ok > dist/index.html
  exit 0
fi
exit 2
NPM
chmod +x "$WORK/bin/npm"

# ---- helpers ----------------------------------------------------------------

ok() {
  printf 'PASS %s\n' "$1"
  PASS=$(( PASS + 1 ))
}

bad() {
  printf 'FAIL %s: %s\n' "$1" "$2"
  FAIL=$(( FAIL + 1 ))
}

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    ok "$name"
  else
    bad "$name" "command failed: $*"
  fi
}

finish() {
  printf '%s passed, %s failed\n' "$PASS" "$FAIL"
  if (( FAIL > 0 )); then
    exit 1
  fi
}

use_stubs() {
  local mode="$1"
  if [[ "$mode" == "full" ]]; then
    PATH="$(pp "$TESTS/stubs"):$ORIG_PATH"
    export PATH
  elif [[ "$mode" == "real" ]]; then
    if [[ ! -d "$WORK/stubs-real" ]]; then
      mkdir -p "$WORK/stubs-real"
      cp "$TESTS/stubs/flock" "$WORK/stubs-real/flock"
      cp "$TESTS/stubs/systemctl" "$WORK/stubs-real/systemctl"
      chmod +x "$WORK/stubs-real/flock" "$WORK/stubs-real/systemctl"
    fi
    PATH="$WORK/stubs-real:$ORIG_PATH"
    export PATH
  fi
}

symlinks_work() {
  local saved_path="$PATH"
  PATH="$ORIG_PATH"
  ln -s x "$WORK/lt.probe"
  local rc=$?
  rm -f "$WORK/lt.probe"
  PATH="$saved_path"
  return "$rc"
}

# ---- case lifecycle ---------------------------------------------------------

new_case() {
  local name="$1"
  CASE="$WORK/$name"
  ROOT="$CASE/root"
  FIX="$CASE/fix"
  STATE="$CASE/state"
  mkdir -p "$ROOT/data" "$FIX" "$STATE"

  # stop previous server
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
  SERVER_PID=""

  # pick free port
  local port_py
  port_py="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1]); s.close()')"
  PORT="$port_py"

  # start fixture server
  "$PY" "$(mp "$TESTS/fixture_server.py")" \
    --port "$PORT" \
    --fixtures "$(mp "$FIX")" \
    --root "$(mp "$ROOT")" \
    --state "$(mp "$STATE")" >/dev/null 2>&1 &
  SERVER_PID=$!

  # poll up to 5 s
  local i=0
  while (( i < 50 )); do
    if curl -s -o /dev/null "http://127.0.0.1:${PORT}/x"; then
      break
    fi
    sleep 0.1
    i=$(( i + 1 ))
  done

  # exports
  export PEARLIE_ROOT="$(mp "$ROOT")"
  export PEARLIE_UPDATE_API_BASE="http://127.0.0.1:${PORT}/gh"
  export PEARLIE_UPDATE_DOWNLOAD_BASE="http://127.0.0.1:${PORT}/dl"
  export PEARLIE_JSON_PY="$PY"
  export PEARLIE_VENV_PY="$(mp "$WORK/bin/venvpy")"
  export PEARLIE_NPM="$(mp "$WORK/bin/npm")"
  export PEARLIE_LOCK="$(mp "$CASE/lock")"
  export PEARLIE_BIN="$(mp "$CASE/nobin")"
  export PEARLIE_SKIP_SWAP=1
  export PEARLIE_HEALTH_TIMEOUT=3
  export STUB_LOG="$CASE/stub.log"
  touch "$STUB_LOG"
  export STUB_STATE="$STATE"
  export STUB_ORIG_PATH="$ORIG_PATH"

  printf 'port=%s\n' "$PORT" > "$ROOT/update.conf"

  if [[ "${MODE_REAL:-0}" == "1" ]]; then
    use_stubs real
  else
    use_stubs full
  fi
}

# ---- fixtures ----------------------------------------------------------------

seed_install() {
  local version="$1"
  local commit="${2:-}"

  local dir="$ROOT/releases/seed/app"
  mkdir -p "$dir"

  if [[ -n "$commit" ]]; then
    printf '{"version":"%s","channel":"main","commit":"%s","built_at":"x"}\n' \
      "$version" "$commit" > "$dir/VERSION.json"
  else
    printf '{"version":"%s","channel":"main","commit":null,"built_at":"x"}\n' \
      "$version" > "$dir/VERSION.json"
  fi

  ln -sfn "$(mp "$ROOT/releases/seed")" "$ROOT/current"
  : > "$STUB_LOG"

  printf 'SECRET=hunter2\n' > "$ROOT/.env"
  printf 'db-old\n' > "$ROOT/data/pearlie.db"
  printf 'x\n' > "$ROOT/data/extra.bin"
}

state_hash() {
  (cd "$ROOT" && { printf '%s\n' .env; find data -type f | sort; } | xargs sha256sum) | sha256sum
}

add_main_release() {
  local version="$1" sha="$2"
  shift 2
  local tag="v${version}"

  mkdir -p "$FIX/gh/releases" "$FIX/gh/commits"
  printf '{"tag_name":"%s"}\n' "$tag" > "$FIX/gh/releases/latest"
  printf '{"sha":"%s"}\n' "$sha" > "$FIX/gh/commits/${tag}"

  local dest="$FIX/dl/tar.gz/refs/tags/${tag}"
  mkdir -p "$(dirname "$dest")"

  PYTHONPATH="$(mp "$TESTS")" "$PY" -c '
import sys
from pathlib import Path
from mkfixture import make_tarball
dest = Path(sys.argv[1])
version = sys.argv[2]
repo = Path(sys.argv[3])
extra = []
for a in sys.argv[4:]:
    parts = a.split(":", 2)
    if len(parts) == 3:
        extra.append((parts[0], parts[1], parts[2]))
make_tarball(dest, "pearlie-" + version, version, repo, extra)
' "$dest" "$version" "$(mp "$REPO")" "$@"
}

add_dev_release() {
  local sha="$1"

  mkdir -p "$FIX/gh/commits"
  printf '{"sha":"%s"}\n' "$sha" > "$FIX/gh/commits/dev"

  local dest="$FIX/dl/tar.gz/${sha}"
  mkdir -p "$(dirname "$dest")"

  PYTHONPATH="$(mp "$TESTS")" "$PY" -c '
import sys
from pathlib import Path
from mkfixture import make_tarball
dest = Path(sys.argv[1])
repo = Path(sys.argv[2])
make_tarball(dest, "pearlie-0.1.0", "0.1.0", repo)
' "$dest" "$(mp "$REPO")"
}

# ---- test helpers ------------------------------------------------------------

run_update() {
  bash "$REPO/deploy/pearlie-update.sh" "$@" > "$CASE/out" 2>&1
  RC=$?
}

status_get() {
  "$PY" -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    print(d.get(sys.argv[2], ""))
except FileNotFoundError:
    pass
' "$ROOT/update-status.json" "$1"
}

stub_calls() {
  local n
  n="$(grep -c -- "$1" "$STUB_LOG" 2>/dev/null)" || n=0
  printf '%s\n' "$n"
}

no_bad_args() {
  local name="$1"
  if grep -q -- '^BAD' "$STUB_LOG" 2>/dev/null; then
    bad "$name" "bad args in stub log"
  else
    ok "$name"
  fi
}

release_dirs() {
  local n=0
  local entry
  for entry in "$ROOT/releases"/*; do
    [[ -e "$entry" ]] || continue
    [[ "$(basename "$entry")" == "seed" ]] && continue
    n=$(( n + 1 ))
  done
  printf '%s\n' "$n"
}

current_target() {
  readlink "$ROOT/current"
}

SHA_A=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
SHA_B=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

expect() {
  local name="$1" actual="$2" expected="$3"
  if [ "$actual" = "$expected" ]; then
    ok "$name"
  else
    bad "$name" "got $actual want $expected"
  fi
}

case_nothing_newer() {
  new_case nothing_newer
  seed_install 1.0.0
  add_main_release 1.0.0 "$SHA_A"
  run_update
  expect "nothing_newer: RC" "$RC" 0
  expect "nothing_newer: state" "$(status_get state)" current
  expect "nothing_newer: release_dirs" "$(release_dirs)" 0
  expect "nothing_newer: stub_calls systemctl" "$(stub_calls systemctl)" 0
  no_bad_args "nothing_newer: stub args"
}

case_check() {
  new_case check
  seed_install 1.0.0
  add_main_release 1.1.0 "$SHA_B"
  run_update --check
  expect "check: RC" "$RC" 10
  if [ ! -f "$ROOT/update-status.json" ]; then
    ok "check: no status file"
  else
    bad "check: no status file" "file present"
  fi
  expect "check: release_dirs" "$(release_dirs)" 0
  no_bad_args "check: stub args"
}

case_success() {
  new_case success
  seed_install 1.0.0
  local H
  H=$(state_hash)
  add_main_release 1.1.0 "$SHA_B"
  run_update
  expect "success: RC" "$RC" 0
  expect "success: state" "$(status_get state)" done
  expect "success: step" "$(status_get step)" health
  expect "success: release_dirs" "$(release_dirs)" 1
  local T
  T=$(current_target)
  case "$T" in
    *bbbbbbb*) ok "success: target contains bbbbbb" ;;
    *) bad "success: target contains bbbbbb" "got $T" ;;
  esac
  if [ -f "$T/app/VERSION.json" ]; then
    ok "success: VERSION.json exists"
  else
    bad "success: VERSION.json exists" "missing"
  fi
  if grep -q '1\.1\.0' "$T/app/VERSION.json"; then
    ok "success: VERSION.json has 1.1.0"
  else
    bad "success: VERSION.json has 1.1.0" "missing"
  fi
  if [ -f "$T/app/frontend/dist/index.html" ]; then
    ok "success: frontend dist"
  else
    bad "success: frontend dist" "missing"
  fi
  expect "success: pip require-hashes" "$(grep -c 'pip install --require-hashes -r' "$STUB_LOG")" 1
  expect "success: pip no-deps" "$(grep -c 'pip install --no-deps' "$STUB_LOG")" 1
  if grep -q 'npm ci' "$STUB_LOG"; then
    ok "success: npm ci"
  else
    bad "success: npm ci" "missing"
  fi
  if grep -q 'npm run build' "$STUB_LOG"; then
    ok "success: npm run build"
  else
    bad "success: npm run build" "missing"
  fi
  local stop_ln start_ln
  stop_ln=$(grep -n 'systemctl stop pearlie' "$STUB_LOG" | head -1 | cut -d: -f1)
  start_ln=$(grep -n 'systemctl start pearlie' "$STUB_LOG" | head -1 | cut -d: -f1)
  if [ -n "$stop_ln" ] && [ -n "$start_ln" ] && [ "$stop_ln" -lt "$start_ln" ]; then
    ok "success: systemctl order"
  else
    bad "success: systemctl order" "stop=$stop_ln start=$start_ln"
  fi
  expect "success: state_hash" "$(state_hash)" "$H"
  if [ -d "$ROOT/backups" ]; then
    ok "success: backup dir exists"
  else
    bad "success: backup dir exists" "missing"
  fi
  local bd
  bd=$(ls -1d "$ROOT"/backups/*/ 2>/dev/null | tail -1)
  if [ -f "${bd}pearlie.db" ]; then
    ok "success: backup pearlie.db"
  else
    bad "success: backup pearlie.db" "missing"
  fi
  if [ -f "${bd}.env" ]; then
    ok "success: backup .env"
  else
    bad "success: backup .env" "missing"
  fi
  local R
  if [ -L "$ROOT/current" ]; then
    R="$ROOT/current/app"
  else
    R="$T/app"
  fi
  local ver_out
  ver_out=$(PYTHONPATH="$(mp "$REPO/backend")" "$PY" -c 'import sys;from pathlib import Path;from app.update.version import current_version as c;i=c(roots=(Path(sys.argv[1]),));print(i.version)' "$(mp "$R")")
  expect "success: version proof" "$ver_out" "1.1.0"
  no_bad_args "success: stub args"
}

case_build_fail() {
  new_case bf_pip
  seed_install 1.0.0
  add_main_release 1.1.0 "$SHA_B"
  touch "$STATE/pip_fail"
  local H
  H=$(state_hash)
  run_update
  expect "bf_pip: RC" "$RC" 1
  expect "bf_pip: state" "$(status_get state)" failed
  expect "bf_pip: step" "$(status_get step)" build
  expect "bf_pip: release_dirs" "$(release_dirs)" 0
  case "$(current_target)" in
    *releases/seed*) ok "bf_pip: target is seed" ;;
    *) bad "bf_pip: target is seed" "not seed" ;;
  esac
  expect "bf_pip: stub_calls systemctl" "$(stub_calls systemctl)" 0
  expect "bf_pip: state_hash" "$(state_hash)" "$H"
  no_bad_args "bf_pip: stub args"

  new_case bf_npm
  seed_install 1.0.0
  add_main_release 1.1.0 "$SHA_B"
  touch "$STATE/npm_fail"
  H=$(state_hash)
  run_update
  expect "bf_npm: RC" "$RC" 1
  expect "bf_npm: state" "$(status_get state)" failed
  expect "bf_npm: step" "$(status_get step)" build
  expect "bf_npm: release_dirs" "$(release_dirs)" 0
  case "$(current_target)" in
    *releases/seed*) ok "bf_npm: target is seed" ;;
    *) bad "bf_npm: target is seed" "not seed" ;;
  esac
  expect "bf_npm: stub_calls systemctl" "$(stub_calls systemctl)" 0
  expect "bf_npm: state_hash" "$(state_hash)" "$H"
  no_bad_args "bf_npm: stub args"
}

case_bad_health() {
  new_case bad_health
  seed_install 1.0.0
  local H
  H=$(state_hash)
  add_main_release 1.1.0 "$SHA_B"
  printf '1.1.0\n' > "$STATE/bad_versions"
  touch "$STATE/corrupt_db_on_start"
  run_update
  expect "bad_health: RC" "$RC" 1
  expect "bad_health: state" "$(status_get state)" rolled_back
  case "$(current_target)" in
    *releases/seed*) ok "bad_health: target is seed" ;;
    *) bad "bad_health: target is seed" "not seed" ;;
  esac
  expect "bad_health: state_hash" "$(state_hash)" "$H"
  expect "bad_health: db content" "$(cat "$ROOT/data/pearlie.db")" "db-old"
  expect "bad_health: stub_calls systemctl stop" "$(stub_calls 'systemctl stop')" 2
  expect "bad_health: stub_calls systemctl start" "$(stub_calls 'systemctl start')" 2
  no_bad_args "bad_health: stub args"
}

case_lock() {
  new_case lock
  seed_install 1.0.0
  add_main_release 1.1.0 "$SHA_B"
  mkdir "$PEARLIE_LOCK.stub.d"
  printf 'SENTINEL' > "$ROOT/update-status.json"
  run_update
  expect "lock: RC" "$RC" 11
  expect "lock: status content" "$(cat "$ROOT/update-status.json")" "SENTINEL"
  expect "lock: release_dirs" "$(release_dirs)" 0
  expect "lock: stub_calls systemctl" "$(stub_calls systemctl)" 0
  no_bad_args "lock: stub args"
}

case_malicious() {
  local line name extra H
  while IFS='|' read -r name extra; do
    new_case "mal_$name"
    seed_install 1.0.0
    H=$(state_hash)
    add_main_release 1.1.0 "$SHA_B" "$extra"
    run_update
    expect "malicious $name: RC" "$RC" 1
    expect "malicious $name: state" "$(status_get state)" failed
    expect "malicious $name: release_dirs" "$(release_dirs)" 0
    case "$(current_target)" in
      *releases/seed*) ok "malicious $name: target is seed" ;;
      *) bad "malicious $name: target is seed" "not seed" ;;
    esac
    if [ ! -e "$CASE/evil" ]; then
      ok "malicious $name: no evil file"
    else
      bad "malicious $name: no evil file" "exists"
    fi
    expect "malicious $name: stub_calls systemctl" "$(stub_calls systemctl)" 0
    expect "malicious $name: state_hash" "$(state_hash)" "$H"
    no_bad_args "malicious $name: stub args"
  done <<< "abs|file:/abs-evil:x
dotdot|file:../evil:x
symlink|symlink:pearlie-1.1.0/link:/etc/passwd
twotop|file:other/x:x
incomplete|omit:frontend/package.json:"
}

case_aborted() {
  new_case aborted
  seed_install 1.0.0
  add_main_release 1.1.0 "$SHA_B"
  touch "$STATE/kill_on_stop"
  run_update
  if [ "$RC" -ne 0 ]; then
    ok "aborted: RC not 0"
  else
    bad "aborted: RC not 0" "RC=0"
  fi
  expect "aborted: state" "$(status_get state)" failed
  local err
  err=$(status_get error)
  case "$err" in
    *aborted*) ok "aborted: error contains aborted" ;;
    *) bad "aborted: error contains aborted" "got: $err" ;;
  esac
  if [ ! -d "$ROOT/staging" ]; then
    ok "aborted: no staging"
  else
    bad "aborted: no staging" "exists"
  fi
  no_bad_args "aborted: stub args"
}

case_dev() {
  new_case dev
  seed_install 1.0.0-dev+aaaaaaa "$SHA_A"
  add_dev_release "$SHA_B"
  run_update --channel dev
  expect "dev: RC" "$RC" 0
  expect "dev: state" "$(status_get state)" done
  local T
  T=$(current_target)
  if grep -q '0\.1\.0-dev+bbbbbbb' "$T/app/VERSION.json"; then
    ok "dev: version in VERSION.json"
  else
    bad "dev: version in VERSION.json" "missing"
  fi
  if grep -q '"channel":"dev"' "$T/app/VERSION.json"; then
    ok "dev: channel dev"
  else
    bad "dev: channel dev" "missing"
  fi
  if grep -q "$SHA_B" "$T/app/VERSION.json"; then
    ok "dev: SHA_B in VERSION.json"
  else
    bad "dev: SHA_B in VERSION.json" "missing"
  fi
  no_bad_args "dev: stub args"

  new_case dev_same
  seed_install 1.0.0-dev+aaaaaaa "$SHA_A"
  add_dev_release "$SHA_A"
  run_update --channel dev
  expect "dev_same: RC" "$RC" 0
  expect "dev_same: state" "$(status_get state)" current
  no_bad_args "dev_same: stub args"
}

case_dry_run() {
  new_case dry_run
  seed_install 1.0.0
  add_main_release 1.1.0 "$SHA_B"
  run_update --dry-run
  expect "dry_run: RC" "$RC" 0
  expect "dry_run: state" "$(status_get state)" current
  expect "dry_run: step" "$(status_get step)" dry-run
  expect "dry_run: release_dirs" "$(release_dirs)" 0
  case "$(current_target)" in
    *releases/seed*) ok "dry_run: target is seed" ;;
    *) bad "dry_run: target is seed" "not seed" ;;
  esac
  expect "dry_run: stub_calls systemctl" "$(stub_calls systemctl)" 0
  no_bad_args "dry_run: stub args"
}

CASES=(case_nothing_newer case_check case_success case_build_fail case_bad_health case_lock case_malicious case_aborted case_dev case_dry_run)

for c in "${CASES[@]}"; do
  "$c"
done

if symlinks_work; then
  echo "== real ln/mv/readlink run =="
  MODE_REAL=1
  export MODE_REAL
  case_success
  case_bad_health
else
  echo "SKIP real-ln run: symlinks unavailable here (stubs only)"
fi
finish
