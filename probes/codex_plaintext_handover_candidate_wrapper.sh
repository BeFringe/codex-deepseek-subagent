#!/bin/sh

set -eu

fail() {
  printf '%s\n' "codex plaintext handover candidate wrapper: $1" >&2
  exit 78
}

[ "${CODEX_G4_LIVE_SELECTION_AUTHORIZED-}" = "schema2-paired-probe" ] ||
  fail "live selection guard is absent"
[ "${CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED-}" = "schema1-headless-stateful" ] ||
  fail "SessionMeta probe guard is absent"
[ "${CODEX_G4_P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED-}" = "schema1-exact-write-then-close" ] ||
  fail "P5b write-then-close guard is absent"
[ "${CODEX_G4_P5B_HANDOVER_PROBE_AUTHORIZED-}" = "schema1-exact-barrier-replacement" ] ||
  fail "handover probe guard is absent"

candidate=${CODEX_G4_CANDIDATE_BIN-}
expected_sha256=${CODEX_G4_CANDIDATE_SHA256-}
stateful_root=${CODEX_G4_SESSIONMETA_PROBE_ROOT-}

case "$candidate" in
  /*) ;;
  *) fail "candidate path must be absolute" ;;
esac
case "$stateful_root" in
  /private/tmp/codex-g4-p5b-write-termination.*) ;;
  *) fail "handover root is outside the fixed temporary namespace" ;;
esac
[ -f "$candidate" ] && [ -x "$candidate" ] || fail "candidate is not executable"
[ "${#expected_sha256}" -eq 64 ] || fail "candidate digest is invalid"
case "$expected_sha256" in
  *[!0-9a-f]*) fail "candidate digest is invalid" ;;
esac
[ "$(/usr/bin/shasum -a 256 "$candidate" | /usr/bin/awk '{print $1}')" = "$expected_sha256" ] ||
  fail "candidate digest mismatch"

mode=
requested_cd=
expect_cd=false
saw_ephemeral=false
saw_ignore_user_config=false
saw_ignore_rules=false
saw_json=false
saw_hook_trust_bypass=false
for argument in "$@"; do
  if [ "$expect_cd" = true ]; then
    requested_cd=$argument
    expect_cd=false
    continue
  fi
  case "$argument" in
    app-server|app|remote-control|mcp-server|login)
      fail "only headless exec is allowed"
      ;;
    exec)
      [ -z "$mode" ] || fail "multiple entry points are forbidden"
      mode=exec
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

[ "$mode" = exec ] || fail "only headless exec is allowed"
[ "$expect_cd" = false ] || fail "working-directory argument is missing"
[ "$saw_ephemeral" = false ] || fail "handover probe must retain SessionMeta"
[ "$saw_ignore_user_config" = true ] || fail "exec requires --ignore-user-config"
[ "$saw_ignore_rules" = true ] || fail "exec requires --ignore-rules"
[ "$saw_json" = true ] || fail "exec requires JSON event output"
[ "$saw_hook_trust_bypass" = true ] || fail "exec requires the vetted Hook trust bypass"
[ "$requested_cd" = "$stateful_root" ] || fail "exec does not use the exact guarded root"
[ -d "$stateful_root" ] || fail "handover root is missing"
git_root=$(/usr/bin/git -C "$stateful_root" rev-parse --show-toplevel 2>/dev/null) ||
  fail "handover root is not a Git worktree"
[ "$git_root" = "$stateful_root" ] || fail "handover root is not the exact Git top level"
[ "$(/usr/bin/git -C "$stateful_root" status --short --untracked-files=all)" = "?? qualified.txt" ] ||
  fail "handover root is not the exact prior dirty frontier"
[ -f "$stateful_root/qualified.txt" ] && [ ! -L "$stateful_root/qualified.txt" ] ||
  fail "handover target is not one regular file"
[ "$(/usr/bin/shasum -a 256 "$stateful_root/qualified.txt" | /usr/bin/awk '{print $1}')" = "4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c" ] ||
  fail "handover target does not match the frozen prior bytes"

CODEX_G4_TOOL_CATALOG_RECEIPT=stderr-v2-parent-child-closed
export CODEX_G4_TOOL_CATALOG_RECEIPT

exec "$candidate" \
  -c 'features.multi_agent_v2.enabled=true' \
  -c 'features.multi_agent_v2.message_delivery="plaintext"' \
  -c 'features.multi_agent_v2.tool_namespace="g4_assignment"' \
  -c 'features.code_mode_host=false' \
  -a never \
  -s workspace-write \
  "$@"
