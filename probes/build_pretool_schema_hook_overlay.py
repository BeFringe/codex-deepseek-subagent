#!/usr/bin/env python3

"""Build a hash-pinned temporary Hooks overlay for the live schema probe."""

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
        raise OverlayError(f"cannot read input Hooks file: {error}") from error
    return digest.hexdigest()


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OverlayError(f"cannot decode input Hooks file: {error}") from error
    if not isinstance(value, dict):
        raise OverlayError("input Hooks file must contain a JSON object")
    return value


def _is_target_command(command: object) -> bool:
    if not isinstance(command, str) or not command:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError as error:
        raise OverlayError("Hook command has invalid shell quoting") from error
    matches = [
        index
        for index, token in enumerate(tokens[:-1])
        if token == "--plaintext-agent-type" and tokens[index + 1] == TARGET_AGENT_TYPE
    ]
    if len(matches) > 1:
        raise OverlayError("Hook command repeats the target agent-type argument")
    return len(matches) == 1


def build_overlay(config: dict, *, observation_root: Path) -> tuple[dict, dict]:
    canonical_root = observation_root.resolve(strict=True)
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        raise OverlayError("Hooks configuration has no hooks object")
    pretool = hooks.get("PreToolUse")
    if not isinstance(pretool, list):
        raise OverlayError("Hooks configuration has no PreToolUse list")
    candidates: list[tuple[int, int]] = []
    for matcher_index, matcher in enumerate(pretool):
        if not isinstance(matcher, dict) or matcher.get("matcher") != "*":
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
    command = result["hooks"]["PreToolUse"][matcher_index]["hooks"][command_index]
    original = command["command"]
    try:
        tokens = shlex.split(original)
    except ValueError as error:
        raise OverlayError("target Hook command has invalid shell quoting") from error
    if "--pretool-schema-observation-root" in tokens:
        raise OverlayError("schema observation is already enabled")
    command["command"] = (
        original
        + " --pretool-schema-observation-root "
        + shlex.quote(str(canonical_root))
    )
    changed = []
    for event_name in sorted(set(config["hooks"]) | set(result["hooks"])):
        if config["hooks"].get(event_name) != result["hooks"].get(event_name):
            changed.append(event_name)
    if changed != ["PreToolUse"]:
        raise OverlayError("overlay changed Hook events outside PreToolUse")
    return result, {
        "schema": 1,
        "changed_event": "PreToolUse",
        "changed_command_count": 1,
        "observation_root": str(canonical_root),
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
    parser.add_argument("--observation-root", type=Path, required=True)
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
            observation_root=arguments.observation_root,
        )
        write_private_new(arguments.output, overlay)
        report["input_sha256"] = observed_input_sha256
        report["output_sha256"] = file_sha256(arguments.output)
    except (OverlayError, OSError, ValueError) as error:
        print(f"PreToolUse schema overlay was not built: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
