#!/usr/bin/env python3

"""Build one hash-pinned, exact-target G4 sandbox qualification overlay."""

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


TARGET_AGENT_TYPE = "g4_qualification_probe_worker"
TARGET_EVENT = "PreToolUse"
TARGET_MATCHER = "*"
OPTION = "--child-sandbox-probe"
PROBE_ROOT = Path("/private/tmp")
TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class OverlayError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise OverlayError(f"cannot read Hooks file: {error}") from error
    return digest.hexdigest()


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OverlayError(f"cannot decode input Hooks file: {error}") from error
    if not isinstance(value, dict):
        raise OverlayError("input Hooks file must contain a JSON object")
    return value


def _command_tokens(command: object) -> list[str]:
    if not isinstance(command, str) or not command:
        return []
    try:
        return shlex.split(command)
    except ValueError as error:
        raise OverlayError("Hook command has invalid shell quoting") from error


def _is_target_command(command: object) -> bool:
    tokens = _command_tokens(command)
    matches = [
        index
        for index, token in enumerate(tokens[:-1])
        if token == "--plaintext-agent-type"
        and tokens[index + 1] == TARGET_AGENT_TYPE
    ]
    if len(matches) > 1:
        raise OverlayError("Hook command repeats the target agent-type argument")
    return len(matches) == 1


def validate_probe_target(task_name: str, target: Path) -> tuple[str, Path]:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise OverlayError("sandbox probe task name is not canonical")
    try:
        root = PROBE_ROOT.resolve(strict=True)
        parent = target.parent.resolve(strict=True)
    except OSError as error:
        raise OverlayError("sandbox probe parent is unavailable") from error
    if not target.is_absolute() or parent != root or target.resolve(strict=False) != target:
        raise OverlayError("sandbox probe target must be a canonical direct /private/tmp child")
    if target.exists() or target.is_symlink():
        raise OverlayError("sandbox probe target must be absent before overlay creation")
    return task_name, target


def build_overlay(config: dict, *, task_name: str, target: Path) -> tuple[dict, dict]:
    task_name, target = validate_probe_target(task_name, target)
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        raise OverlayError("Hooks configuration has no hooks object")
    event_entries = hooks.get(TARGET_EVENT)
    if not isinstance(event_entries, list):
        raise OverlayError("Hooks configuration has no PreToolUse list")
    candidates: list[tuple[int, int]] = []
    for matcher_index, matcher in enumerate(event_entries):
        if not isinstance(matcher, dict) or matcher.get("matcher") != TARGET_MATCHER:
            continue
        commands = matcher.get("hooks")
        if not isinstance(commands, list):
            raise OverlayError("PreToolUse matcher hooks must be a list")
        for command_index, command in enumerate(commands):
            if not isinstance(command, dict) or command.get("type") != "command":
                continue
            if _is_target_command(command.get("command")):
                candidates.append((matcher_index, command_index))
    if len(candidates) != 1:
        raise OverlayError(
            f"expected exactly one G4 PreToolUse command, found {len(candidates)}"
        )
    matcher_index, command_index = candidates[0]
    result = copy.deepcopy(config)
    command = result["hooks"][TARGET_EVENT][matcher_index]["hooks"][command_index]
    tokens = _command_tokens(command["command"])
    if OPTION in tokens:
        raise OverlayError("child sandbox probe is already configured")
    specification = f"{task_name}={target}"
    command["command"] += " " + OPTION + " " + shlex.quote(specification)
    changed_events = [
        event
        for event in sorted(set(hooks) | set(result["hooks"]))
        if hooks.get(event) != result["hooks"].get(event)
    ]
    if changed_events != [TARGET_EVENT]:
        raise OverlayError("overlay changed an unexpected Hook event set")
    return result, {
        "schema": 1,
        "authorization_ceiling": "qualification_sandbox_probe_only",
        "task_name": task_name,
        "target_path": str(target),
        "expected_command": f"/usr/bin/touch {target}",
        "changed_events": changed_events,
        "changed_command_count": 1,
        "authority_consumed_before_execution": True,
        "other_hook_events_unchanged": True,
    }


def write_private_new(path: Path, value: dict) -> None:
    encoded = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise OverlayError(f"cannot publish output Hooks file: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    arguments = parser.parse_args()
    try:
        if not HEX_SHA256.fullmatch(arguments.expected_input_sha256):
            raise OverlayError("expected input hash must be lowercase SHA-256")
        observed_input_sha256 = file_sha256(arguments.input)
        if observed_input_sha256 != arguments.expected_input_sha256:
            raise OverlayError("input Hooks hash does not match the pinned value")
        overlay, report = build_overlay(
            _load(arguments.input),
            task_name=arguments.task_name,
            target=arguments.target,
        )
        write_private_new(arguments.output, overlay)
        report["input_sha256"] = observed_input_sha256
        report["output_sha256"] = file_sha256(arguments.output)
    except (OverlayError, OSError, ValueError) as error:
        print(f"child sandbox probe overlay was not built: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
