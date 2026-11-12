#!/usr/bin/env bash
set -euo pipefail

# --- defaults ---
ROOT="${PEARLIE_ROOT:-/opt/pearlie}"
API="${PEARLIE_UPDATE_API_BASE:-https://api.github.com/repos/bakumetsu/pearlie}"
DL="${PEARLIE_UPDATE_DOWNLOAD_BASE:-https://codeload.github.com/bakumetsu/pearlie}"
JSON_PY="${PEARLIE_JSON_PY:-python3}"
VENV_PY="${PEARLIE_VENV_PY:-python3}"
NPM="${PEARLIE_NPM:-npm}"
SYSTEMCTL="${PEARLIE_SYSTEMCTL:-systemctl}"
BIN="${PEARLIE_BIN:-/usr/local/bin/pearlie-update}"
LOCK="${PEARLIE_LOCK:-/run/pearlie-update.lock}"

CHANNEL=""
HOST="127.0.0.1"
PORT="8000"
CHECK_ONLY=0
INSTALL=0
FROM_UI=0
DRY_RUN=0
CONTINUE_ID=""
STEP="start"
STARTED_AT=""
FROM_V=""
TO_V=""
LOCK_HELD=0
INST_VERSION=""
INST_COMMIT=""
STATUS_ON=0

# --- helpers ---
now_iso() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

log() {
  local msg="$1"
  mkdir -p "$ROOT"
  local ts
  ts="$(now_iso)"
  printf '%s %s\n' "$ts" "$msg" >> "$ROOT/update.log"
  printf '%s %s\n' "$ts" "$msg" >&2
}

json_str() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/ }"
  s="${s//$'\t'/ }"
  printf '"%s"' "$s"
}

write_status() {
  local state="$1" step="$2" error="$3"
  STEP="$step"
  [[ "$STATUS_ON" == "1" ]] || return 0
  local tmp
  tmp="$(mktemp "$ROOT/update-status.json.XXXXXX")"
  local from_json to_json started_at_json error_json
  from_json="$(json_str "$FROM_V")"
  to_json="$(json_str "$TO_V")"
  if [[ -n "$STARTED_AT" ]]; then
    started_at_json="$(json_str "$STARTED_AT")"
  else
    started_at_json="null"
  fi
  if [[ -n "$error" ]]; then
    error_json="$(json_str "$error")"
  else
    error_json="null"
  fi
  printf '{"state":%s,"step":%s,"from":%s,"to":%s,"started_at":%s,"error":%s}\n' \
    "$(json_str "$state")" "$(json_str "$step")" \
    "$from_json" "$to_json" "$started_at_json" "$error_json" > "$tmp"
  mv -f "$tmp" "$ROOT/update-status.json"
}

die() {
  local msg="$1"
  log "$msg"
  write_status failed "$STEP" "$msg"
  FINAL_WRITTEN=1
  exit 1
}

# --- lock ---
acquire_lock() {
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$LOCK"
    if ! flock -n 9; then
      echo "update already running" >&2
      exit 11
    fi
    LOCK_HELD=1
  else
    if mkdir "$LOCK.d" 2>/dev/null; then
      printf '%s\n' "$$" > "$LOCK.d/pid"
      LOCK_HELD=1
    else
      local existing_pid
      existing_pid="$(cat "$LOCK.d/pid" 2>/dev/null)" || existing_pid=""
      if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
        if [[ "$existing_pid" != "$$" ]]; then
          echo "update already running (pid $existing_pid)" >&2
          exit 11
        fi
      fi
      printf '%s\n' "$$" > "$LOCK.d/pid"
      LOCK_HELD=1
    fi
  fi
}

release_lock() {
  if [[ -d "$LOCK.d" ]]; then
    local pid
    pid="$(cat "$LOCK.d/pid" 2>/dev/null)" || pid=""
    if [[ "$pid" == "$$" ]]; then
      rm -rf "$LOCK.d"
    fi
  fi
  LOCK_HELD=0
}

# --- exit trap ---
on_exit() {
  local rc=$?
  if [[ "$STATUS_ON" == "1" && -z "${FINAL_WRITTEN:-}" ]]; then
    write_status failed "$STEP" "aborted at step $STEP"
  fi
  if [[ "$LOCK_HELD" == "1" ]]; then
    # only the lock holder may touch staging; a run that lost the lock must not
    if [[ -f "$ROOT/staging/swap" ]]; then
      swapoff "$ROOT/staging/swap" 2>/dev/null || true
    fi
    rm -rf "$ROOT/staging"
    release_lock
  fi
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 1' INT TERM

# --- config ---
read_conf() {
  local conf_file="$ROOT/update.conf"
  [[ -f "$conf_file" ]] || { CHANNEL="${CHANNEL:-main}"; return 0; }
  local CONF_CHANNEL=""
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" == \#* ]] && continue
    [[ "$line" == *=* ]] || { echo "update.conf: bad line: $line" >&2; exit 1; }
    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      channel)
        if [[ "$value" == "main" || "$value" == "dev" ]]; then
          CONF_CHANNEL="$value"
        else
          echo "update.conf: bad line: $line" >&2
          exit 1
        fi
        ;;
      check)
        if [[ "$value" == "on" || "$value" == "off" ]]; then
          :
        else
          echo "update.conf: bad line: $line" >&2
          exit 1
        fi
        ;;
      port)
        if [[ "$value" =~ ^[0-9]+$ ]] && (( 10#$value >= 1 && 10#$value <= 65535 )); then
          PORT="$value"
        else
          echo "update.conf: bad line: $line" >&2
          exit 1
        fi
        ;;
      host)
        if [[ "$value" =~ ^[0-9A-Fa-f:.]+$ ]]; then
          HOST="$value"
        else
          echo "update.conf: bad line: $line" >&2
          exit 1
        fi
        ;;
      *)
        echo "update.conf: bad line: $line" >&2
        exit 1
        ;;
    esac
  done < "$conf_file"
  CHANNEL="${CHANNEL:-${CONF_CHANNEL:-main}}"
}

read_installed() {
  local vfile="$ROOT/current/app/VERSION.json"
  [[ -f "$vfile" ]] || return 0
  local out
  out="$(
    "$JSON_PY" -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    print(d.get("version", "") or "")
    c = d.get("commit", "") or ""
    print(c)
except Exception:
    print("")
    print("")
' "$vfile" 2>/dev/null
  )" || out=""
  INST_VERSION="${out%%$'\n'*}"
  INST_COMMIT="${out#*$'\n'}"
  INST_COMMIT="${INST_COMMIT%$'\n'}"
}
http_get() {
  curl -fsSL --max-time 30 -H 'Accept: application/vnd.github+json' "$1"
}

json_field() {
  printf '%s' "$1" | "$JSON_PY" -c '
import sys, json
try:
  data = json.load(sys.stdin)
  v = data.get(sys.argv[1], "")
  if isinstance(v, str):
    print(v)
except Exception:
  pass
' "$2"
}

highest_tag() {
  printf '%s' "$1" | "$JSON_PY" -c '
import sys, json, re
try:
  data = json.load(sys.stdin)
  if not isinstance(data, list):
    sys.exit(0)
  pat = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
  best = ""
  best_key = (-1, -1, -1)
  for item in data:
    name = item.get("name", "")
    m = pat.match(name)
    if m:
      key = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
      if key > best_key:
        best = name
        best_key = key
  if best:
    print(best)
except Exception:
  pass
'
}

resolve_target() {
  STEP="resolve"
  if [ "$CHANNEL" = "dev" ]; then
    local body sha
    if ! body=$(http_get "$API/commits/dev"); then
      die "cannot reach update server"
    fi
    sha=$(json_field "$body" "sha")
    if ! printf '%s' "$sha" | grep -qE '^[0-9a-f]{40}$'; then
      die "bad dev head"
    fi
    TARGET_COMMIT="$sha"
    TARGET_URL="$DL/tar.gz/$sha"
    TARGET_VERSION="dev:${sha:0:7}"
  else
    local body tag sha commit_body
    body=$(http_get "$API/releases/latest") || true
    tag=$(json_field "$body" "tag_name")
    if ! printf '%s' "$tag" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
      if ! body=$(http_get "$API/tags"); then
        die "cannot reach update server"
      fi
      tag=$(highest_tag "$body")
    fi
    if ! printf '%s' "$tag" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
      die "no release found"
    fi
    TARGET_VERSION="${tag#v}"
    TARGET_URL="$DL/tar.gz/refs/tags/$tag"
    commit_body=$(http_get "$API/commits/$tag" 2>/dev/null) || true
    sha=$(json_field "$commit_body" "sha")
    if printf '%s' "$sha" | grep -qE '^[0-9a-f]{40}$'; then
      TARGET_COMMIT="$sha"
    else
      TARGET_COMMIT=""
    fi
  fi
}

is_newer() {
  if [ "$CHANNEL" = "dev" ]; then
    if [ "$TARGET_COMMIT" != "$INST_COMMIT" ]; then
      return 0
    fi
    return 1
  fi
  if [ -z "$INST_VERSION" ]; then
    return 0
  fi
  local inst_ver="${INST_VERSION%%[-+]*}"
  local t_major t_minor t_patch i_major i_minor i_patch
  IFS='.' read -r t_major t_minor t_patch <<< "$TARGET_VERSION"
  IFS='.' read -r i_major i_minor i_patch <<< "$inst_ver"
  if [ "$t_major" -gt "$i_major" ] || \
    { [ "$t_major" -eq "$i_major" ] && [ "$t_minor" -gt "$i_minor" ]; } || \
    { [ "$t_major" -eq "$i_major" ] && [ "$t_minor" -eq "$i_minor" ] && [ "$t_patch" -gt "$i_patch" ]; }
  then
    return 0
  fi
  return 1
}

check_only() {
  read_installed
  resolve_target
  printf 'installed: %s\n' "${INST_VERSION:-none}"
  printf 'latest: %s\n' "$TARGET_VERSION"
  if is_newer; then
    exit 10
  fi
  exit 0
}

download_and_extract() {
  STEP="download"
  rm -rf "$ROOT/staging"
  mkdir -p "$ROOT/staging"

  local tarball="$ROOT/staging/src.tar.gz"

  if ! curl -fsSL --max-filesize 104857600 --max-time 600 -o "$tarball" "$TARGET_URL"; then
    die "download failed"
  fi

  local file_size
  file_size=$(wc -c < "$tarball")
  file_size=$((file_size))
  if [ "$file_size" -gt 104857600 ]; then
    die "download too large"
  fi

  local list
  if ! list=$(tar -tzf "$tarball"); then
    die "unreadable archive"
  fi

  if [ -z "$list" ]; then
    die "unsafe archive: empty archive"
  fi

  local -a first_components=()
  local entry
  while IFS= read -r entry; do
    [ -z "$entry" ] && continue
    case "$entry" in
      /*) die "unsafe archive: absolute path" ;;
    esac
    if printf '%s' "$entry" | grep -qE '(^|/)\.\.(/|$)'; then
      die "unsafe archive: path traversal"
    fi
    first_components+=("${entry%%/*}")
  done <<< "$list"

  local distinct
  distinct=$(printf '%s\n' "${first_components[@]}" | sort -u | wc -l)
  distinct=$((distinct))
  if [ "$distinct" -gt 1 ]; then
    die "unsafe archive: multiple top-level directories"
  fi

  local verbose_line
  while IFS= read -r verbose_line; do
    case "$verbose_line" in
      l*|h*) die "unsafe archive: symlink or hardlink" ;;
    esac
  done < <(tar -tvzf "$tarball")

  local short
  if [ -n "$TARGET_COMMIT" ]; then
    short="${TARGET_COMMIT:0:7}"
  else
    short="${TARGET_VERSION#dev:}"
    short="${short:0:7}"
  fi
  RELEASE_ID="$(date -u +%Y%m%d%H%M%S)-${short}"
  REL="$ROOT/releases/$RELEASE_ID"
  mkdir -p "$REL/app"

  if ! tar -xzf "$tarball" --strip-components=1 --no-same-owner -C "$REL/app"; then
    rm -rf "$REL"
    die "extract failed"
  fi

  local required_file
  for required_file in \
    "backend/pyproject.toml" \
    "deploy/pearlie-update.sh" \
    "deploy/requirements.lock" \
    "frontend/package.json"
  do
    if [ ! -f "$REL/app/$required_file" ]; then
      rm -rf "$REL"
      die "incomplete release"
    fi
  done

  if [ "$CHANNEL" = "dev" ]; then
    local base
    base=$(grep -m1 '^version[[:space:]]*=' "$REL/app/backend/pyproject.toml" | sed 's/.*"\(.*\)".*/\1/')
    TARGET_VERSION="${base}-dev+${TARGET_COMMIT:0:7}"
  fi

  write_version_json
}

write_version_json() {
  local commit_json
  if [ -n "$TARGET_COMMIT" ]; then
    commit_json="\"$TARGET_COMMIT\""
  else
    commit_json="null"
  fi
  printf '{"version":"%s","channel":"%s","commit":%s,"built_at":"%s"}\n' \
    "$TARGET_VERSION" "$CHANNEL" "$commit_json" "$(now_iso)" > "$REL/app/VERSION.json"
}
self_refresh() {
  STEP="self-refresh"
  [[ "$DRY_RUN" == "1" ]] && return
  [[ -n "$CONTINUE_ID" ]] && return
  [[ -f "$BIN" ]] || return
  if ! cmp -s "$REL/app/deploy/pearlie-update.sh" "$BIN"; then
    log "refreshing update script"
    install -m 755 "$REL/app/deploy/pearlie-update.sh" "$BIN"
    # the lock (fd 9 or our pid) is inherited across exec; tell the new process so
    PEARLIE_LOCK_INHERITED=1 exec "$BIN" ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"} --continue "$RELEASE_ID"
  fi
}

load_continue() {
  RELEASE_ID="$CONTINUE_ID"
  REL="$ROOT/releases/$RELEASE_ID"
  [[ -f "$REL/app/VERSION.json" ]] || die "release $RELEASE_ID missing"
  TARGET_VERSION=$("$JSON_PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$REL/app/VERSION.json")
  TARGET_COMMIT=$("$JSON_PY" -c 'import json,sys;c=json.load(open(sys.argv[1])).get("commit");print(c or "")' "$REL/app/VERSION.json")
  if [[ -f "$ROOT/update-status.json" ]]; then
    STARTED_AT=$("$JSON_PY" -c 'import json,sys;print(json.load(open(sys.argv[1])).get("started_at",""))' "$ROOT/update-status.json")
  else
    STARTED_AT=""
  fi
}

swap_on() {
  [[ -n "${PEARLIE_SKIP_SWAP:-}" ]] && return
  [[ -f /proc/meminfo ]] || return
  local memtotal
  memtotal=$(awk '/MemTotal/{print $2}' /proc/meminfo)
  [[ "$memtotal" -lt 1572864 ]] || return
  mkdir -p "$ROOT/staging"
  log "adding 1G swap for build"
  if ! fallocate -l 1G "$ROOT/staging/swap"; then
    log "swap: fallocate failed, skipping"
    return
  fi
  if ! chmod 600 "$ROOT/staging/swap"; then
    log "swap: chmod failed, skipping"
    return
  fi
  if ! mkswap "$ROOT/staging/swap"; then
    log "swap: mkswap failed, skipping"
    return
  fi
  if ! swapon "$ROOT/staging/swap"; then
    log "swap: swapon failed, skipping"
    return
  fi
}

build_release() {
  STEP="build"
  write_status "running" "build" ""

  run_build_step() {
    local name="$1"
    shift
    log "build step: $name"
    if ! "$@" >>"$ROOT/update.log" 2>&1; then
      rm -rf "$REL"
      die "$name failed, see update.log"
    fi
  }

  swap_on

  run_build_step venv "$VENV_PY" -m venv "$REL/venv"
  run_build_step pip-lock "$REL/venv/bin/pip" install --require-hashes -r "$REL/app/deploy/requirements.lock"
  run_build_step pip-backend "$REL/venv/bin/pip" install --no-deps "$REL/app/backend"
  run_build_step npm-ci bash -c 'cd "$1/frontend" && NODE_OPTIONS=--max-old-space-size=768 "$2" ci' _ "$REL/app" "$NPM"
  run_build_step npm-build bash -c 'cd "$1/frontend" && NODE_OPTIONS=--max-old-space-size=768 "$2" run build' _ "$REL/app" "$NPM"

  [[ -f "$REL/app/frontend/dist/index.html" ]] || {
    rm -rf "$REL"
    die "frontend build produced no index.html"
  }
}

parse_args() {
  local usage="usage: pearlie-update [--check|--install|--from-ui|--dry-run|--channel main|dev]"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --check)
        CHECK_ONLY=1
        shift
        ;;
      --install)
        INSTALL=1
        shift
        ;;
      --from-ui)
        FROM_UI=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --channel)
        if [[ $# -lt 2 ]]; then
          echo "$usage" >&2
          exit 2
        fi
        case "$2" in
          main|dev)
            CHANNEL="$2"
            shift 2
            ;;
          *)
            echo "$usage" >&2
            exit 2
            ;;
        esac
        ;;
      --continue)
        if [[ $# -lt 2 ]]; then
          echo "$usage" >&2
          exit 2
        fi
        if [[ "$2" =~ ^[0-9A-Za-z._-]+$ ]]; then
          CONTINUE_ID="$2"
          shift 2
        else
          echo "$usage" >&2
          exit 2
        fi
        ;;
      *)
        echo "$usage" >&2
        exit 2
        ;;
    esac
  done
}

health_ok() {
  local expected="$1"
  local h="$HOST"
  local url
  if [[ "$h" == *:* ]]; then
    url="http://[${h}]:${PORT}/api/health"
  else
    url="http://${h}:${PORT}/api/health"
  fi
  local json
  if ! json=$(curl -fsS --max-time 5 "$url"); then
    return 1
  fi
  local version
  if ! version=$(printf '%s\n' "$json" | "$JSON_PY" -c "import sys,json; print(json.load(sys.stdin)['version'])"); then
    return 1
  fi
  [[ "$version" == "$expected" ]]
}

wait_healthy() {
  local expected="$1"
  local timeout="${PEARLIE_HEALTH_TIMEOUT:-60}"
  local elapsed=0
  while (( elapsed < timeout )); do
    if health_ok "$expected"; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  return 1
}

set_current() {
  ln -sfn "$1" "$ROOT/current.new" && mv -Tf "$ROOT/current.new" "$ROOT/current"
}

backup_state() {
  local bk="$ROOT/backups/$RELEASE_ID"
  (umask 077; mkdir -p "$bk")
  if [[ -f "$ROOT/data/pearlie.db" ]]; then
    cp "$ROOT/data/pearlie.db" "$bk/pearlie.db"
  fi
  if [[ -f "$ROOT/data/pearlie.db-wal" ]]; then
    cp "$ROOT/data/pearlie.db-wal" "$bk/pearlie.db-wal"
  fi
  if [[ -f "$ROOT/data/pearlie.db-shm" ]]; then
    cp "$ROOT/data/pearlie.db-shm" "$bk/pearlie.db-shm"
  fi
  if [[ -f "$ROOT/.env" ]]; then
    cp "$ROOT/.env" "$bk/.env"
    chmod 600 "$bk/.env"
  fi
}

restore_db() {
  local bk="$ROOT/backups/$RELEASE_ID"
  rm -f "$ROOT/data/pearlie.db-wal" "$ROOT/data/pearlie.db-shm"
  if [[ -f "$bk/pearlie.db" ]]; then
    cp "$bk/pearlie.db" "$ROOT/data/pearlie.db"
    if [[ -f "$bk/pearlie.db-wal" ]]; then
      cp "$bk/pearlie.db-wal" "$ROOT/data/pearlie.db-wal"
    fi
    if [[ -f "$bk/pearlie.db-shm" ]]; then
      cp "$bk/pearlie.db-shm" "$ROOT/data/pearlie.db-shm"
    fi
  fi
}

prune_old() {
  local keep_a="${1:-}"
  local keep_b="${2:-}"
  local dir full kept=0
  for dir in "$ROOT/releases"/*/; do
    [[ -d "$dir" ]] || continue
    full="${dir%/}"
    if [[ -n "$keep_a" && "$full" == "$keep_a" ]]; then
      continue
    fi
    if [[ -n "$keep_b" && "$full" == "$keep_b" ]]; then
      continue
    fi
    rm -rf "$full"
  done
  if [[ -d "$ROOT/backups" ]]; then
    while IFS= read -r dir; do
      kept=$((kept + 1))
      if (( kept > 3 )); then
        rm -rf "$ROOT/backups/$dir"
      fi
    done < <(find "$ROOT/backups" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
  fi
}

rollback() {
  local prev="$1"
  local reason="$2"
  log "rolling back"
  STEP="rollback"
  "$SYSTEMCTL" stop pearlie 2>/dev/null || true
  restore_db
  if [[ -z "$prev" ]]; then
    write_status failed rollback "no previous release"
    FINAL_WRITTEN=1
    return 1
  fi
  set_current "$prev"
  "$SYSTEMCTL" start pearlie || true
  if wait_healthy "$FROM_V"; then
    write_status rolled_back rollback "$reason"
    FINAL_WRITTEN=1
    echo "update failed, rolled back: $reason" >&2
    return 1
  else
    write_status failed_rollback rollback "rollback also failed, manual repair needed"
    FINAL_WRITTEN=1
    echo "rollback also failed, manual repair needed" >&2
    return 1
  fi
}

switch_and_verify() {
  local prev
  STEP="stop"
  prev=$(readlink "$ROOT/current" 2>/dev/null || true)
  write_status running stop ""
  "$SYSTEMCTL" stop pearlie || log "warning: failed to stop pearlie, continuing"
  STEP="backup"
  backup_state
  STEP="switch"
  write_status running switch ""
  set_current "$REL"
  "$SYSTEMCTL" start pearlie || {
    rollback "$prev" "service did not start"
    return 1
  }
  STEP="health"
  write_status running health ""
  if wait_healthy "$TARGET_VERSION"; then
    prune_old "$REL" "$prev"
    write_status done health ""
    FINAL_WRITTEN=1
    echo "Pearlie updated to $TARGET_VERSION"
    return 0
  else
    rollback "$prev" "health check failed for $TARGET_VERSION"
    return 1
  fi
}

main() {
  ORIG_ARGS=("$@")
  parse_args "$@"
  mkdir -p "$ROOT"/{releases,staging,backups,data}
  read_conf
  if [[ "$CHECK_ONLY" == "1" ]]; then
    check_only
  fi
  if [[ -n "$CONTINUE_ID" ]]; then
    # --continue is only valid after a self-refresh exec that kept the lock
    if [[ "${PEARLIE_LOCK_INHERITED:-}" != "1" ]]; then
      echo "--continue is internal" >&2
      exit 2
    fi
    LOCK_HELD=1
  else
    acquire_lock
  fi
  STATUS_ON=1
  if [[ -z "$CONTINUE_ID" ]]; then
    STARTED_AT=$(now_iso)
  fi
  read_installed
  FROM_V="$INST_VERSION"
  if [[ -n "$CONTINUE_ID" ]]; then
    load_continue
    TO_V="$TARGET_VERSION"
  else
    write_status "running" "resolve" ""
    resolve_target
    TO_V="$TARGET_VERSION"
    if ! is_newer && [[ "$INSTALL" != "1" ]]; then
      write_status "current" "resolve" ""
      FINAL_WRITTEN=1
      echo "Pearlie is up to date (${INST_VERSION:-none})"
      exit 0
    fi
    write_status "running" "download" ""
    download_and_extract
    TO_V="$TARGET_VERSION"
    write_status "running" "download" ""
    self_refresh
  fi
  build_release
  if [[ "$DRY_RUN" == "1" ]]; then
    rm -rf "$REL"
    write_status "current" "dry-run" ""
    FINAL_WRITTEN=1
    echo "dry run ok"
    exit 0
  fi
  switch_and_verify
  exit $?
}

main "$@"
