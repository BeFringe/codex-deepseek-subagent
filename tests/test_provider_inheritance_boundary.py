import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "check_provider_inheritance_boundary.py"
CONTRACT = ROOT / "probes" / "provider-inheritance-boundary-20260907.json"

SPEC = importlib.util.spec_from_file_location("check_provider_inheritance_boundary", SCRIPT)
check_provider_inheritance_boundary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_provider_inheritance_boundary)


class ProviderInheritanceBoundaryTests(unittest.TestCase):
    def test_contract_is_pinned_and_fail_closed(self):
        contract = check_provider_inheritance_boundary.load_contract(CONTRACT)
        result = check_provider_inheritance_boundary.qualification(contract)

        self.assertEqual(
            [source["runtime_role"] for source in contract["openai_sources"]],
            ["prior_signed_runtime", "current_signed_runtime"],
        )
        self.assertFalse(result["legacy_role_provider_override_qualified"])
        self.assertFalse(result["broker_satisfies_native_agentpath_lifecycle_contract"])
        self.assertEqual(result["p7_deepseek_regression"], "blocked-upstream")
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])
        self.assertEqual(result["phase2_state"], "closed")
        self.assertEqual(result["phase3_state"], "closed")

    def test_source_anchors_and_negative_anchor_are_checked(self):
        contract = check_provider_inheritance_boundary.load_contract(CONTRACT)
        source = contract["openai_sources"][0]
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            for anchor in source["anchors"]:
                path = source_root / anchor["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(anchor["contains"] + "\n")

            with mock.patch.object(
                check_provider_inheritance_boundary,
                "_git_identity",
                return_value=(source_root, source["source_commit"], []),
            ):
                observed, failures = check_provider_inheritance_boundary.verify_source(
                    source, source_root, "Codex test"
                )
            self.assertEqual(observed, source["source_commit"])
            self.assertEqual(failures, [])

            role = source_root / "codex-rs/core/src/agent/role.rs"
            with role.open("a", encoding="utf-8") as stream:
                stream.write("model_provider\n")
            with mock.patch.object(
                check_provider_inheritance_boundary,
                "_git_identity",
                return_value=(source_root, source["source_commit"], []),
            ):
                _, failures = check_provider_inheritance_boundary.verify_source(
                    source, source_root, "Codex test"
                )
            self.assertIn(
                "Codex test: forbidden source anchor found in codex-rs/core/src/agent/role.rs",
                failures,
            )

    def test_promoted_verdict_is_rejected(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["verdict"]["legacy_role_provider_override_qualified"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot promote"):
                check_provider_inheritance_boundary.load_contract(path)

    def test_source_role_set_must_be_exact(self):
        role, path = check_provider_inheritance_boundary._parse_codex_source(
            "current_signed_runtime=/tmp/codex"
        )
        self.assertEqual(role, "current_signed_runtime")
        self.assertEqual(path, Path("/tmp/codex"))
        with self.assertRaisesRegex(Exception, "RUNTIME_ROLE=PATH"):
            check_provider_inheritance_boundary._parse_codex_source(
                "current_signed_runtime"
            )


if __name__ == "__main__":
    unittest.main()
