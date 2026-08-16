#!/usr/bin/env python3

"""Isolated Phase 1 runtime-identity and final-attestation fixtures."""

from __future__ import annotations

import datetime as dt
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
    registry_items_sha256,
    StateError,
    StateStore,
)


MAX_SESSION_META_LINE = 1024 * 1024
PINNED_CODEX_VERSION = "0.148.0-alpha.9"
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


def _session_meta_timestamp(value: object, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise IdentityMismatch(f"{label} is missing")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise IdentityMismatch(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IdentityMismatch(f"{label} lacks a UTC offset")
    return parsed


def _session_meta_thread_spawn(source: object) -> dict | None:
    if isinstance(source, str) and source:
        return None
    if not isinstance(source, dict) or set(source) != {"subagent"}:
        raise IdentityMismatch("SessionMeta source is invalid")
    subagent = source.get("subagent")
    if not isinstance(subagent, dict) or set(subagent) != {"thread_spawn"}:
        raise IdentityMismatch("SessionMeta subagent source is invalid")
    spawn = subagent.get("thread_spawn")
    fields = {
        "parent_thread_id",
        "depth",
        "agent_path",
        "agent_nickname",
        "agent_role",
    }
    if not isinstance(spawn, dict) or set(spawn) != fields:
        raise IdentityMismatch("SessionMeta thread-spawn source fields are not exact")
    for field in ("parent_thread_id", "agent_path", "agent_role"):
        if not isinstance(spawn.get(field), str) or not spawn[field]:
            raise IdentityMismatch(f"SessionMeta thread-spawn {field} is invalid")
    if type(spawn.get("depth")) is not int or spawn["depth"] < 1:
        raise IdentityMismatch("SessionMeta thread-spawn depth is invalid")
    nickname = spawn.get("agent_nickname")
    if nickname is not None and (not isinstance(nickname, str) or not nickname):
        raise IdentityMismatch("SessionMeta thread-spawn nickname is invalid")
    if not spawn["agent_path"].startswith("/"):
        raise IdentityMismatch("SessionMeta thread-spawn AgentPath is invalid")
    return spawn


def _active_runtime(envelope: Mapping[str, object]) -> dict:
    runtime = envelope.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {
        "recovery_count",
        "context_lost",
        "first_git_attested_at",
    }:
        raise GuardError("active runtime metadata fields are not exact")
    if type(runtime["recovery_count"]) is not int or runtime["recovery_count"] < 0:
        raise GuardError("active recovery_count is invalid")
    if type(runtime["context_lost"]) is not bool:
        raise GuardError("active context_lost is invalid")
    first_attested = runtime["first_git_attested_at"]
    if first_attested is not None:
        if not isinstance(first_attested, str):
            raise GuardError("active first_git_attested_at is invalid")
        try:
            parsed = dt.datetime.fromisoformat(first_attested)
        except ValueError as error:
            raise GuardError("active first_git_attested_at is invalid") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise GuardError("active first_git_attested_at lacks a UTC offset")
    return runtime


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
    record_timestamp = _session_meta_timestamp(
        item.get("timestamp"), "SessionMeta rollout-record timestamp"
    )
    payload = item.get("payload")
    if not isinstance(payload, dict):
        raise IdentityMismatch("SessionMeta payload is invalid")
    for field in ("session_id", "id", "cwd"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise IdentityMismatch(f"SessionMeta {field} is invalid")
    if payload.get("cli_version") != PINNED_CODEX_VERSION:
        raise IdentityMismatch("SessionMeta cli_version is not pinned")
    created_timestamp = _session_meta_timestamp(
        payload.get("timestamp"), "SessionMeta payload timestamp"
    )
    if created_timestamp > record_timestamp:
        raise IdentityMismatch(
            "SessionMeta payload timestamp is later than its rollout record"
        )
    spawn = _session_meta_thread_spawn(payload.get("source"))
    child_fields = {
        "parent_thread_id": payload.get("parent_thread_id"),
        "agent_role": payload.get("agent_role"),
        "agent_path": payload.get("agent_path"),
        "agent_nickname": payload.get("agent_nickname"),
    }
    if spawn is None:
        if any(value is not None for value in child_fields.values()):
            raise IdentityMismatch("root SessionMeta carries child identity fields")
        if require_child_fields:
            raise IdentityMismatch("SessionMeta is not a spawned child")
        payload["agent_depth"] = None
        return payload
    for field in ("parent_thread_id", "agent_role", "agent_path", "agent_nickname"):
        if child_fields[field] != spawn[field]:
            raise IdentityMismatch(
                f"SessionMeta {field} disagrees with thread-spawn source"
            )
    payload["agent_depth"] = spawn["depth"]
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
        raise IdentityMismatch(
            "SubagentStop session does not match child SessionMeta.session_id"
        )
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
    if parent_meta.get("parent_thread_id") is None and parent_meta["id"] != runtime_session_id:
        raise IdentityMismatch("root parent does not match Hook runtime session")
    return {
        "runtime_session_id": meta["session_id"],
        "child_thread_id": meta["id"],
        "agent_id": meta["id"],
        "parent_thread_id": meta["parent_thread_id"],
        "agent_type": meta["agent_role"],
        "canonical_agent_path": meta["agent_path"],
    }


def pre_tool_use(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    now: dt.datetime | None = None,
) -> dict:
    try:
        if hook_input.get("hook_event_name") != "PreToolUse":
            raise GuardError("expected a PreToolUse event")
        identity = child_identity_from_hook(hook_input)
        assignment_id, envelope = store.find_active(identity)
        tool_name = hook_input.get("tool_name")
        if tool_name not in READ_ONLY_TOOL_NAMES:
            capsule = envelope["capsule"]
            observed_at = now or dt.datetime.now(dt.timezone.utc)
            snapshot = collect_git_snapshot(capsule["root"]["path"])
            mutation_mode = capsule["assignment_mutation_mode"]
            reason = "read_only_mutation_attempt"
            blocking_gates = None
            if mutation_mode == "write":
                reason = "write_authority_gates_missing"
                blocking_gates = [
                    "trusted_host_user_write_consent",
                    "direct_write_qualification",
                    "live_mutation_mediation",
                ]
            evidence = _termination_evidence(
                capsule,
                snapshot,
                reason=reason,
                observed_at=observed_at,
                attempted_tool_name=(
                    tool_name if isinstance(tool_name, str) and tool_name else "<invalid>"
                ),
                blocking_gates=blocking_gates,
            )
            store.terminate_active(assignment_id, evidence)
            if mutation_mode == "read_only":
                raise AuthorityViolation(
                    f"tool {tool_name!r} is not in the qualified read-only allowlist; "
                    "active authority terminated before execution"
                )
            raise AuthorityViolation(
                f"tool {tool_name!r} requested mutation with parent-recorded user intent, "
                "but trusted host user consent is unavailable, direct_write_qualified=false, "
                "and live mutation mediation is unproven; "
                "active authority terminated before execution"
            )
        capsule = envelope["capsule"]
        cwd = hook_input.get("cwd")
        if not isinstance(cwd, str):
            raise GuardError("PreToolUse has no cwd")
        snapshot = collect_git_snapshot(cwd)
        observed_at = now or dt.datetime.now(dt.timezone.utc)
        runtime = _active_runtime(envelope)
        if (
            runtime["first_git_attested_at"] is None
            and observed_at
            > dt.datetime.fromisoformat(capsule["pre_write_attestation_deadline"])
        ):
            evidence = _termination_evidence(
                capsule,
                snapshot,
                reason="pre_write_attestation_timeout",
                observed_at=observed_at,
            )
            store.terminate_active(assignment_id, evidence)
            raise AuthorityViolation("first Git attestation deadline elapsed; authority terminated")
        initial_disk_change = (
            disk_change_from_baseline(snapshot, capsule)
            if runtime["first_git_attested_at"] is None
            else False
        )
        if initial_disk_change is True:
            evidence = _termination_evidence(
                capsule,
                snapshot,
                reason="initial_disk_baseline_mismatch",
                observed_at=observed_at,
            )
            store.terminate_active(assignment_id, evidence)
            raise AuthorityViolation(
                "disk changed after capture and before first Git attestation; authority terminated"
            )
        violations = _snapshot_authority_violations(snapshot, capsule)
        if violations:
            if runtime["first_git_attested_at"] is None:
                evidence = _termination_evidence(
                    capsule,
                    snapshot,
                    reason="initial_location_or_scope_mismatch",
                    observed_at=observed_at,
                )
                store.terminate_active(assignment_id, evidence)
            raise AuthorityViolation("; ".join(violations))
        store.attest_tool_use(
            assignment_id,
            identity,
            root=snapshot["root"],
            branch=snapshot["branch"],
            head=snapshot["head"],
            now=observed_at,
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
        "inventory_summaries",
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
    if not isinstance(value["inventory_summaries"], list):
        raise GuardError("inventory_summaries must be a list")
    for summary in value["inventory_summaries"]:
        if not isinstance(summary, dict) or set(summary) != {
            "registry_id",
            "declared_count",
            "item_ids",
            "items_sha256",
        }:
            raise GuardError("inventory summary fields are not exact")
        if not isinstance(summary["registry_id"], str) or not summary["registry_id"]:
            raise GuardError("inventory registry_id is invalid")
        if type(summary["declared_count"]) is not int or summary["declared_count"] < 0:
            raise GuardError("inventory declared_count is invalid")
        if not isinstance(summary["item_ids"], list) or any(
            not isinstance(item, str) for item in summary["item_ids"]
        ):
            raise GuardError("inventory item_ids are invalid")
        if not isinstance(summary["items_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", summary["items_sha256"]
        ):
            raise GuardError("inventory items_sha256 is invalid")
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


def disk_change_from_baseline(
    snapshot: Mapping[str, object],
    capsule: Mapping[str, object],
) -> bool | None:
    baseline_paths = sorted(
        (
            {
                "path": item["path"],
                "kind": item["kind"],
                "sha256": item["sha256"],
            }
            for item in capsule["preexisting_dirty"]
        ),
        key=lambda item: item["path"],
    )
    expected_root = capsule["root"]
    if any(
        (
            snapshot["root"] != str(Path(expected_root["path"]).resolve()),
            snapshot["branch"] != expected_root["branch"],
            snapshot["head"] != expected_root["base_commit"],
        )
    ):
        return None
    return any(
        (
            snapshot["index_changed"] != expected_root["base_index_changed"],
            snapshot["git_status_short"] != expected_root["base_git_status_short"],
            snapshot["changed_paths"] != baseline_paths,
        )
    )


def _termination_evidence(
    capsule: Mapping[str, object],
    snapshot: Mapping[str, object],
    *,
    reason: str,
    observed_at: dt.datetime,
    attempted_tool_name: str | None = None,
    blocking_gates: list[str] | None = None,
) -> dict:
    disk_changed = disk_change_from_baseline(snapshot, capsule)
    if disk_changed is None:
        classification = "initial_authority_mismatch"
    elif reason == "pre_write_attestation_timeout":
        classification = (
            "unresponsive_with_disk_change_before_attestation"
            if disk_changed
            else "unresponsive_no_disk_change"
        )
    elif reason == "assignment_timeout":
        classification = (
            "unresponsive_with_contribution"
            if disk_changed
            else "unresponsive_no_disk_change"
        )
    elif reason == "initial_disk_baseline_mismatch":
        classification = (
            "late_mutation_after_interrupt"
            if capsule["ownership_handover"]
            else "unresponsive_with_disk_change_before_attestation"
        )
    elif reason == "read_only_mutation_attempt":
        classification = "read_only_child_mutation_attempt"
    elif reason == "write_authority_gates_missing":
        classification = "write_authority_gates_missing"
    else:
        classification = "initial_authority_mismatch"
    if classification == "late_mutation_after_interrupt":
        provenance_status = "overlapping_assignment_provenance"
    elif classification in {
        "read_only_child_mutation_attempt",
        "write_authority_gates_missing",
    } and disk_changed:
        provenance_status = "pre_attempt_disk_drift_unattributed"
    else:
        provenance_status = None
    evidence = {
        "schema": 1,
        "reason": reason,
        "classification": classification,
        "disk_changed": disk_changed,
        "baseline_comparable": disk_changed is not None,
        "provenance_status": provenance_status,
        "observed_at": observed_at.isoformat(),
        "snapshot": dict(snapshot),
    }
    if attempted_tool_name is not None:
        evidence["attempted_tool_name"] = attempted_tool_name
        evidence["mutation_blocked_before_execution"] = True
    if blocking_gates is not None:
        evidence["blocking_gates"] = list(blocking_gates)
    return evidence


def sweep_deadlines(
    store: StateStore,
    *,
    now: dt.datetime | None = None,
) -> list[dict]:
    observed_at = now or dt.datetime.now(dt.timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise GuardError("watchdog time must include a UTC offset")
    results = []
    for assignment_id, envelope in store.list_active():
        capsule = envelope["capsule"]
        runtime = _active_runtime(envelope)
        reason = None
        if (
            runtime["first_git_attested_at"] is None
            and observed_at
            > dt.datetime.fromisoformat(capsule["pre_write_attestation_deadline"])
        ):
            reason = "pre_write_attestation_timeout"
        elif observed_at > dt.datetime.fromisoformat(capsule["expires_at"]):
            reason = "assignment_timeout"
        if reason is None:
            continue
        snapshot = collect_git_snapshot(capsule["root"]["path"])
        evidence = _termination_evidence(
            capsule,
            snapshot,
            reason=reason,
            observed_at=observed_at,
        )
        store.terminate_active(assignment_id, evidence)
        results.append({"assignment_id": assignment_id, **evidence})
    return results


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
        snapshot = collect_git_snapshot(capsule["root"]["path"])
        try:
            attestation = parse_attestation(hook_input.get("last_assistant_message"))
        except GuardError as error:
            disk_changed = disk_change_from_baseline(snapshot, capsule)
            if disk_changed is None:
                classification = "invalid_final_with_untrusted_location"
            elif disk_changed:
                classification = "return_context_loss_with_contribution"
            else:
                classification = "invalid_final_without_contribution"
            return {
                "decision": "block",
                "reason": (
                    f"TASK.FINAL_{classification.upper()}: {error}. "
                    "Disk evidence does not restore missing authority; return a corrected attestation."
                ),
            }
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
        registry_contracts = capsule["execution_contract"]["closed_registries"]
        summaries = attestation["inventory_summaries"]
        if len(summaries) != len(registry_contracts):
            raise GuardError("inventory summaries do not exactly cover closed registries")
        summaries_by_id = {item["registry_id"]: item for item in summaries}
        if len(summaries_by_id) != len(summaries):
            raise GuardError("inventory summaries contain a duplicate registry id")
        for registry in registry_contracts:
            summary = summaries_by_id.get(registry["registry_id"])
            if summary is None:
                raise GuardError("inventory summary is missing a closed registry")
            expected_items = registry["closed_item_ids"]
            if summary["item_ids"] != expected_items:
                raise GuardError("inventory item ids do not match the closed registry")
            if summary["declared_count"] != len(expected_items):
                raise GuardError("inventory declared count does not match item cardinality")
            if summary["items_sha256"] != registry_items_sha256(expected_items):
                raise GuardError("inventory item digest does not match the closed registry")
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
        if complete and _active_runtime(envelope)["first_git_attested_at"] is None:
            raise GuardError("complete return has no durable first Git attestation")
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
