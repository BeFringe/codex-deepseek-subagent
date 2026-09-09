#!/usr/bin/env python3

"""Reconcile one exact post-quiescence child handover, replacement, and close."""

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
from typing import Any, Mapping


SOURCE_ROOT = Path(__file__).resolve().parents[1]
HOOKS = SOURCE_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from compatibility_state import (  # noqa: E402
    _validate_quiescence_barrier,
    git_snapshot_sha256,
    StateError,
    StateStore,
    validate_capsule,
)
from reconcile_g4_read_only_close import (  # noqa: E402
    AGENT_TYPE,
    ReconciliationError,
    parse_timestamp,
    read_json,
    read_jsonl,
    response_items,
    session_meta,
    sha256_file,
    sha256_json,
)
from reconcile_g4_write_then_close import (  # noqa: E402
    expected_snapshot_from_attestation,
    FOLLOWUP_HOLD,
    message_text,
    observe_barrier,
    validate_hook_chain,
    validate_parent_lifecycle,
)
from runtime_guard import parse_attestation  # noqa: E402


PRIOR_TARGET_CONTENT = "G4_CHILD_WRITE_QUALIFIED\n"
TARGET_CONTENT = "G4_HANDOVER_WRITE_QUALIFIED\n"
VERIFICATION = "exact-path post-quiescence child handover qualification probe"
HANDOVER_INVARIANT = "exact prior quiescence barrier handover"


def capture_snapshot(capsule: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "root": capsule["root"]["path"],
        "branch": capsule["root"]["branch"],
        "head": capsule["root"]["base_commit"],
        "index_changed": capsule["root"]["base_index_changed"],
        "git_status_short": capsule["root"]["base_git_status_short"],
        "changed_paths": [
            {
                "path": item["path"],
                "kind": item["kind"],
                "sha256": item["sha256"],
            }
            for item in capsule["preexisting_dirty"]
        ],
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
        raise ReconciliationError("reported handover lacks binding or final attestation")
    root = Path(capsule["root"]["path"])
    relative = target.relative_to(root).as_posix()
    prior_sha256 = hashlib.sha256(PRIOR_TARGET_CONTENT.encode("utf-8")).hexdigest()
    expected_dirty = [
        {
            "path": relative,
            "status": f"?? {relative}\0",
            "kind": "file",
            "sha256": prior_sha256,
        }
    ]
    handovers = capsule["ownership_handover"]
    captured = capture_snapshot(capsule)
    if not (
        capsule["assignment_mutation_mode"] == "write"
        and capsule["parent_recorded_user_write_intent"] == "allow"
        and capsule["owned_paths"] == [relative]
        and capsule["excluded_paths"] == []
        and not any(capsule["git_authority"].values())
        and capsule["verification"] == [VERIFICATION]
        and HANDOVER_INVARIANT
        in capsule["execution_contract"]["required_invariants"]
        and capsule["trusted_host_user_write_consent"].get("status") == "verified"
        and capsule["trusted_host_user_write_consent"].get("source")
        == "qualification_hook_exact_path"
        and capsule["preexisting_dirty"] == expected_dirty
        and capsule["root"]["base_index_changed"] is False
        and capsule["root"]["base_git_status_short"] == f"?? {relative}"
        and len(handovers) == 1
        and handovers[0]["snapshot_sha256"] == capsule["capture_snapshot_sha256"]
        and git_snapshot_sha256(captured) == capsule["capture_snapshot_sha256"]
    ):
        raise ReconciliationError("reported assignment does not have the exact handover ceiling")

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
        raise ReconciliationError("parent SessionMeta does not match the handover capsule")
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
        raise ReconciliationError("child SessionMeta does not match the handover binding")
    return capsule, binding, attestation


def validate_prior_handover(
    store: StateStore,
    capsule: dict[str, Any],
    target: Path,
    *,
    expected_prior_assignment_id: str,
    expected_prior_barrier_sha256: str,
) -> dict[str, Any]:
    handover = capsule["ownership_handover"][0]
    if not (
        handover["prior_assignment_id"] == expected_prior_assignment_id
        and handover["barrier_sha256"] == expected_prior_barrier_sha256
    ):
        raise ReconciliationError("capsule handover does not match the expected prior receipt")
    unresolved_path = store.path("unresolved", expected_prior_assignment_id)
    barrier_path = store.path("quiescence", expected_prior_assignment_id)
    if not unresolved_path.is_file() or not barrier_path.is_file():
        raise ReconciliationError("prior unresolved assignment or barrier is absent")
    prior = read_json(unresolved_path)
    prior_capsule = validate_capsule(prior.get("capsule"), prior.get("assignment"))
    barrier = _validate_quiescence_barrier(read_json(barrier_path))
    relative = target.relative_to(Path(capsule["root"]["path"])).as_posix()
    prior_snapshot = barrier["snapshot"]
    prior_final = prior.get("final_attestation")
    prior_binding = prior.get("binding")
    expected_prior_snapshot = capture_snapshot(capsule)
    termination = prior.get("termination_evidence")
    if not (
        prior_capsule["assignment_id"] == expected_prior_assignment_id
        and prior_capsule["root"]["path"] == capsule["root"]["path"]
        and prior_capsule["owned_paths"] == [relative]
        and isinstance(prior_binding, dict)
        and isinstance(prior_final, dict)
        and isinstance(termination, dict)
        and termination.get("reason") == "native_close_agent_after_accepted_write_report"
        and termination.get("classification")
        == "closed_catalog_write_actor_terminated_and_mutations_quiesced"
        and barrier["prior_assignment_id"] == expected_prior_assignment_id
        and barrier["barrier_sha256"] == expected_prior_barrier_sha256
        and barrier["snapshot_sha256"] == handover["snapshot_sha256"]
        and prior_snapshot == expected_prior_snapshot
        and expected_snapshot_from_attestation(prior_final) == prior_snapshot
        and barrier["runtime_session_id"] == prior_capsule["runtime_session_id"]
        and barrier["terminated_child_thread_id"] == prior_binding.get("child_thread_id")
    ):
        raise ReconciliationError("prior assignment, final, barrier, and replacement do not join")
    return barrier


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
        and attestation.get("verification")
        == [{"command": VERIFICATION, "exit_code": 0}]
    ):
        raise ReconciliationError("reported final is not an accepted handover attestation")
    provenance = attestation.get("authority_provenance")
    if not isinstance(provenance, dict):
        raise ReconciliationError("reported final has no provenance")
    actor = {
        "runtime_session_id": capsule["runtime_session_id"],
        "thread_id": binding["child_thread_id"],
        "agent_type": AGENT_TYPE,
        "canonical_agent_path": capsule["canonical_agent_path"],
    }
    receipt = store.find_writer_receipt(
        actor,
        provenance.get("derivation_receipt_sha256"),
    )
    expected_snapshot = expected_snapshot_from_attestation(attestation)
    if not (
        receipt["actor"] == actor
        and receipt["root"] == capsule["root"]["path"]
        and receipt["paths"] == capsule["owned_paths"]
        and receipt["tool_name"] == "apply_patch"
        and receipt["ownership_handover"] == capsule["ownership_handover"]
        and receipt["before_snapshot"] == capture_snapshot(capsule)
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
        raise ReconciliationError("handover receipt, attestation, and target bytes do not join")
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
        f"*** Update File: {target}\n"
        "@@\n"
        "-G4_CHILD_WRITE_QUALIFIED\n"
        "+G4_HANDOVER_WRITE_QUALIFIED\n"
        "*** End Patch\n"
    )
    if len(calls) != 1 or len(outputs) != 1:
        raise ReconciliationError("replacement child did not make exactly one custom tool call")
    call_record, call = calls[0]
    output_record, output = outputs[0]
    if not (
        call.get("name") == "apply_patch"
        and call.get("call_id") == writer_receipt["tool_use_id"]
        and call.get("input") == expected_patch
        and output.get("call_id") == call.get("call_id")
        and "Success." in str(output.get("output"))
    ):
        raise ReconciliationError("replacement apply_patch and writer receipt do not match")

    assistant = [
        (record, item)
        for record, item in response_items(records, "message")
        if item.get("role") == "assistant"
    ]
    if len(assistant) != 1:
        raise ReconciliationError("replacement child has no unique first-turn final")
    final_text = message_text(assistant[0][1])
    if parse_attestation(final_text) != attestation:
        raise ReconciliationError("replacement child final does not equal durable attestation")
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
        if item.get("role") == "user"
        and message_text(item).endswith(f"Payload:\n{FOLLOWUP_HOLD}")
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
        raise ReconciliationError("replacement completion and interrupted close hold are not exact")
    call_at = parse_timestamp(call_record.get("timestamp"), "replacement apply_patch")
    output_at = parse_timestamp(output_record.get("timestamp"), "replacement output")
    final_at = parse_timestamp(assistant[0][0].get("timestamp"), "replacement final")
    complete_at = parse_timestamp(task_complete[0].get("timestamp"), "replacement completion")
    hold_at = parse_timestamp(hold_messages[0][0].get("timestamp"), "replacement close hold")
    second_start_at = parse_timestamp(task_started[1].get("timestamp"), "replacement second start")
    aborted_at = parse_timestamp(aborted[0].get("timestamp"), "replacement abort")
    if not (
        call_at < output_at < final_at <= complete_at < second_start_at
        and second_start_at <= hold_at < aborted_at <= close_returned_at
    ):
        raise ReconciliationError("replacement write, report, hold, and close ordering is invalid")
    return {
        "final_text": final_text,
        "first_turn_completed_at": complete_at,
        "second_turn_started_at": second_start_at,
        "turn_aborted_at": aborted_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--assignment-id", required=True)
    parser.add_argument("--expected-prior-assignment-id", required=True)
    parser.add_argument("--expected-prior-barrier-sha256", required=True)
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
            raise ReconciliationError("exact reported replacement assignment was not found")
        envelope = read_json(reported_path)
        parent_records = read_jsonl(arguments.parent_rollout)
        child_records = read_jsonl(arguments.child_rollout)
        capsule, binding, attestation = validate_identity(
            envelope,
            parent_records,
            child_records,
            target,
        )
        prior_barrier = validate_prior_handover(
            store,
            capsule,
            target,
            expected_prior_assignment_id=arguments.expected_prior_assignment_id,
            expected_prior_barrier_sha256=arguments.expected_prior_barrier_sha256,
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
                "replacement first completion",
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
            raise ReconciliationError("post-close replacement disk barrier is not stable")
        for claim_path in (arguments.state_directory / "writer_claim").glob("*.json"):
            claim = read_json(claim_path)
            if Path(str(claim.get("root", ""))).resolve() == Path(capsule["root"]["path"]):
                raise ReconciliationError("writer claim remains in the closed replacement root")

        parent_sha256 = sha256_file(arguments.parent_rollout)
        child_sha256 = sha256_file(arguments.child_rollout)
        evidence = {
            "schema": 1,
            "reason": "native_close_agent_after_accepted_handover_report",
            "classification": "closed_catalog_handover_actor_terminated_and_mutations_quiesced",
            "prior_assignment_id": arguments.expected_prior_assignment_id,
            "prior_barrier_sha256": prior_barrier["barrier_sha256"],
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
            f"native-handover-close:{lifecycle['close_tool_use_id']}:"
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
            "prior_assignment_id": arguments.expected_prior_assignment_id,
            "prior_barrier_sha256": prior_barrier["barrier_sha256"],
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
