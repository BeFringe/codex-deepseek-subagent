#!/usr/bin/env python3

"""Arm or disarm short-lived live Hook schema observation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
HOOKS = SOURCE_ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

from compatibility_state import CorruptState, StateError, StateStore  # noqa: E402
from hook_schema_observation_arm import (  # noqa: E402
    ALLOWED_EVENTS,
    build_arm,
    validate_arm,
)


def exact_git_root(value: Path) -> Path:
    requested = value.resolve(strict=True)
    result = subprocess.run(
        ["git", "-C", str(requested), "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or Path(result.stdout.strip()).resolve() != requested:
        raise StateError("schema observation root must be the exact Git top level")
    return requested


def arm(store: StateStore, root: Path, events: list[str], ttl_seconds: int) -> dict:
    value = build_arm(
        exact_git_root(root),
        events,
        now=dt.datetime.now(dt.timezone.utc),
        ttl_seconds=ttl_seconds,
    )
    target = store.path("hook_schema_observation_arm", "current")
    with store.locked():
        if target.exists():
            prior = validate_arm(store._read(target))
            expires = dt.datetime.fromisoformat(prior["expires_at"])
            if expires > dt.datetime.now(dt.timezone.utc):
                raise StateError("a schema observation arm is already active")
            history = store.path("hook_schema_observation_arm_history", prior["arm_id"])
            history.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.replace(target, history)
        store._publish(target, value)
    return value


def disarm(store: StateStore, arm_id: str) -> dict:
    target = store.path("hook_schema_observation_arm", "current")
    with store.locked():
        if not target.exists():
            raise StateError("no schema observation arm is active")
        value = validate_arm(store._read(target))
        if value["arm_id"] != arm_id:
            raise StateError("schema observation arm id does not match")
        history = store.path("hook_schema_observation_arm_history", arm_id)
        history.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if history.exists():
            raise StateError("schema observation arm history already exists")
        os.replace(target, history)
    return value


def report(value: dict, status: str) -> dict:
    return {
        "schema": 1,
        "status": status,
        "arm_id": value["arm_id"],
        "root": value["root"],
        "enabled_events": value["enabled_events"],
        "created_at": value["created_at"],
        "expires_at": value["expires_at"],
        "arm_sha256": value["arm_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-directory", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="action", required=True)
    arm_parser = subparsers.add_parser("arm")
    arm_parser.add_argument("--root", type=Path, required=True)
    arm_parser.add_argument("--event", action="append", choices=sorted(ALLOWED_EVENTS), required=True)
    arm_parser.add_argument("--ttl-seconds", type=int, default=300)
    disarm_parser = subparsers.add_parser("disarm")
    disarm_parser.add_argument("--arm-id", required=True)
    arguments = parser.parse_args()
    store = StateStore(arguments.state_directory)
    try:
        if arguments.action == "arm":
            value = arm(store, arguments.root, arguments.event, arguments.ttl_seconds)
            output = report(value, "armed")
        else:
            value = disarm(store, arguments.arm_id)
            output = report(value, "disarmed_to_history")
    except (OSError, CorruptState, StateError, ValueError) as error:
        print(f"Hook schema observation arm failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
