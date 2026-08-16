#!/usr/bin/env python3

"""Isolated plaintext-v2 assignment capture and child-claim adapter."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Collection, Mapping
import uuid

from compatibility_state import (
    StateError,
    StateStore,
    capsule_sha256,
    canonical_json,
    git_snapshot_sha256,
    sha256_bytes,
)
from compatibility_state import compact_invariant
from runtime_guard import GuardError, _git, child_identity_from_hook, collect_git_snapshot, read_session_meta


AUTHORITY_RE = re.compile(
    r"(?:\A|\n)BEGIN CODEX WORKER AUTHORITY\n(\{.*\})\nEND CODEX WORKER AUTHORITY\s*\Z",
    re.DOTALL,
)
AUTHORITY_FIELDS = {
    "schema",
    "assignment_mutation_mode",
    "user_child_write_authorized",
    "owned_paths",
    "excluded_paths",
    "git_authority",
    "stop_condition",
    "verification",
    "authority_provenance",
    "execution_contract",
    "location_preflight",
    "pre_write_attestation_timeout_seconds",
    "ttl_seconds",
}
USER_WRITE_AUTHORIZATION_FIELDS = {"schema", "allow"}
USER_WRITE_AUTHORIZATION_RE = re.compile(
    r"(?:\A|\n)BEGIN CODEX CHILD WRITE AUTHORIZATION\n(\{.*\})\n"
    r"END CODEX CHILD WRITE AUTHORIZATION\s*\Z",
    re.DOTALL,
)
MAX_ROLLOUT_LINE = 8 * 1024 * 1024
GIT_AUTHORITY_FIELDS = {"stage", "commit", "branch", "push"}
TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")
GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
LOCATION_PREFLIGHT_FIELDS = {
    "expected_root",
    "expected_branch",
    "expected_base_head",
}


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
    mutation_mode = value.get("assignment_mutation_mode")
    if mutation_mode not in {"read_only", "write"}:
        raise GuardError("assignment_mutation_mode must be read_only or write")
    if type(value.get("user_child_write_authorized")) is not bool:
        raise GuardError("user_child_write_authorized must be boolean")
    if mutation_mode == "read_only" and value["user_child_write_authorized"]:
        raise GuardError("read-only assignment cannot request child-write authorization")
    ttl_seconds = value.get("ttl_seconds")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
        raise GuardError("authority ttl_seconds must be between 1 and 3600")
    pre_write_timeout = value.get("pre_write_attestation_timeout_seconds")
    if (
        type(pre_write_timeout) is not int
        or not 1 <= pre_write_timeout <= 60
        or pre_write_timeout > ttl_seconds
    ):
        raise GuardError(
            "pre_write_attestation_timeout_seconds must be between 1 and 60 and no greater than ttl_seconds"
        )
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
    location_preflight = value.get("location_preflight")
    if location_preflight is not None:
        if not isinstance(location_preflight, dict) or set(location_preflight) != LOCATION_PREFLIGHT_FIELDS:
            raise GuardError("authority location_preflight fields are not exact")
        expected_root = location_preflight["expected_root"]
        if not isinstance(expected_root, str) or not Path(expected_root).is_absolute():
            raise GuardError("location_preflight.expected_root must be absolute")
        expected_branch = location_preflight["expected_branch"]
        if expected_branch is not None and (
            not isinstance(expected_branch, str) or not expected_branch
        ):
            raise GuardError("location_preflight.expected_branch is invalid")
        expected_head = location_preflight["expected_base_head"]
        if not isinstance(expected_head, str) or not GIT_OID_RE.fullmatch(expected_head):
            raise GuardError("location_preflight.expected_base_head must be a full Git object id")
    return value


def _check_location_preflight(snapshot: Mapping[str, object], preflight: object) -> None:
    if preflight is None:
        return
    assert isinstance(preflight, dict)
    expected_root = str(Path(preflight["expected_root"]).resolve())
    if snapshot["root"] != expected_root:
        raise GuardError("location preflight root does not match current Git root")
    if snapshot["branch"] != preflight["expected_branch"]:
        raise GuardError("location preflight branch does not match current Git branch")
    if snapshot["head"] != preflight["expected_base_head"]:
        raise GuardError("location preflight base HEAD does not exactly match current HEAD")


def _git_commit(root: Path, oid: object, field: str) -> str:
    if not isinstance(oid, str) or not GIT_OID_RE.fullmatch(oid):
        raise GuardError(f"{field} must be a full Git object id")
    resolved = (
        _git(root, "rev-parse", "--verify", f"{oid}^{{commit}}")
        .decode("ascii")
        .strip()
    )
    if resolved != oid:
        raise GuardError(f"{field} must resolve to its exact full Git object id")
    return resolved


def _path_is_within(path: str, roots: Collection[str]) -> bool:
    if not path or "\\" in path:
        return False
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or path != candidate.as_posix() or ".." in candidate.parts:
        return False
    normalized_roots = [PurePosixPath(root) for root in roots if isinstance(root, str)]
    return any(candidate == root or root in candidate.parents for root in normalized_roots)


def _check_execution_contract(
    root: Path,
    snapshot: Mapping[str, object],
    declaration: Mapping[str, object],
) -> None:
    execution = declaration.get("execution_contract")
    if not isinstance(execution, dict):
        raise GuardError("execution_contract must be an object")
    posture = execution.get("posture")
    review_range = execution.get("review_range")
    mutation_mode = declaration["assignment_mutation_mode"]
    if mutation_mode == "read_only" and posture != "strict_read_only":
        raise GuardError("read-only mutation mode requires strict_read_only posture")
    if mutation_mode == "write" and posture != "direct_write_unqualified":
        raise GuardError("write mutation mode requires direct_write_unqualified posture")
    if posture == "strict_read_only":
        if snapshot["index_changed"] or snapshot["git_status_short"] or snapshot["changed_paths"]:
            raise GuardError("strict read-only review requires a clean captured worktree")
        if declaration["owned_paths"] or declaration["excluded_paths"]:
            raise GuardError("strict read-only review cannot claim path ownership")
        if any(declaration["git_authority"].values()):
            raise GuardError("strict read-only review cannot claim Git authority")
        if not isinstance(review_range, dict) or set(review_range) != {"base_oid", "head_oid"}:
            raise GuardError("strict read-only review requires an exact review range")
        base_oid = _git_commit(root, review_range["base_oid"], "review_range.base_oid")
        head_oid = _git_commit(root, review_range["head_oid"], "review_range.head_oid")
        if head_oid != snapshot["head"]:
            raise GuardError("review_range.head_oid does not exactly match captured HEAD")
        if base_oid != head_oid:
            ancestor = subprocess.run(
                ["git", "-C", str(root), "merge-base", "--is-ancestor", base_oid, head_oid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            if ancestor.returncode != 0:
                raise GuardError("review_range.base_oid is not an ancestor of review_range.head_oid")
    elif posture != "direct_write_unqualified":
        raise GuardError("execution_contract.posture is invalid")
    if posture == "direct_write_unqualified":
        feasibility = execution.get("capsule_feasibility_attestation")
        if not isinstance(feasibility, dict):
            raise GuardError("direct-write spawn requires parent feasibility attestation")
        if feasibility.get("owner_decision") != "dispatch":
            raise GuardError("parent feasibility attestation blocks direct-write dispatch")

    continuation = execution.get("review_continuation")
    if continuation is not None:
        if not isinstance(continuation, dict):
            raise GuardError("review_continuation must be an object")
        if continuation.get("corrected_tip_oid") != snapshot["head"]:
            raise GuardError("review continuation corrected tip does not exactly match captured HEAD")
        for field in (
            "frozen_cumulative_base_oid",
            "prior_review_base_oid",
            "prior_review_tip_oid",
            "corrected_tip_oid",
        ):
            _git_commit(root, continuation.get(field), f"review_continuation.{field}")
        objective = continuation.get("exact_narrowed_objective")
        if not isinstance(objective, str) or objective not in declaration["stop_condition"]:
            raise GuardError("review continuation objective is not bound by the stop condition")

    provenance = declaration["authority_provenance"]
    input_roots = provenance.get("authoritative_input_roots", [])
    baselines = execution.get("proven_input_baselines")
    if not isinstance(baselines, list):
        raise GuardError("proven_input_baselines must be a list")
    for baseline in baselines:
        if not isinstance(baseline, dict):
            raise GuardError("proven input baseline must be an object")
        manifest_path = baseline.get("manifest_path")
        if not isinstance(manifest_path, str) or not _path_is_within(manifest_path, input_roots):
            raise GuardError("proven input baseline is outside authoritative input roots")
        manifest = root / manifest_path
        resolved_manifest = manifest.resolve()
        if (
            manifest.is_symlink()
            or (resolved_manifest != root and root not in resolved_manifest.parents)
            or not resolved_manifest.is_file()
        ):
            raise GuardError("proven input baseline manifest must be a regular file")
        actual = hashlib.sha256(resolved_manifest.read_bytes()).hexdigest()
        if actual != baseline.get("sha256"):
            raise GuardError("proven input baseline manifest hash does not match")


def _user_child_write_authorization(
    transcript_path: object,
    parent_turn_id: object,
    *,
    mutation_mode: str,
    requested: bool,
) -> dict:
    if mutation_mode == "read_only":
        if requested:
            raise GuardError("read-only assignment cannot request child-write authorization")
        return {
            "schema": 1,
            "decision": "not_required",
            "authorizing_turn_id": None,
            "user_prompt_sha256": None,
        }
    if not requested:
        raise GuardError("write assignment lacks explicit user child-write authorization")
    if not isinstance(parent_turn_id, str) or not parent_turn_id:
        raise GuardError("write authorization has no exact parent turn id")
    if not isinstance(transcript_path, str) or not Path(transcript_path).is_absolute():
        raise GuardError("write authorization has no absolute parent transcript path")

    matches: list[dict] = []
    try:
        with Path(transcript_path).open("rb") as stream:
            for raw_line in stream:
                if len(raw_line) > MAX_ROLLOUT_LINE or not raw_line.endswith(b"\n"):
                    raise GuardError("parent rollout contains an unbounded or partial line")
                try:
                    item = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise GuardError("parent rollout contains invalid JSON") from error
                if not isinstance(item, dict) or item.get("type") != "response_item":
                    continue
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    continue
                metadata = payload.get("internal_chat_message_metadata_passthrough")
                if (
                    payload.get("type") != "message"
                    or payload.get("role") != "user"
                    or not isinstance(metadata, dict)
                    or metadata.get("turn_id") != parent_turn_id
                ):
                    continue
                content = payload.get("content")
                if not isinstance(content, list) or not content:
                    raise GuardError("current-turn user prompt content is invalid")
                text_parts = []
                for part in content:
                    if not isinstance(part, dict) or not isinstance(part.get("type"), str):
                        raise GuardError("current-turn user prompt item is invalid")
                    if part["type"] == "input_text":
                        if set(part) != {"type", "text"} or not isinstance(part["text"], str):
                            raise GuardError("current-turn user text item is invalid")
                        text_parts.append(part["text"])
                message = "\n".join(text_parts)
                if message.count("BEGIN CODEX CHILD WRITE AUTHORIZATION") == 0:
                    continue
                if message.count("BEGIN CODEX CHILD WRITE AUTHORIZATION") != 1:
                    raise GuardError("current-turn user prompt has ambiguous write authorization")
                match = USER_WRITE_AUTHORIZATION_RE.search(message)
                if match is None:
                    raise GuardError("user child-write authorization must terminate the user prompt")
                try:
                    authorization = json.loads(match.group(1))
                except json.JSONDecodeError as error:
                    raise GuardError("user child-write authorization is invalid JSON") from error
                if (
                    not isinstance(authorization, dict)
                    or set(authorization) != USER_WRITE_AUTHORIZATION_FIELDS
                    or authorization.get("schema") != 1
                    or authorization.get("allow") is not True
                ):
                    raise GuardError("user child-write authorization fields are not exact")
                matches.append(
                    {
                        "schema": 1,
                        "decision": "allow",
                        "authorizing_turn_id": parent_turn_id,
                        "user_prompt_sha256": sha256_bytes(
                            canonical_json({"turn_id": parent_turn_id, "content": content})
                        ),
                    }
                )
    except OSError as error:
        raise GuardError("parent rollout is unavailable for write authorization") from error
    if len(matches) != 1:
        raise GuardError(
            "write assignment requires exactly one current-turn user authorization"
        )
    return matches[0]


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
        parent_turn_id = hook_input.get("turn_id")
        write_authorization = _user_child_write_authorization(
            hook_input.get("transcript_path"),
            parent_turn_id,
            mutation_mode=declaration["assignment_mutation_mode"],
            requested=declaration["user_child_write_authorized"],
        )
        cwd = hook_input.get("cwd")
        if not isinstance(cwd, str):
            raise GuardError("spawn Hook has no cwd")
        snapshot = collect_git_snapshot(cwd)
        _check_location_preflight(snapshot, declaration["location_preflight"])
        _check_execution_contract(Path(snapshot["root"]), snapshot, declaration)
        created_at = now or dt.datetime.now(dt.timezone.utc)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise GuardError("capture time must include a UTC offset")
        ownership_handover = store.resolve_ownership_handover(
            declaration["owned_paths"],
            snapshot,
            observed_at=created_at,
            require_quiet_root=(
                declaration["execution_contract"]["posture"] == "strict_read_only"
            ),
        )
        assignment_id = str(uuid.uuid4())
        handoff_id = str(uuid.uuid4())
        git_authority = declaration["git_authority"]
        capsule = {
            "schema": 2,
            "assignment_id": assignment_id,
            "handoff_id": handoff_id,
            "runtime_session_id": str(hook_input["session_id"]),
            "parent_thread_id": parent_meta["id"],
            "parent_turn_id": str(parent_turn_id or ""),
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
                "base_index_changed": snapshot["index_changed"],
                "base_git_status_short": snapshot["git_status_short"],
            },
            "capture_preflight": declaration["location_preflight"],
            "capture_snapshot_sha256": git_snapshot_sha256(snapshot),
            "assignment_mutation_mode": declaration["assignment_mutation_mode"],
            "user_child_write_authorization": write_authorization,
            "owned_paths": declaration["owned_paths"],
            "excluded_paths": declaration["excluded_paths"],
            "git_authority": git_authority,
            "ownership_handover": ownership_handover,
            "stop_condition": declaration["stop_condition"],
            "verification": declaration["verification"],
            "authority_provenance": declaration["authority_provenance"],
            "execution_contract": declaration["execution_contract"],
            "preexisting_dirty": _preexisting_dirty(Path(snapshot["root"]), snapshot),
            "assignment_sha256": sha256_bytes(str(message).encode("utf-8")),
            "created_at": created_at.isoformat(),
            "pre_write_attestation_deadline": (
                created_at
                + dt.timedelta(
                    seconds=declaration["pre_write_attestation_timeout_seconds"]
                )
            ).isoformat(),
            "expires_at": (
                created_at + dt.timedelta(seconds=declaration["ttl_seconds"])
            ).isoformat(),
        }
        capsule["capsule_sha256"] = capsule_sha256(capsule)
        staging_snapshot = collect_git_snapshot(cwd)
        store.stage_with_ownership_recheck(
            capsule,
            str(message),
            staging_snapshot,
            observed_at=created_at,
        )
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
