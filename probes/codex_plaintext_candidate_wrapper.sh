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
saw_json=false
saw_hook_trust_bypass=false
requested_cd=
expect_cd=false
sandbox_mode=read-only
code_mode_host=false
catalog_receipt_mode=
auto_compact_config=
for argument in "$@"; do
  if [ "$expect_cd" = true ]; then
    requested_cd=$argument
    expect_cd=false
    continue
  fi
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

case "$mode" in
  login)
    [ "$#" -eq 2 ] && [ "$1" = "login" ] && [ "$2" = "status" ] ||
      fail "only login status is allowed"
    ;;
  exec)
    [ "$saw_ignore_user_config" = true ] || fail "exec requires --ignore-user-config"
    [ "$saw_ignore_rules" = true ] || fail "exec requires --ignore-rules"
    if [ "$saw_ephemeral" != true ]; then
      [ "${CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED-}" = "schema1-headless-stateful" ] ||
        fail "stateful exec requires the SessionMeta probe guard"
      stateful_root=${CODEX_G4_SESSIONMETA_PROBE_ROOT-}
      case "$stateful_root" in
        /*) ;;
        *) fail "stateful probe root must be absolute" ;;
      esac
      [ -d "$stateful_root" ] || fail "stateful probe root is missing"
      [ "$requested_cd" = "$stateful_root" ] || fail "stateful exec requires the exact guarded root"
      [ "$saw_json" = true ] || fail "stateful exec requires JSON event output"
      [ "$saw_hook_trust_bypass" = true ] || fail "stateful exec requires the vetted Hook trust bypass"
      git_root=$(/usr/bin/git -C "$stateful_root" rev-parse --show-toplevel 2>/dev/null) ||
        fail "stateful probe root is not a Git worktree"
      [ "$git_root" = "$stateful_root" ] || fail "stateful probe root is not the exact Git top level"
      [ -z "$(/usr/bin/git -C "$stateful_root" status --short --untracked-files=all)" ] ||
        fail "stateful probe root is not clean"
    fi
    case "${CODEX_G4_EXACT_WRITE_PROBE_AUTHORIZED-}" in
      "") ;;
      schema1-exact-temporary-git-root)
        [ "$saw_ephemeral" = false ] || fail "write probe must retain SessionMeta"
        [ "$requested_cd" = "${CODEX_G4_SESSIONMETA_PROBE_ROOT-}" ] ||
          fail "write probe root is not the stateful root"
        case "$requested_cd" in
          /private/tmp/codex-g4-write-*) ;;
          *) fail "write probe root is outside the fixed temporary namespace" ;;
        esac
        sandbox_mode=workspace-write
        ;;
      *) fail "write probe authorization guard is invalid" ;;
    esac
    case "${CODEX_G4_AUTO_COMPACT_PROBE_AUTHORIZED-}" in
      "") ;;
      schema1-post-action-20000)
        [ "$saw_ephemeral" = false ] || fail "auto-compact probe must retain SessionMeta"
        auto_compact_config=model_auto_compact_token_limit=20000
        ;;
      *) fail "auto-compact probe authorization guard is invalid" ;;
    esac
    case "${CODEX_G4_FAILED_PATCH_CALLBACK_PROBE_AUTHORIZED-}" in
      "") ;;
      schema1-root-failed-apply-patch)
        [ "${CODEX_G4_EXACT_WRITE_PROBE_AUTHORIZED-}" = "schema1-exact-temporary-git-root" ] ||
          fail "failed-patch callback probe requires the exact write guard"
        case "$requested_cd" in
          /private/tmp/codex-g4-write-posttool-*) ;;
          *) fail "failed-patch callback root is outside the fixed temporary namespace" ;;
        esac
        code_mode_host=true
        ;;
      *) fail "failed-patch callback probe authorization guard is invalid" ;;
    esac
    case "${CODEX_G4_PARENT_CHILD_WRITER_CONFLICT_PROBE_AUTHORIZED-}" in
      "") ;;
      schema1-exact-active-child-claim)
        [ "${CODEX_G4_EXACT_WRITE_PROBE_AUTHORIZED-}" = "schema1-exact-temporary-git-root" ] ||
          fail "parent/child writer conflict probe requires the exact write guard"
        case "$requested_cd" in
          /private/tmp/codex-g4-write-parent-conflict.*) ;;
          *) fail "parent/child writer conflict root is outside the fixed temporary namespace" ;;
        esac
        code_mode_host=true
        catalog_receipt_mode=stderr-v2-parent-child-closed
        ;;
      *) fail "parent/child writer conflict probe authorization guard is invalid" ;;
    esac
    case "${CODEX_G4_P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED-}" in
      "") ;;
      schema1-exact-idle-child)
        [ "$saw_ephemeral" = false ] || fail "P5b termination probe must retain SessionMeta"
        case "$requested_cd" in
          /private/tmp/codex-g4-p5b-termination.*) ;;
          *) fail "P5b termination probe root is outside the fixed temporary namespace" ;;
        esac
        catalog_receipt_mode=stderr-v2-parent-child-closed
        ;;
      schema1-exact-tracked-process)
        [ "$saw_ephemeral" = false ] || fail "P5b tracked-process probe must retain SessionMeta"
        case "$requested_cd" in
          /private/tmp/codex-g4-p5b-tracked-process.*) ;;
          *) fail "P5b tracked-process probe root is outside the fixed temporary namespace" ;;
        esac
        code_mode_host_candidate=${candidate%/*}/codex-code-mode-host
        expected_code_mode_host_sha256=${CODEX_G4_CODE_MODE_HOST_SHA256-}
        [ -f "$code_mode_host_candidate" ] || fail "P5b code-mode host is missing beside candidate"
        [ -x "$code_mode_host_candidate" ] || fail "P5b code-mode host is not executable"
        [ "${#expected_code_mode_host_sha256}" -eq 64 ] || fail "P5b code-mode host digest is invalid"
        case "$expected_code_mode_host_sha256" in
          *[!0-9a-f]*) fail "P5b code-mode host digest is invalid" ;;
        esac
        actual_code_mode_host_sha256=$(/usr/bin/shasum -a 256 "$code_mode_host_candidate" | /usr/bin/awk '{print $1}')
        [ "$actual_code_mode_host_sha256" = "$expected_code_mode_host_sha256" ] ||
          fail "P5b code-mode host digest mismatch"
        code_mode_host=true
        catalog_receipt_mode=stderr-v2-parent-child-closed
        ;;
      schema1-exact-write-then-close)
        [ "$saw_ephemeral" = false ] || fail "P5b write-then-close probe must retain SessionMeta"
        case "$requested_cd" in
          /private/tmp/codex-g4-p5b-write-termination.*) ;;
          *) fail "P5b write-then-close root is outside the fixed temporary namespace" ;;
        esac
        sandbox_mode=workspace-write
        catalog_receipt_mode=stderr-v2-parent-child-closed
        ;;
      *) fail "P5b termination probe authorization guard is invalid" ;;
    esac
    ;;
  *)
    fail "only headless exec or login status is allowed"
    ;;
esac

if [ -n "$catalog_receipt_mode" ]; then
  CODEX_G4_TOOL_CATALOG_RECEIPT=$catalog_receipt_mode
  export CODEX_G4_TOOL_CATALOG_RECEIPT
else
  unset CODEX_G4_TOOL_CATALOG_RECEIPT
fi

if [ -n "$auto_compact_config" ]; then
  exec "$candidate" \
    -c 'features.multi_agent_v2.enabled=true' \
    -c 'features.multi_agent_v2.message_delivery="plaintext"' \
    -c 'features.multi_agent_v2.tool_namespace="g4_assignment"' \
    -c "features.code_mode_host=$code_mode_host" \
    -c "$auto_compact_config" \
    -a never \
    -s "$sandbox_mode" \
    "$@"
fi

exec "$candidate" \
  -c 'features.multi_agent_v2.enabled=true' \
  -c 'features.multi_agent_v2.message_delivery="plaintext"' \
  -c 'features.multi_agent_v2.tool_namespace="g4_assignment"' \
  -c "features.code_mode_host=$code_mode_host" \
  -a never \
  -s "$sandbox_mode" \
  "$@"
