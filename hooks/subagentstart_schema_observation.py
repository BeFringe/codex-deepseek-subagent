#!/usr/bin/env python3

"""Value-free schema receipts for a scoped live SubagentStart probe."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Mapping
import uuid

from compatibility_state import CorruptState, StateStore, canonical_json, sha256_bytes
from pretool_schema_observation import _json_type, observes_root
from runtime_guard import child_identity_from_hook


SCHEMA = 1
ACTOR_FIELDS = {
    "runtime_session_id",
    "thread_id",
    "agent_type",
    "canonical_agent_path",
}
SHAPE_FIELDS = {"key", "value_type"}
FINGERPRINT_FIELDS = {"key", "length", "sha256"}
SELECTED_STRING_KEYS = {"message", "prompt"}
RECEIPT_FIELDS = {
    "schema",
    "observation_id",
    "observed_at",
    "hook_event_name",
    "actor",
    "cwd",
    "hook_input_shape",
    "selected_string_fingerprints",
    "raw_payload_stored",
    "receipt_sha256",
}


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CorruptState(f"{field} must be a non-empty string")
    return value


def receipt_sha256(receipt: Mapping[str, object]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def validate_receipt(receipt: object) -> dict:
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise CorruptState("SubagentStart schema receipt fields are not exact")
    if receipt["schema"] != SCHEMA:
        raise CorruptState("SubagentStart schema receipt version is invalid")
    try:
        uuid.UUID(_nonempty(receipt["observation_id"], "observation_id"))
    except ValueError as error:
        raise CorruptState("SubagentStart observation_id must be a UUID") from error
    try:
        observed_at = dt.datetime.fromisoformat(
            _nonempty(receipt["observed_at"], "observed_at")
        )
    except ValueError as error:
        raise CorruptState("SubagentStart observed_at is invalid") from error
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise CorruptState("SubagentStart observed_at must include a UTC offset")
    if receipt["hook_event_name"] != "SubagentStart":
        raise CorruptState("schema receipt is not a SubagentStart event")
    actor = receipt["actor"]
    if not isinstance(actor, dict) or set(actor) != ACTOR_FIELDS:
        raise CorruptState("SubagentStart actor fields are not exact")
    for field in ACTOR_FIELDS:
        _nonempty(actor[field], f"actor.{field}")
    if not actor["canonical_agent_path"].startswith("/"):
        raise CorruptState("SubagentStart actor AgentPath must be absolute")
    _nonempty(receipt["cwd"], "cwd")
    shape = receipt["hook_input_shape"]
    if not isinstance(shape, list):
        raise CorruptState("SubagentStart hook_input_shape must be a list")
    shape_keys = []
    for item in shape:
        if not isinstance(item, dict) or set(item) != SHAPE_FIELDS:
            raise CorruptState("SubagentStart input-shape fields are not exact")
        shape_keys.append(_nonempty(item["key"], "hook_input_shape.key"))
        _nonempty(item["value_type"], "hook_input_shape.value_type")
    if shape_keys != sorted(set(shape_keys)):
        raise CorruptState("SubagentStart input keys are not unique and sorted")
    fingerprints = receipt["selected_string_fingerprints"]
    if not isinstance(fingerprints, list):
        raise CorruptState("SubagentStart string fingerprints must be a list")
    fingerprint_keys = []
    for fingerprint in fingerprints:
        if not isinstance(fingerprint, dict) or set(fingerprint) != FINGERPRINT_FIELDS:
            raise CorruptState("SubagentStart string fingerprint fields are not exact")
        key = _nonempty(fingerprint["key"], "selected fingerprint key")
        fingerprint_keys.append(key)
        if key not in SELECTED_STRING_KEYS:
            raise CorruptState("SubagentStart fingerprint key is not selected")
        length = fingerprint["length"]
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise CorruptState("SubagentStart fingerprint length is invalid")
        digest = fingerprint["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise CorruptState("SubagentStart fingerprint hash is invalid")
    if fingerprint_keys != sorted(set(fingerprint_keys)):
        raise CorruptState("SubagentStart fingerprint keys are not unique and sorted")
    if receipt["raw_payload_stored"] is not False:
        raise CorruptState("SubagentStart schema receipt must not store the raw payload")
    if receipt["receipt_sha256"] != receipt_sha256(receipt):
        raise CorruptState("SubagentStart schema receipt hash does not match")
    return receipt


def observation_from_hook(hook_input: Mapping[str, object]) -> dict:
    if hook_input.get("hook_event_name") != "SubagentStart":
        raise CorruptState("SubagentStart observer only accepts SubagentStart")
    identity = child_identity_from_hook(hook_input)
    shape = [
        {"key": key, "value_type": _json_type(hook_input[key])}
        for key in sorted(hook_input)
    ]
    fingerprints = []
    for key in sorted(SELECTED_STRING_KEYS):
        value = hook_input.get(key)
        if isinstance(value, str):
            fingerprints.append(
                {
                    "key": key,
                    "length": len(value),
                    "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                }
            )
    receipt = {
        "schema": SCHEMA,
        "observation_id": str(uuid.uuid4()),
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hook_event_name": "SubagentStart",
        "actor": {
            "runtime_session_id": identity["runtime_session_id"],
            "thread_id": identity["child_thread_id"],
            "agent_type": identity["agent_type"],
            "canonical_agent_path": identity["canonical_agent_path"],
        },
        "cwd": str(Path(_nonempty(hook_input.get("cwd"), "cwd")).resolve()),
        "hook_input_shape": shape,
        "selected_string_fingerprints": fingerprints,
        "raw_payload_stored": False,
    }
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    return validate_receipt(receipt)


def record_from_hook(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    observation_root: str | Path,
) -> Path | None:
    if hook_input.get("hook_event_name") != "SubagentStart":
        return None
    if not observes_root(hook_input, observation_root):
        return None
    receipt = observation_from_hook(hook_input)
    with store.locked():
        target = store.path(
            "subagentstart_schema_observation",
            receipt["observation_id"],
        )
        store._publish(target, receipt)
    return target


def load_receipts(state_directory: str | Path) -> list[dict]:
    directory = Path(state_directory).resolve() / "subagentstart_schema_observation"
    if not directory.exists():
        return []
    receipts = []
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CorruptState(f"cannot read SubagentStart schema receipt {path.name}") from error
        receipts.append(validate_receipt(value))
    return receipts
