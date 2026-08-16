#!/usr/bin/env python3

"""Isolated parent/sibling apply-patch writer-lease mediation."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from compatibility_state import StateError, StateStore
from runtime_guard import collect_git_snapshot, read_session_meta


class WriterLeaseError(StateError):
    pass


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"TASK.WRITER_LEASE_BLOCKED: {reason}",
        }
    }


def actor_identity_from_hook(hook_input: Mapping[str, object]) -> dict[str, str]:
    transcript_path = hook_input.get("transcript_path")
    if not isinstance(transcript_path, str):
        raise WriterLeaseError("writer Hook has no transcript_path")
    meta = read_session_meta(transcript_path, require_child_fields=False)
    session_id = hook_input.get("session_id")
    if session_id != meta["session_id"]:
        raise WriterLeaseError("writer Hook session does not match SessionMeta")
    hook_agent_id = hook_input.get("agent_id")
    if hook_agent_id is not None and hook_agent_id != meta["id"]:
        raise WriterLeaseError("writer Hook agent id does not match SessionMeta")
    hook_agent_type = hook_input.get("agent_type")
    meta_agent_type = meta.get("agent_role")
    if hook_agent_type is not None and hook_agent_type != meta_agent_type:
        raise WriterLeaseError("writer Hook agent type does not match SessionMeta")
    parent_thread_id = meta.get("parent_thread_id")
    canonical_path = meta.get("agent_path")
    if parent_thread_id is None:
        if canonical_path is None:
            canonical_path = "/root"
        if meta["id"] != session_id or hook_agent_id is not None:
            raise WriterLeaseError("root writer identity does not match SessionMeta")
    elif not isinstance(canonical_path, str) or not canonical_path:
        raise WriterLeaseError("nested writer SessionMeta has no canonical AgentPath")
    elif hook_agent_id is None or hook_agent_type != meta_agent_type:
        raise WriterLeaseError("nested writer Hook lacks exact SessionMeta identity")
    if not isinstance(canonical_path, str) or not canonical_path.startswith("/"):
        raise WriterLeaseError("writer canonical AgentPath is invalid")
    agent_type = meta_agent_type if isinstance(meta_agent_type, str) else "root"
    return {
        "runtime_session_id": session_id,
        "thread_id": meta["id"],
        "agent_type": agent_type,
        "canonical_agent_path": canonical_path,
    }


def extract_apply_patch_paths(command: object) -> list[str]:
    if not isinstance(command, str) or not command:
        raise WriterLeaseError("apply_patch command is missing")
    lines = command.splitlines()
    if len(lines) < 3 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise WriterLeaseError("apply_patch envelope is not exact")
    paths: list[str] = []
    prefixes = (
        "*** Add File: ",
        "*** Delete File: ",
        "*** Update File: ",
        "*** Move to: ",
    )
    for line in lines[1:-1]:
        for prefix in prefixes:
            if line.startswith(prefix):
                path = line[len(prefix) :]
                if not path or path != path.strip() or "\x00" in path or "\\" in path:
                    raise WriterLeaseError("apply_patch contains an invalid path")
                paths.append(path)
                break
    if not paths:
        raise WriterLeaseError("apply_patch contains no file action")
    if len(set(paths)) != len(paths):
        raise WriterLeaseError("apply_patch contains duplicate file actions")
    return paths


def normalize_patch_paths(
    raw_paths: list[str],
    *,
    cwd: str,
    root: str,
) -> list[str]:
    canonical_root = Path(root).resolve()
    canonical_cwd = Path(cwd).resolve()
    try:
        canonical_cwd.relative_to(canonical_root)
    except ValueError as error:
        raise WriterLeaseError("writer cwd is outside the Git root") from error
    normalized: list[str] = []
    for raw in raw_paths:
        candidate = Path(raw)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (canonical_cwd / candidate).resolve()
        )
        try:
            relative = resolved.relative_to(canonical_root)
        except ValueError as error:
            raise WriterLeaseError("apply_patch path escapes the Git root") from error
        value = relative.as_posix()
        if value in {"", "."} or ".." in relative.parts:
            raise WriterLeaseError("apply_patch path is not canonical")
        normalized.append(value)
    if len(set(normalized)) != len(normalized):
        raise WriterLeaseError("apply_patch aliases resolve to the same path")
    return normalized


def pre_tool_use(store: StateStore, hook_input: Mapping[str, object]) -> dict:
    if hook_input.get("hook_event_name") != "PreToolUse":
        return {}
    if hook_input.get("tool_name") != "apply_patch":
        return {}
    try:
        actor = actor_identity_from_hook(hook_input)
        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict) or set(tool_input) != {"command"}:
            raise WriterLeaseError("apply_patch tool_input fields are not exact")
        cwd = hook_input.get("cwd")
        if not isinstance(cwd, str):
            raise WriterLeaseError("apply_patch Hook has no cwd")
        tool_use_id = hook_input.get("tool_use_id")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            raise WriterLeaseError("apply_patch Hook has no tool_use_id")
        snapshot = collect_git_snapshot(cwd)
        raw_paths = extract_apply_patch_paths(tool_input["command"])
        paths = normalize_patch_paths(
            raw_paths,
            cwd=cwd,
            root=snapshot["root"],
        )
        claim = store.acquire_writer_claim(
            actor,
            root=snapshot["root"],
            paths=paths,
            tool_name="apply_patch",
            tool_use_id=tool_use_id,
            before_snapshot=snapshot,
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"WRITER.LEASED claim_id={claim.stem}",
            }
        }
    except StateError as error:
        return _deny(str(error))


def post_tool_use(store: StateStore, hook_input: Mapping[str, object]) -> dict:
    if hook_input.get("hook_event_name") != "PostToolUse":
        return {}
    if hook_input.get("tool_name") != "apply_patch":
        return {}
    try:
        actor = actor_identity_from_hook(hook_input)
        cwd = hook_input.get("cwd")
        if not isinstance(cwd, str):
            raise WriterLeaseError("apply_patch PostToolUse has no cwd")
        tool_use_id = hook_input.get("tool_use_id")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            raise WriterLeaseError("apply_patch PostToolUse has no tool_use_id")
        snapshot = collect_git_snapshot(cwd)
        store.release_writer_claim(
            actor,
            tool_name="apply_patch",
            tool_use_id=tool_use_id,
            after_snapshot=snapshot,
        )
        return {}
    except StateError as error:
        reason = f"TASK.WRITER_LEASE_UNRESOLVED: {error}"
        return {
            "continue": False,
            "stopReason": reason,
            "systemMessage": reason,
        }
