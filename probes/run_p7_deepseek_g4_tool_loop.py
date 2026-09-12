#!/usr/bin/env python3

"""Run an isolated macOS DeepSeek G4 tool-loop comparison."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from build_g4_native_probe_prompt import build_prompt


ROOT = Path(__file__).resolve().parents[1]
HOOK_CAPTURE = ROOT / "probes" / "capture_g4_hook_event.py"
TASK_NAME = "p7_macos_deepseek"
AGENT_TYPE = "g4_qualification_probe_worker"
CATALOG_RECEIPT = "stderr-v2-parent-child-closed"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def run(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        **kwargs,
    )


def initialize_probe_root(root: Path) -> dict[str, str]:
    (root / "docs").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "docs" / "phase1-evidence.md",
        root / "docs" / "phase1-evidence.md",
    )
    initialized = run(["git", "init", "-b", "main", str(root)])
    if initialized.returncode != 0:
        raise RuntimeError(initialized.stderr.strip())
    added = run(["git", "-C", str(root), "add", "docs/phase1-evidence.md"])
    if added.returncode != 0:
        raise RuntimeError(added.stderr.strip())
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "P7 DeepSeek G4 Probe",
        "GIT_AUTHOR_EMAIL": "p7-deepseek-g4@invalid",
        "GIT_COMMITTER_NAME": "P7 DeepSeek G4 Probe",
        "GIT_COMMITTER_EMAIL": "p7-deepseek-g4@invalid",
    }
    committed = run(
        ["git", "-C", str(root), "commit", "-m", "isolated G4 baseline"],
        env=environment,
    )
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip())
    head = run(["git", "-C", str(root), "rev-parse", "HEAD"])
    return {"branch": "main", "head": head.stdout.strip()}


def copy_hook_runtime(destination: Path) -> dict[str, str]:
    destination.mkdir(parents=True, mode=0o700)
    hashes: dict[str, str] = {}
    for source in sorted((ROOT / "hooks").glob("*.py")):
        target = destination / source.name
        shutil.copyfile(source, target)
        target.chmod(0o600)
        hashes[target.name] = sha256_file(target)
    capture_target = destination / HOOK_CAPTURE.name
    shutil.copyfile(HOOK_CAPTURE, capture_target)
    capture_target.chmod(0o600)
    hashes[capture_target.name] = sha256_file(capture_target)
    if "compatibility_hook.py" not in hashes:
        raise RuntimeError("compatibility Hook entry point is unavailable")
    return hashes


def hook_configuration(
    python: Path,
    runtime: Path,
    state: Path,
    events: Path,
) -> dict[str, Any]:
    command = shlex.join(
        [
            str(python),
            str(runtime / HOOK_CAPTURE.name),
            "--guard",
            str(runtime / "compatibility_hook.py"),
            "--state",
            str(state),
            "--events",
            str(events),
        ]
    )
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event, matcher in (
        ("PreToolUse", "*"),
        ("PostToolUse", "^apply_patch$"),
        ("SubagentStart", f"^{AGENT_TYPE}$"),
        ("PreCompact", "*"),
        ("SubagentStop", f"^{AGENT_TYPE}$"),
    ):
        handler: dict[str, Any] = {
            "type": "command",
            "command": command,
            "timeout": 30,
            "statusMessage": f"P7 isolated {event}",
        }
        if event in {"PreToolUse", "PostToolUse"}:
            handler["additionalContextLimit"] = 0
        hooks[event] = [{"matcher": matcher, "hooks": [handler]}]
    return {
        "description": "Isolated product-independent P7 DeepSeek G4 tool-loop comparison",
        "hooks": hooks,
    }


def role_text() -> str:
    return f'''name = "{AGENT_TYPE}"

description = "Temporary read-only worker for product-independent Phase 1/G4 qualification."

developer_instructions = """
Execute only the exact product-independent Phase 1/G4 probe assignment supplied by the parent.
Remain read-only. Do not edit, stage, commit, push, install, change configuration, inspect credential values, request broader permissions, or touch unrelated product files.
Treat the immutable authority capsule injected by the trusted Hook as the complete scope. If it is missing, ambiguous, or reports context loss, call no tool and report the blocker.
Do not adjudicate your own correctness. Return only the requested observation and final attestation; parent, disk, and fresh-owner verification retain integration authority.
"""

sandbox_mode = "read-only"
model = "deepseek-v4-flash"
'''


def session_records(home: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    sessions = home / "sessions"
    if not sessions.is_dir():
        return records
    for path in sorted(sessions.rglob("*.jsonl")):
        selected: list[dict[str, Any]] = []
        kind = "unknown"
        with path.open(encoding="utf-8") as stream:
            for ordinal, line in enumerate(stream, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = record.get("payload")
                if record.get("type") == "session_meta" and isinstance(payload, dict):
                    source = payload.get("source")
                    kind = (
                        "child"
                        if isinstance(source, dict) and "subagent" in source
                        else "parent"
                    )
                    selected.append(
                        {
                            "ordinal": ordinal,
                            "type": "session_meta",
                            "payload": payload,
                        }
                    )
                elif record.get("type") == "response_item" and isinstance(payload, dict):
                    item_type = payload.get("type")
                    if item_type == "function_call" and (
                        payload.get("namespace") == "g4_assignment"
                        or payload.get("name") in {
                            "spawn_agent",
                            "wait_agent",
                            "list_agents",
                            "close_agent",
                        }
                    ):
                        selected.append(
                            {"ordinal": ordinal, "type": "response_item", "payload": payload}
                        )
                    elif item_type == "function_call_output":
                        selected.append(
                            {"ordinal": ordinal, "type": "response_item", "payload": payload}
                        )
                elif record.get("type") == "event_msg" and isinstance(payload, dict):
                    if payload.get("type") == "task_complete":
                        selected.append(
                            {"ordinal": ordinal, "type": "event_msg", "payload": payload}
                        )
        records.append(
            {
                "kind": kind,
                "path": str(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "records": selected,
            }
        )
    return records


def file_inventory(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    result = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        result.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return result


def observed_tool_loop(
    rollouts: list[dict[str, Any]],
    *,
    expected_namespace: str | None,
) -> dict[str, Any]:
    child_rollouts = [rollout for rollout in rollouts if rollout["kind"] == "child"]
    calls: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for rollout in child_rollouts:
        for record in rollout["records"]:
            payload = record["payload"]
            if record["type"] == "response_item" and payload.get("type") == "function_call":
                if payload.get("name") == "list_agents":
                    calls.append(payload)
            elif (
                record["type"] == "response_item"
                and payload.get("type") == "function_call_output"
            ):
                outputs.append(payload)
            elif record["type"] == "event_msg" and payload.get("error") is not None:
                errors.append(payload["error"])
    matching_outputs = []
    for call in calls:
        matching_outputs.extend(
            output
            for output in outputs
            if output.get("call_id") == call.get("call_id")
        )
    return {
        "child_rollout_count": len(child_rollouts),
        "list_agents_calls": calls,
        "function_call_outputs": outputs,
        "matching_call_id_outputs": matching_outputs,
        "exact_single_empty_arguments_call": (
            len(calls) == 1
            and calls[0].get("namespace") == expected_namespace
            and calls[0].get("arguments") == "{}"
        ),
        "matching_output_present": len(matching_outputs) == 1,
        "task_complete_errors": errors,
        "provider_reported_missing_tool_output": any(
            "No tool output found for tool call" in json.dumps(error)
            for error in errors
        ),
    }


def observed_parent_lifecycle(rollouts: list[dict[str, Any]]) -> dict[str, Any]:
    parent_rollouts = [rollout for rollout in rollouts if rollout["kind"] == "parent"]
    pending_names: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    for rollout in parent_rollouts:
        for record in rollout["records"]:
            if record["type"] != "response_item":
                continue
            payload = record["payload"]
            if payload.get("type") == "function_call":
                call_id = payload.get("call_id")
                name = payload.get("name")
                if isinstance(call_id, str) and isinstance(name, str):
                    pending_names[call_id] = name
            elif payload.get("type") == "function_call_output":
                call_id = payload.get("call_id")
                output = payload.get("output")
                if not isinstance(call_id, str) or not isinstance(output, str):
                    continue
                try:
                    parsed = json.loads(output)
                except json.JSONDecodeError:
                    parsed = None
                results.append(
                    {
                        "ordinal": record["ordinal"],
                        "call_id": call_id,
                        "name": pending_names.get(call_id),
                        "output": parsed,
                    }
                )
    close_results = [result for result in results if result["name"] == "close_agent"]
    close_result = close_results[-1]["output"] if close_results else None
    post_close_lists = [
        result
        for result in results
        if result["name"] == "list_agents"
        and close_results
        and result["ordinal"] > close_results[-1]["ordinal"]
    ]
    post_close_list = post_close_lists[-1]["output"] if post_close_lists else None
    agents = post_close_list.get("agents") if isinstance(post_close_list, dict) else None
    child_absent = isinstance(agents, list) and all(
        not isinstance(agent, dict) or agent.get("agent_name") != f"/root/{TASK_NAME}"
        for agent in agents
    )
    empty_process_maps = False
    if isinstance(close_result, dict):
        process_maps = [
            close_result.get("tracked_process_ids_by_thread"),
            close_result.get("confirmed_exit_process_ids_by_thread"),
            close_result.get("unconfirmed_exit_process_ids_by_thread"),
            close_result.get("unresolved_start_process_ids_by_thread"),
        ]
        empty_process_maps = all(
            isinstance(mapping, dict)
            and all(isinstance(values, list) and not values for values in mapping.values())
            for mapping in process_maps
        )
    return {
        "parent_rollout_count": len(parent_rollouts),
        "close_receipt": close_result,
        "post_close_list_agents": post_close_list,
        "post_close_child_absent": child_absent,
        "empty_process_id_maps": empty_process_maps,
        "close_catalog_quiesced": (
            isinstance(close_result, dict)
            and close_result.get("session_loop_terminated") is True
            and close_result.get("tracked_process_termination_confirmed") is True
            and close_result.get("closed_catalog_actor_quiescence_claimed") is True
            and empty_process_maps
            and child_absent
        ),
        "process_tree_quiescence_claimed": (
            close_result.get("process_tree_quiescence_claimed")
            if isinstance(close_result, dict)
            else None
        ),
    }


def state_disposition(state: Path) -> dict[str, Any]:
    active = file_inventory(state / "active")
    reported = file_inventory(state / "reported")
    unresolved = file_inventory(state / "unresolved")
    return {
        "active": active,
        "reported": reported,
        "unresolved": unresolved,
        "reported_without_active_or_unresolved": (
            len(reported) == 1 and not active and not unresolved
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--disable-provider-namespace-tools", action="store_true")
    parser.add_argument(
        "--require-provider-function-call-output-adjacency",
        action="store_true",
    )
    arguments = parser.parse_args()

    if platform.system() != "Darwin":
        print("P7 macOS comparison denied: host is not macOS", file=sys.stderr)
        return 78
    if "DEEPSEEK_API_KEY" not in os.environ:
        print("P7 macOS comparison denied: credential is absent", file=sys.stderr)
        return 78
    candidate = arguments.candidate.resolve()
    if not candidate.is_file() or candidate.is_symlink():
        print("P7 macOS comparison denied: candidate is unavailable", file=sys.stderr)
        return 78
    if sha256_file(candidate) != arguments.candidate_sha256:
        print("P7 macOS comparison denied: candidate digest mismatch", file=sys.stderr)
        return 78
    auth_source = Path.home() / ".codex" / "auth.json"
    if not auth_source.is_file():
        print("P7 macOS comparison denied: ChatGPT login is unavailable", file=sys.stderr)
        return 78

    artifact_root = Path(
        tempfile.mkdtemp(prefix="codex-p7-deepseek-g4-macos.", dir="/private/tmp")
    ).resolve()
    artifact_root.chmod(0o700)
    probe_root = artifact_root / "worktree"
    probe_root.mkdir(mode=0o700)
    baseline = initialize_probe_root(probe_root)
    codex_home = artifact_root / "codex-home"
    codex_home.mkdir(mode=0o700)
    os.symlink(auth_source, codex_home / "auth.json")
    runtime = codex_home / "hooks" / "codex-deepseek-subagent"
    state = artifact_root / "state"
    state.mkdir(mode=0o700)
    events = artifact_root / "hook-events"
    events.mkdir(mode=0o700)
    runtime_hashes = copy_hook_runtime(runtime)
    role = artifact_root / "role.toml"
    write_text(role, role_text())
    role.chmod(0o600)
    hooks_json = codex_home / "hooks.json"
    write_text(
        hooks_json,
        json.dumps(
            hook_configuration(Path(sys.executable).resolve(), runtime, state, events),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    hooks_json.chmod(0o600)
    prompt = build_prompt(
        probe_root,
        TASK_NAME,
        exact_list_agents_empty_arguments=True,
        close_after_callback=True,
    )
    prompt_path = artifact_root / "parent-prompt.txt"
    write_text(prompt_path, prompt)

    environment = {**os.environ}
    api_key_override_removed = environment.pop("CODEX_API_KEY", None) is not None
    environment.update(
        {
            "CODEX_HOME": str(codex_home),
            "CODEX_G4_TOOL_CATALOG_RECEIPT": CATALOG_RECEIPT,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    command = [
        str(candidate),
        "-c",
        'model_provider="openai"',
        "-c",
        'forced_login_method="chatgpt"',
        "-c",
        "features.multi_agent_v2.enabled=true",
        "-c",
        'features.multi_agent_v2.message_delivery="plaintext"',
        "-c",
        'features.multi_agent_v2.tool_namespace="g4_assignment"',
        "-c",
        (
            "features.multi_agent_v2.child_model_providers."
            f'{AGENT_TYPE}="deepseek"'
        ),
        "-c",
        f'agents.{AGENT_TYPE}.config_file={json.dumps(str(role))}',
        "-c",
        'model_providers.deepseek.name="P7 deepseek"',
        "-c",
        'model_providers.deepseek.base_url="https://api.deepseek.com"',
        "-c",
        'model_providers.deepseek.env_key="DEEPSEEK_API_KEY"',
        "-c",
        'model_providers.deepseek.wire_api="responses"',
        "-c",
        "model_providers.deepseek.requires_openai_auth=false",
        "-c",
        "model_providers.deepseek.request_max_retries=0",
        "-c",
        "model_providers.deepseek.stream_max_retries=0",
        "-c",
        "features.code_mode_host=false",
        "-a",
        "never",
        "-s",
        "read-only",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--dangerously-bypass-hook-trust",
        "--json",
        "-C",
        str(probe_root),
        "-",
    ]
    provider_overrides: list[str] = []
    if arguments.disable_provider_namespace_tools:
        provider_overrides.extend(
            ["-c", "model_providers.deepseek.supports_namespace_tools=false"]
        )
    if arguments.require_provider_function_call_output_adjacency:
        provider_overrides.extend(
            [
                "-c",
                "model_providers.deepseek.requires_function_call_output_adjacency=true",
            ]
        )
    if provider_overrides:
        insertion = command.index("features.code_mode_host=false") - 1
        command[insertion:insertion] = provider_overrides
    started_at = dt.datetime.now(dt.timezone.utc)
    completed = run(
        command,
        input=prompt,
        env=environment,
        timeout=arguments.timeout_seconds,
    )
    completed_at = dt.datetime.now(dt.timezone.utc)
    stdout_path = artifact_root / "candidate.stdout.jsonl"
    stderr_path = artifact_root / "candidate.stderr"
    write_text(stdout_path, completed.stdout)
    write_text(stderr_path, completed.stderr)

    rollouts = session_records(codex_home)
    expected_namespace = (
        None if arguments.disable_provider_namespace_tools else "g4_assignment"
    )
    tool_loop = observed_tool_loop(
        rollouts,
        expected_namespace=expected_namespace,
    )
    parent_lifecycle = observed_parent_lifecycle(rollouts)
    compatibility_state = state_disposition(state)
    git_status = run(
        ["git", "-C", str(probe_root), "status", "--short", "--untracked-files=all"]
    ).stdout.rstrip("\n")
    first_barrier = {
        "worktree": file_inventory(probe_root),
        "state": file_inventory(state),
        "events": file_inventory(events),
        "sessions": file_inventory(codex_home / "sessions"),
    }
    time.sleep(2)
    second_barrier = {
        "worktree": file_inventory(probe_root),
        "state": file_inventory(state),
        "events": file_inventory(events),
        "sessions": file_inventory(codex_home / "sessions"),
    }
    manifest = {
        "schema": 1,
        "classification": (
            "p7_macos_deepseek_g4_function_wire_adjacent_output_comparison"
            if arguments.disable_provider_namespace_tools
            and arguments.require_provider_function_call_output_adjacency
            else "p7_macos_deepseek_g4_function_wire_comparison"
            if arguments.disable_provider_namespace_tools
            else "p7_macos_deepseek_g4_namespaced_tool_loop_comparison"
        ),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "platform": platform.platform(),
        "artifact_root": str(artifact_root),
        "candidate": {
            "path": str(candidate),
            "sha256": arguments.candidate_sha256,
            "bytes": candidate.stat().st_size,
        },
        "credential_boundary": {
            "chatgpt_auth_symlink_source": str(auth_source),
            "chatgpt_auth_value_read": False,
            "deepseek_credential_present": True,
            "deepseek_credential_value_recorded": False,
            "process_codex_api_key_override_removed": api_key_override_removed,
        },
        "inputs": {
            "task_name": TASK_NAME,
            "agent_type": AGENT_TYPE,
            "probe_root": str(probe_root),
            "branch": baseline["branch"],
            "head": baseline["head"],
            "prompt_path": str(prompt_path),
            "prompt_sha256": sha256_file(prompt_path),
            "role_path": str(role),
            "role_sha256": sha256_file(role),
            "hooks_json_path": str(hooks_json),
            "hooks_json_sha256": sha256_file(hooks_json),
            "hook_runtime_sha256": runtime_hashes,
            "catalog_receipt": CATALOG_RECEIPT,
            "child_tool_arguments_required": {},
            "expected_child_tool_namespace": expected_namespace,
            "provider_namespace_tools_enabled": (
                not arguments.disable_provider_namespace_tools
            ),
            "provider_requires_function_call_output_adjacency": (
                arguments.require_provider_function_call_output_adjacency
            ),
        },
        "run": {
            "argv": command,
            "exit_code": completed.returncode,
            "stdout_path": str(stdout_path),
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_path": str(stderr_path),
            "stderr_sha256": sha256_file(stderr_path),
        },
        "rollouts": rollouts,
        "tool_loop": tool_loop,
        "parent_lifecycle": parent_lifecycle,
        "compatibility_state": compatibility_state,
        "post_exit": {
            "git_status_short": git_status,
            "first_barrier": first_barrier,
            "second_barrier": second_barrier,
            "two_barriers_equal": first_barrier == second_barrier,
        },
        "scope": {
            "read_only_only": True,
            "gui_app_server_selected": False,
            "live_hooks_modified": False,
            "direct_write_qualified": False,
        },
    }
    manifest_path = artifact_root / "run-manifest.json"
    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "candidate_exit_code": completed.returncode,
                "exact_single_empty_arguments_call": tool_loop[
                    "exact_single_empty_arguments_call"
                ],
                "matching_output_present": tool_loop["matching_output_present"],
                "provider_reported_missing_tool_output": tool_loop[
                    "provider_reported_missing_tool_output"
                ],
                "close_catalog_quiesced": parent_lifecycle["close_catalog_quiesced"],
                "reported_state_closed": compatibility_state[
                    "reported_without_active_or_unresolved"
                ],
                "two_barriers_equal": first_barrier == second_barrier,
                "git_status_short": git_status,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
