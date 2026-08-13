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
provenance_guard = load_module(
    "provenance_guard", REPO / "hooks" / "provenance_guard.py"
)


class ProvenanceGuardTests(unittest.TestCase):
    def setUp(self):
        self.policy = {
            "authoritative_input_owners": ["fixture.owner"],
            "authoritative_input_roots": ["inputs"],
            "forbidden_caller_supplied_derived_facts": ["oracle_obligations"],
            "test_only_injection_seams": ["fixture.inject_oracle"],
            "required_derivation_boundary": "fixture.owner.derive",
        }
        self.derivations = []

        def derive(raw):
            self.derivations.append(raw)
            return {"oracle_obligations": [f"must-cover:{raw['source']}"]}

        self.operation = provenance_guard.OwnerInternalOperation(
            self.policy,
            input_owner="fixture.owner",
            input_roots=["inputs"],
            derivation_boundary="fixture.owner.derive",
            derive=derive,
            build_payloads=lambda raw, facts: [
                {"format": "first", "result": "PASS", "source": raw["source"]},
                {"format": "second", "result": "PASS", "count": len(facts["oracle_obligations"])},
            ],
        )

    def test_hash_valid_output_from_caller_forged_authority_is_rejected(self):
        forged_facts = {"oracle_obligations": []}
        forged = [
            provenance_guard.self_consistent_artifact(
                {"format": "first", "result": "PASS", "source": "authoritative"},
                forged_facts,
            ),
            provenance_guard.self_consistent_artifact(
                {"format": "second", "result": "PASS", "count": 0},
                forged_facts,
            ),
        ]
        self.assertTrue(
            all(
                artifact["digest"]
                == provenance_guard.artifact_digest(
                    artifact["payload"], artifact["derived_facts"]
                )
                for artifact in forged
            )
        )

        with self.assertRaisesRegex(
            provenance_guard.ProvenanceViolation,
            "not derived from authoritative owner input",
        ):
            self.operation.verify_real({"source": "authoritative"}, forged)

    def test_owner_internal_multi_output_derives_once_and_shares_privately(self):
        artifacts, receipt = self.operation.build_real({"source": "authoritative"})

        self.assertEqual(self.derivations, [{"source": "authoritative"}])
        self.assertEqual(artifacts[0]["derived_facts"], artifacts[1]["derived_facts"])
        self.assertEqual(receipt["derived_fact_origin"], "owner_internal")

    def test_test_only_injection_is_explicitly_non_final(self):
        artifacts = self.operation.build_test_only(
            {"source": "fixture"},
            injection_seam="fixture.inject_oracle",
            injected_derived_facts={"oracle_obligations": []},
        )

        self.assertTrue(all(artifact["non_final"] for artifact in artifacts))
        with self.assertRaisesRegex(
            provenance_guard.ProvenanceViolation,
            "not derived from authoritative owner input",
        ):
            self.operation.verify_real({"source": "fixture"}, artifacts)

    def test_real_mode_api_has_no_precomputed_derived_fact_parameter(self):
        with self.assertRaises(TypeError):
            self.operation.build_real(
                {"source": "authoritative"},
                injected_derived_facts={"oracle_obligations": []},
            )


if __name__ == "__main__":
    unittest.main()
