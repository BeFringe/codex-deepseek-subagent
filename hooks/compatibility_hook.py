#!/usr/bin/env python3

"""Isolated multi-event Hook entry point for Phase 1 qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Mapping, Sequence

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


SANDBOX_PROBE_TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")
SANDBOX_PROBE_ROOT = Path("/private/tmp")
WRITER_LEASE_CONTEXT_RE = re.compile(
    r"(?:^|\n)WRITER\.LEASED claim_id=([0-9a-f-]{36}) surface=git(?:\n|$)"
)


def child_sandbox_probe_spec(value: str) -> tuple[str, Path]:
    task_name, separator, raw_path = value.partition("=")
    if not separator or not SANDBOX_PROBE_TASK_NAME_RE.fullmatch(task_name):
        raise argparse.ArgumentTypeError(
            "child sandbox probe must be task_name=/private/tmp/direct-child"
        )
    target = Path(raw_path)
    try:
        root = SANDBOX_PROBE_ROOT.resolve(strict=True)
        parent = target.parent.resolve(strict=True)
    except OSError as error:
        raise argparse.ArgumentTypeError(
            "child sandbox probe parent is unavailable"
        ) from error
    if not target.is_absolute() or parent != root or target.resolve(strict=False) != target:
        raise argparse.ArgumentTypeError(
            "child sandbox probe must target one canonical direct /private/tmp child"
        )
    return task_name, target


def child_write_probe_spec(value: str) -> tuple[str, Path]:
    task_name, separator, raw_path = value.partition("=")
    if not separator or not SANDBOX_PROBE_TASK_NAME_RE.fullmatch(task_name):
        raise argparse.ArgumentTypeError(
            "child write probe must be task_name=/private/tmp/direct-git-root/file"
        )
    target = Path(raw_path)
    try:
        temporary_root = SANDBOX_PROBE_ROOT.resolve(strict=True)
        git_root = target.parent.resolve(strict=True)
    except OSError as error:
        raise argparse.ArgumentTypeError("child write probe root is unavailable") from error
    if (
        not target.is_absolute()
        or git_root.parent != temporary_root
        or target.resolve(strict=False) != target
    ):
        raise argparse.ArgumentTypeError(
            "child write probe must target one canonical direct child of a temporary root"
        )
    return task_name, target


def qualification_writer_hold_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "qualification writer hold must be an integer"
        ) from error
    if not 1 <= seconds <= 10:
        raise argparse.ArgumentTypeError(
            "qualification writer hold must be between 1 and 10 seconds"
        )
    return seconds


def hold_exact_qualification_writer_lease(
    store: StateStore,
    hook_input: Mapping[str, object],
    output: Mapping[str, object],
    *,
    plaintext_agent_types: set[str],
    child_write_probes: Mapping[str, Path],
    seconds: int,
    sleeper=time.sleep,
) -> bool:
    """Expose one exact live child-lease race window without granting authority."""

    if seconds == 0:
        return False
    if len(child_write_probes) != 1:
        raise StateError("qualification writer hold requires one exact write probe")
    if (
        hook_input.get("hook_event_name") != "PreToolUse"
        or hook_input.get("tool_name") != "apply_patch"
        or hook_input.get("agent_type") not in plaintext_agent_types
    ):
        return False
    specific = output.get("hookSpecificOutput")
    if not isinstance(specific, Mapping):
        return False
    context = specific.get("additionalContext")
    if not isinstance(context, str):
        return False
    match = WRITER_LEASE_CONTEXT_RE.search(context)
    if match is None:
        return False

    task_name, target = next(iter(child_write_probes.items()))
    claim = store.read_writer_claim(match.group(1))
    actor = claim["actor"]
    expected_root = target.parent.resolve()
    if (
        actor["agent_type"] not in plaintext_agent_types
        or actor["canonical_agent_path"].rsplit("/", 1)[-1] != task_name
        or Path(claim["root"]).resolve() != expected_root
        or claim["paths"] != [target.name]
    ):
        raise StateError("qualification writer hold claim identity is not exact")
    sleeper(seconds)
    return True


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
    parent_non_git_writer_roots: Sequence[Path] = (),
    child_sandbox_probes: Mapping[str, Path] | None = None,
    child_write_probes: Mapping[str, Path] | None = None,
    child_handover_write_probes: Mapping[str, Path] | None = None,
) -> dict:
    event = hook_input.get("hook_event_name")
    child_is_target = hook_input.get("agent_type") in plaintext_agent_types
    if event == "PreToolUse":
        if child_is_target:
            authority = pre_tool_use(
                store,
                hook_input,
                qualification_sandbox_probes=child_sandbox_probes,
                qualification_write_probes=child_write_probes,
                qualification_handover_write_probes=child_handover_write_probes,
            )
            specific = authority.get("hookSpecificOutput")
            denied = isinstance(specific, dict) and specific.get("permissionDecision") == "deny"
            if denied or hook_input.get("tool_name") != "apply_patch":
                return authority
            lease = guard_writer_lease(
                store,
                hook_input,
                parent_non_git_writer_roots=parent_non_git_writer_roots,
            )
            lease_specific = lease.get("hookSpecificOutput")
            if isinstance(lease_specific, dict) and lease_specific.get("permissionDecision") == "deny":
                return lease
            authority_context = specific.get("additionalContext") if isinstance(specific, dict) else None
            lease_context = lease_specific.get("additionalContext") if isinstance(lease_specific, dict) else None
            if authority_context and lease_context:
                specific["additionalContext"] = f"{authority_context}\n{lease_context}"
            return authority
        captured = capture_spawn(
            store,
            hook_input,
            plaintext_agent_types=plaintext_agent_types,
            qualification_write_probes=child_write_probes,
            qualification_handover_write_probes=child_handover_write_probes,
        )
        return captured or guard_writer_lease(
            store,
            hook_input,
            parent_non_git_writer_roots=parent_non_git_writer_roots,
        )
    if event == "PostToolUse":
        return release_writer_lease(
            store,
            hook_input,
            parent_non_git_writer_roots=parent_non_git_writer_roots,
            emit_observation_receipt=child_is_target,
        )
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
    parent_non_git_writer_roots: Sequence[Path] = (),
    child_sandbox_probes: Mapping[str, Path] | None = None,
    child_write_probes: Mapping[str, Path] | None = None,
    child_handover_write_probes: Mapping[str, Path] | None = None,
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
        (
            child_is_target
            and event
            in {"SubagentStart", "PreToolUse", "PostToolUse", "PreCompact", "SubagentStop"}
        )
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
        parent_non_git_writer_roots=parent_non_git_writer_roots,
        child_sandbox_probes=child_sandbox_probes,
        child_write_probes=child_write_probes,
        child_handover_write_probes=child_handover_write_probes,
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
    parent_non_git_writer_roots: Sequence[Path] = (),
    child_sandbox_probes: Mapping[str, Path] | None = None,
    child_write_probes: Mapping[str, Path] | None = None,
    child_handover_write_probes: Mapping[str, Path] | None = None,
) -> dict:
    try:
        return dispatch_with_receipts(
            store,
            hook_input,
            plaintext_agent_types=plaintext_agent_types,
            pretool_schema_observation_root=pretool_schema_observation_root,
            parent_non_git_writer_roots=parent_non_git_writer_roots,
            child_sandbox_probes=child_sandbox_probes,
            child_write_probes=child_write_probes,
            child_handover_write_probes=child_handover_write_probes,
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
    parser.add_argument(
        "--parent-non-git-writer-root",
        action="append",
        default=[],
        type=Path,
        dest="parent_non_git_writer_roots",
    )
    parser.add_argument(
        "--child-sandbox-probe",
        action="append",
        default=[],
        type=child_sandbox_probe_spec,
        dest="child_sandbox_probe_specs",
    )
    parser.add_argument(
        "--child-write-probe",
        action="append",
        default=[],
        type=child_write_probe_spec,
        dest="child_write_probe_specs",
    )
    parser.add_argument(
        "--child-handover-write-probe",
        action="append",
        default=[],
        type=child_write_probe_spec,
        dest="child_handover_write_probe_specs",
    )
    parser.add_argument(
        "--qualification-writer-hold-seconds",
        type=qualification_writer_hold_seconds,
        default=0,
    )
    arguments = parser.parse_args()
    child_sandbox_probes: dict[str, Path] = {}
    for task_name, target in arguments.child_sandbox_probe_specs:
        if task_name in child_sandbox_probes:
            parser.error("child sandbox probe task name is duplicated")
        child_sandbox_probes[task_name] = target
    child_write_probes: dict[str, Path] = {}
    for task_name, target in arguments.child_write_probe_specs:
        if task_name in child_write_probes:
            parser.error("child write probe task name is duplicated")
        child_write_probes[task_name] = target
    child_handover_write_probes: dict[str, Path] = {}
    for task_name, target in arguments.child_handover_write_probe_specs:
        if task_name in child_handover_write_probes:
            parser.error("child handover write probe task name is duplicated")
        if task_name in child_write_probes:
            parser.error("write probe task has two qualification ceilings")
        child_handover_write_probes[task_name] = target
    if arguments.qualification_writer_hold_seconds and len(child_write_probes) != 1:
        parser.error("qualification writer hold requires one exact child write probe")
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        print(f"Hook input was invalid JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(hook_input, dict):
        print("Hook input must be a JSON object.", file=sys.stderr)
        return 2
    store = StateStore(arguments.state_directory)
    output = run_dispatch(
        store,
        hook_input,
        plaintext_agent_types=set(arguments.plaintext_agent_types),
        pretool_schema_observation_root=arguments.pretool_schema_observation_root,
        parent_non_git_writer_roots=arguments.parent_non_git_writer_roots,
        child_sandbox_probes=child_sandbox_probes,
        child_write_probes=child_write_probes,
        child_handover_write_probes=child_handover_write_probes,
    )
    try:
        hold_exact_qualification_writer_lease(
            store,
            hook_input,
            output,
            plaintext_agent_types=set(arguments.plaintext_agent_types),
            child_write_probes=child_write_probes,
            seconds=arguments.qualification_writer_hold_seconds,
        )
    except (OSError, StateError) as error:
        output = fail_closed_output(hook_input.get("hook_event_name"), error)
    json.dump(output, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
