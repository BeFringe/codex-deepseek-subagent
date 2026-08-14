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
feasibility_guard = load_module(
    "feasibility_guard", REPO / "hooks" / "feasibility_guard.py"
)


class FeasibilityGuardTests(unittest.TestCase):
    def bounded_result(
        self,
        required_lower_bound,
        *,
        cardinality_domain="semantic-equivalence-class",
        scale_basis="adversarial_scale_witness",
        witness_input=None,
    ):
        if witness_input is None and scale_basis == "adversarial_scale_witness":
            witness_input = {"qualifying_identities": 17, "equivalence_classes": 9}
        return {
            "mechanism_measurement": {
                "unit": "expensive-evaluator-invocation",
                "cardinality_domain": cardinality_domain,
                "required_lower_bound": required_lower_bound,
            },
            "scale_evidence": {
                "basis": scale_basis,
                "witness_input": witness_input,
                "evidence": {"required_lower_bound": required_lower_bound},
            },
            "evidence": {"required_invocations": required_lower_bound},
        }

    def compression(self, **overrides):
        value = {
            "equivalence_rule": "owner semantic equality",
            "class_cardinality_domain": "semantic-equivalence-class",
            "identity_cardinality_domain": "object-identity",
            "evaluated_class_count": 300,
            "proven_identity_count": 3000,
            "fanout_identity_count": 3000,
            "evidence": {"class_digest": "owner-derived"},
        }
        value.update(overrides)
        return value

    def build(
        self,
        mechanism,
        assessor,
        *,
        assumptions=(),
        limit=10,
        probe_input=None,
        compression=None,
    ):
        probes = []
        if probe_input is None:
            probe_input = {"qualifying_identities": 17, "equivalence_classes": 9}

        def negative_probe(value):
            probes.append(value)
            return {
                "counterexample_found": False,
                "evidence": {"tested_boundary": value, "counterexamples": []},
            }

        attestation = feasibility_guard.build_parent_feasibility_attestation(
            parent_owner_id="fixture.owner",
            exact_claimed_invariant="mechanism closes the finite gap",
            probe_id="cheap-boundary-falsifier",
            probe_input=probe_input,
            completion_condition="finite gap closes",
            work_budget={
                "unit": "expensive-evaluator-invocation",
                "cardinality_domain": "semantic-equivalence-class",
                "limit": limit,
            },
            proposed_mechanism=mechanism,
            unresolved_assumptions=assumptions,
            run_counterexample_probe=negative_probe,
            assess_bounded_completion=assessor,
            derive_equivalence_compression=lambda owner_input, owner_mechanism: compression,
        )
        return probes, attestation

    def test_sound_but_too_loose_mechanism_is_blocked_before_dispatch(self):
        probes, attestation = self.build(
            "safe upper bound only",
            lambda mechanism, budget: self.bounded_result(17),
        )

        self.assertEqual(
            probes, [{"qualifying_identities": 17, "equivalence_classes": 9}]
        )
        self.assertFalse(attestation["bounded_completion"]["mechanism_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_independent_bound_term_can_make_final_mechanism_dispatchable(self):
        probes, attestation = self.build(
            "upper bound plus independent lower-bound term",
            lambda mechanism, budget: self.bounded_result(9),
        )

        self.assertEqual(len(probes), 1)
        self.assertTrue(attestation["counterexample_probe"]["executed"])
        self.assertEqual(attestation["owner_decision"], "dispatch")

    def test_blocking_unresolved_assumption_prevents_dispatch(self):
        _, attestation = self.build(
            "bounded mechanism",
            lambda mechanism, budget: self.bounded_result(9),
            assumptions=[{"assumption": "input remains finite", "blocking": True}],
        )

        self.assertEqual(attestation["owner_decision"], "block")

    def test_budget_domain_mismatch_blocks_identity_counted_mechanism(self):
        _, attestation = self.build(
            "identity-counted persisted proof",
            lambda mechanism, budget: self.bounded_result(
                300, cardinality_domain="object-identity"
            ),
            limit=2048,
            probe_input={"qualifying_identities": 3000, "equivalence_classes": 300},
        )

        bounded = attestation["bounded_completion"]
        self.assertEqual(
            bounded["work_budget"]["cardinality_domain"],
            "semantic-equivalence-class",
        )
        self.assertEqual(
            bounded["mechanism_measurement"]["cardinality_domain"],
            "object-identity",
        )
        self.assertFalse(bounded["mechanism_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_owner_derived_equivalence_compression_conserves_fanout_at_scale(self):
        _, attestation = self.build(
            "owner-derived equivalence compression",
            lambda mechanism, budget: self.bounded_result(
                300,
                witness_input={"qualifying_identities": 3000, "equivalence_classes": 300},
            ),
            limit=2048,
            probe_input={"qualifying_identities": 3000, "equivalence_classes": 300},
            compression=self.compression(),
        )

        bounded = attestation["bounded_completion"]
        self.assertEqual(bounded["equivalence_compression"]["evaluated_class_count"], 300)
        self.assertEqual(bounded["equivalence_compression"]["proven_identity_count"], 3000)
        self.assertTrue(bounded["mechanism_satisfies"])
        self.assertEqual(attestation["owner_decision"], "dispatch")

    def test_self_reported_grouping_origin_is_not_an_accepted_derivation_seam(self):
        with self.assertRaisesRegex(
            feasibility_guard.FeasibilityViolation, "compression fields"
        ):
            self.build(
                "caller-labelled equivalence compression",
                lambda mechanism, budget: self.bounded_result(300),
                limit=2048,
                compression=self.compression(grouping_origin="caller_supplied"),
            )

    def test_broken_owner_derived_fanout_blocks_dispatch(self):
        _, attestation = self.build(
            "non-conserving equivalence compression",
            lambda mechanism, budget: self.bounded_result(300),
            limit=2048,
            compression=self.compression(fanout_identity_count=2999),
        )

        self.assertFalse(attestation["bounded_completion"]["mechanism_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_small_cohort_without_monotonicity_or_scale_witness_is_rejected(self):
        with self.assertRaisesRegex(
            feasibility_guard.FeasibilityViolation, "scale witness input"
        ):
            self.build(
                "small-cohort-only mechanism",
                lambda mechanism, budget: self.bounded_result(
                    1,
                    scale_basis="adversarial_scale_witness",
                    witness_input=None,
                )
                | {
                    "scale_evidence": {
                        "basis": "adversarial_scale_witness",
                        "witness_input": None,
                        "evidence": {"cohort": "small-only"},
                    }
                },
            )

    def test_public_builder_has_no_precomputed_probe_or_grouping_parameters(self):
        with self.assertRaises(TypeError):
            feasibility_guard.build_parent_feasibility_attestation(
                parent_owner_id="fixture.owner",
                exact_claimed_invariant="invariant",
                probe_id="probe",
                probe_input={},
                completion_condition="condition",
                work_budget={
                    "unit": "expensive-evaluator-invocation",
                    "cardinality_domain": "semantic-equivalence-class",
                    "limit": 1,
                },
                proposed_mechanism="mechanism",
                unresolved_assumptions=[],
                run_counterexample_probe=lambda value: {
                    "counterexample_found": False,
                    "evidence": {},
                },
                assess_bounded_completion=lambda mechanism, budget: self.bounded_result(1),
                derive_equivalence_compression=lambda owner_input, mechanism: None,
                precomputed_counterexample_found=False,
                precomputed_equivalence_compression=self.compression(),
            )


if __name__ == "__main__":
    unittest.main()
