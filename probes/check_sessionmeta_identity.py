#!/usr/bin/env python3

"""Mechanically join pinned spawn, Hook, and SessionMeta identity evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import uuid


PROBE_DIRECTORY = Path(__file__).resolve().parent
if str(PROBE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROBE_DIRECTORY))

from check_runtime_evidence_index import (  # noqa: E402
    load_index,
    runtime_identity,
    runtime_pairs,
)


RUNTIME_EVIDENCE_INDEX = load_index()
SUPPORTED_RUNTIME_PAIRS = runtime_pairs(
    RUNTIME_EVIDENCE_INDEX, "sessionmeta_evidence_roles"
)
CURRENT_SIGNED_RUNTIME = runtime_identity(RUNTIME_EVIDENCE_INDEX)
PINNED_CODEX_VERSION = CURRENT_SIGNED_RUNTIME["codex_version"]
PINNED_SOURCE_COMMIT = CURRENT_SIGNED_RUNTIME["source_commit"]
MAX_SESSION_META_LINE = 1024 * 1024
TASK_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}")
CASE_KINDS = {
    "root_serial",
    "root_concurrent",
    "nested_serial",
    "nested_concurrent",
}
ORIGINS = {"provider_free_fixture", "live_parent_capture"}

PRE_TOOL_REQUIRED = {
    "session_id",
    "turn_id",
    "transcript_path",
    "cwd",
    "hook_event_name",
    "model",
    "permission_mode",
    "tool_name",
    "tool_input",
    "tool_use_id",
}
PRE_TOOL_OPTIONAL = {"agent_id", "agent_type"}
START_REQUIRED = {
    "session_id",
    "turn_id",
    "transcript_path",
    "cwd",
    "hook_event_name",
    "model",
    "permission_mode",
    "agent_id",
    "agent_type",
}
SPAWN_INPUT_REQUIRED = {"message", "task_name", "agent_type", "fork_turns"}
SPAWN_INPUT_OPTIONAL = {
    "model",
    "reasoning_effort",
    "service_tier",
    "fork_context",
}


class IdentityEvidenceError(ValueError):
    pass


def _canonical_sha256(value) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise IdentityEvidenceError(f"{label} must be an object")
    return value


def _exact_fields(value: dict, required: set[str], optional: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - required - optional)
    if missing or extra:
        raise IdentityEvidenceError(
            f"{label} fields are not exact: missing={missing}, extra={extra}"
        )


def _string(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise IdentityEvidenceError(f"{label} must be a non-empty string")
    return value


def _optional_string(value, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _uuid7(value, label: str) -> str:
    value = _string(value, label)
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise IdentityEvidenceError(f"{label} must be a UUIDv7") from error
    if parsed.version != 7 or str(parsed) != value:
        raise IdentityEvidenceError(f"{label} must be a canonical UUIDv7")
    return value


def _timestamp(value, label: str) -> dt.datetime:
    value = _string(value, label)
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as error:
        raise IdentityEvidenceError(f"{label} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IdentityEvidenceError(f"{label} must include a UTC offset")
    return parsed


def _absolute_path_flavor(value: str, label: str) -> str:
    if PureWindowsPath(value).is_absolute():
        return "windows"
    if PurePosixPath(value).is_absolute():
        return "posix"
    raise IdentityEvidenceError(f"{label} must be an absolute POSIX or Windows path")


def _session_meta(
    rollout, label: str, *, codex_version: str
) -> tuple[str, str, dict, str]:
    rollout = _object(rollout, label)
    _exact_fields(rollout, {"path", "session_meta_line"}, set(), label)
    path = _string(rollout["path"], f"{label}.path")
    path_flavor = _absolute_path_flavor(path, f"{label}.path")
    line = _string(rollout["session_meta_line"], f"{label}.session_meta_line")
    encoded = line.encode("utf-8")
    if len(encoded) > MAX_SESSION_META_LINE or not line.endswith("\n"):
        raise IdentityEvidenceError(f"{label} SessionMeta line is missing or unbounded")
    if line.count("\n") != 1:
        raise IdentityEvidenceError(f"{label} must contain exactly one first SessionMeta line")
    try:
        item = json.loads(line)
    except json.JSONDecodeError as error:
        raise IdentityEvidenceError(f"{label} SessionMeta line is invalid") from error
    item = _object(item, f"{label} SessionMeta record")
    _exact_fields(
        item,
        {"timestamp", "type", "payload"},
        {"ordinal"},
        f"{label} SessionMeta record",
    )
    if item["type"] != "session_meta":
        raise IdentityEvidenceError(f"{label} first rollout record is not SessionMeta")
    record_timestamp = _timestamp(
        item["timestamp"], f"{label} SessionMeta record timestamp"
    )
    if "ordinal" in item and item["ordinal"] != 0:
        raise IdentityEvidenceError(f"{label} first SessionMeta ordinal is not zero")
    payload = _object(item["payload"], f"{label} SessionMeta payload")
    if payload.get("cli_version") != codex_version:
        raise IdentityEvidenceError(f"{label} SessionMeta cli_version is not pinned")
    _string(payload.get("cwd"), f"{label} SessionMeta cwd")
    created_timestamp = _timestamp(
        payload.get("timestamp"), f"{label} SessionMeta payload timestamp"
    )
    if created_timestamp > record_timestamp:
        raise IdentityEvidenceError(
            f"{label} SessionMeta payload timestamp is later than its rollout record"
        )
    return path, path_flavor, payload, hashlib.sha256(encoded).hexdigest()


def _thread_spawn(meta: dict, label: str) -> dict:
    source = _object(meta.get("source"), f"{label}.source")
    _exact_fields(source, {"subagent"}, set(), f"{label}.source")
    subagent = _object(source["subagent"], f"{label}.source.subagent")
    _exact_fields(
        subagent, {"thread_spawn"}, set(), f"{label}.source.subagent"
    )
    spawn = _object(
        subagent["thread_spawn"], f"{label}.source.subagent.thread_spawn"
    )
    _exact_fields(
        spawn,
        {"parent_thread_id", "depth", "agent_path", "agent_nickname", "agent_role"},
        set(),
        f"{label}.source.subagent.thread_spawn",
    )
    _uuid7(spawn["parent_thread_id"], f"{label}.source parent_thread_id")
    if type(spawn["depth"]) is not int or spawn["depth"] < 1:
        raise IdentityEvidenceError(f"{label}.source depth must be a positive integer")
    _string(spawn["agent_path"], f"{label}.source agent_path")
    _optional_string(spawn["agent_nickname"], f"{label}.source agent_nickname")
    _string(spawn["agent_role"], f"{label}.source agent_role")
    return spawn


def _root_parent(meta: dict, label: str) -> None:
    if meta.get("parent_thread_id") is not None:
        raise IdentityEvidenceError(f"{label} root parent has a parent_thread_id")
    if meta.get("agent_path") is not None or meta.get("agent_role") is not None:
        raise IdentityEvidenceError(f"{label} root parent has child identity fields")
    source = meta.get("source")
    if not isinstance(source, str) or not source:
        raise IdentityEvidenceError(f"{label} root parent source is not a root source")


def _observation(value: dict, *, codex_version: str) -> dict:
    value = _object(value, "observation")
    _exact_fields(
        value,
        {
            "case_id",
            "case_kind",
            "cohort_id",
            "capture_hook",
            "spawn_result",
            "start_hook",
            "parent_rollout",
            "child_rollout",
        },
        set(),
        "observation",
    )
    case_id = _string(value["case_id"], "case_id")
    case_kind = value["case_kind"]
    if case_kind not in CASE_KINDS:
        raise IdentityEvidenceError(f"{case_id} has an invalid case_kind")
    concurrent = case_kind.endswith("concurrent")
    cohort_id = value["cohort_id"]
    if concurrent:
        cohort_id = _string(cohort_id, f"{case_id}.cohort_id")
    elif cohort_id is not None:
        raise IdentityEvidenceError(f"{case_id} serial observation has a cohort_id")

    capture = _object(value["capture_hook"], f"{case_id}.capture_hook")
    _exact_fields(capture, PRE_TOOL_REQUIRED, PRE_TOOL_OPTIONAL, f"{case_id}.capture_hook")
    if capture["hook_event_name"] != "PreToolUse" or capture["tool_name"] != "spawn_agent":
        raise IdentityEvidenceError(f"{case_id} did not capture PreToolUse(spawn_agent)")
    capture_session = _uuid7(capture["session_id"], f"{case_id}.capture session_id")
    _string(capture["turn_id"], f"{case_id}.capture turn_id")
    tool_use_id = _string(capture["tool_use_id"], f"{case_id}.tool_use_id")
    for field in ("transcript_path", "cwd", "model", "permission_mode"):
        _string(capture[field], f"{case_id}.capture {field}")
    if capture.get("agent_id") is not None:
        _uuid7(capture["agent_id"], f"{case_id}.capture agent_id")
    _optional_string(capture.get("agent_type"), f"{case_id}.capture agent_type")

    tool_input = _object(capture["tool_input"], f"{case_id}.spawn tool_input")
    _exact_fields(
        tool_input,
        SPAWN_INPUT_REQUIRED,
        SPAWN_INPUT_OPTIONAL,
        f"{case_id}.spawn tool_input",
    )
    _string(tool_input["message"], f"{case_id}.spawn message")
    requested = _string(tool_input["task_name"], f"{case_id}.requested task name")
    if not TASK_NAME_RE.fullmatch(requested):
        raise IdentityEvidenceError(f"{case_id} requested task name is not one path segment")
    agent_type = _string(tool_input["agent_type"], f"{case_id}.spawn agent_type")
    if tool_input["fork_turns"] != "none" or tool_input.get("fork_context") is not None:
        raise IdentityEvidenceError(f"{case_id} spawn does not use fork_turns=none")

    spawn_result = _object(value["spawn_result"], f"{case_id}.spawn_result")
    _exact_fields(spawn_result, {"task_name"}, {"nickname"}, f"{case_id}.spawn_result")
    canonical_from_spawn = _string(
        spawn_result["task_name"], f"{case_id}.spawn_result.task_name"
    )
    _optional_string(spawn_result.get("nickname"), f"{case_id}.spawn_result.nickname")

    start = _object(value["start_hook"], f"{case_id}.start_hook")
    _exact_fields(start, START_REQUIRED, set(), f"{case_id}.start_hook")
    if start["hook_event_name"] != "SubagentStart":
        raise IdentityEvidenceError(f"{case_id} start event is not SubagentStart")
    start_session = _uuid7(start["session_id"], f"{case_id}.start session_id")
    start_turn_id = _string(start["turn_id"], f"{case_id}.start turn_id")
    child_id = _uuid7(start["agent_id"], f"{case_id}.start agent_id")
    for field in ("transcript_path", "cwd", "model", "permission_mode"):
        _string(start[field], f"{case_id}.start {field}")
    if start["agent_type"] != agent_type:
        raise IdentityEvidenceError(f"{case_id} start role does not match spawn role")

    parent_path, parent_path_flavor, parent_meta, parent_line_sha256 = _session_meta(
        value["parent_rollout"],
        f"{case_id}.parent_rollout",
        codex_version=codex_version,
    )
    child_path, child_path_flavor, child_meta, child_line_sha256 = _session_meta(
        value["child_rollout"],
        f"{case_id}.child_rollout",
        codex_version=codex_version,
    )
    if capture["transcript_path"] != parent_path:
        raise IdentityEvidenceError(f"{case_id} capture transcript path is not the parent rollout")
    if start["transcript_path"] != child_path:
        raise IdentityEvidenceError(f"{case_id} start transcript path is not the child rollout")
    if parent_path == child_path:
        raise IdentityEvidenceError(f"{case_id} parent and child transcripts are identical")
    if parent_path_flavor != child_path_flavor:
        raise IdentityEvidenceError(
            f"{case_id} parent and child transcript path flavors do not match"
        )

    parent_session = _uuid7(parent_meta.get("session_id"), f"{case_id}.parent session_id")
    parent_id = _uuid7(parent_meta.get("id"), f"{case_id}.parent id")
    if capture_session != parent_session or start_session != parent_session:
        raise IdentityEvidenceError(f"{case_id} Hook and SessionMeta sessions do not match")
    if capture["cwd"] != parent_meta.get("cwd") or start["cwd"] != child_meta.get("cwd"):
        raise IdentityEvidenceError(f"{case_id} Hook cwd does not match SessionMeta cwd")
    if capture.get("agent_id") is not None and capture["agent_id"] != parent_id:
        raise IdentityEvidenceError(f"{case_id} capture agent_id does not match parent")

    nested = case_kind.startswith("nested")
    if nested:
        parent_role = _string(parent_meta.get("agent_role"), f"{case_id}.parent agent_role")
        parent_agent_path = _string(
            parent_meta.get("agent_path"), f"{case_id}.parent agent_path"
        )
        if capture.get("agent_id") != parent_id or capture.get("agent_type") != parent_role:
            raise IdentityEvidenceError(f"{case_id} nested capture lacks exact parent identity")
        parent_source = _thread_spawn(parent_meta, f"{case_id}.parent")
        if (
            parent_source["parent_thread_id"] != parent_meta.get("parent_thread_id")
            or parent_source["agent_path"] != parent_agent_path
            or parent_source["agent_role"] != parent_role
        ):
            raise IdentityEvidenceError(f"{case_id} parent source disagrees with SessionMeta")
        expected_depth = parent_source["depth"] + 1
    else:
        _root_parent(parent_meta, f"{case_id}.parent")
        parent_agent_path = "/root"
        expected_depth = 1

    child_session = _uuid7(child_meta.get("session_id"), f"{case_id}.child session_id")
    if child_session != parent_session:
        raise IdentityEvidenceError(f"{case_id} child and parent sessions do not match")
    if child_meta.get("id") != child_id:
        raise IdentityEvidenceError(f"{case_id} start agent_id does not match child SessionMeta")
    if child_meta.get("parent_thread_id") != parent_id:
        raise IdentityEvidenceError(f"{case_id} child parent_thread_id is not the spawner")
    if child_meta.get("agent_role") != agent_type:
        raise IdentityEvidenceError(f"{case_id} child role does not match spawn role")

    expected_path = f"{parent_agent_path}/{requested}"
    if canonical_from_spawn != expected_path:
        raise IdentityEvidenceError(f"{case_id} spawn canonical path is not the exact AgentPath join")
    if child_meta.get("agent_path") != canonical_from_spawn:
        raise IdentityEvidenceError(f"{case_id} child AgentPath does not match spawn result")
    if canonical_from_spawn.rsplit("/", 1)[-1] != requested:
        raise IdentityEvidenceError(f"{case_id} requested task name is not the exact final component")

    child_source = _thread_spawn(child_meta, f"{case_id}.child")
    if (
        child_source["parent_thread_id"] != parent_id
        or child_source["depth"] != expected_depth
        or child_source["agent_path"] != canonical_from_spawn
        or child_source["agent_role"] != agent_type
    ):
        raise IdentityEvidenceError(f"{case_id} child source disagrees with exact runtime identity")
    child_nickname = _optional_string(
        child_meta.get("agent_nickname"), f"{case_id}.child agent_nickname"
    )
    if child_source["agent_nickname"] != child_nickname:
        raise IdentityEvidenceError(f"{case_id} child source nickname disagrees with SessionMeta")
    if "nickname" in spawn_result and spawn_result["nickname"] != child_nickname:
        raise IdentityEvidenceError(f"{case_id} spawn nickname disagrees with SessionMeta")

    return {
        "case_id": case_id,
        "case_kind": case_kind,
        "cohort_id": cohort_id,
        "runtime_session_id": parent_session,
        "parent_thread_id": parent_id,
        "child_thread_id": child_id,
        "requested_task_name": requested,
        "canonical_agent_path": canonical_from_spawn,
        "agent_type": agent_type,
        "spawn_tool_use_id": tool_use_id,
        "start_turn_id": start_turn_id,
        "parent_transcript_path": parent_path,
        "child_transcript_path": child_path,
        "path_flavor": child_path_flavor,
        "parent_session_meta_line_sha256": parent_line_sha256,
        "child_session_meta_line_sha256": child_line_sha256,
    }


def _unique(receipts: list[dict], field: str) -> None:
    values = [receipt[field] for receipt in receipts]
    if len(set(values)) != len(values):
        raise IdentityEvidenceError(f"observations contain duplicate {field}")


def validate_bundle(value, *, minimum_per_case: int = 2) -> dict:
    value = _object(value, "identity evidence bundle")
    _exact_fields(
        value,
        {"schema", "codex_version", "source_commit", "evidence_origin", "observations"},
        set(),
        "identity evidence bundle",
    )
    if value["schema"] != 1:
        raise IdentityEvidenceError("identity evidence bundle has an invalid schema")
    codex_version = value["codex_version"]
    source_commit = value["source_commit"]
    if SUPPORTED_RUNTIME_PAIRS.get(codex_version) != source_commit:
        raise IdentityEvidenceError(
            "identity evidence bundle has an unpinned runtime/source pair"
        )
    if value["evidence_origin"] not in ORIGINS:
        raise IdentityEvidenceError("identity evidence bundle has an invalid origin")
    if type(minimum_per_case) is not int or minimum_per_case < 1:
        raise IdentityEvidenceError("minimum_per_case must be a positive integer")
    observations = value["observations"]
    if not isinstance(observations, list) or not observations:
        raise IdentityEvidenceError("identity evidence bundle has no observations")

    receipts = [
        _observation(observation, codex_version=codex_version)
        for observation in observations
    ]
    for field in (
        "case_id",
        "child_thread_id",
        "requested_task_name",
        "canonical_agent_path",
        "spawn_tool_use_id",
        "start_turn_id",
        "child_transcript_path",
    ):
        _unique(receipts, field)

    roles = {receipt["agent_type"] for receipt in receipts}
    if len(roles) != 1:
        raise IdentityEvidenceError("repeated-role matrix contains more than one agent type")

    counts = {kind: 0 for kind in sorted(CASE_KINDS)}
    for receipt in receipts:
        counts[receipt["case_kind"]] += 1
    matrix_complete = all(count >= minimum_per_case for count in counts.values())
    for kind in CASE_KINDS:
        members = [receipt for receipt in receipts if receipt["case_kind"] == kind]
        if members and len({receipt["parent_thread_id"] for receipt in members}) != 1:
            raise IdentityEvidenceError(f"{kind} observations do not share one exact parent")
        if kind.endswith("concurrent") and members:
            if len({receipt["cohort_id"] for receipt in members}) != 1:
                raise IdentityEvidenceError(f"{kind} observations do not share one cohort")

    normalized = {
        "schema": 1,
        "codex_version": codex_version,
        "source_commit": source_commit,
        "evidence_origin": value["evidence_origin"],
        "minimum_per_case": minimum_per_case,
        "case_counts": counts,
        "path_flavors": {
            flavor: sum(receipt["path_flavor"] == flavor for receipt in receipts)
            for flavor in ("posix", "windows")
        },
        "observations": sorted(receipts, key=lambda receipt: receipt["case_id"]),
    }
    return {
        "valid": True,
        "mechanically_exact": True,
        "matrix_complete": matrix_complete,
        "case_counts": counts,
        "path_flavors": normalized["path_flavors"],
        "observation_count": len(receipts),
        "agent_type": next(iter(roles)),
        "bundle_sha256": _canonical_sha256(value),
        "receipt_sha256": _canonical_sha256(normalized),
        "adjudication_authority": "none",
        "p2_live_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--minimum-per-case", type=int, default=2)
    parser.add_argument("--require-complete-matrix", action="store_true")
    arguments = parser.parse_args()
    try:
        value = json.loads(arguments.bundle.read_text(encoding="utf-8"))
        result = validate_bundle(value, minimum_per_case=arguments.minimum_per_case)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, IdentityEvidenceError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if arguments.require_complete_matrix and not result["matrix_complete"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
