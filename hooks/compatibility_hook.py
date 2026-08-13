#!/usr/bin/env python3

"""Isolated multi-event Hook entry point for Phase 1 qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from assignment_transport import capture_spawn, subagent_start
from compatibility_state import StateError, StateStore
from runtime_guard import pre_compact, pre_tool_use, subagent_stop


def dispatch(
    store: StateStore,
    hook_input: dict,
    *,
    plaintext_agent_types: set[str],
) -> dict:
    event = hook_input.get("hook_event_name")
    child_is_target = hook_input.get("agent_type") in plaintext_agent_types
    if event == "PreToolUse":
        if child_is_target:
            return pre_tool_use(store, hook_input)
        return capture_spawn(
            store,
            hook_input,
            plaintext_agent_types=plaintext_agent_types,
        )
    if event == "SubagentStart":
        return subagent_start(store, hook_input) if child_is_target else {}
    if event == "PreCompact":
        if not child_is_target:
            return {}
        try:
            return pre_compact(store, hook_input)
        except StateError as error:
            raise StateError(f"TASK.AUTHORITY_BLOCKED: {error}") from error
    if event == "PostCompact":
        return {}
    if event == "SubagentStop":
        return subagent_stop(store, hook_input) if child_is_target else {}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument(
        "--plaintext-agent-type",
        action="append",
        required=True,
        dest="plaintext_agent_types",
    )
    arguments = parser.parse_args()
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        print(f"Hook input was invalid JSON: {error}", file=sys.stderr)
        return 4
    if not isinstance(hook_input, dict):
        print("Hook input must be a JSON object.", file=sys.stderr)
        return 4
    try:
        output = dispatch(
            StateStore(arguments.state_directory),
            hook_input,
            plaintext_agent_types=set(arguments.plaintext_agent_types),
        )
    except StateError as error:
        print(str(error), file=sys.stderr)
        return 12
    json.dump(output, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
