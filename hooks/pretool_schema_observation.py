#!/usr/bin/env python3

"""Value-free schema receipts for a narrowly scoped live PreToolUse probe."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping
import uuid

from compatibility_state import CorruptState, StateStore, canonical_json, sha256_bytes
from writer_lease_guard import actor_identity_from_hook


CURRENT_SCHEMA = 2
OMITTED_PAYLOAD_FIELDS = [
    "agent_transcript_path",
    "last_assistant_message",
    "tool_input_values",
    "tool_response",
    "transcript_path",
]
ACTOR_FIELDS = {
    "runtime_session_id",
    "thread_id",
    "agent_type",
    "canonical_agent_path",
}
SHAPE_FIELDS = {"key", "value_type"}
RECEIPT_FIELDS_V1 = {
    "schema",
    "observation_id",
    "observed_at",
    "hook_event_name",
    "actor",
    "cwd",
    "tool_name",
    "tool_use_id",
    "tool_input_type",
    "tool_input_shape",
    "raw_payload_stored",
    "omitted_payload_fields",
    "receipt_sha256",
}
RECEIPT_FIELDS_V2 = RECEIPT_FIELDS_V1 | {"selected_string_fingerprints"}
FINGERPRINT_FIELDS = {
    "key",
    "length",
    "sha256",
    "authority_begin_count",
    "authority_end_count",
}
FINGERPRINTED_TOOL_NAMES = {"spawn_agent", "Agent", "collaborationspawn_agent"}
JSON_TYPES = {"null", "boolean", "integer", "number", "string", "array", "object"}


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CorruptState(f"{field} must be a non-empty string")
    return value


def _timestamp(value: object) -> None:
    if not isinstance(value, str):
        raise CorruptState("observed_at must be a timestamp string")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as error:
        raise CorruptState("observed_at is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CorruptState("observed_at must include a UTC offset")


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise CorruptState("Hook input contains a non-JSON tool_input value")


def receipt_sha256(receipt: Mapping[str, object]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def validate_receipt(receipt: object) -> dict:
    if not isinstance(receipt, dict):
        raise CorruptState("PreToolUse schema receipt fields are not exact")
    schema = receipt.get("schema")
    expected_fields = {1: RECEIPT_FIELDS_V1, 2: RECEIPT_FIELDS_V2}.get(schema)
    if expected_fields is None or set(receipt) != expected_fields:
        raise CorruptState("PreToolUse schema receipt version is invalid")
    try:
        uuid.UUID(_nonempty(receipt["observation_id"], "observation_id"))
    except ValueError as error:
        raise CorruptState("observation_id must be a UUID") from error
    _timestamp(receipt["observed_at"])
    if receipt["hook_event_name"] != "PreToolUse":
        raise CorruptState("schema receipt is not a PreToolUse event")
    actor = receipt["actor"]
    if not isinstance(actor, dict) or set(actor) != ACTOR_FIELDS:
        raise CorruptState("schema receipt actor fields are not exact")
    for field in ACTOR_FIELDS:
        _nonempty(actor[field], f"actor.{field}")
    if not actor["canonical_agent_path"].startswith("/"):
        raise CorruptState("schema receipt actor AgentPath must be absolute")
    _nonempty(receipt["cwd"], "cwd")
    _nonempty(receipt["tool_name"], "tool_name")
    _nonempty(receipt["tool_use_id"], "tool_use_id")
    if receipt["tool_input_type"] not in JSON_TYPES:
        raise CorruptState("schema receipt tool_input_type is invalid")
    shape = receipt["tool_input_shape"]
    if not isinstance(shape, list):
        raise CorruptState("schema receipt tool_input_shape must be a list")
    keys = []
    for item in shape:
        if not isinstance(item, dict) or set(item) != SHAPE_FIELDS:
            raise CorruptState("schema receipt input-shape fields are not exact")
        keys.append(_nonempty(item["key"], "tool_input_shape.key"))
        if item["value_type"] not in JSON_TYPES:
            raise CorruptState("schema receipt input value type is invalid")
    if keys != sorted(set(keys)):
        raise CorruptState("schema receipt input keys are not unique and sorted")
    if receipt["tool_input_type"] != "object" and shape:
        raise CorruptState("non-object tool input cannot have a field shape")
    if schema == 2:
        fingerprints = receipt["selected_string_fingerprints"]
        if not isinstance(fingerprints, list):
            raise CorruptState("selected string fingerprints must be a list")
        fingerprint_keys = []
        for fingerprint in fingerprints:
            if not isinstance(fingerprint, dict) or set(fingerprint) != FINGERPRINT_FIELDS:
                raise CorruptState("selected string fingerprint fields are not exact")
            key = _nonempty(fingerprint["key"], "selected fingerprint key")
            fingerprint_keys.append(key)
            if key != "message":
                raise CorruptState("only the spawn message may be fingerprinted")
            length = fingerprint["length"]
            if isinstance(length, bool) or not isinstance(length, int) or length < 0:
                raise CorruptState("selected string fingerprint length is invalid")
            digest = fingerprint["sha256"]
            if not isinstance(digest, str) or len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise CorruptState("selected string fingerprint hash is invalid")
            for count_field in ("authority_begin_count", "authority_end_count"):
                count = fingerprint[count_field]
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise CorruptState("selected string marker count is invalid")
        if fingerprint_keys != sorted(set(fingerprint_keys)):
            raise CorruptState("selected string fingerprint keys are not unique and sorted")
        if fingerprints and receipt["tool_name"] not in FINGERPRINTED_TOOL_NAMES:
            raise CorruptState("non-spawn tool cannot carry a message fingerprint")
    if receipt["raw_payload_stored"] is not False:
        raise CorruptState("schema receipt must not store the raw payload")
    if receipt["omitted_payload_fields"] != OMITTED_PAYLOAD_FIELDS:
        raise CorruptState("schema receipt omitted-field catalog is invalid")
    if receipt["receipt_sha256"] != receipt_sha256(receipt):
        raise CorruptState("PreToolUse schema receipt hash does not match")
    return receipt


def _canonical_path(value: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(value)))


def observes_root(hook_input: Mapping[str, object], root: str | Path) -> bool:
    cwd = hook_input.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return False
    return _canonical_path(cwd) == _canonical_path(root)


def observation_from_hook(hook_input: Mapping[str, object]) -> dict:
    if hook_input.get("hook_event_name") != "PreToolUse":
        raise CorruptState("schema observer only accepts PreToolUse")
    tool_name = _nonempty(hook_input.get("tool_name"), "tool_name")
    tool_use_id = _nonempty(hook_input.get("tool_use_id"), "tool_use_id")
    cwd = _nonempty(hook_input.get("cwd"), "cwd")
    tool_input = hook_input.get("tool_input")
    input_type = _json_type(tool_input)
    shape = []
    if isinstance(tool_input, dict):
        for key in sorted(tool_input):
            if not isinstance(key, str) or not key:
                raise CorruptState("tool_input keys must be non-empty strings")
            shape.append({"key": key, "value_type": _json_type(tool_input[key])})
    fingerprints = []
    if tool_name in FINGERPRINTED_TOOL_NAMES and isinstance(tool_input, dict):
        message = tool_input.get("message")
        if isinstance(message, str):
            fingerprints.append(
                {
                    "key": "message",
                    "length": len(message),
                    "sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
                    "authority_begin_count": message.count(
                        "BEGIN CODEX WORKER AUTHORITY"
                    ),
                    "authority_end_count": message.count(
                        "END CODEX WORKER AUTHORITY"
                    ),
                }
            )
    receipt = {
        "schema": CURRENT_SCHEMA,
        "observation_id": str(uuid.uuid4()),
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hook_event_name": "PreToolUse",
        "actor": actor_identity_from_hook(hook_input),
        "cwd": _canonical_path(cwd),
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "tool_input_type": input_type,
        "tool_input_shape": shape,
        "selected_string_fingerprints": fingerprints,
        "raw_payload_stored": False,
        "omitted_payload_fields": OMITTED_PAYLOAD_FIELDS,
    }
    receipt["receipt_sha256"] = receipt_sha256(receipt)
    return validate_receipt(receipt)


def record_from_hook(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    observation_root: str | Path,
) -> Path | None:
    if hook_input.get("hook_event_name") != "PreToolUse":
        return None
    if not observes_root(hook_input, observation_root):
        return None
    receipt = observation_from_hook(hook_input)
    with store.locked():
        target = store.path(
            "pretool_schema_observation",
            receipt["observation_id"],
        )
        store._publish(target, receipt)
    return target


def load_receipts(state_directory: str | Path) -> list[dict]:
    directory = Path(state_directory).resolve() / "pretool_schema_observation"
    if not directory.exists():
        return []
    receipts = []
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CorruptState(f"cannot read schema receipt {path.name}") from error
        receipts.append(validate_receipt(value))
    return receipts
