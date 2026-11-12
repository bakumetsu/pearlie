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

curl -fsSL "${PEARLIE_RAW_URL:-https://raw.githubusercontent.com/bakumetsu/pearlie/main}/deploy/pearlie-update.sh" -o /usr/local/bin/pearlie-update
chmod 755 /usr/local/bin/pearlie-update

if [[ ! -f /opt/pearlie/.env ]]; then
  (
    umask 077
    {
      echo "# written by pearlie-install; the container script (ct/pearlie.sh) switches mode and host after host setup"
      echo "PEARLIE_MODE=fixture"
      echo "PEARLIE_DB_PATH=/opt/pearlie/data/pearlie.db"
      echo "PEARLIE_STATIC_DIR=/opt/pearlie/current/app/frontend/dist"
      echo "PEARLIE_HOST=127.0.0.1"
      echo "PEARLIE_PORT=8000"
      printf 'PEARLIE_SECRET_KEY=%s\n' "$(openssl rand -hex 32)"
    } > /opt/pearlie/.env
  )
  chmod 600 /opt/pearlie/.env
fi

cat <<'CONF' > /opt/pearlie/update.conf
channel=main
check=on
host=127.0.0.1
port=8000
CONF

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

msg_ok "Pearlie has no login of its own: reach it only over Tailscale or a reverse proxy."

motd_ssh
customize
cleanup_lxc
