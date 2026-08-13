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
    def build(self, mechanism, assessor, *, assumptions=()):
        probes = []

        def negative_probe(probe_input):
            probes.append(probe_input)
            return {
                "counterexample_found": False,
                "evidence": {"tested_boundary": probe_input, "counterexamples": []},
            }

        attestation = feasibility_guard.build_parent_feasibility_attestation(
            parent_owner_id="fixture.owner",
            exact_claimed_invariant="mechanism closes the finite gap",
            probe_id="cheap-boundary-falsifier",
            probe_input={"gap": 17, "budget": 10},
            completion_condition="finite gap closes",
            work_budget={"unit": "step", "limit": 10},
            proposed_mechanism=mechanism,
            unresolved_assumptions=assumptions,
            run_counterexample_probe=negative_probe,
            assess_bounded_completion=assessor,
        )
        return probes, attestation

    def test_sound_but_too_loose_mechanism_is_blocked_before_dispatch(self):
        probes, attestation = self.build(
            "safe upper bound only",
            lambda mechanism, budget: {
                "mechanism_satisfies": False,
                "evidence": {"required_steps": 17, "budget": budget["limit"]},
            },
        )

        self.assertEqual(probes, [{"gap": 17, "budget": 10}])
        self.assertFalse(attestation["bounded_completion"]["mechanism_satisfies"])
        self.assertEqual(attestation["owner_decision"], "block")

    def test_independent_bound_term_can_make_final_mechanism_dispatchable(self):
        probes, attestation = self.build(
            "upper bound plus independent lower-bound term",
            lambda mechanism, budget: {
                "mechanism_satisfies": True,
                "evidence": {"required_steps": 9, "budget": budget["limit"]},
            },
        )

        self.assertEqual(len(probes), 1)
        self.assertTrue(attestation["counterexample_probe"]["executed"])
        self.assertEqual(attestation["owner_decision"], "dispatch")

    def test_blocking_unresolved_assumption_prevents_dispatch(self):
        _, attestation = self.build(
            "bounded mechanism",
            lambda mechanism, budget: {
                "mechanism_satisfies": True,
                "evidence": {"required_steps": 9},
            },
            assumptions=[{"assumption": "input remains finite", "blocking": True}],
        )

        self.assertEqual(attestation["owner_decision"], "block")

    def test_public_builder_has_no_precomputed_probe_outcome_parameter(self):
        with self.assertRaises(TypeError):
            feasibility_guard.build_parent_feasibility_attestation(
                parent_owner_id="fixture.owner",
                exact_claimed_invariant="invariant",
                probe_id="probe",
                probe_input={},
                completion_condition="condition",
                work_budget={"unit": "step", "limit": 1},
                proposed_mechanism="mechanism",
                unresolved_assumptions=[],
                run_counterexample_probe=lambda value: {
                    "counterexample_found": False,
                    "evidence": {},
                },
                assess_bounded_completion=lambda mechanism, budget: {
                    "mechanism_satisfies": True,
                    "evidence": {},
                },
                precomputed_counterexample_found=False,
            )


if __name__ == "__main__":
    unittest.main()
