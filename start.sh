#!/bin/bash
set -e

# Mirror dashboard-ref-only's startup: create every directory hermes expects
# and seed a default config.yaml if the volume is empty. Without these,
# `hermes dashboard` endpoints that hit logs/, sessions/, cron/, etc. can fail
# with opaque errors even though no auth is actually involved.
# NOTE (hermes >= v2026.7.1): several dirs were consolidated and are now
# resolved via get_hermes_dir("<new>", "<old>"), which returns the NEW path
# unless the OLD one already has *content*. Seeding an empty legacy stub no
# longer "claims" it — hermes ignores empty stubs and writes to the new path
# (upstream #27602). So we seed the NEW paths: pairing -> platforms/pairing,
# image_cache -> cache/images, audio_cache -> cache/audio. A populated legacy
# dir from a pre-v2026.7.1 deploy still wins on both sides, so no migration is
# needed. server.py:_resolve_pairing_dir() mirrors this same rule for the
# admin panel's Users tab — keep the two in sync on future bumps.
mkdir -p /data/.hermes/cron /data/.hermes/sessions /data/.hermes/logs \
         /data/.hermes/memories /data/.hermes/skills /data/.hermes/platforms/pairing \
         /data/.hermes/hooks /data/.hermes/cache/images /data/.hermes/cache/audio \
         /data/.hermes/workspace /data/.hermes/skins /data/.hermes/plans \
         /data/.hermes/home

# Stamp the install method as "docker" so hermes treats this as an immutable
# container image, not a pip checkout. hermes's detect_install_method() reads
# $HERMES_HOME/.install_method FIRST (before any .git / pip fallback). Without
# this stamp the template falls through to "pip" — because the Dockerfile strips
# /opt/hermes-agent/.git — and the dashboard's "Update Hermes" button then runs
# a real `hermes update` (PyPI pip-upgrade) INSIDE the running container. That
# upgrade is ephemeral (reverts on the next redeploy) and can desync the Python
# package from the image's pre-built web_dist/ui-tui bundles. Stamping "docker"
# makes that button correctly refuse with "pull a fresh image / redeploy", which
# matches the real upgrade path here (bump HERMES_REF in Railway + redeploy).
# Written unconditionally each boot so it stays correct and self-heals.
printf 'docker\n' > /data/.hermes/.install_method

if [ ! -f /data/.hermes/config.yaml ] && [ -f /opt/hermes-agent/cli-config.yaml.example ]; then
  cp /opt/hermes-agent/cli-config.yaml.example /data/.hermes/config.yaml
fi

[ ! -f /data/.hermes/.env ] && touch /data/.hermes/.env

# Bootstrap OAuth tokens from env var (e.g. xAI Grok SuperGrok).
# Set HERMES_AUTH_JSON_BOOTSTRAP to the contents of a locally-generated
# ~/.hermes/auth.json. Written only once — subsequent token refreshes update
# the file in place on the persistent volume.
if [ ! -f /data/.hermes/auth.json ] && [ -n "${HERMES_AUTH_JSON_BOOTSTRAP}" ]; then
  printf '%s' "${HERMES_AUTH_JSON_BOOTSTRAP}" > /data/.hermes/auth.json
  chmod 600 /data/.hermes/auth.json
fi
unset HERMES_AUTH_JSON_BOOTSTRAP

# Bootstrap the single Google Workspace credential onto the persistent volume.
# The Railway secret is consumed only on the first boot; refreshed OAuth tokens
# then stay in the file and are not overwritten by an older bootstrap value.
if [ -n "${WORKSPACE_MCP_GOOGLE_TOKEN_JSON_BOOTSTRAP:-}" ]; then
  case "${USER_GOOGLE_EMAIL:-}" in
    ""|*[!A-Za-z0-9@._+-]*)
      echo "Invalid or missing USER_GOOGLE_EMAIL for Workspace MCP" >&2
      exit 1
      ;;
  esac
  workspace_credentials_dir="${WORKSPACE_MCP_CREDENTIALS_DIR:-/data/.hermes/workspace-mcp/credentials}"
  workspace_credentials_file="${workspace_credentials_dir}/${USER_GOOGLE_EMAIL}.json"
  mkdir -p "${workspace_credentials_dir}"
  chmod 700 "${workspace_credentials_dir}"
  if [ ! -f "${workspace_credentials_file}" ]; then
    printf '%s' "${WORKSPACE_MCP_GOOGLE_TOKEN_JSON_BOOTSTRAP}" > "${workspace_credentials_file}"
    chmod 600 "${workspace_credentials_file}"
  fi
fi
unset WORKSPACE_MCP_GOOGLE_TOKEN_JSON_BOOTSTRAP

# Run two fully isolated WhatsApp Web linked-device sessions on the persistent
# volume. Their REST APIs stay inside the container, on separate loopback ports,
# and the bridge itself enforces read-only mode even if a prompt tries to bypass
# the MCP tool filter and call /api/send directly.
start_whatsapp_bridge() {
  local account="$1"
  local port="$2"
  local account_dir="/data/.hermes/whatsapp/${account}"
  local log_file="/data/.hermes/logs/whatsapp-${account}.log"
  mkdir -p "${account_dir}/store"
  touch "${log_file}"
  chmod 600 "${log_file}"
  (
    set +e
    cd "${account_dir}"
    while true; do
      WHATSAPP_READ_ONLY=true /usr/local/bin/whatsapp-bridge-mcp -port "${port}"
      bridge_exit=$?
      printf 'WhatsApp bridge exited with code %s; restarting in 5 seconds\n' "${bridge_exit}"
      sleep 5
    done
  ) >> "${log_file}" 2>&1 &
}

start_whatsapp_bridge pro 8180
start_whatsapp_bridge personnel 8181

# Clear any stale gateway PID file left over from the previous container.
# `hermes gateway` writes /data/.hermes/gateway.pid on start but does not
# remove it on SIGTERM. Since /data is a persistent volume, the file
# survives container restarts and causes every subsequent boot to exit with
# "ERROR gateway.run: PID file race lost to another gateway instance".
# No hermes process can be running at this point (we're pre-exec in a fresh
# container), so removing the file unconditionally is safe.
rm -f /data/.hermes/gateway.pid

# Tell the dashboard its externally reachable URL.
# hermes >= v2026.7.20 builds the MCP OAuth redirect_uri from the request's own
# Host header. Our reverse proxy must strip that Host (hermes 400s anything but
# loopback on a loopback bind), so hermes would otherwise hand the OAuth
# provider `http://127.0.0.1:9119/...` — a URL only reachable inside this
# container, leaving the browser on a dead tab after consent with nothing in the
# logs. resolve_public_url() checks HERMES_DASHBOARD_PUBLIC_URL first, so
# setting it is the supported fix. Railway injects RAILWAY_PUBLIC_DOMAIN; `:=`
# keeps an operator-set value (e.g. a custom domain) winning.
if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
  : "${HERMES_DASHBOARD_PUBLIC_URL:=https://${RAILWAY_PUBLIC_DOMAIN}}"
  export HERMES_DASHBOARD_PUBLIC_URL
fi

exec python /app/server.py
