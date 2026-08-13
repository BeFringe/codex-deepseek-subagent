#!/usr/bin/env python3

"""Isolated Phase 1 runtime-identity and final-attestation fixtures."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Mapping

from compatibility_state import (
    AuthorityViolation,
    compact_invariant,
    compact_invariant_sha256,
    IdentityMismatch,
    MissingState,
    provenance_policy_sha256,
    StateError,
    StateStore,
)


MAX_SESSION_META_LINE = 1024 * 1024
ATTESTATION_RE = re.compile(
    r"\ABEGIN CODEX WORKER ATTESTATION\n(\{.*\})\nEND CODEX WORKER ATTESTATION\Z",
    re.DOTALL,
)
READ_ONLY_TOOL_NAMES = {
    "current_time",
    "get_context_remaining",
    "list_agents",
    "list_mcp_resource_templates",
    "list_mcp_resources",
    "read_mcp_resource",
    "tool_search",
    "view_image",
}


class GuardError(StateError):
    pass


def read_session_meta(transcript_path: str, *, require_child_fields: bool = True) -> dict:
    path = Path(transcript_path)
    if not path.is_absolute():
        raise IdentityMismatch("transcript_path must be absolute")
    try:
        with path.open("rb") as stream:
            line = stream.readline(MAX_SESSION_META_LINE + 1)
    except OSError as error:
        raise IdentityMismatch("child SessionMeta is unavailable") from error
    if not line or len(line) > MAX_SESSION_META_LINE or not line.endswith(b"\n"):
        raise IdentityMismatch("child SessionMeta line is missing or unbounded")
    try:
        item = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IdentityMismatch("child SessionMeta line is invalid") from error
    if not isinstance(item, dict) or item.get("type") != "session_meta":
        raise IdentityMismatch("the first rollout record is not SessionMeta")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        raise IdentityMismatch("SessionMeta payload is invalid")
    required = ("session_id", "id")
    if require_child_fields:
        required += ("parent_thread_id", "agent_role", "agent_path")
    if any(not isinstance(payload.get(field), str) or not payload[field] for field in required):
        raise IdentityMismatch("SessionMeta lacks child identity fields")
    return payload


def child_identity_from_hook(hook_input: Mapping[str, object]) -> dict[str, str]:
    event_name = hook_input.get("hook_event_name")
    if event_name not in {"SubagentStart", "PreToolUse", "PreCompact", "PostCompact"}:
        raise IdentityMismatch("hook event does not carry direct child identity")
    transcript_path = hook_input.get("transcript_path")
    if not isinstance(transcript_path, str):
        raise IdentityMismatch("hook input has no child transcript_path")
    meta = read_session_meta(transcript_path)
    session_id = hook_input.get("session_id")
    agent_id = hook_input.get("agent_id")
    agent_type = hook_input.get("agent_type")
    if session_id != meta["session_id"]:
        raise IdentityMismatch("Hook session_id does not match SessionMeta.session_id")
    if agent_id != meta["id"]:
        raise IdentityMismatch("Hook agent_id does not match SessionMeta.id")
    if agent_type != meta["agent_role"]:
        raise IdentityMismatch("Hook agent_type does not match SessionMeta.agent_role")
    return {
        "runtime_session_id": str(session_id),
        "child_thread_id": str(agent_id),
        "agent_id": str(agent_id),
        "parent_thread_id": meta["parent_thread_id"],
        "agent_type": str(agent_type),
        "canonical_agent_path": meta["agent_path"],
    }


def child_identity_from_stop(hook_input: Mapping[str, object]) -> dict[str, str]:
    if hook_input.get("hook_event_name") != "SubagentStop":
        raise IdentityMismatch("expected a SubagentStop event")
    transcript_path = hook_input.get("agent_transcript_path")
    if not isinstance(transcript_path, str):
        raise IdentityMismatch("SubagentStop has no child transcript path")
    meta = read_session_meta(transcript_path)
    runtime_session_id = hook_input.get("session_id")
    agent_id = hook_input.get("agent_id")
    agent_type = hook_input.get("agent_type")
    if agent_id != meta["id"]:
        raise IdentityMismatch("SubagentStop agent_id does not match SessionMeta.id")
    if runtime_session_id != meta["session_id"]:
        raise IdentityMismatch("SubagentStop session does not match child SessionMeta.session_id")
    if agent_type != meta["agent_role"]:
        raise IdentityMismatch("SubagentStop role does not match SessionMeta.agent_role")
    parent_transcript = hook_input.get("transcript_path")
    if not isinstance(parent_transcript, str):
        raise IdentityMismatch("SubagentStop has no parent transcript path")
    parent_meta = read_session_meta(parent_transcript, require_child_fields=False)
    if parent_meta["session_id"] != runtime_session_id:
        raise IdentityMismatch("parent and child runtime sessions do not match")
    if parent_meta["id"] != meta["parent_thread_id"]:
        raise IdentityMismatch("stopping thread is not the direct parent")
    return {
        "runtime_session_id": meta["session_id"],
        "child_thread_id": meta["id"],
        "agent_id": meta["id"],
        "parent_thread_id": meta["parent_thread_id"],
        "agent_type": meta["agent_role"],
        "canonical_agent_path": meta["agent_path"],
    }


def pre_tool_use(store: StateStore, hook_input: Mapping[str, object]) -> dict:
    try:
        if hook_input.get("hook_event_name") != "PreToolUse":
            raise GuardError("expected a PreToolUse event")
        identity = child_identity_from_hook(hook_input)
        assignment_id, envelope = store.find_active(identity)
        tool_name = hook_input.get("tool_name")
        if tool_name not in READ_ONLY_TOOL_NAMES:
            raise AuthorityViolation(
                f"tool {tool_name!r} is not in the qualified read-only allowlist"
            )
        capsule = envelope["capsule"]
        cwd = hook_input.get("cwd")
        if not isinstance(cwd, str):
            raise GuardError("PreToolUse has no cwd")
        snapshot = collect_git_snapshot(cwd)
        violations = _snapshot_authority_violations(snapshot, capsule)
        if violations:
            raise AuthorityViolation("; ".join(violations))
        store.attest_tool_use(
            assignment_id,
            identity,
            root=snapshot["root"],
            branch=snapshot["branch"],
            head=snapshot["head"],
        )
        recovery_count = envelope["runtime"]["recovery_count"]
        context = (
            "AUTHORITY.REATTESTED "
            f"assignment_id={assignment_id} "
            f"capsule_sha256={capsule['capsule_sha256']} "
            f"recovery_count={recovery_count}\n"
            "BEGIN CODEX WORKER COMPACT INVARIANT\n"
            f"{json.dumps(compact_invariant(capsule), ensure_ascii=False, separators=(',', ':'), sort_keys=True)}\n"
            "END CODEX WORKER COMPACT INVARIANT\n"
            "BEGIN CODEX WORKER CAPSULE\n"
            f"{json.dumps(capsule, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}\n"
            "END CODEX WORKER CAPSULE\n"
            "BEGIN PARENT ASSIGNMENT\n"
            f"{envelope['assignment']}\n"
            "END PARENT ASSIGNMENT"
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": context,
            }
        }
    except StateError as error:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"TASK.AUTHORITY_BLOCKED: {error}",
            }
        }


def pre_compact(store: StateStore, hook_input: Mapping[str, object]) -> dict:
    identity = child_identity_from_hook(hook_input)
    assignment_id, _ = store.find_active(identity)
    store.mark_recovery(assignment_id)
    return {}


def parse_attestation(message: object) -> dict:
    if not isinstance(message, str):
        raise GuardError("final message has no attestation")
    match = ATTESTATION_RE.fullmatch(message.strip())
    if match is None:
        raise GuardError("final message must contain only the attestation envelope")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise GuardError("final attestation is invalid JSON") from error
    if not isinstance(value, dict):
        raise GuardError("final attestation must be a JSON object")
    required = {
        "assignment_id",
        "handoff_id",
        "capsule_sha256",
        "compact_invariant_sha256",
        "authority_provenance",
        "canonical_agent_path",
        "recovery_count",
        "context_lost",
        "root",
        "branch",
        "head",
        "index_changed",
        "git_status_short",
        "changed_paths",
        "verification",
        "authority_violation",
        "assigned_slice_complete",
    }
    if set(value) != required:
        raise GuardError("final attestation fields are not exact")
    if type(value["recovery_count"]) is not int or value["recovery_count"] < 0:
        raise GuardError("recovery_count must be a non-negative integer")
    for field in (
        "context_lost",
        "index_changed",
        "authority_violation",
        "assigned_slice_complete",
    ):
        if type(value[field]) is not bool:
            raise GuardError(f"{field} must be boolean")
    if not isinstance(value["changed_paths"], list) or not isinstance(value["verification"], list):
        raise GuardError("changed_paths and verification must be lists")
    provenance = value["authority_provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {
        "policy_sha256",
        "worker_claimed_origin",
        "test_only_injection_used",
        "derivation_receipt_sha256",
    }:
        raise GuardError("final authority_provenance fields are not exact")
    if provenance["worker_claimed_origin"] not in {"owner_internal", "caller", "unknown"}:
        raise GuardError("worker_claimed_origin is invalid")
    if type(provenance["test_only_injection_used"]) is not bool:
        raise GuardError("test_only_injection_used must be boolean")
    receipt_sha256 = provenance["derivation_receipt_sha256"]
    if receipt_sha256 is not None and (
        not isinstance(receipt_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256)
    ):
        raise GuardError("derivation_receipt_sha256 is invalid")
    return value


def _git(root: Path, *arguments: str, allow_code_one: bool = False) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0 or allow_code_one and result.returncode == 1:
        return result.stdout
    raise GuardError(f"Git snapshot command failed: {' '.join(arguments)}")


def collect_git_snapshot(root_value: str) -> dict:
    cwd = Path(root_value).resolve()
    root = Path(_git(cwd, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    branch_bytes = _git(root, "symbolic-ref", "--short", "-q", "HEAD", allow_code_one=True)
    branch = branch_bytes.decode("utf-8").strip() or None
    status = _git(root, "status", "--short", "--untracked-files=all").decode("utf-8").rstrip("\n")
    index_result = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--quiet", "--exit-code", "--"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if index_result.returncode not in {0, 1}:
        raise GuardError("Git index snapshot failed")
    tracked = _git(root, "diff", "--name-only", "-z", "HEAD", "--")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    try:
        paths = {
            item.decode("utf-8")
            for item in (tracked + untracked).split(b"\0")
            if item
        }
    except UnicodeDecodeError as error:
        raise GuardError("changed path is not valid UTF-8") from error
    changed_paths = []
    for relative in sorted(paths):
        path = root / relative
        if path.is_symlink():
            content = os.readlink(path).encode("utf-8")
            kind = "symlink"
            digest = hashlib.sha256(content).hexdigest()
        elif path.is_file():
            kind = "file"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        elif not path.exists():
            kind = "deleted"
            digest = None
        else:
            raise GuardError(f"unsupported changed path kind: {relative}")
        changed_paths.append({"path": relative, "kind": kind, "sha256": digest})
    return {
        "root": str(root),
        "branch": branch,
        "head": head,
        "index_changed": index_result.returncode == 1,
        "git_status_short": status,
        "changed_paths": changed_paths,
    }


def _snapshot_authority_violations(
    snapshot: Mapping[str, object], capsule: Mapping[str, object]
) -> list[str]:
    violations: list[str] = []
    expected_root = capsule["root"]
    if snapshot["root"] != str(Path(expected_root["path"]).resolve()):
        violations.append("final root does not match the capsule")
    if snapshot["branch"] != expected_root["branch"]:
        violations.append("final branch does not match the capsule")
    if not expected_root["allow_descendant_head"] and snapshot["head"] != expected_root["base_commit"]:
        violations.append("final HEAD changed without authority")
    if snapshot["index_changed"] and not capsule["git_authority"]["stage"]:
        violations.append("final Git index changed without stage authority")
    owned = capsule["owned_paths"]
    excluded = capsule["excluded_paths"]
    preexisting = {
        item["path"]: (item["kind"], item["sha256"])
        for item in capsule["preexisting_dirty"]
    }
    for item in snapshot["changed_paths"]:
        path = item["path"]
        in_owned = any(path == owner or path.startswith(owner + "/") for owner in owned)
        in_excluded = any(path == excluded_path or path.startswith(excluded_path + "/") for excluded_path in excluded)
        unchanged_preexisting = preexisting.get(path) == (item["kind"], item["sha256"])
        if (not in_owned or in_excluded) and not unchanged_preexisting:
            violations.append(f"final disk contains unauthorized change: {path}")
    return violations


def subagent_stop(store: StateStore, hook_input: Mapping[str, object]) -> dict:
    try:
        identity = child_identity_from_stop(hook_input)
        try:
            assignment_id, envelope = store.find_active(identity)
        except MissingState:
            lost = store.context_lost_for(identity)
            message = hook_input.get("last_assistant_message")
            if lost is not None and isinstance(message, str) and message.strip() == "TASK.CONTEXT_LOST":
                return {}
            raise
        capsule = envelope["capsule"]
        attestation = parse_attestation(hook_input.get("last_assistant_message"))
        snapshot = collect_git_snapshot(capsule["root"]["path"])
        violations = _snapshot_authority_violations(snapshot, capsule)
        expected = {
            "assignment_id": assignment_id,
            "handoff_id": capsule["handoff_id"],
            "capsule_sha256": capsule["capsule_sha256"],
            "compact_invariant_sha256": compact_invariant_sha256(capsule),
            "canonical_agent_path": identity["canonical_agent_path"],
            "recovery_count": envelope["runtime"]["recovery_count"],
            **snapshot,
            "authority_violation": bool(violations),
        }
        for field, expected_value in expected.items():
            if attestation.get(field) != expected_value:
                raise GuardError(f"final attestation mismatch: {field}")
        if attestation["context_lost"] and attestation["assigned_slice_complete"]:
            raise GuardError("context-lost return cannot claim the assigned slice complete")
        if violations and attestation["assigned_slice_complete"]:
            raise GuardError("authority-violating return cannot claim the assigned slice complete")
        provenance = attestation["authority_provenance"]
        if provenance["policy_sha256"] != provenance_policy_sha256(capsule):
            raise GuardError("final authority provenance policy hash does not match")
        if attestation["assigned_slice_complete"] and (
            provenance["worker_claimed_origin"] != "owner_internal"
            or provenance["test_only_injection_used"]
        ):
            raise GuardError("complete return has an inadmissible provenance claim")
        if any(
            not isinstance(item, dict)
            or set(item) != {"command", "exit_code"}
            or not isinstance(item["command"], str)
            or type(item["exit_code"]) is not int
            for item in attestation["verification"]
        ):
            raise GuardError("verification records are invalid")
        if [item["command"] for item in attestation["verification"]] != capsule["verification"]:
            raise GuardError("verification commands do not match the capsule contract")
        complete = (
            attestation["assigned_slice_complete"]
            and not attestation["context_lost"]
            and not violations
        )
        if complete and any(item["exit_code"] != 0 for item in attestation["verification"]):
            raise GuardError("complete return includes failed verification")
        store.finalize(assignment_id, attestation, complete=complete)
        return {}
    except StateError as error:
        return {
            "decision": "block",
            "reason": (
                "TASK.FINAL_ATTESTATION_REQUIRED: "
                f"{error}. Return only a corrected attestation; set context_lost=true "
                "and assigned_slice_complete=false when authority cannot be recovered."
            ),
        }
