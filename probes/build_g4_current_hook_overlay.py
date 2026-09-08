#!/usr/bin/env python3

"""Build a hash-pinned overlay that selects the current G4 Hook source only."""

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
EVENTS = ("SubagentStart", "PreToolUse", "PostToolUse", "PreCompact", "SubagentStop")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class OverlayError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_tokens(command: object) -> list[str]:
    if not isinstance(command, str) or not command:
        return []
    try:
        return shlex.split(command)
    except ValueError as error:
        raise OverlayError("Hook command quoting is invalid") from error


def is_target(tokens: list[str]) -> bool:
    indexes = [
        index
        for index in range(len(tokens) - 1)
        if tokens[index : index + 2] == ["--plaintext-agent-type", AGENT_TYPE]
    ]
    if len(indexes) > 1:
        raise OverlayError("G4 Hook command repeats the agent type")
    return len(indexes) == 1


def build(config: dict, *, hook_script: Path) -> tuple[dict, dict]:
    if not hook_script.is_absolute() or not hook_script.is_file():
        raise OverlayError("Hook script is not an absolute regular file")
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        raise OverlayError("configuration has no hooks object")
    result = copy.deepcopy(config)
    changed_commands = 0
    for event in EVENTS:
        entries = result["hooks"].get(event)
        if not isinstance(entries, list):
            raise OverlayError(f"configuration has no {event} list")
        matches: list[tuple[int, int, list[str]]] = []
        for matcher_index, matcher in enumerate(entries):
            if not isinstance(matcher, dict) or not isinstance(matcher.get("hooks"), list):
                continue
            for command_index, command in enumerate(matcher["hooks"]):
                if not isinstance(command, dict) or command.get("type") != "command":
                    continue
                tokens = command_tokens(command.get("command"))
                if is_target(tokens):
                    matches.append((matcher_index, command_index, tokens))
        if len(matches) != 1:
            raise OverlayError(f"expected one G4 {event} command, found {len(matches)}")
        matcher_index, command_index, tokens = matches[0]
        script_indexes = [
            index for index, token in enumerate(tokens) if token.endswith("/compatibility_hook.py")
        ]
        if len(script_indexes) != 1:
            raise OverlayError(f"G4 {event} command has no unique Hook script")
        tokens[script_indexes[0]] = str(hook_script)
        result["hooks"][event][matcher_index]["hooks"][command_index]["command"] = (
            shlex.join(tokens)
        )
        changed_commands += 1
    return result, {
        "schema": 1,
        "agent_type": AGENT_TYPE,
        "hook_script": str(hook_script),
        "changed_events": list(EVENTS),
        "changed_command_count": changed_commands,
        "qualification_options_added": False,
        "v4_entries_preserved": True,
    }


def write_new(path: Path, value: dict) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--hook-script", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if not SHA_RE.fullmatch(arguments.expected_input_sha256):
            raise OverlayError("input hash is invalid")
        observed = sha256(arguments.input)
        if observed != arguments.expected_input_sha256:
            raise OverlayError("input hash drifted")
        config = json.loads(arguments.input.read_text(encoding="utf-8"))
        overlay, report = build(config, hook_script=arguments.hook_script)
        write_new(arguments.output, overlay)
        report["input_sha256"] = observed
        report["output_sha256"] = sha256(arguments.output)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, OverlayError) as error:
        print(f"current G4 Hook overlay was not built: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
