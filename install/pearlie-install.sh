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

cat <<CONF > /opt/pearlie/update.conf
channel=main
check=on
host=auto
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

msg_ok "Pearlie has no login: keep it behind Tailscale, a firewall or a reverse proxy."

motd_ssh
customize
cleanup_lxc
