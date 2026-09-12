import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "probes" / "check_p6c_live_bundle.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p6c_live_bundle = load_module("p6c_live_bundle", PROBE)
cost_phase_guard = sys.modules["cost_phase_guard"]


class P6CLiveBundleTests(unittest.TestCase):
    def setUp(self):
        item_ids = ["frontier-a", "frontier-b", "frontier-c"]
        edges = [
            {"input_id": item_id, "output_id": item_id}
            for item_id in item_ids
        ]
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
                    "input_identity": cost_phase_guard.registry_identity(item_ids),
                    "output_identity": cost_phase_guard.registry_identity(item_ids),
                    "conservation_edges": copy.deepcopy(edges),
                    "timing_unit": "millisecond",
                    "timing_limit": 50,
                    "timing_definition": "owner wall clock around exact phase boundary",
                }
            )

        contract = {
            "invocation_authority": {
                "unit": "expensive-evaluator-invocation",
                "cardinality_domain": "semantic-equivalence-class",
                "limit": 20,
            },
            "latency_authority": {
                "unit": "millisecond",
                "statistic": "p95_nearest_rank",
                "limit": 100,
                "sample_count": 20,
                "sample_definition": "full end-to-end owner transaction",
                "window_definition": "one frozen representative dense cohort",
                "multiplicity_distribution_identity": "dense-multiplicity-v1",
                "equivalence_class_distribution_identity": "dense-classes-v1",
                "representative_scope": "representative_dense",
            },
            "completion_condition": "all exact frontier items materialized and verified",
            "source_root": "/frozen/source",
            "root_identity": "root-sha256",
            "authority_epoch": "epoch-7",
            "refinement_set_identity": cost_phase_guard.registry_identity(["r1", "r2"]),
            "phase_catalog": phases,
        }

        samples = []
        invocations = []
        for index in range(20):
            sample_id = f"sample-{index:02d}"
            invocation_id = f"invocation-{index:02d}"
            partition_id = f"partition-{index:02d}"
            samples.append(
                {
                    "sample_id": sample_id,
                    "cohort_id": "dense-cohort-v1",
                    "elapsed": 71 + index,
                    "invocation_ids": [invocation_id],
                    "proof_partition_ids": [partition_id],
                    "evidence": {"sample_receipt": sample_id},
                }
            )
            invocations.append(
                {
                    "invocation_id": invocation_id,
                    "sample_id": sample_id,
                    "equivalence_class_id": f"equivalence-{index % 5}",
                    "proof_partition_id": partition_id,
                    "evidence": {"invocation_receipt": invocation_id},
                }
            )

        phase_results = []
        for phase in phases:
            if phase["kind"] == "coarse":
                bound = 5
                refinement_ids = []
                reductions = []
                true_cardinality = None
            elif phase["kind"] == "refine":
                bound = 3
                refinement_ids = ["r1", "r2"]
                reductions = [
                    {"refinement_id": "r1", "reduction": 1},
                    {"refinement_id": "r2", "reduction": 1},
                ]
                true_cardinality = None
            else:
                bound = 3
                refinement_ids = []
                reductions = []
                true_cardinality = 3
            phase_results.append(
                {
                    "phase_id": phase["phase_id"],
                    "input_item_ids": list(item_ids),
                    "output_item_ids": list(item_ids),
                    "input_identity": phase["input_identity"],
                    "output_identity": phase["output_identity"],
                    "source_root": contract["source_root"],
                    "root_identity": contract["root_identity"],
                    "authority_epoch": contract["authority_epoch"],
                    "conservation_edges": copy.deepcopy(edges),
                    "bound": bound,
                    "refinement_ids": refinement_ids,
                    "refinement_reductions": reductions,
                    "true_cardinality": true_cardinality,
                    "timing_unit": "millisecond",
                    "timing_definition": "owner wall clock around exact phase boundary",
                    "elapsed": 10,
                    "evidence": {"phase_receipt": phase["phase_id"]},
                }
            )

        frontier = [
            {"identity": item_id, "payload": {"rank": index, "kind": "mixed"}}
            for index, item_id in enumerate(item_ids)
        ]
        observations = [
            {
                "seam": seam,
                "source_root": contract["source_root"],
                "root_identity": contract["root_identity"],
                "authority_epoch": contract["authority_epoch"],
                "mutation_detected": False,
                "evidence": {"seam_receipt": seam},
            }
            for seam in p6c_live_bundle.EXPECTED_SEAMS
        ]
        self.bundle = {
            "schema": 1,
            "parent_owner_id": "fixture.owner",
            "frozen_contract": contract,
            "representative_dense_cohort": {
                "cohort_id": "dense-cohort-v1",
                "population_identity": "dense-population-v1",
                "selection_policy": "frozen stratified dense cohort",
                "selection_evidence": {"manifest": "dense-manifest-v1"},
                "sample_count": 20,
                "multiplicity_distribution_identity": "dense-multiplicity-v1",
                "equivalence_class_distribution_identity": "dense-classes-v1",
                "worst_dense_witness_sample_id": "sample-19",
            },
            "latency_sample_receipts": samples,
            "invocation_receipts": invocations,
            "phase_results": phase_results,
            "authoritative_frontier": {
                "items": copy.deepcopy(frontier),
                "evidence": {"owner": "fresh"},
            },
            "materialized_frontier": {
                "items": copy.deepcopy(frontier),
                "evidence": {"mechanism": "staged"},
            },
            "mutation_observations": observations,
        }

    def test_exact_joined_bundle_is_dispatchable_but_not_live_qualified(self):
        result = p6c_live_bundle.qualification(copy.deepcopy(self.bundle))

        self.assertTrue(result["provider_free_bundle_dispatchable"])
        self.assertEqual(result["attestation"]["latency_authority"]["observed_p95"], 89)
        self.assertEqual(result["attestation"]["invocation_authority"]["observed"], 20)
        self.assertFalse(result["fresh_parent_disk_adjudication_present"])
        self.assertFalse(result["p6c_live_qualified"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])

    def test_orphaned_invocation_is_rejected(self):
        self.bundle["invocation_receipts"][0]["sample_id"] = "foreign-sample"

        with self.assertRaisesRegex(p6c_live_bundle.BundleViolation, "orphan sample"):
            p6c_live_bundle.qualification(self.bundle)

    def test_small_cohort_is_rejected_before_cost_adjudication(self):
        self.bundle["representative_dense_cohort"]["sample_count"] = 3
        self.bundle["representative_dense_cohort"]["worst_dense_witness_sample_id"] = (
            "sample-02"
        )
        self.bundle["frozen_contract"]["latency_authority"]["sample_count"] = 3
        self.bundle["latency_sample_receipts"] = self.bundle["latency_sample_receipts"][:3]
        self.bundle["invocation_receipts"] = self.bundle["invocation_receipts"][:3]

        with self.assertRaisesRegex(p6c_live_bundle.BundleViolation, "at least 20"):
            p6c_live_bundle.qualification(self.bundle)

    def test_missing_or_reordered_mutation_seam_is_rejected(self):
        self.bundle["mutation_observations"].pop(4)

        with self.assertRaisesRegex(
            p6c_live_bundle.BundleViolation, "catalog or order is not exact"
        ):
            p6c_live_bundle.qualification(self.bundle)

    def test_raw_evidence_worst_witness_and_phase_order_fail_closed(self):
        cases = []

        missing_evidence = copy.deepcopy(self.bundle)
        missing_evidence["latency_sample_receipts"][0]["evidence"] = None
        cases.append((missing_evidence, "sample evidence is absent"))

        wrong_witness = copy.deepcopy(self.bundle)
        wrong_witness["representative_dense_cohort"][
            "worst_dense_witness_sample_id"
        ] = "sample-18"
        cases.append((wrong_witness, "does not identify a maximum sample"))

        reordered_phases = copy.deepcopy(self.bundle)
        reordered_phases["phase_results"].reverse()
        cases.append((reordered_phases, "phase result catalog or order is not exact"))

        for bundle, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(p6c_live_bundle.BundleViolation, message):
                    p6c_live_bundle.qualification(bundle)

    def test_phase_binding_drift_blocks_without_becoming_live_qualified(self):
        self.bundle["phase_results"][1]["root_identity"] = "drifted-root"

        result = p6c_live_bundle.qualification(self.bundle)

        self.assertFalse(result["provider_free_bundle_dispatchable"])
        self.assertFalse(result["attestation"]["phase_binding_satisfies"])
        self.assertFalse(result["p6c_live_qualified"])

    def test_mixed_frontier_payload_drift_blocks(self):
        self.bundle["materialized_frontier"]["items"][1]["payload"]["kind"] = (
            "substituted"
        )

        result = p6c_live_bundle.qualification(self.bundle)

        self.assertFalse(result["provider_free_bundle_dispatchable"])
        self.assertFalse(result["attestation"]["mixed_frontier"]["exact_matches"])

    def test_cli_exit_codes_distinguish_valid_blocked_and_malformed(self):
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            valid_path = directory / "valid.json"
            blocked_path = directory / "blocked.json"
            malformed_path = directory / "malformed.json"
            valid_path.write_text(json.dumps(self.bundle), encoding="utf-8")
            blocked = copy.deepcopy(self.bundle)
            blocked["phase_results"][0]["elapsed"] = 51
            blocked_path.write_text(json.dumps(blocked), encoding="utf-8")
            malformed_path.write_text('{"schema":1}', encoding="utf-8")

            valid = subprocess.run(
                [sys.executable, str(PROBE), "--bundle", str(valid_path), "--require-dispatchable"],
                cwd=REPO,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            blocked_result = subprocess.run(
                [sys.executable, str(PROBE), "--bundle", str(blocked_path), "--require-dispatchable"],
                cwd=REPO,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            malformed = subprocess.run(
                [sys.executable, str(PROBE), "--bundle", str(malformed_path)],
                cwd=REPO,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(blocked_result.returncode, 2, blocked_result.stderr)
        self.assertEqual(malformed.returncode, 1, malformed.stderr)


if __name__ == "__main__":
    unittest.main()
