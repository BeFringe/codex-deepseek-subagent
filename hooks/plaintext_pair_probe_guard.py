#!/usr/bin/env python3

"""One-shot PreToolUse negative control for the P1 plaintext-pair probe.

This is qualification plumbing, not a production authorization mechanism.  For
each explicitly configured native V2 operation it permits the first distinct
tool-use carrying one exact message fingerprint and denies the second before
handler dispatch.  It never stores the message bytes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Mapping

sys.dont_write_bytecode = True

from compatibility_state import StateError, StateStore, canonical_json, sha256_bytes


OPERATIONS = ("spawn_agent", "send_message", "followup_task")
TOOL_NAMES = {operation: f"g4_assignment{operation}" for operation in OPERATIONS}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STATE_SCHEMA = 1


class ProbeGuardError(StateError):
    pass


def parse_spec(value: str) -> tuple[str, str]:
    operation, separator, digest = value.partition("=")
    if not separator or operation not in OPERATIONS or SHA256_RE.fullmatch(digest) is None:
        raise argparse.ArgumentTypeError("deny-second must be operation=lowercase-sha256")
    return operation, digest


def validate_state_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise ProbeGuardError("qualification state directory must be absolute")
    resolved = path.resolve(strict=False)
    temporary_root = Path("/private/tmp").resolve(strict=True)
    if resolved != path or temporary_root not in resolved.parents:
        raise ProbeGuardError(
            "qualification state directory must be a canonical /private/tmp descendant"
        )
    existing_parent = resolved
    while not existing_parent.exists():
        if existing_parent.parent == existing_parent:
            raise ProbeGuardError("qualification state directory has no existing parent")
        existing_parent = existing_parent.parent
    if existing_parent.resolve(strict=True) != existing_parent:
        raise ProbeGuardError("qualification state directory traverses a symlink")
    return resolved


def validate_specs(specs: list[tuple[str, str]]) -> dict[str, str]:
    configured = dict(specs)
    if len(configured) != len(specs) or set(configured) != set(OPERATIONS):
        raise ProbeGuardError("qualification guard requires one exact spec per operation")
    return configured


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProbeGuardError(f"{field} is missing")
    return value


def _unsigned_state(state: Mapping[str, object]) -> dict:
    value = dict(state)
    value.pop("state_sha256", None)
    return value


def state_sha256(state: Mapping[str, object]) -> str:
    return sha256_bytes(canonical_json(_unsigned_state(state)))


def _new_state(configured: Mapping[str, str]) -> dict:
    state = {
        "schema": STATE_SCHEMA,
        "configured_message_sha256": dict(sorted(configured.items())),
        "calls": {operation: [] for operation in OPERATIONS},
        "raw_plaintext_stored": False,
    }
    state["state_sha256"] = state_sha256(state)
    return state


def _validate_state(value: object, configured: Mapping[str, str]) -> dict:
    if not isinstance(value, dict):
        raise ProbeGuardError("qualification pair state is not an object")
    if set(value) != {
        "schema",
        "configured_message_sha256",
        "calls",
        "raw_plaintext_stored",
        "state_sha256",
    }:
        raise ProbeGuardError("qualification pair state fields are not exact")
    if value.get("schema") != STATE_SCHEMA:
        raise ProbeGuardError("qualification pair state schema is invalid")
    if value.get("configured_message_sha256") != dict(sorted(configured.items())):
        raise ProbeGuardError("qualification pair configuration drifted")
    if value.get("raw_plaintext_stored") is not False:
        raise ProbeGuardError("qualification pair state claims plaintext storage")
    calls = value.get("calls")
    if not isinstance(calls, dict) or set(calls) != set(OPERATIONS):
        raise ProbeGuardError("qualification pair call registry is invalid")
    for operation, entries in calls.items():
        if not isinstance(entries, list) or len(entries) > 2:
            raise ProbeGuardError(f"{operation} qualification call count is invalid")
        tool_ids: set[str] = set()
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict) or set(entry) != {
                "ordinal",
                "decision",
                "observed_at",
                "parent_session_id",
                "parent_turn_id",
                "parent_agent_path",
                "tool_use_id",
                "message_length",
                "message_sha256",
            }:
                raise ProbeGuardError(f"{operation} qualification call fields are not exact")
            if entry["ordinal"] != index or entry["decision"] != (
                "allow" if index == 1 else "deny"
            ):
                raise ProbeGuardError(f"{operation} qualification call order is invalid")
            tool_id = _nonempty(entry["tool_use_id"], "stored tool_use_id")
            if tool_id in tool_ids:
                raise ProbeGuardError(f"{operation} qualification tool-use id is duplicated")
            tool_ids.add(tool_id)
            if entry["message_sha256"] != configured[operation]:
                raise ProbeGuardError(f"{operation} qualification fingerprint drifted")
            if not isinstance(entry["message_length"], int) or entry["message_length"] <= 0:
                raise ProbeGuardError(f"{operation} qualification message length is invalid")
    if value.get("state_sha256") != state_sha256(value):
        raise ProbeGuardError("qualification pair state hash is invalid")
    return value


def _read_state(path: Path, configured: Mapping[str, str]) -> dict:
    if not path.exists():
        return _new_state(configured)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeGuardError("qualification pair state cannot be decoded") from error
    return _validate_state(value, configured)


def run_guard(
    state_directory: Path,
    hook_input: Mapping[str, object],
    configured: Mapping[str, str],
) -> dict:
    if hook_input.get("hook_event_name") != "PreToolUse":
        return {}
    reverse_names = {tool_name: operation for operation, tool_name in TOOL_NAMES.items()}
    operation = reverse_names.get(hook_input.get("tool_name"))
    if operation is None:
        return {}
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        raise ProbeGuardError("qualification pair tool_input is not an object")
    message = tool_input.get("message")
    if not isinstance(message, str) or not message:
        raise ProbeGuardError("qualification pair message is missing")
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
    if digest != configured[operation]:
        return {}

    identity = {
        "parent_session_id": _nonempty(hook_input.get("session_id"), "session_id"),
        "parent_turn_id": _nonempty(hook_input.get("turn_id"), "turn_id"),
        "parent_agent_path": _nonempty(
            hook_input.get("agent_path") or "/root", "agent_path"
        ),
        "tool_use_id": _nonempty(hook_input.get("tool_use_id"), "tool_use_id"),
    }
    store = StateStore(validate_state_directory(state_directory))
    target = store.root / "plaintext_pair_probe" / "state.json"
    with store.locked():
        state = _read_state(target, configured)
        entries = state["calls"][operation]
        for entry in entries:
            if entry["tool_use_id"] == identity["tool_use_id"]:
                decision = entry["decision"]
                break
        else:
            if len(entries) >= 2:
                decision = "deny"
            else:
                decision = "allow" if not entries else "deny"
                entries.append(
                    {
                        "ordinal": len(entries) + 1,
                        "decision": decision,
                        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                        **identity,
                        "message_length": len(message),
                        "message_sha256": digest,
                    }
                )
                state["state_sha256"] = state_sha256(state)
                store._publish(target, state, replace=True)
    if decision == "deny":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "TASK.P1_PLAINTEXT_PAIR_DENY: qualification-only second "
                    f"{operation} call with the exact configured message fingerprint"
                ),
            }
        }
    return {}


def fail_closed(error: BaseException) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"TASK.P1_PLAINTEXT_PAIR_BLOCKED: {error}",
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--deny-second", action="append", type=parse_spec, required=True)
    arguments = parser.parse_args()
    try:
        configured = validate_specs(arguments.deny_second)
        hook_input = json.load(sys.stdin)
        if not isinstance(hook_input, dict):
            raise ProbeGuardError("Hook input must be a JSON object")
        output = run_guard(arguments.state_directory, hook_input, configured)
    except (OSError, StateError, json.JSONDecodeError) as error:
        output = fail_closed(error)
    json.dump(output, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
