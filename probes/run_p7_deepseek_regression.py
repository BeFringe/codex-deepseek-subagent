#!/usr/bin/env python3

"""Run one isolated, product-independent native DeepSeek P7 regression."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from build_p7_deepseek_regression_prompt import build_inputs


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "probes" / "codex_deepseek_regression_candidate_wrapper.sh"
ROLE = ROOT / "agents" / "v4-flash-worker.toml"
HANDOFF = ROOT / "hooks" / "plaintext_handoff.py"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        **kwargs,
    )


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def initialize_probe_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="codex-p7-deepseek-regression.", dir="/private/tmp"))
    (root / "fixtures").mkdir()
    shutil.copyfile(ROOT / "fixtures" / "smoke-input.txt", root / "fixtures" / "smoke-input.txt")
    initialized = run(["git", "init", "-b", "main", str(root)])
    if initialized.returncode != 0:
        raise RuntimeError(initialized.stderr.strip())
    added = run(["git", "-C", str(root), "add", "fixtures/smoke-input.txt"])
    if added.returncode != 0:
        raise RuntimeError(added.stderr.strip())
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "P7 DeepSeek Probe",
        "GIT_AUTHOR_EMAIL": "p7-deepseek-probe@invalid",
        "GIT_COMMITTER_NAME": "P7 DeepSeek Probe",
        "GIT_COMMITTER_EMAIL": "p7-deepseek-probe@invalid",
    }
    committed = run(
        ["git", "-C", str(root), "commit", "-m", "product-independent smoke fixture"],
        env=environment,
    )
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip())
    return root.resolve()


def read_session_meta(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                if record.get("type") == "session_meta" and isinstance(record.get("payload"), dict):
                    return record["payload"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return None


def matching_rollouts(root: Path, started_epoch: float) -> list[dict[str, Any]]:
    sessions = Path.home() / ".codex" / "sessions"
    matches = []
    for path in sessions.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < started_epoch - 5:
                continue
        except OSError:
            continue
        meta = read_session_meta(path)
        if not meta or meta.get("cwd") != str(root):
            continue
        source = meta.get("source")
        kind = "child" if isinstance(source, dict) and "subagent" in source else "parent"
        matches.append(
            {
                "kind": kind,
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "session_id": meta.get("session_id"),
                "id": meta.get("id"),
                "parent_thread_id": meta.get("parent_thread_id"),
                "agent_role": meta.get("agent_role"),
                "agent_path": meta.get("agent_path"),
                "model_provider": meta.get("model_provider"),
                "source": source,
            }
        )
    return sorted(matches, key=lambda value: (value["kind"], value["path"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--task-name", default="p7_deepseek_readonly_1")
    arguments = parser.parse_args()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("P7 DeepSeek regression denied: credential is absent", file=sys.stderr)
        return 78
    candidate = arguments.candidate.resolve()
    if sha256_file(candidate) != arguments.candidate_sha256:
        print("P7 DeepSeek regression denied: candidate digest mismatch", file=sys.stderr)
        return 78

    probe_root = initialize_probe_root()
    handoff_root = Path(
        tempfile.mkdtemp(prefix="codex-p7-deepseek-handoff.", dir="/private/tmp")
    ).resolve()
    artifact_root = Path(
        tempfile.mkdtemp(prefix="codex-p7-deepseek-artifacts.", dir="/private/tmp")
    ).resolve()
    marker = secrets.token_hex(16)
    inputs = build_inputs(probe_root, arguments.task_name, marker)
    assignment_path = artifact_root / "assignment.txt"
    prompt_path = artifact_root / "parent-prompt.txt"
    write_text(assignment_path, inputs["assignment"])
    write_text(prompt_path, inputs["parent_prompt"])

    environment = {
        **os.environ,
        "CODEX_DEEPSEEK_HANDOFF_DIR": str(handoff_root),
    }
    staged = run(
        [
            sys.executable,
            str(HANDOFF),
            "--mode",
            "stage",
            "--state-directory",
            str(handoff_root),
            "--ttl-seconds",
            "900",
        ],
        input=inputs["assignment"],
        env=environment,
    )
    stage_stdout = artifact_root / "stage.stdout"
    stage_stderr = artifact_root / "stage.stderr"
    write_text(stage_stdout, staged.stdout)
    write_text(stage_stderr, staged.stderr)

    manifest: dict[str, Any] = {
        "schema": 1,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "probe_root": str(probe_root),
        "handoff_root": str(handoff_root),
        "artifact_root": str(artifact_root),
        "task_name": arguments.task_name,
        "marker_sha256": hashlib.sha256(marker.encode()).hexdigest(),
        "credential_present": True,
        "credential_value_recorded": False,
        "candidate": {
            "path": str(candidate),
            "sha256": arguments.candidate_sha256,
            "bytes": candidate.stat().st_size,
        },
        "inputs": {
            "assignment_path": str(assignment_path),
            "assignment_sha256": sha256_file(assignment_path),
            "parent_prompt_path": str(prompt_path),
            "parent_prompt_sha256": sha256_file(prompt_path),
            "role_path": str(ROLE),
            "role_sha256": sha256_file(ROLE),
            "wrapper_path": str(WRAPPER),
            "wrapper_sha256": sha256_file(WRAPPER),
            "handoff_script_path": str(HANDOFF),
            "handoff_script_sha256": sha256_file(HANDOFF),
        },
        "stage": {
            "exit_code": staged.returncode,
            "stdout_path": str(stage_stdout),
            "stdout_sha256": sha256_file(stage_stdout),
            "stderr_path": str(stage_stderr),
            "stderr_sha256": sha256_file(stage_stderr),
        },
    }

    if staged.returncode != 0:
        manifest_path = artifact_root / "run-manifest.json"
        write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"completed": False, "manifest": str(manifest_path)}))
        return staged.returncode

    stage_result = json.loads(staged.stdout)
    manifest["stage"]["handoff_id"] = stage_result.get("handoff_id")
    candidate_environment = {
        **environment,
        "CODEX_P7_DEEPSEEK_REGRESSION_AUTHORIZED": "schema1-native-readonly",
        "CODEX_G4_CANDIDATE_BIN": str(candidate),
        "CODEX_G4_CANDIDATE_SHA256": arguments.candidate_sha256,
        "CODEX_P7_DEEPSEEK_ROLE_CONFIG": str(ROLE),
        "CODEX_P7_DEEPSEEK_ROLE_SHA256": sha256_file(ROLE),
        "CODEX_P7_DEEPSEEK_PROBE_ROOT": str(probe_root),
    }
    command = [
        str(WRAPPER),
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--dangerously-bypass-hook-trust",
        "--json",
        "-C",
        str(probe_root),
        "-",
    ]
    started_epoch = time.time()
    completed = run(
        command,
        input=inputs["parent_prompt"],
        env=candidate_environment,
        timeout=900,
    )
    stdout_path = artifact_root / "candidate.stdout.jsonl"
    stderr_path = artifact_root / "candidate.stderr"
    write_text(stdout_path, completed.stdout)
    write_text(stderr_path, completed.stderr)
    state_names = sorted(path.name for path in handoff_root.iterdir())
    status = run(
        ["git", "-C", str(probe_root), "status", "--short", "--untracked-files=all"]
    )
    head = run(["git", "-C", str(probe_root), "rev-parse", "HEAD"])
    rollouts = matching_rollouts(probe_root, started_epoch)
    manifest["candidate_run"] = {
        "exit_code": completed.returncode,
        "stdout_path": str(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr_path": str(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
        "stderr_bytes": stderr_path.stat().st_size,
        "rollouts": rollouts,
    }
    manifest["post_run"] = {
        "handoff_state_names": state_names,
        "pending_present": "v4_flash_worker.pending.json" in state_names,
        "claimed_or_failed": [
            name
            for name in state_names
            if name.startswith("v4_flash_worker.claimed.")
            or name.startswith("v4_flash_worker.failed.")
        ],
        "git_status_short": status.stdout.rstrip("\n"),
        "full_head": head.stdout.rstrip("\n"),
    }
    preliminary_complete = (
        completed.returncode == 0
        and "v4_flash_worker.pending.json" not in state_names
        and not manifest["post_run"]["claimed_or_failed"]
        and sum(value["kind"] == "parent" for value in rollouts) == 1
        and sum(value["kind"] == "child" for value in rollouts) == 1
        and not manifest["post_run"]["git_status_short"]
    )
    manifest["preliminary_complete"] = preliminary_complete
    manifest_path = artifact_root / "run-manifest.json"
    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "completed": preliminary_complete,
                "candidate_exit_code": completed.returncode,
                "manifest": str(manifest_path),
                "probe_root": str(probe_root),
                "artifact_root": str(artifact_root),
            },
            separators=(",", ":"),
        )
    )
    return 0 if preliminary_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
