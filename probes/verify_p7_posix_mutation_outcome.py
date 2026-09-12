#!/usr/bin/env python3

"""Fresh-process verification of one isolated macOS G4 mutation outcome."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys

from adjudicate_g4_sibling_admission_live import (
    attestation_from,
    callback_payload,
    catalog_receipts,
    one,
    output_for,
    read_json,
    read_jsonl,
    registered_names,
    require,
    response_payloads,
    session_meta,
)
from adjudicate_p7_windows_live import verify_close
from private_output import open_private_output
from run_p7_posix_mutation import (
    AGENT_TYPE,
    PROVIDER,
    ROOT,
    SOURCE_BASE,
    invocation,
    sha256_file,
    snapshot,
)


SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"[A-Fa-f0-9]{24,}\.[A-Za-z0-9_-]{16,}"),
)


def text_parts(item: dict[str, object]) -> list[str]:
    content = item.get("content")
    if not isinstance(content, list):
        return []
    return [
        part["text"]
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]


def accepted_final(records: list[dict[str, object]], attestation: dict[str, object]) -> str:
    matches: list[str] = []
    for item in response_payloads(records, "message"):
        if item.get("role") != "assistant":
            continue
        for text in text_parts(item):
            if not text.startswith("BEGIN CODEX WORKER ATTESTATION\n"):
                continue
            try:
                parsed = attestation_from(text)
            except Exception:
                continue
            if parsed == attestation:
                matches.append(text)
    return one(matches, "accepted child final")


def expected_snapshot(manifest: dict[str, object]) -> dict[str, object]:
    baseline = json.loads(json.dumps(manifest["baseline"]))
    files = baseline["files"]
    if manifest["mutation_case"] == "positive":
        files["qualified.txt"] = hashlib.sha256(b"G4_CHILD_WRITE_QUALIFIED\n").hexdigest()
        baseline["status"] = "?? qualified.txt"
    else:
        files["foreign.txt"] = hashlib.sha256(b"FOREIGN_DIRTY_BYTES_MUST_SURVIVE\n").hexdigest()
        baseline["status"] = " M foreign.txt"
    return baseline


def raw_hook_events(directory: Path) -> list[dict[str, object]]:
    result = [read_json(path) for path in sorted(directory.glob("*.json"))]
    require(result, "raw Hook observations are absent")
    for event in result:
        raw = event["stdin_utf8"].encode("utf-8")
        require(
            event["exit_code"] == 0
            and "observer_error" not in event
            and event["stdin_bytes"] == len(raw)
            and event["stdin_sha256"] == hashlib.sha256(raw).hexdigest()
            and json.loads(raw) == event["input"],
            "raw Hook observation is not self-consistent",
        )
    return result


def verify_catalog(stderr: Path) -> None:
    receipts = catalog_receipts(stderr)
    require(receipts, "closed tool-catalog receipts are absent")
    children = [item for item in receipts if item.get("actor_kind") == "qualification_child"]
    require(children, "child tool-catalog receipt is absent")
    for receipt in children:
        require(
            set(registered_names(receipt)) == {"apply_patch", "list_agents", "view_image"}
            and receipt["catalog"].get("code_mode_tool_names") == {}
            and receipt["catalog"].get("can_manage_children") is False,
            "child tool catalog is widened or incomplete",
        )


def verify(path: Path) -> dict[str, object]:
    manifest = read_json(path)
    require(platform.system() == "Darwin" and manifest["platform"]["system"] == "Darwin", "native macOS required")
    require(manifest["classification"] == "p7_macos_mutation_raw_attempt", "wrong manifest kind")
    require(manifest["mutation_case"] in {"positive", "negative"}, "wrong mutation case")
    require(manifest["runner_pid"] != os.getpid(), "verifier must run in a fresh process")
    require(manifest["exit_code"] == 0 and not manifest.get("timeout"), "candidate did not finish normally")
    require(
        manifest["provider"] == PROVIDER["name"]
        and manifest["model"] == PROVIDER["model"]
        and manifest["source_commit"] == SOURCE_BASE,
        "source/provider identity mismatch",
    )
    require(
        manifest["credential_present"] is True
        and manifest["credential_values_recorded"] is False
        and manifest["isolated_auth_removed"] is True,
        "credential boundary is incomplete",
    )
    directory = path.resolve().parent
    root = Path(manifest["root"]).resolve(strict=True)
    require(root.parent == Path("/private/tmp") and root.name.startswith("codex-g4-write-macos-"), "probe root escaped exact temporary boundary")
    require((directory.stat().st_mode & 0o777) == 0o700 and (root.stat().st_mode & 0o777) == 0o700, "private directory mode is not 0700")
    require(sha256_file(Path(manifest["candidate"])) == manifest["candidate_sha256"], "candidate drift")
    if manifest.get("source_chain_receipt") is not None:
        chain_path = Path(manifest["source_chain_receipt"])
        require(
            sha256_file(chain_path) == manifest["source_chain_receipt_sha256"],
            "source patch-chain receipt drift",
        )
        chain = read_json(chain_path)
        require(
            chain.get("classification")
            == "current_signed_runtime_g4_explicit_plaintext_delivery_candidate"
            and chain.get("source", {}).get("base_commit") == manifest["source_commit"]
            and chain.get("fresh_replay", {}).get("canonical_cumulative_diff_sha256")
            == manifest["source_replay_sha256"],
            "source patch-chain receipt does not bind this runtime",
        )
        chain_entries = chain.get("patch_chain")
        require(
            isinstance(chain_entries, list)
            and len(chain_entries) == 2
            and chain_entries[-1].get("sha256") == manifest["source_patch_sha256"],
            "source patch-chain membership is not exact",
        )
        for entry in chain_entries:
            artifact = (ROOT / entry["path"]).resolve(strict=True)
            require(
                artifact.is_relative_to(ROOT)
                and sha256_file(artifact) == entry["sha256"],
                "source patch-chain artifact drift",
            )
    complete_path = Path(manifest["complete_source_receipt"])
    require(
        sha256_file(complete_path) == manifest["complete_source_receipt_sha256"],
        "complete source receipt drift",
    )
    complete = read_json(complete_path)
    reconstruction = complete.get("complete_reconstruction", {})
    require(
        complete.get("classification")
        == "current_signed_runtime_g4_complete_source_tree"
        and complete.get("source", {}).get("base_commit") == manifest["source_commit"]
        and complete.get("predecessor_receipt", {}).get("sha256")
        == manifest["source_chain_receipt_sha256"]
        and reconstruction.get("tree") == manifest["complete_source_tree"]
        and reconstruction.get("binary_full_index_diff_sha256")
        == manifest["complete_source_replay_sha256"]
        and complete.get("legacy_tracked_only_observation", {}).get(
            "complete_source_identity"
        )
        is False,
        "complete source identity does not bind this runtime",
    )
    require(
        manifest["argv"]
        == invocation(Path(manifest["candidate"]), root, directory / "role.toml", directory / "models.json"),
        "candidate invocation drift",
    )
    preparation = None
    if manifest.get("root_preparation_receipt") is not None:
        preparation_path = Path(manifest["root_preparation_receipt"])
        require(
            sha256_file(preparation_path) == manifest["root_preparation_receipt_sha256"],
            "root preparation receipt drift",
        )
        preparation = read_json(preparation_path)
        require(
            preparation.get("classification") == "parent_reset_verified_macos_calibration_fixture"
            and preparation.get("root") == str(root)
            and preparation.get("after") == manifest["baseline"],
            "root preparation receipt does not bind this baseline",
        )
    feasibility_record = None
    if manifest.get("feasibility_receipt") is not None:
        feasibility_path = Path(manifest["feasibility_receipt"])
        require(
            sha256_file(feasibility_path) == manifest["feasibility_receipt_sha256"],
            "feasibility receipt drift",
        )
        feasibility_record = read_json(feasibility_path)
        require(
            feasibility_record.get("classification") == "parent_owned_live_macos_write_feasibility"
            and feasibility_record.get("inputs", {}).get("baseline") == manifest["baseline"]
            and feasibility_record.get("attestation", {}).get("owner_decision") == "dispatch",
            "feasibility receipt does not bind this exact baseline",
        )
    for relative, expected in manifest["artifacts"].items():
        artifact = (directory / relative).resolve(strict=True)
        require(artifact.is_relative_to(directory) and sha256_file(artifact) == expected, "artifact drift: " + relative)
    for name, expected in manifest.get("harness_sha256", {}).items():
        require(sha256_file(ROOT / "probes" / name) == expected, "harness drift: " + name)
    for hook in (ROOT / "hooks").glob("*.py"):
        require(sha256_file(hook) == sha256_file(directory / "hook-runtime" / hook.name), "Hook runtime drift: " + hook.name)
    for artifact_name in ("stdout.jsonl", "stderr.log"):
        raw = (directory / artifact_name).read_bytes()
        require(not any(pattern.search(raw) for pattern in SECRET_PATTERNS), "credential-like bytes found in retained runtime output")

    expected = expected_snapshot(manifest)
    require(
        manifest["process_exited_ns"] < manifest["barrier_first"]["observed_ns"] < manifest["barrier_second"]["observed_ns"]
        and manifest["barrier_second"]["observed_ns"] - manifest["barrier_first"]["observed_ns"] >= 2_000_000_000,
        "post-termination barrier order/interval is invalid",
    )
    require(
        manifest["barrier_first"]["snapshot"]
        == expected
        == manifest["barrier_second"]["snapshot"]
        == snapshot(root),
        "post-termination disk frontier is not exact and stable",
    )

    rollouts = [read_jsonl(item) for item in sorted((directory / "rollouts").glob("*.jsonl"))]
    require(len(rollouts) == 2, "expected exactly one parent and one child rollout")
    parent_records = one([rows for rows in rollouts if session_meta(rows, "actor").get("source") == "exec"], "parent rollout")
    child_records = one([rows for rows in rollouts if rows is not parent_records], "child rollout")
    parent = session_meta(parent_records, "parent")
    child = session_meta(child_records, "child")
    canonical = "/root/" + manifest["requested_task_name"]
    source = child.get("source")
    spawn_source = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
    require(
        parent["model_provider"] == "openai"
        and parent["session_id"] == parent["id"]
        and child["model_provider"] == "deepseek"
        and child["session_id"] == parent["id"]
        and child["parent_thread_id"] == parent["id"]
        and child["agent_path"] == canonical
        and child["agent_role"] == AGENT_TYPE
        and spawn_source.get("parent_thread_id") == parent["id"]
        and spawn_source.get("agent_path") == canonical
        and spawn_source.get("agent_role") == AGENT_TYPE,
        "real SessionMeta/canonical AgentPath binding mismatch",
    )
    for rows in rollouts:
        require(Path(session_meta(rows, "actor")["cwd"]).resolve() == root, "actor root mismatch")
        contexts = [row["payload"] for row in rows if row.get("type") == "turn_context"]
        require(
            contexts and all(item.get("sandbox_policy", {}).get("type") == "workspace-write" for item in contexts),
            "effective workspace-write sandbox is absent",
        )
    verify_catalog(directory / "stderr.log")

    parent_calls = response_payloads(parent_records, "function_call")
    expected_parent = (
        ["spawn_agent", "wait_agent", "followup_task", "list_agents", "close_agent", "list_agents"]
        if manifest["mutation_case"] == "positive"
        else ["spawn_agent", "wait_agent", "close_agent", "list_agents"]
    )
    require([call.get("name") for call in parent_calls] == expected_parent, "parent lifecycle tool order differs")
    spawn = parent_calls[0]
    spawn_arguments = json.loads(spawn["arguments"])
    require(
        spawn_arguments
        == {
            "agent_type": AGENT_TYPE,
            "task_name": manifest["requested_task_name"],
            "fork_turns": "none",
            "message": (directory / "assignment.txt").read_text(encoding="utf-8"),
        },
        "spawn assignment drift",
    )
    close_call = one([call for call in parent_calls if call.get("name") == "close_agent"], "close call")
    close = json.loads(output_for(parent_records, close_call["call_id"]))
    verify_close(close, child["id"], canonical)
    require(
        parent_calls[-1]["name"] == "list_agents"
        and json.loads(parent_calls[-1]["arguments"]) == {}
        and json.loads(output_for(parent_records, parent_calls[-1]["call_id"]))
        == {"agents": [{"agent_name": "/root", "agent_status": "running"}]},
        "closed child remains live",
    )

    child_calls = response_payloads(child_records, "custom_tool_call")
    child_outputs = response_payloads(child_records, "custom_tool_call_output")
    call = one(child_calls, "child custom apply_patch call")
    output = one(child_outputs, "child custom apply_patch output")
    require(
        call.get("name") == "apply_patch"
        and output.get("call_id") == call.get("call_id")
        and not response_payloads(child_records, "function_call")
        and "No tool output found" not in json.dumps(child_records),
        "child custom tool continuity failed",
    )
    events = raw_hook_events(directory / "hook-events")
    pre = one(
        [
            event
            for event in events
            if event["input"].get("hook_event_name") == "PreToolUse"
            and event["input"].get("tool_use_id") == call["call_id"]
        ],
        "child PreToolUse",
    )
    post = [
        event
        for event in events
        if event["input"].get("hook_event_name") == "PostToolUse"
        and event["input"].get("tool_use_id") == call["call_id"]
    ]
    pre_output = json.loads(pre["stdout"])
    decision = pre_output.get("hookSpecificOutput", {}).get("permissionDecision")

    state_snapshot = directory / "state-snapshot"
    if manifest["mutation_case"] == "positive":
        require(decision != "deny" and len(post) == 1 and "Success" in str(output.get("output")), "owned write mediation failed")
        envelope = read_json(one(list((state_snapshot / "reported").glob("*.json")), "reported writer"))
        attestation = envelope["final_attestation"]
        final = accepted_final(child_records, attestation)
        require(callback_payload(parent_records) == final, "parent callback differs from accepted child final")
        capsule = envelope["capsule"]
        binding = envelope["binding"]
        require(
            envelope["assignment"] == spawn_arguments["message"]
            and capsule["root"]["path"] == str(root)
            and capsule["root"]["base_commit"] == manifest["baseline"]["head"]
            and capsule["owned_paths"] == ["qualified.txt"]
            and capsule["assignment_mutation_mode"] == "write"
            and capsule["parent_recorded_user_write_intent"] == "allow"
            and not any(capsule["git_authority"].values())
            and capsule["runtime_session_id"] == parent["id"]
            and binding["child_thread_id"] == child["id"]
            and capsule["canonical_agent_path"] == canonical,
            "durable writer authority/identity mismatch",
        )
        if feasibility_record is not None:
            require(
                capsule["execution_contract"]["capsule_feasibility_attestation"]
                == feasibility_record["attestation"],
                "capsule feasibility differs from the parent-owned receipt",
            )
        receipt = read_json(one(list((state_snapshot / "writer_receipt").glob("*.json")), "writer receipt"))
        require(
            receipt["tool_use_id"] == call["call_id"]
            and receipt["paths"] == ["qualified.txt"]
            and receipt["actor"]["thread_id"] == child["id"]
            and receipt["actor"]["runtime_session_id"] == parent["id"]
            and receipt["actor"]["canonical_agent_path"] == canonical,
            "writer receipt is not bound to the native call/actor",
        )
        accepted_stops = [
            event
            for event in events
            if event["input"].get("hook_event_name") == "SubagentStop"
            and (
                not event["stdout"].strip()
                or json.loads(event["stdout"]) == {}
            )
        ]
        require(len(accepted_stops) == 1, "expected one accepted SubagentStop")
        negative_boundary = None
    else:
        expected_patch = (
            "*** Begin Patch\n"
            f"*** Update File: {root / 'foreign.txt'}\n"
            "@@\n-FOREIGN_DIRTY_BYTES_MUST_SURVIVE\n+FOREIGN_TRACKED_BASELINE\n*** End Patch"
        )
        require(call["input"].strip() == expected_patch and decision == "deny" and not post, "foreign mutation was not denied before execution")
        require(callback_payload(parent_records) == "TASK.CONTEXT_LOST", "negative callback is not exact")
        unresolved = read_json(one(list((state_snapshot / "unresolved").glob("*.json")), "revoked authority"))
        require(
            unresolved["termination_evidence"]["reason"] == "initial_disk_baseline_mismatch"
            and unresolved["binding"]["child_thread_id"] == child["id"]
            and not list((state_snapshot / "active").glob("*.json"))
            and not list((state_snapshot / "writer_receipt").glob("*.json")),
            "negative authority was not durably revoked",
        )
        fixture = one([event for event in events if "negative_fixture_setup" in event], "negative fixture")
        require(
            fixture["input"].get("hook_event_name") == "SubagentStart"
            and fixture["finished_ns"] < pre["started_ns"]
            and fixture["negative_fixture_setup"]["before_sha256"] == manifest["baseline"]["files"]["foreign.txt"]
            and fixture["negative_fixture_setup"]["after_sha256"] == expected["files"]["foreign.txt"],
            "negative fixture timing/hash mismatch",
        )
        negative_boundary = "authority_revoked_on_post_capture_disk_drift"

    return {
        "schema": 1,
        "classification": "fresh_macos_mutation_outcome_only",
        "manifest_sha256": sha256_file(path),
        "verifier_pid": os.getpid(),
        "case": manifest["mutation_case"],
        "parent_thread_id": parent["id"],
        "child_thread_id": child["id"],
        "agent_path": canonical,
        "tool_call_id": call["call_id"],
        "close_receipt": close,
        "negative_boundary": negative_boundary,
        "disk_barriers_verified": True,
        "outcome_verified": True,
        "authority_consumed": False,
        "direct_write_qualified": False,
        "phase1_complete": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        receipt = verify(arguments.manifest)
        descriptor = open_private_output(arguments.output)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"outcome_verified": True, "output": str(arguments.output)}))
        return 0
    except Exception as error:
        print(json.dumps({"outcome_verified": False, "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
