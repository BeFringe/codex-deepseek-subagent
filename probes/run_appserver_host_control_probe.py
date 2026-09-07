#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import subprocess
import sys
import tempfile
import time


PROBE_DIRECTORY = Path(__file__).resolve().parent
if str(PROBE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROBE_DIRECTORY))

from check_runtime_evidence_index import (  # noqa: E402
    DEFAULT_INDEX,
    REPO_ROOT,
    evidence_path,
    load_index,
    runtime_identity,
    verify_current_evidence,
)


SAFE_ENVIRONMENT_KEYS = {"CODEX_HOME", "PATH", "TMPDIR", "LANG", "RUST_LOG"}


class ProbeError(RuntimeError):
    pass


def probe_configuration(
    index_path: Path = DEFAULT_INDEX, repo_root: Path = REPO_ROOT
) -> dict:
    index = load_index(index_path)
    failures = verify_current_evidence(index, repo_root)
    if failures:
        raise ProbeError("current runtime evidence is inconsistent: " + "; ".join(failures))
    baseline = json.loads(
        evidence_path(index, "installed_baseline", repo_root).read_text(encoding="utf-8")
    )
    return {
        "runtime_role": index["current_runtime_role"],
        "identity": runtime_identity(index),
        "binary": Path(baseline["codex_app"]["app_server_binary"]),
        "binary_sha256": baseline["codex_app"]["app_server_sha256"],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def isolated_environment(isolated_codex_home: Path) -> dict[str, str]:
    return {
        "CODEX_HOME": str(isolated_codex_home),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": "/private/tmp",
        "LANG": "C.UTF-8",
        "RUST_LOG": "error",
    }


def initialize_message() -> dict:
    return {
        "method": "initialize",
        "id": 0,
        "params": {
            "clientInfo": {
                "name": "g4_isolated_probe",
                "title": "G4 isolated probe",
                "version": "1",
            },
            "capabilities": {"experimentalApi": True},
        },
    }


def fs_write_message(path: Path, payload: bytes) -> dict:
    return {
        "method": "fs/writeFile",
        "id": 1,
        "params": {
            "path": str(path),
            "dataBase64": base64.b64encode(payload).decode("ascii"),
        },
    }


def process_spawn_message(root: Path, output_path: Path) -> dict:
    return {
        "method": "process/spawn",
        "id": 2,
        "params": {
            "command": ["/usr/bin/touch", str(output_path)],
            "processHandle": "g4-process-1",
            "cwd": str(root),
        },
    }


def _send(stream, message: dict) -> None:
    stream.write(json.dumps(message, separators=(",", ":")) + "\n")
    stream.flush()


def _read_until(stream, selector, predicate, *, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = selector.select(deadline - time.monotonic())
        if not ready:
            break
        line = stream.readline()
        if not line:
            break
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProbeError("App Server emitted invalid JSONL") from error
        if isinstance(item, dict) and predicate(item):
            return item
    raise ProbeError("timed out waiting for a sanitized App Server response")


def _read_process_completion(stream, selector, *, timeout: float) -> tuple[dict, dict]:
    deadline = time.monotonic() + timeout
    response = None
    exit_notification = None
    while time.monotonic() < deadline and (response is None or exit_notification is None):
        ready = selector.select(deadline - time.monotonic())
        if not ready:
            break
        line = stream.readline()
        if not line:
            break
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProbeError("App Server emitted invalid JSONL") from error
        if not isinstance(item, dict):
            continue
        if item.get("id") == 2:
            response = item
        elif (
            item.get("method") == "process/exited"
            and item.get("params", {}).get("processHandle") == "g4-process-1"
        ):
            exit_notification = item
    if response is None or exit_notification is None:
        raise ProbeError("process/spawn response or exit notification is missing")
    return response, exit_notification


def _disk_observation(fs_path: Path, process_path: Path) -> dict:
    def one(path: Path) -> dict:
        exists = path.is_file()
        return {
            "exists": exists,
            "sha256": sha256_file(path) if exists else None,
        }

    return {"fs_write": one(fs_path), "process_spawn": one(process_path)}


def run_probe(
    binary: Path,
    expected_sha256: str,
    identity: dict,
    *,
    runtime_role: str = "current_signed_runtime",
    timeout: float = 10.0,
) -> dict:
    if not binary.is_absolute():
        raise ProbeError("Codex binary path must be absolute")
    binary = binary.resolve(strict=True)
    observed_sha256 = sha256_file(binary)
    if observed_sha256 != expected_sha256:
        raise ProbeError("Codex binary SHA-256 does not match the pinned value")

    process = None
    with tempfile.TemporaryDirectory(
        prefix="codex-g4-appserver-home-"
    ) as isolated_home_name, tempfile.TemporaryDirectory(
        prefix="codex-g4-appserver-root-"
    ) as isolated_root_name:
        isolated_home = Path(isolated_home_name)
        isolated_root = Path(isolated_root_name)
        environment = isolated_environment(isolated_home)
        if set(environment) != SAFE_ENVIRONMENT_KEYS:
            raise ProbeError("isolated environment is not the exact closed key set")
        version = subprocess.run(
            [str(binary), "--version"],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.strip()
        if version != f"codex-cli {identity['codex_version']}":
            raise ProbeError("Codex binary version is not pinned")

        fs_path = isolated_root / "fs-write-sentinel.txt"
        process_path = isolated_root / "process-spawn-sentinel.txt"
        process = subprocess.Popen(
            [str(binary), "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=environment,
            cwd=isolated_root,
        )
        try:
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise ProbeError("App Server stdio was not created")
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)

            _send(process.stdin, initialize_message())
            initialize = _read_until(
                process.stdout, selector, lambda item: item.get("id") == 0, timeout=timeout
            )
            if "error" in initialize:
                raise ProbeError("App Server initialize returned an error")
            _send(process.stdin, {"method": "initialized"})

            payload = b"g4-isolated-fs-write\n"
            _send(process.stdin, fs_write_message(fs_path, payload))
            fs_response = _read_until(
                process.stdout, selector, lambda item: item.get("id") == 1, timeout=timeout
            )
            if "error" in fs_response:
                raise ProbeError("fs/writeFile returned an error")

            _send(process.stdin, process_spawn_message(isolated_root, process_path))
            spawn_response, exited = _read_process_completion(
                process.stdout, selector, timeout=timeout
            )
            if "error" in spawn_response:
                raise ProbeError("process/spawn returned an error")

            before_eof = _disk_observation(fs_path, process_path)
            process.stdin.close()
            app_server_exit = process.wait(timeout=timeout)
            time.sleep(0.2)
            after_eof = _disk_observation(fs_path, process_path)
            stderr_line_count = len(process.stderr.read().splitlines())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=timeout)

    return {
        "schema": 1,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "runtime_role": runtime_role,
        "codex_version": identity["codex_version"],
        "source_commit": identity["source_commit"],
        "binary_path": str(binary),
        "binary_sha256": observed_sha256,
        "transport": "disposable-stdio",
        "explicit_environment_keys": sorted(SAFE_ENVIRONMENT_KEYS),
        "credential_environment_inherited": False,
        "client_auth_supplied": False,
        "thread_started": False,
        "thread_identity_supplied": False,
        "initialize_ok": True,
        "fs_write_response_ok": True,
        "process_spawn_response_ok": True,
        "process_exit_code": exited.get("params", {}).get("exitCode"),
        "app_server_exit_code_after_stdin_eof": app_server_exit,
        "app_server_stderr_line_count": stderr_line_count,
        "before_server_eof": before_eof,
        "bounded_post_termination_disk_observation": after_eof,
        "temporary_roots_removed_after_probe": True,
        "client_connection_sufficient_for_observed_host_control": True,
        "native_child_reachability_proven": False,
        "pretooluse_child_mediation_proven": False,
        "strong_global_quiescence_proven": False,
        "phase1_complete": False,
        "direct_write_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--codex-binary", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        configuration = probe_configuration(args.release_index)
        result = run_probe(
            args.codex_binary or configuration["binary"],
            args.expected_sha256 or configuration["binary_sha256"],
            configuration["identity"],
            runtime_role=configuration["runtime_role"],
        )
    except (
        KeyError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        ProbeError,
        ValueError,
    ) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
