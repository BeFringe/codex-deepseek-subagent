#!/usr/bin/env python3

"""Inject one foreign dirty path after a durable G4 recovery epoch."""

from __future__ import annotations

import tempfile

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
# Support standalone importlib-based probe tests as well as direct CLI launch.
_probe_module_directory = str(Path(__file__).resolve().parent)
if _probe_module_directory not in sys.path:
    sys.path.insert(0, _probe_module_directory)
from private_output import open_private_output
import time


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from compatibility_state import StateStore, canonical_json  # noqa: E402
from runtime_guard import collect_git_snapshot  # noqa: E402


TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")
ROOT_NAME_RE = re.compile(r"^codex-g4-postcompact-drift-[A-Za-z0-9._-]+$")
TARGET_NAME = "foreign-postcompact-drift.txt"
TARGET_CONTENT = b"foreign postcompact scope drift\n"


class ProbeError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_exclusive(path: Path, content: bytes) -> None:
    descriptor = open_private_output(path)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def validate_root(root: Path) -> Path:
    resolved = root.resolve(strict=True)
    if resolved.parent != Path(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp").resolve() or not ROOT_NAME_RE.fullmatch(resolved.name):
        raise ProbeError("probe root is outside the fixed temporary namespace")
    return resolved


def _active_matches(store: StateStore, root: Path, task_name: str) -> list[tuple[Path, dict]]:
    directory = store.root / "active"
    if not directory.exists():
        return []
    matches: list[tuple[Path, dict]] = []
    for path in sorted(directory.glob("*.json")):
        envelope = store._validated_envelope(path)
        capsule = envelope["capsule"]
        if (
            capsule["requested_task_name"] == task_name
            and Path(capsule["root"]["path"]).resolve() == root
        ):
            matches.append((path, envelope))
    return matches


def inject_if_recovered(store: StateStore, root_value: Path, task_name: str) -> dict | None:
    root = validate_root(root_value)
    if not TASK_NAME_RE.fullmatch(task_name):
        raise ProbeError("task name is not canonical")
    target = root / TARGET_NAME
    with store.locked():
        matches = _active_matches(store, root, task_name)
        if not matches:
            return None
        if len(matches) != 1:
            raise ProbeError("active task/root binding is ambiguous")
        state_path, envelope = matches[0]
        capsule = envelope["capsule"]
        binding = envelope.get("binding")
        runtime = envelope.get("runtime")
        if capsule["canonical_agent_path"] != f"/root/{task_name}":
            raise ProbeError("capsule AgentPath is not exact")
        if capsule["assignment_mutation_mode"] != "read_only":
            raise ProbeError("scope-drift probe requires read-only authority")
        if capsule["owned_paths"] or capsule["excluded_paths"]:
            raise ProbeError("scope-drift probe requires empty path authority")
        if any(capsule["git_authority"].values()):
            raise ProbeError("scope-drift probe requires empty Git authority")
        if not isinstance(binding, dict) or binding.get("canonical_agent_path") != f"/root/{task_name}":
            raise ProbeError("active child binding is not exact")
        if not isinstance(runtime, dict) or type(runtime.get("recovery_count")) is not int:
            raise ProbeError("active recovery metadata is invalid")
        if runtime["recovery_count"] < 1:
            return None
        if runtime.get("context_lost") is not False:
            raise ProbeError("active authority is already context-lost")
        if not isinstance(runtime.get("first_git_attested_at"), str):
            raise ProbeError("first Git attestation is unavailable")
        snapshot = collect_git_snapshot(str(root))
        expected_root = capsule["root"]
        if (
            snapshot["root"] != str(root)
            or snapshot["branch"] != expected_root["branch"]
            or snapshot["head"] != expected_root["base_commit"]
            or snapshot["index_changed"]
            or snapshot["git_status_short"]
            or snapshot["changed_paths"]
        ):
            raise ProbeError("probe root drifted before the controlled injection")
        if target.exists() or target.is_symlink():
            raise ProbeError("controlled drift target is not absent")
        before_state_sha256 = sha256_bytes(state_path.read_bytes())
        injected_at = dt.datetime.now(dt.timezone.utc).isoformat()
        write_exclusive(target, TARGET_CONTENT)
        after = collect_git_snapshot(str(root))
        expected_change = {
            "path": TARGET_NAME,
            "kind": "file",
            "sha256": sha256_bytes(TARGET_CONTENT),
        }
        if (
            after["root"] != snapshot["root"]
            or after["branch"] != snapshot["branch"]
            or after["head"] != snapshot["head"]
            or after["index_changed"]
            or after["changed_paths"] != [expected_change]
        ):
            raise ProbeError("controlled drift postcondition is not exact")
        return {
            "schema": 1,
            "injection_kind": "host_foreign_postcompact_scope_drift",
            "assignment_id": capsule["assignment_id"],
            "handoff_id": capsule["handoff_id"],
            "runtime_session_id": capsule["runtime_session_id"],
            "child_thread_id": binding["child_thread_id"],
            "canonical_agent_path": binding["canonical_agent_path"],
            "root": str(root),
            "branch": snapshot["branch"],
            "head": snapshot["head"],
            "recovery_count": runtime["recovery_count"],
            "first_git_attested_at": runtime["first_git_attested_at"],
            "injected_at": injected_at,
            "state_lock_held_during_injection": True,
            "active_envelope_sha256_before_injection": before_state_sha256,
            "target": str(target),
            "target_relative_path": TARGET_NAME,
            "target_sha256": expected_change["sha256"],
            "target_bytes": len(TARGET_CONTENT),
            "before_snapshot": snapshot,
            "after_snapshot": after,
            "child_mutation_authorized": False,
            "injected_bytes_attributed_to_child": False,
        }


def wait_and_inject(
    store: StateStore,
    root: Path,
    task_name: str,
    *,
    timeout_seconds: float,
) -> dict:
    if timeout_seconds <= 0 or timeout_seconds > 900:
        raise ProbeError("timeout must be in (0, 900]")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = inject_if_recovered(store, root, task_name)
        if result is not None:
            return result
        time.sleep(0.01)
    raise ProbeError("no exact recovered active assignment appeared before timeout")


def write_report(path: Path, value: dict) -> None:
    write_exclusive(path, canonical_json(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    arguments = parser.parse_args()
    if arguments.output.exists() or arguments.output.is_symlink():
        print("post-compact scope-drift injection denied: output already exists", file=sys.stderr)
        return 2
    try:
        result = wait_and_inject(
            StateStore(arguments.state_directory),
            arguments.root,
            arguments.task_name,
            timeout_seconds=arguments.timeout_seconds,
        )
        write_report(arguments.output, result)
    except (OSError, ProbeError) as error:
        print(f"post-compact scope-drift injection denied: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
