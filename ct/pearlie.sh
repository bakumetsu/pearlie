#!/usr/bin/env bash
# Copyright (c) Pearlie contributors | License: MIT | https://github.com/bakumetsu/pearlie
# Pin: community-scripts/core sha checked 2026-11-12. To bump: pick a new core commit, re-read core/build.func, replace the sha below.
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/bakumetsu/pearlie/main}"
export COMMUNITY_SCRIPTS_CORE_URL="${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/39ac4530299dd2c0d8c162a4bd7b1b9c826dd5c8}"
# shellcheck source=/dev/null
source <(curl -fsSL "$COMMUNITY_SCRIPTS_CORE_URL/core/build.func")

APP="Pearlie"
var_tags="${var_tags:-media;arr}"
var_cpu="${var_cpu:-1}"
var_ram="${var_ram:-1024}"
var_disk="${var_disk:-4}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/pearlie/current ]]; then
    msg_error "No Pearlie installation found!"
    exit
  fi
  msg_info "Updating Pearlie"
  if ! /usr/local/bin/pearlie-update; then
    msg_error "Update failed or was rolled back, see /opt/pearlie/update.log"
    exit 1
  fi
  msg_ok "Update finished"
  exit
}

function pearlie_host_setup() {
  local ans _input

  read -r -p "Bind media folders from the Proxmox host into the container (Stash Temp, Stash Other)? Mount the shares on the host first. [y/N] " ans
  if [[ "${ans,,}" != "y" ]]; then
    NFS_MODE="fixture"
  else
    NFS_MODE="nfs"

    read -r -p "Host folder for Stash Temp (already mounted): " HOST_TEMP
    if [[ ! -d "$HOST_TEMP" ]]; then
      msg_error "Host folder for Stash Temp does not exist: $HOST_TEMP"
      exit 1
    fi
    read -r -p "Host folder for Stash Other (already mounted): " HOST_OTHER
    if [[ ! -d "$HOST_OTHER" ]]; then
      msg_error "Host folder for Stash Other does not exist: $HOST_OTHER"
      exit 1
    fi

    read -r -p "Container path for Stash Temp [/mnt/media/stash/Temp]: " _input
    MP_TEMP="${_input:-/mnt/media/stash/Temp}"
    read -r -p "Container path for Stash Other [/mnt/media/stash/Other]: " _input
    MP_OTHER="${_input:-/mnt/media/stash/Other}"
  fi

  read -r -p "Is access to this container limited to your tailnet or reverse proxy (for example a Proxmox firewall rule on the container)? [y/N] " ans
  if [[ "${ans,,}" == "y" ]]; then
    TRUSTED=1
  else
    TRUSTED=0
    msg_info "Pearlie will bind to 127.0.0.1. You must put tailscale serve or a reverse proxy in front."
  fi
}

function pearlie_finish() {
  local mode_val host_ip temp_val other_val i

  if [[ "${NFS_MODE}" == "nfs" ]]; then
    pct set "$CTID" -mp0 "${HOST_TEMP},mp=${MP_TEMP}"
    pct set "$CTID" -mp1 "${HOST_OTHER},mp=${MP_OTHER}"
    pct reboot "$CTID"

    for i in $(seq 1 30); do
      if pct exec "$CTID" -- true 2>/dev/null; then
        break
      fi
      sleep 1
    done
    if ! pct exec "$CTID" -- true 2>/dev/null; then
      msg_error "Container did not come up within 30s"
      exit 1
    fi
  fi

  mode_val="fixture"
  if [[ "${NFS_MODE}" == "nfs" ]]; then
    mode_val="real"
  fi

  host_ip=""
  if [[ "${TRUSTED}" == "1" ]]; then
    for i in 1 2 3 4 5 6 7 8 9 10; do
      host_ip=$(pct exec "$CTID" -- hostname -I 2>/dev/null |
        awk '{for (j = 1; j <= NF; j++) if ($j ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) { print $j; exit }}')
      [[ -n "$host_ip" ]] && break
      sleep 2
    done
    if [[ -z "$host_ip" ]]; then
      TRUSTED=0
      msg_info "No container IP yet: Pearlie stays on 127.0.0.1. Put tailscale serve or a reverse proxy in front."
    fi
  fi

  temp_val=""
  other_val=""
  if [[ "${NFS_MODE}" == "nfs" ]]; then
    temp_val="${MP_TEMP}"
    other_val="${MP_OTHER}"
  fi

  pct exec "$CTID" -- bash -c '
set -eu
ENV_FILE="/opt/pearlie/.env"
mode="$1"
trusted="$2"
host_ip="$3"
temp_dir="$4"
other_dir="$5"

set_key() {
  local key="$1" val="$2"
  (umask 077; grep -v "^${key}=" "$ENV_FILE" > "${ENV_FILE}.new" || true)
  printf "%s=%s\n" "$key" "$val" >> "${ENV_FILE}.new"
  mv "${ENV_FILE}.new" "$ENV_FILE"
}

set_key "PEARLIE_MODE" "$mode"

if [ "$trusted" = "1" ]; then
  set_key "PEARLIE_HOST" "$host_ip"
  set_key "PEARLIE_TRUSTED_NETWORK" "1"
  if grep -q "^host=" /opt/pearlie/update.conf; then
    sed -i "s|^host=.*|host=${host_ip}|" /opt/pearlie/update.conf
  else
    printf "host=%s\n" "$host_ip" >> /opt/pearlie/update.conf
  fi
fi

if [ -n "$temp_dir" ]; then
  set_key "PEARLIE_STASH_TEMP_DIR" "$temp_dir"
  set_key "PEARLIE_STASH_DEFAULT_DIR" "$other_dir"
fi

chmod 600 "$ENV_FILE"
systemctl restart pearlie
' _ "$mode_val" "$TRUSTED" "$host_ip" "$temp_val" "$other_val"
}

NFS_MODE="fixture"
TRUSTED=0
if command -v pveversion >/dev/null 2>&1; then
  pearlie_host_setup
fi
start
build_container
pearlie_finish
description
msg_ok "Completed successfully!"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW} Access it using the following URL:${CL}"
if [[ "$TRUSTED" == "1" ]]; then
  echo -e "${TAB}${GATEWAY}${BGN}http://${host_ip:-$IP}:8000${CL}"
else
  echo -e "${TAB}${INFO} Bound to 127.0.0.1 inside the container: use tailscale serve or a reverse proxy to reach it.${CL}"
fi
echo -e "${TAB}${INFO} Pearlie has no login of its own: keep it behind Tailscale or a reverse proxy.${CL}"
