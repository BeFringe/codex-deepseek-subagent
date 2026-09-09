#!/usr/bin/env python3

"""Reconcile one exact G4 write, accepted report, resumed hold, and host close."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping


SOURCE_ROOT = Path(__file__).resolve().parents[1]
HOOKS = SOURCE_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from compatibility_state import StateError, StateStore, validate_capsule  # noqa: E402
from reconcile_g4_read_only_close import (  # noqa: E402
    AGENT_TYPE,
    CLOSE_FIELDS,
    ReconciliationError,
    json_object,
    parse_timestamp,
    process_absent,
    read_json,
    read_jsonl,
    response_items,
    session_meta,
    sha256_file,
    sha256_json,
)
from runtime_guard import collect_git_snapshot, parse_attestation  # noqa: E402


TOOL_NAMESPACE = "g4_assignment"
TARGET_CONTENT = "G4_CHILD_WRITE_QUALIFIED\n"
FOLLOWUP_HOLD = (
    "P5B.WRITE.CLOSE.HOLD: make no tool call and no final; remain active for exact host close"
)
PARENT_CALLS = [
    "spawn_agent",
    "wait_agent",
    "followup_task",
    "list_agents",
    "close_agent",
    "list_agents",
]


def message_text(item: Mapping[str, Any]) -> str:
    content = item.get("content")
    if not isinstance(content, list):
        return ""
    return "".join(
        part.get("text", "")
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )


def expected_snapshot_from_attestation(attestation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "root": attestation["root"],
        "branch": attestation["branch"],
        "head": attestation["head"],
        "index_changed": attestation["index_changed"],
        "git_status_short": attestation["git_status_short"],
        "changed_paths": attestation["changed_paths"],
    }


def validate_identity(
    envelope: dict[str, Any],
    parent_records: list[dict[str, Any]],
    child_records: list[dict[str, Any]],
    target: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    capsule = validate_capsule(envelope.get("capsule"), envelope.get("assignment"))
    binding = envelope.get("binding")
    attestation = envelope.get("final_attestation")
    if not isinstance(binding, dict) or not isinstance(attestation, dict):
        raise ReconciliationError("reported assignment lacks binding or final attestation")
    root = Path(capsule["root"]["path"])
    if not (
        capsule["assignment_mutation_mode"] == "write"
        and capsule["parent_recorded_user_write_intent"] == "allow"
        and capsule["owned_paths"] == [target.relative_to(root).as_posix()]
        and capsule["excluded_paths"] == []
        and not any(capsule["git_authority"].values())
        and capsule["trusted_host_user_write_consent"].get("status") == "verified"
        and capsule["trusted_host_user_write_consent"].get("source")
        == "qualification_hook_exact_path"
    ):
        raise ReconciliationError("reported assignment does not have the exact write ceiling")

    parent = session_meta(parent_records, "parent rollout")
    child = session_meta(child_records, "child rollout")
    parent_thread = capsule["parent_thread_id"]
    child_thread = binding.get("child_thread_id")
    canonical_path = capsule["canonical_agent_path"]
    if not (
        parent.get("id") == parent_thread
        and parent.get("session_id") == capsule["runtime_session_id"]
        and parent.get("cwd") == str(root)
        and parent.get("source") == "exec"
        and parent.get("model_provider") == "openai"
    ):
        raise ReconciliationError("parent SessionMeta does not match the write capsule")
    source = child.get("source")
    spawn_source = (
        source.get("subagent", {}).get("thread_spawn", {})
        if isinstance(source, dict)
        else {}
    )
    if not (
        isinstance(child_thread, str)
        and child.get("id") == child_thread
        and child.get("session_id") == capsule["runtime_session_id"]
        and child.get("parent_thread_id") == parent_thread
        and child.get("cwd") == str(root)
        and child.get("agent_role") == AGENT_TYPE
        and child.get("agent_path") == canonical_path
        and child.get("model_provider") == "openai"
        and spawn_source.get("parent_thread_id") == parent_thread
        and spawn_source.get("agent_path") == canonical_path
        and spawn_source.get("agent_role") == AGENT_TYPE
    ):
        raise ReconciliationError("child SessionMeta does not match the write binding")
    return capsule, binding, attestation


def validate_writer_evidence(
    store: StateStore,
    capsule: dict[str, Any],
    binding: dict[str, Any],
    attestation: dict[str, Any],
    target: Path,
) -> dict[str, Any]:
    if not (
        attestation.get("assigned_slice_complete") is True
        and attestation.get("context_lost") is False
        and attestation.get("authority_violation") is False
    ):
        raise ReconciliationError("reported final is not an accepted complete attestation")
    provenance = attestation.get("authority_provenance")
    if not isinstance(provenance, dict):
        raise ReconciliationError("reported final has no provenance")
    receipt_sha256 = provenance.get("derivation_receipt_sha256")
    actor = {
        "runtime_session_id": capsule["runtime_session_id"],
        "thread_id": binding["child_thread_id"],
        "agent_type": AGENT_TYPE,
        "canonical_agent_path": capsule["canonical_agent_path"],
    }
    receipt = store.find_writer_receipt(actor, receipt_sha256)
    expected_snapshot = expected_snapshot_from_attestation(attestation)
    if not (
        receipt["actor"] == actor
        and receipt["root"] == capsule["root"]["path"]
        and receipt["paths"] == capsule["owned_paths"]
        and receipt["tool_name"] == "apply_patch"
        and receipt["after_snapshot"] == expected_snapshot
        and target.read_text(encoding="utf-8") == TARGET_CONTENT
        and expected_snapshot["changed_paths"]
        == [
            {
                "kind": "file",
                "path": capsule["owned_paths"][0],
                "sha256": sha256_file(target),
            }
        ]
    ):
        raise ReconciliationError("writer receipt, attestation, and target bytes do not join")
    return receipt


def validate_child_lifecycle(
    records: list[dict[str, Any]],
    capsule: dict[str, Any],
    attestation: dict[str, Any],
    writer_receipt: dict[str, Any],
    target: Path,
    close_returned_at: dt.datetime,
) -> dict[str, Any]:
    calls = response_items(records, "custom_tool_call")
    outputs = response_items(records, "custom_tool_call_output")
    expected_patch = (
        "*** Begin Patch\n"
        f"*** Add File: {target}\n"
        "+G4_CHILD_WRITE_QUALIFIED\n"
        "*** End Patch\n"
    )
    if len(calls) != 1 or len(outputs) != 1:
        raise ReconciliationError("child did not make exactly one custom tool call")
    call_record, call = calls[0]
    output_record, output = outputs[0]
    if not (
        call.get("name") == "apply_patch"
        and call.get("call_id") == writer_receipt["tool_use_id"]
        and call.get("input") == expected_patch
        and output.get("call_id") == call.get("call_id")
        and "Success." in str(output.get("output"))
    ):
        raise ReconciliationError("child apply_patch call and writer receipt do not match")

    assistant = [
        (record, item)
        for record, item in response_items(records, "message")
        if item.get("role") == "assistant"
    ]
    if len(assistant) != 1:
        raise ReconciliationError("child has no unique first-turn final")
    final_text = message_text(assistant[0][1])
    if parse_attestation(final_text) != attestation:
        raise ReconciliationError("child final does not equal the durable attestation")

    task_started = [
        record
        for record in records
        if record.get("type") == "event_msg"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("type") == "task_started"
    ]
    task_complete = [
        record
        for record in records
        if record.get("type") == "event_msg"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("type") == "task_complete"
    ]
    aborted = [
        record
        for record in records
        if record.get("type") == "event_msg"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("type") == "turn_aborted"
    ]
    hold_messages = [
        (record, item)
        for record, item in response_items(records, "message")
        if item.get("role") == "user" and message_text(item).endswith(f"Payload:\n{FOLLOWUP_HOLD}")
    ]
    if not (
        len(task_started) == 2
        and len(task_complete) == 1
        and len(aborted) == 1
        and len(hold_messages) == 1
        and aborted[0]["payload"].get("reason") == "interrupted"
        and task_started[0]["payload"].get("turn_id")
        == task_complete[0]["payload"].get("turn_id")
        and task_started[1]["payload"].get("turn_id")
        == aborted[0]["payload"].get("turn_id")
        and task_started[0]["payload"].get("turn_id")
        != task_started[1]["payload"].get("turn_id")
    ):
        raise ReconciliationError("child first completion and second interrupted turn are not exact")
    call_at = parse_timestamp(call_record.get("timestamp"), "child apply_patch")
    output_at = parse_timestamp(output_record.get("timestamp"), "child apply_patch output")
    final_at = parse_timestamp(assistant[0][0].get("timestamp"), "child final")
    complete_at = parse_timestamp(task_complete[0].get("timestamp"), "child first completion")
    hold_at = parse_timestamp(hold_messages[0][0].get("timestamp"), "child close hold")
    second_start_at = parse_timestamp(task_started[1].get("timestamp"), "child second start")
    aborted_at = parse_timestamp(aborted[0].get("timestamp"), "child abort")
    if not (
        call_at < output_at < final_at <= complete_at < second_start_at
        and second_start_at <= hold_at < aborted_at <= close_returned_at
    ):
        raise ReconciliationError("child write, report, hold, and close ordering is invalid")
    return {
        "final_text": final_text,
        "first_turn_completed_at": complete_at,
        "second_turn_started_at": second_start_at,
        "turn_aborted_at": aborted_at,
    }


def validate_parent_lifecycle(
    records: list[dict[str, Any]],
    capsule: dict[str, Any],
    binding: dict[str, Any],
    assignment: str,
    child_final: str,
    child_first_completed_at: dt.datetime,
) -> dict[str, Any]:
    calls = response_items(records, "function_call")
    selected = [(record, item) for record, item in calls if item.get("namespace") == TOOL_NAMESPACE]
    if len(calls) != len(selected) or [item.get("name") for _, item in selected] != PARENT_CALLS:
        raise ReconciliationError("parent tool order is not exact write/wait/followup/list/close/list")
    outputs = {
        item.get("call_id"): (record, item)
        for record, item in response_items(records, "function_call_output")
    }
    if any(item.get("call_id") not in outputs for _, item in selected):
        raise ReconciliationError("parent lifecycle has a missing output")
    canonical_path = capsule["canonical_agent_path"]
    child_thread = binding["child_thread_id"]

    spawn_record, spawn = selected[0]
    if not (
        spawn.get("call_id") == capsule["spawn_tool_use_id"]
        and json_object(spawn.get("arguments"), "spawn arguments")
        == {
            "agent_type": AGENT_TYPE,
            "task_name": capsule["requested_task_name"],
            "fork_turns": "none",
            "message": assignment,
        }
    ):
        raise ReconciliationError("parent spawn does not match the durable assignment")

    wait_record, wait_call = selected[1]
    wait_output = json_object(outputs[wait_call["call_id"]][1].get("output"), "wait output")
    if not (
        json_object(wait_call.get("arguments"), "wait arguments") == {"timeout_ms": 60000}
        and wait_output == {"message": "Wait completed.", "timed_out": False}
    ):
        raise ReconciliationError("parent did not observe the accepted first-turn completion")
    callbacks = [
        (record, item)
        for record, item in response_items(records, "message")
        if item.get("role") == "user"
        and message_text(item).startswith("Message Type: FINAL_ANSWER\n")
    ]
    expected_callback = (
        "Message Type: FINAL_ANSWER\n"
        "Task name: /root\n"
        f"Sender: {canonical_path}\n"
        f"Payload:\n{child_final}"
    )
    if len(callbacks) != 1 or message_text(callbacks[0][1]) != expected_callback:
        raise ReconciliationError("parent callback is not byte-identical to the child final")

    follow_record, follow = selected[2]
    if json_object(follow.get("arguments"), "follow-up arguments") != {
        "target": canonical_path,
        "message": FOLLOWUP_HOLD,
    }:
        raise ReconciliationError("parent follow-up does not carry the exact close hold")
    if outputs[follow["call_id"]][1].get("output") != "":
        raise ReconciliationError("parent follow-up was not accepted")

    pre_record, pre_call = selected[3]
    pre_list = json_object(outputs[pre_call["call_id"]][1].get("output"), "pre-close list output")
    if not any(
        isinstance(agent, dict)
        and agent.get("agent_name") == canonical_path
        and agent.get("agent_status") == "running"
        for agent in pre_list.get("agents", [])
    ):
        raise ReconciliationError("pre-close list does not show the resumed child running")

    close_record, close_call = selected[4]
    if json_object(close_call.get("arguments"), "close arguments") != {"target": canonical_path}:
        raise ReconciliationError("close target is not the canonical AgentPath")
    close_output_record, close_output = outputs[close_call["call_id"]]
    close = json_object(close_output.get("output"), "close output")
    empty_map = {child_thread: []}
    if not (
        set(close) == CLOSE_FIELDS
        and close["previous_status"] == "running"
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
        raise ReconciliationError("close receipt does not prove the bounded write actor barrier")

    post_record, post_call = selected[5]
    post_list = json_object(outputs[post_call["call_id"]][1].get("output"), "post-close list output")
    if any(
        isinstance(agent, dict) and agent.get("agent_name") == canonical_path
        for agent in post_list.get("agents", [])
    ):
        raise ReconciliationError("child remains in the post-close live tree")
    callback_at = parse_timestamp(callbacks[0][0].get("timestamp"), "parent callback")
    wait_at = parse_timestamp(wait_record.get("timestamp"), "parent wait")
    follow_at = parse_timestamp(follow_record.get("timestamp"), "parent follow-up")
    pre_at = parse_timestamp(pre_record.get("timestamp"), "parent pre-close list")
    close_at = parse_timestamp(close_record.get("timestamp"), "parent close")
    close_returned_at = parse_timestamp(close_output_record.get("timestamp"), "close output")
    post_at = parse_timestamp(post_record.get("timestamp"), "parent post-close list")
    if not (
        parse_timestamp(spawn_record.get("timestamp"), "parent spawn")
        < wait_at
        < child_first_completed_at
        <= callback_at
        < follow_at
        < pre_at
        < close_at
        < close_returned_at
        < post_at
    ):
        raise ReconciliationError("parent callback, resumed hold, and close ordering is invalid")
    return {
        "close_tool_use_id": close_call["call_id"],
        "close_receipt": close,
        "close_receipt_sha256": sha256_json(close),
        "terminated_at": close_returned_at,
    }


def validate_hook_chain(
    chain: dict[str, Any],
    capsule: dict[str, Any],
    binding: dict[str, Any],
    writer_receipt: dict[str, Any],
) -> list[dict[str, Any]]:
    events = chain.get("events")
    if not isinstance(events, list):
        raise ReconciliationError("Hook chain has no events")
    selected = [
        event
        for event in events
        if isinstance(event, dict)
        and isinstance(event.get("actor"), dict)
        and event["actor"].get("runtime_session_id") == capsule["runtime_session_id"]
    ]
    if len(selected) != 5:
        raise ReconciliationError("write-then-close run does not have five exact Hook events")
    expected = [
        ("PreToolUse", "target_spawn"),
        ("SubagentStart", "target_child"),
        ("PreToolUse", "target_child"),
        ("PostToolUse", "target_child"),
        ("SubagentStop", "target_child"),
    ]
    if [(event.get("hook_event_name"), event.get("scope")) for event in selected] != expected:
        raise ReconciliationError("Hook event kinds are not exact")
    sequences = [event.get("sequence") for event in selected]
    if not all(isinstance(value, int) for value in sequences) or sequences != list(
        range(sequences[0], sequences[0] + 5)
    ):
        raise ReconciliationError("Hook events are not contiguous")
    child_thread = binding["child_thread_id"]
    if not (
        selected[0].get("tool_use_id") == capsule["spawn_tool_use_id"]
        and selected[0]["actor"].get("thread_id") == capsule["parent_thread_id"]
        and all(event["actor"].get("thread_id") == child_thread for event in selected[1:])
        and all(
            event["actor"].get("canonical_agent_path") == capsule["canonical_agent_path"]
            for event in selected[1:]
        )
        and selected[2].get("tool_name") == "apply_patch"
        and selected[3].get("tool_name") == "apply_patch"
        and selected[2].get("tool_use_id") == writer_receipt["tool_use_id"]
        and selected[3].get("tool_use_id") == writer_receipt["tool_use_id"]
    ):
        raise ReconciliationError("Hook events do not bind the exact write identity")
    return selected


def observe_barrier(root: Path, candidate: Path) -> dict[str, Any]:
    return {
        "observed_at": dt.datetime.now(dt.timezone.utc),
        "snapshot": collect_git_snapshot(str(root)),
        "candidate_process_absent": process_absent(candidate),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--assignment-id", required=True)
    parser.add_argument("--parent-rollout", type=Path, required=True)
    parser.add_argument("--child-rollout", type=Path, required=True)
    parser.add_argument("--hook-chain", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--barrier-delay-seconds", type=float, default=2.0)
    arguments = parser.parse_args()
    try:
        if not 0 <= arguments.barrier_delay_seconds <= 10:
            raise ReconciliationError("barrier delay must be between zero and ten seconds")
        target = arguments.target.resolve(strict=True)
        candidate = arguments.candidate.resolve(strict=True)
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise ReconciliationError("candidate is not an executable regular file")
        candidate_sha256 = sha256_file(candidate)
        if candidate_sha256 != arguments.expected_candidate_sha256:
            raise ReconciliationError("candidate digest does not match")

        store = StateStore(arguments.state_directory)
        reported_path = store.path("reported", arguments.assignment_id)
        if not reported_path.is_file():
            raise ReconciliationError("exact reported assignment was not found")
        envelope = read_json(reported_path)
        parent_records = read_jsonl(arguments.parent_rollout)
        child_records = read_jsonl(arguments.child_rollout)
        capsule, binding, attestation = validate_identity(
            envelope,
            parent_records,
            child_records,
            target,
        )
        writer_receipt = validate_writer_evidence(
            store,
            capsule,
            binding,
            attestation,
            target,
        )

        first = observe_barrier(Path(capsule["root"]["path"]), candidate)
        parent_preview = validate_parent_lifecycle(
            parent_records,
            capsule,
            binding,
            envelope["assignment"],
            message_text(
                next(
                    item
                    for _, item in response_items(child_records, "message")
                    if item.get("role") == "assistant"
                )
            ),
            parse_timestamp(
                next(
                    record.get("timestamp")
                    for record in child_records
                    if record.get("type") == "event_msg"
                    and isinstance(record.get("payload"), dict)
                    and record["payload"].get("type") == "task_complete"
                ),
                "child first completion",
            ),
        )
        child_lifecycle = validate_child_lifecycle(
            child_records,
            capsule,
            attestation,
            writer_receipt,
            target,
            parent_preview["terminated_at"],
        )
        lifecycle = validate_parent_lifecycle(
            parent_records,
            capsule,
            binding,
            envelope["assignment"],
            child_lifecycle["final_text"],
            child_lifecycle["first_turn_completed_at"],
        )
        hook_events = validate_hook_chain(
            read_json(arguments.hook_chain),
            capsule,
            binding,
            writer_receipt,
        )
        time.sleep(arguments.barrier_delay_seconds)
        second = observe_barrier(Path(capsule["root"]["path"]), candidate)
        expected_snapshot = expected_snapshot_from_attestation(attestation)
        if not (
            first["candidate_process_absent"]
            and second["candidate_process_absent"]
            and first["snapshot"] == second["snapshot"] == expected_snapshot
        ):
            raise ReconciliationError("post-close write actor disk barrier is not stable")
        for claim_path in (arguments.state_directory / "writer_claim").glob("*.json"):
            claim = read_json(claim_path)
            if Path(str(claim.get("root", ""))).resolve() == Path(capsule["root"]["path"]):
                raise ReconciliationError("writer claim remains in the closed write actor root")

        parent_sha256 = sha256_file(arguments.parent_rollout)
        child_sha256 = sha256_file(arguments.child_rollout)
        evidence = {
            "schema": 1,
            "reason": "native_close_agent_after_accepted_write_report",
            "classification": "closed_catalog_write_actor_terminated_and_mutations_quiesced",
            "runtime_session_id": capsule["runtime_session_id"],
            "child_thread_id": binding["child_thread_id"],
            "canonical_agent_path": capsule["canonical_agent_path"],
            "writer_receipt_sha256": writer_receipt["receipt_sha256"],
            "close_tool_use_id": lifecycle["close_tool_use_id"],
            "close_receipt_sha256": lifecycle["close_receipt_sha256"],
            "parent_rollout_sha256": parent_sha256,
            "child_rollout_sha256": child_sha256,
            "hook_sequences": [event["sequence"] for event in hook_events],
            "first_turn_completed_at": child_lifecycle["first_turn_completed_at"].isoformat(),
            "second_turn_started_at": child_lifecycle["second_turn_started_at"].isoformat(),
            "child_turn_aborted_at": child_lifecycle["turn_aborted_at"].isoformat(),
            "terminated_at": lifecycle["terminated_at"].isoformat(),
            "process_tree_quiescence_claimed": False,
        }
        store.freeze_reported_after_termination(arguments.assignment_id, evidence)
        receipt_id = (
            f"native-write-close:{lifecycle['close_tool_use_id']}:"
            f"{lifecycle['close_receipt_sha256'][:16]}"
        )
        barrier_path = store.record_quiescence_barrier(
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
        barrier = read_json(barrier_path)
        result = {
            "valid": True,
            "assignment_id": arguments.assignment_id,
            "runtime_session_id": capsule["runtime_session_id"],
            "child_thread_id": binding["child_thread_id"],
            "canonical_agent_path": capsule["canonical_agent_path"],
            "writer_receipt_sha256": writer_receipt["receipt_sha256"],
            "close_receipt_sha256": lifecycle["close_receipt_sha256"],
            "termination_evidence_sha256": sha256_json(evidence),
            "quiescence_barrier_sha256": barrier["barrier_sha256"],
            "snapshot_sha256": barrier["snapshot_sha256"],
            "candidate_sha256": candidate_sha256,
            "parent_rollout_sha256": parent_sha256,
            "child_rollout_sha256": child_sha256,
            "hook_sequences": evidence["hook_sequences"],
            "process_tree_quiescence_claimed": False,
            "direct_write_qualified": False,
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return 0
    except (
        OSError,
        StopIteration,
        subprocess.SubprocessError,
        StateError,
        ReconciliationError,
        ValueError,
    ) as error:
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
