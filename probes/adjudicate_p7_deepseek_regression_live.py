#!/usr/bin/env python3

"""Fresh-process adjudication for one product-independent DeepSeek P7 run."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from build_p7_deepseek_regression_prompt import build_inputs


ROOT = MODULE_DIR.parent
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"
SOURCE_RECEIPT = ROOT / "probes" / "current-signed-runtime-g4-sibling-admission-source-candidate.json"
EXPECTED_HOOKS_JSON_SHA256 = "82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e"


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


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} is not an object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = json.loads(line)
        require(isinstance(value, dict), f"{path.name}:{number} is not an object")
        records.append(value)
    return records


def one(values: list[Any], label: str) -> Any:
    require(len(values) == 1, f"expected one {label}, found {len(values)}")
    return values[0]


def response_items(records: list[dict[str, Any]], item_type: str) -> list[dict[str, Any]]:
    return [
        payload
        for record in records
        if record.get("type") == "response_item"
        and isinstance((payload := record.get("payload")), dict)
        and payload.get("type") == item_type
    ]


def message_texts(records: list[dict[str, Any]], role: str) -> list[str]:
    result = []
    for message in response_items(records, "message"):
        if message.get("role") != role or not isinstance(message.get("content"), list):
            continue
        for part in message["content"]:
            if isinstance(part, dict) and part.get("type") in ("input_text", "output_text"):
                if isinstance(part.get("text"), str):
                    result.append(part["text"])
    return result


def session_meta(records: list[dict[str, Any]], label: str) -> dict[str, Any]:
    return one(
        [
            record["payload"]
            for record in records
            if record.get("type") == "session_meta" and isinstance(record.get("payload"), dict)
        ],
        f"{label} SessionMeta",
    )


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(result.returncode == 0, f"git {' '.join(arguments)} failed")
    return result.stdout.rstrip("\n")


def verify_manifest_hashes(manifest: dict[str, Any]) -> None:
    candidate = manifest["candidate"]
    require(
        sha256_file(Path(candidate["path"])) == candidate["sha256"],
        "candidate hash drifted",
    )
    inputs = manifest["inputs"]
    for path_field, hash_field in (
        ("assignment_path", "assignment_sha256"),
        ("parent_prompt_path", "parent_prompt_sha256"),
        ("role_path", "role_sha256"),
        ("wrapper_path", "wrapper_sha256"),
        ("handoff_script_path", "handoff_script_sha256"),
    ):
        require(
            sha256_file(Path(inputs[path_field])) == inputs[hash_field],
            f"{path_field} hash drifted",
        )
    stage = manifest["stage"]
    for path_field, hash_field in (
        ("stdout_path", "stdout_sha256"),
        ("stderr_path", "stderr_sha256"),
    ):
        require(sha256_file(Path(stage[path_field])) == stage[hash_field], f"stage {path_field} drifted")
    run = manifest["candidate_run"]
    for path_field, hash_field in (
        ("stdout_path", "stdout_sha256"),
        ("stderr_path", "stderr_sha256"),
    ):
        require(sha256_file(Path(run[path_field])) == run[hash_field], f"run {path_field} drifted")
    for rollout in run["rollouts"]:
        require(sha256_file(Path(rollout["path"])) == rollout["sha256"], "rollout hash drifted")


def adjudicate(manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == 1, "manifest schema is invalid")
    require(manifest.get("preliminary_complete") is True, "runner did not reach preliminary completion")
    require(manifest.get("credential_present") is True, "credential presence was not recorded")
    require(manifest.get("credential_value_recorded") is False, "credential value entered evidence")
    verify_manifest_hashes(manifest)

    probe_root = Path(manifest["probe_root"]).resolve()
    require(str(probe_root).startswith("/private/tmp/codex-p7-deepseek-regression."), "root escaped namespace")
    assignment = Path(manifest["inputs"]["assignment_path"]).read_text(encoding="utf-8")
    parent_prompt = Path(manifest["inputs"]["parent_prompt_path"]).read_text(encoding="utf-8")
    marker = one(re.findall(r"(?m)^marker=([0-9a-f]{32})$", assignment), "assignment marker")
    require(hashlib.sha256(marker.encode()).hexdigest() == manifest["marker_sha256"], "marker hash mismatched")
    expected_digest = sha256_file(probe_root / "fixtures" / "smoke-input.txt")
    require(expected_digest == "b7383fea044646d48d597239385c40246df3ef511a3486053d4711d171589bc1", "fixture drifted")
    expected_inputs = build_inputs(probe_root, manifest["task_name"], marker)
    require(expected_inputs["assignment"] == assignment, "assignment does not match the builder")
    require(expected_inputs["parent_prompt"] == parent_prompt, "parent prompt does not match the builder")
    require(marker not in parent_prompt and expected_digest not in parent_prompt, "parent received child-only facts")

    require(manifest["stage"]["exit_code"] == 0, "staging failed")
    stage = read_json(Path(manifest["stage"]["stdout_path"]))
    require(stage.get("staged") is True, "stage receipt is not successful")
    require(stage.get("handoff_id") == manifest["stage"]["handoff_id"], "handoff id mismatched")
    require(stage.get("agent_type") == "v4_flash_worker", "stage role mismatched")
    require(manifest["candidate_run"]["exit_code"] == 0, "candidate process failed")

    rollouts = manifest["candidate_run"]["rollouts"]
    parent_rollout = one([value for value in rollouts if value["kind"] == "parent"], "parent rollout")
    child_rollout = one([value for value in rollouts if value["kind"] == "child"], "child rollout")
    parent_records = read_jsonl(Path(parent_rollout["path"]))
    child_records = read_jsonl(Path(child_rollout["path"]))
    parent = session_meta(parent_records, "parent")
    child = session_meta(child_records, "child")
    parent_thread = parent["id"]
    child_thread = child["id"]
    canonical_path = f"/root/{manifest['task_name']}"
    require(parent.get("session_id") == parent_thread, "parent session identity mismatched")
    require(parent.get("source") == "exec" and parent.get("model_provider") == "openai", "parent provider/source mismatched")
    require(parent.get("cwd") == str(probe_root), "parent root mismatched")
    source = child.get("source", {}).get("subagent", {}).get("thread_spawn", {})
    require(child.get("session_id") == parent_thread, "child runtime session mismatched")
    require(child.get("parent_thread_id") == parent_thread, "child parent mismatched")
    require(child.get("model_provider") == "deepseek", "child provider mismatched")
    require(child.get("agent_role") == "v4_flash_worker", "child role mismatched")
    require(child.get("agent_path") == canonical_path and child.get("cwd") == str(probe_root), "child path/root mismatched")
    require(
        source.get("parent_thread_id") == parent_thread
        and source.get("depth") == 1
        and source.get("agent_path") == canonical_path
        and source.get("agent_role") == "v4_flash_worker",
        "child source edge mismatched",
    )

    parent_calls = response_items(parent_records, "function_call")
    spawn = one([call for call in parent_calls if call.get("name") == "spawn_agent"], "spawn call")
    wait = one([call for call in parent_calls if call.get("name") == "wait_agent"], "wait call")
    spawn_arguments = json.loads(spawn["arguments"])
    require(
        spawn_arguments
        == {
            "agent_type": "v4_flash_worker",
            "task_name": manifest["task_name"],
            "fork_turns": "none",
            "message": "Execute the assignment supplied by the trusted one-shot SubagentStart Hook.",
        },
        "spawn arguments mismatched",
    )
    outputs = response_items(parent_records, "function_call_output")
    spawn_output = one([item for item in outputs if item.get("call_id") == spawn["call_id"]], "spawn output")
    wait_output = one([item for item in outputs if item.get("call_id") == wait["call_id"]], "wait output")
    require(json.loads(spawn_output["output"]) == {"task_name": canonical_path}, "spawn output mismatched")
    require(json.loads(wait_output["output"]) == {"message": "Wait completed.", "timed_out": False}, "wait output mismatched")

    hook_context = one(
        [
            text
            for text in message_texts(child_records, "developer")
            if "BEGIN PARENT ASSIGNMENT\n" in text and "\nEND PARENT ASSIGNMENT" in text
        ],
        "SubagentStart additional context",
    )
    delivered = hook_context.split("BEGIN PARENT ASSIGNMENT\n", 1)[1].rsplit("\nEND PARENT ASSIGNMENT", 1)[0]
    require(delivered == assignment, "Hook-delivered assignment mismatched")
    new_task = one(
        [text for text in message_texts(child_records, "user") if text.startswith("Message Type: NEW_TASK\n")],
        "child NEW_TASK",
    )
    require(marker not in new_task and expected_digest not in new_task, "spawn message carried child-only facts")

    child_calls = response_items(child_records, "function_call")
    tool = one(child_calls, "child tool call")
    require(tool.get("name") == "exec_command", "child used the wrong tool")
    tool_arguments = json.loads(tool["arguments"])
    require(tool_arguments.get("workdir") == str(probe_root), "child tool root mismatched")
    expected_command = one(re.findall(r"cmd exactly `([^`]+)`", assignment), "exact child command")
    require(tool_arguments.get("cmd") == expected_command, "child command mismatched")
    child_outputs = response_items(child_records, "function_call_output")
    tool_output = one([item for item in child_outputs if item.get("call_id") == tool["call_id"]], "child tool output")
    require(f"\nresponses\n{expected_digest}\n" in tool_output["output"], "child tool result mismatched")

    child_final = one(
        [text for text in message_texts(child_records, "assistant") if text.startswith("marker=")],
        "child final",
    )
    expected_final = f"marker={marker}\nthird_line=responses\nsha256={expected_digest}"
    require(child_final == expected_final, "child final mismatched")
    callback = one(
        [text for text in message_texts(parent_records, "user") if text.startswith("Message Type: FINAL_ANSWER\n")],
        "parent callback",
    )
    require(callback.endswith("Payload:\n" + expected_final), "parent callback mismatched")
    require(any(expected_final in text for text in message_texts(parent_records, "assistant")), "parent final omitted child result")

    post = manifest["post_run"]
    require(post["pending_present"] is False and post["claimed_or_failed"] == [], "handoff was not consumed")
    require([path.name for path in Path(manifest["handoff_root"]).iterdir()] == [".v4_flash_worker.lock"], "handoff disk changed")
    require(git(probe_root, "status", "--short", "--untracked-files=all") == "", "probe root is dirty")
    require(git(probe_root, "rev-parse", "HEAD") == post["full_head"], "probe HEAD changed")
    stderr = Path(manifest["candidate_run"]["stderr_path"]).read_text(encoding="utf-8")
    require("ERROR" not in stderr and "authentication" not in stderr.lower(), "candidate stderr contains an error")

    runtime_index = read_json(RUNTIME_INDEX)
    runtime_role = runtime_index["current_runtime_role"]
    runtime = runtime_index["runtime_roles"][runtime_role]
    require(parent.get("cli_version") == runtime["codex_version"], "runtime semantic version mismatched")
    source_receipt = read_json(SOURCE_RECEIPT)
    require(
        source_receipt["candidate"]["sha256"] == manifest["candidate"]["sha256"],
        "candidate is not the current source receipt binary",
    )
    hooks_json = Path.home() / ".codex" / "hooks.json"
    require(sha256_file(hooks_json) == EXPECTED_HOOKS_JSON_SHA256, "installed Hook registry drifted")
    installed_handoff = Path.home() / ".codex" / "hooks" / "codex-deepseek-subagent" / "plaintext_handoff.py"
    require(
        sha256_file(installed_handoff) == manifest["inputs"]["handoff_script_sha256"],
        "installed one-shot Hook script mismatched",
    )

    return {
        "schema": 1,
        "classification": "product_independent_native_deepseek_readonly_regression_qualified",
        "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fresh_adjudicator_pid": os.getpid(),
        "runtime": {
            "semantic_role": runtime_role,
            "codex_version": runtime["codex_version"],
            "source_commit": runtime["source_commit"],
            "candidate_path": manifest["candidate"]["path"],
            "candidate_sha256": manifest["candidate"]["sha256"],
            "candidate_installed_or_selected_by_gui": False,
            "live_config_modified": False,
        },
        "credential_boundary": {
            "credential_name": "DEEPSEEK_API_KEY",
            "credential_present": True,
            "credential_value_read": False,
            "credential_value_printed": False,
            "credential_value_hashed": False,
            "credential_value_retained": False,
            "credential_value_committed": False,
        },
        "transport": {
            "assignment_transport": "one-shot plaintext SubagentStart Hook",
            "wire_transport": "responses-direct",
            "request_normalization": "none",
            "handoff_id": manifest["stage"]["handoff_id"],
            "assignment_sha256": manifest["inputs"]["assignment_sha256"],
            "marker_sha256": manifest["marker_sha256"],
            "marker_absent_from_parent_prompt_and_spawn_message": True,
            "handoff_consumed": True,
        },
        "identity": {
            "parent_thread_id": parent_thread,
            "parent_provider": "openai",
            "child_thread_id": child_thread,
            "child_provider": "deepseek",
            "child_model": "deepseek-v4-flash",
            "agent_type": "v4_flash_worker",
            "requested_task_name": manifest["task_name"],
            "canonical_agent_path": canonical_path,
            "depth": 1,
        },
        "native_loop": {
            "spawn_call_id": spawn["call_id"],
            "wait_call_id": wait["call_id"],
            "wait_timed_out": False,
            "child_tool_name": "exec_command",
            "child_tool_call_id": tool["call_id"],
            "child_tool_call_count": 1,
            "third_nonempty_line": "responses",
            "fixture_sha256": expected_digest,
            "callback_byte_exact": True,
        },
        "disk_barrier": {
            "root": str(probe_root),
            "branch": git(probe_root, "symbolic-ref", "--short", "HEAD"),
            "full_head": post["full_head"],
            "git_status_short": "",
            "handoff_state_names": [".v4_flash_worker.lock"],
        },
        "raw_artifacts": {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": sha256_file(manifest_path),
            "parent_rollout_path": parent_rollout["path"],
            "parent_rollout_sha256": parent_rollout["sha256"],
            "child_rollout_path": child_rollout["path"],
            "child_rollout_sha256": child_rollout["sha256"],
            "candidate_stdout_path": manifest["candidate_run"]["stdout_path"],
            "candidate_stdout_sha256": manifest["candidate_run"]["stdout_sha256"],
            "candidate_stderr_path": manifest["candidate_run"]["stderr_path"],
            "candidate_stderr_sha256": manifest["candidate_run"]["stderr_sha256"],
        },
        "verdict": {
            "native_openai_parent_preserved": True,
            "native_deepseek_child_observed": True,
            "one_shot_hook_delivery_observed": True,
            "native_tool_result_observed": True,
            "native_wait_and_callback_observed": True,
            "read_only_disk_barrier_clean": True,
            "deepseek_regression_qualified": True,
            "phase1_complete": False,
            "direct_write_qualified": False,
            "phase2_state": "closed",
            "phase3_state": "closed",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = adjudicate(arguments.manifest)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AdjudicationError) as error:
        print(json.dumps({"qualified": False, "error": str(error)}, separators=(",", ":")))
        return 2
    arguments.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "qualified": True,
                "output": str(arguments.output),
                "output_sha256": sha256_file(arguments.output),
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
