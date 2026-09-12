#!/usr/bin/env python3

"""Abort an unchanged non-Git apply_patch claim after a missing failure callback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
HOOKS = SOURCE_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

from compatibility_state import (  # noqa: E402
    StateError,
    StateStore,
    validate_non_git_writer_abort,
)
from writer_lease_guard import (  # noqa: E402
    actor_identity_from_hook,
    collect_patch_non_git_snapshot,
)


RECOVERY_REASON = "missing_posttooluse_after_tool_failure"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--transcript-path", type=Path, required=True)
    parser.add_argument("--recovery-reason", choices=[RECOVERY_REASON], required=True)
    arguments = parser.parse_args()

    hook_identity = {
        "session_id": arguments.session_id,
        "transcript_path": str(arguments.transcript_path.resolve()),
    }
    try:
        store = StateStore(arguments.state_directory)
        actor = actor_identity_from_hook(hook_identity)
        claim = store.read_non_git_writer_claim(arguments.claim_id)
        raw_paths = [str(Path(claim["root"]) / path) for path in claim["paths"]]
        snapshot, _ = collect_patch_non_git_snapshot(
            raw_paths,
            cwd=claim["root"],
            parent_non_git_writer_roots=[claim["root"]],
        )
        receipt_path = store.abort_unchanged_non_git_writer_claim(
            actor,
            claim_id=arguments.claim_id,
            after_snapshot=snapshot,
            recovery_reason=arguments.recovery_reason,
        )
        receipt = validate_non_git_writer_abort(
            json.loads(receipt_path.read_text(encoding="utf-8"))
        )
    except (OSError, StateError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"Non-Git writer claim recovery denied: {error}", file=sys.stderr)
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
        "before_snapshot_sha256": receipt["before_snapshot_sha256"],
        "after_snapshot_sha256": receipt["after_snapshot_sha256"],
        "recovered_at": receipt["recovered_at"],
        "raw_payload_stored": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
