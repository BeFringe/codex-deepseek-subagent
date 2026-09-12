import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "check_codex_lifecycle_sources.py"
HISTORICAL_CONTRACT = (
    ROOT / "probes" / "codex-0.150.0-alpha.8-lifecycle-sources.json"
)

SPEC = importlib.util.spec_from_file_location("check_codex_lifecycle_sources", SCRIPT)
check_codex_lifecycle_sources = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_codex_lifecycle_sources)

RELEASE_INDEX = check_codex_lifecycle_sources.load_index()
CURRENT_RUNTIME = check_codex_lifecycle_sources.runtime_identity(RELEASE_INDEX)
CONTRACT = check_codex_lifecycle_sources.evidence_path(
    RELEASE_INDEX, "lifecycle_sources"
)


class CodexLifecycleSourceTests(unittest.TestCase):
    def test_current_runtime_contract_does_not_promote_live_evidence(self):
        contract = check_codex_lifecycle_sources.load_contract(CONTRACT)
        result = check_codex_lifecycle_sources.qualification(contract)

        self.assertEqual(RELEASE_INDEX["current_runtime_role"], "current_signed_runtime")
        self.assertEqual(contract["codex_version"], CURRENT_RUNTIME["codex_version"])
        self.assertEqual(contract["source_commit"], CURRENT_RUNTIME["source_commit"])
        self.assertTrue(result["hook_schema_source_verified"])
        self.assertTrue(result["sessionmeta_flush_source_verified"])
        self.assertTrue(result["canonical_agentpath_source_verified"])
        self.assertTrue(result["resume_identity_source_verified"])
        self.assertTrue(result["internal_subagent_resume_identity_supported"])
        self.assertFalse(result["v2_root_resume_reopens_descendants"])
        self.assertFalse(result["live_sessionmeta_identity_qualified"])
        self.assertFalse(result["termination_quiescence_qualified"])
        self.assertFalse(result["phase1_complete"])
        self.assertFalse(result["direct_write_qualified"])

    def test_prior_runtime_contract_remains_historical_replay_evidence(self):
        contract = check_codex_lifecycle_sources.load_contract(HISTORICAL_CONTRACT)
        prior = check_codex_lifecycle_sources.runtime_identity(
            RELEASE_INDEX, "prior_signed_runtime"
        )

        self.assertEqual(contract["codex_version"], prior["codex_version"])
        self.assertEqual(contract["source_commit"], prior["source_commit"])

    def test_every_source_anchor_is_verified(self):
        contract = check_codex_lifecycle_sources.load_contract(CONTRACT)
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir)
            for anchor in contract["anchors"]:
                path = source_root / anchor["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(anchor["contains"] + "\n")

            with mock.patch.object(
                check_codex_lifecycle_sources,
                "_git_identity",
                return_value=(source_root, contract["source_commit"], []),
            ):
                observed, failures = check_codex_lifecycle_sources.verify_source(
                    contract, source_root
                )
            self.assertEqual(observed, contract["source_commit"])
            self.assertEqual(failures, [])

            path = source_root / contract["anchors"][0]["path"]
            path.write_text("drifted\n", encoding="utf-8")
            with mock.patch.object(
                check_codex_lifecycle_sources,
                "_git_identity",
                return_value=(source_root, contract["source_commit"], []),
            ):
                _, failures = check_codex_lifecycle_sources.verify_source(
                    contract, source_root
                )
            self.assertIn("source anchor drifted: app_server_hook_event_enum", failures)

    def test_live_promotion_is_rejected(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["verdict"]["live_sessionmeta_identity_qualified"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot promote"):
                check_codex_lifecycle_sources.load_contract(path)


if __name__ == "__main__":
    unittest.main()
