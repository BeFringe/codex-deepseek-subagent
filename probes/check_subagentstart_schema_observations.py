#!/usr/bin/env python3

"""Validate and summarize value-free live SubagentStart schema receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
HOOKS = SOURCE_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

from compatibility_state import StateError  # noqa: E402
from subagentstart_schema_observation import load_receipts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--runtime-session-id")
    parser.add_argument("--require-observation", action="store_true")
    arguments = parser.parse_args()
    try:
        receipts = load_receipts(arguments.state_directory)
    except (OSError, StateError, ValueError) as error:
        print(f"SubagentStart schema observations are not qualified: {error}", file=sys.stderr)
        return 2
    if arguments.runtime_session_id:
        receipts = [
            receipt
            for receipt in receipts
            if receipt["actor"]["runtime_session_id"] == arguments.runtime_session_id
        ]
    if arguments.require_observation and not receipts:
        print("SubagentStart schema observations are not qualified: no matching receipt", file=sys.stderr)
        return 2
    report = {
        "schema": 1,
        "observation_count": len(receipts),
        "observations": [
            {
                "receipt_sha256": receipt["receipt_sha256"],
                "observed_at": receipt["observed_at"],
                "actor": receipt["actor"],
                "cwd": receipt["cwd"],
                "hook_input_shape": receipt["hook_input_shape"],
                "selected_string_fingerprints": receipt["selected_string_fingerprints"],
            }
            for receipt in receipts
        ],
        "raw_payload_stored": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
