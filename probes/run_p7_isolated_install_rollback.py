#!/usr/bin/env python3

"""Run a reversible isolated-home P7 install/reload/rollback probe."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"
SOURCE_RECEIPT = ROOT / "probes" / "g4-live-failed-apply-patch-posttool-callback-20260908.json"
SOURCE_PATCH = ROOT / "probes" / "current-signed-runtime-failed-apply-patch-posttool-source-candidate.patch"
LIVE_PATHS = {
    "app_binary": Path("/Applications/Codex.app/Contents/Resources/codex"),
    "hooks_json": Path.home() / ".codex" / "hooks.json",
    "v4_agent": Path.home() / ".codex" / "agents" / "v4-flash-worker.toml",
    "v4_hook": (
        Path.home()
        / ".codex"
        / "hooks"
        / "codex-deepseek-subagent"
        / "plaintext_handoff.py"
    ),
}


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


def hash_existing(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    result = {}
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"required live baseline is unavailable: {label}")
        result[label] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return result


def initialize_worktree() -> Path:
    root = Path(
        tempfile.mkdtemp(prefix="codex-g4-write-posttool-install-", dir="/private/tmp")
    ).resolve()
    write_text(root / "baseline.txt", "before\n")
    initialized = run(["git", "init", "-b", "main", str(root)])
    if initialized.returncode != 0:
        raise RuntimeError(initialized.stderr.strip())
    added = run(["git", "-C", str(root), "add", "baseline.txt"])
    if added.returncode != 0:
        raise RuntimeError(added.stderr.strip())
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "P7 Install Probe",
        "GIT_AUTHOR_EMAIL": "p7-install-probe@invalid",
        "GIT_COMMITTER_NAME": "P7 Install Probe",
        "GIT_COMMITTER_EMAIL": "p7-install-probe@invalid",
    }
    committed = run(
        ["git", "-C", str(root), "commit", "-m", "isolated rollback baseline"],
        env=environment,
    )
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip())
    return root


def git(root: Path, *arguments: str) -> str:
    completed = run(["git", "-C", str(root), *arguments])
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Git observation failed")
    return completed.stdout.rstrip("\n")


def hook_config(script: Path, state: Path) -> dict[str, Any]:
    command = (
        f"python3 {json.dumps(str(script))} --state-directory "
        f"{json.dumps(str(state))} --plaintext-agent-type "
        "g4_qualification_probe_worker"
    )
    return {
        "description": "Isolated P7 failed-PostToolUse install/rollback probe",
        "hooks": {
            event: [
                {
                    "matcher": "^apply_patch$",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 15,
                            "statusMessage": f"P7 isolated {event}",
                            "additionalContextLimit": 0,
                        }
                    ],
                }
            ]
            for event in ("PreToolUse", "PostToolUse")
        },
    }


def copy_hook_runtime(destination: Path) -> dict[str, str]:
    destination.mkdir(parents=True, mode=0o700)
    hashes = {}
    for source in sorted((ROOT / "hooks").glob("*.py")):
        target = destination / source.name
        shutil.copyfile(source, target)
        target.chmod(0o600)
        hashes[source.name] = sha256_file(target)
    if "compatibility_hook.py" not in hashes:
        raise RuntimeError("compatibility Hook entry point was not installed")
    return hashes


def snapshot_rollouts(home: Path) -> list[dict[str, Any]]:
    result = []
    sessions = home / "sessions"
    if not sessions.is_dir():
        return result
    for path in sorted(sessions.rglob("*.jsonl")):
        result.append(
            {
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return result


def run_candidate(
    candidate: Path,
    candidate_sha256: str,
    codex_home: Path,
    worktree: Path,
    output_prefix: Path,
) -> dict[str, Any]:
    prompt = """Call apply_patch exactly once with the following patch. It must fail because the expected context is absent. Do not retry, repair, or call another tool. After the tool returns, answer exactly FAILED_PATCH_OBSERVED.

*** Begin Patch
*** Update File: baseline.txt
@@
-missing
+after
*** End Patch"""
    environment = {
        **os.environ,
        "CODEX_HOME": str(codex_home),
        "CODEX_G4_LIVE_SELECTION_AUTHORIZED": "schema2-paired-probe",
        "CODEX_G4_CANDIDATE_BIN": str(candidate),
        "CODEX_G4_CANDIDATE_SHA256": candidate_sha256,
        "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
        "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(worktree),
        "CODEX_G4_EXACT_WRITE_PROBE_AUTHORIZED": "schema1-exact-temporary-git-root",
        "CODEX_G4_FAILED_PATCH_CALLBACK_PROBE_AUTHORIZED": (
            "schema1-root-failed-apply-patch"
        ),
    }
    completed = run(
        [
            str(WRAPPER),
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--dangerously-bypass-hook-trust",
            "--json",
            "-C",
            str(worktree),
            "-",
        ],
        input=prompt,
        env=environment,
        timeout=900,
    )
    stdout_path = output_prefix.with_suffix(".stdout.jsonl")
    stderr_path = output_prefix.with_suffix(".stderr")
    write_text(stdout_path, completed.stdout)
    write_text(stderr_path, completed.stderr)
    return {
        "candidate_path": str(candidate),
        "exit_code": completed.returncode,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "stdout_path": str(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stdout_bytes": stdout_path.stat().st_size,
        "stderr_path": str(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
        "stderr_bytes": stderr_path.stat().st_size,
    }


def move_if_present(source: Path, destination: Path) -> bool:
    if not source.exists() and not source.is_symlink():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--code-mode-host", type=Path, required=True)
    parser.add_argument("--code-mode-host-sha256", required=True)
    arguments = parser.parse_args()

    source_candidate = arguments.candidate.resolve()
    if not source_candidate.is_file() or source_candidate.is_symlink():
        print("P7 isolated install denied: candidate is unavailable", file=sys.stderr)
        return 78
    if sha256_file(source_candidate) != arguments.candidate_sha256:
        print("P7 isolated install denied: candidate hash mismatched", file=sys.stderr)
        return 78
    source_code_mode_host = arguments.code_mode_host.resolve()
    if not source_code_mode_host.is_file() or source_code_mode_host.is_symlink():
        print("P7 isolated install denied: code-mode host is unavailable", file=sys.stderr)
        return 78
    if sha256_file(source_code_mode_host) != arguments.code_mode_host_sha256:
        print("P7 isolated install denied: code-mode host hash mismatched", file=sys.stderr)
        return 78
    source_receipt = json.loads(SOURCE_RECEIPT.read_text(encoding="utf-8"))
    receipt_runtime = source_receipt.get("runtime", {})
    if (
        receipt_runtime.get("candidate_sha256") != arguments.candidate_sha256
        or receipt_runtime.get("code_mode_host_sha256")
        != arguments.code_mode_host_sha256
    ):
        print("P7 isolated install denied: callback source receipt mismatched", file=sys.stderr)
        return 78
    auth_source = Path.home() / ".codex" / "auth.json"
    if not auth_source.is_file():
        print("P7 isolated install denied: ChatGPT login is unavailable", file=sys.stderr)
        return 78

    live_before = hash_existing(LIVE_PATHS)
    worktree = initialize_worktree()
    install_root = Path(
        tempfile.mkdtemp(prefix="codex-p7-isolated-install.", dir="/private/tmp")
    ).resolve()
    install_root.chmod(0o700)
    codex_home = install_root / "codex-home"
    codex_home.mkdir(mode=0o700)
    os.symlink(auth_source, codex_home / "auth.json")
    artifacts = install_root / "artifacts"
    artifacts.mkdir(mode=0o700)
    installed_candidate = install_root / "installed" / "bin" / "codex"
    installed_code_mode_host = install_root / "installed" / "bin" / "codex-code-mode-host"
    installed_hooks = codex_home / "hooks" / "codex-deepseek-subagent"
    installed_state = install_root / "managed-state"
    hooks_json = codex_home / "hooks.json"
    managed_paths = [
        installed_candidate,
        installed_code_mode_host,
        installed_hooks,
        installed_state,
        hooks_json,
    ]
    baseline_absent = all(not path.exists() for path in managed_paths)
    installed_candidate.parent.mkdir(parents=True, mode=0o700)
    installed_state.mkdir(mode=0o700)

    manifest: dict[str, Any] = {
        "schema": 1,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "worktree": str(worktree),
        "install_root": str(install_root),
        "codex_home": str(codex_home),
        "artifacts": str(artifacts),
        "source_candidate": {
            "path": str(source_candidate),
            "sha256": arguments.candidate_sha256,
            "bytes": source_candidate.stat().st_size,
        },
        "source_code_mode_host": {
            "path": str(source_code_mode_host),
            "sha256": arguments.code_mode_host_sha256,
            "bytes": source_code_mode_host.stat().st_size,
        },
        "credential_boundary": {
            "auth_symlink_source": str(auth_source),
            "auth_value_read": False,
            "auth_value_printed": False,
            "auth_value_hashed": False,
            "auth_value_retained": False,
        },
        "harness": {
            "runner_path": str(Path(__file__).resolve()),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "wrapper_path": str(WRAPPER),
            "wrapper_sha256": sha256_file(WRAPPER),
            "source_receipt_path": str(SOURCE_RECEIPT),
            "source_receipt_sha256": sha256_file(SOURCE_RECEIPT),
            "source_patch_path": str(SOURCE_PATCH),
            "source_patch_sha256": sha256_file(SOURCE_PATCH),
        },
        "live_before": live_before,
        "baseline_managed_paths_absent": baseline_absent,
    }

    rollback_archive = artifacts / "rollback-archive"
    positive_completed = False
    try:
        shutil.copyfile(source_candidate, installed_candidate)
        installed_candidate.chmod(0o700)
        shutil.copyfile(source_code_mode_host, installed_code_mode_host)
        installed_code_mode_host.chmod(0o700)
        script_hashes = copy_hook_runtime(installed_hooks)
        write_text(
            hooks_json,
            json.dumps(
                hook_config(installed_hooks / "compatibility_hook.py", installed_state),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        hooks_json.chmod(0o600)
        manifest["install"] = {
            "candidate_path": str(installed_candidate),
            "candidate_sha256": sha256_file(installed_candidate),
            "code_mode_host_path": str(installed_code_mode_host),
            "code_mode_host_sha256": sha256_file(installed_code_mode_host),
            "hook_scripts": script_hashes,
            "hooks_json_path": str(hooks_json),
            "hooks_json_sha256": sha256_file(hooks_json),
            "state_path": str(installed_state),
            "skill_installed": False,
        }
        before_rollouts = snapshot_rollouts(codex_home)
        positive = run_candidate(
            installed_candidate,
            arguments.candidate_sha256,
            codex_home,
            worktree,
            artifacts / "installed-positive",
        )
        after_rollouts = snapshot_rollouts(codex_home)
        positive["new_rollouts"] = [
            item for item in after_rollouts if item not in before_rollouts
        ]
        manifest["positive_run"] = positive
        chain_path = installed_state / "hook_event_chain" / "current.json"
        manifest["positive_state"] = {
            "chain_path": str(chain_path),
            "chain_sha256": sha256_file(chain_path) if chain_path.is_file() else None,
            "writer_claim_names": sorted(
                path.name for path in (installed_state / "writer_claim").glob("*.json")
            ),
            "writer_receipts": [
                {
                    "path": str(path),
                    "sha256": sha256_file(path),
                }
                for path in sorted((installed_state / "writer_receipt").glob("*.json"))
            ],
        }
        positive_completed = bool(
            positive["exit_code"] == 0
            and chain_path.is_file()
            and not manifest["positive_state"]["writer_claim_names"]
            and len(manifest["positive_state"]["writer_receipts"]) == 1
        )
    finally:
        moved = {
            "candidate": move_if_present(
                installed_candidate, rollback_archive / "candidate" / "codex"
            ),
            "code_mode_host": move_if_present(
                installed_code_mode_host,
                rollback_archive / "candidate" / "codex-code-mode-host",
            ),
            "hooks_json": move_if_present(
                hooks_json, rollback_archive / "configuration" / "hooks.json"
            ),
            "hook_scripts": move_if_present(
                installed_hooks, rollback_archive / "configuration" / "hook-scripts"
            ),
            "state": move_if_present(
                installed_state, rollback_archive / "diagnostic-state"
            ),
        }
        manifest["rollback"] = {
            "moved_to_archive": moved,
            "managed_paths_absent": all(not path.exists() for path in managed_paths),
            "archive_candidate_path": str(rollback_archive / "candidate" / "codex"),
            "archive_candidate_sha256": (
                sha256_file(rollback_archive / "candidate" / "codex")
                if (rollback_archive / "candidate" / "codex").is_file()
                else None
            ),
            "archive_code_mode_host_path": str(
                rollback_archive / "candidate" / "codex-code-mode-host"
            ),
            "archive_code_mode_host_sha256": (
                sha256_file(rollback_archive / "candidate" / "codex-code-mode-host")
                if (rollback_archive / "candidate" / "codex-code-mode-host").is_file()
                else None
            ),
            "auth_symlink_unchanged": (
                (codex_home / "auth.json").is_symlink()
                and Path(os.readlink(codex_home / "auth.json")) == auth_source
            ),
        }
        if "positive_state" in manifest:
            archived_state = rollback_archive / "diagnostic-state"
            manifest["positive_state"]["archived_chain_path"] = str(
                archived_state / "hook_event_chain" / "current.json"
            )
            for receipt in manifest["positive_state"]["writer_receipts"]:
                receipt["archived_path"] = str(
                    archived_state / "writer_receipt" / Path(receipt["path"]).name
                )

    if positive_completed and manifest["rollback"]["managed_paths_absent"]:
        before_negative_rollouts = snapshot_rollouts(codex_home)
        negative = run_candidate(
            Path(manifest["rollback"]["archive_candidate_path"]),
            arguments.candidate_sha256,
            codex_home,
            worktree,
            artifacts / "rollback-negative",
        )
        after_negative_rollouts = snapshot_rollouts(codex_home)
        negative["new_rollouts"] = [
            item for item in after_negative_rollouts if item not in before_negative_rollouts
        ]
        negative["managed_state_recreated"] = installed_state.exists()
        manifest["negative_after_rollback"] = negative

    manifest["worktree_final"] = {
        "branch": git(worktree, "symbolic-ref", "--short", "HEAD"),
        "full_head": git(worktree, "rev-parse", "HEAD"),
        "status_short": git(worktree, "status", "--short", "--untracked-files=all"),
        "baseline_sha256": sha256_file(worktree / "baseline.txt"),
    }
    manifest["live_after"] = hash_existing(LIVE_PATHS)
    manifest["live_paths_unchanged"] = manifest["live_after"] == live_before
    manifest["gui_app_server_selected"] = False
    manifest["codex_cli_path_modified"] = False
    manifest["preliminary_complete"] = bool(
        baseline_absent
        and positive_completed
        and manifest["rollback"]["managed_paths_absent"]
        and "negative_after_rollback" in manifest
        and manifest["negative_after_rollback"]["exit_code"] == 0
        and not manifest["negative_after_rollback"]["managed_state_recreated"]
        and manifest["worktree_final"]["status_short"] == ""
        and manifest["live_paths_unchanged"]
    )
    manifest_path = artifacts / "run-manifest.json"
    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "completed": manifest["preliminary_complete"],
                "manifest": str(manifest_path),
                "manifest_sha256": sha256_file(manifest_path),
                "install_root": str(install_root),
                "worktree": str(worktree),
            },
            separators=(",", ":"),
        )
    )
    return 0 if manifest["preliminary_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
