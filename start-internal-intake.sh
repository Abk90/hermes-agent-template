#!/bin/bash
set -euo pipefail

mkdir -p /data/.hermes/logs /data/.hermes/sessions /data/.hermes/memories \
         /data/.hermes/skills /data/.hermes/platforms/pairing \
         /data/.hermes/executive-os /data/.hermes/home
chmod 700 /data/.hermes /data/.hermes/executive-os

if [ ! -f /data/.hermes/config.yaml ] && [ -f /opt/hermes-agent/cli-config.yaml.example ]; then
  cp /opt/hermes-agent/cli-config.yaml.example /data/.hermes/config.yaml
fi
[ -f /data/.hermes/.env ] || touch /data/.hermes/.env
chmod 600 /data/.hermes/.env /data/.hermes/config.yaml

case "${TELEGRAM_ALLOW_ALL_USERS:-false}:${GATEWAY_ALLOW_ALL_USERS:-false}" in
  true:*|*:true|1:*|*:1|yes:*|*:yes|on:*|*:on)
    echo "Internal intake refuses allow-all Telegram or gateway access" >&2
    exit 1
    ;;
esac

if [ -z "${TELEGRAM_ALLOWED_USERS:-}" ]; then
  echo "TELEGRAM_ALLOWED_USERS with exact numeric pilot IDs is required" >&2
  exit 1
fi
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "A distinct Bureau Ahmed TELEGRAM_BOT_TOKEN is required" >&2
  exit 1
fi
if [ -z "${INTERNAL_INTAKE_DEVICE_CREDENTIALS_JSON:-}" ]; then
  echo "INTERNAL_INTAKE_DEVICE_CREDENTIALS_JSON is required" >&2
  exit 1
fi
if [ -z "${INTERNAL_INTAKE_CONTEXT_SIGNING_KEY:-}" ] || [ "${#INTERNAL_INTAKE_CONTEXT_SIGNING_KEY}" -lt 32 ]; then
  echo "INTERNAL_INTAKE_CONTEXT_SIGNING_KEY with at least 32 characters is required" >&2
  exit 1
fi
if [ -z "${ODOO_MCP_URL:-}" ]; then
  echo "A private ODOO_MCP_URL is required for exact context verification" >&2
  exit 1
fi

export TELEGRAM_ALLOW_ALL_USERS=false
export GATEWAY_ALLOW_ALL_USERS=false
export INTERNAL_INTAKE_ENABLED=true
export INTERNAL_INTAKE_API_ENABLED=true

python -m executive_os.intake_bootstrap
python -m executive_os.intake_selftest

# Keep a persistent gateway log while mirroring it to Railway so an unhealthy
# Telegram poller cannot hide behind a green API healthcheck.
hermes gateway > >(tee -a /data/.hermes/logs/internal-intake-gateway.log) 2>&1 &
gateway_pid=$!
uvicorn executive_os.intake_api:create_app --factory --host 0.0.0.0 --port "${PORT:-8080}" --workers 1 &
api_pid=$!

cleanup() {
  kill "${gateway_pid}" "${api_pid}" 2>/dev/null || true
  wait "${gateway_pid}" "${api_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

set +e
wait -n "${gateway_pid}" "${api_pid}"
exit_code=$?
set -e
cleanup
exit "${exit_code}"
