#!/usr/bin/env python3

"""Build a hash-pinned one-shot G4 exact-path write qualification overlay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys


AGENT_TYPE = "g4_qualification_probe_worker"
EVENTS = {"SubagentStart", "PreToolUse", "PostToolUse", "PreCompact", "SubagentStop"}
TASK_RE = re.compile(r"^[a-z0-9_]+$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class OverlayError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tokens(command: object) -> list[str]:
    if not isinstance(command, str) or not command:
        return []
    try:
        return shlex.split(command)
    except ValueError as error:
        raise OverlayError("Hook command quoting is invalid") from error


def is_g4(command: object) -> bool:
    value = tokens(command)
    return any(
        value[index : index + 2] == ["--plaintext-agent-type", AGENT_TYPE]
        for index in range(len(value) - 1)
    )


def validate(task_name: str, target: Path, hook_script: Path) -> None:
    if not TASK_RE.fullmatch(task_name):
        raise OverlayError("task name is not canonical")
    temporary = Path("/private/tmp").resolve(strict=True)
    root = target.parent.resolve(strict=True)
    if (
        not target.is_absolute()
        or root.parent != temporary
        or target.resolve(strict=False) != target
        or target.exists()
        or target.is_symlink()
    ):
        raise OverlayError("target must be an absent direct child of a temporary root")
    if not (root / ".git").exists():
        raise OverlayError("target root is not a Git worktree")
    if not hook_script.is_absolute() or not hook_script.is_file():
        raise OverlayError("Hook script is not an absolute regular file")


def build(config: dict, *, task_name: str, target: Path, hook_script: Path) -> tuple[dict, dict]:
    validate(task_name, target, hook_script)
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        raise OverlayError("configuration has no hooks object")
    result = copy.deepcopy(config)
    changed = []
    command_count = 0
    for event in EVENTS:
        entries = result["hooks"].get(event)
        if not isinstance(entries, list):
            raise OverlayError(f"configuration has no {event} list")
        matches = []
        for matcher_index, matcher in enumerate(entries):
            if not isinstance(matcher, dict) or not isinstance(matcher.get("hooks"), list):
                continue
            for command_index, command in enumerate(matcher["hooks"]):
                if isinstance(command, dict) and command.get("type") == "command" and is_g4(command.get("command")):
                    matches.append((matcher_index, command_index))
        if len(matches) != 1:
            raise OverlayError(f"expected one G4 {event} command, found {len(matches)}")
        matcher_index, command_index = matches[0]
        command = entries[matcher_index]["hooks"][command_index]
        value = tokens(command["command"])
        script_indexes = [index for index, item in enumerate(value) if item.endswith("/compatibility_hook.py")]
        if len(script_indexes) != 1:
            raise OverlayError(f"G4 {event} command has no unique Hook script")
        value[script_indexes[0]] = str(hook_script)
        if event == "PreToolUse":
            if "--child-write-probe" in value:
                raise OverlayError("write probe option is already present")
            value.extend(["--child-write-probe", f"{task_name}={target}"])
        command["command"] = shlex.join(value)
        command_count += 1
        changed.append(event)
    for event, entries in hooks.items():
        if event not in EVENTS and result["hooks"].get(event) != entries:
            raise OverlayError("overlay changed a non-G4 event")
    return result, {
        "schema": 1,
        "authorization_ceiling": "qualification_only",
        "task_name": task_name,
        "target_path": str(target),
        "hook_script": str(hook_script),
        "changed_events": sorted(changed),
        "changed_command_count": command_count,
        "v4_entries_preserved": True,
    }


def write_new(path: Path, value: dict) -> None:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--hook-script", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if not SHA_RE.fullmatch(arguments.expected_input_sha256):
            raise OverlayError("input hash is invalid")
        observed = sha256(arguments.input)
        if observed != arguments.expected_input_sha256:
            raise OverlayError("input hash drifted")
        config = json.loads(arguments.input.read_text(encoding="utf-8"))
        overlay, report = build(
            config,
            task_name=arguments.task_name,
            target=arguments.target,
            hook_script=arguments.hook_script,
        )
        write_new(arguments.output, overlay)
        report["input_sha256"] = observed
        report["output_sha256"] = sha256(arguments.output)
    except (OSError, ValueError, json.JSONDecodeError, OverlayError) as error:
        print(f"child write overlay was not built: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
