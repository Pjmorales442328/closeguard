#!/usr/bin/env bash
# One-time, idempotent VM prep: Docker + compose, deploy user, ufw, unattended-upgrades, UTC.
# Run from the repo root: ssh root@$VULTR_VM_IP 'bash -s' < deploy/bootstrap.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl ufw unattended-upgrades

# Docker Engine + compose plugin from the official apt repo
install -m 0755 -d /etc/apt/keyrings
[ -f /etc/apt/keyrings/docker.asc ] || curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -q
apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Non-root deploy user in the docker group, same authorized key as root
id deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
install -m 600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys

# Firewall: 22/80/443 only (443/udp for HTTP/3)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

# Security updates on autopilot
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades
systemctl enable --now unattended-upgrades

timedatectl set-timezone UTC

# App dir + server-side .env with a generated DB password (never overwritten)
install -d -o deploy -g deploy /opt/closeguard
if [ ! -f /opt/closeguard/.env ]; then
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)" > /opt/closeguard/.env
  chown deploy:deploy /opt/closeguard/.env
  chmod 600 /opt/closeguard/.env
fi

docker --version
docker compose version
ufw status verbose
