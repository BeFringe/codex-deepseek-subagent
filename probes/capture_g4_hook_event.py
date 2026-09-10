#!/usr/bin/env python3

"""Capture one raw qualification Hook input before delegating to the guard."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


def _atomic_write(directory: Path, name: str, payload: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
    temporary = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        destination = directory / name
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    arguments = parser.parse_args()

    raw_input = sys.stdin.buffer.read()
    try:
        hook_input = json.loads(raw_input)
    except json.JSONDecodeError as error:
        print(f"Hook input was invalid JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(hook_input, dict):
        print("Hook input must be a JSON object.", file=sys.stderr)
        return 2
    event = str(hook_input.get("hook_event_name") or "unknown")
    safe_event = "".join(character if character.isalnum() else "_" for character in event)
    stem = f"{time.time_ns()}-{safe_event}-{uuid.uuid4().hex}"
    _atomic_write(arguments.events, f"{stem}.stdin.json", raw_input)

    completed = subprocess.run(
        [
            sys.executable,
            str(arguments.guard),
            "--state-directory",
            str(arguments.state),
            "--plaintext-agent-type",
            "g4_qualification_probe_worker",
        ],
        input=raw_input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    _atomic_write(arguments.events, f"{stem}.stdout.json", completed.stdout)
    _atomic_write(arguments.events, f"{stem}.stderr", completed.stderr)
    sys.stdout.buffer.write(completed.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(completed.stderr)
    sys.stderr.buffer.flush()
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
