#!/usr/bin/env bash
# Ship the repo to the VM and (re)start the compose stack. Reads VULTR_VM_IP from .env.
# Usage (repo root): ENV_FILE=path/to/.env deploy/deploy.sh   (default ENV_FILE=.env)
set -euo pipefail
ENV_FILE=${ENV_FILE:-.env}
IP=$(grep '^VULTR_VM_IP=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r"')
[ -n "$IP" ] || { echo "VULTR_VM_IP missing in $ENV_FILE" >&2; exit 1; }
KEY=${SSH_KEY:-.keys/id_ed25519}
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new root@$IP"
DIR=/opt/closeguard

# tar over ssh because Git Bash has no rsync; stale remote files persist until removed by hand
tar --exclude=.git --exclude=.env --exclude=.keys --exclude=credentials.md \
    --exclude=__pycache__ --exclude=.venv -cz . | $SSH "tar -xz -C $DIR && chown -R deploy:deploy $DIR"

# VM .env (never overwritten): DOMAIN, random hex role passwords, model switch. Values are generated on the VM.
$SSH "cd $DIR && touch .env && chmod 600 .env && chown deploy:deploy .env
  grep -q '^DOMAIN=' .env || echo DOMAIN=closeguard.\$(echo $IP | tr . -).sslip.io >> .env
  grep -q '^CG_WRITER_PASSWORD=' .env || echo CG_WRITER_PASSWORD=\$(openssl rand -hex 24) >> .env
  grep -q '^CG_READER_PASSWORD=' .env || echo CG_READER_PASSWORD=\$(openssl rand -hex 24) >> .env
  grep -q '^CG_MODEL_LIVE=' .env || echo CG_MODEL_LIVE=1 >> .env"

# Inference key: copied once over stdin (never argv, never printed)
if ! $SSH "grep -q '^VULTR_INFERENCE_KEY=.' $DIR/.env"; then
  grep '^VULTR_INFERENCE_KEY=' "$ENV_FILE" | sed 's/\r$//' | $SSH "cat >> $DIR/.env" && echo "inference key added to VM .env"
fi

$SSH "cd $DIR && docker compose up -d --build --remove-orphans && docker compose ps"
