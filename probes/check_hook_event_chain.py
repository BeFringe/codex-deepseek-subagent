#!/usr/bin/env python3

"""Validate the durable privacy-minimized Hook event chain."""

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
from hook_event_receipts import (  # noqa: E402
    audit_apply_patch_callbacks,
    load_chain,
    load_writer_aborts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--require-complete-callbacks", action="store_true")
    arguments = parser.parse_args()
    try:
        chain = load_chain(arguments.state_directory)
        report = audit_apply_patch_callbacks(
            chain,
            require_complete=arguments.require_complete_callbacks,
            writer_aborts=load_writer_aborts(arguments.state_directory),
        )
    except (OSError, StateError, ValueError) as error:
        print(f"Hook event chain is not qualified: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
