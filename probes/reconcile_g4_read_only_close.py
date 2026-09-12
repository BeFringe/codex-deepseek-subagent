#!/usr/bin/env python3

"""Reconcile one exact read-only G4 close receipt into a durable barrier."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from compatibility_state import (  # noqa: E402
    CorruptState,
    MissingState,
    StateError,
    StateStore,
    validate_capsule,
)
from runtime_guard import collect_git_snapshot  # noqa: E402


AGENT_TYPE = "g4_qualification_probe_worker"
TOOL_NAMESPACE = "g4_assignment"
ALLOWED_CALLS = ["spawn_agent", "list_agents", "close_agent", "list_agents"]
CLOSE_FIELDS = {
    "previous_status",
    "target_thread_id",
    "target_agent_path",
    "session_loop_terminated",
    "model_callable_process_bootstrap_absent",
    "tracked_background_processes_before_close",
    "tracked_process_ids_by_thread",
    "confirmed_exit_process_ids_by_thread",
    "unconfirmed_exit_process_ids_by_thread",
    "unresolved_start_process_ids_by_thread",
    "tracked_process_termination_confirmed",
    "closed_catalog_actor_quiescence_claimed",
    "process_tree_quiescence_claimed",
}


class ReconciliationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconciliationError(f"cannot decode {path.name}") from error
    if not isinstance(value, dict):
        raise ReconciliationError(f"{path.name} is not a JSON object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReconciliationError(f"cannot read {path.name}") from error
    for line_number, line in enumerate(lines, 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReconciliationError(
                f"{path.name}:{line_number} is not valid JSON"
            ) from error
        if not isinstance(value, dict):
            raise ReconciliationError(
                f"{path.name}:{line_number} is not a JSON object"
            )
        records.append(value)
    return records


def parse_timestamp(value: object, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ReconciliationError(f"{label} has no timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReconciliationError(f"{label} timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReconciliationError(f"{label} timestamp lacks a UTC offset")
    return parsed


def session_meta(records: list[dict[str, Any]], label: str) -> dict[str, Any]:
    matches = [record.get("payload") for record in records if record.get("type") == "session_meta"]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ReconciliationError(f"{label} must contain exactly one SessionMeta")
    return matches[0]


def response_items(records: list[dict[str, Any]], item_type: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    result = []
    for record in records:
        if record.get("type") != "response_item":
            continue
        payload = record.get("payload")
        if isinstance(payload, dict) and payload.get("type") == item_type:
            result.append((record, payload))
    return result


def json_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ReconciliationError(f"{label} is not encoded JSON")
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise ReconciliationError(f"{label} is invalid JSON") from error
    if not isinstance(result, dict):
        raise ReconciliationError(f"{label} is not a JSON object")
    return result


def validate_identity(
    envelope: dict[str, Any],
    parent_records: list[dict[str, Any]],
    child_records: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    capsule = validate_capsule(envelope.get("capsule"), envelope.get("assignment"))
    binding = envelope.get("binding")
    if not isinstance(binding, dict):
        raise ReconciliationError("active authority has no child binding")
    if capsule["assignment_mutation_mode"] != "read_only":
        raise ReconciliationError("only a read-only assignment may use this reconciler")
    if capsule["agent_type"] != AGENT_TYPE or binding.get("agent_type") != AGENT_TYPE:
        raise ReconciliationError("assignment is not the exact G4 qualification role")
    if capsule["owned_paths"] or capsule["excluded_paths"]:
        raise ReconciliationError("read-only close reconciliation requires an empty path scope")
    if capsule["parent_recorded_user_write_intent"] != "deny":
        raise ReconciliationError("read-only close reconciliation has write intent")

    parent = session_meta(parent_records, "parent rollout")
    child = session_meta(child_records, "child rollout")
    parent_thread = capsule["parent_thread_id"]
    child_thread = binding.get("child_thread_id")
    canonical_path = capsule["canonical_agent_path"]
    if not isinstance(child_thread, str):
        raise ReconciliationError("binding has no child thread id")
    if not (
        parent.get("id") == parent_thread
        and parent.get("session_id") == capsule["runtime_session_id"]
        and parent.get("cwd") == capsule["root"]["path"]
        and parent.get("source") == "exec"
        and parent.get("model_provider") == "openai"
    ):
        raise ReconciliationError("parent SessionMeta does not match the capsule")
    source = child.get("source")
    spawn_source = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
    if not (
        child.get("id") == child_thread
        and child.get("session_id") == capsule["runtime_session_id"]
        and child.get("parent_thread_id") == parent_thread
        and child.get("cwd") == capsule["root"]["path"]
        and child.get("agent_role") == AGENT_TYPE
        and child.get("agent_path") == canonical_path
        and child.get("model_provider") == "openai"
        and spawn_source.get("parent_thread_id") == parent_thread
        and spawn_source.get("agent_path") == canonical_path
        and spawn_source.get("agent_role") == AGENT_TYPE
    ):
        raise ReconciliationError("child SessionMeta does not match the durable binding")
    return capsule, binding, parent, child


def validate_parent_lifecycle(
    capsule: dict[str, Any],
    binding: dict[str, Any],
    assignment: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    calls = response_items(records, "function_call")
    selected = [
        (record, item)
        for record, item in calls
        if item.get("namespace") == TOOL_NAMESPACE
    ]
    names = [item.get("name") for _, item in selected]
    if names != ALLOWED_CALLS or len(calls) != len(selected):
        raise ReconciliationError("parent tool order is not exact spawn/list/close/list")
    if any(item.get("name") == "wait_agent" for _, item in calls):
        raise ReconciliationError("parent inserted a wait before close")

    spawn_record, spawn = selected[0]
    spawn_arguments = json_object(spawn.get("arguments"), "spawn arguments")
    if not (
        spawn.get("call_id") == capsule["spawn_tool_use_id"]
        and spawn_arguments
        == {
            "agent_type": AGENT_TYPE,
            "task_name": capsule["requested_task_name"],
            "fork_turns": "none",
            "message": assignment,
        }
    ):
        raise ReconciliationError("spawn call does not match the durable assignment")

    outputs = {
        item.get("call_id"): (record, item)
        for record, item in response_items(records, "function_call_output")
    }
    if any(item.get("call_id") not in outputs for _, item in selected):
        raise ReconciliationError("parent lifecycle has a missing tool output")
    child_thread = binding["child_thread_id"]
    canonical_path = capsule["canonical_agent_path"]

    pre_list = json_object(outputs[selected[1][1]["call_id"]][1].get("output"), "pre-close list output")
    agents = pre_list.get("agents")
    if not isinstance(agents, list) or not any(
        isinstance(agent, dict)
        and agent.get("agent_name") == canonical_path
        and agent.get("agent_status") == "running"
        for agent in agents
    ):
        raise ReconciliationError("pre-close live tree does not show the target running")

    close_record, close_call = selected[2]
    close_arguments = json_object(close_call.get("arguments"), "close arguments")
    if close_arguments != {"target": canonical_path}:
        raise ReconciliationError("close target is not the canonical AgentPath")
    close_output_record, close_output_item = outputs[close_call["call_id"]]
    close = json_object(close_output_item.get("output"), "close output")
    if set(close) != CLOSE_FIELDS:
        raise ReconciliationError("close receipt fields are not exact")
    empty_map = {child_thread: []}
    if not (
        close["previous_status"] == "running"
        and close["target_thread_id"] == child_thread
        and close["target_agent_path"] == canonical_path
        and close["session_loop_terminated"] is True
        and close["model_callable_process_bootstrap_absent"] is True
        and close["tracked_background_processes_before_close"] == 0
        and close["tracked_process_ids_by_thread"] == empty_map
        and close["confirmed_exit_process_ids_by_thread"] == empty_map
        and close["unconfirmed_exit_process_ids_by_thread"] == empty_map
        and close["unresolved_start_process_ids_by_thread"] == empty_map
        and close["tracked_process_termination_confirmed"] is True
        and close["closed_catalog_actor_quiescence_claimed"] is True
        and close["process_tree_quiescence_claimed"] is False
    ):
        raise ReconciliationError("close receipt does not prove the bounded actor barrier")

    post_list = json_object(outputs[selected[3][1]["call_id"]][1].get("output"), "post-close list output")
    post_agents = post_list.get("agents")
    if not isinstance(post_agents, list) or any(
        isinstance(agent, dict) and agent.get("agent_name") == canonical_path
        for agent in post_agents
    ):
        raise ReconciliationError("target remains in the post-close live tree")
    if not (selected[1][0]["timestamp"] < close_record["timestamp"] < selected[3][0]["timestamp"]):
        raise ReconciliationError("parent lifecycle timestamps are not ordered")
    return {
        "close_tool_use_id": close_call["call_id"],
        "close_receipt": close,
        "close_receipt_sha256": sha256_json(close),
        "terminated_at": parse_timestamp(close_output_record.get("timestamp"), "close output"),
        "spawn_called_at": parse_timestamp(spawn_record.get("timestamp"), "spawn call"),
    }


def validate_child_lifecycle(
    records: list[dict[str, Any]],
    terminated_at: dt.datetime,
) -> dict[str, Any]:
    if response_items(records, "function_call"):
        raise ReconciliationError("child called a tool before close")
    if any(
        item.get("role") == "assistant"
        for _, item in response_items(records, "message")
    ):
        raise ReconciliationError("child produced a message before close")
    task_complete = [
        record for record in records
        if record.get("type") == "event_msg"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("type") == "task_complete"
    ]
    if task_complete:
        raise ReconciliationError("child completed before close")
    aborted = [
        record for record in records
        if record.get("type") == "event_msg"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("type") == "turn_aborted"
    ]
    if len(aborted) != 1 or aborted[0]["payload"].get("reason") != "interrupted":
        raise ReconciliationError("child has no exact interrupted terminal event")
    aborted_at = parse_timestamp(aborted[0].get("timestamp"), "child abort")
    if aborted_at > terminated_at:
        raise ReconciliationError("child abort follows the completed close receipt")
    return {"turn_aborted_at": aborted_at}


def validate_hook_chain(
    chain: dict[str, Any],
    capsule: dict[str, Any],
    binding: dict[str, Any],
) -> list[dict[str, Any]]:
    events = chain.get("events")
    if not isinstance(events, list):
        raise ReconciliationError("Hook chain has no event list")
    session_id = capsule["runtime_session_id"]
    selected = [
        event for event in events
        if isinstance(event, dict)
        and isinstance(event.get("actor"), dict)
        and event["actor"].get("runtime_session_id") == session_id
    ]
    if len(selected) != 2:
        raise ReconciliationError("exact close run must have one spawn and one SubagentStart Hook event")
    spawn, start = selected
    if not (
        spawn.get("hook_event_name") == "PreToolUse"
        and spawn.get("scope") == "target_spawn"
        and spawn.get("tool_use_id") == capsule["spawn_tool_use_id"]
        and spawn["actor"].get("thread_id") == capsule["parent_thread_id"]
        and start.get("hook_event_name") == "SubagentStart"
        and start.get("scope") == "target_child"
        and start["actor"].get("thread_id") == binding["child_thread_id"]
        and start["actor"].get("canonical_agent_path") == capsule["canonical_agent_path"]
        and start["actor"].get("agent_type") == AGENT_TYPE
        and isinstance(spawn.get("sequence"), int)
        and start.get("sequence") == spawn["sequence"] + 1
    ):
        raise ReconciliationError("Hook events do not bind the exact parent and child")
    return selected


def process_absent(candidate: Path) -> bool:
    result = subprocess.run(
        ["lsof", str(candidate)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise ReconciliationError("lsof could not inspect the candidate executable")
    return not result.stdout.strip()


def observe_barrier(root: Path, candidate: Path) -> dict[str, Any]:
    snapshot = collect_git_snapshot(str(root))
    return {
        "observed_at": dt.datetime.now(dt.timezone.utc),
        "snapshot": snapshot,
        "candidate_process_absent": process_absent(candidate),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--assignment-id", required=True)
    parser.add_argument("--parent-rollout", type=Path, required=True)
    parser.add_argument("--child-rollout", type=Path, required=True)
    parser.add_argument("--hook-chain", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--barrier-delay-seconds", type=float, default=2.0)
    arguments = parser.parse_args()
    try:
        if not 0 <= arguments.barrier_delay_seconds <= 10:
            raise ReconciliationError("barrier delay must be between zero and ten seconds")
        candidate = arguments.candidate.resolve(strict=True)
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise ReconciliationError("candidate is not an executable regular file")
        candidate_sha256 = sha256_file(candidate)
        if candidate_sha256 != arguments.expected_candidate_sha256:
            raise ReconciliationError("candidate digest does not match")

        store = StateStore(arguments.state_directory)
        active_path = store.path("active", arguments.assignment_id)
        if not active_path.is_file():
            raise MissingState("exact active assignment was not found")
        envelope = read_json(active_path)
        parent_records = read_jsonl(arguments.parent_rollout)
        child_records = read_jsonl(arguments.child_rollout)
        capsule, binding, _, _ = validate_identity(
            envelope,
            parent_records,
            child_records,
        )
        lifecycle = validate_parent_lifecycle(
            capsule,
            binding,
            envelope["assignment"],
            parent_records,
        )
        child_lifecycle = validate_child_lifecycle(
            child_records,
            lifecycle["terminated_at"],
        )
        hook_events = validate_hook_chain(
            read_json(arguments.hook_chain),
            capsule,
            binding,
        )

        first = observe_barrier(Path(capsule["root"]["path"]), candidate)
        time.sleep(arguments.barrier_delay_seconds)
        second = observe_barrier(Path(capsule["root"]["path"]), candidate)
        expected_snapshot = {
            "root": capsule["root"]["path"],
            "branch": capsule["root"]["branch"],
            "head": capsule["root"]["base_commit"],
            "index_changed": capsule["root"]["base_index_changed"],
            "git_status_short": capsule["root"]["base_git_status_short"],
            "changed_paths": capsule["preexisting_dirty"],
        }
        if not (
            first["candidate_process_absent"]
            and second["candidate_process_absent"]
            and first["snapshot"] == second["snapshot"] == expected_snapshot
        ):
            raise ReconciliationError("post-close process or disk barrier is not stable")

        for claim_path in (arguments.state_directory / "writer_claim").glob("*.json"):
            claim = read_json(claim_path)
            if Path(str(claim.get("root", ""))).resolve() == Path(capsule["root"]["path"]).resolve():
                raise ReconciliationError("writer claim remains in the closed actor root")

        parent_sha256 = sha256_file(arguments.parent_rollout)
        child_sha256 = sha256_file(arguments.child_rollout)
        evidence = {
            "schema": 1,
            "reason": "native_close_agent",
            "classification": "closed_catalog_read_only_actor_terminated_and_mutations_quiesced",
            "runtime_session_id": capsule["runtime_session_id"],
            "child_thread_id": binding["child_thread_id"],
            "canonical_agent_path": capsule["canonical_agent_path"],
            "close_tool_use_id": lifecycle["close_tool_use_id"],
            "close_receipt_sha256": lifecycle["close_receipt_sha256"],
            "parent_rollout_sha256": parent_sha256,
            "child_rollout_sha256": child_sha256,
            "hook_sequences": [event["sequence"] for event in hook_events],
            "child_turn_aborted_at": child_lifecycle["turn_aborted_at"].isoformat(),
            "terminated_at": lifecycle["terminated_at"].isoformat(),
            "process_tree_quiescence_claimed": False,
        }
        store.terminate_active(arguments.assignment_id, evidence)
        receipt_id = f"native-close:{lifecycle['close_tool_use_id']}:{lifecycle['close_receipt_sha256'][:16]}"
        barrier = store.record_quiescence_barrier(
            arguments.assignment_id,
            {
                "receipt_id": receipt_id,
                "runtime_session_id": capsule["runtime_session_id"],
                "child_thread_id": binding["child_thread_id"],
                "guarantee": "child_terminated_and_mutations_quiesced",
                "terminated_at": lifecycle["terminated_at"].isoformat(),
            },
            second["snapshot"],
            observed_at=second["observed_at"],
        )
        barrier_value = read_json(barrier)
        result = {
            "valid": True,
            "assignment_id": arguments.assignment_id,
            "runtime_session_id": capsule["runtime_session_id"],
            "child_thread_id": binding["child_thread_id"],
            "canonical_agent_path": capsule["canonical_agent_path"],
            "close_receipt_sha256": lifecycle["close_receipt_sha256"],
            "termination_evidence_sha256": sha256_json(evidence),
            "quiescence_barrier_sha256": barrier_value["barrier_sha256"],
            "snapshot_sha256": barrier_value["snapshot_sha256"],
            "candidate_sha256": candidate_sha256,
            "parent_rollout_sha256": parent_sha256,
            "child_rollout_sha256": child_sha256,
            "hook_sequences": evidence["hook_sequences"],
            "process_tree_quiescence_claimed": False,
            "direct_write_qualified": False,
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return 0
    except (OSError, subprocess.SubprocessError, StateError, ReconciliationError) as error:
        print(
            json.dumps(
                {"valid": False, "error": str(error)},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
