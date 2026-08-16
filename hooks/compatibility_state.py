#!/usr/bin/env python3

"""Provider-independent schema-v2 authority state primitives.

This module is intentionally not wired into the live Hook yet.  It provides the
state and validation core used by isolated Phase 1 probes.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import unicodedata
import uuid
from typing import Iterator, Mapping, Sequence

if os.name == "posix":
    import fcntl
else:  # pragma: no cover - exercised by the Windows parity harness later
    fcntl = None


SCHEMA = 2
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
PROVENANCE_FIELDS = {
    "authoritative_input_owners",
    "authoritative_input_roots",
    "forbidden_caller_supplied_derived_facts",
    "test_only_injection_seams",
    "required_derivation_boundary",
}
EXECUTION_CONTRACT_FIELDS = {
    "posture",
    "review_range",
    "required_invariants",
    "diagnostics",
    "proven_input_baselines",
    "termination_contract",
    "evidence_binding",
    "review_continuation",
    "closed_registries",
    "relation_contracts",
    "capsule_feasibility_attestation",
}
DIAGNOSTIC_CONTRACT_FIELDS = {
    "stable_failure_codes",
    "known_true_failure_codes",
    "generic_unclassified_failure_code",
    "allow_literal_expensive_rerun",
    "allowed_failure_code_localities",
}
PROVEN_INPUT_BASELINE_FIELDS = {
    "baseline_id",
    "owner",
    "manifest_path",
    "sha256",
    "proven_failure_code",
    "non_authorizing",
    "replay_policy",
}
FAILURE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_.-]*$")
FINDING_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
DIAGNOSTIC_LOCALITIES = {"overall", "per_item"}
TERMINATION_CONTRACT_FIELDS = {"catalog_closed", "boundary_catalog"}
TERMINATION_BOUNDARY_FIELDS = {
    "boundary_id",
    "seam",
    "ordinal",
    "termination_primitive",
    "expected_durable_resolution",
}
DURABLE_RESOLUTIONS = {
    "UNJOURNALED",
    "BLOCKED",
    "CANCELLED",
    "COMPLETED",
    "TERMINAL_NOOP",
}
EVIDENCE_BINDING_FIELDS = {
    "executed_root",
    "hashed_root",
    "source_identity",
    "canonical_output",
    "no_follow_dirfd_walk",
    "terminal_regular_file_reproof",
    "preflight_before_expensive_execution",
}
REVIEW_CONTINUATION_FIELDS = {
    "prior_assignment_id",
    "frozen_cumulative_base_oid",
    "prior_review_base_oid",
    "prior_review_tip_oid",
    "corrected_tip_oid",
    "prior_findings_sha256",
    "unresolved_finding_ids",
    "exact_narrowed_objective",
    "require_clean_worktree",
}
CLOSED_REGISTRY_FIELDS = {
    "registry_id",
    "closed_item_ids",
    "count_authority",
}
RELATION_CONTRACT_FIELDS = {
    "relation_id",
    "owner_schema_fields",
    "handoff_schema_fields",
    "owner_id_field",
    "handoff_id_field",
    "handoff_owner_id_field",
    "terminal_state_field",
    "referential_cardinality",
    "absence_semantics",
    "allowed_terminal_absence",
}
FEASIBILITY_ATTESTATION_FIELDS = {
    "parent_owner_id",
    "exact_claimed_invariant",
    "counterexample_probe",
    "bounded_completion",
    "unresolved_assumptions",
    "owner_decision",
}
COUNTEREXAMPLE_PROBE_FIELDS = {
    "probe_id",
    "probe_input_sha256",
    "executed",
    "counterexample_found",
    "evidence_sha256",
}
BOUNDED_COMPLETION_FIELDS = {
    "completion_condition",
    "work_budget",
    "proposed_mechanism",
    "mechanism_measurement",
    "scale_evidence",
    "equivalence_compression",
    "mechanism_satisfies",
    "evidence_sha256",
}
WORK_BUDGET_FIELDS = {"unit", "cardinality_domain", "limit"}
MECHANISM_MEASUREMENT_FIELDS = {"unit", "cardinality_domain", "required_lower_bound"}
SCALE_EVIDENCE_FIELDS = {"basis", "witness_input_sha256", "evidence_sha256"}
EQUIVALENCE_COMPRESSION_FIELDS = {
    "authoritative_owner_id",
    "equivalence_rule",
    "grouping_origin",
    "class_cardinality_domain",
    "identity_cardinality_domain",
    "evaluated_class_count",
    "proven_identity_count",
    "fanout_identity_count",
    "evidence_sha256",
}
UNRESOLVED_ASSUMPTION_FIELDS = {"assumption", "blocking"}
PARENT_ADJUDICATION_FIELDS = {
    "location_integrity",
    "mutation_scope_integrity",
    "verification_freshness",
    "derivation_provenance_integrity",
    "feasibility_contract_integrity",
    "evidence_sha256",
}
STATE_KINDS = (
    "pending",
    "claimed",
    "active",
    "reported",
    "consumed",
    "expired",
    "lost",
    "quarantine",
    "unresolved",
    "quiescence",
    "overlap",
    "writer_claim",
    "writer_receipt",
    "writer_abort",
    "writer_conflict",
    "hook_event_chain",
    "pretool_schema_observation",
)
WRITER_ACTOR_FIELDS = {
    "runtime_session_id",
    "thread_id",
    "agent_type",
    "canonical_agent_path",
}
TRUSTED_HOST_USER_WRITE_CONSENT_FIELDS = {
    "schema",
    "status",
    "source",
    "receipt_sha256",
}


class StateError(RuntimeError):
    """Base class for fail-closed state errors."""


class CorruptState(StateError):
    """Serialized state is malformed, untrusted, or hash-invalid."""


class IdentityMismatch(StateError):
    """A valid assignment was presented to the wrong child."""


class AuthorityViolation(StateError):
    """A child requested authority outside its immutable capsule."""


class MissingState(StateError):
    """No state record matched an otherwise valid identity."""


class AmbiguousState(StateError):
    """More than one state record matched an identity."""


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def registry_items_sha256(item_ids: Sequence[str]) -> str:
    return sha256_bytes(canonical_json(list(item_ids)))


def capsule_sha256(capsule: Mapping[str, object]) -> str:
    unsigned = dict(capsule)
    unsigned.pop("capsule_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def compact_invariant(capsule: Mapping[str, object]) -> dict:
    """Derive the small authority subset that must survive context recovery."""
    return {
        "assignment_id": capsule["assignment_id"],
        "handoff_id": capsule["handoff_id"],
        "runtime_session_id": capsule["runtime_session_id"],
        "parent_thread_id": capsule["parent_thread_id"],
        "agent_type": capsule["agent_type"],
        "requested_task_name": capsule["requested_task_name"],
        "canonical_agent_path": capsule["canonical_agent_path"],
        "root": capsule["root"],
        "assignment_mutation_mode": capsule["assignment_mutation_mode"],
        "parent_recorded_user_write_intent": capsule[
            "parent_recorded_user_write_intent"
        ],
        "trusted_host_user_write_consent": capsule[
            "trusted_host_user_write_consent"
        ],
        "owned_paths": capsule["owned_paths"],
        "excluded_paths": capsule["excluded_paths"],
        "git_authority": capsule["git_authority"],
        "stop_condition": capsule["stop_condition"],
        "pre_write_attestation_deadline": capsule["pre_write_attestation_deadline"],
        "ownership_handover": capsule["ownership_handover"],
        "authority_provenance": capsule["authority_provenance"],
        "execution_contract": capsule["execution_contract"],
    }


def compact_invariant_sha256(capsule: Mapping[str, object]) -> str:
    return sha256_bytes(canonical_json(compact_invariant(capsule)))


def provenance_policy_sha256(capsule: Mapping[str, object]) -> str:
    return sha256_bytes(canonical_json(capsule["authority_provenance"]))


def quiescence_barrier_sha256(barrier: Mapping[str, object]) -> str:
    unsigned = dict(barrier)
    unsigned.pop("barrier_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


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


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise CorruptState(f"{field} must be a UUID string")
    try:
        uuid.UUID(value)
    except ValueError as error:
        raise CorruptState(f"{field} must be a UUID string") from error
    return value


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CorruptState(f"{field} must be a non-empty string")
    return value


def _relative_paths(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CorruptState(f"{field} must be a list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or "\\" in item:
            raise CorruptState(f"{field} contains an invalid path")
        path = pathlib.PurePosixPath(item)
        if item == "." or path.is_absolute() or item != path.as_posix() or ".." in path.parts:
            raise CorruptState(f"{field} contains a non-canonical relative path")
        normalized.append(item)
    if len(set(normalized)) != len(normalized):
        raise CorruptState(f"{field} contains duplicate paths")
    return tuple(normalized)


def _paths_overlap(first: Sequence[str], second: Sequence[str]) -> bool:
    for left in first:
        left_path = pathlib.PurePosixPath(left)
        for right in second:
            right_path = pathlib.PurePosixPath(right)
            if left_path == right_path or left_path in right_path.parents or right_path in left_path.parents:
                return True
    return False


def _paths_overlap_case_safe(first: Sequence[str], second: Sequence[str]) -> bool:
    if _paths_overlap(first, second):
        return True
    if os.name != "nt" and sys.platform != "darwin":
        return False
    folded_first = [unicodedata.normalize("NFC", item).casefold() for item in first]
    folded_second = [unicodedata.normalize("NFC", item).casefold() for item in second]
    return _paths_overlap(folded_first, folded_second)


def _snapshot_sha256(snapshot: Mapping[str, object]) -> str:
    _validate_git_snapshot(snapshot)
    return sha256_bytes(canonical_json(dict(snapshot)))


def git_snapshot_sha256(snapshot: Mapping[str, object]) -> str:
    return _snapshot_sha256(snapshot)


def writer_path_snapshot_sha256(
    snapshot: Mapping[str, object], paths: Sequence[str], *, schema: int = 2
) -> str:
    if schema not in {1, 2}:
        raise CorruptState("writer path snapshot schema is invalid")
    value = _validate_git_snapshot(dict(snapshot))
    normalized_paths = list(_relative_paths(list(paths), "writer_path_snapshot.paths"))
    changed = {item["path"]: item for item in value["changed_paths"]}
    path_states = []
    for path in normalized_paths:
        state = changed.get(path)
        if state is None:
            state = {"path": path, "kind": "clean_at_head", "sha256": None}
        path_states.append(state)
    identity = {
        "root": value["root"],
        "branch": value["branch"],
        "head": value["head"],
        "path_states": path_states,
    }
    if schema == 2:
        identity["index_changed"] = value["index_changed"]
    return sha256_bytes(canonical_json(identity))


def writer_claim_sha256(claim: Mapping[str, object]) -> str:
    unsigned = {key: value for key, value in claim.items() if key != "claim_sha256"}
    return sha256_bytes(canonical_json(unsigned))


def writer_abort_sha256(receipt: Mapping[str, object]) -> str:
    unsigned = {key: value for key, value in receipt.items() if key != "abort_sha256"}
    return sha256_bytes(canonical_json(unsigned))


def _validate_writer_actor(actor: object) -> dict:
    if not isinstance(actor, dict) or set(actor) != WRITER_ACTOR_FIELDS:
        raise CorruptState("writer actor fields are not exact")
    for field in WRITER_ACTOR_FIELDS:
        _nonempty_string(actor[field], f"writer_actor.{field}")
    if not actor["canonical_agent_path"].startswith("/"):
        raise CorruptState("writer actor canonical path must be absolute")
    return actor


def _validate_writer_claim(claim: object) -> dict:
    if not isinstance(claim, dict) or set(claim) != {
        "schema",
        "claim_id",
        "actor",
        "root",
        "paths",
        "tool_name",
        "tool_use_id",
        "created_at",
        "ownership_handover",
        "before_snapshot",
        "before_snapshot_sha256",
        "claim_sha256",
    }:
        raise CorruptState("writer claim fields are not exact")
    if claim["schema"] != 1:
        raise CorruptState("writer claim schema is invalid")
    _uuid(claim["claim_id"], "writer_claim.claim_id")
    _validate_writer_actor(claim["actor"])
    root = pathlib.Path(_nonempty_string(claim["root"], "writer_claim.root"))
    if not root.is_absolute() or str(root.resolve()) != str(root):
        raise CorruptState("writer claim root is not canonical and absolute")
    _relative_paths(claim["paths"], "writer_claim.paths")
    if not claim["paths"]:
        raise CorruptState("writer claim paths are empty")
    if claim["tool_name"] != "apply_patch":
        raise CorruptState("writer claim tool is not qualified")
    _nonempty_string(claim["tool_use_id"], "writer_claim.tool_use_id")
    _timestamp(claim["created_at"], "writer_claim.created_at")
    handovers = claim["ownership_handover"]
    if not isinstance(handovers, list):
        raise CorruptState("writer claim ownership_handover is invalid")
    prior_ids = set()
    for handover in handovers:
        if not isinstance(handover, dict) or set(handover) != {
            "prior_assignment_id",
            "barrier_sha256",
            "snapshot_sha256",
        }:
            raise CorruptState("writer claim ownership_handover fields are not exact")
        prior_id = _uuid(
            handover["prior_assignment_id"],
            "writer_claim.ownership_handover.prior_assignment_id",
        )
        if prior_id in prior_ids:
            raise CorruptState("writer claim ownership_handover contains a duplicate")
        prior_ids.add(prior_id)
        for field in ("barrier_sha256", "snapshot_sha256"):
            if not isinstance(handover[field], str) or not SHA256_RE.fullmatch(handover[field]):
                raise CorruptState(f"writer claim ownership_handover.{field} is invalid")
    snapshot = _validate_git_snapshot(claim["before_snapshot"])
    if pathlib.Path(snapshot["root"]).resolve() != root:
        raise CorruptState("writer claim snapshot root does not match")
    if claim["before_snapshot_sha256"] != _snapshot_sha256(snapshot):
        raise CorruptState("writer claim snapshot hash does not match")
    if claim["claim_sha256"] != writer_claim_sha256(claim):
        raise CorruptState("writer claim hash does not match")
    return claim


def validate_writer_abort(receipt: object) -> dict:
    if not isinstance(receipt, dict) or set(receipt) != {
        "schema",
        "classification",
        "claim_id",
        "claim_sha256",
        "actor",
        "root",
        "paths",
        "tool_name",
        "tool_use_id",
        "ownership_handover",
        "before_snapshot_sha256",
        "before_path_snapshot_sha256",
        "after_snapshot",
        "after_snapshot_sha256",
        "after_path_snapshot_sha256",
        "recovery_reason",
        "recovered_at",
        "abort_sha256",
    }:
        raise CorruptState("writer abort fields are not exact")
    if receipt["schema"] not in {1, 2}:
        raise CorruptState("writer abort schema is invalid")
    if receipt["classification"] != "aborted_unchanged_after_missing_callback":
        raise CorruptState("writer abort classification is invalid")
    _uuid(receipt["claim_id"], "writer_abort.claim_id")
    if not isinstance(receipt["claim_sha256"], str) or not SHA256_RE.fullmatch(
        receipt["claim_sha256"]
    ):
        raise CorruptState("writer abort claim hash is invalid")
    _validate_writer_actor(receipt["actor"])
    root = pathlib.Path(_nonempty_string(receipt["root"], "writer_abort.root"))
    if not root.is_absolute() or str(root.resolve()) != str(root):
        raise CorruptState("writer abort root is not canonical and absolute")
    paths = _relative_paths(receipt["paths"], "writer_abort.paths")
    if not paths:
        raise CorruptState("writer abort paths are empty")
    if receipt["tool_name"] != "apply_patch":
        raise CorruptState("writer abort tool is not qualified")
    _nonempty_string(receipt["tool_use_id"], "writer_abort.tool_use_id")
    if not isinstance(receipt["ownership_handover"], list):
        raise CorruptState("writer abort ownership_handover is invalid")
    for field in (
        "before_snapshot_sha256",
        "before_path_snapshot_sha256",
        "after_snapshot_sha256",
        "after_path_snapshot_sha256",
    ):
        if not isinstance(receipt[field], str) or not SHA256_RE.fullmatch(receipt[field]):
            raise CorruptState(f"writer abort {field} is invalid")
    after_snapshot = _validate_git_snapshot(receipt["after_snapshot"])
    if pathlib.Path(after_snapshot["root"]).resolve() != root:
        raise CorruptState("writer abort snapshot root does not match")
    if receipt["after_snapshot_sha256"] != _snapshot_sha256(after_snapshot):
        raise CorruptState("writer abort after snapshot hash does not match")
    if receipt["after_path_snapshot_sha256"] != writer_path_snapshot_sha256(
        after_snapshot, paths, schema=receipt["schema"]
    ):
        raise CorruptState("writer abort after path snapshot hash does not match")
    if receipt["before_path_snapshot_sha256"] != receipt["after_path_snapshot_sha256"]:
        raise CorruptState("writer abort path snapshot changed")
    if receipt["recovery_reason"] != "missing_posttooluse_after_tool_failure":
        raise CorruptState("writer abort recovery reason is invalid")
    _timestamp(receipt["recovered_at"], "writer_abort.recovered_at")
    if receipt["abort_sha256"] != writer_abort_sha256(receipt):
        raise CorruptState("writer abort hash does not match")
    return receipt


def _validate_git_snapshot(snapshot: object) -> dict:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "root",
        "branch",
        "head",
        "index_changed",
        "git_status_short",
        "changed_paths",
    }:
        raise CorruptState("Git snapshot fields are not exact")
    root = pathlib.Path(_nonempty_string(snapshot["root"], "snapshot.root"))
    if not root.is_absolute():
        raise CorruptState("snapshot.root must be absolute")
    if snapshot["branch"] is not None and not isinstance(snapshot["branch"], str):
        raise CorruptState("snapshot.branch is invalid")
    if not isinstance(snapshot["head"], str) or not GIT_OID_RE.fullmatch(snapshot["head"]):
        raise CorruptState("snapshot.head is invalid")
    if type(snapshot["index_changed"]) is not bool:
        raise CorruptState("snapshot.index_changed is invalid")
    if not isinstance(snapshot["git_status_short"], str):
        raise CorruptState("snapshot.git_status_short is invalid")
    changed_paths = snapshot["changed_paths"]
    if not isinstance(changed_paths, list):
        raise CorruptState("snapshot.changed_paths is invalid")
    for item in changed_paths:
        if not isinstance(item, dict) or set(item) != {"path", "kind", "sha256"}:
            raise CorruptState("snapshot changed-path entry is invalid")
        _relative_paths([item["path"]], "snapshot.changed_paths.path")
        if item["kind"] not in {"file", "symlink", "deleted"}:
            raise CorruptState("snapshot changed-path kind is invalid")
        digest = item["sha256"]
        if item["kind"] == "deleted":
            if digest is not None:
                raise CorruptState("deleted snapshot path must have null sha256")
        elif not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise CorruptState("snapshot changed-path sha256 is invalid")
    return snapshot


def _validate_quiescence_barrier(barrier: object) -> dict:
    if not isinstance(barrier, dict) or set(barrier) != {
        "schema",
        "prior_assignment_id",
        "runtime_session_id",
        "terminated_child_thread_id",
        "host_termination_receipt_id",
        "host_guarantee",
        "terminated_at",
        "observed_at",
        "snapshot",
        "snapshot_sha256",
        "barrier_sha256",
    }:
        raise CorruptState("quiescence barrier fields are not exact")
    if barrier["schema"] != 1:
        raise CorruptState("quiescence barrier schema is invalid")
    _uuid(barrier["prior_assignment_id"], "prior_assignment_id")
    for field in (
        "runtime_session_id",
        "terminated_child_thread_id",
        "host_termination_receipt_id",
    ):
        _nonempty_string(barrier[field], field)
    if barrier["host_guarantee"] != "child_terminated_and_mutations_quiesced":
        raise CorruptState("quiescence barrier host guarantee is insufficient")
    terminated_at = _timestamp(barrier["terminated_at"], "terminated_at")
    observed_at = _timestamp(barrier["observed_at"], "observed_at")
    if observed_at < terminated_at:
        raise CorruptState("quiescence snapshot predates child termination")
    if not isinstance(barrier["snapshot"], dict):
        raise CorruptState("quiescence snapshot is invalid")
    if barrier["snapshot_sha256"] != _snapshot_sha256(barrier["snapshot"]):
        raise CorruptState("quiescence snapshot hash does not match")
    if barrier["barrier_sha256"] != quiescence_barrier_sha256(barrier):
        raise CorruptState("quiescence barrier hash does not match")
    return barrier


def validate_capsule(capsule: object, assignment: str) -> dict:
    if not isinstance(capsule, dict):
        raise CorruptState("capsule must be a JSON object")
    if type(capsule.get("schema")) is not int or capsule["schema"] != SCHEMA:
        raise CorruptState("capsule has an invalid schema")

    _uuid(capsule.get("assignment_id"), "assignment_id")
    _uuid(capsule.get("handoff_id"), "handoff_id")
    for field in (
        "runtime_session_id",
        "parent_thread_id",
        "parent_turn_id",
        "spawn_tool_use_id",
        "worker_profile",
        "agent_type",
        "requested_task_name",
        "stop_condition",
    ):
        _nonempty_string(capsule.get(field), field)
    if "/" in str(capsule["requested_task_name"]) or "\\" in str(capsule["requested_task_name"]):
        raise CorruptState("requested_task_name must be one path segment")

    canonical_path = capsule.get("canonical_agent_path")
    if canonical_path is not None:
        _nonempty_string(canonical_path, "canonical_agent_path")

    root = capsule.get("root")
    if not isinstance(root, dict):
        raise CorruptState("root must be a JSON object")
    root_path = pathlib.Path(_nonempty_string(root.get("path"), "root.path"))
    if not root_path.is_absolute():
        raise CorruptState("root.path must be absolute")
    branch = root.get("branch")
    base_commit = root.get("base_commit")
    if branch is not None and not isinstance(branch, str):
        raise CorruptState("root.branch must be a string or null")
    if base_commit is not None and not GIT_OID_RE.fullmatch(base_commit):
        raise CorruptState("root.base_commit must be a full lowercase hash or null")
    if type(root.get("allow_descendant_head")) is not bool:
        raise CorruptState("root.allow_descendant_head must be boolean")
    if type(root.get("base_index_changed")) is not bool:
        raise CorruptState("root.base_index_changed must be boolean")
    if not isinstance(root.get("base_git_status_short"), str):
        raise CorruptState("root.base_git_status_short must be a string")

    capture_preflight = capsule.get("capture_preflight")
    if capture_preflight is not None:
        if not isinstance(capture_preflight, dict) or set(capture_preflight) != {
            "expected_root",
            "expected_branch",
            "expected_base_head",
        }:
            raise CorruptState("capture_preflight fields are not exact")
        expected_root = pathlib.Path(
            _nonempty_string(capture_preflight["expected_root"], "capture_preflight.expected_root")
        )
        if not expected_root.is_absolute():
            raise CorruptState("capture_preflight.expected_root must be absolute")
        if capture_preflight["expected_branch"] is not None and not isinstance(
            capture_preflight["expected_branch"], str
        ):
            raise CorruptState("capture_preflight.expected_branch is invalid")
        if not GIT_OID_RE.fullmatch(str(capture_preflight["expected_base_head"])):
            raise CorruptState("capture_preflight.expected_base_head is invalid")
        if expected_root.resolve() != root_path.resolve():
            raise CorruptState("capture_preflight.expected_root does not match root.path")
        if capture_preflight["expected_branch"] != branch:
            raise CorruptState("capture_preflight.expected_branch does not match root.branch")
        if capture_preflight["expected_base_head"] != base_commit:
            raise CorruptState(
                "capture_preflight.expected_base_head does not match root.base_commit"
            )
    capture_snapshot_sha256 = capsule.get("capture_snapshot_sha256")
    if (
        not isinstance(capture_snapshot_sha256, str)
        or not SHA256_RE.fullmatch(capture_snapshot_sha256)
    ):
        raise CorruptState("capture_snapshot_sha256 is invalid")

    mutation_mode = capsule.get("assignment_mutation_mode")
    if mutation_mode not in {"read_only", "write"}:
        raise CorruptState("assignment_mutation_mode must be read_only or write")
    parent_intent = capsule.get("parent_recorded_user_write_intent")
    if parent_intent not in {"deny", "allow"}:
        raise CorruptState("parent-recorded user write intent must be deny or allow")
    if mutation_mode == "read_only" and parent_intent != "deny":
        raise CorruptState("read-only assignment cannot record user write intent")
    if mutation_mode == "write" and parent_intent != "allow":
        raise CorruptState("write assignment lacks parent-recorded explicit user intent")
    host_consent = capsule.get("trusted_host_user_write_consent")
    if (
        not isinstance(host_consent, dict)
        or set(host_consent) != TRUSTED_HOST_USER_WRITE_CONSENT_FIELDS
        or host_consent.get("schema") != 1
    ):
        raise CorruptState("trusted host user write consent fields are not exact")
    if host_consent != {
        "schema": 1,
        "status": "unavailable",
        "source": None,
        "receipt_sha256": None,
    }:
        raise CorruptState(
            "trusted host user write consent is unavailable in isolated schema 2"
        )

    _relative_paths(capsule.get("owned_paths"), "owned_paths")
    _relative_paths(capsule.get("excluded_paths"), "excluded_paths")
    git_authority = capsule.get("git_authority")
    if not isinstance(git_authority, dict):
        raise CorruptState("git_authority must be a JSON object")
    for operation in ("stage", "commit", "branch", "push"):
        if type(git_authority.get(operation)) is not bool:
            raise CorruptState(f"git_authority.{operation} must be boolean")

    ownership_handover = capsule.get("ownership_handover")
    if not isinstance(ownership_handover, list):
        raise CorruptState("ownership_handover must be a list")
    seen_prior_assignments = set()
    for item in ownership_handover:
        if not isinstance(item, dict) or set(item) != {
            "prior_assignment_id",
            "barrier_sha256",
            "snapshot_sha256",
        }:
            raise CorruptState("ownership_handover entries are invalid")
        prior_assignment_id = _uuid(item["prior_assignment_id"], "prior_assignment_id")
        if prior_assignment_id in seen_prior_assignments:
            raise CorruptState("ownership_handover contains a duplicate prior assignment")
        seen_prior_assignments.add(prior_assignment_id)
        for field in ("barrier_sha256", "snapshot_sha256"):
            if not isinstance(item[field], str) or not SHA256_RE.fullmatch(item[field]):
                raise CorruptState(f"ownership_handover.{field} is invalid")

    verification = capsule.get("verification")
    if not isinstance(verification, list) or any(
        not isinstance(item, str) or not item.strip() for item in verification
    ):
        raise CorruptState("verification must contain only non-empty strings")

    provenance = capsule.get("authority_provenance")
    if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_FIELDS:
        raise CorruptState("authority_provenance fields are not exact")
    for field in (
        "authoritative_input_owners",
        "forbidden_caller_supplied_derived_facts",
    ):
        values = provenance[field]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or len(values) != len(set(values))
        ):
            raise CorruptState(f"authority_provenance.{field} is invalid")
    _relative_paths(
        provenance["authoritative_input_roots"],
        "authority_provenance.authoritative_input_roots",
    )
    if not provenance["authoritative_input_roots"]:
        raise CorruptState("authority_provenance.authoritative_input_roots is empty")
    seams = provenance["test_only_injection_seams"]
    if (
        not isinstance(seams, list)
        or any(not isinstance(item, str) or not item.strip() for item in seams)
        or len(seams) != len(set(seams))
    ):
        raise CorruptState("authority_provenance.test_only_injection_seams is invalid")
    _nonempty_string(
        provenance["required_derivation_boundary"],
        "authority_provenance.required_derivation_boundary",
    )

    execution = capsule.get("execution_contract")
    if not isinstance(execution, dict) or set(execution) != EXECUTION_CONTRACT_FIELDS:
        raise CorruptState("execution_contract fields are not exact")
    posture = execution["posture"]
    if posture not in {"strict_read_only", "direct_write_unqualified"}:
        raise CorruptState("execution_contract.posture is invalid")
    if mutation_mode == "read_only" and posture != "strict_read_only":
        raise CorruptState("read-only mutation mode requires strict_read_only posture")
    if mutation_mode == "write" and posture != "direct_write_unqualified":
        raise CorruptState("write mutation mode requires direct_write_unqualified posture")
    review_range = execution["review_range"]
    if review_range is not None:
        if not isinstance(review_range, dict) or set(review_range) != {"base_oid", "head_oid"}:
            raise CorruptState("execution_contract.review_range fields are not exact")
        for field in ("base_oid", "head_oid"):
            if not isinstance(review_range[field], str) or not GIT_OID_RE.fullmatch(
                review_range[field]
            ):
                raise CorruptState(f"execution_contract.review_range.{field} is invalid")
    invariants = execution["required_invariants"]
    if (
        not isinstance(invariants, list)
        or any(not isinstance(item, str) or not item.strip() for item in invariants)
        or len(invariants) != len(set(invariants))
    ):
        raise CorruptState("execution_contract.required_invariants is invalid")
    diagnostics = execution["diagnostics"]
    if not isinstance(diagnostics, dict) or set(diagnostics) != DIAGNOSTIC_CONTRACT_FIELDS:
        raise CorruptState("execution_contract.diagnostics fields are not exact")
    for field in ("stable_failure_codes", "known_true_failure_codes"):
        codes = diagnostics[field]
        if (
            not isinstance(codes, list)
            or any(not isinstance(code, str) or not FAILURE_CODE_RE.fullmatch(code) for code in codes)
            or len(codes) != len(set(codes))
        ):
            raise CorruptState(f"execution_contract.diagnostics.{field} is invalid")
    stable_codes = diagnostics["stable_failure_codes"]
    known_codes = diagnostics["known_true_failure_codes"]
    if not set(known_codes).issubset(stable_codes):
        raise CorruptState("known-true failure codes must be stable owner codes")
    generic_code = diagnostics["generic_unclassified_failure_code"]
    if not isinstance(generic_code, str) or not FAILURE_CODE_RE.fullmatch(generic_code):
        raise CorruptState("generic unclassified failure code is invalid")
    if generic_code in stable_codes:
        raise CorruptState("generic unclassified code must not shadow a stable owner code")
    if type(diagnostics["allow_literal_expensive_rerun"]) is not bool:
        raise CorruptState("allow_literal_expensive_rerun must be boolean")
    localities = diagnostics["allowed_failure_code_localities"]
    if not isinstance(localities, dict) or set(localities) != set(stable_codes):
        raise CorruptState("every stable failure code must declare exact allowed localities")
    for code, allowed in localities.items():
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(item not in DIAGNOSTIC_LOCALITIES for item in allowed)
            or len(allowed) != len(set(allowed))
        ):
            raise CorruptState(f"allowed failure-code localities are invalid for {code}")
    baselines = execution["proven_input_baselines"]
    if not isinstance(baselines, list):
        raise CorruptState("execution_contract.proven_input_baselines must be a list")
    seen_baseline_ids = set()
    input_roots = tuple(provenance["authoritative_input_roots"])
    for baseline in baselines:
        if not isinstance(baseline, dict) or set(baseline) != PROVEN_INPUT_BASELINE_FIELDS:
            raise CorruptState("proven input baseline fields are not exact")
        baseline_id = _nonempty_string(baseline["baseline_id"], "baseline_id")
        if baseline_id in seen_baseline_ids:
            raise CorruptState("proven input baseline id is duplicated")
        seen_baseline_ids.add(baseline_id)
        if baseline["owner"] not in provenance["authoritative_input_owners"]:
            raise CorruptState("proven input baseline owner is not authoritative")
        manifest_path = _relative_paths(
            [baseline["manifest_path"]], "proven_input_baseline.manifest_path"
        )[0]
        manifest = pathlib.PurePosixPath(manifest_path)
        if not any(
            manifest == pathlib.PurePosixPath(root)
            or pathlib.PurePosixPath(root) in manifest.parents
            for root in input_roots
        ):
            raise CorruptState("proven input baseline is outside authoritative input roots")
        if not isinstance(baseline["sha256"], str) or not SHA256_RE.fullmatch(
            baseline["sha256"]
        ):
            raise CorruptState("proven input baseline sha256 is invalid")
        if baseline["proven_failure_code"] not in known_codes:
            raise CorruptState("proven input baseline failure code is not known-true")
        if baseline["non_authorizing"] is not True:
            raise CorruptState("proven input baseline must be explicitly non-authorizing")
        if baseline["replay_policy"] != "reuse_without_authority_expansion":
            raise CorruptState("proven input baseline replay policy is invalid")

    termination = execution["termination_contract"]
    if not isinstance(termination, dict) or set(termination) != TERMINATION_CONTRACT_FIELDS:
        raise CorruptState("termination_contract fields are not exact")
    if termination["catalog_closed"] is not True:
        raise CorruptState("termination boundary catalog must be explicitly closed")
    boundary_catalog = termination["boundary_catalog"]
    if not isinstance(boundary_catalog, list):
        raise CorruptState("termination boundary catalog must be a list")
    boundary_ids = set()
    seam_ordinals = set()
    for boundary in boundary_catalog:
        if not isinstance(boundary, dict) or set(boundary) != TERMINATION_BOUNDARY_FIELDS:
            raise CorruptState("termination boundary fields are not exact")
        boundary_id = _nonempty_string(boundary["boundary_id"], "boundary_id")
        seam = _nonempty_string(boundary["seam"], "termination seam")
        ordinal = boundary["ordinal"]
        if type(ordinal) is not int or ordinal < 0:
            raise CorruptState("termination boundary ordinal must be non-negative")
        if boundary_id in boundary_ids or (seam, ordinal) in seam_ordinals:
            raise CorruptState("termination boundary catalog contains a duplicate")
        boundary_ids.add(boundary_id)
        seam_ordinals.add((seam, ordinal))
        if boundary["termination_primitive"] != "os._exit":
            raise CorruptState("crash evidence requires the os._exit termination primitive")
        if boundary["expected_durable_resolution"] not in DURABLE_RESOLUTIONS:
            raise CorruptState("termination boundary durable resolution is invalid")

    evidence_binding = execution["evidence_binding"]
    if evidence_binding is not None:
        if not isinstance(evidence_binding, dict) or set(evidence_binding) != EVIDENCE_BINDING_FIELDS:
            raise CorruptState("evidence_binding fields are not exact")
        executed_root = pathlib.Path(
            _nonempty_string(evidence_binding["executed_root"], "evidence executed_root")
        )
        hashed_root = pathlib.Path(
            _nonempty_string(evidence_binding["hashed_root"], "evidence hashed_root")
        )
        if not executed_root.is_absolute() or not hashed_root.is_absolute():
            raise CorruptState("evidence roots must be absolute")
        if executed_root.resolve() != root_path.resolve() or hashed_root.resolve() != root_path.resolve():
            raise CorruptState("executed, hashed, and capsule roots must be identical")
        source_identity = evidence_binding["source_identity"]
        if not isinstance(source_identity, dict) or set(source_identity) != {"kind", "value"}:
            raise CorruptState("evidence source_identity fields are not exact")
        if source_identity["kind"] != "git_commit" or not GIT_OID_RE.fullmatch(
            str(source_identity["value"])
        ):
            raise CorruptState("evidence source identity must be a full Git commit id")
        if source_identity["value"] != root["base_commit"]:
            raise CorruptState("evidence source identity must match the captured base commit")
        _relative_paths([evidence_binding["canonical_output"]], "evidence canonical_output")
        for field in (
            "no_follow_dirfd_walk",
            "terminal_regular_file_reproof",
            "preflight_before_expensive_execution",
        ):
            if evidence_binding[field] is not True:
                raise CorruptState(f"evidence_binding.{field} must be true")

    continuation = execution["review_continuation"]
    if continuation is not None:
        if not isinstance(continuation, dict) or set(continuation) != REVIEW_CONTINUATION_FIELDS:
            raise CorruptState("review_continuation fields are not exact")
        _uuid(continuation["prior_assignment_id"], "prior_assignment_id")
        for field in (
            "frozen_cumulative_base_oid",
            "prior_review_base_oid",
            "prior_review_tip_oid",
            "corrected_tip_oid",
        ):
            if not isinstance(continuation[field], str) or not GIT_OID_RE.fullmatch(
                continuation[field]
            ):
                raise CorruptState(f"review_continuation.{field} is invalid")
        if not isinstance(continuation["prior_findings_sha256"], str) or not SHA256_RE.fullmatch(
            continuation["prior_findings_sha256"]
        ):
            raise CorruptState("review_continuation.prior_findings_sha256 is invalid")
        finding_ids = continuation["unresolved_finding_ids"]
        if (
            not isinstance(finding_ids, list)
            or any(not isinstance(item, str) or not FINDING_ID_RE.fullmatch(item) for item in finding_ids)
            or len(finding_ids) != len(set(finding_ids))
        ):
            raise CorruptState("review_continuation.unresolved_finding_ids is invalid")
        if continuation["require_clean_worktree"] is not True:
            raise CorruptState("review continuation must require a clean worktree")
        _nonempty_string(
            continuation["exact_narrowed_objective"],
            "review_continuation.exact_narrowed_objective",
        )
        if continuation["prior_review_base_oid"] != continuation["frozen_cumulative_base_oid"]:
            raise CorruptState("prior review base changed from the frozen cumulative base")

    closed_registries = execution["closed_registries"]
    if not isinstance(closed_registries, list):
        raise CorruptState("closed_registries must be a list")
    registry_ids = set()
    for registry in closed_registries:
        if not isinstance(registry, dict) or set(registry) != CLOSED_REGISTRY_FIELDS:
            raise CorruptState("closed registry fields are not exact")
        registry_id = _nonempty_string(registry["registry_id"], "registry_id")
        if registry_id in registry_ids:
            raise CorruptState("closed registry id is duplicated")
        registry_ids.add(registry_id)
        item_ids = registry["closed_item_ids"]
        if (
            not isinstance(item_ids, list)
            or any(not isinstance(item, str) or not FINDING_ID_RE.fullmatch(item) for item in item_ids)
            or len(item_ids) != len(set(item_ids))
        ):
            raise CorruptState("closed registry item ids are invalid")
        if registry["count_authority"] != "mechanical_cardinality_only":
            raise CorruptState("closed registry count authority is invalid")

    relation_contracts = execution["relation_contracts"]
    if not isinstance(relation_contracts, list):
        raise CorruptState("relation_contracts must be a list")
    relation_ids = set()
    for relation in relation_contracts:
        if not isinstance(relation, dict) or set(relation) != RELATION_CONTRACT_FIELDS:
            raise CorruptState("relation contract fields are not exact")
        relation_id = _nonempty_string(relation["relation_id"], "relation_id")
        if relation_id in relation_ids:
            raise CorruptState("relation contract id is duplicated")
        relation_ids.add(relation_id)
        for field in ("owner_schema_fields", "handoff_schema_fields"):
            fields = relation[field]
            if (
                not isinstance(fields, list)
                or not fields
                or any(not isinstance(item, str) or not item for item in fields)
                or len(fields) != len(set(fields))
            ):
                raise CorruptState(f"relation {field} is invalid")
        for field in (
            "owner_id_field",
            "handoff_id_field",
            "handoff_owner_id_field",
            "terminal_state_field",
        ):
            _nonempty_string(relation[field], f"relation {field}")
        if relation["owner_id_field"] not in relation["owner_schema_fields"]:
            raise CorruptState("owner id field is absent from owner schema")
        if relation["handoff_id_field"] not in relation["handoff_schema_fields"]:
            raise CorruptState("handoff id field is absent from handoff schema")
        if relation["handoff_owner_id_field"] not in relation["handoff_schema_fields"]:
            raise CorruptState("handoff owner field is absent from handoff schema")
        if (
            relation["terminal_state_field"] not in relation["owner_schema_fields"]
            or relation["terminal_state_field"] not in relation["handoff_schema_fields"]
        ):
            raise CorruptState("terminal state field must exist in both object schemas")
        if relation["referential_cardinality"] != "exactly_one_to_one_nonterminal":
            raise CorruptState("relation referential cardinality is invalid")
        if relation["absence_semantics"] != "missing_or_orphan_relation_is_error":
            raise CorruptState("relation absence semantics are invalid")
        if relation["allowed_terminal_absence"] != "tombstone_or_clear_only":
            raise CorruptState("relation terminal absence exception is invalid")

    feasibility = execution["capsule_feasibility_attestation"]
    if feasibility is not None:
        if not isinstance(feasibility, dict) or set(feasibility) != FEASIBILITY_ATTESTATION_FIELDS:
            raise CorruptState("capsule feasibility attestation fields are not exact")
        if feasibility["parent_owner_id"] not in provenance["authoritative_input_owners"]:
            raise CorruptState(
                "feasibility attestation is not authored by an authoritative parent owner"
            )
        _nonempty_string(
            feasibility["exact_claimed_invariant"],
            "feasibility exact_claimed_invariant",
        )
        probe = feasibility["counterexample_probe"]
        if not isinstance(probe, dict) or set(probe) != COUNTEREXAMPLE_PROBE_FIELDS:
            raise CorruptState("counterexample probe fields are not exact")
        _nonempty_string(probe["probe_id"], "counterexample probe_id")
        for field in ("probe_input_sha256", "evidence_sha256"):
            if not isinstance(probe[field], str) or not SHA256_RE.fullmatch(probe[field]):
                raise CorruptState(f"counterexample probe {field} is invalid")
        if probe["executed"] is not True:
            raise CorruptState("counterexample probe must be executed before dispatch")
        if type(probe["counterexample_found"]) is not bool:
            raise CorruptState("counterexample_found must be boolean")
        bounded = feasibility["bounded_completion"]
        if not isinstance(bounded, dict) or set(bounded) != BOUNDED_COMPLETION_FIELDS:
            raise CorruptState("bounded completion fields are not exact")
        for field in ("completion_condition", "proposed_mechanism"):
            _nonempty_string(bounded[field], f"bounded completion {field}")
        if bounded["completion_condition"] not in capsule["stop_condition"]:
            raise CorruptState("bounded completion condition is not bound by stop_condition")
        work_budget = bounded["work_budget"]
        if not isinstance(work_budget, dict) or set(work_budget) != WORK_BUDGET_FIELDS:
            raise CorruptState("work budget fields are not exact")
        for field in ("unit", "cardinality_domain"):
            _nonempty_string(work_budget[field], f"work budget {field}")
        if type(work_budget["limit"]) not in {int, float} or work_budget["limit"] <= 0:
            raise CorruptState("work budget limit must be positive")

        measurement = bounded["mechanism_measurement"]
        if not isinstance(measurement, dict) or set(measurement) != MECHANISM_MEASUREMENT_FIELDS:
            raise CorruptState("mechanism measurement fields are not exact")
        for field in ("unit", "cardinality_domain"):
            _nonempty_string(measurement[field], f"mechanism measurement {field}")
        if (
            type(measurement["required_lower_bound"]) is not int
            or measurement["required_lower_bound"] < 0
        ):
            raise CorruptState("mechanism required_lower_bound must be a non-negative integer")

        scale = bounded["scale_evidence"]
        if not isinstance(scale, dict) or set(scale) != SCALE_EVIDENCE_FIELDS:
            raise CorruptState("scale evidence fields are not exact")
        if scale["basis"] not in {"proven_monotonicity", "adversarial_scale_witness"}:
            raise CorruptState("scale evidence basis is invalid")
        witness_sha256 = scale["witness_input_sha256"]
        if scale["basis"] == "adversarial_scale_witness":
            if not isinstance(witness_sha256, str) or not SHA256_RE.fullmatch(witness_sha256):
                raise CorruptState("adversarial scale witness hash is invalid")
        elif witness_sha256 is not None:
            raise CorruptState("monotonicity evidence cannot carry a scale witness hash")
        if not isinstance(scale["evidence_sha256"], str) or not SHA256_RE.fullmatch(
            scale["evidence_sha256"]
        ):
            raise CorruptState("scale evidence_sha256 is invalid")

        compression = bounded["equivalence_compression"]
        compression_valid = True
        if compression is not None:
            if (
                not isinstance(compression, dict)
                or set(compression) != EQUIVALENCE_COMPRESSION_FIELDS
            ):
                raise CorruptState("equivalence compression fields are not exact")
            for field in (
                "authoritative_owner_id",
                "equivalence_rule",
                "grouping_origin",
                "class_cardinality_domain",
                "identity_cardinality_domain",
            ):
                _nonempty_string(compression[field], f"equivalence compression {field}")
            for field in (
                "evaluated_class_count",
                "proven_identity_count",
                "fanout_identity_count",
            ):
                if type(compression[field]) is not int or compression[field] < 0:
                    raise CorruptState(f"equivalence compression {field} must be non-negative")
            if not isinstance(compression["evidence_sha256"], str) or not SHA256_RE.fullmatch(
                compression["evidence_sha256"]
            ):
                raise CorruptState("equivalence compression evidence_sha256 is invalid")
            compression_valid = all(
                (
                    compression["authoritative_owner_id"] == feasibility["parent_owner_id"],
                    compression["grouping_origin"] == "owner_derived",
                    compression["class_cardinality_domain"] == measurement["cardinality_domain"],
                    compression["evaluated_class_count"] <= compression["proven_identity_count"],
                    compression["fanout_identity_count"] == compression["proven_identity_count"],
                    measurement["required_lower_bound"] >= compression["evaluated_class_count"],
                )
            )

        mechanism_satisfies = all(
            (
                measurement["unit"] == work_budget["unit"],
                measurement["cardinality_domain"] == work_budget["cardinality_domain"],
                measurement["required_lower_bound"] <= work_budget["limit"],
                compression_valid,
            )
        )
        if type(bounded["mechanism_satisfies"]) is not bool:
            raise CorruptState("mechanism_satisfies must be boolean")
        if bounded["mechanism_satisfies"] != mechanism_satisfies:
            raise CorruptState("mechanism_satisfies contradicts budget-domain evidence")
        if not isinstance(bounded["evidence_sha256"], str) or not SHA256_RE.fullmatch(
            bounded["evidence_sha256"]
        ):
            raise CorruptState("bounded completion evidence_sha256 is invalid")
        assumptions = feasibility["unresolved_assumptions"]
        if not isinstance(assumptions, list):
            raise CorruptState("unresolved assumptions must be a list")
        for assumption in assumptions:
            if not isinstance(assumption, dict) or set(assumption) != UNRESOLVED_ASSUMPTION_FIELDS:
                raise CorruptState("unresolved assumption fields are not exact")
            _nonempty_string(assumption["assumption"], "unresolved assumption")
            if type(assumption["blocking"]) is not bool:
                raise CorruptState("unresolved assumption blocking flag is invalid")
        dispatchable = (
            not probe["counterexample_found"]
            and bounded["mechanism_satisfies"]
            and not any(item["blocking"] for item in assumptions)
        )
        if feasibility["owner_decision"] not in {"dispatch", "block"}:
            raise CorruptState("feasibility owner_decision is invalid")
        if (feasibility["owner_decision"] == "dispatch") != dispatchable:
            raise CorruptState("feasibility owner decision contradicts executable evidence")

    if posture == "strict_read_only":
        if review_range is None:
            raise CorruptState("strict read-only execution requires an exact review range")
        if review_range["head_oid"] != root["base_commit"]:
            raise CorruptState("strict read-only review head must match the captured base commit")
        if root["base_index_changed"] or root["base_git_status_short"]:
            raise CorruptState("strict read-only execution requires a clean captured root")
        if capsule["owned_paths"] or capsule["excluded_paths"]:
            raise CorruptState("strict read-only execution cannot claim path ownership")
        if any(capsule["git_authority"].values()):
            raise CorruptState("strict read-only execution cannot claim Git authority")
        if capsule["ownership_handover"]:
            raise CorruptState("strict read-only execution cannot consume an ownership handover")
        if diagnostics["allow_literal_expensive_rerun"]:
            raise CorruptState("strict read-only execution cannot authorize a literal expensive rerun")
        if capsule.get("preexisting_dirty") != []:
            raise CorruptState("strict read-only execution cannot capture pre-existing dirty paths")
        if continuation is not None:
            if continuation["frozen_cumulative_base_oid"] != review_range["base_oid"]:
                raise CorruptState("review continuation changed the frozen cumulative base")
            if continuation["corrected_tip_oid"] != review_range["head_oid"]:
                raise CorruptState("review continuation tip does not match the review range")
            if continuation["exact_narrowed_objective"] not in capsule["stop_condition"]:
                raise CorruptState("narrowed objective is not bound by the stop condition")
    elif review_range is not None:
        raise CorruptState("direct-write execution cannot reuse the read-only review range field")
    elif continuation is not None:
        raise CorruptState("review continuation is valid only for strict read-only execution")
    if posture == "direct_write_unqualified":
        if feasibility is None:
            raise CorruptState("direct-write execution requires parent feasibility attestation")
        if feasibility["owner_decision"] != "dispatch":
            raise CorruptState("direct-write execution is not feasible for dispatch")

    dirty = capsule.get("preexisting_dirty")
    if not isinstance(dirty, list):
        raise CorruptState("preexisting_dirty must be a list")
    for item in dirty:
        if not isinstance(item, dict):
            raise CorruptState("preexisting_dirty entries must be objects")
        _relative_paths([item.get("path")], "preexisting_dirty.path")
        _nonempty_string(item.get("status"), "preexisting_dirty.status")
        if item.get("kind") not in {"file", "symlink", "deleted"}:
            raise CorruptState("preexisting_dirty.kind is invalid")
        digest = item.get("sha256")
        if item["kind"] == "deleted":
            if digest is not None:
                raise CorruptState("deleted preexisting_dirty.sha256 must be null")
        elif not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise CorruptState("preexisting_dirty.sha256 must be lowercase SHA-256")

    created_at = _timestamp(capsule.get("created_at"), "created_at")
    pre_write_deadline = _timestamp(
        capsule.get("pre_write_attestation_deadline"),
        "pre_write_attestation_deadline",
    )
    expires_at = _timestamp(capsule.get("expires_at"), "expires_at")
    if pre_write_deadline <= created_at or pre_write_deadline > expires_at:
        raise CorruptState("pre_write_attestation_deadline is outside capsule lifetime")
    if expires_at <= created_at:
        raise CorruptState("expires_at must be later than created_at")

    if not isinstance(assignment, str) or not assignment.strip():
        raise CorruptState("assignment must be a non-empty string")
    if capsule.get("assignment_sha256") != sha256_bytes(assignment.encode("utf-8")):
        raise CorruptState("assignment_sha256 does not match the assignment")
    digest = capsule.get("capsule_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise CorruptState("capsule_sha256 must be lowercase SHA-256")
    if digest != capsule_sha256(capsule):
        raise CorruptState("capsule_sha256 does not match the capsule")
    return capsule


def _path_is_owned(path: str, owned_paths: Sequence[str]) -> bool:
    candidate = pathlib.PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or path != candidate.as_posix():
        return False
    return any(candidate == pathlib.PurePosixPath(owner) or pathlib.PurePosixPath(owner) in candidate.parents for owner in owned_paths)


class StateStore:
    """Keyed lifecycle store. Every transition is serialized by an OS lock."""

    def __init__(self, root: pathlib.Path | str):
        self.root = pathlib.Path(root).resolve()

    def path(self, kind: str, identity: str) -> pathlib.Path:
        if kind not in STATE_KINDS:
            raise ValueError(f"unknown state kind: {kind}")
        return self.root / kind / f"{identity}.json"

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        if fcntl is None:
            raise StateError("schema-v2 locking is not qualified on this platform")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.root / ".compatibility-state.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _publish(self, target: pathlib.Path, value: object, *, replace: bool = False) -> None:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists() and not replace:
            raise StateError(f"state already exists: {target.name}")
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _read(self, path: pathlib.Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CorruptState(f"cannot decode {path.name}") from error
        if not isinstance(value, dict):
            raise CorruptState(f"{path.name} must contain a JSON object")
        return value

    def _validated_envelope(self, path: pathlib.Path) -> dict:
        envelope = self._read(path)
        if envelope.get("schema") != SCHEMA:
            raise CorruptState("envelope has an invalid schema")
        assignment = envelope.get("assignment")
        validate_capsule(envelope.get("capsule"), assignment)
        return envelope

    def _quarantine(self, source: pathlib.Path) -> pathlib.Path:
        target = self.path("quarantine", f"{source.stem}.{uuid.uuid4().hex}")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source.rename(target)
        return target

    def stage(self, capsule: dict, assignment: str) -> pathlib.Path:
        validate_capsule(capsule, assignment)
        if _timestamp(capsule["expires_at"], "expires_at") <= dt.datetime.now(dt.timezone.utc):
            raise StateError("refusing to stage an expired capsule")
        target = self.path("pending", capsule["handoff_id"])
        with self.locked():
            self._publish(target, {"schema": SCHEMA, "capsule": capsule, "assignment": assignment})
        return target

    def claim(self, handoff_id: str, identity: Mapping[str, str]) -> pathlib.Path:
        _uuid(handoff_id, "handoff_id")
        pending = self.path("pending", handoff_id)
        with self.locked():
            try:
                envelope = self._validated_envelope(pending)
            except CorruptState:
                if pending.exists():
                    self._quarantine(pending)
                raise
            capsule = envelope["capsule"]
            if _timestamp(capsule["expires_at"], "expires_at") <= dt.datetime.now(dt.timezone.utc):
                expired = self.path("expired", handoff_id)
                self._publish(expired, envelope)
                pending.unlink()
                raise StateError("pending capsule expired before child binding")
            self._assert_identity(capsule, identity)
            claimed = self.path("claimed", handoff_id)
            envelope["binding"] = dict(identity)
            self._publish(claimed, envelope)
            pending.unlink()
            return claimed

    def claim_unique(self, identity: Mapping[str, str]) -> tuple[str, pathlib.Path]:
        matches: list[tuple[str, pathlib.Path, dict]] = []
        now = dt.datetime.now(dt.timezone.utc)
        with self.locked():
            pending_directory = self.root / "pending"
            if not pending_directory.exists():
                raise MissingState("expected one pending authority capsule, found 0")
            for pending in sorted(pending_directory.glob("*.json")):
                try:
                    envelope = self._validated_envelope(pending)
                except CorruptState:
                    self._quarantine(pending)
                    continue
                capsule = envelope["capsule"]
                if _timestamp(capsule["expires_at"], "expires_at") <= now:
                    expired = self.path("expired", capsule["handoff_id"])
                    self._publish(expired, envelope)
                    pending.unlink()
                    continue
                try:
                    self._assert_identity(capsule, identity)
                except IdentityMismatch:
                    continue
                matches.append((capsule["handoff_id"], pending, envelope))
            if not matches:
                raise MissingState("expected one pending authority capsule, found 0")
            if len(matches) > 1:
                raise AmbiguousState(
                    f"expected one pending authority capsule, found {len(matches)}"
                )
            handoff_id, pending, envelope = matches[0]
            envelope["binding"] = dict(identity)
            claimed = self.path("claimed", handoff_id)
            self._publish(claimed, envelope)
            pending.unlink()
            return handoff_id, claimed

    def activate(self, handoff_id: str) -> pathlib.Path:
        claimed = self.path("claimed", handoff_id)
        with self.locked():
            envelope = self._validated_envelope(claimed)
            if not isinstance(envelope.get("binding"), dict):
                raise CorruptState("claimed envelope has no binding")
            capsule = envelope["capsule"]
            if _timestamp(capsule["expires_at"], "expires_at") <= dt.datetime.now(dt.timezone.utc):
                unresolved = self.path("unresolved", capsule["assignment_id"])
                self._publish(unresolved, envelope)
                claimed.unlink()
                raise StateError("claimed capsule expired before activation")
            envelope["runtime"] = {
                "recovery_count": 0,
                "context_lost": False,
                "first_git_attested_at": None,
            }
            active = self.path("active", capsule["assignment_id"])
            self._publish(active, envelope)
            claimed.unlink()
            return active

    def mark_recovery(self, assignment_id: str) -> int:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            runtime = envelope.get("runtime")
            if not isinstance(runtime, dict) or type(runtime.get("recovery_count")) is not int:
                raise CorruptState("active runtime metadata is invalid")
            runtime["recovery_count"] += 1
            self._publish(active, envelope, replace=True)
            return runtime["recovery_count"]

    def attest_tool_use(
        self,
        assignment_id: str,
        identity: Mapping[str, str],
        *,
        root: str,
        branch: str | None,
        head: str | None,
        changed_paths: Sequence[str] = (),
        git_operation: str | None = None,
        now: dt.datetime | None = None,
    ) -> dict:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            capsule = envelope["capsule"]
            observed_at = now or dt.datetime.now(dt.timezone.utc)
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise AuthorityViolation("attestation time must include a UTC offset")
            if _timestamp(capsule["expires_at"], "expires_at") <= observed_at:
                unresolved = self.path("unresolved", assignment_id)
                self._publish(unresolved, envelope)
                active.unlink()
                raise AuthorityViolation("active authority expired")
            runtime = envelope.get("runtime")
            if not isinstance(runtime, dict):
                raise CorruptState("active runtime metadata is invalid")
            if (
                runtime.get("first_git_attested_at") is None
                and observed_at > _timestamp(
                    capsule["pre_write_attestation_deadline"],
                    "pre_write_attestation_deadline",
                )
            ):
                raise AuthorityViolation("first Git attestation deadline elapsed")
            self._assert_identity(capsule, identity, envelope.get("binding"))
            expected_root = capsule["root"]
            if pathlib.Path(root).resolve() != pathlib.Path(expected_root["path"]).resolve():
                raise AuthorityViolation("root expansion is not authorized")
            if branch != expected_root["branch"]:
                raise AuthorityViolation("branch change is not authorized")
            if not expected_root["allow_descendant_head"] and head != expected_root["base_commit"]:
                raise AuthorityViolation("HEAD change is not authorized")
            if git_operation is not None:
                if git_operation not in capsule["git_authority"]:
                    raise AuthorityViolation("unknown Git operation")
                if not capsule["git_authority"][git_operation]:
                    raise AuthorityViolation(f"Git {git_operation} is not authorized")
            excluded = capsule["excluded_paths"]
            for path in changed_paths:
                if not _path_is_owned(path, capsule["owned_paths"]):
                    raise AuthorityViolation(f"path is outside owned_paths: {path}")
                if _path_is_owned(path, excluded):
                    raise AuthorityViolation(f"path is excluded: {path}")
            if runtime.get("first_git_attested_at") is None:
                runtime["first_git_attested_at"] = observed_at.isoformat()
                self._publish(active, envelope, replace=True)
            return envelope

    def list_active(self) -> list[tuple[str, dict]]:
        values: list[tuple[str, dict]] = []
        with self.locked():
            directory = self.root / "active"
            if not directory.exists():
                return values
            for path in sorted(directory.glob("*.json")):
                try:
                    envelope = self._validated_envelope(path)
                except CorruptState:
                    self._quarantine(path)
                    continue
                values.append((envelope["capsule"]["assignment_id"], envelope))
        return values

    def acquire_writer_claim(
        self,
        actor: Mapping[str, str],
        *,
        root: str,
        paths: Sequence[str],
        tool_name: str,
        tool_use_id: str,
        before_snapshot: Mapping[str, object],
        observed_at: dt.datetime | None = None,
    ) -> pathlib.Path:
        _validate_writer_actor(dict(actor))
        canonical_root = pathlib.Path(root).resolve()
        if str(canonical_root) != root:
            raise AuthorityViolation("writer claim root is not canonical")
        normalized_paths = list(_relative_paths(list(paths), "writer_claim.paths"))
        if not normalized_paths:
            raise AuthorityViolation("writer claim must name at least one path")
        if tool_name != "apply_patch":
            raise AuthorityViolation("writer claim tool is not qualified")
        _nonempty_string(tool_use_id, "writer_claim.tool_use_id")
        _validate_git_snapshot(dict(before_snapshot))
        if pathlib.Path(before_snapshot["root"]).resolve() != canonical_root:
            raise AuthorityViolation("writer claim snapshot root does not match")
        now = observed_at or dt.datetime.now(dt.timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise StateError("writer claim time must include a UTC offset")

        with self.locked():
            conflicts: list[dict] = []
            ownership_handover: list[dict] = []
            claims_directory = self.root / "writer_claim"
            if claims_directory.exists():
                for path in sorted(claims_directory.glob("*.json")):
                    try:
                        prior_claim = _validate_writer_claim(self._read(path))
                    except CorruptState:
                        self._quarantine(path)
                        raise
                    same_tool_use = (
                        prior_claim["actor"] == dict(actor)
                        and prior_claim["tool_use_id"] == tool_use_id
                    )
                    if pathlib.Path(prior_claim["root"]).resolve() == canonical_root and (
                        same_tool_use
                        or _paths_overlap_case_safe(normalized_paths, prior_claim["paths"])
                    ):
                        conflicts.append(
                            {
                                "kind": "writer_claim",
                                "claim_id": prior_claim["claim_id"],
                                "paths": prior_claim["paths"],
                            }
                        )

            for kind in ("pending", "claimed", "active", "reported"):
                directory = self.root / kind
                if not directory.exists():
                    continue
                for path in sorted(directory.glob("*.json")):
                    try:
                        envelope = self._validated_envelope(path)
                    except CorruptState:
                        self._quarantine(path)
                        raise
                    capsule = envelope["capsule"]
                    if pathlib.Path(capsule["root"]["path"]).resolve() != canonical_root:
                        continue
                    if not _paths_overlap_case_safe(normalized_paths, capsule["owned_paths"]):
                        continue
                    binding = envelope.get("binding")
                    conflicts.append(
                        {
                            "kind": kind,
                            "assignment_id": capsule["assignment_id"],
                            "owned_paths": capsule["owned_paths"],
                            "parent_thread_id": capsule["parent_thread_id"],
                            "bound_child_thread_id": (
                                binding.get("child_thread_id")
                                if isinstance(binding, dict)
                                else None
                            ),
                        }
                    )

            unresolved_directory = self.root / "unresolved"
            if unresolved_directory.exists():
                for path in sorted(unresolved_directory.glob("*.json")):
                    try:
                        envelope = self._validated_envelope(path)
                    except CorruptState:
                        self._quarantine(path)
                        raise
                    capsule = envelope["capsule"]
                    if pathlib.Path(capsule["root"]["path"]).resolve() != canonical_root:
                        continue
                    if not _paths_overlap_case_safe(normalized_paths, capsule["owned_paths"]):
                        continue
                    barrier_path = self.path("quiescence", capsule["assignment_id"])
                    barrier = None
                    if barrier_path.exists():
                        try:
                            barrier = _validate_quiescence_barrier(self._read(barrier_path))
                        except CorruptState:
                            self._quarantine(barrier_path)
                            raise
                    parent_reclaim_is_exact = (
                        barrier is not None
                        and actor["runtime_session_id"] == capsule["runtime_session_id"]
                        and actor["thread_id"] == capsule["parent_thread_id"]
                        and barrier["snapshot_sha256"] == _snapshot_sha256(before_snapshot)
                    )
                    if parent_reclaim_is_exact:
                        ownership_handover.append(
                            {
                                "prior_assignment_id": capsule["assignment_id"],
                                "barrier_sha256": barrier["barrier_sha256"],
                                "snapshot_sha256": barrier["snapshot_sha256"],
                            }
                        )
                        continue
                    binding = envelope.get("binding")
                    conflicts.append(
                        {
                            "kind": "unresolved",
                            "assignment_id": capsule["assignment_id"],
                            "owned_paths": capsule["owned_paths"],
                            "parent_thread_id": capsule["parent_thread_id"],
                            "bound_child_thread_id": (
                                binding.get("child_thread_id")
                                if isinstance(binding, dict)
                                else None
                            ),
                        }
                    )

            if conflicts:
                conflict_id = str(uuid.uuid4())
                self._publish(
                    self.path("writer_conflict", conflict_id),
                    {
                        "schema": 1,
                        "classification": "foreign_actor_writer_lease_conflict",
                        "conflict_id": conflict_id,
                        "actor": dict(actor),
                        "root": str(canonical_root),
                        "paths": normalized_paths,
                        "tool_name": tool_name,
                        "tool_use_id": tool_use_id,
                        "conflicts": conflicts,
                        "observed_at": now.isoformat(),
                    },
                )
                raise AuthorityViolation(
                    "apply_patch paths overlap an existing child or foreign writer lease"
                )

            claim_id = str(uuid.uuid4())
            claim = {
                "schema": 1,
                "claim_id": claim_id,
                "actor": dict(actor),
                "root": str(canonical_root),
                "paths": normalized_paths,
                "tool_name": tool_name,
                "tool_use_id": tool_use_id,
                "created_at": now.isoformat(),
                "ownership_handover": ownership_handover,
                "before_snapshot": dict(before_snapshot),
                "before_snapshot_sha256": _snapshot_sha256(before_snapshot),
            }
            claim["claim_sha256"] = writer_claim_sha256(claim)
            _validate_writer_claim(claim)
            target = self.path("writer_claim", claim_id)
            self._publish(target, claim)
            return target

    def read_writer_claim(self, claim_id: str) -> dict:
        _uuid(claim_id, "writer_claim.claim_id")
        target = self.path("writer_claim", claim_id)
        with self.locked():
            if not target.exists():
                raise MissingState("writer claim does not exist")
            try:
                return _validate_writer_claim(self._read(target))
            except CorruptState:
                self._quarantine(target)
                raise

    def abort_unchanged_writer_claim(
        self,
        actor: Mapping[str, str],
        *,
        claim_id: str,
        after_snapshot: Mapping[str, object],
        recovery_reason: str,
        observed_at: dt.datetime | None = None,
    ) -> pathlib.Path:
        _validate_writer_actor(dict(actor))
        _uuid(claim_id, "writer_abort.claim_id")
        if recovery_reason != "missing_posttooluse_after_tool_failure":
            raise AuthorityViolation("writer abort recovery reason is not qualified")
        _validate_git_snapshot(dict(after_snapshot))
        now = observed_at or dt.datetime.now(dt.timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise StateError("writer abort time must include a UTC offset")

        claim_path = self.path("writer_claim", claim_id)
        with self.locked():
            if not claim_path.exists():
                raise MissingState("writer claim does not exist")
            try:
                claim = _validate_writer_claim(self._read(claim_path))
            except CorruptState:
                self._quarantine(claim_path)
                raise
            if claim["actor"] != dict(actor):
                raise AuthorityViolation("writer abort actor does not match claim")
            if pathlib.Path(after_snapshot["root"]).resolve() != pathlib.Path(claim["root"]):
                raise AuthorityViolation("writer abort snapshot root does not match claim")
            abort_schema = 2
            before_path_sha256 = writer_path_snapshot_sha256(
                claim["before_snapshot"], claim["paths"], schema=abort_schema
            )
            after_path_sha256 = writer_path_snapshot_sha256(
                after_snapshot, claim["paths"], schema=abort_schema
            )
            if after_path_sha256 != before_path_sha256:
                raise AuthorityViolation(
                    "writer abort requires every claimed path and Git frontier to be unchanged"
                )
            receipt = {
                "schema": abort_schema,
                "classification": "aborted_unchanged_after_missing_callback",
                "claim_id": claim["claim_id"],
                "claim_sha256": claim["claim_sha256"],
                "actor": dict(actor),
                "root": claim["root"],
                "paths": claim["paths"],
                "tool_name": claim["tool_name"],
                "tool_use_id": claim["tool_use_id"],
                "ownership_handover": claim["ownership_handover"],
                "before_snapshot_sha256": claim["before_snapshot_sha256"],
                "before_path_snapshot_sha256": before_path_sha256,
                "after_snapshot": dict(after_snapshot),
                "after_snapshot_sha256": _snapshot_sha256(after_snapshot),
                "after_path_snapshot_sha256": after_path_sha256,
                "recovery_reason": recovery_reason,
                "recovered_at": now.isoformat(),
            }
            receipt["abort_sha256"] = writer_abort_sha256(receipt)
            validate_writer_abort(receipt)
            target = self.path("writer_abort", claim["claim_id"])
            self._publish(target, receipt)
            claim_path.unlink()
            return target

    def release_writer_claim(
        self,
        actor: Mapping[str, str],
        *,
        tool_name: str,
        tool_use_id: str,
        after_snapshot: Mapping[str, object],
        observed_at: dt.datetime | None = None,
    ) -> pathlib.Path:
        _validate_writer_actor(dict(actor))
        if tool_name != "apply_patch":
            raise AuthorityViolation("writer release tool is not qualified")
        _nonempty_string(tool_use_id, "writer_release.tool_use_id")
        _validate_git_snapshot(dict(after_snapshot))
        now = observed_at or dt.datetime.now(dt.timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise StateError("writer release time must include a UTC offset")

        with self.locked():
            matches: list[tuple[pathlib.Path, dict]] = []
            directory = self.root / "writer_claim"
            if directory.exists():
                for path in sorted(directory.glob("*.json")):
                    try:
                        claim = _validate_writer_claim(self._read(path))
                    except CorruptState:
                        self._quarantine(path)
                        raise
                    if (
                        claim["actor"] == dict(actor)
                        and claim["tool_name"] == tool_name
                        and claim["tool_use_id"] == tool_use_id
                    ):
                        matches.append((path, claim))
            if not matches:
                raise MissingState("expected one in-flight writer claim, found 0")
            if len(matches) > 1:
                raise AmbiguousState(
                    f"expected one in-flight writer claim, found {len(matches)}"
                )
            claim_path, claim = matches[0]
            if pathlib.Path(after_snapshot["root"]).resolve() != pathlib.Path(claim["root"]):
                raise AuthorityViolation("writer release snapshot root does not match claim")
            receipt = {
                "schema": 1,
                "claim_id": claim["claim_id"],
                "claim_sha256": claim["claim_sha256"],
                "actor": dict(actor),
                "root": claim["root"],
                "paths": claim["paths"],
                "tool_name": tool_name,
                "tool_use_id": tool_use_id,
                "ownership_handover": claim["ownership_handover"],
                "before_snapshot_sha256": claim["before_snapshot_sha256"],
                "after_snapshot": dict(after_snapshot),
                "after_snapshot_sha256": _snapshot_sha256(after_snapshot),
                "released_at": now.isoformat(),
            }
            target = self.path("writer_receipt", claim["claim_id"])
            self._publish(target, receipt)
            claim_path.unlink()
            return target

    def terminate_active(
        self,
        assignment_id: str,
        termination_evidence: Mapping[str, object],
    ) -> pathlib.Path:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            envelope["termination_evidence"] = dict(termination_evidence)
            unresolved = self.path("unresolved", assignment_id)
            self._publish(unresolved, envelope)
            active.unlink()
            return unresolved

    def record_quiescence_barrier(
        self,
        prior_assignment_id: str,
        host_termination_receipt: Mapping[str, object],
        snapshot: Mapping[str, object],
        *,
        observed_at: dt.datetime | None = None,
    ) -> pathlib.Path:
        _uuid(prior_assignment_id, "prior_assignment_id")
        if set(host_termination_receipt) != {
            "receipt_id",
            "runtime_session_id",
            "child_thread_id",
            "guarantee",
            "terminated_at",
        }:
            raise StateError("host termination receipt fields are not exact")
        if host_termination_receipt["guarantee"] != "child_terminated_and_mutations_quiesced":
            raise AuthorityViolation("interrupt/cancel acknowledgement is not mutation quiescence")
        receipt_id = _nonempty_string(
            host_termination_receipt["receipt_id"],
            "host_termination_receipt.receipt_id",
        )
        runtime_session_id = _nonempty_string(
            host_termination_receipt["runtime_session_id"],
            "host_termination_receipt.runtime_session_id",
        )
        child_thread_id = _nonempty_string(
            host_termination_receipt["child_thread_id"],
            "host_termination_receipt.child_thread_id",
        )
        terminated_at = _timestamp(
            host_termination_receipt["terminated_at"],
            "host_termination_receipt.terminated_at",
        )
        barrier_observed_at = observed_at or dt.datetime.now(dt.timezone.utc)
        if barrier_observed_at.tzinfo is None or barrier_observed_at.utcoffset() is None:
            raise StateError("quiescence observation must include a UTC offset")
        if barrier_observed_at < terminated_at:
            raise StateError("quiescence observation predates child termination")
        unresolved = self.path("unresolved", prior_assignment_id)
        with self.locked():
            envelope = self._validated_envelope(unresolved)
            capsule = envelope["capsule"]
            binding = envelope.get("binding")
            if not isinstance(binding, dict):
                raise CorruptState("unresolved assignment has no child binding")
            if runtime_session_id != capsule["runtime_session_id"]:
                raise IdentityMismatch("termination receipt runtime session does not match")
            if child_thread_id != binding.get("child_thread_id"):
                raise IdentityMismatch("termination receipt child thread does not match")
            _validate_git_snapshot(snapshot)
            if pathlib.Path(snapshot["root"]).resolve() != pathlib.Path(
                capsule["root"]["path"]
            ).resolve():
                raise AuthorityViolation("quiescence snapshot root does not match assignment root")
            barrier = {
                "schema": 1,
                "prior_assignment_id": prior_assignment_id,
                "runtime_session_id": runtime_session_id,
                "terminated_child_thread_id": child_thread_id,
                "host_termination_receipt_id": receipt_id,
                "host_guarantee": host_termination_receipt["guarantee"],
                "terminated_at": terminated_at.isoformat(),
                "observed_at": barrier_observed_at.isoformat(),
                "snapshot": dict(snapshot),
                "snapshot_sha256": _snapshot_sha256(snapshot),
            }
            barrier["barrier_sha256"] = quiescence_barrier_sha256(barrier)
            _validate_quiescence_barrier(barrier)
            target = self.path("quiescence", prior_assignment_id)
            self._publish(target, barrier)
            return target

    def _resolve_ownership_handover_locked(
        self,
        owned_paths: Sequence[str],
        snapshot: Mapping[str, object],
        *,
        observed_at: dt.datetime,
        require_quiet_root: bool = False,
    ) -> list[dict]:
        current_snapshot_sha256 = _snapshot_sha256(snapshot)
        handovers = []
        claims_directory = self.root / "writer_claim"
        if claims_directory.exists():
            for path in sorted(claims_directory.glob("*.json")):
                try:
                    claim = _validate_writer_claim(self._read(path))
                except CorruptState:
                    self._quarantine(path)
                    raise
                if pathlib.Path(claim["root"]).resolve() != pathlib.Path(snapshot["root"]).resolve():
                    continue
                if require_quiet_root or _paths_overlap_case_safe(owned_paths, claim["paths"]):
                    raise AuthorityViolation(
                        "assignment capture overlaps an in-flight parent or sibling writer claim"
                    )
        for kind in ("pending", "claimed", "active", "reported"):
            directory = self.root / kind
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.json")):
                try:
                    envelope = self._validated_envelope(path)
                except CorruptState:
                    self._quarantine(path)
                    raise
                prior = envelope["capsule"]
                if _paths_overlap(owned_paths, prior["owned_paths"]):
                    raise AuthorityViolation(
                        f"owned paths overlap non-quiesced {kind} assignment {prior['assignment_id']}"
                    )

        unresolved_directory = self.root / "unresolved"
        if not unresolved_directory.exists():
            return handovers
        for path in sorted(unresolved_directory.glob("*.json")):
            try:
                envelope = self._validated_envelope(path)
            except CorruptState:
                self._quarantine(path)
                raise
            prior = envelope["capsule"]
            if not _paths_overlap(owned_paths, prior["owned_paths"]):
                continue
            barrier_path = self.path("quiescence", prior["assignment_id"])
            if not barrier_path.exists():
                raise AuthorityViolation(
                    "overlapping assignment has no host termination and disk quiescence barrier"
                )
            try:
                barrier = _validate_quiescence_barrier(self._read(barrier_path))
            except CorruptState:
                self._quarantine(barrier_path)
                raise
            if barrier["snapshot_sha256"] != current_snapshot_sha256:
                overlap = {
                    "schema": 1,
                    "classifications": [
                        "late_mutation_after_interrupt",
                        "overlapping_assignment_provenance",
                    ],
                    "prior_assignment_id": prior["assignment_id"],
                    "owned_paths": list(owned_paths),
                    "barrier_sha256": barrier["barrier_sha256"],
                    "barrier_snapshot_sha256": barrier["snapshot_sha256"],
                    "current_snapshot_sha256": current_snapshot_sha256,
                    "observed_at": observed_at.isoformat(),
                }
                self._publish(
                    self.path("overlap", str(uuid.uuid4())),
                    overlap,
                )
                raise AuthorityViolation(
                    "late mutation after termination barrier creates overlapping assignment provenance"
                )
            handovers.append(
                {
                    "prior_assignment_id": prior["assignment_id"],
                    "barrier_sha256": barrier["barrier_sha256"],
                    "snapshot_sha256": barrier["snapshot_sha256"],
                }
            )
        return handovers

    def resolve_ownership_handover(
        self,
        owned_paths: Sequence[str],
        snapshot: Mapping[str, object],
        *,
        observed_at: dt.datetime | None = None,
        require_quiet_root: bool = False,
    ) -> list[dict]:
        _relative_paths(list(owned_paths), "owned_paths")
        now = observed_at or dt.datetime.now(dt.timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise StateError("ownership handover observation must include a UTC offset")
        with self.locked():
            return self._resolve_ownership_handover_locked(
                owned_paths,
                snapshot,
                observed_at=now,
                require_quiet_root=require_quiet_root,
            )

    def stage_with_ownership_recheck(
        self,
        capsule: dict,
        assignment: str,
        snapshot: Mapping[str, object],
        *,
        observed_at: dt.datetime,
    ) -> pathlib.Path:
        validate_capsule(capsule, assignment)
        if _timestamp(capsule["expires_at"], "expires_at") <= dt.datetime.now(dt.timezone.utc):
            raise StateError("refusing to stage an expired capsule")
        with self.locked():
            handover = self._resolve_ownership_handover_locked(
                capsule["owned_paths"],
                snapshot,
                observed_at=observed_at,
                require_quiet_root=(
                    capsule["execution_contract"]["posture"] == "strict_read_only"
                ),
            )
            if handover != capsule["ownership_handover"]:
                raise AuthorityViolation("ownership handover changed before atomic staging")
            if _snapshot_sha256(snapshot) != capsule["capture_snapshot_sha256"]:
                raise AuthorityViolation("capture snapshot changed before atomic staging")
            target = self.path("pending", capsule["handoff_id"])
            self._publish(
                target,
                {"schema": SCHEMA, "capsule": capsule, "assignment": assignment},
            )
            return target

    def expire_active(self, assignment_id: str, *, now: dt.datetime) -> pathlib.Path | None:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            expires_at = _timestamp(envelope["capsule"]["expires_at"], "expires_at")
            if expires_at > now:
                return None
            unresolved = self.path("unresolved", assignment_id)
            self._publish(unresolved, envelope)
            active.unlink()
            return unresolved

    def find_active(self, identity: Mapping[str, str]) -> tuple[str, dict]:
        matches: list[tuple[str, dict]] = []
        with self.locked():
            active_directory = self.root / "active"
            if not active_directory.exists():
                raise MissingState("expected one active authority capsule, found 0")
            for path in sorted(active_directory.glob("*.json")):
                try:
                    envelope = self._validated_envelope(path)
                except CorruptState:
                    self._quarantine(path)
                    continue
                try:
                    self._assert_identity(
                        envelope["capsule"], identity, envelope.get("binding")
                    )
                except IdentityMismatch:
                    continue
                matches.append((envelope["capsule"]["assignment_id"], envelope))
            if not matches:
                raise MissingState("expected one active authority capsule, found 0")
            if len(matches) > 1:
                raise AmbiguousState(
                    f"expected one active authority capsule, found {len(matches)}"
                )
            return matches[0]

    def finalize(
        self,
        assignment_id: str,
        attestation: Mapping[str, object],
        *,
        complete: bool,
    ) -> pathlib.Path:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            envelope["final_attestation"] = dict(attestation)
            disposition = "reported" if complete else "unresolved"
            final = self.path(disposition, assignment_id)
            self._publish(final, envelope)
            active.unlink()
            return final

    def adjudicate_parent(
        self,
        assignment_id: str,
        adjudication: Mapping[str, object],
    ) -> pathlib.Path:
        """Promote a report only from the trusted parent integration boundary."""
        if not isinstance(adjudication, Mapping) or set(adjudication) != PARENT_ADJUDICATION_FIELDS:
            raise StateError("parent adjudication fields are not exact")
        integrity_fields = PARENT_ADJUDICATION_FIELDS - {"evidence_sha256"}
        for field in integrity_fields:
            if adjudication[field] not in {"pass", "fail", "unverified"}:
                raise StateError(f"parent adjudication {field} is invalid")
        evidence_sha256 = adjudication["evidence_sha256"]
        if not isinstance(evidence_sha256, str) or not SHA256_RE.fullmatch(evidence_sha256):
            raise StateError("parent adjudication evidence_sha256 is invalid")
        reported = self.path("reported", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(reported)
            envelope["parent_adjudication"] = dict(adjudication)
            complete = all(adjudication[field] == "pass" for field in integrity_fields)
            final = self.path("consumed" if complete else "unresolved", assignment_id)
            self._publish(final, envelope)
            reported.unlink()
            return final

    def record_context_lost(
        self,
        identity: Mapping[str, str],
        reason: str,
    ) -> pathlib.Path:
        if not reason.strip():
            raise StateError("context-lost reason must not be blank")
        marker_id = sha256_bytes(canonical_json(dict(identity)))
        target = self.path("lost", marker_id)
        marker = {
            "schema": 1,
            "identity": dict(identity),
            "reason": reason,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        with self.locked():
            self._publish(target, marker, replace=True)
        return target

    def context_lost_for(self, identity: Mapping[str, str]) -> dict | None:
        marker_id = sha256_bytes(canonical_json(dict(identity)))
        target = self.path("lost", marker_id)
        with self.locked():
            if not target.exists():
                return None
            marker = self._read(target)
            if (
                marker.get("schema") != 1
                or marker.get("identity") != dict(identity)
                or not isinstance(marker.get("reason"), str)
                or not marker["reason"].strip()
            ):
                self._quarantine(target)
                raise CorruptState("context-lost marker is invalid")
            return marker

    @staticmethod
    def _assert_identity(
        capsule: Mapping[str, object],
        identity: Mapping[str, str],
        binding: object | None = None,
    ) -> None:
        runtime_session_id = identity.get("runtime_session_id")
        child_thread_id = identity.get("child_thread_id")
        if not runtime_session_id:
            raise IdentityMismatch("runtime session id is missing")
        if not child_thread_id or child_thread_id != identity.get("agent_id"):
            raise IdentityMismatch("child thread id and agent_id do not match")
        if runtime_session_id != capsule["runtime_session_id"]:
            raise IdentityMismatch("runtime session does not match")
        if identity.get("parent_thread_id") != capsule["parent_thread_id"]:
            raise IdentityMismatch("direct parent thread does not match")
        if identity.get("agent_type") != capsule["agent_type"]:
            raise IdentityMismatch("agent type does not match")
        canonical = identity.get("canonical_agent_path")
        if not canonical or canonical.rstrip("/").split("/")[-1] != capsule["requested_task_name"]:
            raise IdentityMismatch("canonical AgentPath does not match requested task name")
        expected_canonical = capsule.get("canonical_agent_path")
        if expected_canonical is not None and canonical != expected_canonical:
            raise IdentityMismatch("canonical AgentPath does not match the capsule")
        if binding is not None and dict(identity) != binding:
            raise IdentityMismatch("child identity does not match the active binding")
