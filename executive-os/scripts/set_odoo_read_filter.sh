#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${RAILWAY_PUBLIC_DOMAIN:?RAILWAY_PUBLIC_DOMAIN is required}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD is required}"

audit_dir="$(mktemp -d /tmp/hermes-odoo-filter.XXXXXX)"
cleanup() {
  rm -rf -- "${audit_dir}"
}
trap cleanup EXIT

base_url="https://${RAILWAY_PUBLIC_DOMAIN}"

curl -sS --fail --max-time 15 \
  -c "${audit_dir}/cookies" \
  -o /dev/null \
  -X POST \
  --data-urlencode "username=${ADMIN_USERNAME:-admin}" \
  --data-urlencode "password=${ADMIN_PASSWORD}" \
  --data-urlencode "returnTo=/" \
  "${base_url}/login"

hermes_token="$(
  curl -sS --fail --max-time 20 \
    -b "${audit_dir}/cookies" \
    "${base_url}/" |
  sed -n 's/.*window.__HERMES_SESSION_TOKEN__="\([^"]*\)".*/\1/p' |
  head -n 1
)"
test -n "${hermes_token}"

curl -sS --fail --max-time 20 \
  -b "${audit_dir}/cookies" \
  -H "X-Hermes-Session-Token: ${hermes_token}" \
  -o "${audit_dir}/config.json" \
  "${base_url}/api/config?profile=default"

jq '
  .mcp_servers.odoo.tools = {
    "include": [
      "search_records",
      "get_record",
      "list_models",
      "list_resource_templates",
      "aggregate_records"
    ]
  }
  | {"servers": .mcp_servers, "profile": "default"}
' "${audit_dir}/config.json" > "${audit_dir}/payload.json"

jq -S '.mcp_servers | keys' "${audit_dir}/config.json" > "${audit_dir}/keys-before.json"
jq -S '.servers | keys' "${audit_dir}/payload.json" > "${audit_dir}/keys-after.json"
cmp -s "${audit_dir}/keys-before.json" "${audit_dir}/keys-after.json"

http_code="$(
  curl -sS --max-time 20 \
    -b "${audit_dir}/cookies" \
    -H "X-Hermes-Session-Token: ${hermes_token}" \
    -H "Content-Type: application/json" \
    -X PUT \
    --data-binary @"${audit_dir}/payload.json" \
    -o "${audit_dir}/put-response.json" \
    -w "%{http_code}" \
    "${base_url}/api/mcp/servers?profile=default"
)"
test "${http_code}" = "200"
jq -e '.ok == true' "${audit_dir}/put-response.json" >/dev/null

curl -sS --fail --max-time 20 \
  -b "${audit_dir}/cookies" \
  -H "X-Hermes-Session-Token: ${hermes_token}" \
  -o "${audit_dir}/inventory.json" \
  "${base_url}/api/mcp/servers?profile=default"

jq -e '
  .servers[]
  | select(.name == "odoo")
  | .enabled == true
    and .tools.include == [
      "search_records",
      "get_record",
      "list_models",
      "list_resource_templates",
      "aggregate_records"
    ]
' "${audit_dir}/inventory.json" >/dev/null

jq '
  .servers[]
  | select(.name == "odoo")
  | {name, enabled, transport, tools}
' "${audit_dir}/inventory.json"
