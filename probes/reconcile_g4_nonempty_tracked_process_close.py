#!/usr/bin/env python3

"""Reconcile one native child nonempty tracked-process close receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "probes"
if str(PROBES) not in sys.path:
    sys.path.insert(0, str(PROBES))

from build_p5b_tracked_process_probe_prompt import (  # noqa: E402
    AGENT_TYPE,
    CHILD_POLL_TIMEOUT_MS,
    PARENT_WAIT_TIMEOUT_MS,
    PROCESS_SECONDS,
    TOOL_NAMESPACE,
    build_prompt,
)


PARENT_CALLS = ["spawn_agent", "wait_agent", "list_agents", "close_agent", "list_agents"]
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
TRUST_WARNING = (
    "`--dangerously-bypass-hook-trust` is enabled. "
    "Enabled hooks may run without review for this invocation."
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReconciliationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ReconciliationError(f"cannot hash {path}") from error
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReconciliationError(f"cannot read {path}") from error
    for line_number, line in enumerate(lines, 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReconciliationError(f"{path}:{line_number} is not JSON") from error
        if not isinstance(value, dict):
            raise ReconciliationError(f"{path}:{line_number} is not a JSON object")
        records.append(value)
    if not records:
        raise ReconciliationError(f"{path} is empty")
    return records


def parse_timestamp(value: object, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ReconciliationError(f"{label} has no timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReconciliationError(f"{label} timestamp is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReconciliationError(f"{label} timestamp lacks an offset")
    return parsed


def json_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ReconciliationError(f"{label} is not encoded JSON")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ReconciliationError(f"{label} is invalid JSON") from error
    if not isinstance(decoded, dict):
        raise ReconciliationError(f"{label} is not a JSON object")
    return decoded


def session_meta(records: list[dict[str, Any]], label: str) -> dict[str, Any]:
    values = [record.get("payload") for record in records if record.get("type") == "session_meta"]
    if len(values) != 1 or not isinstance(values[0], dict):
        raise ReconciliationError(f"{label} must contain exactly one SessionMeta")
    return values[0]


def response_items(
    records: list[dict[str, Any]], item_type: str
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    items = []
    for record in records:
        payload = record.get("payload")
        if (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == item_type
        ):
            items.append((record, payload))
    return items


def git_value(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ReconciliationError(
            f"Git command failed ({' '.join(arguments)}): {result.stderr.strip()}"
        )
    return result.stdout.rstrip("\n")


def candidate_semantic_version(candidate: Path) -> str:
    result = subprocess.run(
        [str(candidate), "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    match = re.fullmatch(
        r"codex-cli ([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)\n?",
        result.stdout,
    )
    if result.returncode != 0 or match is None:
        raise ReconciliationError("candidate did not expose one semantic Codex version")
    return match.group(1)


def validate_probe_root(root: Path) -> dict[str, str]:
    resolved = root.resolve(strict=True)
    if not str(resolved).startswith("/private/tmp/codex-g4-p5b-tracked-process."):
        raise ReconciliationError("probe root is outside the fixed temporary namespace")
    if Path(git_value(resolved, "rev-parse", "--show-toplevel")).resolve() != resolved:
        raise ReconciliationError("probe root is not the exact Git top level")
    branch = git_value(resolved, "symbolic-ref", "--short", "HEAD")
    head = git_value(resolved, "rev-parse", "HEAD")
    tree = git_value(resolved, "rev-parse", "HEAD^{tree}")
    status = git_value(resolved, "status", "--short", "--untracked-files=all")
    if branch != "main" or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise ReconciliationError("probe Git identity is invalid")
    if status:
        raise ReconciliationError("probe Git root is dirty")
    return {"root": str(resolved), "branch": branch, "head": head, "tree": tree}


def validate_identity(
    parent_records: list[dict[str, Any]],
    child_records: list[dict[str, Any]],
    baseline: dict[str, str],
    task_name: str,
) -> dict[str, str]:
    parent = session_meta(parent_records, "parent rollout")
    child = session_meta(child_records, "child rollout")
    parent_thread = parent.get("id")
    child_thread = child.get("id")
    canonical_path = f"/root/{task_name}"
    expected_git = {"commit_hash": baseline["head"], "branch": baseline["branch"]}
    if not (
        isinstance(parent_thread, str)
        and parent.get("session_id") == parent_thread
        and parent.get("cwd") == baseline["root"]
        and parent.get("source") == "exec"
        and parent.get("model_provider") == "openai"
        and parent.get("git") == expected_git
    ):
        raise ReconciliationError("parent SessionMeta does not match the probe baseline")
    source = child.get("source")
    spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
    if not (
        isinstance(child_thread, str)
        and child.get("session_id") == parent_thread
        and child.get("parent_thread_id") == parent_thread
        and child.get("cwd") == baseline["root"]
        and child.get("agent_path") == canonical_path
        and child.get("agent_role") == AGENT_TYPE
        and child.get("model_provider") == "openai"
        and child.get("git") == expected_git
        and spawn.get("parent_thread_id") == parent_thread
        and spawn.get("depth") == 1
        and spawn.get("agent_path") == canonical_path
        and spawn.get("agent_role") == AGENT_TYPE
    ):
        raise ReconciliationError("child SessionMeta does not match the native spawn identity")
    return {
        "parent_thread_id": parent_thread,
        "runtime_session_id": parent_thread,
        "child_thread_id": child_thread,
        "requested_task_name": task_name,
        "canonical_agent_path": canonical_path,
        "agent_type": AGENT_TYPE,
    }


def validate_close_receipt(
    close: dict[str, Any], child_thread: str, canonical_path: str
) -> int:
    if set(close) != CLOSE_FIELDS:
        raise ReconciliationError("close receipt fields are not exact")
    tracked = close.get("tracked_process_ids_by_thread")
    confirmed = close.get("confirmed_exit_process_ids_by_thread")
    empty = {child_thread: []}
    if not (
        close.get("previous_status") == "running"
        and close.get("target_thread_id") == child_thread
        and close.get("target_agent_path") == canonical_path
        and close.get("session_loop_terminated") is True
        and close.get("model_callable_process_bootstrap_absent") is False
        and close.get("tracked_background_processes_before_close") is None
        and isinstance(tracked, dict)
        and set(tracked) == {child_thread}
        and isinstance(tracked[child_thread], list)
        and len(tracked[child_thread]) == 1
        and isinstance(tracked[child_thread][0], int)
        and tracked[child_thread][0] > 0
        and confirmed == tracked
        and close.get("unconfirmed_exit_process_ids_by_thread") == empty
        and close.get("unresolved_start_process_ids_by_thread") == empty
        and close.get("tracked_process_termination_confirmed") is True
        and close.get("closed_catalog_actor_quiescence_claimed") is False
        and close.get("process_tree_quiescence_claimed") is False
    ):
        raise ReconciliationError("close receipt does not prove one exact tracked process exit")
    return tracked[child_thread][0]


def validate_parent_lifecycle(
    records: list[dict[str, Any]],
    identity: dict[str, str],
    expected_assignment: str,
) -> dict[str, Any]:
    calls = response_items(records, "function_call")
    if [item.get("name") for _, item in calls] != PARENT_CALLS:
        raise ReconciliationError("parent tool order is not exact")
    if any(item.get("namespace") != TOOL_NAMESPACE for _, item in calls):
        raise ReconciliationError("parent used a non-G4 assignment namespace")
    if response_items(records, "custom_tool_call"):
        raise ReconciliationError("parent used a code-mode tool")
    outputs = {
        item.get("call_id"): (record, item)
        for record, item in response_items(records, "function_call_output")
    }
    if set(outputs) != {item.get("call_id") for _, item in calls}:
        raise ReconciliationError("parent lifecycle outputs do not match its calls")

    canonical_path = identity["canonical_agent_path"]
    spawn_record, spawn = calls[0]
    if json_object(spawn.get("arguments"), "spawn arguments") != {
        "agent_type": AGENT_TYPE,
        "task_name": identity["requested_task_name"],
        "fork_turns": "none",
        "message": expected_assignment,
    }:
        raise ReconciliationError("spawn arguments do not match the frozen assignment")
    spawn_output = json_object(outputs[spawn["call_id"]][1].get("output"), "spawn output")
    if spawn_output != {"task_name": canonical_path}:
        raise ReconciliationError("spawn projection is not the exact canonical path")

    wait_record, wait_call = calls[1]
    if json_object(wait_call.get("arguments"), "wait arguments") != {
        "timeout_ms": PARENT_WAIT_TIMEOUT_MS
    }:
        raise ReconciliationError("parent wait arguments are not exact")
    wait_output = json_object(outputs[wait_call["call_id"]][1].get("output"), "wait output")
    if wait_output.get("timed_out") is not True:
        raise ReconciliationError("parent wait did not reach the intended running boundary")

    pre_record, pre_call = calls[2]
    if json_object(pre_call.get("arguments"), "pre-close list arguments") != {}:
        raise ReconciliationError("pre-close list arguments are not empty")
    pre = json_object(outputs[pre_call["call_id"]][1].get("output"), "pre-close list output")
    if pre.get("agents") != [
        {"agent_name": "/root", "agent_status": "running"},
        {"agent_name": canonical_path, "agent_status": "running"},
    ]:
        raise ReconciliationError("pre-close live tree is not exact")

    close_record, close_call = calls[3]
    if json_object(close_call.get("arguments"), "close arguments") != {
        "target": canonical_path
    }:
        raise ReconciliationError("close target is not the canonical AgentPath")
    close_output_record, close_output_item = outputs[close_call["call_id"]]
    close = json_object(close_output_item.get("output"), "close output")
    process_id = validate_close_receipt(
        close,
        identity["child_thread_id"],
        canonical_path,
    )

    post_record, post_call = calls[4]
    if json_object(post_call.get("arguments"), "post-close list arguments") != {}:
        raise ReconciliationError("post-close list arguments are not empty")
    post = json_object(outputs[post_call["call_id"]][1].get("output"), "post-close list output")
    if post != {"agents": [{"agent_name": "/root", "agent_status": "running"}]}:
        raise ReconciliationError("post-close live tree still contains the child")

    timestamps = {
        "spawn_called_at": parse_timestamp(spawn_record.get("timestamp"), "spawn call"),
        "wait_called_at": parse_timestamp(wait_record.get("timestamp"), "wait call"),
        "pre_close_list_called_at": parse_timestamp(pre_record.get("timestamp"), "pre-close list"),
        "close_called_at": parse_timestamp(close_record.get("timestamp"), "close call"),
        "close_returned_at": parse_timestamp(close_output_record.get("timestamp"), "close output"),
        "post_close_list_called_at": parse_timestamp(post_record.get("timestamp"), "post-close list"),
    }
    if list(timestamps.values()) != sorted(timestamps.values()):
        raise ReconciliationError("parent lifecycle timestamps are not ordered")
    return {
        "spawn_tool_use_id": spawn["call_id"],
        "wait_tool_use_id": wait_call["call_id"],
        "pre_close_list_tool_use_id": pre_call["call_id"],
        "close_tool_use_id": close_call["call_id"],
        "post_close_list_tool_use_id": post_call["call_id"],
        **{name: value.isoformat() for name, value in timestamps.items()},
        "wait_timed_out": True,
        "pre_close_status": "running",
        "close_receipt": close,
        "close_receipt_sha256": sha256_json(close),
        "tracked_process_id": process_id,
        "target_absent_from_post_close_tree": True,
    }


def nested_result(item: dict[str, Any], label: str) -> dict[str, Any]:
    output = item.get("output")
    if not isinstance(output, list):
        raise ReconciliationError(f"{label} output is not a content list")
    candidates = []
    for entry in output:
        if not isinstance(entry, dict) or entry.get("type") != "input_text":
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates.append(json_object(stripped, label))
    if len(candidates) != 1:
        raise ReconciliationError(f"{label} must contain one nested result")
    return candidates[0]


def validate_child_process(
    records: list[dict[str, Any]],
    baseline: dict[str, str],
    marker: str,
    tracked_process_id: int,
    close_called_at: str,
    close_returned_at: str,
) -> dict[str, Any]:
    calls = response_items(records, "custom_tool_call")
    outputs = {
        item.get("call_id"): (record, item)
        for record, item in response_items(records, "custom_tool_call_output")
    }
    if len(calls) != 2 or [item.get("name") for _, item in calls] != ["exec", "exec"]:
        raise ReconciliationError("child code-mode call sequence is not exact")
    if response_items(records, "function_call"):
        raise ReconciliationError("child used an unexpected direct tool")
    if set(outputs) != {item.get("call_id") for _, item in calls}:
        raise ReconciliationError("child tool outputs do not match its calls")

    command = f"python3 -c 'import time; time.sleep({PROCESS_SECONDS})' {marker}"
    first_inputs = {
        "const result = await tools.exec_command("
        f'{{cmd:"{command}",workdir:"{baseline["root"]}",yield_time_ms:1000,tty:false}});'
        f"{separator}text(JSON.stringify(result));\n"
        for separator in ("", " ")
    }
    second_inputs = {
        "const result = await tools.write_stdin("
        f'{{session_id:{tracked_process_id},chars:"",yield_time_ms:{CHILD_POLL_TIMEOUT_MS}}});'
        f"{separator}text(JSON.stringify(result));\n"
        for separator in ("", " ")
    }
    if calls[0][1].get("input") not in first_inputs:
        raise ReconciliationError("child process start JavaScript is not exact")
    if calls[1][1].get("input") not in second_inputs:
        raise ReconciliationError("child process poll JavaScript is not exact")

    started = nested_result(outputs[calls[0][1]["call_id"]][1], "process start")
    exited = nested_result(outputs[calls[1][1]["call_id"]][1], "process exit")
    if not (
        set(started) == {"chunk_id", "wall_time_seconds", "session_id", "original_token_count", "output"}
        and started.get("session_id") == tracked_process_id
        and started.get("output") == ""
        and isinstance(started.get("wall_time_seconds"), (int, float))
        and set(exited) == {"chunk_id", "wall_time_seconds", "exit_code", "original_token_count", "output"}
        and exited.get("exit_code") == 137
        and exited.get("output") == ""
        and isinstance(exited.get("wall_time_seconds"), (int, float))
    ):
        raise ReconciliationError("nested process receipts do not join to the tracked exit")

    start_call_at = parse_timestamp(calls[0][0].get("timestamp"), "process start call")
    start_returned_at = parse_timestamp(
        outputs[calls[0][1]["call_id"]][0].get("timestamp"), "process start output"
    )
    poll_called_at = parse_timestamp(calls[1][0].get("timestamp"), "process poll call")
    poll_returned_at = parse_timestamp(
        outputs[calls[1][1]["call_id"]][0].get("timestamp"), "process poll output"
    )
    close_call = parse_timestamp(close_called_at, "close call")
    close_return = parse_timestamp(close_returned_at, "close return")
    if not (
        start_call_at < start_returned_at < poll_called_at < close_call
        < poll_returned_at < close_return
    ):
        raise ReconciliationError("process exit is not ordered inside the close interval")
    aborted = [
        record
        for record in records
        if record.get("type") == "event_msg"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("type") == "turn_aborted"
    ]
    if len(aborted) != 1 or aborted[0]["payload"].get("reason") != "interrupted":
        raise ReconciliationError("child termination did not freeze one interrupted turn")
    aborted_at = parse_timestamp(aborted[0].get("timestamp"), "turn aborted")
    if not poll_returned_at < aborted_at < close_return:
        raise ReconciliationError("child turn abort is not ordered after process exit")
    return {
        "start_tool_use_id": calls[0][1]["call_id"],
        "poll_tool_use_id": calls[1][1]["call_id"],
        "process_id": tracked_process_id,
        "start_session_id_equals_tracked_process_id": True,
        "process_exit_code": 137,
        "process_exit_observed_before_close_return": True,
        "turn_aborted_reason": "interrupted",
        "start_called_at": start_call_at.isoformat(),
        "start_returned_at": start_returned_at.isoformat(),
        "poll_called_at": poll_called_at.isoformat(),
        "poll_returned_at": poll_returned_at.isoformat(),
        "turn_aborted_at": aborted_at.isoformat(),
    }


def validate_headless_events(records: list[dict[str, Any]], parent_thread_id: str) -> None:
    if records[0] != {"type": "thread.started", "thread_id": parent_thread_id}:
        raise ReconciliationError("headless event stream has the wrong parent thread")
    if sum(record.get("type") == "turn.started" for record in records) != 1:
        raise ReconciliationError("headless event stream lacks one turn start")
    if sum(record.get("type") == "turn.completed" for record in records) != 1:
        raise ReconciliationError("headless event stream lacks one completed turn")
    if any(record.get("type") == "turn.failed" for record in records):
        raise ReconciliationError("headless event stream contains a failed turn")
    errors = [
        record.get("item", {}).get("message")
        for record in records
        if record.get("type") == "item.completed"
        and isinstance(record.get("item"), dict)
        and record["item"].get("type") == "error"
    ]
    if not errors or any(message != TRUST_WARNING for message in errors):
        raise ReconciliationError("headless errors are not only the exact trust-bypass warning")


def validate_parent_catalog(stderr: Path, parent_thread_id: str) -> dict[str, Any]:
    receipts = []
    try:
        lines = stderr.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReconciliationError("cannot read candidate stderr") from error
    for line in lines:
        prefix = "G4_TOOL_CATALOG_RECEIPT_V2 "
        if line.startswith(prefix):
            receipts.append(json_object(line[len(prefix):], "catalog receipt"))
    if not receipts:
        raise ReconciliationError("candidate stderr has no runtime-final catalog receipt")
    first = receipts[0]
    if any(receipt != first for receipt in receipts[1:]):
        raise ReconciliationError("parent catalog receipts are not stable")
    catalog = first.get("catalog")
    registered = catalog.get("registered_tools") if isinstance(catalog, dict) else None
    names = [
        f"{entry['namespace']}.{entry['name']}" if entry.get("namespace") else entry.get("name")
        for entry in registered
    ] if isinstance(registered, list) and all(isinstance(entry, dict) for entry in registered) else []
    expected = [
        "apply_patch",
        "g4_assignment.close_agent",
        "g4_assignment.followup_task",
        "g4_assignment.interrupt_agent",
        "g4_assignment.list_agents",
        "g4_assignment.send_message",
        "g4_assignment.spawn_agent",
        "g4_assignment.wait_agent",
        "view_image",
    ]
    if not (
        first.get("schema") == 2
        and first.get("event") == "finalized_tool_catalog"
        and first.get("session_id") == parent_thread_id
        and first.get("thread_id") == parent_thread_id
        and first.get("agent_path") == "/root"
        and first.get("agent_role") == "root"
        and isinstance(catalog, dict)
        and catalog.get("source") == "finalized_tool_router_after_all_contributors"
        and catalog.get("tool_mode") == "direct"
        and names == expected
        and catalog.get("code_mode_tool_names") == {}
        and catalog.get("can_manage_children") is True
    ):
        raise ReconciliationError("parent runtime-final catalog is not the closed projection")
    return {"receipt_count": len(receipts), "registered_tools": names}


def host_observation(
    baseline: dict[str, str], candidate: Path, marker: str, process_id: int
) -> dict[str, Any]:
    root = Path(baseline["root"])
    current = validate_probe_root(root)
    if current != baseline:
        raise ReconciliationError("post-close Git frontier changed")
    ps = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if ps.returncode != 0:
        raise ReconciliationError("cannot inspect the host process table")
    marker_matches = [
        line
        for line in ps.stdout.splitlines()
        if marker in line and f"time.sleep({PROCESS_SECONDS})" in line
    ]
    pid_matches = [
        line
        for line in ps.stdout.splitlines()
        if line.lstrip().startswith(f"{process_id} ")
    ]
    opened = subprocess.run(
        ["lsof", str(candidate)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    candidate_open_file_count = max(0, len(opened.stdout.splitlines()) - 1)
    return {
        "observed_at_ns": time.time_ns(),
        "head": current["head"],
        "tree": current["tree"],
        "git_status_short": "",
        "tracked_process_id_present": bool(pid_matches),
        "marked_process_match_count": len(marker_matches),
        "candidate_open_file_count": candidate_open_file_count,
    }


def reconcile(arguments: argparse.Namespace) -> dict[str, Any]:
    baseline = validate_probe_root(arguments.root)
    run_dir = arguments.run_dir.resolve(strict=True)
    if not str(run_dir).startswith("/private/tmp/codex-g4-p5b-tracked-run."):
        raise ReconciliationError("run directory is outside the fixed temporary namespace")
    if not SHA256_RE.fullmatch(arguments.candidate_sha256):
        raise ReconciliationError("candidate digest is invalid")
    if not SHA256_RE.fullmatch(arguments.code_mode_host_sha256):
        raise ReconciliationError("code-mode host digest is invalid")
    if sha256_file(arguments.candidate) != arguments.candidate_sha256:
        raise ReconciliationError("candidate digest mismatch")
    if sha256_file(arguments.code_mode_host) != arguments.code_mode_host_sha256:
        raise ReconciliationError("code-mode host digest mismatch")
    semantic_version = candidate_semantic_version(arguments.candidate)

    prompt_path = run_dir / "prompt.txt"
    events_path = run_dir / "events.jsonl"
    stderr_path = run_dir / "stderr.txt"
    last_path = run_dir / "last.txt"
    exit_path = run_dir / "exit.txt"
    expected_prompt = build_prompt(arguments.root, arguments.task_name, arguments.process_marker)
    if prompt_path.read_text(encoding="utf-8") != expected_prompt:
        raise ReconciliationError("raw prompt is not the exact rebuilt prompt")
    if exit_path.read_text(encoding="utf-8") != "CANDIDATE_EXIT=0\n":
        raise ReconciliationError("candidate exit code is not exactly zero")
    parent_records = read_jsonl(arguments.parent_rollout)
    child_records = read_jsonl(arguments.child_rollout)
    events = read_jsonl(events_path)
    identity = validate_identity(parent_records, child_records, baseline, arguments.task_name)
    expected_assignment = expected_prompt.split("\nEXACT CHILD ASSIGNMENT:\n\n", 1)[1].rstrip("\n")
    lifecycle = validate_parent_lifecycle(parent_records, identity, expected_assignment)
    child_process = validate_child_process(
        child_records,
        baseline,
        arguments.process_marker,
        lifecycle["tracked_process_id"],
        lifecycle["close_called_at"],
        lifecycle["close_returned_at"],
    )
    validate_headless_events(events, identity["parent_thread_id"])
    catalog = validate_parent_catalog(stderr_path, identity["parent_thread_id"])
    if identity["child_thread_id"] not in last_path.read_text(encoding="utf-8"):
        raise ReconciliationError("last message omits the close-provided child identity")

    first = host_observation(
        baseline,
        arguments.candidate,
        arguments.process_marker,
        lifecycle["tracked_process_id"],
    )
    time.sleep(arguments.barrier_delay_seconds)
    second = host_observation(
        baseline,
        arguments.candidate,
        arguments.process_marker,
        lifecycle["tracked_process_id"],
    )
    observations = [first, second]
    if any(
        observation["tracked_process_id_present"]
        or observation["marked_process_match_count"] != 0
        or observation["candidate_open_file_count"] != 0
        for observation in observations
    ):
        raise ReconciliationError("post-close host barrier observed a live probe process")

    raw_paths = {
        "prompt": prompt_path,
        "events": events_path,
        "stderr": stderr_path,
        "last_message": last_path,
        "candidate_exit": exit_path,
        "parent_rollout": arguments.parent_rollout,
        "child_rollout": arguments.child_rollout,
    }
    raw_artifacts = {
        name: {
            "path": str(path),
            "sha256": sha256_file(path),
            "line_count": len(path.read_text(encoding="utf-8").splitlines()),
        }
        for name, path in raw_paths.items()
    }
    return {
        "schema": 1,
        "evidence_kind": "native_standard_worker_nonempty_tracked_process_close",
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "probe_baseline": baseline,
        "runtime": {
            "codex_semantic_version": semantic_version,
            "candidate_selection_path": str(arguments.candidate.absolute()),
            "candidate_resolved_path": str(arguments.candidate.resolve(strict=True)),
            "candidate_sha256": arguments.candidate_sha256,
            "candidate_size_bytes": arguments.candidate.stat().st_size,
            "code_mode_host_selection_path": str(arguments.code_mode_host.absolute()),
            "code_mode_host_resolved_path": str(
                arguments.code_mode_host.resolve(strict=True)
            ),
            "code_mode_host_sha256": arguments.code_mode_host_sha256,
            "candidate_exit_code": 0,
            "parent_model_provider": "openai",
            "child_model_provider": "openai",
            "sandbox": "read-only",
            "approval_policy": "never",
            "gui_app_server_selected": False,
            "credential_value_observed": False,
        },
        "probe_guard": {
            "wrapper": "probes/codex_plaintext_candidate_wrapper.sh",
            "wrapper_sha256": sha256_file(PROBES / "codex_plaintext_candidate_wrapper.sh"),
            "prompt_builder": "probes/build_p5b_tracked_process_probe_prompt.py",
            "prompt_builder_sha256": sha256_file(
                PROBES / "build_p5b_tracked_process_probe_prompt.py"
            ),
            "authorization": (
                "CODEX_G4_P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED="
                "schema1-exact-tracked-process"
            ),
            "candidate_and_code_mode_host_sha256_bound": True,
        },
        "raw_artifacts": raw_artifacts,
        "identity": identity,
        "parent_runtime_final_catalog": catalog,
        "native_lifecycle": lifecycle,
        "child_process": child_process,
        "post_termination_host_barrier": {
            "observations": observations,
            "stable_git_frontier": True,
            "tracked_process_absent": True,
            "exact_marker_absent": True,
            "candidate_open_file_count_zero": True,
            "strong_global_process_tree_quiescence_claimed": False,
        },
        "reconciler": {
            "path": "probes/reconcile_g4_nonempty_tracked_process_close.py",
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "verdict": {
            "native_standard_worker_nonempty_tracked_process_exit_qualified": True,
            "real_sessionmeta_identity_join_qualified": True,
            "post_termination_host_barrier_qualified_for_this_run": True,
            "g4_closed_catalog_process_surface_qualified": False,
            "mutation_capable_actor_termination_qualified": False,
            "detached_or_untracked_process_quiescence_qualified": False,
            "strong_global_process_tree_quiescence_qualified": False,
            "p5b_state": "partial",
            "phase1_complete": False,
            "direct_write_qualified": False,
            "phase2_state": "closed",
            "phase3_state": "closed",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--parent-rollout", type=Path, required=True)
    parser.add_argument("--child-rollout", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--code-mode-host", type=Path, required=True)
    parser.add_argument("--code-mode-host-sha256", required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--process-marker", required=True)
    parser.add_argument("--barrier-delay-seconds", type=float, default=2.0)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not 0.1 <= arguments.barrier_delay_seconds <= 10.0:
        print("P5b nonempty reconciliation denied: invalid barrier delay", file=sys.stderr)
        return 2
    try:
        receipt = reconcile(arguments)
        descriptor = os.open(
            arguments.output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, UnicodeDecodeError, ReconciliationError) as error:
        print(f"P5b nonempty reconciliation denied: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
