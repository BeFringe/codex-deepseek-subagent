#!/usr/bin/env python3

"""Fresh-process disk adjudication for the product-independent P6b/P6c run."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "probes"
sys.path.insert(0, str(PROBES))

import check_p6c_live_bundle as checker  # noqa: E402
import run_p6c_product_independent_live as runner  # noqa: E402


class AdjudicationError(RuntimeError):
    pass


def exact_mapping(value: object, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise AdjudicationError(f"{name} fields are not exact")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdjudicationError(message)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_source(bundle: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    contract = bundle["frozen_contract"]
    source_root = Path(contract["source_root"])
    require(source_root.is_absolute(), "source root is not absolute")
    require(source_root.is_dir(), "source root is unavailable to the fresh owner")
    snapshot = runner.source_snapshot(source_root)
    require(not snapshot["status_porcelain_v1"], "source root is dirty at fresh adjudication")
    require(
        runner.source_identity(snapshot) == contract["root_identity"],
        "fresh source identity does not match the frozen root",
    )
    return source_root, snapshot


def verify_population(
    bundle: Mapping[str, Any], source_root: Path
) -> tuple[list[dict], dict[str, dict]]:
    population_path = source_root / "population.json"
    value = exact_mapping(load_json(population_path), {"schema", "cases"}, "population")
    require(value["schema"] == 1, "population schema is invalid")
    population = value["cases"]
    require(population == runner.build_population(), "population is not the frozen exhaustive domain")
    cohort = bundle["representative_dense_cohort"]
    require(cohort["sample_count"] == runner.SAMPLE_COUNT, "cohort sample count drifted")
    require(len(population) == cohort["sample_count"], "population is not exhaustively sampled")
    require(
        cohort["population_identity"] == runner.digest(population),
        "population identity drifted",
    )
    require(
        cohort["selection_policy"]
        == "exhaustive frozen population; no sampled or omitted cases",
        "cohort selection is not exhaustive",
    )
    require(
        cohort["multiplicity_distribution_identity"]
        == runner.distribution_identity(population, "multiplicity"),
        "multiplicity distribution identity drifted",
    )
    require(
        cohort["equivalence_class_distribution_identity"]
        == runner.distribution_identity(population, "equivalence_class_id"),
        "equivalence-class distribution identity drifted",
    )
    evidence = exact_mapping(
        cohort["selection_evidence"],
        {
            "schema",
            "producer_pid",
            "population_path",
            "population_file_sha256",
            "source_full_head",
            "source_tree",
        },
        "selection evidence",
    )
    require(evidence["schema"] == 1, "selection evidence schema is invalid")
    require(type(evidence["producer_pid"]) is int and evidence["producer_pid"] > 0, "producer pid is invalid")
    require(evidence["producer_pid"] != os.getpid(), "fresh adjudicator is not a distinct process")
    require(evidence["population_path"] == str(population_path), "population path drifted")
    require(
        evidence["population_file_sha256"] == runner.file_sha256(population_path),
        "population file hash drifted",
    )
    by_sample = {item["sample_id"]: item for item in population}
    require(len(by_sample) == len(population), "population sample ids are not unique")
    return population, by_sample


def verify_transactions(bundle: Mapping[str, Any], by_sample: Mapping[str, dict]) -> dict:
    invocations = bundle["invocation_receipts"]
    samples = bundle["latency_sample_receipts"]
    require(len(invocations) == runner.SAMPLE_COUNT, "invocation count is not exact")
    require(len(samples) == runner.SAMPLE_COUNT, "latency sample count is not exact")
    invocation_by_id = {item["invocation_id"]: item for item in invocations}
    require(len(invocation_by_id) == len(invocations), "invocation ids are not unique")
    recomputed_output_hashes = []
    for sample in samples:
        case = by_sample.get(sample["sample_id"])
        require(case is not None, "sample is absent from the frozen population")
        require(len(sample["invocation_ids"]) == 1, "sample invocation cardinality is not one")
        invocation = invocation_by_id.get(sample["invocation_ids"][0])
        require(invocation is not None, "sample invocation is absent")
        require(invocation["sample_id"] == sample["sample_id"], "sample invocation join drifted")
        require(
            invocation["equivalence_class_id"] == case["equivalence_class_id"]
            and invocation["proof_partition_id"] == case["proof_partition_id"],
            "invocation authority fields drifted",
        )
        require(
            sample["proof_partition_ids"] == [case["proof_partition_id"]],
            "sample proof-partition join drifted",
        )
        result = runner.evaluate_case(case)
        input_sha256 = runner.digest(case)
        output_sha256 = runner.digest(result)
        recomputed_output_hashes.append(output_sha256)
        sample_evidence = exact_mapping(
            sample["evidence"],
            {
                "schema",
                "clock",
                "sample_definition",
                "input_sha256",
                "output_sha256",
                "started_ns",
                "ended_ns",
                "elapsed_ns",
            },
            "sample timing evidence",
        )
        invocation_evidence = exact_mapping(
            invocation["evidence"],
            {
                "schema",
                "evaluator",
                "input_sha256",
                "output_sha256",
                "started_ns",
                "ended_ns",
                "elapsed_ns",
            },
            "invocation evidence",
        )
        require(
            sample_evidence["schema"] == invocation_evidence["schema"] == 1,
            "transaction evidence schema is invalid",
        )
        require(
            sample_evidence["clock"] == "time.perf_counter_ns"
            and sample_evidence["sample_definition"] == runner.SAMPLE_DEFINITION,
            "sample timing authority drifted",
        )
        require(
            invocation_evidence["evaluator"] == runner.EVALUATOR_ID,
            "invocation evaluator drifted",
        )
        require(
            sample_evidence["input_sha256"]
            == invocation_evidence["input_sha256"]
            == input_sha256,
            "transaction input hash drifted",
        )
        require(
            sample_evidence["output_sha256"]
            == invocation_evidence["output_sha256"]
            == output_sha256,
            "transaction output hash drifted",
        )
        for evidence in (sample_evidence, invocation_evidence):
            require(
                type(evidence["started_ns"]) is int
                and type(evidence["ended_ns"]) is int
                and type(evidence["elapsed_ns"]) is int,
                "transaction timing is not integer nanoseconds",
            )
            require(
                evidence["ended_ns"] >= evidence["started_ns"]
                and evidence["elapsed_ns"]
                == evidence["ended_ns"] - evidence["started_ns"],
                "transaction elapsed time is not clock-derived",
            )
        require(sample["elapsed"] == sample_evidence["elapsed_ns"], "sample elapsed drifted")
        require(
            sample_evidence["started_ns"] == invocation_evidence["started_ns"]
            and sample_evidence["ended_ns"] == invocation_evidence["ended_ns"],
            "sample and invocation do not share one transaction window",
        )
    observed_worst = max(samples, key=lambda item: item["elapsed"])["sample_id"]
    require(
        observed_worst == bundle["representative_dense_cohort"]["worst_dense_witness_sample_id"],
        "worst dense witness drifted",
    )
    return {
        "sample_count": len(samples),
        "invocation_count": len(invocations),
        "recomputed_outputs_sha256": runner.digest(recomputed_output_hashes),
        "multiplicity_counts": dict(
            sorted(Counter(item["multiplicity"] for item in by_sample.values()).items())
        ),
        "equivalence_class_count": len(
            {item["equivalence_class_id"] for item in by_sample.values()}
        ),
    }


def verify_phases_and_seams(
    bundle: Mapping[str, Any], source_snapshot: Mapping[str, Any]
) -> dict:
    contract = bundle["frozen_contract"]
    phases = bundle["phase_results"]
    require(len(phases) == 3, "phase result count is not exact")
    for phase in phases:
        evidence = exact_mapping(
            phase["evidence"],
            {"schema", "clock", "started_ns", "ended_ns", "elapsed_ns", "operation_sha256"},
            "phase evidence",
        )
        require(
            evidence["schema"] == 1 and evidence["clock"] == "time.perf_counter_ns",
            "phase timing evidence is invalid",
        )
        require(
            type(evidence["started_ns"]) is int
            and type(evidence["ended_ns"]) is int
            and type(evidence["elapsed_ns"]) is int
            and evidence["ended_ns"] >= evidence["started_ns"],
            "phase timing is invalid",
        )
        require(
            evidence["elapsed_ns"] == evidence["ended_ns"] - evidence["started_ns"]
            and phase["elapsed"] == evidence["elapsed_ns"],
            "phase elapsed time is not clock-derived",
        )
        operation_prefix = runner.digest(
            {"phase_id": phase["phase_id"], "input_item_ids": phase["input_item_ids"]}
        )
        require(
            evidence["operation_sha256"]
            == runner.digest(
                {"operation_prefix": operation_prefix, "authority_epoch": contract["authority_epoch"]}
            ),
            "phase operation identity drifted",
        )

    observations = bundle["mutation_observations"]
    observed_times = []
    for observation in observations:
        evidence = exact_mapping(
            observation["evidence"],
            {"schema", "clock", "observed_ns", "observed_root_identity", "source_snapshot"},
            "mutation seam evidence",
        )
        require(
            evidence["schema"] == 1 and evidence["clock"] == "time.perf_counter_ns",
            "mutation seam clock evidence is invalid",
        )
        require(type(evidence["observed_ns"]) is int, "mutation seam time is invalid")
        observed_times.append(evidence["observed_ns"])
        require(
            evidence["source_snapshot"] == source_snapshot,
            "mutation seam source snapshot drifted",
        )
        require(
            evidence["observed_root_identity"] == contract["root_identity"],
            "mutation seam root identity drifted",
        )
        require(not observation["mutation_detected"], "mutation was detected at a phase seam")
    require(
        all(left < right for left, right in zip(observed_times, observed_times[1:])),
        "mutation seam observations are not strictly ordered",
    )
    return {
        "phase_count": len(phases),
        "mutation_seam_count": len(observations),
        "strictly_ordered": True,
    }


def verify_frontiers(bundle: Mapping[str, Any], source_root: Path) -> dict:
    authoritative_path = source_root / "authoritative-frontier.json"
    authoritative_file = exact_mapping(
        load_json(authoritative_path), {"schema", "items"}, "authoritative frontier file"
    )
    require(authoritative_file["schema"] == 1, "authoritative frontier schema is invalid")
    require(
        authoritative_file["items"] == runner.build_frontier(),
        "authoritative frontier is not owner-derived",
    )
    require(
        bundle["authoritative_frontier"]["items"] == authoritative_file["items"],
        "bundle authoritative frontier drifted",
    )
    authoritative_evidence = exact_mapping(
        bundle["authoritative_frontier"]["evidence"],
        {"schema", "path", "file_sha256", "source_root_identity"},
        "authoritative frontier evidence",
    )
    require(
        authoritative_evidence["schema"] == 1
        and authoritative_evidence["path"] == str(authoritative_path)
        and authoritative_evidence["file_sha256"] == runner.file_sha256(authoritative_path),
        "authoritative frontier disk evidence drifted",
    )

    materialized_evidence = exact_mapping(
        bundle["materialized_frontier"]["evidence"],
        {"schema", "path", "file_sha256", "materialization"},
        "materialized frontier evidence",
    )
    materialized_path = Path(materialized_evidence["path"])
    require(materialized_path.is_absolute() and materialized_path.is_file(), "materialized frontier is absent")
    materialized_file = exact_mapping(
        load_json(materialized_path), {"schema", "items"}, "materialized frontier file"
    )
    require(materialized_file["schema"] == 1, "materialized frontier schema is invalid")
    require(
        materialized_file["items"]
        == bundle["materialized_frontier"]["items"]
        == authoritative_file["items"],
        "materialized mixed frontier is not exact",
    )
    require(
        materialized_evidence["schema"] == 1
        and materialized_evidence["materialization"] == "atomic-os-replace"
        and materialized_evidence["file_sha256"] == runner.file_sha256(materialized_path),
        "materialized frontier disk evidence drifted",
    )
    return {
        "authoritative_path": str(authoritative_path),
        "authoritative_file_sha256": runner.file_sha256(authoritative_path),
        "materialized_path": str(materialized_path),
        "materialized_file_sha256": runner.file_sha256(materialized_path),
        "exact_frontier_sha256": runner.digest(authoritative_file["items"]),
    }


def adjudicate(bundle_path: Path) -> dict:
    bundle_path = bundle_path.resolve()
    bundle = load_json(bundle_path)
    checked = checker.qualification(bundle)
    require(checked["provider_free_bundle_dispatchable"], "bundle guard blocked dispatch")
    source_root, snapshot = verify_source(bundle)
    population, by_sample = verify_population(bundle, source_root)
    transactions = verify_transactions(bundle, by_sample)
    phases = verify_phases_and_seams(bundle, snapshot)
    frontiers = verify_frontiers(bundle, source_root)
    producer_pid = bundle["representative_dense_cohort"]["selection_evidence"]["producer_pid"]
    return {
        "schema": 1,
        "adjudication": "fresh-process-parent-disk-owner-v1",
        "provider_free": True,
        "producer_pid": producer_pid,
        "adjudicator_pid": os.getpid(),
        "distinct_process": producer_pid != os.getpid(),
        "bundle_path": str(bundle_path),
        "bundle_file_sha256": runner.file_sha256(bundle_path),
        "bundle_canonical_sha256": checker.bundle_sha256(bundle),
        "source_root": str(source_root),
        "source_snapshot": snapshot,
        "root_identity": runner.source_identity(snapshot),
        "authority_epoch": bundle["frozen_contract"]["authority_epoch"],
        "population_identity": runner.digest(population),
        "transactions": transactions,
        "phase_and_seam_recomputation": phases,
        "frontier_recomputation": frontiers,
        "guard_owner_decision": checked["attestation"]["owner_decision"],
        "p6b_state": "qualified",
        "p6c_state": "qualified",
        "phase1_complete": False,
        "direct_write_qualified": False,
        "phase2_open": False,
        "phase3_open": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--require-qualified", action="store_true")
    arguments = parser.parse_args()
    try:
        receipt = adjudicate(arguments.bundle)
        runner.write_json(arguments.receipt.resolve(), receipt)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        checker.BundleViolation,
        checker.CostPhaseViolation,
        runner.LiveBundleError,
        AdjudicationError,
    ) as error:
        print(json.dumps({"qualified": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    if arguments.require_qualified and not (
        receipt["p6b_state"] == receipt["p6c_state"] == "qualified"
    ):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
