#!/usr/bin/env python3

"""Build a hash-pinned temporary PreToolUse overlay for the P1 pair probe."""

from __future__ import annotations

import tempfile

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
# Support standalone importlib-based probe tests as well as direct CLI launch.
_probe_module_directory = str(Path(__file__).resolve().parent)
if _probe_module_directory not in sys.path:
    sys.path.insert(0, _probe_module_directory)
from private_output import open_private_output


OPERATIONS = ("spawn_agent", "send_message", "followup_task")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class OverlayError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_spec(value: str) -> tuple[str, str]:
    operation, separator, digest = value.partition("=")
    if not separator or operation not in OPERATIONS or SHA256_RE.fullmatch(digest) is None:
        raise argparse.ArgumentTypeError("message-sha256 must be operation=lowercase-sha256")
    return operation, digest


def validate_specs(specs: list[tuple[str, str]]) -> dict[str, str]:
    configured = dict(specs)
    if len(configured) != len(specs) or set(configured) != set(OPERATIONS):
        raise OverlayError("overlay requires one exact message hash per operation")
    return configured


def canonical_temporary_state(path: Path) -> Path:
    if not path.is_absolute():
        raise OverlayError("pair state directory must be absolute")
    resolved = path.resolve(strict=False)
    temporary_root = Path(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp").resolve().resolve(strict=True)
    if resolved != path or temporary_root not in resolved.parents:
        raise OverlayError("pair state directory must be a canonical /private/tmp descendant")
    if resolved.exists():
        if not resolved.is_dir() or any(resolved.iterdir()):
            raise OverlayError("pair state directory must be absent or empty")
    else:
        parent = resolved.parent.resolve(strict=True)
        if parent != resolved.parent or temporary_root not in parent.parents:
            raise OverlayError("pair state parent must be a canonical /private/tmp descendant")
    return resolved


def build_overlay(
    config: dict,
    *,
    guard_script: Path,
    state_directory: Path,
    configured: dict[str, str],
) -> tuple[dict, dict]:
    if not guard_script.is_absolute() or not guard_script.is_file():
        raise OverlayError("pair guard must be an absolute regular file")
    state_directory = canonical_temporary_state(state_directory)
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        raise OverlayError("configuration has no hooks object")
    pretool = hooks.get("PreToolUse")
    if not isinstance(pretool, list) or not pretool:
        raise OverlayError("configuration has no PreToolUse hooks")
    result = copy.deepcopy(config)
    target_matchers = [
        matcher
        for matcher in result["hooks"]["PreToolUse"]
        if isinstance(matcher, dict) and matcher.get("matcher") == "*"
    ]
    if len(target_matchers) != 1:
        raise OverlayError("expected one wildcard PreToolUse matcher")
    commands = target_matchers[0].get("hooks")
    if not isinstance(commands, list) or not commands:
        raise OverlayError("wildcard PreToolUse matcher has no commands")
    guard_path = str(guard_script)
    for command in commands:
        if not isinstance(command, dict) or command.get("type") != "command":
            continue
        try:
            tokens = shlex.split(command.get("command", ""))
        except ValueError as error:
            raise OverlayError("existing Hook command quoting is invalid") from error
        if guard_path in tokens or any(
            token.endswith("/plaintext_pair_probe_guard.py") for token in tokens
        ):
            raise OverlayError("plaintext pair guard is already installed")
    python = Path(sys.executable).resolve(strict=True)
    tokens = [str(python), guard_path, "--state-directory", str(state_directory)]
    for operation in OPERATIONS:
        tokens.extend(["--deny-second", f"{operation}={configured[operation]}"])
    commands.append(
        {
            "type": "command",
            "command": shlex.join(tokens),
            "timeout": 15,
            "statusMessage": "Checking P1 plaintext pair",
            "additionalContextLimit": 0,
        }
    )
    changed = [
        event
        for event in sorted(set(config["hooks"]) | set(result["hooks"]))
        if config["hooks"].get(event) != result["hooks"].get(event)
    ]
    if changed != ["PreToolUse"]:
        raise OverlayError("overlay changed an unexpected Hook event set")
    return result, {
        "schema": 1,
        "changed_events": changed,
        "added_hook_count": 1,
        "guard_script": guard_path,
        "guard_script_sha256": file_sha256(guard_script),
        "state_directory": str(state_directory),
        "configured_message_sha256": dict(sorted(configured.items())),
        "existing_hooks_preserved": True,
        "v4_entries_preserved": True,
        "g4_authority_hook_preserved": True,
        "qualification_only": True,
        "grants_mutation_authority": False,
    }


def write_private_new(path: Path, value: dict) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor = open_private_output(path)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--guard-script", type=Path, required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--message-sha256", action="append", type=parse_spec, required=True)
    arguments = parser.parse_args()
    try:
        if SHA256_RE.fullmatch(arguments.expected_input_sha256) is None:
            raise OverlayError("expected input hash is invalid")
        observed = file_sha256(arguments.input)
        if observed != arguments.expected_input_sha256:
            raise OverlayError("input Hooks hash drifted")
        config = json.loads(arguments.input.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise OverlayError("input Hooks file is not an object")
        overlay, report = build_overlay(
            config,
            guard_script=arguments.guard_script,
            state_directory=arguments.state_directory,
            configured=validate_specs(arguments.message_sha256),
        )
        write_private_new(arguments.output, overlay)
        report["input_sha256"] = observed
        report["output_sha256"] = file_sha256(arguments.output)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, OverlayError) as error:
        print(f"plaintext pair overlay was not built: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
