import hashlib
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADJUDICATION = (
    ROOT / "probes" / "g4-p5b-closed-catalog-quiescence-adjudication-20260909.json"
)
SOURCE = ROOT / "probes" / "current-signed-runtime-g4-p5b-tracked-termination-source-candidate.json"
WRITE_CLOSE = ROOT / "probes" / "g4-live-write-then-close-20260909.json"
NONEMPTY = ROOT / "probes" / "g4-live-nonempty-tracked-process-termination-20260909.json"
HANDOVER = ROOT / "probes" / "g4-live-handover-cleanup-close-20260909.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"


class G4P5bClosedCatalogQuiescenceAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.write_close = json.loads(WRITE_CLOSE.read_text(encoding="utf-8"))
        cls.nonempty = json.loads(NONEMPTY.read_text(encoding="utf-8"))
        cls.handover = json.loads(HANDOVER.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_frozen_inputs_are_hash_bound(self):
        evidence = self.adjudication
        for section, path in (
            (evidence["source_evidence"], SOURCE),
            (evidence["live_mutation_actor"], WRITE_CLOSE),
            (evidence["handover_evidence"], HANDOVER),
        ):
            self.assertEqual(
                section["receipt_sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
            )
        ordering = evidence["atomic_ordering_evidence"]
        # This historical receipt binds the frozen test bytes, not subsequent
        # Windows fixture edits. The qualification base contains that exact blob.
        frozen = subprocess.run(
            ["git", "-C", str(ROOT), "show",
             "785b945d46a9a8879f659a428ff0a03d940cf7a1:" + ordering["test"]],
            capture_output=True,
        )
        if frozen.returncode != 0:
            self.skipTest("originating-host frozen test anchor is unavailable in Git history")
        self.assertEqual(
            ordering["test_sha256"],
            hashlib.sha256(frozen.stdout).hexdigest(),
        )

    def test_source_close_contract_uses_real_exit_witnesses(self):
        contract = self.source["host_contract"]
        evidence = self.adjudication["source_evidence"]
        self.assertIn("closing state", contract["admission_gate"])
        self.assertIn("rejects a later start", contract["admission_gate"])
        self.assertEqual(evidence["local_pty_exit_witness"], "exit_rx")
        self.assertEqual(
            evidence["exec_server_exit_witness"], "ExecProcessEvent::Exited"
        )
        self.assertFalse(evidence["synthetic_exit_after_kill_or_rpc_ack"])

    def test_live_write_actor_has_strong_closed_catalog_barrier(self):
        catalog = self.write_close["runtime_tool_catalog"]
        lifecycle = self.write_close["native_lifecycle"]
        close = lifecycle["close_receipt"]
        barrier = self.write_close["post_termination_barrier"]
        adjudicated = self.adjudication["live_mutation_actor"]
        self.assertTrue(catalog["catalog_closed"])
        self.assertFalse(catalog["child_process_bootstrap_tools_present"])
        self.assertEqual(catalog["child_registered_tools"], [
            "apply_patch", "g4_assignment.list_agents", "view_image"
        ])
        self.assertEqual(close["previous_status"], "running")
        self.assertTrue(close["session_loop_terminated"])
        self.assertTrue(close["model_callable_process_bootstrap_absent"])
        self.assertEqual(close["tracked_background_processes_before_close"], 0)
        self.assertTrue(close["tracked_process_termination_confirmed"])
        self.assertTrue(close["closed_catalog_actor_quiescence_claimed"])
        self.assertTrue(lifecycle["target_absent_from_post_close_tree"])
        self.assertTrue(self.write_close["write_authority"]["writer_claim_absent_after_tool"])
        self.assertEqual(len(barrier["observations"]), 2)
        self.assertFalse(barrier["late_write_observed"])
        self.assertTrue(adjudicated["post_termination_disk_stable"])

    def test_nonempty_exit_and_handover_are_complementary_not_scope_expansion(self):
        cross = self.adjudication["true_exit_cross_check"]
        nonempty_verdict = self.nonempty["verdict"]
        handover = self.adjudication["handover_evidence"]
        self.assertTrue(cross["tracked_process_nonempty"])
        self.assertTrue(cross["same_process_id_joined_across_start_close_and_exit"])
        self.assertTrue(nonempty_verdict["native_standard_worker_nonempty_tracked_process_exit_qualified"])
        self.assertFalse(cross["actor_is_exact_g4_closed_catalog_role"])
        self.assertTrue(cross["does_not_expand_g4_child_catalog"])
        self.assertTrue(self.handover["ownership_handover"]["prior_actor_quiescence_consumed_exactly_once"])
        self.assertTrue(handover["prior_barrier_consumed_exactly_once"])
        self.assertTrue(handover["replacement_exact_path_write"])
        self.assertTrue(handover["replacement_post_close_disk_stable"])

    def test_gate_is_qualified_without_overclaiming_p4_or_p7(self):
        adjudication = self.adjudication["adjudication"]
        self.assertEqual(set(adjudication.values()), {"pass"})
        verification = self.adjudication["post_record_verification"]
        self.assertEqual(verification["provider_free_suite"]["result"], "pass")
        self.assertEqual(verification["provider_free_suite"]["test_count"], 782)
        self.assertEqual(verification["provider_free_suite"]["agent_template_checks"], "pass")
        self.assertEqual(verification["phase1_normal_exit"], 0)
        self.assertEqual(verification["phase1_required_exit"], 2)
        self.assertEqual(verification["mutation_normal_exit"], 0)
        self.assertEqual(verification["mutation_required_exit"], 2)
        self.assertEqual(verification["same_uid_normal_exit"], 0)
        self.assertEqual(verification["same_uid_required_exit"], 2)
        self.assertEqual(verification["semantic_runtime_index_exit"], 0)
        verdict = self.adjudication["verdict"]
        self.assertTrue(verdict["p5b_qualified"])
        self.assertTrue(verdict["strong_exact_actor_termination_quiescence_receipt_qualified"])
        self.assertTrue(verdict["post_termination_disk_barrier_qualified"])
        self.assertTrue(verdict["exact_path_handover_qualified"])
        self.assertFalse(verdict["global_host_process_tree_quiescence_claimed"])
        self.assertFalse(verdict["p4_qualified"])
        self.assertFalse(verdict["p7_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])

        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        self.assertEqual(gates["P5b"]["state"], "qualified")
        self.assertEqual(gates["P5b"]["provider_free"], "pass")
        self.assertIn(ADJUDICATION.relative_to(ROOT).as_posix(), gates["P5b"]["evidence"])
        self.assertEqual(gates["P4"]["state"], "qualified")
        self.assertEqual(gates["P7"]["state"], "qualified")
        self.assertTrue(self.status["phase1"]["declared_complete"])
        self.assertTrue(self.status["phase1"]["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
