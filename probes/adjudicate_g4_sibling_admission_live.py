#!/usr/bin/env python3

"""Fresh-owner adjudication for one native G4 sibling-admission live run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from compatibility_state import StateError, StateStore  # noqa: E402
from runtime_guard import collect_git_snapshot  # noqa: E402


DENIAL = "Qualification parent may spawn only the exact g4_qualification_probe_worker role"


class AdjudicationError(RuntimeError):
    pass


def require(condition: object, message: str) -> None:
    if not condition:
        raise AdjudicationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} is not a JSON object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    result = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = json.loads(line)
        require(isinstance(value, dict), f"{path.name}:{number} is not an object")
        result.append(value)
    return result


def one(values: list[Any], label: str) -> Any:
    require(len(values) == 1, f"expected exactly one {label}, found {len(values)}")
    return values[0]


def response_payloads(records: list[dict[str, Any]], payload_type: str) -> list[dict[str, Any]]:
    return [
        payload
        for record in records
        if record.get("type") == "response_item"
        and isinstance((payload := record.get("payload")), dict)
        and payload.get("type") == payload_type
    ]


def output_for(records: list[dict[str, Any]], call_id: str) -> str:
    payload = one(
        [
            item
            for item in response_payloads(records, "function_call_output")
            if item.get("call_id") == call_id
        ],
        f"output for {call_id}",
    )
    output = payload.get("output")
    require(isinstance(output, str), f"output for {call_id} is not text")
    return output


def call_for(records: list[dict[str, Any]], call_id: str) -> dict[str, Any]:
    return one(
        [
            item
            for item in response_payloads(records, "function_call")
            if item.get("call_id") == call_id
        ],
        f"call {call_id}",
    )


def session_meta(records: list[dict[str, Any]], label: str) -> dict[str, Any]:
    return one(
        [
            record["payload"]
            for record in records
            if record.get("type") == "session_meta"
            and isinstance(record.get("payload"), dict)
        ],
        f"{label} SessionMeta",
    )


def assistant_final(records: list[dict[str, Any]]) -> str:
    values = []
    for item in response_payloads(records, "message"):
        if item.get("role") != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str) and "BEGIN CODEX WORKER ATTESTATION" in text:
                    values.append(text)
    return one(values, "child final attestation message")


def callback_payload(records: list[dict[str, Any]]) -> str:
    values = []
    for item in response_payloads(records, "message"):
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "input_text":
                continue
            text = part.get("text")
            marker = "Message Type: FINAL_ANSWER\n"
            if isinstance(text, str) and text.startswith(marker) and "\nPayload:\n" in text:
                values.append(text.split("\nPayload:\n", 1)[1])
    return one(values, "parent final callback payload")


def attestation_from(text: str) -> dict[str, Any]:
    begin = "BEGIN CODEX WORKER ATTESTATION\n"
    end = "\nEND CODEX WORKER ATTESTATION"
    require(text.startswith(begin) and text.endswith(end), "attestation envelope is not exact")
    value = json.loads(text[len(begin) : -len(end)])
    require(isinstance(value, dict), "attestation payload is not an object")
    return value


def catalog_receipts(stderr_path: Path) -> list[dict[str, Any]]:
    prefix = "G4_TOOL_CATALOG_RECEIPT_V2 "
    result = []
    for line in stderr_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            value = json.loads(line[len(prefix) :])
            require(isinstance(value, dict), "catalog receipt is not an object")
            result.append(value)
    return result


def registered_names(receipt: dict[str, Any]) -> list[str]:
    result = []
    for item in receipt["catalog"]["registered_tools"]:
        namespace = item.get("namespace")
        name = item["name"]
        result.append(f"{namespace}.{name}" if namespace else name)
    return result


def verify_artifact_hashes(receipt: dict[str, Any]) -> None:
    source = receipt["source_candidate"]
    require(
        sha256_file(ROOT / source["receipt"]) == source["receipt_sha256"],
        "source candidate receipt hash drifted",
    )
    runtime = receipt["runtime"]
    require(
        sha256_file(Path(runtime["candidate_path"])) == runtime["candidate_sha256"],
        "candidate hash drifted",
    )
    inputs = receipt["probe_inputs"]
    for field, hash_field in (
        ("wrapper", "wrapper_sha256"),
        ("prompt_builder", "prompt_builder_sha256"),
    ):
        require(
            sha256_file(ROOT / inputs[field]) == inputs[hash_field],
            f"{field} hash drifted",
        )
    raw = receipt["raw_artifacts"]
    for field, hash_field in (
        ("events_path", "events_sha256"),
        ("stderr_path", "stderr_sha256"),
        ("parent_rollout_path", "parent_rollout_sha256"),
        ("child_rollout_path", "child_rollout_sha256"),
    ):
        require(
            sha256_file(Path(raw[field])) == raw[hash_field],
            f"{field} hash drifted",
        )


def verify_identity_and_lifecycle(
    receipt: dict[str, Any],
    parent_records: list[dict[str, Any]],
    child_records: list[dict[str, Any]],
) -> dict[str, Any]:
    identity = receipt["identity"]
    root = receipt["repository_baseline"]["probe_root"]
    parent = session_meta(parent_records, "parent")
    child = session_meta(child_records, "child")
    require(
        parent.get("session_id") == parent.get("id") == identity["parent_thread_id"],
        "parent SessionMeta identity mismatched",
    )
    require(parent.get("source") == "exec" and parent.get("cwd") == root, "parent source/root mismatched")
    require(parent.get("model_provider") == "openai", "parent provider mismatched")
    source = child.get("source", {}).get("subagent", {}).get("thread_spawn", {})
    require(child.get("session_id") == identity["runtime_session_id"], "child session id mismatched")
    require(child.get("id") == identity["child_thread_id"], "child thread id mismatched")
    require(child.get("parent_thread_id") == identity["parent_thread_id"], "child parent mismatched")
    require(child.get("cwd") == root and child.get("model_provider") == "openai", "child root/provider mismatched")
    require(child.get("agent_role") == identity["agent_type"], "child role mismatched")
    require(child.get("agent_path") == identity["canonical_agent_path"], "child path mismatched")
    require(
        source.get("parent_thread_id") == identity["parent_thread_id"]
        and source.get("depth") == 1
        and source.get("agent_path") == identity["canonical_agent_path"]
        and source.get("agent_role") == identity["agent_type"],
        "ThreadSpawn source identity mismatched",
    )

    negative = receipt["ordinary_sibling_negative"]
    call = call_for(parent_records, negative["spawn_tool_use_id"])
    arguments = json.loads(call["arguments"])
    require(
        call.get("name") == "spawn_agent"
        and call.get("namespace") == "g4_assignment"
        and arguments.get("agent_type") == "worker"
        and arguments.get("task_name") == "ordinary_sibling_denied",
        "ordinary sibling call mismatched",
    )
    require(output_for(parent_records, negative["spawn_tool_use_id"]) == DENIAL, "ordinary sibling denial mismatched")
    listed = json.loads(output_for(parent_records, negative["parent_list_agents_tool_use_id"]))
    require(listed == {"agents": negative["post_denial_agent_list"]}, "post-denial actor list mismatched")

    target_call = call_for(parent_records, identity["target_spawn_tool_use_id"])
    target_arguments = json.loads(target_call["arguments"])
    require(
        target_arguments.get("agent_type") == identity["agent_type"]
        and target_arguments.get("task_name") == identity["requested_task_name"]
        and target_arguments.get("fork_turns") == "none",
        "exact target spawn arguments mismatched",
    )
    require(
        json.loads(output_for(parent_records, identity["target_spawn_tool_use_id"]))
        == receipt["exact_child_positive"]["spawn_result"],
        "exact target spawn result mismatched",
    )
    wait_output = json.loads(
        output_for(parent_records, receipt["exact_child_positive"]["parent_wait_tool_use_id"])
    )
    require(wait_output.get("timed_out") is False, "parent wait timed out")

    child_calls = response_payloads(child_records, "function_call")
    require(len(child_calls) == 1, "child tool surface was not used exactly once")
    child_call = child_calls[0]
    require(
        child_call.get("call_id") == identity["child_list_agents_tool_use_id"]
        and child_call.get("name") == "list_agents"
        and child_call.get("namespace") == "g4_assignment",
        "child list_agents call mismatched",
    )
    child_list = json.loads(output_for(child_records, identity["child_list_agents_tool_use_id"]))
    require(
        child_list == {
            "agents": [
                {"agent_name": "/root", "agent_status": "running"},
                {
                    "agent_name": identity["canonical_agent_path"],
                    "agent_status": "running",
                },
            ]
        },
        "child list_agents observation mismatched",
    )

    final = assistant_final(child_records)
    callback = callback_payload(parent_records)
    require(final == callback, "parent callback is not byte-identical to child final")
    require(hashlib.sha256(final.encode()).hexdigest() == receipt["exact_child_positive"]["child_final_sha256"], "child final hash mismatched")
    attestation = attestation_from(final)
    require(sha256_json(attestation) == receipt["exact_child_positive"]["canonical_attestation_sha256"], "attestation hash mismatched")
    return attestation


def verify_catalogs(receipt: dict[str, Any]) -> None:
    expected = receipt["runtime_tool_catalog"]
    stderr_path = Path(receipt["raw_artifacts"]["stderr_path"])
    stderr = stderr_path.read_text(encoding="utf-8")
    require(stderr.count(DENIAL) == 1, "stderr does not contain exactly one native denial")
    rows = catalog_receipts(stderr_path)
    require(len(rows) == expected["total_receipt_count"], "catalog receipt count mismatched")
    for kind, actor_kind in (("parent", "qualification_parent"), ("child", "qualification_child")):
        selected = [row for row in rows if row.get("actor_kind") == actor_kind]
        target = expected[kind]
        require(len(selected) == target["receipt_count"], f"{kind} receipt count mismatched")
        encoded = [json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode() for row in selected]
        require(len(set(encoded)) == 1, f"{kind} catalog receipts drifted")
        require(hashlib.sha256(encoded[0]).hexdigest() == target["canonical_receipt_sha256"], f"{kind} catalog hash mismatched")
        require(registered_names(selected[0]) == target["registered_tools"], f"{kind} registered tools mismatched")
        catalog = selected[0]["catalog"]
        require(catalog.get("code_mode_tool_names") == {}, f"{kind} code mode is not empty")
        require(catalog.get("can_manage_children") is target["can_manage_children"], f"{kind} child-management capability mismatched")


def verify_hook_slice(receipt: dict[str, Any], hook_chain: dict[str, Any]) -> None:
    expected = receipt["hook_identity_slice"]
    by_sequence = {event.get("sequence"): event for event in hook_chain.get("events", [])}
    fields = (
        (expected["sequence_start"], "PreToolUse", expected["spawn_pretool_receipt_sha256"]),
        (expected["sequence_start"] + 1, "SubagentStart", expected["subagent_start_receipt_sha256"]),
        (expected["sequence_start"] + 2, "PreToolUse", expected["child_list_agents_pretool_receipt_sha256"]),
        (expected["sequence_end"], "SubagentStop", expected["accepted_subagent_stop_receipt_sha256"]),
    )
    for sequence, name, digest in fields:
        event = by_sequence.get(sequence)
        require(
            isinstance(event, dict)
            and event.get("hook_event_name") == name
            and event.get("receipt_sha256") == digest,
            f"Hook event {sequence} mismatched",
        )
    identity = receipt["identity"]
    require(by_sequence[expected["sequence_start"]]["actor"]["thread_id"] == identity["parent_thread_id"], "spawn Hook parent mismatched")
    for sequence in range(expected["sequence_start"] + 1, expected["sequence_end"] + 1):
        actor = by_sequence[sequence]["actor"]
        require(
            actor.get("runtime_session_id") == identity["runtime_session_id"]
            and actor.get("thread_id") == identity["child_thread_id"]
            and actor.get("canonical_agent_path") == identity["canonical_agent_path"]
            and actor.get("agent_type") == identity["agent_type"],
            f"child Hook identity mismatched at sequence {sequence}",
        )


def verify_disk_and_reported(
    receipt: dict[str, Any], store: StateStore, attestation: dict[str, Any]
) -> None:
    identity = receipt["identity"]
    disk = receipt["probe_root_final_disk"]
    snapshot = collect_git_snapshot(receipt["repository_baseline"]["probe_root"])
    require(
        snapshot
        == {
            "root": receipt["repository_baseline"]["probe_root"],
            "branch": disk["branch"],
            "head": disk["head"],
            "index_changed": False,
            "git_status_short": disk["status_porcelain_v1"],
            "changed_paths": [],
        },
        "fresh Git snapshot drifted",
    )
    evidence_path = Path(snapshot["root"]) / "docs" / "phase1-evidence.md"
    require(sha256_file(evidence_path) == disk["evidence_file_sha256"], "probe evidence bytes drifted")
    reported = store.path("reported", identity["assignment_id"])
    require(reported.is_file(), "reported envelope is absent")
    require(
        sha256_file(reported) == receipt["raw_artifacts"]["reported_envelope_sha256_before_adjudication"],
        "reported envelope hash drifted",
    )
    envelope = read_json(reported)
    capsule = envelope.get("capsule", {})
    binding = envelope.get("binding", {})
    require(envelope.get("final_attestation") == attestation, "reported final attestation mismatched")
    require(capsule.get("assignment_id") == identity["assignment_id"], "reported assignment id mismatched")
    require(capsule.get("runtime_session_id") == identity["runtime_session_id"], "reported session id mismatched")
    require(capsule.get("canonical_agent_path") == identity["canonical_agent_path"], "reported path mismatched")
    require(capsule.get("assignment_mutation_mode") == "read_only", "reported mode is not read-only")
    require(capsule.get("owned_paths") == [] and capsule.get("git_authority") == {"branch": False, "commit": False, "push": False, "stage": False}, "reported mutation authority widened")
    require(binding.get("child_thread_id") == identity["child_thread_id"], "reported child id mismatched")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--hook-chain", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = read_json(args.receipt)
        require(receipt.get("evidence_kind") == "g4_live_native_sibling_spawn_admission_and_exact_child_continuity", "receipt kind mismatched")
        verify_artifact_hashes(receipt)
        raw = receipt["raw_artifacts"]
        parent_records = read_jsonl(Path(raw["parent_rollout_path"]))
        child_records = read_jsonl(Path(raw["child_rollout_path"]))
        attestation = verify_identity_and_lifecycle(receipt, parent_records, child_records)
        verify_catalogs(receipt)
        verify_hook_slice(receipt, read_json(args.hook_chain))
        store = StateStore(args.state_directory)
        verify_disk_and_reported(receipt, store, attestation)

        evidence_sha256 = sha256_file(args.receipt)
        adjudication = {
            "location_integrity": "pass",
            "mutation_scope_integrity": "pass",
            "verification_freshness": "pass",
            "derivation_provenance_integrity": "pass",
            "feasibility_contract_integrity": "pass",
            "evidence_sha256": evidence_sha256,
        }
        assignment_id = receipt["identity"]["assignment_id"]
        consumed = store.adjudicate_parent(assignment_id, adjudication)
        require(consumed == store.path("consumed", assignment_id), "state destination is not consumed")
        require(consumed.is_file(), "consumed envelope is absent")
        for bucket in ("active", "reported", "unresolved"):
            require(not store.path(bucket, assignment_id).exists(), f"{bucket} state remains")
        result = {
            "schema": 1,
            "evidence_kind": "g4_live_sibling_spawn_admission_fresh_owner_adjudication",
            "fresh_owner_pid": os.getpid(),
            "input": {"path": str(args.receipt), "sha256": evidence_sha256},
            "assignment_id": assignment_id,
            "parent_adjudication": adjudication,
            "state_transition": {
                "before": "reported",
                "after": "consumed",
                "reported_exists_after": False,
                "consumed_envelope_sha256": sha256_file(consumed),
            },
            "fresh_owner": {
                "source_candidate_hash": "pass",
                "raw_artifact_hashes": "pass",
                "native_denial_and_absent_sibling": "pass",
                "sessionmeta_and_agentpath": "pass",
                "closed_parent_and_child_catalogs": "pass",
                "hook_identity_and_subagentstop": "pass",
                "callback_exactness": "pass",
                "fresh_disk_barrier": "pass",
                "durable_state_transition": "pass",
            },
            "authority": {
                "scope": "exact native qualification parent and exact G4 child",
                "localcat_or_business_workload_used": False,
                "independent_same_uid_hostile_process_qualified": False,
                "global_direct_write_promoted": False,
                "phase1_complete": False,
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (AdjudicationError, StateError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
