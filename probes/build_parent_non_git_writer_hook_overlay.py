#!/usr/bin/env python3

"""Build a hash-pinned Hooks overlay for an explicit parent non-Git writer root."""

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

from private_output import open_private_output


TARGET_AGENT_TYPE = "g4_qualification_probe_worker"
TARGET_EVENTS = {"PreToolUse": "*", "PostToolUse": "apply_patch"}
OPTION = "--parent-non-git-writer-root"
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


def build_overlay(config: dict, *, non_git_root: Path) -> tuple[dict, dict]:
    canonical_root = non_git_root.resolve(strict=True)
    if canonical_root != non_git_root or not canonical_root.is_dir():
        raise OverlayError("non-Git writer root must be a canonical directory")
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        raise OverlayError("Hooks configuration has no hooks object")
    result = copy.deepcopy(config)
    changed_commands = []
    for event, matcher_value in TARGET_EVENTS.items():
        event_entries = hooks.get(event)
        if not isinstance(event_entries, list):
            raise OverlayError(f"Hooks configuration has no {event} list")
        candidates: list[tuple[int, int]] = []
        for matcher_index, matcher in enumerate(event_entries):
            if not isinstance(matcher, dict) or matcher.get("matcher") != matcher_value:
                continue
            commands = matcher.get("hooks")
            if not isinstance(commands, list):
                raise OverlayError(f"{event} matcher hooks must be a list")
            for command_index, command in enumerate(commands):
                if not isinstance(command, dict) or command.get("type") != "command":
                    continue
                if _is_target_command(command.get("command")):
                    candidates.append((matcher_index, command_index))
        if len(candidates) != 1:
            raise OverlayError(
                f"expected exactly one G4 {event} command, found {len(candidates)}"
            )
        matcher_index, command_index = candidates[0]
        target = result["hooks"][event][matcher_index]["hooks"][command_index]
        tokens = _command_tokens(target["command"])
        if OPTION in tokens:
            raise OverlayError(f"{event} non-Git writer root is already configured")
        target["command"] += " " + OPTION + " " + shlex.quote(str(canonical_root))
        changed_commands.append(event)
    changed_events = [
        event
        for event in sorted(set(hooks) | set(result["hooks"]))
        if hooks.get(event) != result["hooks"].get(event)
    ]
    if changed_events != sorted(TARGET_EVENTS):
        raise OverlayError("overlay changed an unexpected Hook event set")
    return result, {
        "schema": 1,
        "authorization_ceiling": "parent_only",
        "non_git_writer_root": str(canonical_root),
        "changed_events": changed_events,
        "changed_command_count": len(changed_commands),
        "other_hook_events_unchanged": True,
    }


def write_private_new(path: Path, value: dict) -> None:
    encoded = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")
    try:
        descriptor = open_private_output(path)
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
    parser.add_argument("--non-git-root", type=Path, required=True)
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
            non_git_root=arguments.non_git_root,
        )
        write_private_new(arguments.output, overlay)
        report["input_sha256"] = observed_input_sha256
        report["output_sha256"] = file_sha256(arguments.output)
    except (OverlayError, OSError, ValueError) as error:
        print(f"parent non-Git writer overlay was not built: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
