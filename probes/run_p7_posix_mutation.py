#!/usr/bin/env python3

"""Run one isolated macOS G4 mutation attempt without self-qualification."""

from __future__ import annotations

import argparse
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
import tomllib
import uuid

from build_g4_write_probe_prompt import build as build_write_prompt
from p7_windows_model_catalog import build as build_catalog, validate_generated
from private_output import open_private_output


ROOT = Path(__file__).resolve().parents[1]
AGENT_TYPE = "g4_qualification_probe_worker"
SOURCE_BASE = "3d2ee51ca2d5db578f328aa75e20aa22c0197c9a"
PROVIDER = {
    "name": "deepseek",
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com",
    "env_key": "DEEPSEEK_API_KEY",
}


class ProbeError(RuntimeError):
    pass


def require(value: object, message: str) -> None:
    if not value:
        raise ProbeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, check=True, capture_output=True, **kwargs)


def git(root: Path, *arguments: str) -> str:
    return run(["git", "--no-optional-locks", "-C", str(root), *arguments]).stdout.decode().rstrip("\n")


def write_private_json(path: Path, value: object) -> None:
    descriptor = open_private_output(path)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_private_text(path: Path, value: str) -> None:
    descriptor = open_private_output(path)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def snapshot(root: Path) -> dict[str, object]:
    names = run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    ).stdout.split(b"\0")
    paths = [name.decode("utf-8") for name in names if name]
    return {
        "root": str(root.resolve()),
        "branch": git(root, "symbolic-ref", "--short", "HEAD"),
        "head": git(root, "rev-parse", "HEAD"),
        "status": git(root, "status", "--short", "--untracked-files=all"),
        "index_sha256": hashlib.sha256(
            run(["git", "-C", str(root), "ls-files", "--stage", "-z"]).stdout
        ).hexdigest(),
        "files": {name: sha256_file(root / name) for name in paths},
    }


def role_text(*, negative: bool) -> str:
    mutation = (
        "For the explicit negative qualification, issue exactly the supplied foreign-path apply_patch request so PreToolUse can reject it. "
        "This grants no foreign-path ownership or successful-write authority. Do not retry, use shell, stage, commit, push, config, or another tool. "
        "Use the actual native denial, trusted Hook identity, and frozen baseline; return exactly TASK.CONTEXT_LOST."
        if negative
        else
        "Require the Hook-delivered write capsule and writer lease for exactly its single owned path before one apply_patch. "
        "Never use shell, stage, commit, push, config, another path, or another tool. Use only trusted PostToolUse observation for final facts."
    )
    return (
        'name = "g4_qualification_probe_worker"\n'
        'description = "Isolated exact-path mutation qualification only"\n'
        'sandbox_mode = "workspace-write"\n'
        f'model = {json.dumps(PROVIDER["model"])}\n'
        'developer_instructions = """Perform only the exact parent qualification assignment. '
        'User consent is an upper bound, never a lease or integration authority. '
        + mutation
        + ' Never self-adjudicate."""\n'
    )


def negative_prompt(root: Path, task_name: str, baseline: dict[str, object]) -> str:
    write_prompt = build_write_prompt(root, task_name, root / "qualified.txt")
    authority = json.loads(
        write_prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
            "\nEND CODEX WORKER AUTHORITY", 1
        )[0]
    )
    child = (
        "This is a deliberate negative guard qualification. The capsule owns only qualified.txt; foreign.txt is outside that ownership and its dirty bytes must survive. "
        "Request native apply_patch exactly once with the exact patch below so trusted PreToolUse rejects it before execution. Do not retry or emulate denial in prose. "
        "After the actual denial return exactly TASK.CONTEXT_LOST. The independent owner will verify the native denial, unchanged foreign bytes, callback, close, and disk barriers.\n\n"
        "*** Begin Patch\n"
        f"*** Update File: {root / 'foreign.txt'}\n"
        "@@\n"
        "-FOREIGN_DIRTY_BYTES_MUST_SURVIVE\n"
        "+FOREIGN_TRACKED_BASELINE\n"
        "*** End Patch\n\n"
        "BEGIN CODEX WORKER AUTHORITY\n"
        + json.dumps(authority, separators=(",", ":"), sort_keys=True)
        + "\nEND CODEX WORKER AUTHORITY"
    )
    return (
        "Perform one product-independent native G4 negative mutation probe. Do not mutate files yourself.\n"
        f"1. Spawn exactly one {AGENT_TYPE} with task_name={task_name}, fork_turns=none, and the exact assignment below.\n"
        "2. Wait for its exact TASK.CONTEXT_LOST callback.\n"
        f"3. Close exactly /root/{task_name}; require session_loop_terminated, tracked_process_termination_confirmed, and closed_catalog_actor_quiescence_claimed with empty captured process lists.\n"
        "4. List agents exactly once and require the child absent. Do not spawn, mutate, retry, or adjudicate.\n\n"
        "EXACT CHILD ASSIGNMENT:\n\n"
        + child
        + "\n"
    )


def invocation(candidate: Path, root: Path, role: Path, catalog: Path) -> list[str]:
    overrides: dict[str, object] = {
        "model_provider": "openai",
        "model": "gpt-6-astra",
        "model_catalog_json": str(catalog),
        "forced_login_method": "chatgpt",
        "features.multi_agent_v2.enabled": True,
        "features.multi_agent_v2.message_delivery": "plaintext",
        "features.multi_agent_v2.tool_namespace": "g4_assignment",
        f"features.multi_agent_v2.child_model_providers.{AGENT_TYPE}": PROVIDER["name"],
        f"agents.{AGENT_TYPE}.config_file": str(role),
        "model_providers.deepseek.name": "P7 DeepSeek",
        "model_providers.deepseek.base_url": PROVIDER["base_url"],
        "model_providers.deepseek.env_key": PROVIDER["env_key"],
        "model_providers.deepseek.wire_api": "responses",
        "model_providers.deepseek.requires_openai_auth": False,
        "model_providers.deepseek.request_max_retries": 0,
        "model_providers.deepseek.stream_max_retries": 0,
        "model_providers.deepseek.supports_namespace_tools": False,
        "model_providers.deepseek.requires_function_call_output_adjacency": True,
        "features.code_mode_host": False,
    }
    result = [str(candidate)]
    for name, value in overrides.items():
        result += ["-c", name + "=" + json.dumps(value)]
    return result + [
        "-a", "never", "-s", "workspace-write", "exec", "--ignore-user-config",
        "--ignore-rules", "--dangerously-bypass-hook-trust", "--json", "-C", str(root), "-",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-patch-artifact", type=Path, required=True)
    parser.add_argument("--source-patch-sha256", required=True)
    parser.add_argument("--source-replay-sha256", required=True)
    parser.add_argument("--source-chain-receipt", type=Path)
    parser.add_argument("--case", choices=("positive", "negative"), required=True)
    parser.add_argument("--feasibility-receipt", type=Path)
    parser.add_argument("--reuse-root", type=Path)
    parser.add_argument("--root-preparation-receipt", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    arguments = parser.parse_args()
    try:
        require(platform.system() == "Darwin", "native macOS is required")
        require("CODEX_CLI_PATH" not in os.environ, "CODEX_CLI_PATH must be absent")
        require(PROVIDER["env_key"] in os.environ, "provider credential is absent")
        candidate = arguments.candidate.resolve(strict=True)
        source = arguments.source_root.resolve(strict=True)
        source_patch = arguments.source_patch_artifact.resolve(strict=True)
        source_chain = None
        require(candidate.is_file() and not candidate.is_symlink(), "candidate is not a regular file")
        require(sha256_file(candidate) == arguments.candidate_sha256, "candidate hash mismatch")
        require(
            source_patch.is_file()
            and not source_patch.is_symlink()
            and sha256_file(source_patch) == arguments.source_patch_sha256,
            "source patch artifact mismatch",
        )
        if arguments.source_chain_receipt is not None:
            source_chain_path = arguments.source_chain_receipt.resolve(strict=True)
            source_chain = json.loads(source_chain_path.read_text(encoding="utf-8"))
            require(
                source_chain.get("classification")
                == "current_signed_runtime_g4_explicit_plaintext_delivery_candidate"
                and source_chain.get("source", {}).get("base_commit") == SOURCE_BASE
                and source_chain.get("fresh_replay", {}).get(
                    "canonical_cumulative_diff_sha256"
                )
                == arguments.source_replay_sha256,
                "source patch-chain receipt does not bind the cumulative replay",
            )
            chain_entries = source_chain.get("patch_chain")
            require(
                isinstance(chain_entries, list)
                and len(chain_entries) == 2
                and chain_entries[-1].get("sha256") == arguments.source_patch_sha256,
                "source patch-chain membership is not exact",
            )
            for entry in chain_entries:
                artifact = (ROOT / entry["path"]).resolve(strict=True)
                require(
                    artifact.is_relative_to(ROOT)
                    and artifact.is_file()
                    and not artifact.is_symlink()
                    and sha256_file(artifact) == entry["sha256"],
                    "source patch-chain artifact mismatch",
                )
        require(git(source, "rev-parse", "HEAD") == SOURCE_BASE, "source commit mismatch")
        source_diff = run(["git", "-C", str(source), "diff", "--binary", "--full-index", "HEAD"]).stdout
        require(hashlib.sha256(source_diff).hexdigest() == arguments.source_replay_sha256, "source patch replay drift")
        require(not git(source, "diff", "--check", "HEAD"), "source patch has whitespace errors")
        cargo = tomllib.loads((source / "codex-rs" / "Cargo.toml").read_text(encoding="utf-8"))
        source_version = cargo["workspace"]["package"]["version"]
        require(
            run([str(candidate), "--version"]).stdout.decode().strip() == f"codex-cli {source_version}",
            "candidate semantic version differs from source",
        )
        auth = Path.home() / ".codex" / "auth.json"
        require(auth.is_file(), "current ChatGPT login file is absent")

        run_id = f"p7-macos-mutation-{arguments.case}-{uuid.uuid4().hex}"
        artifacts = Path(tempfile.mkdtemp(prefix=run_id + ".", dir="/private/tmp")).resolve()
        artifacts.chmod(0o700)
        preparation = None
        if arguments.reuse_root is not None:
            require(arguments.case == "positive", "only a final positive run may reuse a root")
            require(arguments.root_preparation_receipt is not None, "root reuse needs a preparation receipt")
            root = arguments.reuse_root.resolve(strict=True)
            preparation = json.loads(arguments.root_preparation_receipt.read_text(encoding="utf-8"))
            require(
                isinstance(preparation, dict)
                and preparation.get("classification") == "parent_reset_verified_macos_calibration_fixture"
                and preparation.get("root") == str(root),
                "root preparation receipt mismatch",
            )
        else:
            require(arguments.root_preparation_receipt is None, "preparation receipt without root reuse")
            root = Path(tempfile.mkdtemp(prefix="codex-g4-write-macos-", dir="/private/tmp")).resolve()
            root.chmod(0o700)
            (root / "docs").mkdir(mode=0o700)
            (root / "docs" / "phase1-evidence.md").write_text("Product-independent macOS mutation fixture.\n", encoding="utf-8")
            (root / "foreign.txt").write_bytes(b"FOREIGN_TRACKED_BASELINE\n")
            git(root, "init", "-b", "main")
            git(root, "add", "docs/phase1-evidence.md", "foreign.txt")
            git(root, "-c", "user.name=P7 qualification", "-c", "user.email=p7@invalid", "commit", "-m", "macOS mutation fixture")
        require(
            root.parent == Path("/private/tmp")
            and root.name.startswith("codex-g4-write-macos-")
            and Path(git(root, "rev-parse", "--show-toplevel")).resolve() == root,
            "probe root is not an exact isolated Git top level",
        )
        baseline = snapshot(root)
        require(not baseline["status"], "probe root baseline is dirty")
        if preparation is not None:
            require(preparation.get("after") == baseline, "prepared root no longer matches its exact baseline")

        state = artifacts / "state"
        events = artifacts / "hook-events"
        events.mkdir(mode=0o700)
        runtime = artifacts / "hook-runtime"
        runtime.mkdir(mode=0o700)
        for path in (ROOT / "hooks").glob("*.py"):
            shutil.copyfile(path, runtime / path.name)
        observer = runtime / "p7_macos_mutation_hook.py"
        shutil.copyfile(ROOT / "probes" / observer.name, observer)
        role = artifacts / "role.toml"
        write_private_text(role, role_text(negative=arguments.case == "negative"))
        bundled_path = source / "codex-rs" / "models-manager" / "models.json"
        bundled = bundled_path.read_bytes()
        catalog = artifacts / "models.json"
        write_private_json(catalog, build_catalog(bundled, sha256_file(bundled_path), parent_slug="gpt-6-astra"))
        validate_generated(catalog.read_bytes(), sha256_file(catalog), bundled, parent_slug="gpt-6-astra")
        task_name = "p7_macos_" + arguments.case
        feasibility = None
        if arguments.feasibility_receipt is not None:
            feasibility_record = json.loads(arguments.feasibility_receipt.read_text(encoding="utf-8"))
            feasibility = feasibility_record.get("attestation")
            require(isinstance(feasibility, dict), "feasibility receipt has no attestation")
            require(
                feasibility_record.get("inputs", {}).get("baseline") == baseline
                and feasibility_record.get("inputs", {}).get("patch")
                == (
                    "*** Begin Patch\n"
                    f"*** Add File: {root / 'qualified.txt'}\n"
                    "+G4_CHILD_WRITE_QUALIFIED\n"
                    "*** End Patch"
                ),
                "feasibility receipt does not bind this exact root/head/path",
            )
        prompt = (
            negative_prompt(root, task_name, baseline)
            if arguments.case == "negative"
            else build_write_prompt(
                root,
                task_name,
                root / "qualified.txt",
                p5b_close_after_write=True,
                feasibility_attestation=feasibility,
            )
        )
        write_private_text(artifacts / "prompt.txt", prompt)
        assignment = prompt.split("EXACT CHILD ASSIGNMENT:\n\n", 1)[1].removesuffix("\n")
        write_private_text(artifacts / "assignment.txt", assignment)

        home = artifacts / "codex-home"
        home.mkdir(mode=0o700)
        os.symlink(auth, home / "auth.json")
        hook_args = [
            sys.executable, str(observer), "--guard", str(runtime / "compatibility_hook.py"),
            "--state", str(state), "--events", str(events),
            "--write-target", task_name + "=" + str(root / "qualified.txt"),
        ]
        if arguments.case == "negative":
            hook_args += ["--dirty-foreign-after-start", str(root / "foreign.txt")]
        hooks = json.loads((ROOT / "hooks" / "hooks.g4-qualification.posix.example.json").read_text(encoding="utf-8"))
        for groups in hooks["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    hook["command"] = shlex.join(hook_args)
                    hook["timeout"] = 30
        write_private_json(home / "hooks.json", hooks)
        argv = invocation(candidate, root, role, catalog)
        environment = dict(os.environ)
        parent_api_key_override_removed = "CODEX_API_KEY" in environment
        if parent_api_key_override_removed:
            del environment["CODEX_API_KEY"]
        environment.update({
            "CODEX_HOME": str(home),
            "CODEX_G4_TOOL_CATALOG_RECEIPT": "stderr-v2-parent-child-closed",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        manifest: dict[str, object] = {
            "schema": 1,
            "classification": "p7_macos_mutation_raw_attempt",
            "mutation_case": arguments.case,
            "run_id": run_id,
            "runner_pid": os.getpid(),
            "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
            "source_commit": SOURCE_BASE,
            "source_patch_sha256": arguments.source_patch_sha256,
            "source_replay_sha256": arguments.source_replay_sha256,
            "source_chain_receipt": (
                str(arguments.source_chain_receipt.resolve())
                if arguments.source_chain_receipt
                else None
            ),
            "source_chain_receipt_sha256": (
                sha256_file(arguments.source_chain_receipt)
                if arguments.source_chain_receipt
                else None
            ),
            "source_version": source_version,
            "candidate": str(candidate),
            "candidate_sha256": arguments.candidate_sha256,
            "provider": PROVIDER["name"],
            "model": PROVIDER["model"],
            "credential_present": True,
            "credential_values_recorded": False,
            "parent_api_key_override_removed": parent_api_key_override_removed,
            "requested_task_name": task_name,
            "root": str(root),
            "baseline": baseline,
            "state": str(state),
            "events": str(events),
            "home": str(home),
            "argv": argv,
            "harness_sha256": {
                name: sha256_file(ROOT / "probes" / name)
                for name in (
                    "run_p7_posix_mutation.py",
                    "p7_macos_mutation_hook.py",
                    "p7_windows_model_catalog.py",
                    "build_g4_write_probe_prompt.py",
                )
            },
            "feasibility_receipt": str(arguments.feasibility_receipt.resolve()) if arguments.feasibility_receipt else None,
            "feasibility_receipt_sha256": sha256_file(arguments.feasibility_receipt) if arguments.feasibility_receipt else None,
            "root_preparation_receipt": str(arguments.root_preparation_receipt.resolve()) if arguments.root_preparation_receipt else None,
            "root_preparation_receipt_sha256": sha256_file(arguments.root_preparation_receipt) if arguments.root_preparation_receipt else None,
            "phase1_complete": False,
            "direct_write_qualified": False,
        }
        stdout_path = artifacts / "stdout.jsonl"
        stderr_path = artifacts / "stderr.log"
        manifest["started_ns"] = time.time_ns()
        try:
            with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
                process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, env=environment)
                manifest["candidate_pid"] = process.pid
                try:
                    process.communicate(prompt.encode("utf-8"), timeout=arguments.timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=30)
                    manifest["timeout"] = True
                manifest["exit_code"] = process.returncode
        finally:
            (home / "auth.json").unlink(missing_ok=True)
            manifest["isolated_auth_removed"] = True
        manifest["process_exited_ns"] = time.time_ns()
        first = snapshot(root)
        first_at = time.time_ns()
        time.sleep(2.05)
        second = snapshot(root)
        second_at = time.time_ns()
        manifest["barrier_first"] = {"observed_ns": first_at, "snapshot": first}
        manifest["barrier_second"] = {"observed_ns": second_at, "snapshot": second}

        rollouts = artifacts / "rollouts"
        rollouts.mkdir(mode=0o700)
        for path in (home / "sessions").rglob("*.jsonl"):
            shutil.copyfile(path, rollouts / path.name)
        state_snapshot = artifacts / "state-snapshot"
        state_snapshot.mkdir(mode=0o700)
        if state.exists():
            for path in state.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    copy = state_snapshot / path.relative_to(state)
                    copy.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, copy)
        artifact_files = [
            stdout_path,
            stderr_path,
            artifacts / "prompt.txt",
            artifacts / "assignment.txt",
            role,
            catalog,
            home / "hooks.json",
        ]
        for directory in (runtime, events, rollouts, state_snapshot):
            artifact_files.extend(
                path
                for path in directory.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts
            )
        manifest["artifacts"] = {
            path.relative_to(artifacts).as_posix(): sha256_file(path)
            for path in artifact_files
        }
        write_private_json(artifacts / "manifest.json", manifest)
        print(artifacts / "manifest.json")
        return 2
    except (OSError, ProbeError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError, tomllib.TOMLDecodeError) as error:
        print(f"P7 macOS mutation denied: {error}", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
