from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    ROOT
    / "probes"
    / "g4-current-headless-root-lifecycle-adjudication-input-20260907.json"
)
RESULT_PATH = (
    ROOT
    / "probes"
    / "g4-current-headless-root-lifecycle-adjudication-result-20260907.json"
)
RUNTIME_INDEX_PATH = ROOT / "probes" / "codex-runtime-evidence-index.json"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4CurrentHeadlessRootLifecycleAdjudicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.input = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
        self.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        self.runtime_index = json.loads(
            RUNTIME_INDEX_PATH.read_text(encoding="utf-8")
        )

    def test_receipt_resolves_the_semantic_current_runtime(self) -> None:
        current_role = self.runtime_index["current_runtime_role"]
        current = self.runtime_index["runtime_roles"][current_role]

        self.assertEqual(current_role, "current_signed_runtime")
        self.assertEqual(self.input["runtime_role"], current_role)
        self.assertEqual(self.result["runtime_role"], current_role)
        self.assertEqual(self.input["runtime"]["codex_version"], current["codex_version"])
        self.assertEqual(
            self.input["runtime"]["base_source_commit"], current["source_commit"]
        )

    def test_result_hash_binds_the_exact_adjudication_input(self) -> None:
        digest = hashlib.sha256(INPUT_PATH.read_bytes()).hexdigest()
        identity = self.input["identity"]
        transition = self.result["transition"]
        adjudication = self.result["parent_adjudication"]

        self.assertEqual(self.result["input_evidence"]["sha256"], digest)
        self.assertEqual(adjudication["evidence_sha256"], digest)
        self.assertEqual(self.result["assignment_id"], identity["assignment_id"])
        self.assertEqual((transition["source"], transition["destination"]), ("reported", "consumed"))
        self.assertTrue(transition["active_absent_after"])
        self.assertTrue(transition["reported_absent_after"])
        self.assertTrue(transition["unresolved_absent_after"])
        self.assertTrue(transition["consumed_present_after"])
        self.assertRegex(transition["consumed_envelope_sha256"], SHA256)
        for field in (
            "location_integrity",
            "mutation_scope_integrity",
            "verification_freshness",
            "derivation_provenance_integrity",
            "feasibility_contract_integrity",
        ):
            self.assertEqual(adjudication[field], "pass")

    def test_plaintext_assignment_binds_exact_live_sessionmeta_identity(self) -> None:
        transport = self.input["assignment_transport"]
        identity = self.input["identity"]
        sessionmeta = self.input["sessionmeta"]

        self.assertEqual(
            transport["assignment_message_sha256"], identity["assignment_sha256"]
        )
        self.assertFalse(transport["encrypted_assignment_marker_present"])
        self.assertTrue(transport["plaintext_assignment_hash_matches_active_capsule"])
        self.assertEqual(
            transport["spawn_output_canonical_agent_path"],
            identity["canonical_agent_path"],
        )
        self.assertEqual(
            sessionmeta["child_source_parent_thread_id"],
            identity["parent_thread_id"],
        )
        self.assertEqual(
            sessionmeta["child_source_agent_path"], identity["canonical_agent_path"]
        )
        self.assertEqual(
            sessionmeta["child_source_agent_role"], identity["agent_type"]
        )
        self.assertEqual(sessionmeta["root_cli_version"], sessionmeta["child_cli_version"])
        self.assertEqual(identity["runtime_session_id"], identity["parent_thread_id"])

    def test_subagentstop_rejects_then_accepts_exact_attestation(self) -> None:
        chain = self.input["live_chain"]

        self.assertEqual((chain["sequence_start"], chain["sequence_end"]), (1052, 1056))
        self.assertEqual(chain["stop_attempts"], 2)
        self.assertEqual(
            chain["first_stop_error_code"],
            "TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION",
        )
        self.assertEqual(
            set(chain["first_stop_missing_fields"]),
            {
                "branch",
                "changed_paths",
                "git_status_short",
                "head",
                "index_changed",
                "inventory_summaries",
            },
        )
        self.assertNotEqual(chain["first_final_sha256"], chain["corrected_final_sha256"])
        self.assertRegex(chain["accepted_subagent_stop_receipt_sha256"], SHA256)
        self.assertRegex(chain["chain_sha256_after"], SHA256)
        self.assertNotEqual(
            chain["accepted_subagent_stop_receipt_sha256"],
            chain["chain_sha256_after"],
        )
        self.assertFalse(chain["raw_payload_stored"])

    def test_callback_is_observed_without_overclaiming_wait_receiver_identity(self) -> None:
        callback = self.input["callback_and_wait"]

        self.assertEqual(callback["completion_activity_kind"], "completed")
        self.assertEqual(
            callback["completion_activity_agent_path"],
            self.input["identity"]["canonical_agent_path"],
        )
        self.assertEqual(
            callback["completion_activity_child_thread_id"],
            self.input["identity"]["child_thread_id"],
        )
        self.assertFalse(callback["wait_timed_out"])
        self.assertEqual(callback["wait_event_receiver_thread_ids"], [])
        self.assertFalse(callback["wait_event_receiver_identity_exact"])

    def test_current_live_progress_does_not_open_direct_write(self) -> None:
        verdict = self.result["scope_verdict"]
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        result_path = (
            "probes/"
            "g4-current-headless-root-lifecycle-adjudication-result-20260907.json"
        )

        self.assertTrue(verdict["current_runtime_root_read_only_assignment_consumed"])
        self.assertTrue(verdict["current_runtime_plaintext_spawn_observed"])
        self.assertTrue(verdict["current_runtime_subagentstart_identity_bound"])
        self.assertFalse(verdict["wait_receiver_identity_exact"])
        self.assertFalse(verdict["identity_cohort_complete"])
        self.assertFalse(verdict["paired_delivery_contract_complete"])
        self.assertFalse(verdict["mutation_negative_space_complete"])
        self.assertFalse(verdict["strong_global_quiescence_complete"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertIn(result_path, gates["P1"]["evidence"])
        self.assertEqual(gates["P1"]["state"], "qualified")
        for gate_id in ("P2", "P3", "P4", "P5b", "P6", "P6a", "P6b"):
            self.assertIn(result_path, gates[gate_id]["evidence"])
        for gate_id in ("P2", "P3", "P5b", "P6", "P6a", "P6b"):
            self.assertEqual(gates[gate_id]["state"], "qualified")
        self.assertEqual(gates["P4"]["state"], "partial")
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])
        self.assertEqual(status["phase2"]["state"], "closed")
        self.assertEqual(status["phase3"]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
