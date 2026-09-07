#!/usr/bin/env python3

"""Probe whether App Server exit is a strong barrier for spawned process trees."""

from __future__ import annotations

import argparse
import datetime as dt
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

from check_runtime_evidence_index import DEFAULT_INDEX  # noqa: E402
from run_appserver_host_control_probe import (  # noqa: E402
    ProbeError,
    _read_until,
    _send,
    initialize_message,
    isolated_environment,
    probe_configuration,
    sha256_file,
)


PROCESS_HANDLE = "g4-detached-late-writer"


def detached_late_writer_message(
    root: Path, ready_path: Path, late_path: Path, delay_seconds: float
) -> dict:
    if delay_seconds <= 0:
        raise ProbeError("late-writer delay must be positive")
    child_code = "\n".join(
        (
            "import os",
            "import signal",
            "import time",
            "from pathlib import Path",
            f"ready_path = Path({str(ready_path)!r})",
            f"late_path = Path({str(late_path)!r})",
            "child_pid = os.fork()",
            "if child_pid == 0:",
            "    os.setsid()",
            "    signal.signal(signal.SIGTERM, signal.SIG_IGN)",
            "    ready_path.write_bytes(b'ready\\n')",
            f"    time.sleep({delay_seconds!r})",
            "    late_path.write_bytes(b'late\\n')",
            "    os._exit(0)",
            "time.sleep(30)",
        )
    )
    return {
        "method": "process/spawn",
        "id": 7,
        "params": {
            "command": ["/usr/bin/python3", "-c", child_code],
            "processHandle": PROCESS_HANDLE,
            "cwd": str(root),
        },
    }


def _wait_for_path(path: Path, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return True
        time.sleep(0.01)
    return path.is_file()


def run_probe(
    index_path: Path = DEFAULT_INDEX,
    *,
    delay_seconds: float = 0.8,
    post_exit_observation_seconds: float = 1.2,
    timeout: float = 10.0,
) -> dict:
    if post_exit_observation_seconds <= delay_seconds:
        raise ProbeError("post-exit observation must exceed the child delay")
    if not hasattr(os, "fork"):
        raise ProbeError("detached process-tree probe requires POSIX fork")

    configuration = probe_configuration(index_path)
    binary = configuration["binary"].resolve(strict=True)
    observed_binary_sha256 = sha256_file(binary)
    if observed_binary_sha256 != configuration["binary_sha256"]:
        raise ProbeError("Codex binary SHA-256 does not match semantic baseline")

    server = None
    with tempfile.TemporaryDirectory(
        prefix="codex-g4-quiescence-home-"
    ) as home_name, tempfile.TemporaryDirectory(
        prefix="codex-g4-quiescence-root-"
    ) as root_name:
        home = Path(home_name)
        root = Path(root_name)
        ready_path = root / "detached-ready"
        late_path = root / "late-write"
        server = subprocess.Popen(
            [str(binary), "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=isolated_environment(home),
            cwd=root,
        )
        try:
            if server.stdin is None or server.stdout is None or server.stderr is None:
                raise ProbeError("App Server stdio was not created")
            selector = selectors.DefaultSelector()
            selector.register(server.stdout, selectors.EVENT_READ)
            _send(server.stdin, initialize_message())
            initialized = _read_until(
                server.stdout, selector, lambda item: item.get("id") == 0, timeout=timeout
            )
            if "error" in initialized:
                raise ProbeError("App Server initialize returned an error")
            _send(server.stdin, {"method": "initialized"})
            _send(
                server.stdin,
                detached_late_writer_message(
                    root, ready_path, late_path, delay_seconds
                ),
            )
            spawned = _read_until(
                server.stdout, selector, lambda item: item.get("id") == 7, timeout=timeout
            )
            if "error" in spawned:
                raise ProbeError("detached process/spawn returned an error")
            if not _wait_for_path(ready_path, min(timeout, 3.0)):
                raise ProbeError("detached descendant did not publish its ready marker")

            before_eof_late_write = late_path.is_file()
            eof_started = time.monotonic()
            server.stdin.close()
            server_exit_code = server.wait(timeout=timeout)
            server_exit_at = time.monotonic()
            at_server_exit_late_write = late_path.is_file()
            time.sleep(post_exit_observation_seconds)
            after_observation_late_write = late_path.is_file()
            late_write_sha256 = (
                sha256_file(late_path) if after_observation_late_write else None
            )
            stderr_line_count = len(server.stderr.read().splitlines())
        finally:
            if server.poll() is None:
                server.terminate()
                server.wait(timeout=timeout)

    late_write_after_server_exit = (
        not before_eof_late_write
        and not at_server_exit_late_write
        and after_observation_late_write
    )
    return {
        "schema": 1,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "runtime_role": configuration["runtime_role"],
        "codex_version": configuration["identity"]["codex_version"],
        "source_commit": configuration["identity"]["source_commit"],
        "binary_sha256": observed_binary_sha256,
        "transport": "disposable-stdio",
        "client_auth_supplied": False,
        "thread_started": False,
        "thread_identity_supplied": False,
        "credential_environment_inherited": False,
        "process_api": "experimental-unsandboxed",
        "detached_descendant_ready_before_eof": True,
        "descendant_ignored_sigterm": True,
        "descendant_started_new_session": True,
        "delay_seconds": delay_seconds,
        "post_exit_observation_seconds": post_exit_observation_seconds,
        "app_server_exit_code": server_exit_code,
        "app_server_exit_latency_ms": round(
            (server_exit_at - eof_started) * 1000, 3
        ),
        "app_server_stderr_line_count": stderr_line_count,
        "late_write_exists_before_eof": before_eof_late_write,
        "late_write_exists_at_server_exit": at_server_exit_late_write,
        "late_write_exists_after_observation": after_observation_late_write,
        "late_write_sha256": late_write_sha256,
        "late_write_after_app_server_exit_observed": late_write_after_server_exit,
        "temporary_roots_removed_after_probe": True,
        "app_server_exit_strong_process_tree_barrier_proven": False,
        "external_process_tree_quiescence_barrier_required": (
            late_write_after_server_exit
        ),
        "native_child_termination_quiescence_proven": False,
        "phase1_complete": False,
        "direct_write_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--require-late-write", action="store_true")
    arguments = parser.parse_args()
    try:
        result = run_probe(arguments.release_index)
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
    result["valid"] = True
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    if arguments.require_late_write and not result[
        "late_write_after_app_server_exit_observed"
    ]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
