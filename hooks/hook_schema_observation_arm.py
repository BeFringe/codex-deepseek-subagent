#!/usr/bin/env python3

"""Short-lived, tamper-evident opt-in for live Hook schema observations."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import re
from typing import Collection, Mapping
import uuid

from compatibility_state import CorruptState, StateStore, canonical_json, sha256_bytes


SCHEMA = 1
ARM_FIELDS = {
    "schema",
    "arm_id",
    "root",
    "enabled_events",
    "created_at",
    "expires_at",
    "arm_sha256",
}
ALLOWED_EVENTS = {"PreToolUse", "SubagentStart"}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise CorruptState(f"schema observation arm {field} must be a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as error:
        raise CorruptState(f"schema observation arm {field} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CorruptState(f"schema observation arm {field} must include UTC offset")
    return parsed


def arm_sha256(arm: Mapping[str, object]) -> str:
    unsigned = dict(arm)
    unsigned.pop("arm_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def validate_arm(arm: object) -> dict:
    if not isinstance(arm, dict) or set(arm) != ARM_FIELDS:
        raise CorruptState("schema observation arm fields are not exact")
    if arm["schema"] != SCHEMA:
        raise CorruptState("schema observation arm version is invalid")
    try:
        uuid.UUID(str(arm["arm_id"]))
    except (ValueError, TypeError) as error:
        raise CorruptState("schema observation arm id is invalid") from error
    root = arm["root"]
    if not isinstance(root, str) or not root or not Path(root).is_absolute():
        raise CorruptState("schema observation arm root is invalid")
    if str(Path(root).resolve()) != root:
        raise CorruptState("schema observation arm root is not canonical")
    events = arm["enabled_events"]
    if not isinstance(events, list) or events != sorted(set(events)) or not events:
        raise CorruptState("schema observation arm events are not unique and sorted")
    if not set(events) <= ALLOWED_EVENTS:
        raise CorruptState("schema observation arm contains an unsupported event")
    created_at = _timestamp(arm["created_at"], "created_at")
    expires_at = _timestamp(arm["expires_at"], "expires_at")
    if expires_at <= created_at:
        raise CorruptState("schema observation arm does not have a positive lifetime")
    digest = arm["arm_sha256"]
    if not isinstance(digest, str) or not HEX_SHA256.fullmatch(digest):
        raise CorruptState("schema observation arm hash is invalid")
    if digest != arm_sha256(arm):
        raise CorruptState("schema observation arm hash does not match")
    return arm


def build_arm(
    root: str | Path,
    events: Collection[str],
    *,
    now: dt.datetime,
    ttl_seconds: int,
) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise CorruptState("schema observation arm creation time needs a UTC offset")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise CorruptState("schema observation arm TTL must be an integer")
    if ttl_seconds < 1 or ttl_seconds > 900:
        raise CorruptState("schema observation arm TTL must be between 1 and 900 seconds")
    canonical_root = str(Path(root).resolve(strict=True))
    arm = {
        "schema": SCHEMA,
        "arm_id": str(uuid.uuid4()),
        "root": canonical_root,
        "enabled_events": sorted(set(events)),
        "created_at": now.isoformat(),
        "expires_at": (now + dt.timedelta(seconds=ttl_seconds)).isoformat(),
    }
    arm["arm_sha256"] = arm_sha256(arm)
    return validate_arm(arm)


def observation_root_for_event(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    now: dt.datetime | None = None,
) -> Path | None:
    target = store.path("hook_schema_observation_arm", "current")
    if not target.exists():
        return None
    with store.locked():
        arm = validate_arm(store._read(target))
    observed_at = now or dt.datetime.now(dt.timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise CorruptState("schema observation time needs a UTC offset")
    if observed_at >= _timestamp(arm["expires_at"], "expires_at"):
        return None
    if hook_input.get("hook_event_name") not in arm["enabled_events"]:
        return None
    return Path(arm["root"])
