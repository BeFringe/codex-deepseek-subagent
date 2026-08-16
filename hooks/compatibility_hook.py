#!/usr/bin/env python3

"""Isolated multi-event Hook entry point for Phase 1 qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from assignment_transport import capture_spawn, subagent_start
from compatibility_state import StateError, StateStore
from hook_event_receipts import (
    UnverifiableHookIdentity,
    is_target_spawn,
    record_from_hook,
)
from hook_schema_observation_arm import observation_root_for_event
from pretool_schema_observation import record_from_hook as record_pretool_schema
from runtime_guard import pre_compact, pre_tool_use, subagent_stop
from subagentstart_schema_observation import (
    record_from_hook as record_subagentstart_schema,
)
from writer_lease_guard import post_tool_use as release_writer_lease
from writer_lease_guard import pre_tool_use as guard_writer_lease


def fail_closed_output(event: object, error: BaseException) -> dict:
    """Translate an internal failure into the blocking shape for its Hook event."""

    reason = f"TASK.AUTHORITY_BLOCKED: {error}"
    if event == "PreToolUse":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    if event == "SubagentStop":
        return {
            "decision": "block",
            "reason": (
                f"{reason}. Continue the child only to return a fail-closed "
                "context-loss attestation."
            ),
        }
    if event == "SubagentStart":
        # Current Codex parses continue=false for this event but does not stop the
        # child. Make the loss explicit; the later PreToolUse guard must deny it.
        context = (
            f"TASK.CONTEXT_LOST: {reason}. Do not call tools or claim completion; "
            "return exactly TASK.CONTEXT_LOST and no other text. "
            "SubagentStart cannot itself cancel this child."
        )
        return {
            "systemMessage": context,
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": context,
            },
        }
    return {
        "continue": False,
        "stopReason": reason,
        "systemMessage": reason,
    }


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
        captured = capture_spawn(
            store,
            hook_input,
            plaintext_agent_types=plaintext_agent_types,
        )
        return captured or guard_writer_lease(store, hook_input)
    if event == "PostToolUse":
        return {} if child_is_target else release_writer_lease(store, hook_input)
    if event == "SubagentStart":
        return subagent_start(store, hook_input) if child_is_target else {}
    if event == "PreCompact":
        if not child_is_target:
            return {}
        return pre_compact(store, hook_input)
    if event == "PostCompact":
        return {}
    if event == "SubagentStop":
        return subagent_stop(store, hook_input) if child_is_target else {}
    return {}


def dispatch_with_receipts(
    store: StateStore,
    hook_input: dict,
    *,
    plaintext_agent_types: set[str],
    pretool_schema_observation_root: Path | None = None,
) -> dict:
    event = hook_input.get("hook_event_name")
    observation_root = pretool_schema_observation_root
    if observation_root is None:
        observation_root = observation_root_for_event(store, hook_input)
    if observation_root is not None:
        record_pretool_schema(
            store,
            hook_input,
            observation_root=observation_root,
        )
        record_subagentstart_schema(
            store,
            hook_input,
            observation_root=observation_root,
        )
    child_is_target = hook_input.get("agent_type") in plaintext_agent_types
    is_parent_writer = (
        event in {"PreToolUse", "PostToolUse"}
        and hook_input.get("tool_name") == "apply_patch"
        and not child_is_target
    )
    observe_before = (
        (child_is_target and event in {"SubagentStart", "PreToolUse", "PreCompact", "SubagentStop"})
        or is_target_spawn(hook_input, plaintext_agent_types=plaintext_agent_types)
        or (is_parent_writer and event == "PostToolUse")
    )
    if observe_before:
        try:
            record_from_hook(
                store,
                hook_input,
                plaintext_agent_types=plaintext_agent_types,
                writer_stage="callback_observed" if is_parent_writer else None,
            )
        except UnverifiableHookIdentity:
            pass
    output = dispatch(
        store,
        hook_input,
        plaintext_agent_types=plaintext_agent_types,
    )
    if is_parent_writer and event == "PreToolUse":
        specific = output.get("hookSpecificOutput")
        denied = isinstance(specific, dict) and specific.get("permissionDecision") == "deny"
        try:
            record_from_hook(
                store,
                hook_input,
                plaintext_agent_types=plaintext_agent_types,
                writer_stage="denied" if denied else "authorized",
            )
        except UnverifiableHookIdentity:
            pass
    return output


def run_dispatch(
    store: StateStore,
    hook_input: dict,
    *,
    plaintext_agent_types: set[str],
    pretool_schema_observation_root: Path | None = None,
) -> dict:
    try:
        return dispatch_with_receipts(
            store,
            hook_input,
            plaintext_agent_types=plaintext_agent_types,
            pretool_schema_observation_root=pretool_schema_observation_root,
        )
    except (OSError, StateError) as error:
        return fail_closed_output(hook_input.get("hook_event_name"), error)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument(
        "--plaintext-agent-type",
        action="append",
        required=True,
        dest="plaintext_agent_types",
    )
    parser.add_argument("--pretool-schema-observation-root", type=Path)
    arguments = parser.parse_args()
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        print(f"Hook input was invalid JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(hook_input, dict):
        print("Hook input must be a JSON object.", file=sys.stderr)
        return 2
    output = run_dispatch(
        StateStore(arguments.state_directory),
        hook_input,
        plaintext_agent_types=set(arguments.plaintext_agent_types),
        pretool_schema_observation_root=arguments.pretool_schema_observation_root,
    )
    json.dump(output, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
