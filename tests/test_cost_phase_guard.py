import copy
import importlib.util
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compatibility_state = load_module(
    "compatibility_state", REPO / "hooks" / "compatibility_state.py"
)
cost_phase_guard = load_module(
    "cost_phase_guard", REPO / "hooks" / "cost_phase_guard.py"
)


class CostPhaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.item_ids = ["frontier-a", "frontier-b", "frontier-c"]
        edges = [
            {"input_id": item_id, "output_id": item_id}
            for item_id in self.item_ids
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
                    "input_item_ids": list(self.item_ids),
                    "output_item_ids": list(self.item_ids),
                    "input_identity": cost_phase_guard.registry_identity(self.item_ids),
                    "output_identity": cost_phase_guard.registry_identity(self.item_ids),
                    "conservation_edges": copy.deepcopy(edges),
                    "timing_unit": "millisecond",
                    "timing_limit": 50,
                    "timing_definition": "owner wall clock around exact phase boundary",
                }
            )
        self.contract = {
            "invocation_authority": {
                "unit": "expensive-evaluator-invocation",
                "cardinality_domain": "semantic-equivalence-class",
                "limit": 10,
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
        self.authoritative = [
            {"identity": item_id, "payload": {"rank": index, "kind": "mixed"}}
            for index, item_id in enumerate(self.item_ids)
        ]

    def invocation(self, contract):
        return {
            "unit": "expensive-evaluator-invocation",
            "cardinality_domain": "semantic-equivalence-class",
            "observed": 9,
            "evidence": {"counted": 9},
        }

    def latency(self, contract):
        return {
            "scope": "representative_dense",
            "unit": "millisecond",
            "sample_definition": "full end-to-end owner transaction",
            "window_definition": "one frozen representative dense cohort",
            "multiplicity_distribution_identity": "dense-multiplicity-v1",
            "equivalence_class_distribution_identity": "dense-classes-v1",
            "samples": list(range(71, 91)),
            "evidence": {"cohort": "dense", "samples": 20},
        }

    def observer(self, seam, contract):
        return {
            "seam": seam,
            "source_root": contract["source_root"],
            "root_identity": contract["root_identity"],
            "authority_epoch": contract["authority_epoch"],
            "mutation_detected": False,
            "evidence": {"seam": seam, "unchanged": True},
        }

    def phase_runner(self, phase, current_ids, observe_mid):
        observe_mid()
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
        return {
            "phase_id": phase["phase_id"],
            "input_item_ids": list(current_ids),
            "output_item_ids": list(phase["output_item_ids"]),
            "input_identity": phase["input_identity"],
            "output_identity": phase["output_identity"],
            "source_root": "/frozen/source",
            "root_identity": "root-sha256",
            "authority_epoch": "epoch-7",
            "conservation_edges": copy.deepcopy(phase["conservation_edges"]),
            "bound": bound,
            "refinement_ids": refinement_ids,
            "refinement_reductions": reductions,
            "true_cardinality": true_cardinality,
            "timing_unit": "millisecond",
            "timing_definition": "owner wall clock around exact phase boundary",
            "elapsed": 10,
            "evidence": {"phase": phase["phase_id"]},
        }

    def build(self, **overrides):
        callbacks = {
            "measure_invocations": self.invocation,
            "sample_dense_latency": self.latency,
            "observe_mutation": self.observer,
            "run_phase": self.phase_runner,
            "compute_authoritative_frontier": lambda contract: {
                "items": copy.deepcopy(self.authoritative),
                "evidence": {"owner": "fresh"},
            },
            "materialize_final_frontier": lambda phase, contract: {
                "items": copy.deepcopy(self.authoritative),
                "evidence": {"mechanism": "staged"},
            },
        }
        callbacks.update(overrides)
        return cost_phase_guard.build_end_to_end_cost_phase_attestation(
            parent_owner_id="fixture.owner",
            frozen_contract=copy.deepcopy(self.contract),
            **callbacks,
        )

    def test_representative_dense_end_to_end_contract_dispatches(self):
        attestation = self.build()

        self.assertEqual(attestation["latency_authority"]["observed_p95"], 89)
        self.assertTrue(attestation["invocation_authority"]["satisfies"])
        self.assertTrue(attestation["latency_authority"]["satisfies"])
        self.assertTrue(attestation["refinement_equation"]["satisfies"])
        self.assertTrue(attestation["mixed_frontier"]["exact_matches"])
        self.assertEqual(len(attestation["mutation_seams"]), 10)
        self.assertEqual(attestation["owner_decision"], "dispatch")

    def test_invocation_pass_does_not_override_dense_p95_failure(self):
        def slow_latency(contract):
            result = self.latency(contract)
            result["samples"][-1] = 150
            result["samples"][-2] = 140
            return result

        attestation = self.build(sample_dense_latency=slow_latency)

        self.assertTrue(attestation["invocation_authority"]["satisfies"])
        self.assertEqual(attestation["latency_authority"]["observed_p95"], 140)
        self.assertFalse(attestation["latency_authority"]["satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_small_cohort_cannot_authorize_end_to_end_completion(self):
        def small_cohort(contract):
            result = self.latency(contract)
            result["samples"] = [20, 21, 22]
            return result

        attestation = self.build(sample_dense_latency=small_cohort)

        self.assertFalse(attestation["latency_authority"]["definition_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_sql_only_spike_cannot_stand_for_end_to_end_latency(self):
        def sql_spike(contract):
            result = self.latency(contract)
            result["scope"] = "sql_only"
            result["sample_definition"] = "single storage query"
            return result

        attestation = self.build(sample_dense_latency=sql_spike)

        self.assertFalse(attestation["latency_authority"]["definition_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_nearest_rank_p95_definition_is_not_interpolated(self):
        samples = list(range(1, 21))
        self.assertEqual(cost_phase_guard.nearest_rank_p95(samples), 19)

    def test_refinement_equation_drift_blocks(self):
        def broken_refinement(phase, current_ids, observe_mid):
            result = self.phase_runner(phase, current_ids, observe_mid)
            if phase["kind"] == "refine":
                result["bound"] = 4
            return result

        attestation = self.build(run_phase=broken_refinement)

        self.assertFalse(attestation["refinement_equation"]["satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_phase_root_or_epoch_drift_blocks(self):
        def drifted_phase(phase, current_ids, observe_mid):
            result = self.phase_runner(phase, current_ids, observe_mid)
            if phase["kind"] == "refine":
                result["authority_epoch"] = "epoch-8"
            return result

        attestation = self.build(run_phase=drifted_phase)

        self.assertFalse(attestation["phase_binding_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_phase_timing_is_separate_and_over_limit_blocks(self):
        def slow_phase(phase, current_ids, observe_mid):
            result = self.phase_runner(phase, current_ids, observe_mid)
            if phase["kind"] == "refine":
                result["elapsed"] = 51
            return result

        attestation = self.build(run_phase=slow_phase)

        self.assertTrue(attestation["latency_authority"]["satisfies"])
        self.assertFalse(attestation["phase_timing_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_cross_phase_substitution_is_rejected(self):
        def substituted_phase(phase, current_ids, observe_mid):
            result = self.phase_runner(phase, current_ids, observe_mid)
            if phase["kind"] == "refine":
                result["output_item_ids"][-1] = "foreign-frontier"
            return result

        with self.assertRaisesRegex(
            cost_phase_guard.CostPhaseViolation, "missing, duplicate, or orphaned output"
        ):
            self.build(run_phase=substituted_phase)

    def test_frozen_catalog_rejects_missing_or_orphaned_conservation(self):
        self.contract["phase_catalog"][1]["conservation_edges"].pop()

        with self.assertRaisesRegex(
            cost_phase_guard.CostPhaseViolation, "missing or orphaned input"
        ):
            self.build()

    def test_mixed_frontier_cardinality_drift_blocks(self):
        def short_frontier(phase, contract):
            return {"items": copy.deepcopy(self.authoritative[:-1]), "evidence": {}}

        attestation = self.build(materialize_final_frontier=short_frontier)

        self.assertFalse(attestation["mixed_frontier"]["cardinality_matches"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_mixed_frontier_canonical_order_drift_blocks(self):
        def reordered_frontier(phase, contract):
            return {"items": list(reversed(copy.deepcopy(self.authoritative))), "evidence": {}}

        attestation = self.build(materialize_final_frontier=reordered_frontier)

        self.assertTrue(attestation["mixed_frontier"]["cardinality_matches"])
        self.assertFalse(attestation["mixed_frontier"]["canonical_order_matches"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_self_consistent_payload_drift_still_fails_exact_frontier(self):
        def forged_frontier(phase, contract):
            items = copy.deepcopy(self.authoritative)
            items[1]["payload"]["kind"] = "substituted"
            return {"items": items, "evidence": {"digest": "self-consistent"}}

        attestation = self.build(materialize_final_frontier=forged_frontier)

        self.assertTrue(attestation["mixed_frontier"]["canonical_order_matches"])
        self.assertFalse(attestation["mixed_frontier"]["exact_matches"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_before_mid_and_after_mutation_races_each_block(self):
        for target in (
            "before:coarse-bound",
            "mid:owner-refinement",
            "after:mixed-materialization",
            "after:final_materialization",
        ):
            with self.subTest(target=target):
                def raced_observer(seam, contract, target=target):
                    result = self.observer(seam, contract)
                    result["mutation_detected"] = seam == target
                    return result

                attestation = self.build(observe_mutation=raced_observer)
                self.assertFalse(attestation["mutation_seams_satisfy"])
                self.assertEqual(attestation["owner_decision"], "block")

    def test_opaque_phase_without_internal_seam_is_rejected(self):
        def opaque_phase(phase, current_ids, observe_mid):
            return self.phase_runner(phase, current_ids, lambda: None)

        with self.assertRaisesRegex(
            cost_phase_guard.CostPhaseViolation, "must expose exactly one internal"
        ):
            self.build(run_phase=opaque_phase)

    def test_public_builder_accepts_no_precomputed_pass_flags(self):
        with self.assertRaises(TypeError):
            cost_phase_guard.build_end_to_end_cost_phase_attestation(
                parent_owner_id="fixture.owner",
                frozen_contract=copy.deepcopy(self.contract),
                measure_invocations=self.invocation,
                sample_dense_latency=self.latency,
                observe_mutation=self.observer,
                run_phase=self.phase_runner,
                compute_authoritative_frontier=lambda contract: {
                    "items": copy.deepcopy(self.authoritative),
                    "evidence": {},
                },
                materialize_final_frontier=lambda phase, contract: {
                    "items": copy.deepcopy(self.authoritative),
                    "evidence": {},
                },
                precomputed_latency_pass=True,
                precomputed_phase_pass=True,
            )


if __name__ == "__main__":
    unittest.main()
