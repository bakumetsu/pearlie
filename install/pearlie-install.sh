#!/usr/bin/env bash

# Copyright (c) Pearlie contributors | License: MIT | https://github.com/bakumetsu/pearlie
# Runs inside the new container; sourced helpers come from community-scripts (build.func passes FUNCTIONS_FILE_PATH).

# shellcheck source=/dev/null
source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing Dependencies"
# shellcheck disable=SC2086
$STD apt-get install -y python3 python3-venv ca-certificates curl rsync openssl
msg_ok "Installed Dependencies"

NODE_VERSION="22" setup_nodejs

msg_info "Setting up Pearlie"
mkdir -p /opt/pearlie/data /opt/pearlie/releases /opt/pearlie/backups

# BEGIN fetch_update_script (tested by deploy/tests/run.sh)
# Fetch pearlie-update from a release tag, not from the mutable main branch. Fails closed.
PEARLIE_API="${PEARLIE_UPDATE_API_BASE:-https://api.github.com/repos/bakumetsu/pearlie}"
PEARLIE_DL="${PEARLIE_UPDATE_DOWNLOAD_BASE:-https://codeload.github.com/bakumetsu/pearlie}"
PEARLIE_BIN_DEST="${PEARLIE_BIN:-/usr/local/bin/pearlie-update}"

pearlie_json_field() {
  printf '%s' "$1" | "${PEARLIE_JSON_PY:-python3}" -c '
import sys, json
try:
  v = json.load(sys.stdin).get(sys.argv[1], "")
  if isinstance(v, str):
    print(v)
except Exception:
  pass
' "$2"
}

fetch_update_script() {
  local ref="${PEARLIE_REF:-}" body sha tmp stamp
  if [[ -z $ref ]]; then
    if ! body=$(curl -fsSL --max-time 30 -H 'Accept: application/vnd.github+json' "$PEARLIE_API/releases/latest"); then
      msg_error "Cannot reach GitHub to find the latest release; nothing installed."
      return 1
    fi
    ref=$(pearlie_json_field "$body" tag_name)
  fi
  if [[ $ref != dev && ! $ref =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    msg_error "Bad release ref '$ref'; nothing installed."
    return 1
  fi
  if ! body=$(curl -fsSL --max-time 30 -H 'Accept: application/vnd.github+json' "$PEARLIE_API/commits/$ref"); then
    msg_error "Cannot resolve $ref to a commit; nothing installed."
    return 1
  fi
  sha=$(pearlie_json_field "$body" sha)
  if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then
    msg_error "Bad commit for $ref; nothing installed."
    return 1
  fi
  tmp=$(mktemp -d)
  if ! curl -fsSL --max-filesize 104857600 --max-time 600 -o "$tmp/src.tar.gz" "$PEARLIE_DL/tar.gz/$sha" || ! gzip -t "$tmp/src.tar.gz"; then
    rm -rf "$tmp"
    msg_error "Download failed or corrupt; nothing installed."
    return 1
  fi
  # same stamp check as deploy/pearlie-update.sh (download_and_extract)
  stamp=$(gzip -dc "$tmp/src.tar.gz" 2>/dev/null | head -c 4096 | grep -a -o 'comment=[0-9a-f]\{40\}' | head -n1) || true
  stamp="${stamp#comment=}"
  if [[ $stamp != "$sha" ]]; then
    rm -rf "$tmp"
    msg_error "Download does not match commit $sha; nothing installed."
    return 1
  fi
  if ! tar -xzf "$tmp/src.tar.gz" -O --wildcards '*/deploy/pearlie-update.sh' > "$tmp/pearlie-update" || [[ ! -s $tmp/pearlie-update ]]; then
    rm -rf "$tmp"
    msg_error "Update script missing in the release; nothing installed."
    return 1
  fi
  install -m 755 "$tmp/pearlie-update" "$PEARLIE_BIN_DEST"
  rm -rf "$tmp"
  PEARLIE_RESOLVED_REF="$ref"
}
# END fetch_update_script

fetch_update_script || exit 1

host_ip=$(hostname -I | awk '{for (j = 1; j <= NF; j++) if ($j ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) { print $j; exit }}')
if [[ -z $host_ip ]]; then
  msg_info "No container IPv4 found now; Pearlie stays on 127.0.0.1 until the container gets one; tailscale serve or a reverse proxy in front."
fi
mkdir -p /mnt/media/stash/Temp /mnt/media/stash/Other

if [[ ! -f /opt/pearlie/.env ]]; then
  (
    umask 077
    {
      echo "# written by pearlie-install; edit and run: systemctl restart pearlie"
      echo "PEARLIE_MODE=real"
      echo "PEARLIE_DB_PATH=/opt/pearlie/data/pearlie.db"
      echo "PEARLIE_STATIC_DIR=/opt/pearlie/current/app/frontend/dist"
      echo "PEARLIE_HOST=auto"
      echo "PEARLIE_PORT=8000"
      echo "PEARLIE_TRUSTED_NETWORK=1"
      echo "PEARLIE_STASH_TEMP_DIR=/mnt/media/stash/Temp"
      echo "PEARLIE_STASH_DEFAULT_DIR=/mnt/media/stash/Other"
    } > /opt/pearlie/.env
  )
  chmod 600 /opt/pearlie/.env
fi

# keep the user's settings on a re-run, like .env
if [[ ! -f /opt/pearlie/update.conf ]]; then
  cat <<CONF > /opt/pearlie/update.conf
channel=$([[ ${PEARLIE_RESOLVED_REF:-} == dev ]] && echo dev || echo main)
check=on
host=auto
port=8000
CONF
fi

cat <<'UNIT' > /etc/systemd/system/pearlie.service
[Unit]
Description=Pearlie media hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/pearlie
ExecStart=/opt/pearlie/current/venv/bin/python -m app.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload

msg_ok "Set up Pearlie"
msg_info "Building Pearlie (first release)"
# shellcheck disable=SC2086
$STD /usr/local/bin/pearlie-update --install
msg_ok "Built Pearlie"
systemctl enable -q --now pearlie

msg_ok "Pearlie has no login: keep it behind Tailscale, a firewall or a reverse proxy."

motd_ssh
customize
cleanup_lxc
