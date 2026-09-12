import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "adjudicate_phase1_completion.py"
SPEC = importlib.util.spec_from_file_location("adjudicate_phase1_completion", SCRIPT)
adjudicator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(adjudicator)


class Phase1CompletionAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.paths = dict(adjudicator.DEFAULTS)
        source = adjudicator.read_json(self.paths["source"])
        self.source_identity = adjudicator.expected_source_identity(
            self.paths["source"], source
        )

    def valid_windows_receipt(self):
        # This is a schema/negative-space fixture, never a live evidence receipt.
        return {
            "schema": 1,
            "classification": "p7_windows_current_candidate_writer_live_evidence",
            "platform": {"system": "Windows", "machine": "AMD64"},
            "source": {
                **self.source_identity,
                "candidate_sha256": "a" * 64,
            },
            "provider_boundary": {
                "parent_provider": "openai",
                "parent_auth": "current_chatgpt_login",
                "child_provider": "deepseek",
                "credential_present": True,
                "credential_values_recorded": False,
                "parent_provider_routed_through_project": False,
            },
            "rust_validation": {
                "targeted_all_passed": True,
                "patch_regressions": 0,
            },
            "deterministic_schedules": {
                "all_passed": True,
                "schedule_count": 6,
                "unexplained_negative_count": 0,
            },
            "parent_same_path_negative": {
                "pretool_decision": "deny",
                "posttool_observation_count": 0,
                "durable_conflict_observed": True,
                "child_writer_claim_preserved": True,
            },
            "foreign_path_negative": {
                "pretool_decision": "deny",
                "posttool_observation_count": 0,
                "foreign_dirty_bytes_preserved": True,
                "authority_revoked": True,
                "disk_barriers_verified": True,
                "session_loop_terminated": True,
                "tracked_process_termination_confirmed": True,
                "closed_catalog_actor_quiescence_claimed": True,
                "child_absent_after_close": True,
            },
            "final_positive": {
                "callback_exact": True,
                "custom_tool_call_output_paired": True,
                "feasibility_bound_before_dispatch": True,
                "post_termination_barrier_interval_ns": 2_000_000_000,
                "disk_barriers_exact_and_stable": True,
                "session_loop_terminated": True,
                "tracked_process_termination_confirmed": True,
                "closed_catalog_actor_quiescence_claimed": True,
                "child_absent_after_close": True,
                "in_flight_authority_empty": True,
                "authority_consumed": True,
                "exact_closed_writer_run_qualified": True,
            },
            "provider_free_regression": {
                "tests_run": 100,
                "passed": 96,
                "skipped": 4,
                "failed": 0,
                "windows_equivalence_cases": 85,
                "windows_equivalence_passed": 85,
            },
            "scope_decision": {
                "windows_current_candidate_qualified": True,
                "p7_complete": False,
                "phase1_complete": False,
                "direct_write_qualified": False,
                "phase2_state": "closed",
                "phase3_state": "closed",
            },
        }

    def adjudicate(self, receipt, directory):
        path = Path(directory) / "windows-compact.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        paths = dict(self.paths)
        paths["windows"] = path
        return adjudicator.adjudicate(paths)

    def test_exact_contract_is_promotion_ready_without_self_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.adjudicate(self.valid_windows_receipt(), directory)

        self.assertTrue(result["promotion_ready"])
        self.assertFalse(result["status_already_promoted"])
        self.assertEqual(result["source_identity"], self.source_identity)
        self.assertNotEqual(
            result["candidate_sha256"]["darwin_arm64"],
            result["candidate_sha256"]["windows_amd64"],
        )

    def test_source_patch_drift_fails_closed(self):
        receipt = self.valid_windows_receipt()
        receipt["source"]["patch_sha256"] = "b" * 64

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                adjudicator.AdjudicationError, "source identity drifted"
            ):
                self.adjudicate(receipt, directory)

    def test_missing_foreign_mutation_barrier_fails_closed(self):
        receipt = self.valid_windows_receipt()
        receipt["foreign_path_negative"]["foreign_dirty_bytes_preserved"] = False

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                adjudicator.AdjudicationError, "foreign_dirty_bytes_preserved"
            ):
                self.adjudicate(receipt, directory)

    def test_windows_receipt_cannot_self_promote_phase_one(self):
        receipt = self.valid_windows_receipt()
        receipt["scope_decision"]["phase1_complete"] = True

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                adjudicator.AdjudicationError, "must not self-promote"
            ):
                self.adjudicate(receipt, directory)

    def test_compact_receipt_rejects_originating_host_paths(self):
        receipt = self.valid_windows_receipt()
        receipt["raw_artifact"] = "C:\\Users\\Example\\private\\manifest.json"

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                adjudicator.AdjudicationError, "leaks a host path"
            ):
                self.adjudicate(receipt, directory)

    def test_status_boolean_cannot_jump_ahead_of_p7(self):
        status = json.loads(self.paths["status"].read_text(encoding="utf-8"))
        status["phase1"]["declared_complete"] = True
        status["phase1"]["declared_direct_write_qualified"] = True

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            status_path = directory / "status.json"
            status_path.write_text(json.dumps(status), encoding="utf-8")
            paths = copy.copy(self.paths)
            paths["status"] = status_path
            windows_path = directory / "windows.json"
            windows_path.write_text(
                json.dumps(self.valid_windows_receipt()), encoding="utf-8"
            )
            paths["windows"] = windows_path

            with self.assertRaisesRegex(
                adjudicator.AdjudicationError, "declared Phase 1 completion"
            ):
                adjudicator.adjudicate(paths)


if __name__ == "__main__":
    unittest.main()
