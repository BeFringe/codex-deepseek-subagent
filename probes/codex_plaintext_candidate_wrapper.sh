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

exec "$candidate" \
  -c 'features.multi_agent_v2.enabled=true' \
  -c 'features.multi_agent_v2.message_delivery="plaintext"' \
  "$@"
