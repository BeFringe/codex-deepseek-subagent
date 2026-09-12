import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "g4-live-postcompact-scope-drift-denial-20260908.json"
ADJUDICATION = (
    ROOT / "probes" / "g4-live-postcompact-scope-drift-parent-adjudication-20260908.json"
)
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LivePostcompactScopeDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
        cls.status = json.loads(STATUS.read_text(encoding="utf-8"))

    def test_real_sessionmeta_and_canonical_agentpath_are_exact(self):
        identity = self.receipt["identity"]
        authority = self.receipt["authority"]

        self.assertEqual(identity["runtime_session_id"], identity["parent_thread_id"])
        self.assertNotEqual(identity["child_thread_id"], identity["parent_thread_id"])
        self.assertEqual(identity["canonical_agent_path"], "/root/g4_postcompact_scope_drift_1")
        self.assertEqual(identity["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(authority["assignment_mutation_mode"], "read_only")
        self.assertEqual(authority["owned_paths"], [])
        self.assertEqual(authority["excluded_paths"], [])
        self.assertFalse(any(authority["git_authority"].values()))
        self.assertEqual(authority["recovery_count"], 1)
        for field in ("assignment_sha256", "capsule_sha256"):
            self.assertRegex(authority[field], SHA256)

    def test_host_injection_is_lock_ordered_between_compact_and_fourth_pretool(self):
        injection = self.receipt["host_injection"]
        chain = self.receipt["hook_chain"]
        precompact = dt.datetime.fromisoformat(chain["precompact_observed_at"])
        injected = dt.datetime.fromisoformat(injection["injected_at"])
        fourth = dt.datetime.fromisoformat(chain["fourth_pretool_observed_at"])

        self.assertLess(precompact, injected)
        self.assertLess(injected, fourth)
        self.assertTrue(injection["state_lock_held_during_injection"])
        self.assertEqual(injection["recovery_count_observed_before_injection"], 1)
        self.assertEqual(injection["before_snapshot"]["changed_paths"], [])
        self.assertEqual(
            injection["after_snapshot"]["changed_paths"],
            [
                {
                    "path": "foreign-postcompact-drift.txt",
                    "kind": "file",
                    "sha256": injection["target_sha256"],
                }
            ],
        )
        self.assertFalse(injection["child_mutation_authorized"])
        self.assertFalse(injection["injected_bytes_attributed_to_child"])

    def test_fourth_tool_is_denied_and_authority_terminates_unresolved(self):
        execution = self.receipt["child_execution"]
        termination = self.receipt["termination_evidence"]

        self.assertEqual(len(execution["native_list_agents_calls"]), 4)
        self.assertEqual(len(set(execution["native_list_agents_calls"])), 4)
        self.assertEqual(execution["child_rollout_compacted_record_count"], 1)
        self.assertLess(
            execution["child_rollout_compacted_record_ordinal"], execution["fourth_call_ordinal"]
        )
        self.assertFalse(execution["fourth_call_executed"])
        self.assertIn("foreign-postcompact-drift.txt", execution["fourth_call_denial"])
        self.assertEqual(termination["state_before_fourth_pretool"], "active")
        self.assertEqual(termination["state_after_fourth_pretool"], "unresolved")
        self.assertEqual(termination["reason"], "authority_reattestation_mismatch")
        self.assertEqual(termination["classification"], "post_attestation_authority_drift")
        self.assertEqual(
            termination["provenance_status"],
            "post_attestation_authority_drift_unattributed",
        )
        self.assertTrue(termination["mutation_blocked_before_execution"])
        self.assertTrue(termination["disk_changed"])
        self.assertFalse(termination["integration_authority_granted"])
        self.assertFalse(termination["ownership_handover_authorized"])

    def test_hook_chain_callback_disk_and_rollback_are_exact(self):
        chain = self.receipt["hook_chain"]
        execution = self.receipt["child_execution"]
        barrier = self.receipt["fresh_owner_disk_barrier"]
        overlay = self.receipt["qualification_overlay"]

        self.assertEqual(list(chain["sequences"].values()), list(range(1940, 1948)))
        self.assertEqual(chain["event_count"], 1947)
        self.assertRegex(chain["head_receipt_sha256"], SHA256)
        self.assertTrue(execution["child_task_complete"])
        self.assertTrue(execution["parent_callback_exactly_equals_final_marker"])
        self.assertEqual(execution["final_marker"], "TASK.AUTHORITY_REATTESTATION_BLOCKED")
        self.assertEqual(self.receipt["raw_runtime"]["candidate_exit_code"], 0)
        self.assertEqual(self.receipt["raw_runtime"]["injector_exit_code"], 0)
        self.assertEqual(barrier["candidate_process_count"], 0)
        self.assertFalse(barrier["late_write_observed"])
        self.assertFalse(barrier["strong_global_quiescence_claimed"])
        self.assertEqual(overlay["restored_hooks_sha256"], overlay["base_hooks_sha256"])
        self.assertTrue(overlay["v4_entries_preserved"])
        self.assertFalse(overlay["qualification_options_added"])

    def test_fresh_owner_adjudicates_frozen_negative_without_consuming_it(self):
        adjudication = self.adjudication
        transition = adjudication["state_transition"]

        self.assertEqual(
            adjudication["input"]["sha256"], hashlib.sha256(RECEIPT.read_bytes()).hexdigest()
        )
        self.assertEqual(set(adjudication["fresh_owner"].values()), {"pass"})
        self.assertEqual(transition["before"], "unresolved")
        self.assertEqual(transition["after"], "unresolved")
        self.assertEqual(
            transition["unresolved_envelope_sha256_before"],
            transition["unresolved_envelope_sha256_after"],
        )
        self.assertTrue(adjudication["authority"]["unresolved_authority_retained"])
        self.assertFalse(adjudication["authority"]["ownership_handover_authorized"])
        self.assertFalse(adjudication["authority"]["global_direct_write_promoted"])
        verification = adjudication["verification"]
        self.assertEqual(verification["provider_free_suite"]["test_count"], 589)
        self.assertEqual(verification["provider_free_suite"]["exit_code"], 0)
        self.assertEqual(verification["phase1_gate_normal_exit_code"], 0)
        self.assertEqual(verification["phase1_gate_require_complete_exit_code"], 2)
        self.assertEqual(verification["mutation_matrix_blocker_count"], 13)
        self.assertFalse(verification["same_uid_rollout_protected"])
        self.assertFalse(verification["same_uid_state_protected"])

    def test_p5_qualifies_without_inventing_process_restart_child_resume(self):
        verdict = self.receipt["verdict"]
        gates = {gate["id"]: gate for gate in self.status["phase1"]["gates"]}
        receipt_path = "probes/g4-live-postcompact-scope-drift-denial-20260908.json"
        adjudication_path = (
            "probes/g4-live-postcompact-scope-drift-parent-adjudication-20260908.json"
        )

        for gate_id in ("P1", "P2", "P3", "P4", "P5", "P5b", "P6", "P6a", "P7"):
            self.assertIn(receipt_path, gates[gate_id]["evidence"])
            self.assertIn(adjudication_path, gates[gate_id]["evidence"])
        self.assertTrue(verdict["postcompact_scope_expansion_negative_live_qualified"])
        self.assertFalse(verdict["process_restart_resume_qualified"])
        self.assertFalse(verdict["strong_global_quiescence_qualified"])
        self.assertEqual(gates["P5"]["state"], "qualified")
        self.assertEqual(gates["P5"]["provider_free"], "pass")
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertTrue(self.status["phase1"]["declared_complete"])
        self.assertTrue(self.status["phase1"]["declared_direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
