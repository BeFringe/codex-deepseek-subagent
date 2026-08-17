#!/bin/sh

set -eu

fail() {
  printf '%s\n' "codex plaintext candidate wrapper: $1" >&2
  exit 78
}

[ "${CODEX_G4_LIVE_SELECTION_AUTHORIZED-}" = "schema2-paired-probe" ] ||
  fail "live selection guard is absent"

candidate=${CODEX_G4_CANDIDATE_BIN-}
expected_sha256=${CODEX_G4_CANDIDATE_SHA256-}

case "$candidate" in
  /*) ;;
  *) fail "candidate path must be absolute" ;;
esac

[ -f "$candidate" ] || fail "candidate binary is missing"
[ -x "$candidate" ] || fail "candidate binary is not executable"
[ "${#expected_sha256}" -eq 64 ] || fail "candidate digest is invalid"
case "$expected_sha256" in
  *[!0-9a-f]*) fail "candidate digest is invalid" ;;
esac

actual_sha256=$(/usr/bin/shasum -a 256 "$candidate" | /usr/bin/awk '{print $1}')
[ "$actual_sha256" = "$expected_sha256" ] || fail "candidate digest mismatch"

mode=
saw_ephemeral=false
saw_ignore_user_config=false
saw_ignore_rules=false
for argument in "$@"; do
  case "$argument" in
    app-server|app|remote-control|mcp-server)
      fail "GUI and server entry points are forbidden"
      ;;
    exec)
      [ -z "$mode" ] || fail "multiple candidate entry points are forbidden"
      mode=exec
      ;;
    login)
      [ -z "$mode" ] || fail "multiple candidate entry points are forbidden"
      mode=login
      ;;
    --ephemeral)
      saw_ephemeral=true
      ;;
    --ignore-user-config)
      saw_ignore_user_config=true
      ;;
    --ignore-rules)
      saw_ignore_rules=true
      ;;
    --dangerously-bypass-approvals-and-sandbox|--approve-for-me|--add-dir|-s|--sandbox|-a|--ask-for-approval)
      fail "caller may not widen the probe permission posture"
      ;;
  esac
done

case "$mode" in
  login)
    [ "$#" -eq 2 ] && [ "$1" = "login" ] && [ "$2" = "status" ] ||
      fail "only login status is allowed"
    ;;
  exec)
    [ "$saw_ephemeral" = true ] || fail "exec requires --ephemeral"
    [ "$saw_ignore_user_config" = true ] || fail "exec requires --ignore-user-config"
    [ "$saw_ignore_rules" = true ] || fail "exec requires --ignore-rules"
    ;;
  *)
    fail "only headless exec or login status is allowed"
    ;;
esac

exec "$candidate" \
  -c 'features.multi_agent_v2.enabled=true' \
  -c 'features.multi_agent_v2.message_delivery="plaintext"' \
  -c 'features.multi_agent_v2.tool_namespace="g4_assignment"' \
  -c 'features.code_mode_host=false' \
  -a never \
  -s read-only \
  "$@"
