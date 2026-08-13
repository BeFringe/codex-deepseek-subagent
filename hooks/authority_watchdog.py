#!/usr/bin/env python3

"""One-shot isolated watchdog for active authority deadlines."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

from compatibility_state import StateError, StateStore
from runtime_guard import sweep_deadlines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--now")
    parser.add_argument("--fail-on-termination", action="store_true")
    arguments = parser.parse_args()
    try:
        now = dt.datetime.fromisoformat(arguments.now) if arguments.now else None
        terminated = sweep_deadlines(
            StateStore(arguments.state_directory),
            now=now,
        )
    except (StateError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1
    result = {
        "valid": True,
        "terminated_count": len(terminated),
        "terminated": terminated,
        "parent_cancel_required": bool(terminated),
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    if arguments.fail_on_termination and terminated:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
