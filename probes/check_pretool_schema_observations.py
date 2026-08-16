#!/usr/bin/env python3

"""Validate and summarize value-free live PreToolUse schema receipts."""

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

from compatibility_state import StateError  # noqa: E402
from pretool_schema_observation import load_receipts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--runtime-session-id")
    parser.add_argument("--require-tool-name", action="append", default=[])
    parser.add_argument("--require-observation", action="store_true")
    arguments = parser.parse_args()
    try:
        receipts = load_receipts(arguments.state_directory)
    except (OSError, StateError, ValueError) as error:
        print(f"PreToolUse schema observations are not qualified: {error}", file=sys.stderr)
        return 2
    if arguments.runtime_session_id:
        receipts = [
            receipt
            for receipt in receipts
            if receipt["actor"]["runtime_session_id"] == arguments.runtime_session_id
        ]
    if arguments.require_observation and not receipts:
        print("PreToolUse schema observations are not qualified: no matching receipt", file=sys.stderr)
        return 2
    observed_names = {receipt["tool_name"] for receipt in receipts}
    missing_names = sorted(set(arguments.require_tool_name) - observed_names)
    if missing_names:
        print(
            "PreToolUse schema observations are not qualified: missing tool names "
            + ", ".join(missing_names),
            file=sys.stderr,
        )
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
                "tool_name": receipt["tool_name"],
                "tool_use_id": receipt["tool_use_id"],
                "tool_input_type": receipt["tool_input_type"],
                "tool_input_shape": receipt["tool_input_shape"],
            }
            for receipt in receipts
        ],
        "raw_payload_stored": False,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
