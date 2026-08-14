#!/usr/bin/env python3

"""Parent-owned pre-dispatch feasibility attestation fixture."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from compatibility_state import canonical_json, sha256_bytes


class FeasibilityViolation(RuntimeError):
    pass


def _receipt_sha256(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeasibilityViolation(f"{name} must be a non-empty string")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise FeasibilityViolation(f"{name} must be a non-negative integer")
    return value


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
    derive_equivalence_compression: Callable[
        [object, str], Mapping[str, object] | None
    ],
) -> dict:
    """Invoke owner callbacks; callers cannot inject precomputed derived outcomes."""
    if not isinstance(work_budget, Mapping) or set(work_budget) != {
        "unit",
        "cardinality_domain",
        "limit",
    }:
        raise FeasibilityViolation("work budget fields are not exact")
    budget_unit = _nonempty_string(work_budget["unit"], "work budget unit")
    budget_domain = _nonempty_string(
        work_budget["cardinality_domain"], "work budget cardinality_domain"
    )
    budget_limit = work_budget["limit"]
    if type(budget_limit) not in {int, float} or budget_limit <= 0:
        raise FeasibilityViolation("work budget limit must be positive")

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
        "mechanism_measurement",
        "scale_evidence",
        "evidence",
    }:
        raise FeasibilityViolation("bounded completion result fields are not exact")

    measurement = bounded_result["mechanism_measurement"]
    if not isinstance(measurement, Mapping) or set(measurement) != {
        "unit",
        "cardinality_domain",
        "required_lower_bound",
    }:
        raise FeasibilityViolation("mechanism measurement fields are not exact")
    measurement_unit = _nonempty_string(measurement["unit"], "mechanism measurement unit")
    measurement_domain = _nonempty_string(
        measurement["cardinality_domain"], "mechanism measurement cardinality_domain"
    )
    required_lower_bound = _nonnegative_integer(
        measurement["required_lower_bound"], "required invocation lower bound"
    )

    scale = bounded_result["scale_evidence"]
    if not isinstance(scale, Mapping) or set(scale) != {"basis", "witness_input", "evidence"}:
        raise FeasibilityViolation("scale evidence fields are not exact")
    if scale["basis"] not in {"proven_monotonicity", "adversarial_scale_witness"}:
        raise FeasibilityViolation("scale evidence basis is invalid")
    if scale["basis"] == "adversarial_scale_witness" and scale["witness_input"] is None:
        raise FeasibilityViolation("adversarial scale witness input is required")
    if scale["basis"] == "proven_monotonicity" and scale["witness_input"] is not None:
        raise FeasibilityViolation("monotonicity evidence cannot masquerade as a scale witness")

    compression = derive_equivalence_compression(probe_input, proposed_mechanism)
    normalized_compression = None
    compression_valid = True
    if compression is not None:
        if not isinstance(compression, Mapping) or set(compression) != {
            "equivalence_rule",
            "class_cardinality_domain",
            "identity_cardinality_domain",
            "evaluated_class_count",
            "proven_identity_count",
            "fanout_identity_count",
            "evidence",
        }:
            raise FeasibilityViolation("equivalence compression fields are not exact")
        for field in (
            "equivalence_rule",
            "class_cardinality_domain",
            "identity_cardinality_domain",
        ):
            _nonempty_string(compression[field], f"equivalence compression {field}")
        evaluated_class_count = _nonnegative_integer(
            compression["evaluated_class_count"], "evaluated class count"
        )
        proven_identity_count = _nonnegative_integer(
            compression["proven_identity_count"], "proven identity count"
        )
        fanout_identity_count = _nonnegative_integer(
            compression["fanout_identity_count"], "fan-out identity count"
        )
        compression_valid = all(
            (
                compression["class_cardinality_domain"] == measurement_domain,
                evaluated_class_count <= proven_identity_count,
                fanout_identity_count == proven_identity_count,
                required_lower_bound >= evaluated_class_count,
            )
        )
        normalized_compression = {
            "authoritative_owner_id": parent_owner_id,
            "grouping_origin": "owner_derived",
            **{key: value for key, value in compression.items() if key != "evidence"},
            "evidence_sha256": _receipt_sha256(compression["evidence"]),
        }

    mechanism_satisfies = all(
        (
            measurement_unit == budget_unit,
            measurement_domain == budget_domain,
            required_lower_bound <= budget_limit,
            compression_valid,
        )
    )
    normalized_assumptions = [dict(item) for item in unresolved_assumptions]
    blocking = any(item.get("blocking") is True for item in normalized_assumptions)
    dispatchable = (
        not probe_result["counterexample_found"]
        and mechanism_satisfies
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
            "mechanism_measurement": dict(measurement),
            "scale_evidence": {
                "basis": scale["basis"],
                "witness_input_sha256": (
                    None
                    if scale["witness_input"] is None
                    else _receipt_sha256(scale["witness_input"])
                ),
                "evidence_sha256": _receipt_sha256(scale["evidence"]),
            },
            "equivalence_compression": normalized_compression,
            "mechanism_satisfies": mechanism_satisfies,
            "evidence_sha256": _receipt_sha256(bounded_result["evidence"]),
        },
        "unresolved_assumptions": normalized_assumptions,
        "owner_decision": "dispatch" if dispatchable else "block",
    }
