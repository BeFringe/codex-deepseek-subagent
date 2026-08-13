#!/usr/bin/env python3

"""Parent-owned pre-dispatch feasibility attestation fixture."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from compatibility_state import canonical_json, sha256_bytes


class FeasibilityViolation(RuntimeError):
    pass


def _receipt_sha256(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def build_parent_feasibility_attestation(
    *,
    parent_owner_id: str,
    exact_claimed_invariant: str,
    probe_id: str,
    probe_input: object,
    completion_condition: str,
    work_budget: Mapping[str, object],
    proposed_mechanism: str,
    unresolved_assumptions: Sequence[Mapping[str, object]],
    run_counterexample_probe: Callable[[object], Mapping[str, object]],
    assess_bounded_completion: Callable[[str, Mapping[str, object]], Mapping[str, object]],
) -> dict:
    """Invoke owner callbacks; callers cannot inject precomputed derived outcomes."""
    probe_result = run_counterexample_probe(probe_input)
    if not isinstance(probe_result, Mapping) or set(probe_result) != {
        "counterexample_found",
        "evidence",
    }:
        raise FeasibilityViolation("counterexample probe result fields are not exact")
    if type(probe_result["counterexample_found"]) is not bool:
        raise FeasibilityViolation("counterexample probe outcome is invalid")
    bounded_result = assess_bounded_completion(proposed_mechanism, work_budget)
    if not isinstance(bounded_result, Mapping) or set(bounded_result) != {
        "mechanism_satisfies",
        "evidence",
    }:
        raise FeasibilityViolation("bounded completion result fields are not exact")
    if type(bounded_result["mechanism_satisfies"]) is not bool:
        raise FeasibilityViolation("bounded completion outcome is invalid")
    normalized_assumptions = [dict(item) for item in unresolved_assumptions]
    blocking = any(item.get("blocking") is True for item in normalized_assumptions)
    dispatchable = (
        not probe_result["counterexample_found"]
        and bounded_result["mechanism_satisfies"]
        and not blocking
    )
    return {
        "parent_owner_id": parent_owner_id,
        "exact_claimed_invariant": exact_claimed_invariant,
        "counterexample_probe": {
            "probe_id": probe_id,
            "probe_input_sha256": _receipt_sha256(probe_input),
            "executed": True,
            "counterexample_found": probe_result["counterexample_found"],
            "evidence_sha256": _receipt_sha256(probe_result["evidence"]),
        },
        "bounded_completion": {
            "completion_condition": completion_condition,
            "work_budget": dict(work_budget),
            "proposed_mechanism": proposed_mechanism,
            "mechanism_satisfies": bounded_result["mechanism_satisfies"],
            "evidence_sha256": _receipt_sha256(bounded_result["evidence"]),
        },
        "unresolved_assumptions": normalized_assumptions,
        "owner_decision": "dispatch" if dispatchable else "block",
    }
