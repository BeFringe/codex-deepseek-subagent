#!/usr/bin/env python3

"""Isolated parent/sibling apply-patch writer-lease mediation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import subprocess
from typing import Mapping, Sequence

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


def collect_patch_git_snapshot(
    raw_paths: list[str],
    *,
    cwd: str,
) -> tuple[dict, list[str]]:
    """Bind a patch to the unique Git root containing its resolved targets."""

    canonical_cwd = Path(cwd).resolve()
    first = Path(raw_paths[0])
    first_resolved = (
        first.resolve() if first.is_absolute() else (canonical_cwd / first).resolve()
    )
    probe = first_resolved.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        raise WriterLeaseError("apply_patch target has no existing parent directory")
    snapshot = collect_git_snapshot(str(probe))
    paths = normalize_patch_paths(
        raw_paths,
        cwd=str(canonical_cwd),
        root=snapshot["root"],
    )
    return snapshot, paths


def normalize_parent_non_git_writer_roots(
    roots: Sequence[str | Path],
) -> tuple[Path, ...]:
    normalized: list[Path] = []
    for value in roots:
        root = Path(value)
        if not root.is_absolute():
            raise WriterLeaseError("parent non-Git writer root must be absolute")
        canonical = root.resolve()
        if canonical != root or not canonical.is_dir():
            raise WriterLeaseError(
                "parent non-Git writer root must be an existing canonical directory"
            )
        normalized.append(canonical)
    if len(set(normalized)) != len(normalized):
        raise WriterLeaseError("parent non-Git writer roots contain duplicates")
    for index, root in enumerate(normalized):
        for other in normalized[index + 1 :]:
            if root in other.parents or other in root.parents:
                raise WriterLeaseError("parent non-Git writer roots overlap")
    return tuple(normalized)


def _lexical_absolute_path(raw: str, *, cwd: str) -> Path:
    value = Path(raw)
    joined = value if value.is_absolute() else Path(cwd) / value
    return Path(os.path.abspath(os.fspath(joined)))


def _matching_non_git_root(target: Path, roots: Sequence[Path]) -> Path:
    matches = []
    for root in roots:
        try:
            target.relative_to(root)
        except ValueError:
            continue
        matches.append(root)
    if len(matches) != 1:
        raise WriterLeaseError(
            "apply_patch target is outside the explicit parent non-Git writer ceiling"
        )
    return matches[0]


def _reject_git_control_path(root: Path, target: Path) -> None:
    relative = target.relative_to(root)
    if relative == Path("."):
        raise WriterLeaseError("non-Git writer target cannot be the ceiling root")
    if ".git" in relative.parts:
        raise WriterLeaseError("non-Git writer path enters Git control state")
    cursor = target.parent
    while True:
        git_entry = cursor / ".git"
        if git_entry.exists() or git_entry.is_symlink():
            raise WriterLeaseError(
                "Git discovery failed inside a Git-marked non-Git writer path"
            )
        if cursor == root:
            return
        if root not in cursor.parents:
            raise WriterLeaseError("non-Git writer target escapes its ceiling root")
        cursor = cursor.parent


def _non_git_file_state(root: Path, target: Path) -> dict:
    relative = target.relative_to(root)
    cursor = root
    components = relative.parts
    for component in components[:-1]:
        cursor = cursor / component
        try:
            status = cursor.lstat()
        except FileNotFoundError as error:
            raise WriterLeaseError(
                "non-Git writer target has no existing parent directory"
            ) from error
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
            raise WriterLeaseError(
                "non-Git writer target traverses a symlink or non-directory"
            )
    try:
        target_status = target.lstat()
    except FileNotFoundError:
        return {
            "path": relative.as_posix(),
            "kind": "missing",
            "sha256": None,
            "byte_length": None,
        }
    if stat.S_ISLNK(target_status.st_mode) or not stat.S_ISREG(target_status.st_mode):
        raise WriterLeaseError("non-Git writer target is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as error:
        raise WriterLeaseError("non-Git writer target could not be opened safely") from error
    digest = hashlib.sha256()
    length = 0
    try:
        opened_status = os.fstat(descriptor)
        if not stat.S_ISREG(opened_status.st_mode):
            raise WriterLeaseError("non-Git writer target changed file kind")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            length += len(chunk)
    finally:
        os.close(descriptor)
    return {
        "path": relative.as_posix(),
        "kind": "file",
        "sha256": digest.hexdigest(),
        "byte_length": length,
    }


def collect_patch_non_git_snapshot(
    raw_paths: list[str],
    *,
    cwd: str,
    parent_non_git_writer_roots: Sequence[str | Path],
) -> tuple[dict, list[str]]:
    roots = normalize_parent_non_git_writer_roots(parent_non_git_writer_roots)
    if not roots:
        raise WriterLeaseError("no parent non-Git writer root is configured")
    targets = [_lexical_absolute_path(raw, cwd=cwd) for raw in raw_paths]
    selected_roots = [_matching_non_git_root(target, roots) for target in targets]
    root = selected_roots[0]
    if any(candidate != root for candidate in selected_roots[1:]):
        raise WriterLeaseError("apply_patch targets span non-Git writer roots")
    states = []
    for target in targets:
        _reject_git_control_path(root, target)
        states.append(_non_git_file_state(root, target))
    paths = [state["path"] for state in states]
    if len(set(paths)) != len(paths):
        raise WriterLeaseError("apply_patch aliases resolve to the same non-Git path")
    return {
        "schema": 1,
        "surface": "non_git_filesystem",
        "root": str(root),
        "path_states": states,
    }, paths


def _git_worktree_contains_target(raw_path: str, *, cwd: str) -> bool:
    target = _lexical_absolute_path(raw_path, cwd=cwd)
    probe = target.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        raise WriterLeaseError("apply_patch target has no existing parent directory")
    try:
        result = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as error:
        raise WriterLeaseError("Git root discovery could not run") from error
    return result.returncode == 0


def collect_patch_writer_snapshot(
    raw_paths: list[str],
    *,
    cwd: str,
    parent_non_git_writer_roots: Sequence[str | Path],
    allow_non_git: bool,
) -> tuple[str, dict, list[str]]:
    if _git_worktree_contains_target(raw_paths[0], cwd=cwd):
        snapshot, paths = collect_patch_git_snapshot(raw_paths, cwd=cwd)
        return "git", snapshot, paths
    if not allow_non_git:
        raise WriterLeaseError("non-Git writer ceiling is root-parent only")
    snapshot, paths = collect_patch_non_git_snapshot(
        raw_paths,
        cwd=cwd,
        parent_non_git_writer_roots=parent_non_git_writer_roots,
    )
    return "non_git_filesystem", snapshot, paths


def pre_tool_use(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    parent_non_git_writer_roots: Sequence[str | Path] = (),
) -> dict:
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
        raw_paths = extract_apply_patch_paths(tool_input["command"])
        surface, snapshot, paths = collect_patch_writer_snapshot(
            raw_paths,
            cwd=cwd,
            parent_non_git_writer_roots=parent_non_git_writer_roots,
            allow_non_git=(
                actor["canonical_agent_path"] == "/root"
                and actor["agent_type"] == "root"
                and actor["runtime_session_id"] == actor["thread_id"]
            ),
        )
        if surface == "git":
            claim = store.acquire_writer_claim(
                actor,
                root=snapshot["root"],
                paths=paths,
                tool_name="apply_patch",
                tool_use_id=tool_use_id,
                before_snapshot=snapshot,
            )
        else:
            claim = store.acquire_non_git_writer_claim(
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
                "additionalContext": (
                    f"WRITER.LEASED claim_id={claim.stem} surface={surface}"
                ),
            }
        }
    except StateError as error:
        return _deny(str(error))


def post_tool_use(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    parent_non_git_writer_roots: Sequence[str | Path] = (),
) -> dict:
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
        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict) or set(tool_input) != {"command"}:
            raise WriterLeaseError("apply_patch PostToolUse input fields are not exact")
        raw_paths = extract_apply_patch_paths(tool_input["command"])
        surface, snapshot, _ = collect_patch_writer_snapshot(
            raw_paths,
            cwd=cwd,
            parent_non_git_writer_roots=parent_non_git_writer_roots,
            allow_non_git=(
                actor["canonical_agent_path"] == "/root"
                and actor["agent_type"] == "root"
                and actor["runtime_session_id"] == actor["thread_id"]
            ),
        )
        if surface == "git":
            store.release_writer_claim(
                actor,
                tool_name="apply_patch",
                tool_use_id=tool_use_id,
                after_snapshot=snapshot,
            )
        else:
            store.release_non_git_writer_claim(
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
