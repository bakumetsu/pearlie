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

start
build_container
description
msg_ok "Completed successfully!"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW} Access it using the following URL:${CL}"
echo -e "${TAB}${GATEWAY}${BGN}http://${IP}:8000${CL}"
echo -e "${TAB}${INFO} Pearlie has no login: keep it behind Tailscale, a firewall or a reverse proxy.${CL}"
