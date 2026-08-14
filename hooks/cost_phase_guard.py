#!/usr/bin/env python3

"""Provider-free owner fixture for end-to-end cost and phase continuity."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
import math

from compatibility_state import canonical_json, sha256_bytes


class CostPhaseViolation(RuntimeError):
    pass


def _receipt_sha256(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def _exact_mapping(value: object, fields: set[str], name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CostPhaseViolation(f"{name} fields are not exact")
    return value


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CostPhaseViolation(f"{name} must be a non-empty string")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise CostPhaseViolation(f"{name} must be a non-negative integer")
    return value


def _positive_number(value: object, name: str) -> int | float:
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise CostPhaseViolation(f"{name} must be a positive finite number")
    return value


def _nonnegative_number(value: object, name: str) -> int | float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise CostPhaseViolation(f"{name} must be a non-negative finite number")
    return value


def _string_list(value: object, name: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise CostPhaseViolation(f"{name} must be a{' non-empty' if nonempty else ''} list")
    for item in value:
        _nonempty_string(item, f"{name} item")
    if len(set(value)) != len(value):
        raise CostPhaseViolation(f"{name} contains duplicate identities")
    return list(value)


def registry_identity(item_ids: Sequence[str]) -> str:
    """Return the canonical, order-sensitive identity for a frozen registry."""
    return _receipt_sha256(list(item_ids))


def nearest_rank_p95(samples: Sequence[int | float]) -> int | float:
    """Compute p95 using the frozen nearest-rank definition."""
    if not samples:
        raise CostPhaseViolation("latency samples must not be empty")
    normalized = []
    for sample in samples:
        if type(sample) not in {int, float} or not math.isfinite(sample) or sample < 0:
            raise CostPhaseViolation("latency sample must be a non-negative finite number")
        normalized.append(sample)
    normalized.sort()
    rank = math.ceil(0.95 * len(normalized))
    return normalized[rank - 1]


def _validate_edges(
    edges_value: object,
    input_ids: list[str],
    output_ids: list[str],
    name: str,
) -> list[dict[str, str]]:
    if not isinstance(edges_value, list):
        raise CostPhaseViolation(f"{name} must be a list")
    edges = []
    for index, edge_value in enumerate(edges_value):
        edge = _exact_mapping(
            edge_value,
            {"input_id", "output_id"},
            f"{name}[{index}]",
        )
        input_id = _nonempty_string(edge["input_id"], f"{name} input_id")
        output_id = _nonempty_string(edge["output_id"], f"{name} output_id")
        edges.append({"input_id": input_id, "output_id": output_id})
    if len({(edge["input_id"], edge["output_id"]) for edge in edges}) != len(edges):
        raise CostPhaseViolation(f"{name} contains duplicate edges")
    input_counts = Counter(edge["input_id"] for edge in edges)
    output_counts = Counter(edge["output_id"] for edge in edges)
    if set(input_counts) != set(input_ids):
        raise CostPhaseViolation(f"{name} has a missing or orphaned input identity")
    if set(output_counts) != set(output_ids) or any(count != 1 for count in output_counts.values()):
        raise CostPhaseViolation(f"{name} has a missing, duplicate, or orphaned output identity")
    return edges


def _validate_contract(value: object) -> dict:
    contract = _exact_mapping(
        value,
        {
            "invocation_authority",
            "latency_authority",
            "completion_condition",
            "source_root",
            "root_identity",
            "authority_epoch",
            "refinement_set_identity",
            "phase_catalog",
        },
        "cost phase contract",
    )
    invocation = _exact_mapping(
        contract["invocation_authority"],
        {"unit", "cardinality_domain", "limit"},
        "invocation authority",
    )
    invocation = {
        "unit": _nonempty_string(invocation["unit"], "invocation unit"),
        "cardinality_domain": _nonempty_string(
            invocation["cardinality_domain"], "invocation cardinality domain"
        ),
        "limit": _positive_number(invocation["limit"], "invocation limit"),
    }
    latency = _exact_mapping(
        contract["latency_authority"],
        {
            "unit",
            "statistic",
            "limit",
            "sample_count",
            "sample_definition",
            "window_definition",
            "multiplicity_distribution_identity",
            "equivalence_class_distribution_identity",
            "representative_scope",
        },
        "latency authority",
    )
    if latency["statistic"] != "p95_nearest_rank":
        raise CostPhaseViolation("latency statistic must be p95_nearest_rank")
    if type(latency["sample_count"]) is not int or latency["sample_count"] <= 0:
        raise CostPhaseViolation("latency sample_count must be a positive integer")
    latency = {
        "unit": _nonempty_string(latency["unit"], "latency unit"),
        "statistic": latency["statistic"],
        "limit": _positive_number(latency["limit"], "latency limit"),
        "sample_count": latency["sample_count"],
        "sample_definition": _nonempty_string(
            latency["sample_definition"], "latency sample definition"
        ),
        "window_definition": _nonempty_string(
            latency["window_definition"], "latency window definition"
        ),
        "multiplicity_distribution_identity": _nonempty_string(
            latency["multiplicity_distribution_identity"],
            "latency multiplicity distribution identity",
        ),
        "equivalence_class_distribution_identity": _nonempty_string(
            latency["equivalence_class_distribution_identity"],
            "latency equivalence-class distribution identity",
        ),
        "representative_scope": _nonempty_string(
            latency["representative_scope"], "latency representative scope"
        ),
    }
    if latency["representative_scope"] != "representative_dense":
        raise CostPhaseViolation("frozen latency scope must be representative_dense")

    phase_values = contract["phase_catalog"]
    if not isinstance(phase_values, list) or len(phase_values) != 3:
        raise CostPhaseViolation("phase catalog must contain coarse, refine, and materialize")
    phases = []
    for index, phase_value in enumerate(phase_values):
        phase = _exact_mapping(
            phase_value,
            {
                "phase_id",
                "kind",
                "input_item_ids",
                "output_item_ids",
                "input_identity",
                "output_identity",
                "conservation_edges",
                "timing_unit",
                "timing_limit",
                "timing_definition",
            },
            f"phase catalog[{index}]",
        )
        input_ids = _string_list(
            phase["input_item_ids"], f"phase catalog[{index}] input ids", nonempty=True
        )
        output_ids = _string_list(
            phase["output_item_ids"], f"phase catalog[{index}] output ids", nonempty=True
        )
        edges = _validate_edges(
            phase["conservation_edges"],
            input_ids,
            output_ids,
            f"phase catalog[{index}] conservation edges",
        )
        normalized = {
            "phase_id": _nonempty_string(phase["phase_id"], "phase id"),
            "kind": phase["kind"],
            "input_item_ids": input_ids,
            "output_item_ids": output_ids,
            "input_identity": _nonempty_string(phase["input_identity"], "phase input identity"),
            "output_identity": _nonempty_string(
                phase["output_identity"], "phase output identity"
            ),
            "conservation_edges": edges,
            "timing_unit": _nonempty_string(phase["timing_unit"], "phase timing unit"),
            "timing_limit": _positive_number(phase["timing_limit"], "phase timing limit"),
            "timing_definition": _nonempty_string(
                phase["timing_definition"], "phase timing definition"
            ),
        }
        if normalized["input_identity"] != registry_identity(input_ids):
            raise CostPhaseViolation("phase input identity does not match its frozen registry")
        if normalized["output_identity"] != registry_identity(output_ids):
            raise CostPhaseViolation("phase output identity does not match its frozen registry")
        phases.append(normalized)
    if [phase["kind"] for phase in phases] != ["coarse", "refine", "materialize"]:
        raise CostPhaseViolation("phase kinds or order are not exact")
    if len({phase["phase_id"] for phase in phases}) != len(phases):
        raise CostPhaseViolation("phase ids must be unique")
    for prior, current in zip(phases, phases[1:]):
        if prior["output_item_ids"] != current["input_item_ids"]:
            raise CostPhaseViolation("cross-phase registry conservation failed")
        if prior["output_identity"] != current["input_identity"]:
            raise CostPhaseViolation("cross-phase identity conservation failed")

    return {
        "invocation_authority": invocation,
        "latency_authority": latency,
        "completion_condition": _nonempty_string(
            contract["completion_condition"], "completion condition"
        ),
        "source_root": _nonempty_string(contract["source_root"], "source root"),
        "root_identity": _nonempty_string(contract["root_identity"], "root identity"),
        "authority_epoch": _nonempty_string(contract["authority_epoch"], "authority epoch"),
        "refinement_set_identity": _nonempty_string(
            contract["refinement_set_identity"], "refinement set identity"
        ),
        "phase_catalog": phases,
    }


def _observe_seam(
    observer: Callable[[str, Mapping[str, object]], Mapping[str, object]],
    seam: str,
    contract: Mapping[str, object],
) -> dict:
    observed = _exact_mapping(
        observer(seam, contract),
        {"seam", "source_root", "root_identity", "authority_epoch", "mutation_detected", "evidence"},
        f"mutation observation {seam}",
    )
    if type(observed["mutation_detected"]) is not bool:
        raise CostPhaseViolation("mutation_detected must be a boolean")
    binding_satisfies = all(
        (
            observed["seam"] == seam,
            observed["source_root"] == contract["source_root"],
            observed["root_identity"] == contract["root_identity"],
            observed["authority_epoch"] == contract["authority_epoch"],
            not observed["mutation_detected"],
        )
    )
    return {
        "seam": seam,
        "binding_satisfies": binding_satisfies,
        "mutation_detected": observed["mutation_detected"],
        "evidence_sha256": _receipt_sha256(observed["evidence"]),
    }


def _frontier(value: object, name: str) -> tuple[list[dict], str]:
    result = _exact_mapping(value, {"items", "evidence"}, name)
    if not isinstance(result["items"], list):
        raise CostPhaseViolation(f"{name} items must be a list")
    items = []
    for index, item_value in enumerate(result["items"]):
        item = _exact_mapping(item_value, {"identity", "payload"}, f"{name} item[{index}]")
        items.append(
            {
                "identity": _nonempty_string(
                    item["identity"], f"{name} item[{index}] identity"
                ),
                "payload": item["payload"],
            }
        )
    if len({item["identity"] for item in items}) != len(items):
        raise CostPhaseViolation(f"{name} contains duplicate identities")
    return items, _receipt_sha256(result["evidence"])


def build_end_to_end_cost_phase_attestation(
    *,
    parent_owner_id: str,
    frozen_contract: Mapping[str, object],
    measure_invocations: Callable[[Mapping[str, object]], Mapping[str, object]],
    sample_dense_latency: Callable[[Mapping[str, object]], Mapping[str, object]],
    observe_mutation: Callable[[str, Mapping[str, object]], Mapping[str, object]],
    run_phase: Callable[
        [Mapping[str, object], Sequence[str], Callable[[], None]], Mapping[str, object]
    ],
    compute_authoritative_frontier: Callable[[Mapping[str, object]], Mapping[str, object]],
    materialize_final_frontier: Callable[
        [Mapping[str, object], Mapping[str, object]], Mapping[str, object]
    ],
) -> dict:
    """Execute owner callbacks and compute every P6c decision inside the guard."""
    owner_id = _nonempty_string(parent_owner_id, "parent owner id")
    contract = _validate_contract(frozen_contract)

    invocation = _exact_mapping(
        measure_invocations(contract),
        {"unit", "cardinality_domain", "observed", "evidence"},
        "invocation measurement",
    )
    observed_invocations = _nonnegative_integer(
        invocation["observed"], "observed invocation count"
    )
    invocation_satisfies = all(
        (
            invocation["unit"] == contract["invocation_authority"]["unit"],
            invocation["cardinality_domain"]
            == contract["invocation_authority"]["cardinality_domain"],
            observed_invocations <= contract["invocation_authority"]["limit"],
        )
    )

    latency = _exact_mapping(
        sample_dense_latency(contract),
        {
            "scope",
            "unit",
            "sample_definition",
            "window_definition",
            "multiplicity_distribution_identity",
            "equivalence_class_distribution_identity",
            "samples",
            "evidence",
        },
        "latency measurement",
    )
    if not isinstance(latency["samples"], list):
        raise CostPhaseViolation("latency samples must be a list")
    p95 = nearest_rank_p95(latency["samples"])
    latency_authority = contract["latency_authority"]
    latency_definition_satisfies = all(
        (
            latency["scope"] == latency_authority["representative_scope"],
            latency["unit"] == latency_authority["unit"],
            latency["sample_definition"] == latency_authority["sample_definition"],
            latency["window_definition"] == latency_authority["window_definition"],
            latency["multiplicity_distribution_identity"]
            == latency_authority["multiplicity_distribution_identity"],
            latency["equivalence_class_distribution_identity"]
            == latency_authority["equivalence_class_distribution_identity"],
            len(latency["samples"]) == latency_authority["sample_count"],
        )
    )
    latency_satisfies = latency_definition_satisfies and p95 <= latency_authority["limit"]

    seam_receipts = []
    phase_receipts = []
    phase_results = []
    current_ids = list(contract["phase_catalog"][0]["input_item_ids"])
    for phase in contract["phase_catalog"]:
        before_seam = f"before:{phase['phase_id']}"
        mid_seam = f"mid:{phase['phase_id']}"
        after_seam = f"after:{phase['phase_id']}"
        seam_receipts.append(_observe_seam(observe_mutation, before_seam, contract))
        mid_receipts = []

        def observe_mid() -> None:
            mid_receipts.append(_observe_seam(observe_mutation, mid_seam, contract))

        result = _exact_mapping(
            run_phase(phase, tuple(current_ids), observe_mid),
            {
                "phase_id",
                "input_item_ids",
                "output_item_ids",
                "input_identity",
                "output_identity",
                "source_root",
                "root_identity",
                "authority_epoch",
                "conservation_edges",
                "bound",
                "refinement_ids",
                "refinement_reductions",
                "true_cardinality",
                "timing_unit",
                "timing_definition",
                "elapsed",
                "evidence",
            },
            f"phase result {phase['phase_id']}",
        )
        if len(mid_receipts) != 1:
            raise CostPhaseViolation(
                f"phase {phase['phase_id']} must expose exactly one internal mutation seam"
            )
        seam_receipts.extend(mid_receipts)
        seam_receipts.append(_observe_seam(observe_mutation, after_seam, contract))

        result_input_ids = _string_list(result["input_item_ids"], "phase result input ids")
        result_output_ids = _string_list(result["output_item_ids"], "phase result output ids")
        result_edges = _validate_edges(
            result["conservation_edges"],
            result_input_ids,
            result_output_ids,
            "phase result conservation edges",
        )
        bound = _nonnegative_integer(result["bound"], "phase bound")
        refinement_ids = _string_list(result["refinement_ids"], "refinement ids")
        if not isinstance(result["refinement_reductions"], list):
            raise CostPhaseViolation("refinement reductions must be a list")
        reductions = []
        for reduction_value in result["refinement_reductions"]:
            reduction = _exact_mapping(
                reduction_value,
                {"refinement_id", "reduction"},
                "refinement reduction",
            )
            reductions.append(
                {
                    "refinement_id": _nonempty_string(
                        reduction["refinement_id"], "refinement reduction id"
                    ),
                    "reduction": _nonnegative_integer(
                        reduction["reduction"], "refinement reduction amount"
                    ),
                }
            )
        true_cardinality = result["true_cardinality"]
        if true_cardinality is not None:
            true_cardinality = _nonnegative_integer(true_cardinality, "true cardinality")
        elapsed = _nonnegative_number(result["elapsed"], "phase elapsed time")
        binding_satisfies = all(
            (
                result["phase_id"] == phase["phase_id"],
                result_input_ids == phase["input_item_ids"],
                result_output_ids == phase["output_item_ids"],
                result["input_identity"] == phase["input_identity"],
                result["output_identity"] == phase["output_identity"],
                result["source_root"] == contract["source_root"],
                result["root_identity"] == contract["root_identity"],
                result["authority_epoch"] == contract["authority_epoch"],
                result_edges == phase["conservation_edges"],
            )
        )
        timing_satisfies = all(
            (
                result["timing_unit"] == phase["timing_unit"],
                result["timing_definition"] == phase["timing_definition"],
                elapsed <= phase["timing_limit"],
            )
        )
        phase_receipts.append(
            {
                "phase_id": phase["phase_id"],
                "kind": phase["kind"],
                "binding_satisfies": binding_satisfies,
                "input_identity": phase["input_identity"],
                "output_identity": phase["output_identity"],
                "bound": bound,
                "refinement_ids": refinement_ids,
                "refinement_reductions": reductions,
                "true_cardinality": true_cardinality,
                "timing_unit": phase["timing_unit"],
                "timing_limit": phase["timing_limit"],
                "timing_definition": phase["timing_definition"],
                "elapsed": elapsed,
                "timing_satisfies": timing_satisfies,
                "evidence_sha256": _receipt_sha256(result["evidence"]),
            }
        )
        phase_results.append(
            {
                **dict(result),
                "input_item_ids": result_input_ids,
                "output_item_ids": result_output_ids,
                "conservation_edges": result_edges,
                "bound": bound,
                "refinement_ids": refinement_ids,
                "refinement_reductions": reductions,
                "true_cardinality": true_cardinality,
                "elapsed": elapsed,
            }
        )
        current_ids = result_output_ids

    coarse, refine, materialize = phase_receipts
    refinement_ids = refine["refinement_ids"]
    reductions = refine["refinement_reductions"]
    refinement_equation_satisfies = all(
        (
            [item["refinement_id"] for item in reductions] == refinement_ids,
            registry_identity(refinement_ids) == contract["refinement_set_identity"],
            refine["bound"]
            == coarse["bound"] - sum(item["reduction"] for item in reductions),
            materialize["bound"] == refine["bound"],
            coarse["true_cardinality"] is None,
            refine["true_cardinality"] is None,
            materialize["true_cardinality"] is not None,
        )
    )
    if materialize["true_cardinality"] is not None:
        refinement_equation_satisfies = (
            refinement_equation_satisfies
            and materialize["true_cardinality"] <= refine["bound"] <= coarse["bound"]
        )

    authoritative_items, authoritative_evidence = _frontier(
        compute_authoritative_frontier(contract), "authoritative frontier"
    )
    materialized_items, materialized_evidence = _frontier(
        materialize_final_frontier(phase_results[-1], contract), "materialized frontier"
    )
    seam_receipts.append(
        _observe_seam(observe_mutation, "after:final_materialization", contract)
    )
    authoritative_ids = [item["identity"] for item in authoritative_items]
    materialized_ids = [item["identity"] for item in materialized_items]
    frontier = {
        "authoritative_count": len(authoritative_items),
        "materialized_count": len(materialized_items),
        "cardinality_matches": len(materialized_items) == len(authoritative_items),
        "canonical_order_matches": materialized_ids == authoritative_ids,
        "exact_matches": materialized_items == authoritative_items,
        "phase_output_matches": authoritative_ids
        == contract["phase_catalog"][-1]["output_item_ids"],
        "authoritative_sha256": _receipt_sha256(authoritative_items),
        "materialized_sha256": _receipt_sha256(materialized_items),
        "authoritative_evidence_sha256": authoritative_evidence,
        "materialized_evidence_sha256": materialized_evidence,
    }
    frontier_satisfies = all(
        (
            frontier["cardinality_matches"],
            frontier["canonical_order_matches"],
            frontier["exact_matches"],
            frontier["phase_output_matches"],
            materialize["true_cardinality"] == len(authoritative_items),
        )
    )
    phase_bindings_satisfy = all(
        receipt["binding_satisfies"] for receipt in phase_receipts
    )
    phase_timings_satisfy = all(
        receipt["timing_satisfies"] for receipt in phase_receipts
    )
    phases_satisfy = phase_bindings_satisfy and phase_timings_satisfy
    mutation_seams_satisfy = all(receipt["binding_satisfies"] for receipt in seam_receipts)
    dispatchable = all(
        (
            invocation_satisfies,
            latency_satisfies,
            phases_satisfy,
            refinement_equation_satisfies,
            frontier_satisfies,
            mutation_seams_satisfy,
        )
    )

    return {
        "parent_owner_id": owner_id,
        "contract_sha256": _receipt_sha256(contract),
        "completion_condition": contract["completion_condition"],
        "invocation_authority": {
            **contract["invocation_authority"],
            "observed": observed_invocations,
            "satisfies": invocation_satisfies,
            "evidence_sha256": _receipt_sha256(invocation["evidence"]),
        },
        "latency_authority": {
            **latency_authority,
            "observed_sample_count": len(latency["samples"]),
            "observed_p95": p95,
            "definition_satisfies": latency_definition_satisfies,
            "satisfies": latency_satisfies,
            "evidence_sha256": _receipt_sha256(latency["evidence"]),
        },
        "phase_receipts": phase_receipts,
        "refinement_equation": {
            "coarse_upper_bound": coarse["bound"],
            "refined_upper_bound": refine["bound"],
            "true_cardinality": materialize["true_cardinality"],
            "refinement_set_identity": contract["refinement_set_identity"],
            "satisfies": refinement_equation_satisfies,
        },
        "mixed_frontier": frontier,
        "mutation_seams": seam_receipts,
        "phase_binding_satisfies": phase_bindings_satisfy,
        "phase_timing_satisfies": phase_timings_satisfy,
        "mutation_seams_satisfy": mutation_seams_satisfy,
        "owner_decision": "dispatch" if dispatchable else "block",
    }
