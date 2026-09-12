#!/usr/bin/env python3

"""Abort an unchanged apply_patch claim after a missing failure callback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
HOOKS = SOURCE_ROOT / "hooks"
if not (HOOKS / "compatibility_state.py").is_file():
    HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))

from compatibility_state import StateError, StateStore, validate_writer_abort  # noqa: E402
from runtime_guard import collect_git_snapshot  # noqa: E402
from writer_lease_guard import actor_identity_from_hook  # noqa: E402


RECOVERY_REASON = "missing_posttooluse_after_tool_failure"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--transcript-path", type=Path, required=True)
    parser.add_argument("--agent-id")
    parser.add_argument("--agent-type")
    parser.add_argument("--recovery-reason", choices=[RECOVERY_REASON], required=True)
    arguments = parser.parse_args()

    hook_identity = {
        "session_id": arguments.session_id,
        "transcript_path": str(arguments.transcript_path.resolve()),
    }
    if arguments.agent_id is not None:
        hook_identity["agent_id"] = arguments.agent_id
    if arguments.agent_type is not None:
        hook_identity["agent_type"] = arguments.agent_type
    try:
        store = StateStore(arguments.state_directory)
        actor = actor_identity_from_hook(hook_identity)
        claim = store.read_writer_claim(arguments.claim_id)
        after_snapshot = collect_git_snapshot(claim["root"])
        receipt_path = store.abort_unchanged_writer_claim(
            actor,
            claim_id=arguments.claim_id,
            after_snapshot=after_snapshot,
            recovery_reason=arguments.recovery_reason,
        )
        receipt = validate_writer_abort(
            json.loads(receipt_path.read_text(encoding="utf-8"))
        )
    except (OSError, StateError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"Writer claim recovery denied: {error}", file=sys.stderr)
        return 2
    report = {
        "schema": 1,
        "classification": receipt["classification"],
        "claim_id": receipt["claim_id"],
        "claim_sha256": receipt["claim_sha256"],
        "abort_sha256": receipt["abort_sha256"],
        "actor": receipt["actor"],
        "root": receipt["root"],
        "paths": receipt["paths"],
        "before_path_snapshot_sha256": receipt["before_path_snapshot_sha256"],
        "after_path_snapshot_sha256": receipt["after_path_snapshot_sha256"],
        "recovered_at": receipt["recovered_at"],
        "raw_payload_stored": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
