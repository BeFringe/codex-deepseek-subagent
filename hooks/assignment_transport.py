#!/usr/bin/env python3

"""Isolated plaintext-v2 assignment capture and child-claim adapter."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
from typing import Collection, Mapping
import uuid

from compatibility_state import StateError, StateStore, capsule_sha256, canonical_json, sha256_bytes
from compatibility_state import compact_invariant
from runtime_guard import GuardError, _git, child_identity_from_hook, collect_git_snapshot, read_session_meta


AUTHORITY_RE = re.compile(
    r"(?:\A|\n)BEGIN CODEX WORKER AUTHORITY\n(\{.*\})\nEND CODEX WORKER AUTHORITY\s*\Z",
    re.DOTALL,
)
AUTHORITY_FIELDS = {
    "schema",
    "owned_paths",
    "excluded_paths",
    "git_authority",
    "stop_condition",
    "verification",
    "authority_provenance",
    "ttl_seconds",
}
GIT_AUTHORITY_FIELDS = {"stage", "commit", "branch", "push"}
TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"TASK.HANDOFF_BLOCKED: {reason}",
        }
    }


def parse_authority_declaration(message: object) -> dict:
    if not isinstance(message, str) or not message.strip():
        raise GuardError("spawn message must be a non-empty string")
    if message.count("BEGIN CODEX WORKER AUTHORITY") != 1:
        raise GuardError("spawn message must contain exactly one authority declaration")
    match = AUTHORITY_RE.search(message)
    if match is None:
        raise GuardError("authority declaration must terminate the spawn message")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise GuardError("authority declaration is invalid JSON") from error
    if not isinstance(value, dict) or set(value) != AUTHORITY_FIELDS:
        raise GuardError("authority declaration fields are not exact")
    if value.get("schema") != 1:
        raise GuardError("authority declaration schema is invalid")
    ttl_seconds = value.get("ttl_seconds")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
        raise GuardError("authority ttl_seconds must be between 1 and 3600")
    for field in ("owned_paths", "excluded_paths", "verification"):
        items = value.get(field)
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise GuardError(f"authority {field} must contain only strings")
    if any(not item.strip() for item in value["verification"]):
        raise GuardError("authority verification entries must not be blank")
    if not isinstance(value.get("stop_condition"), str) or not value["stop_condition"].strip():
        raise GuardError("authority stop_condition must be a non-empty string")
    git_authority = value.get("git_authority")
    if not isinstance(git_authority, dict) or set(git_authority) != GIT_AUTHORITY_FIELDS:
        raise GuardError("authority git_authority fields are not exact")
    if any(type(git_authority[field]) is not bool for field in GIT_AUTHORITY_FIELDS):
        raise GuardError("authority Git permissions must be boolean")
    provenance = value.get("authority_provenance")
    if not isinstance(provenance, dict):
        raise GuardError("authority authority_provenance must be an object")
    return value


def _preexisting_dirty(root: Path, snapshot: Mapping[str, object]) -> list[dict]:
    entries = []
    for item in snapshot["changed_paths"]:
        status = _git(
            root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            item["path"],
        ).decode("utf-8")
        if not status:
            raise GuardError(f"Git status omitted changed path: {item['path']}")
        entries.append(
            {
                "path": item["path"],
                "status": status,
                "kind": item["kind"],
                "sha256": item["sha256"],
            }
        )
    return entries


def _parent_runtime_identity(hook_input: Mapping[str, object]) -> tuple[dict, str]:
    transcript_path = hook_input.get("transcript_path")
    if not isinstance(transcript_path, str):
        raise GuardError("spawn hook has no parent transcript_path")
    meta = read_session_meta(transcript_path, require_child_fields=False)
    session_id = hook_input.get("session_id")
    if session_id != meta["session_id"]:
        raise GuardError("spawn Hook session_id does not match parent SessionMeta.session_id")
    hook_agent_id = hook_input.get("agent_id")
    if hook_agent_id is not None and hook_agent_id != meta["id"]:
        raise GuardError("spawn Hook agent_id does not match parent SessionMeta.id")
    parent_path = meta.get("agent_path")
    if not isinstance(parent_path, str) or not parent_path:
        if meta.get("parent_thread_id") is not None:
            raise GuardError("nested parent SessionMeta has no canonical AgentPath")
        parent_path = "/root"
    return meta, parent_path.rstrip("/")


def capture_spawn(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    plaintext_agent_types: Collection[str],
    now: dt.datetime | None = None,
) -> dict:
    if hook_input.get("hook_event_name") != "PreToolUse":
        return {}
    if hook_input.get("tool_name") != "spawn_agent":
        return {}
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        return _deny("spawn tool_input must be an object")
    agent_type = tool_input.get("agent_type")
    if agent_type not in plaintext_agent_types:
        return {}
    try:
        message = tool_input.get("message")
        declaration = parse_authority_declaration(message)
        requested_task_name = tool_input.get("task_name")
        if not isinstance(requested_task_name, str) or not TASK_NAME_RE.fullmatch(
            requested_task_name
        ):
            raise GuardError("task_name must use lowercase letters, digits, and underscores")
        if tool_input.get("fork_turns") != "none":
            raise GuardError("plaintext-v2 spawn requires fork_turns=none")
        parent_meta, parent_path = _parent_runtime_identity(hook_input)
        cwd = hook_input.get("cwd")
        if not isinstance(cwd, str):
            raise GuardError("spawn Hook has no cwd")
        snapshot = collect_git_snapshot(cwd)
        created_at = now or dt.datetime.now(dt.timezone.utc)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise GuardError("capture time must include a UTC offset")
        assignment_id = str(uuid.uuid4())
        handoff_id = str(uuid.uuid4())
        git_authority = declaration["git_authority"]
        capsule = {
            "schema": 2,
            "assignment_id": assignment_id,
            "handoff_id": handoff_id,
            "runtime_session_id": str(hook_input["session_id"]),
            "parent_thread_id": parent_meta["id"],
            "parent_turn_id": str(hook_input.get("turn_id") or ""),
            "spawn_tool_use_id": str(hook_input.get("tool_use_id") or ""),
            "worker_profile": str(agent_type),
            "agent_type": str(agent_type),
            "requested_task_name": requested_task_name,
            "canonical_agent_path": f"{parent_path}/{requested_task_name}",
            "root": {
                "path": snapshot["root"],
                "branch": snapshot["branch"],
                "base_commit": snapshot["head"],
                "allow_descendant_head": bool(git_authority.get("commit")),
            },
            "owned_paths": declaration["owned_paths"],
            "excluded_paths": declaration["excluded_paths"],
            "git_authority": git_authority,
            "stop_condition": declaration["stop_condition"],
            "verification": declaration["verification"],
            "authority_provenance": declaration["authority_provenance"],
            "preexisting_dirty": _preexisting_dirty(Path(snapshot["root"]), snapshot),
            "assignment_sha256": sha256_bytes(str(message).encode("utf-8")),
            "created_at": created_at.isoformat(),
            "expires_at": (
                created_at + dt.timedelta(seconds=declaration["ttl_seconds"])
            ).isoformat(),
        }
        capsule["capsule_sha256"] = capsule_sha256(capsule)
        store.stage(capsule, str(message))
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    "HANDOFF.STAGED "
                    f"assignment_id={assignment_id} handoff_id={handoff_id}"
                ),
            }
        }
    except (KeyError, StateError, UnicodeDecodeError) as error:
        return _deny(str(error))


def subagent_start(store: StateStore, hook_input: Mapping[str, object]) -> dict:
    try:
        if hook_input.get("hook_event_name") != "SubagentStart":
            raise GuardError("expected a SubagentStart event")
        identity = child_identity_from_hook(hook_input)
        handoff_id, _ = store.claim_unique(identity)
        active = store.activate(handoff_id)
        envelope = store._validated_envelope(active)
        capsule = envelope["capsule"]
        capsule_json = canonical_json(capsule).decode("utf-8")
        invariant_json = canonical_json(compact_invariant(capsule)).decode("utf-8")
        context = (
            "You are an external worker child bound to the immutable authority capsule below. "
            "The complete spawn message remains the assignment source. Re-attest this capsule "
            "after recovery and before final return.\n\n"
            f"BEGIN CODEX WORKER COMPACT INVARIANT\n{invariant_json}\n"
            "END CODEX WORKER COMPACT INVARIANT\n\n"
            f"BEGIN CODEX WORKER CAPSULE\n{capsule_json}\nEND CODEX WORKER CAPSULE\n\n"
            f"BEGIN PARENT ASSIGNMENT\n{envelope['assignment']}\nEND PARENT ASSIGNMENT"
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": context,
            }
        }
    except StateError as error:
        try:
            identity = child_identity_from_hook(hook_input)
            store.record_context_lost(identity, str(error))
        except StateError:
            pass
        return {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": (
                    "TASK.CONTEXT_LOST: runtime could not uniquely bind an authority capsule. "
                    f"Do not call tools or claim completion. Binding error: {error}"
                ),
            }
        }
