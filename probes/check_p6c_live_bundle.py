#!/usr/bin/env python3

"""Validate a raw, product-independent P6c live-bundle candidate."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
sys.path.insert(0, str(HOOKS))

from compatibility_state import canonical_json, sha256_bytes  # noqa: E402
from cost_phase_guard import (  # noqa: E402
    CostPhaseViolation,
    build_end_to_end_cost_phase_attestation,
)


MIN_DENSE_SAMPLE_COUNT = 20
EXPECTED_PHASE_IDS = (
    "coarse-bound",
    "owner-refinement",
    "mixed-materialization",
)
EXPECTED_SEAMS = (
    "before:coarse-bound",
    "mid:coarse-bound",
    "after:coarse-bound",
    "before:owner-refinement",
    "mid:owner-refinement",
    "after:owner-refinement",
    "before:mixed-materialization",
    "mid:mixed-materialization",
    "after:mixed-materialization",
    "after:final_materialization",
)
BUNDLE_FIELDS = {
    "schema",
    "parent_owner_id",
    "frozen_contract",
    "representative_dense_cohort",
    "latency_sample_receipts",
    "invocation_receipts",
    "phase_results",
    "authoritative_frontier",
    "materialized_frontier",
    "mutation_observations",
}
COHORT_FIELDS = {
    "cohort_id",
    "population_identity",
    "selection_policy",
    "selection_evidence",
    "sample_count",
    "multiplicity_distribution_identity",
    "equivalence_class_distribution_identity",
    "worst_dense_witness_sample_id",
}
SAMPLE_FIELDS = {
    "sample_id",
    "cohort_id",
    "elapsed",
    "invocation_ids",
    "proof_partition_ids",
    "evidence",
}
INVOCATION_FIELDS = {
    "invocation_id",
    "sample_id",
    "equivalence_class_id",
    "proof_partition_id",
    "evidence",
}
MUTATION_FIELDS = {
    "seam",
    "source_root",
    "root_identity",
    "authority_epoch",
    "mutation_detected",
    "evidence",
}


class BundleViolation(RuntimeError):
    pass


def exact_mapping(value: object, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise BundleViolation(f"{name} fields are not exact")
    return value


def nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleViolation(f"{name} must be a non-empty string")
    return value


def identity_list(value: object, name: str, *, nonempty_list: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty_list and not value):
        raise BundleViolation(f"{name} must be a{' non-empty' if nonempty_list else ''} list")
    result = [nonempty(item, f"{name} item") for item in value]
    if len(result) != len(set(result)):
        raise BundleViolation(f"{name} contains duplicate identities")
    return result


def finite_nonnegative(value: object, name: str) -> int | float:
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise BundleViolation(f"{name} must be a non-negative finite number")
    return value


def bundle_sha256(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def validate_raw_joins(bundle: dict[str, Any]) -> tuple[dict, list[dict], list[dict]]:
    contract = bundle["frozen_contract"]
    if not isinstance(contract, Mapping):
        raise BundleViolation("frozen_contract must be an object")
    latency_authority = contract.get("latency_authority")
    if not isinstance(latency_authority, Mapping):
        raise BundleViolation("latency authority is absent")

    cohort = exact_mapping(
        bundle["representative_dense_cohort"],
        COHORT_FIELDS,
        "representative dense cohort",
    )
    cohort_id = nonempty(cohort["cohort_id"], "cohort id")
    nonempty(cohort["population_identity"], "population identity")
    nonempty(cohort["selection_policy"], "selection policy")
    if cohort["selection_evidence"] is None:
        raise BundleViolation("selection evidence is absent")
    if type(cohort["sample_count"]) is not int or cohort["sample_count"] < MIN_DENSE_SAMPLE_COUNT:
        raise BundleViolation(
            f"representative dense cohort requires at least {MIN_DENSE_SAMPLE_COUNT} samples"
        )
    for field in (
        "multiplicity_distribution_identity",
        "equivalence_class_distribution_identity",
        "worst_dense_witness_sample_id",
    ):
        nonempty(cohort[field], field.replace("_", " "))
    if not (
        cohort["sample_count"] == latency_authority.get("sample_count")
        and cohort["multiplicity_distribution_identity"]
        == latency_authority.get("multiplicity_distribution_identity")
        and cohort["equivalence_class_distribution_identity"]
        == latency_authority.get("equivalence_class_distribution_identity")
        and latency_authority.get("representative_scope") == "representative_dense"
    ):
        raise BundleViolation("cohort identity does not match frozen latency authority")

    raw_samples = bundle["latency_sample_receipts"]
    if not isinstance(raw_samples, list) or len(raw_samples) != cohort["sample_count"]:
        raise BundleViolation("latency sample receipt count does not match the cohort")
    samples = []
    sample_by_id = {}
    for index, value in enumerate(raw_samples):
        sample = exact_mapping(value, SAMPLE_FIELDS, f"latency sample[{index}]")
        sample_id = nonempty(sample["sample_id"], "sample id")
        if sample_id in sample_by_id:
            raise BundleViolation("latency sample ids are not unique")
        if sample["cohort_id"] != cohort_id:
            raise BundleViolation("latency sample belongs to another cohort")
        normalized = {
            **sample,
            "sample_id": sample_id,
            "elapsed": finite_nonnegative(sample["elapsed"], "sample elapsed"),
            "invocation_ids": identity_list(
                sample["invocation_ids"],
                "sample invocation ids",
                nonempty_list=True,
            ),
            "proof_partition_ids": identity_list(
                sample["proof_partition_ids"],
                "sample proof partition ids",
                nonempty_list=True,
            ),
        }
        if normalized["evidence"] is None:
            raise BundleViolation("latency sample evidence is absent")
        samples.append(normalized)
        sample_by_id[sample_id] = normalized
    if cohort["worst_dense_witness_sample_id"] not in sample_by_id:
        raise BundleViolation("worst dense witness is not a cohort sample")
    worst_sample = sample_by_id[cohort["worst_dense_witness_sample_id"]]
    if worst_sample["elapsed"] != max(sample["elapsed"] for sample in samples):
        raise BundleViolation("worst dense witness does not identify a maximum sample")

    raw_invocations = bundle["invocation_receipts"]
    if not isinstance(raw_invocations, list) or not raw_invocations:
        raise BundleViolation("invocation receipts must be a non-empty list")
    invocations = []
    invocation_by_id = {}
    by_sample: dict[str, list[dict]] = {sample_id: [] for sample_id in sample_by_id}
    for index, value in enumerate(raw_invocations):
        invocation = exact_mapping(value, INVOCATION_FIELDS, f"invocation[{index}]")
        invocation_id = nonempty(invocation["invocation_id"], "invocation id")
        if invocation_id in invocation_by_id:
            raise BundleViolation("invocation ids are not unique")
        sample_id = nonempty(invocation["sample_id"], "invocation sample id")
        if sample_id not in sample_by_id:
            raise BundleViolation("invocation references an orphan sample")
        normalized = {
            **invocation,
            "invocation_id": invocation_id,
            "sample_id": sample_id,
            "equivalence_class_id": nonempty(
                invocation["equivalence_class_id"],
                "invocation equivalence class id",
            ),
            "proof_partition_id": nonempty(
                invocation["proof_partition_id"],
                "invocation proof partition id",
            ),
        }
        if normalized["evidence"] is None:
            raise BundleViolation("invocation evidence is absent")
        invocations.append(normalized)
        invocation_by_id[invocation_id] = normalized
        by_sample[sample_id].append(normalized)

    for sample in samples:
        joined = by_sample[sample["sample_id"]]
        if [item["invocation_id"] for item in joined] != sample["invocation_ids"]:
            raise BundleViolation("sample-to-invocation order or membership drifted")
        joined_partitions = []
        for item in joined:
            if item["proof_partition_id"] not in joined_partitions:
                joined_partitions.append(item["proof_partition_id"])
        if joined_partitions != sample["proof_partition_ids"]:
            raise BundleViolation("sample-to-proof-partition join drifted")
    return cohort, samples, invocations


def validate_bundle(value: object) -> tuple[dict, dict]:
    bundle = exact_mapping(value, BUNDLE_FIELDS, "P6c live bundle")
    if bundle["schema"] != 1:
        raise BundleViolation("P6c live bundle schema is invalid")
    owner = nonempty(bundle["parent_owner_id"], "parent owner id")
    cohort, samples, invocations = validate_raw_joins(bundle)

    phase_results = bundle["phase_results"]
    if not isinstance(phase_results, list) or len(phase_results) != 3:
        raise BundleViolation("phase results must contain three entries")
    phase_by_id = {}
    for phase in phase_results:
        if not isinstance(phase, dict):
            raise BundleViolation("phase result must be an object")
        phase_id = nonempty(phase.get("phase_id"), "phase result id")
        if phase_id in phase_by_id:
            raise BundleViolation("phase result ids are not unique")
        if phase.get("evidence") is None:
            raise BundleViolation("phase result evidence is absent")
        phase_by_id[phase_id] = phase
    if tuple(phase_by_id) != EXPECTED_PHASE_IDS:
        raise BundleViolation("phase result catalog or order is not exact")

    contract_phase_catalog = bundle["frozen_contract"].get("phase_catalog")
    if not isinstance(contract_phase_catalog, list) or [
        phase.get("phase_id") if isinstance(phase, Mapping) else None
        for phase in contract_phase_catalog
    ] != list(EXPECTED_PHASE_IDS):
        raise BundleViolation("frozen phase catalog ids or order are not exact")

    for frontier_name in ("authoritative_frontier", "materialized_frontier"):
        frontier = bundle[frontier_name]
        if not isinstance(frontier, Mapping) or frontier.get("evidence") is None:
            raise BundleViolation(f"{frontier_name.replace('_', ' ')} evidence is absent")

    raw_observations = bundle["mutation_observations"]
    if not isinstance(raw_observations, list):
        raise BundleViolation("mutation observations must be a list")
    observations = {}
    for value in raw_observations:
        observation = exact_mapping(value, MUTATION_FIELDS, "mutation observation")
        seam = nonempty(observation["seam"], "mutation seam")
        if seam in observations:
            raise BundleViolation("mutation observations contain a duplicate seam")
        if observation["evidence"] is None:
            raise BundleViolation("mutation observation evidence is absent")
        observations[seam] = observation
    if tuple(observations) != EXPECTED_SEAMS:
        raise BundleViolation("mutation observation catalog or order is not exact")

    consumed_phases = []
    consumed_seams = []

    def measure_invocations(contract):
        authority = contract["invocation_authority"]
        return {
            "unit": authority["unit"],
            "cardinality_domain": authority["cardinality_domain"],
            "observed": len(invocations),
            "evidence": {"invocation_receipts": invocations},
        }

    def sample_dense_latency(contract):
        authority = contract["latency_authority"]
        return {
            "scope": authority["representative_scope"],
            "unit": authority["unit"],
            "sample_definition": authority["sample_definition"],
            "window_definition": authority["window_definition"],
            "multiplicity_distribution_identity": cohort[
                "multiplicity_distribution_identity"
            ],
            "equivalence_class_distribution_identity": cohort[
                "equivalence_class_distribution_identity"
            ],
            "samples": [sample["elapsed"] for sample in samples],
            "evidence": {
                "cohort": cohort,
                "sample_receipts": samples,
            },
        }

    def observe_mutation(seam, contract):
        consumed_seams.append(seam)
        return observations[seam]

    def run_phase(phase, current_ids, observe_mid):
        phase_id = phase["phase_id"]
        if phase_id not in phase_by_id:
            raise BundleViolation("phase result is absent from the raw bundle")
        result = phase_by_id[phase_id]
        if list(current_ids) != result.get("input_item_ids"):
            raise BundleViolation("phase callback input does not match raw phase input")
        consumed_phases.append(phase_id)
        observe_mid()
        return result

    attestation = build_end_to_end_cost_phase_attestation(
        parent_owner_id=owner,
        frozen_contract=bundle["frozen_contract"],
        measure_invocations=measure_invocations,
        sample_dense_latency=sample_dense_latency,
        observe_mutation=observe_mutation,
        run_phase=run_phase,
        compute_authoritative_frontier=lambda contract: bundle[
            "authoritative_frontier"
        ],
        materialize_final_frontier=lambda phase, contract: bundle[
            "materialized_frontier"
        ],
    )
    if consumed_phases != [phase["phase_id"] for phase in phase_results]:
        raise BundleViolation("phase results were not consumed exactly once in order")
    if consumed_seams != list(EXPECTED_SEAMS):
        raise BundleViolation("mutation observations were not consumed exactly once in order")
    return bundle, attestation


def qualification(value: object) -> dict:
    bundle, attestation = validate_bundle(value)
    dispatchable = attestation["owner_decision"] == "dispatch"
    return {
        "valid": True,
        "bundle_sha256": bundle_sha256(bundle),
        "provider_free_bundle_dispatchable": dispatchable,
        "attestation": attestation,
        "fresh_parent_disk_adjudication_present": False,
        "p6c_live_qualified": False,
        "phase1_complete": False,
        "direct_write_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--require-dispatchable", action="store_true")
    arguments = parser.parse_args()
    try:
        result = qualification(json.loads(arguments.bundle.read_text(encoding="utf-8")))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        BundleViolation,
        CostPhaseViolation,
    ) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    if arguments.require_dispatchable and not result["provider_free_bundle_dispatchable"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
