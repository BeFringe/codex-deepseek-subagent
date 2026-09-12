#!/usr/bin/env python3

"""Produce one real, provider-free P6b/P6c bundle in a disposable Git root."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
PROBES = ROOT / "probes"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(PROBES))

from compatibility_state import canonical_json, sha256_bytes  # noqa: E402
from cost_phase_guard import (  # noqa: E402
    build_end_to_end_cost_phase_attestation,
    registry_identity,
)


SAMPLE_COUNT = 20
LATENCY_LIMIT_NS = 500_000_000
PHASE_LIMIT_NS = 500_000_000
OWNER_ID = "p6c.product-independent.owner.v1"
COHORT_ID = "p6c-product-independent-dense-v1"
SAMPLE_DEFINITION = "full deterministic evaluator transaction measured by time.perf_counter_ns"
WINDOW_DEFINITION = "exhaustive frozen twenty-case product-independent dense population"
PHASE_TIMING_DEFINITION = "time.perf_counter_ns around exact owner phase transaction"
EVALUATOR_ID = "sha256-dense-equivalence-evaluator-v1"


class LiveBundleError(RuntimeError):
    pass


def digest(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(canonical_json(value) + b"\n")
    os.replace(temporary, path)


def run_git(root: Path, *arguments: str, environment: Mapping[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        env=None if environment is None else dict(environment),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise LiveBundleError(
            f"git {' '.join(arguments)} failed with {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.rstrip("\n")


def build_population() -> list[dict[str, Any]]:
    population = []
    for index in range(SAMPLE_COUNT):
        equivalence_class_id = f"equivalence-{index % 5}"
        proof_partition_id = f"partition-{index % 4}"
        multiplicity = 8 * (1 + index // 5)
        population.append(
            {
                "sample_id": f"sample-{index:02d}",
                "equivalence_class_id": equivalence_class_id,
                "proof_partition_id": proof_partition_id,
                "multiplicity": multiplicity,
                "payload_seed": digest(
                    {
                        "equivalence_class_id": equivalence_class_id,
                        "proof_partition_id": proof_partition_id,
                        "ordinal": index,
                    }
                ),
            }
        )
    return population


def build_frontier() -> list[dict[str, Any]]:
    return [
        {
            "identity": "frontier-owner",
            "payload": {"kind": "owner-derived", "rank": 0},
        },
        {
            "identity": "frontier-contribution",
            "payload": {"kind": "worker-contribution", "rank": 1},
        },
        {
            "identity": "frontier-recovery",
            "payload": {"kind": "recovery-baseline", "rank": 2},
        },
    ]


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    seed = bytes.fromhex(str(case["payload_seed"]))
    accumulator = seed
    multiplicity = int(case["multiplicity"])
    for ordinal in range(multiplicity * 128):
        accumulator = hashlib.sha256(
            accumulator
            + str(case["equivalence_class_id"]).encode("utf-8")
            + str(case["proof_partition_id"]).encode("utf-8")
            + ordinal.to_bytes(4, "big")
        ).digest()
    return {
        "evaluator": EVALUATOR_ID,
        "semantic_identity": digest(
            {
                "equivalence_class_id": case["equivalence_class_id"],
                "proof_partition_id": case["proof_partition_id"],
            }
        ),
        "result_sha256": accumulator.hex(),
    }


def initialize_source(work_root: Path) -> tuple[Path, Path, list[dict], list[dict]]:
    if not work_root.is_absolute():
        raise LiveBundleError("work root must be absolute")
    work_root.mkdir(parents=True, exist_ok=True)
    if any(work_root.iterdir()):
        raise LiveBundleError("work root must be empty")
    source_root = work_root / "source"
    output_root = work_root / "output"
    source_root.mkdir()
    output_root.mkdir()

    population = build_population()
    frontier = build_frontier()
    write_json(source_root / "population.json", {"schema": 1, "cases": population})
    write_json(
        source_root / "authoritative-frontier.json",
        {"schema": 1, "items": frontier},
    )
    write_json(
        source_root / "protocol.json",
        {
            "schema": 1,
            "cohort": "exhaustive-product-independent-dense-v1",
            "sample_count": SAMPLE_COUNT,
            "evaluator": EVALUATOR_ID,
            "phases": [
                "coarse-bound",
                "owner-refinement",
                "mixed-materialization",
            ],
        },
    )

    run_git(source_root, "init", "-q")
    run_git(source_root, "checkout", "-q", "-b", "main")
    run_git(source_root, "config", "user.name", "Codex P6c Fixture")
    run_git(source_root, "config", "user.email", "p6c-fixture.invalid@example.invalid")
    run_git(source_root, "add", "--", ".")
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    }
    run_git(source_root, "commit", "-q", "-m", "fixture: freeze product-independent P6c source", environment=environment)
    return source_root.resolve(), output_root.resolve(), population, frontier


def source_snapshot(source_root: Path) -> dict[str, Any]:
    tracked = run_git(source_root, "ls-files").splitlines()
    manifest = [
        {"path": relative, "sha256": file_sha256(source_root / relative)}
        for relative in tracked
    ]
    return {
        "branch": run_git(source_root, "symbolic-ref", "--short", "HEAD"),
        "full_head": run_git(source_root, "rev-parse", "HEAD"),
        "tree": run_git(source_root, "rev-parse", "HEAD^{tree}"),
        "status_porcelain_v1": run_git(
            source_root, "status", "--porcelain=v1", "--untracked-files=all"
        ),
        "tracked_manifest": manifest,
    }


def source_identity(snapshot: Mapping[str, Any]) -> str:
    return digest(snapshot)


def distribution_identity(population: list[dict], field: str) -> str:
    counts = Counter(item[field] for item in population)
    return digest([{"value": key, "count": counts[key]} for key in sorted(counts)])


def phase_catalog(source_root: Path, root_identity: str, authority_epoch: str) -> list[dict]:
    del source_root, root_identity, authority_epoch
    item_ids = [item["identity"] for item in build_frontier()]
    edges = [{"input_id": item_id, "output_id": item_id} for item_id in item_ids]
    phases = []
    for phase_id, kind in (
        ("coarse-bound", "coarse"),
        ("owner-refinement", "refine"),
        ("mixed-materialization", "materialize"),
    ):
        phases.append(
            {
                "phase_id": phase_id,
                "kind": kind,
                "input_item_ids": list(item_ids),
                "output_item_ids": list(item_ids),
                "input_identity": registry_identity(item_ids),
                "output_identity": registry_identity(item_ids),
                "conservation_edges": list(edges),
                "timing_unit": "nanosecond",
                "timing_limit": PHASE_LIMIT_NS,
                "timing_definition": PHASE_TIMING_DEFINITION,
            }
        )
    return phases


def produce_bundle(work_root: Path) -> tuple[dict, dict]:
    source_root, output_root, population, frontier = initialize_source(work_root)
    initial_snapshot = source_snapshot(source_root)
    if initial_snapshot["status_porcelain_v1"]:
        raise LiveBundleError("frozen source root is dirty immediately after commit")
    root_identity = source_identity(initial_snapshot)
    population_identity = digest(population)
    multiplicity_identity = distribution_identity(population, "multiplicity")
    equivalence_identity = distribution_identity(population, "equivalence_class_id")
    authority_epoch = digest(
        {
            "owner": OWNER_ID,
            "root_identity": root_identity,
            "population_identity": population_identity,
            "phase_ids": [
                "coarse-bound",
                "owner-refinement",
                "mixed-materialization",
            ],
        }
    )
    phases = phase_catalog(source_root, root_identity, authority_epoch)
    contract = {
        "invocation_authority": {
            "unit": "expensive-evaluator-invocation",
            "cardinality_domain": "frozen-sample-transaction",
            "limit": SAMPLE_COUNT,
        },
        "latency_authority": {
            "unit": "nanosecond",
            "statistic": "p95_nearest_rank",
            "limit": LATENCY_LIMIT_NS,
            "sample_count": SAMPLE_COUNT,
            "sample_definition": SAMPLE_DEFINITION,
            "window_definition": WINDOW_DEFINITION,
            "multiplicity_distribution_identity": multiplicity_identity,
            "equivalence_class_distribution_identity": equivalence_identity,
            "representative_scope": "representative_dense",
        },
        "completion_condition": "all exact mixed-frontier items materialized and disk-verified",
        "source_root": str(source_root),
        "root_identity": root_identity,
        "authority_epoch": authority_epoch,
        "refinement_set_identity": registry_identity(["remove-duplicate-a", "remove-duplicate-b"]),
        "phase_catalog": phases,
    }

    sample_receipts = []
    invocation_receipts = []
    for index, case in enumerate(population):
        invocation_id = f"invocation-{index:02d}"
        input_sha256 = digest(case)
        started_ns = time.perf_counter_ns()
        result = evaluate_case(case)
        ended_ns = time.perf_counter_ns()
        elapsed_ns = ended_ns - started_ns
        invocation_evidence = {
            "schema": 1,
            "evaluator": EVALUATOR_ID,
            "input_sha256": input_sha256,
            "output_sha256": digest(result),
            "started_ns": started_ns,
            "ended_ns": ended_ns,
            "elapsed_ns": elapsed_ns,
        }
        invocation_receipts.append(
            {
                "invocation_id": invocation_id,
                "sample_id": case["sample_id"],
                "equivalence_class_id": case["equivalence_class_id"],
                "proof_partition_id": case["proof_partition_id"],
                "evidence": invocation_evidence,
            }
        )
        sample_receipts.append(
            {
                "sample_id": case["sample_id"],
                "cohort_id": COHORT_ID,
                "elapsed": elapsed_ns,
                "invocation_ids": [invocation_id],
                "proof_partition_ids": [case["proof_partition_id"]],
                "evidence": {
                    "schema": 1,
                    "clock": "time.perf_counter_ns",
                    "sample_definition": SAMPLE_DEFINITION,
                    "input_sha256": input_sha256,
                    "output_sha256": digest(result),
                    "started_ns": started_ns,
                    "ended_ns": ended_ns,
                    "elapsed_ns": elapsed_ns,
                },
            }
        )

    mutation_observations = []
    phase_results = []

    def observe_mutation(seam: str, frozen_contract: Mapping[str, Any]) -> dict:
        snapshot = source_snapshot(source_root)
        observed_identity = source_identity(snapshot)
        receipt = {
            "seam": seam,
            "source_root": str(source_root),
            "root_identity": frozen_contract["root_identity"],
            "authority_epoch": frozen_contract["authority_epoch"],
            "mutation_detected": observed_identity != frozen_contract["root_identity"],
            "evidence": {
                "schema": 1,
                "clock": "time.perf_counter_ns",
                "observed_ns": time.perf_counter_ns(),
                "observed_root_identity": observed_identity,
                "source_snapshot": snapshot,
            },
        }
        mutation_observations.append(receipt)
        return receipt

    def run_phase(
        phase: Mapping[str, Any],
        current_ids: tuple[str, ...],
        observe_mid,
    ) -> dict:
        started_ns = time.perf_counter_ns()
        phase_id = str(phase["phase_id"])
        operation_prefix = digest(
            {"phase_id": phase_id, "input_item_ids": list(current_ids)}
        )
        observe_mid()
        operation_sha256 = digest(
            {"operation_prefix": operation_prefix, "authority_epoch": authority_epoch}
        )
        if phase_id == "coarse-bound":
            bound = 5
            refinement_ids = []
            reductions = []
            true_cardinality = None
        elif phase_id == "owner-refinement":
            bound = 3
            refinement_ids = ["remove-duplicate-a", "remove-duplicate-b"]
            reductions = [
                {"refinement_id": "remove-duplicate-a", "reduction": 1},
                {"refinement_id": "remove-duplicate-b", "reduction": 1},
            ]
            true_cardinality = None
        elif phase_id == "mixed-materialization":
            bound = len(frontier)
            refinement_ids = []
            reductions = []
            true_cardinality = len(frontier)
        else:  # pragma: no cover - frozen catalog makes this unreachable
            raise LiveBundleError(f"unexpected phase: {phase_id}")
        ended_ns = time.perf_counter_ns()
        result = {
            "phase_id": phase_id,
            "input_item_ids": list(current_ids),
            "output_item_ids": list(phase["output_item_ids"]),
            "input_identity": registry_identity(current_ids),
            "output_identity": registry_identity(phase["output_item_ids"]),
            "source_root": str(source_root),
            "root_identity": root_identity,
            "authority_epoch": authority_epoch,
            "conservation_edges": list(phase["conservation_edges"]),
            "bound": bound,
            "refinement_ids": refinement_ids,
            "refinement_reductions": reductions,
            "true_cardinality": true_cardinality,
            "timing_unit": "nanosecond",
            "timing_definition": PHASE_TIMING_DEFINITION,
            "elapsed": ended_ns - started_ns,
            "evidence": {
                "schema": 1,
                "clock": "time.perf_counter_ns",
                "started_ns": started_ns,
                "ended_ns": ended_ns,
                "elapsed_ns": ended_ns - started_ns,
                "operation_sha256": operation_sha256,
            },
        }
        phase_results.append(result)
        return result

    def authoritative_frontier(_contract: Mapping[str, Any]) -> dict:
        path = source_root / "authoritative-frontier.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        return {
            "items": value["items"],
            "evidence": {
                "schema": 1,
                "path": str(path),
                "file_sha256": file_sha256(path),
                "source_root_identity": source_identity(source_snapshot(source_root)),
            },
        }

    materialized_path = output_root / "materialized-frontier.json"

    def materialized_frontier(
        _phase: Mapping[str, Any], _contract: Mapping[str, Any]
    ) -> dict:
        write_json(materialized_path, {"schema": 1, "items": frontier})
        return {
            "items": json.loads(materialized_path.read_text(encoding="utf-8"))["items"],
            "evidence": {
                "schema": 1,
                "path": str(materialized_path),
                "file_sha256": file_sha256(materialized_path),
                "materialization": "atomic-os-replace",
            },
        }

    cohort = {
        "cohort_id": COHORT_ID,
        "population_identity": population_identity,
        "selection_policy": "exhaustive frozen population; no sampled or omitted cases",
        "selection_evidence": {
            "schema": 1,
            "producer_pid": os.getpid(),
            "population_path": str(source_root / "population.json"),
            "population_file_sha256": file_sha256(source_root / "population.json"),
            "source_full_head": initial_snapshot["full_head"],
            "source_tree": initial_snapshot["tree"],
        },
        "sample_count": SAMPLE_COUNT,
        "multiplicity_distribution_identity": multiplicity_identity,
        "equivalence_class_distribution_identity": equivalence_identity,
        "worst_dense_witness_sample_id": max(
            sample_receipts, key=lambda item: item["elapsed"]
        )["sample_id"],
    }
    bundle: dict[str, Any] = {
        "schema": 1,
        "parent_owner_id": OWNER_ID,
        "frozen_contract": contract,
        "representative_dense_cohort": cohort,
        "latency_sample_receipts": sample_receipts,
        "invocation_receipts": invocation_receipts,
        "phase_results": phase_results,
        "authoritative_frontier": {},
        "materialized_frontier": {},
        "mutation_observations": mutation_observations,
    }

    attestation = build_end_to_end_cost_phase_attestation(
        parent_owner_id=OWNER_ID,
        frozen_contract=contract,
        measure_invocations=lambda frozen: {
            "unit": frozen["invocation_authority"]["unit"],
            "cardinality_domain": frozen["invocation_authority"]["cardinality_domain"],
            "observed": len(invocation_receipts),
            "evidence": {"invocation_receipts": invocation_receipts},
        },
        sample_dense_latency=lambda frozen: {
            "scope": frozen["latency_authority"]["representative_scope"],
            "unit": frozen["latency_authority"]["unit"],
            "sample_definition": frozen["latency_authority"]["sample_definition"],
            "window_definition": frozen["latency_authority"]["window_definition"],
            "multiplicity_distribution_identity": multiplicity_identity,
            "equivalence_class_distribution_identity": equivalence_identity,
            "samples": [item["elapsed"] for item in sample_receipts],
            "evidence": {"cohort": cohort, "sample_receipts": sample_receipts},
        },
        observe_mutation=observe_mutation,
        run_phase=run_phase,
        compute_authoritative_frontier=authoritative_frontier,
        materialize_final_frontier=materialized_frontier,
    )
    bundle["authoritative_frontier"] = authoritative_frontier(contract)
    bundle["materialized_frontier"] = {
        "items": json.loads(materialized_path.read_text(encoding="utf-8"))["items"],
        "evidence": {
            "schema": 1,
            "path": str(materialized_path),
            "file_sha256": file_sha256(materialized_path),
            "materialization": "atomic-os-replace",
        },
    }
    if attestation["owner_decision"] != "dispatch":
        raise LiveBundleError("freshly produced live bundle did not dispatch")
    if len(mutation_observations) != 10:
        raise LiveBundleError("live run did not expose all ten mutation seams")
    return bundle, attestation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        bundle, attestation = produce_bundle(arguments.work_root.resolve())
        bundle_path = arguments.bundle.resolve()
        write_json(bundle_path, bundle)
    except (OSError, ValueError, json.JSONDecodeError, LiveBundleError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "bundle": str(bundle_path),
                "bundle_sha256": file_sha256(bundle_path),
                "owner_decision": attestation["owner_decision"],
                "sample_count": len(bundle["latency_sample_receipts"]),
                "invocation_count": len(bundle["invocation_receipts"]),
                "mutation_seam_count": len(bundle["mutation_observations"]),
                "phase1_complete": False,
                "direct_write_qualified": False,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
