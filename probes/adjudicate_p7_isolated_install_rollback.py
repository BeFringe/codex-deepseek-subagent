#!/usr/bin/env python3

"""Fresh-owner adjudication for the isolated P7 install/rollback probe."""

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


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"
RUNNER = ROOT / "probes" / "run_p7_isolated_install_rollback.py"
WRAPPER = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"
SOURCE_RECEIPT = ROOT / "probes" / "g4-live-failed-apply-patch-posttool-callback-20260908.json"
SOURCE_PATCH = ROOT / "probes" / "current-signed-runtime-failed-apply-patch-posttool-source-candidate.patch"
EXPECTED_PROMPT_SHA256 = "6dc04fc2f311abd503c381979e1f6a06970b9d0246ee9562fbea037abcb3a16e"
EXPECTED_BASELINE_SHA256 = "9160d4be34c8695bd172a76c7c7966587ea5a4d991ad22c87b2b91af54aa9ebb"


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
    result = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = json.loads(line)
        require(isinstance(value, dict), f"{path.name}:{number} is not an object")
        result.append(value)
    return result


def one(values: list[Any], label: str) -> Any:
    require(len(values) == 1, f"expected one {label}, found {len(values)}")
    return values[0]


def response_items(records: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [
        payload
        for record in records
        if record.get("type") == "response_item"
        and isinstance((payload := record.get("payload")), dict)
        and payload.get("type") == kind
    ]


def session_meta(records: list[dict[str, Any]]) -> dict[str, Any]:
    return one(
        [
            record["payload"]
            for record in records
            if record.get("type") == "session_meta"
            and isinstance(record.get("payload"), dict)
        ],
        "SessionMeta",
    )


def message_texts(records: list[dict[str, Any]], role: str) -> list[str]:
    result = []
    for message in response_items(records, "message"):
        if message.get("role") != role or not isinstance(message.get("content"), list):
            continue
        for part in message["content"]:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                result.append(part["text"])
    return result


def tool_output_text(item: dict[str, Any]) -> str:
    output = item.get("output")
    if not isinstance(output, list):
        return ""
    return "\n".join(
        part["text"]
        for part in output
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(completed.returncode == 0, f"git {' '.join(arguments)} failed")
    return completed.stdout.rstrip("\n")


def verify_file_record(record: dict[str, Any]) -> None:
    path = Path(record["path"])
    require(path.is_file(), f"raw artifact is absent: {path}")
    require(sha256_file(path) == record["sha256"], f"raw artifact drifted: {path}")
    if "bytes" in record:
        require(path.stat().st_size == record["bytes"], f"raw artifact size drifted: {path}")


def inspect_run(
    run: dict[str, Any],
    *,
    worktree: Path,
    runtime_version: str,
) -> dict[str, Any]:
    require(run["exit_code"] == 0, "candidate run did not exit zero")
    require(run["prompt_sha256"] == EXPECTED_PROMPT_SHA256, "probe prompt drifted")
    for prefix in ("stdout", "stderr"):
        verify_file_record(
            {
                "path": run[f"{prefix}_path"],
                "sha256": run[f"{prefix}_sha256"],
                "bytes": run[f"{prefix}_bytes"],
            }
        )
    rollout = one(run["new_rollouts"], "new rollout")
    verify_file_record(rollout)
    records = read_jsonl(Path(rollout["path"]))
    meta = session_meta(records)
    require(meta.get("source") == "exec", "run was not a native exec session")
    require(meta.get("model_provider") == "openai", "parent provider changed")
    require(meta.get("cwd") == str(worktree), "run root mismatched")
    require(meta.get("cli_version") == runtime_version, "runtime semantic version mismatched")
    require(meta.get("session_id") == meta.get("id"), "root SessionMeta identity mismatched")

    call = one(response_items(records, "custom_tool_call"), "code-mode tool call")
    require(call.get("name") == "exec", "outer code-mode tool was not exec")
    source = call.get("input")
    require(isinstance(source, str) and "tools.apply_patch" in source, "nested apply_patch is absent")
    require("-missing" in source and "+after" in source, "failed patch payload drifted")
    output = one(
        [
            item
            for item in response_items(records, "custom_tool_call_output")
            if item.get("call_id") == call.get("call_id")
        ],
        "code-mode tool output",
    )
    output_text = tool_output_text(output)
    require("apply_patch verification failed" in output_text, "patch did not fail at verification")
    require(str(worktree / "baseline.txt") in output_text, "failure output root mismatched")
    final = one(
        [text for text in message_texts(records, "assistant") if text == "FAILED_PATCH_OBSERVED"],
        "exact final answer",
    )
    require(final == "FAILED_PATCH_OBSERVED", "final answer drifted")
    stderr = Path(run["stderr_path"]).read_text(encoding="utf-8")
    require("apply_patch verification failed" in stderr, "router failure is absent")
    require("code-mode host" not in stderr.lower(), "code-mode host failed")
    require("authentication" not in stderr.lower(), "authentication failed")
    return {
        "thread_id": meta["id"],
        "turn_id": call.get("internal_chat_message_metadata_passthrough", {}).get("turn_id"),
        "outer_tool_call_id": call["call_id"],
        "provider": meta["model_provider"],
        "canonical_agent_path": "/root",
        "failed_patch_observed": True,
    }


def active_processes(paths: list[str]) -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(completed.returncode == 0, "process observation failed")
    result = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        pid_text, separator, command = stripped.partition(" ")
        if not separator or not pid_text.isdigit() or int(pid_text) == os.getpid():
            continue
        if any(path in command for path in paths):
            result.append({"pid": int(pid_text), "command": command})
    return result


def adjudicate(manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == 1, "manifest schema is invalid")
    require(manifest.get("preliminary_complete") is True, "runner did not complete")
    require(manifest.get("baseline_managed_paths_absent") is True, "managed baseline was not empty")
    require(manifest.get("gui_app_server_selected") is False, "GUI App Server was selected")
    require(manifest.get("codex_cli_path_modified") is False, "CODEX_CLI_PATH was modified")
    require(manifest.get("live_paths_unchanged") is True, "live paths changed")
    credential = manifest["credential_boundary"]
    for field in ("auth_value_read", "auth_value_printed", "auth_value_hashed", "auth_value_retained"):
        require(credential[field] is False, f"credential boundary failed: {field}")
    harness = manifest["harness"]
    for label, path in (
        ("runner", RUNNER),
        ("wrapper", WRAPPER),
        ("source_receipt", SOURCE_RECEIPT),
        ("source_patch", SOURCE_PATCH),
    ):
        require(Path(harness[f"{label}_path"]).resolve() == path, f"{label} path mismatched")
        require(sha256_file(path) == harness[f"{label}_sha256"], f"{label} hash drifted")

    runtime_index = read_json(RUNTIME_INDEX)
    runtime_role = runtime_index["current_runtime_role"]
    runtime = runtime_index["runtime_roles"][runtime_role]
    source_candidate = manifest["source_candidate"]
    source_host = manifest["source_code_mode_host"]
    verify_file_record(source_candidate)
    verify_file_record(source_host)
    source_receipt = read_json(SOURCE_RECEIPT)
    require(
        source_receipt.get("runtime", {}).get("candidate_sha256")
        == source_candidate["sha256"],
        "candidate is not the failed-PostToolUse source receipt binary",
    )
    require(
        source_receipt.get("runtime", {}).get("code_mode_host_sha256")
        == source_host["sha256"],
        "code-mode host is not the failed-PostToolUse source receipt binary",
    )
    install = manifest["install"]
    require(install["candidate_sha256"] == source_candidate["sha256"], "installed candidate drifted")
    require(install["code_mode_host_sha256"] == source_host["sha256"], "installed host drifted")
    for name, digest in install["hook_scripts"].items():
        require(sha256_file(ROOT / "hooks" / name) == digest, f"installed Hook source drifted: {name}")
    require(install["skill_installed"] is False, "probe installed an unnecessary skill")

    rollback = manifest["rollback"]
    require(all(rollback["moved_to_archive"].values()), "rollback did not archive every artifact")
    require(rollback["managed_paths_absent"] is True, "managed install paths remain")
    require(rollback["auth_symlink_unchanged"] is True, "auth symlink changed")
    archive_candidate = Path(rollback["archive_candidate_path"])
    archive_host = Path(rollback["archive_code_mode_host_path"])
    require(sha256_file(archive_candidate) == source_candidate["sha256"], "archived candidate drifted")
    require(sha256_file(archive_host) == source_host["sha256"], "archived host drifted")
    archived_hooks = Path(manifest["artifacts"]) / "rollback-archive" / "configuration"
    require(
        sha256_file(archived_hooks / "hooks.json") == install["hooks_json_sha256"],
        "archived Hook registry drifted",
    )

    worktree = Path(manifest["worktree"]).resolve()
    positive = inspect_run(
        manifest["positive_run"], worktree=worktree, runtime_version=runtime["codex_version"]
    )
    negative = inspect_run(
        manifest["negative_after_rollback"],
        worktree=worktree,
        runtime_version=runtime["codex_version"],
    )
    require(positive["thread_id"] != negative["thread_id"], "rollback did not start a fresh process")
    require(manifest["negative_after_rollback"]["managed_state_recreated"] is False, "removed Hook ran after rollback")

    state_root = Path(manifest["artifacts"]) / "rollback-archive" / "diagnostic-state"
    chain_path = state_root / "hook_event_chain" / "current.json"
    positive_state = manifest["positive_state"]
    require(sha256_file(chain_path) == positive_state["chain_sha256"], "Hook chain drifted")
    chain = read_json(chain_path)
    events = chain.get("events")
    require(isinstance(events, list) and len(events) == 2, "Hook chain is not exactly Pre/Post")
    pre, post = events
    require(
        pre.get("hook_event_name") == "PreToolUse"
        and pre.get("event_stage") == "authorized"
        and post.get("hook_event_name") == "PostToolUse"
        and post.get("event_stage") == "callback_observed",
        "Hook event stages mismatched",
    )
    require(pre.get("tool_name") == post.get("tool_name") == "apply_patch", "Hook tool mismatched")
    require(pre.get("tool_use_id") == post.get("tool_use_id"), "Pre/Post tool identity mismatched")
    require(pre.get("actor", {}).get("thread_id") == positive["thread_id"], "Hook actor mismatched")
    require(post.get("previous_receipt_sha256") == pre.get("receipt_sha256"), "Hook chain link mismatched")
    require(chain.get("head_receipt_sha256") == post.get("receipt_sha256"), "Hook chain head mismatched")

    receipt_record = one(positive_state["writer_receipts"], "writer receipt")
    receipt_path = state_root / "writer_receipt" / Path(receipt_record["path"]).name
    require(sha256_file(receipt_path) == receipt_record["sha256"], "writer receipt file drifted")
    receipt = read_json(receipt_path)
    require(receipt.get("tool_use_id") == pre.get("tool_use_id"), "writer receipt tool identity mismatched")
    require(receipt.get("root") == str(worktree), "writer receipt root mismatched")
    require(receipt.get("paths") == ["baseline.txt"], "writer receipt path mismatched")
    require(receipt.get("before_snapshot_sha256") == receipt.get("after_snapshot_sha256"), "failed patch changed disk")
    require(receipt.get("after_snapshot", {}).get("changed_paths") == [], "writer receipt observed changes")
    require(positive_state["writer_claim_names"] == [], "writer claim survived PostToolUse")

    final = manifest["worktree_final"]
    require(final["branch"] == git(worktree, "symbolic-ref", "--short", "HEAD"), "branch drifted")
    require(final["full_head"] == git(worktree, "rev-parse", "HEAD"), "HEAD drifted")
    require(git(worktree, "status", "--short", "--untracked-files=all") == "", "worktree is dirty")
    require(final["baseline_sha256"] == EXPECTED_BASELINE_SHA256, "baseline bytes drifted")
    require(sha256_file(worktree / "baseline.txt") == EXPECTED_BASELINE_SHA256, "baseline disk drifted")
    require(manifest["live_before"] == manifest["live_after"], "live baseline comparison mismatched")
    for record in manifest["live_after"].values():
        verify_file_record(record)

    process_paths = [
        install["candidate_path"],
        install["code_mode_host_path"],
        rollback["archive_candidate_path"],
        rollback["archive_code_mode_host_path"],
    ]
    require(active_processes(process_paths) == [], "candidate process survived the barrier")

    return {
        "schema": 1,
        "classification": "isolated_headless_install_reload_rollback_qualified",
        "adjudicated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fresh_adjudicator_pid": os.getpid(),
        "runtime": {
            "semantic_role": runtime_role,
            "codex_version": runtime["codex_version"],
            "source_commit": runtime["source_commit"],
            "candidate_sha256": source_candidate["sha256"],
            "code_mode_host_sha256": source_host["sha256"],
            "parent_provider": "openai",
            "gui_app_server_selected": False,
            "codex_cli_path_modified": False,
        },
        "functional_reload": {
            "positive_thread_id": positive["thread_id"],
            "canonical_agent_path": "/root",
            "tool_name": "apply_patch",
            "tool_use_id": pre["tool_use_id"],
            "pretool_authorized": True,
            "posttool_callback_observed": True,
            "writer_claim_released": True,
            "failed_patch_left_disk_unchanged": True,
        },
        "rollback": {
            "negative_thread_id": negative["thread_id"],
            "fresh_process_after_rollback": True,
            "removed_hook_state_recreated": False,
            "managed_install_paths_absent": True,
            "diagnostic_state_archived": True,
            "live_app_and_v4_hashes_unchanged": True,
            "candidate_processes_after_barrier": 0,
        },
        "credential_boundary": {
            "current_chatgpt_login_reused_by_symlink": True,
            "credential_value_read": False,
            "credential_value_printed": False,
            "credential_value_hashed": False,
            "credential_value_committed": False,
        },
        "harness": {
            "runner_sha256": harness["runner_sha256"],
            "adjudicator_sha256": sha256_file(Path(__file__).resolve()),
            "wrapper_sha256": harness["wrapper_sha256"],
            "source_receipt_sha256": harness["source_receipt_sha256"],
            "source_patch_sha256": harness["source_patch_sha256"],
        },
        "raw_artifacts": {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": sha256_file(manifest_path),
            "positive_rollout_path": manifest["positive_run"]["new_rollouts"][0]["path"],
            "positive_rollout_sha256": manifest["positive_run"]["new_rollouts"][0]["sha256"],
            "negative_rollout_path": manifest["negative_after_rollback"]["new_rollouts"][0]["path"],
            "negative_rollout_sha256": manifest["negative_after_rollback"]["new_rollouts"][0]["sha256"],
            "hook_chain_sha256": positive_state["chain_sha256"],
            "writer_receipt_sha256": receipt_record["sha256"],
        },
        "verdict": {
            "isolated_install_reload_rollback_qualified": True,
            "installed_failed_posttool_callback_regression_qualified": True,
            "install_rollback_exit_receipt_qualified": True,
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
