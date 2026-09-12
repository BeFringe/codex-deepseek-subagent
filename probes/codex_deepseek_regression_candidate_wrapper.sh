#!/bin/sh

set -eu

fail() {
  printf '%s\n' "codex DeepSeek regression wrapper: $1" >&2
  exit 78
}

[ "${CODEX_P7_DEEPSEEK_REGRESSION_AUTHORIZED-}" = "schema1-native-readonly" ] ||
  fail "probe authorization guard is absent"

candidate=${CODEX_G4_CANDIDATE_BIN-}
expected_candidate_sha256=${CODEX_G4_CANDIDATE_SHA256-}
role_config=${CODEX_P7_DEEPSEEK_ROLE_CONFIG-}
expected_role_sha256=${CODEX_P7_DEEPSEEK_ROLE_SHA256-}
probe_root=${CODEX_P7_DEEPSEEK_PROBE_ROOT-}
handoff_root=${CODEX_DEEPSEEK_HANDOFF_DIR-}

case "$candidate" in
  /*) ;;
  *) fail "candidate path must be absolute" ;;
esac
case "$role_config" in
  */agents/v4-flash-worker.toml) ;;
  *) fail "role config must be the exact generic v4 role path" ;;
esac
case "$probe_root" in
  /private/tmp/codex-p7-deepseek-regression.*) ;;
  *) fail "probe root is outside the fixed temporary namespace" ;;
esac
case "$handoff_root" in
  /private/tmp/codex-p7-deepseek-handoff.*) ;;
  *) fail "handoff root is outside the fixed temporary namespace" ;;
esac

[ -f "$candidate" ] && [ -x "$candidate" ] || fail "candidate binary is unavailable"
[ ! -L "$candidate" ] || fail "candidate binary must not be a symlink"
[ -f "$role_config" ] && [ ! -L "$role_config" ] || fail "role config is unavailable"
[ -d "$probe_root" ] && [ ! -L "$probe_root" ] || fail "probe root is unavailable"
[ -d "$handoff_root" ] && [ ! -L "$handoff_root" ] || fail "handoff root is unavailable"
[ -n "${DEEPSEEK_API_KEY-}" ] || fail "DeepSeek credential is absent"

for digest in "$expected_candidate_sha256" "$expected_role_sha256"; do
  [ "${#digest}" -eq 64 ] || fail "expected digest is invalid"
  case "$digest" in
    *[!0-9a-f]*) fail "expected digest is invalid" ;;
  esac
done

actual_candidate_sha256=$(/usr/bin/shasum -a 256 "$candidate" | /usr/bin/awk '{print $1}')
[ "$actual_candidate_sha256" = "$expected_candidate_sha256" ] || fail "candidate digest mismatch"
actual_role_sha256=$(/usr/bin/shasum -a 256 "$role_config" | /usr/bin/awk '{print $1}')
[ "$actual_role_sha256" = "$expected_role_sha256" ] || fail "role config digest mismatch"

[ "$#" -ge 1 ] && [ "$1" = "exec" ] || fail "only headless exec is allowed"
saw_ignore_user_config=false
saw_ignore_rules=false
saw_json=false
saw_hook_trust_bypass=false
requested_cd=
expect_cd=false
for argument in "$@"; do
  if [ "$expect_cd" = true ]; then
    requested_cd=$argument
    expect_cd=false
    continue
  fi
  case "$argument" in
    app-server|app|remote-control|mcp-server|login)
      fail "non-exec entry points are forbidden"
      ;;
    --ephemeral)
      fail "probe must retain SessionMeta"
      ;;
    --ignore-user-config)
      saw_ignore_user_config=true
      ;;
    --ignore-rules)
      saw_ignore_rules=true
      ;;
    --json)
      saw_json=true
      ;;
    --dangerously-bypass-hook-trust)
      saw_hook_trust_bypass=true
      ;;
    -C|--cd)
      expect_cd=true
      ;;
    --cd=*)
      requested_cd=${argument#--cd=}
      ;;
    --dangerously-bypass-approvals-and-sandbox|--approve-for-me|--add-dir|-s|--sandbox|-a|--ask-for-approval)
      fail "caller may not widen the probe permission posture"
      ;;
    -c|--config|--config=*|-c?*)
      fail "caller may not override candidate configuration"
      ;;
  esac
done

[ "$expect_cd" = false ] || fail "working-directory option is missing its value"
[ "$saw_ignore_user_config" = true ] || fail "exec requires --ignore-user-config"
[ "$saw_ignore_rules" = true ] || fail "exec requires --ignore-rules"
[ "$saw_json" = true ] || fail "exec requires JSON event output"
[ "$saw_hook_trust_bypass" = true ] || fail "exec requires the vetted Hook trust bypass"
[ "$requested_cd" = "$probe_root" ] || fail "exec requires the exact guarded root"

git_root=$(/usr/bin/git -C "$probe_root" rev-parse --show-toplevel 2>/dev/null) ||
  fail "probe root is not a Git worktree"
[ "$git_root" = "$probe_root" ] || fail "probe root is not the exact Git top level"
[ -n "$(/usr/bin/git -C "$probe_root" symbolic-ref --short HEAD 2>/dev/null)" ] ||
  fail "probe root must have an attached branch"
[ -z "$(/usr/bin/git -C "$probe_root" status --short --untracked-files=all)" ] ||
  fail "probe root is not clean"

exec "$candidate" \
  -c 'features.multi_agent_v2.enabled=true' \
  -c 'features.multi_agent_v2.message_delivery="plaintext"' \
  -c 'features.multi_agent_v2.tool_namespace="g4_assignment"' \
  -c 'features.multi_agent_v2.child_model_providers={v4_flash_worker="deepseek"}' \
  -c "agents.v4_flash_worker.config_file=\"$role_config\"" \
  -c 'model_providers.deepseek.name="DeepSeek P7 child"' \
  -c 'model_providers.deepseek.base_url="https://api.deepseek.com"' \
  -c 'model_providers.deepseek.env_key="DEEPSEEK_API_KEY"' \
  -c 'model_providers.deepseek.wire_api="responses"' \
  -c 'model_providers.deepseek.requires_openai_auth=false' \
  -c 'model_providers.deepseek.request_max_retries=0' \
  -c 'model_providers.deepseek.stream_max_retries=0' \
  -c 'features.code_mode_host=false' \
  -a never \
  -s read-only \
  "$@"
