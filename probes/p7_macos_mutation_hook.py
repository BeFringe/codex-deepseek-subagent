#!/usr/bin/env python3

"""Capture one isolated macOS Hook event and delegate to the G4 guard."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid


def _write_exact_regular_file(path: Path, expected: bytes, replacement: bytes) -> None:
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise ValueError("negative fixture is not a regular file")
        current = bytearray()
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            current.extend(chunk)
        if bytes(current) != expected:
            raise ValueError("negative fixture was already modified")
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        view = memoryview(replacement)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("negative fixture write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_event(directory: Path, started_ns: int, record: dict) -> None:
    target = directory / f"{started_ns}-{uuid.uuid4().hex}.json"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--write-target")
    parser.add_argument("--dirty-foreign-after-start", type=Path)
    arguments = parser.parse_args()

    started_ns = time.time_ns()
    raw = sys.stdin.buffer.read()
    record = {
        "schema": 1,
        "started_ns": started_ns,
        "stdin_sha256": hashlib.sha256(raw).hexdigest(),
        "stdin_bytes": len(raw),
    }
    stdout, stderr, code = b"", b"", 2
    try:
        record["stdin_utf8"] = raw.decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Hook input is not an object")
        record["input"] = payload
        guard_arguments = [
            sys.executable,
            str(arguments.guard),
            "--state-directory",
            str(arguments.state),
            "--plaintext-agent-type",
            "g4_qualification_probe_worker",
        ]
        if arguments.write_target:
            guard_arguments += ["--child-write-probe", arguments.write_target]
        result = subprocess.run(
            guard_arguments,
            input=raw,
            capture_output=True,
            timeout=20,
            check=False,
        )
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
        if (
            arguments.dirty_foreign_after_start
            and payload.get("hook_event_name") == "SubagentStart"
        ):
            target = arguments.dirty_foreign_after_start
            output = json.loads(stdout) if stdout.strip() else {}
            context = output.get("hookSpecificOutput", {}).get("additionalContext", "")
            root = Path(payload["cwd"]).resolve(strict=True)
            if not (
                code == 0
                and "BEGIN CODEX WORKER CAPSULE" in context
                and payload.get("agent_type") == "g4_qualification_probe_worker"
                and root.parent == Path("/private/tmp").resolve(strict=True)
                and root.name.startswith("codex-g4-write-macos-")
                and target == root / "foreign.txt"
                and target.resolve(strict=True) == target
                and not target.is_symlink()
            ):
                raise ValueError("negative fixture boundary rejected")
            before = target.read_bytes()
            after = b"FOREIGN_DIRTY_BYTES_MUST_SURVIVE\n"
            _write_exact_regular_file(target, b"FOREIGN_TRACKED_BASELINE\n", after)
            record["negative_fixture_setup"] = {
                "source": "isolated_test_fixture_after_child_binding_before_model_start",
                "path": str(target),
                "before_sha256": hashlib.sha256(before).hexdigest(),
                "after_sha256": hashlib.sha256(after).hexdigest(),
                "test_only_injection": True,
            }
        record["stdout"] = stdout.decode("utf-8")
        record["stderr"] = stderr.decode("utf-8")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        record["observer_error"] = type(error).__name__
        stdout, stderr, code = b"", b"P7 Hook observer failed closed\n", 2
    record["exit_code"] = code
    record["finished_ns"] = time.time_ns()
    _publish_event(arguments.events, started_ns, record)
    sys.stdout.buffer.write(stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
