#!/usr/bin/env python3

"""Prove whether same-UID mode bits protect authority and rollout fixtures."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def probe() -> dict:
    with tempfile.TemporaryDirectory(prefix="codex-authority-trust-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        state = root / "active-capsule.json"
        rollout = root / "child-rollout.jsonl"
        state.write_text("trusted-state\n", encoding="utf-8")
        rollout.write_text("trusted-rollout\n", encoding="utf-8")
        state.chmod(0o600)
        rollout.chmod(0o600)
        child_program = (
            "from pathlib import Path; import sys; "
            "Path(sys.argv[1]).write_text('child-mutated-state\\n', encoding='utf-8'); "
            "Path(sys.argv[2]).write_text('child-mutated-rollout\\n', encoding='utf-8')"
        )
        completed = subprocess.run(
            [sys.executable, "-c", child_program, str(state), str(rollout)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        state_protected = state.read_text(encoding="utf-8") == "trusted-state\n"
        rollout_protected = rollout.read_text(encoding="utf-8") == "trusted-rollout\n"
        return {
            "schema": 1,
            "platform": os.name,
            "same_uid_child_exit_code": completed.returncode,
            "same_uid_state_protected": state_protected,
            "same_uid_rollout_protected": rollout_protected,
            "direct_write_qualified": state_protected and rollout_protected,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-protected", action="store_true")
    arguments = parser.parse_args()
    result = probe()
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    if result["same_uid_child_exit_code"] != 0:
        return 1
    if arguments.require_protected and not result["direct_write_qualified"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
