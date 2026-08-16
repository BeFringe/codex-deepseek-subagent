import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "check_native_assignment_seam.py"
CONTRACT = (
    ROOT / "probes" / "codex-0.148.0-alpha.9-native-assignment-seam.json"
)

SPEC = importlib.util.spec_from_file_location("check_native_assignment_seam", SCRIPT)
check_native_assignment_seam = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_native_assignment_seam)


class NativeAssignmentSeamTests(unittest.TestCase):
    def test_contract_is_pinned_and_fail_closed(self):
        contract = check_native_assignment_seam.load_contract(CONTRACT)
        result = check_native_assignment_seam.qualification(contract)

        self.assertEqual(contract["codex_version"], "0.148.0-alpha.9")
        self.assertEqual(
            contract["source_commit"],
            "9392c3fa5bcda342b5b96a1a04d67b2f781617c2",
        )
        self.assertIn(
            "encrypted Responses parameter", contract["behavior"]["schema_policy"]
        )
        self.assertFalse(
            contract["official_upstream"]["mainline_plaintext_config_switch_observed"]
        )
        self.assertFalse(result["plaintext_assignment_seam_qualified"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])
        self.assertIn("opaque", result["blocker"])

    def test_source_anchors_and_causal_order_are_checked(self):
        contract = check_native_assignment_seam.load_contract(CONTRACT)
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            fragments = {}
            for check in contract["order_checks"]:
                fragments.setdefault(check["path"], []).extend(
                    [check["before"], check["after"]]
                )
            for anchor in contract["anchors"]:
                fragments.setdefault(anchor["path"], []).append(anchor["contains"])
            for relative, values in fragments.items():
                path = source_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(values), encoding="utf-8")

            with mock.patch.object(
                check_native_assignment_seam,
                "_git_head",
                return_value=(contract["source_commit"], None),
            ):
                observed_head, failures = check_native_assignment_seam.verify_source(
                    contract, source_root
                )

            self.assertEqual(observed_head, contract["source_commit"])
            self.assertEqual(failures, [])

            registry = source_root / "codex-rs/core/src/tools/registry.rs"
            registry.write_text(
                registry.read_text(encoding="utf-8").replace(
                    "handle_any_tool(tool.as_ref(), invocation_for_tool).await", ""
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                check_native_assignment_seam,
                "_git_head",
                return_value=(contract["source_commit"], None),
            ):
                _, failures = check_native_assignment_seam.verify_source(
                    contract, source_root
                )
            self.assertIn("source order drifted: pretool_before_handler", failures)

    def test_invalid_completion_claim_is_rejected(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["verdict"]["direct_write_qualified"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot qualify direct write"):
                check_native_assignment_seam.load_contract(path)


if __name__ == "__main__":
    unittest.main()
