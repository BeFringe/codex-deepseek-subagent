#!/usr/bin/env python3

"""Privacy-minimized, hash-linked observations of qualified Hook events."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Collection, Mapping
import uuid

from compatibility_state import (
    AuthorityViolation,
    CorruptState,
    StateError,
    StateStore,
    canonical_json,
    sha256_bytes,
    validate_writer_abort,
)
from assignment_transport import SPAWN_TOOL_NAMES
from runtime_guard import child_identity_from_hook, child_identity_from_stop
from writer_lease_guard import actor_identity_from_hook


CHAIN_SCHEMA = 1
OMITTED_PAYLOAD_FIELDS = [
    "agent_transcript_path",
    "last_assistant_message",
    "tool_input",
    "tool_response",
    "transcript_path",
]
ACTOR_FIELDS = {
    "runtime_session_id",
    "thread_id",
    "agent_type",
    "canonical_agent_path",
}
OBSERVATION_FIELDS = {
    "hook_event_name",
    "event_stage",
    "scope",
    "turn_id",
    "actor",
    "tool_name",
    "tool_use_id",
    "trigger",
    "raw_payload_stored",
    "omitted_payload_fields",
}
RECEIPT_FIELDS = OBSERVATION_FIELDS | {
    "schema",
    "receipt_id",
    "sequence",
    "previous_receipt_sha256",
    "observed_at",
    "receipt_sha256",
}
CHAIN_FIELDS = {
    "schema",
    "event_count",
    "head_receipt_sha256",
    "events",
    "chain_sha256",
}
EVENT_NAMES = {
    "PreToolUse",
    "PostToolUse",
    "SubagentStart",
    "PreCompact",
    "SubagentStop",
}
SCOPES = {"target_spawn", "target_child", "writer"}
EVENT_STAGES = {"observed", "authorized", "denied", "callback_observed"}


class UnverifiableHookIdentity(StateError):
    """The event cannot be joined to SessionMeta and is not receipt authority."""


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CorruptState(f"{field} must be a non-empty string")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise CorruptState(f"{field} must be null or a non-empty string")
    return value


def _timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise CorruptState(f"{field} must be a timestamp string")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as error:
        raise CorruptState(f"{field} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CorruptState(f"{field} must include a UTC offset")
    return parsed


def receipt_sha256(receipt: Mapping[str, object]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def chain_sha256(chain: Mapping[str, object]) -> str:
    unsigned = dict(chain)
    unsigned.pop("chain_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def _validate_actor(actor: object) -> dict[str, str]:
    if not isinstance(actor, dict) or set(actor) != ACTOR_FIELDS:
        raise CorruptState("Hook event actor fields are not exact")
    for field in ACTOR_FIELDS:
        _nonempty(actor[field], f"actor.{field}")
    if not actor["canonical_agent_path"].startswith("/"):
        raise CorruptState("actor canonical AgentPath must be absolute")
    return actor


def _validate_observation(observation: object) -> dict:
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_FIELDS:
        raise CorruptState("Hook event observation fields are not exact")
    if observation["hook_event_name"] not in EVENT_NAMES:
        raise CorruptState("Hook event name is not qualified")
    if observation["event_stage"] not in EVENT_STAGES:
        raise CorruptState("Hook event stage is invalid")
    if observation["scope"] not in SCOPES:
        raise CorruptState("Hook event scope is invalid")
    _optional_string(observation["turn_id"], "turn_id")
    _validate_actor(observation["actor"])
    tool_name = _optional_string(observation["tool_name"], "tool_name")
    tool_use_id = _optional_string(observation["tool_use_id"], "tool_use_id")
    if (tool_name is None) != (tool_use_id is None):
        raise CorruptState("tool name and tool-use id must be present together")
    trigger = _optional_string(observation["trigger"], "trigger")
    if observation["hook_event_name"] == "PreCompact":
        if trigger not in {"manual", "auto"}:
            raise CorruptState("PreCompact trigger is invalid")
    elif trigger is not None:
        raise CorruptState("non-compact Hook event cannot record a trigger")
    if observation["raw_payload_stored"] is not False:
        raise CorruptState("Hook event receipt must not store the raw payload")
    if observation["omitted_payload_fields"] != OMITTED_PAYLOAD_FIELDS:
        raise CorruptState("Hook event omitted-field catalog is invalid")
    if observation["scope"] == "writer":
        if tool_name != "apply_patch":
            raise CorruptState("writer event must be an apply_patch event")
        expected_stage = {
            "PreToolUse": {"authorized", "denied"},
            "PostToolUse": {"callback_observed"},
        }.get(observation["hook_event_name"])
        if expected_stage is None or observation["event_stage"] not in expected_stage:
            raise CorruptState("writer event stage does not match its Hook event")
    elif observation["event_stage"] != "observed":
        raise CorruptState("non-writer events must use the observed stage")
    return observation


def _validate_receipt(receipt: object, *, sequence: int, previous: str | None) -> dict:
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise CorruptState("Hook event receipt fields are not exact")
    if receipt["schema"] != CHAIN_SCHEMA:
        raise CorruptState("Hook event receipt schema is invalid")
    try:
        uuid.UUID(_nonempty(receipt["receipt_id"], "receipt_id"))
    except ValueError as error:
        raise CorruptState("receipt_id must be a UUID") from error
    if receipt["sequence"] != sequence:
        raise CorruptState("Hook event sequence is not contiguous")
    if receipt["previous_receipt_sha256"] != previous:
        raise CorruptState("Hook event previous-receipt link does not match")
    _timestamp(receipt["observed_at"], "observed_at")
    _validate_observation({field: receipt[field] for field in OBSERVATION_FIELDS})
    if receipt["receipt_sha256"] != receipt_sha256(receipt):
        raise CorruptState("Hook event receipt hash does not match")
    return receipt


def _writer_key(receipt: Mapping[str, object]) -> tuple[str, str, str]:
    actor = receipt["actor"]
    assert isinstance(actor, dict)
    return (
        str(actor["runtime_session_id"]),
        str(actor["thread_id"]),
        str(receipt["tool_use_id"]),
    )


def _validate_writer_order(events: list[dict]) -> None:
    pre_events: dict[tuple[str, str, str], dict] = {}
    post_events: dict[tuple[str, str, str], dict] = {}
    for event in events:
        if event["scope"] != "writer":
            continue
        key = _writer_key(event)
        if event["hook_event_name"] == "PreToolUse":
            if key in pre_events or key in post_events:
                raise CorruptState("writer PreToolUse tool-use id is duplicated")
            pre_events[key] = event
            continue
        if key not in pre_events:
            raise CorruptState("writer PostToolUse has no preceding PreToolUse")
        if key in post_events:
            raise CorruptState("writer PostToolUse tool-use id is duplicated")
        if pre_events[key]["event_stage"] != "authorized":
            raise CorruptState("denied writer event cannot receive PostToolUse")
        post_events[key] = event


def validate_chain(chain: object) -> dict:
    if not isinstance(chain, dict) or set(chain) != CHAIN_FIELDS:
        raise CorruptState("Hook event chain fields are not exact")
    if chain["schema"] != CHAIN_SCHEMA:
        raise CorruptState("Hook event chain schema is invalid")
    events = chain["events"]
    if not isinstance(events, list) or not events:
        raise CorruptState("Hook event chain must contain events")
    if chain["event_count"] != len(events):
        raise CorruptState("Hook event chain count does not match")
    previous = None
    receipt_ids = set()
    for sequence, event in enumerate(events, start=1):
        receipt = _validate_receipt(event, sequence=sequence, previous=previous)
        if receipt["receipt_id"] in receipt_ids:
            raise CorruptState("Hook event receipt id is duplicated")
        receipt_ids.add(receipt["receipt_id"])
        previous = receipt["receipt_sha256"]
    _validate_writer_order(events)
    if chain["head_receipt_sha256"] != previous:
        raise CorruptState("Hook event chain head does not match")
    if chain["chain_sha256"] != chain_sha256(chain):
        raise CorruptState("Hook event chain hash does not match")
    return chain


def _append(store: StateStore, observation: Mapping[str, object]) -> Path:
    _validate_observation(dict(observation))
    target = store.path("hook_event_chain", "current")
    now = dt.datetime.now(dt.timezone.utc)
    with store.locked():
        events: list[dict] = []
        previous = None
        if target.exists():
            try:
                prior = validate_chain(store._read(target))
            except CorruptState:
                store._quarantine(target)
                raise
            events = [dict(event) for event in prior["events"]]
            previous = prior["head_receipt_sha256"]
        receipt = {
            "schema": CHAIN_SCHEMA,
            "receipt_id": str(uuid.uuid4()),
            "sequence": len(events) + 1,
            "previous_receipt_sha256": previous,
            "observed_at": now.isoformat(),
            **dict(observation),
        }
        receipt["receipt_sha256"] = receipt_sha256(receipt)
        events.append(receipt)
        chain = {
            "schema": CHAIN_SCHEMA,
            "event_count": len(events),
            "head_receipt_sha256": receipt["receipt_sha256"],
            "events": events,
        }
        chain["chain_sha256"] = chain_sha256(chain)
        validate_chain(chain)
        store._publish(target, chain, replace=target.exists())
    return target


def _actor_from_child(identity: Mapping[str, str]) -> dict[str, str]:
    return {
        "runtime_session_id": identity["runtime_session_id"],
        "thread_id": identity["child_thread_id"],
        "agent_type": identity["agent_type"],
        "canonical_agent_path": identity["canonical_agent_path"],
    }


def is_target_spawn(
    hook_input: Mapping[str, object], *, plaintext_agent_types: Collection[str]
) -> bool:
    tool_input = hook_input.get("tool_input")
    return (
        hook_input.get("hook_event_name") == "PreToolUse"
        and hook_input.get("tool_name") in SPAWN_TOOL_NAMES
        and isinstance(tool_input, dict)
        and tool_input.get("agent_type") in plaintext_agent_types
    )


def observation_from_hook(
    hook_input: Mapping[str, object],
    *,
    plaintext_agent_types: Collection[str],
    writer_stage: str | None = None,
) -> dict | None:
    event = hook_input.get("hook_event_name")
    child_is_target = hook_input.get("agent_type") in plaintext_agent_types
    scope = None
    actor = None
    stage = "observed"
    try:
        if event in {"PreToolUse", "PostToolUse"} and hook_input.get("tool_name") == "apply_patch" and not child_is_target:
            if writer_stage is None:
                return None
            scope = "writer"
            stage = writer_stage
            actor = actor_identity_from_hook(hook_input)
        elif is_target_spawn(hook_input, plaintext_agent_types=plaintext_agent_types):
            scope = "target_spawn"
            actor = actor_identity_from_hook(hook_input)
        elif child_is_target and event in {
            "SubagentStart",
            "PreToolUse",
            "PostToolUse",
            "PreCompact",
        }:
            scope = "target_child"
            actor = _actor_from_child(child_identity_from_hook(hook_input))
        elif child_is_target and event == "SubagentStop":
            scope = "target_child"
            actor = _actor_from_child(child_identity_from_stop(hook_input))
        else:
            return None
    except (OSError, StateError) as error:
        raise UnverifiableHookIdentity(str(error)) from error
    turn_id = hook_input.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        turn_id = None
    tool_name = hook_input.get("tool_name")
    tool_use_id = hook_input.get("tool_use_id")
    if not isinstance(tool_name, str) or not tool_name:
        tool_name = None
        tool_use_id = None
    elif not isinstance(tool_use_id, str) or not tool_use_id:
        raise StateError("qualified tool Hook event has no tool_use_id")
    trigger = hook_input.get("trigger") if event == "PreCompact" else None
    observation = {
        "hook_event_name": event,
        "event_stage": stage,
        "scope": scope,
        "turn_id": turn_id,
        "actor": actor,
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "trigger": trigger,
        "raw_payload_stored": False,
        "omitted_payload_fields": OMITTED_PAYLOAD_FIELDS,
    }
    _validate_observation(observation)
    return observation


def record_from_hook(
    store: StateStore,
    hook_input: Mapping[str, object],
    *,
    plaintext_agent_types: Collection[str],
    writer_stage: str | None = None,
) -> Path | None:
    observation = observation_from_hook(
        hook_input,
        plaintext_agent_types=plaintext_agent_types,
        writer_stage=writer_stage,
    )
    return None if observation is None else _append(store, observation)


def load_chain(state_directory: Path | str) -> dict:
    path = Path(state_directory).resolve() / "hook_event_chain" / "current.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CorruptState("cannot read the Hook event chain") from error
    return validate_chain(value)


def load_writer_aborts(state_directory: Path | str) -> list[dict]:
    directory = Path(state_directory).resolve() / "writer_abort"
    receipts = []
    if not directory.exists():
        return receipts
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CorruptState("cannot read a writer abort receipt") from error
        receipts.append(validate_writer_abort(value))
    return receipts


def _writer_abort_key(receipt: Mapping[str, object]) -> tuple[str, str, str]:
    actor = receipt["actor"]
    assert isinstance(actor, dict)
    return (
        str(actor["runtime_session_id"]),
        str(actor["thread_id"]),
        str(receipt["tool_use_id"]),
    )


def audit_apply_patch_callbacks(
    chain: Mapping[str, object],
    *,
    require_complete: bool,
    writer_aborts: Collection[Mapping[str, object]] = (),
) -> dict:
    value = validate_chain(dict(chain))
    pre_events: dict[tuple[str, str, str], dict] = {}
    post_events: dict[tuple[str, str, str], dict] = {}
    abort_events: dict[tuple[str, str, str], dict] = {}
    denied = []
    for event in value["events"]:
        if event["scope"] != "writer":
            continue
        key = _writer_key(event)
        if event["hook_event_name"] == "PreToolUse":
            if event["event_stage"] == "denied":
                denied.append(event["tool_use_id"])
            else:
                pre_events[key] = event
        else:
            post_events[key] = event
    for candidate in writer_aborts:
        abort = validate_writer_abort(dict(candidate))
        key = _writer_abort_key(abort)
        if key in abort_events:
            raise CorruptState("writer abort actor/tool-use identity is duplicated")
        abort_events[key] = abort
    callbacks = []
    pending = []
    matched_abort_ids = []
    for key, event in sorted(pre_events.items()):
        post = post_events.get(key)
        abort = abort_events.get(key)
        if post is not None and abort is not None:
            raise CorruptState("writer event has both PostToolUse and abort receipts")
        if post is not None:
            status = "callback_observed"
        elif abort is not None:
            status = "aborted_unchanged"
            matched_abort_ids.append(abort["claim_id"])
        else:
            status = "callback_pending"
            pending.append(event["tool_use_id"])
        callbacks.append(
            {
                "runtime_session_id": key[0],
                "thread_id": key[1],
                "tool_use_id": key[2],
                "pre_sequence": event["sequence"],
                "post_sequence": None if post is None else post["sequence"],
                "abort_claim_id": None if abort is None else abort["claim_id"],
                "abort_sha256": None if abort is None else abort["abort_sha256"],
                "status": status,
            }
        )
    if require_complete and pending:
        raise AuthorityViolation(
            "authorized apply_patch event has no observed PostToolUse callback"
        )
    return {
        "schema": 1,
        "chain_sha256": value["chain_sha256"],
        "event_count": value["event_count"],
        "callbacks": callbacks,
        "denied_tool_use_ids": sorted(denied),
        "pending_tool_use_ids": sorted(pending),
        "matched_abort_claim_ids": sorted(matched_abort_ids),
        "unmatched_abort_claim_ids": sorted(
            abort["claim_id"]
            for key, abort in abort_events.items()
            if key not in pre_events
        ),
        "raw_payload_stored": False,
    }
