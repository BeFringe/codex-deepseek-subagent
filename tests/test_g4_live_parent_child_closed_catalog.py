from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-parent-child-closed-catalog-source-candidate.json"
)
SOURCE_PATCH = (
    ROOT
    / "probes"
    / "current-signed-runtime-g4-parent-child-closed-catalog-source-candidate.patch"
)
RECEIPT = ROOT / "probes" / "g4-live-parent-child-closed-catalog-20260909.json"
ADJUDICATION = (
    ROOT
    / "probes"
    / "g4-live-parent-child-closed-catalog-parent-adjudication-20260909.json"
)
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class G4LiveParentChildClosedCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))

    def test_incremental_source_patch_is_hash_bound_and_narrow(self):
        reconstruction = self.source["reconstruction"]
        self.assertEqual(
            reconstruction["patch_sha256"],
            hashlib.sha256(SOURCE_PATCH.read_bytes()).hexdigest(),
        )
        self.assertEqual(reconstruction["incremental_changed_paths"], 3)
        self.assertFalse(reconstruction["cargo_lock_included"])
        self.assertEqual(reconstruction["forward_apply_to_predecessor"], "pass")
        self.assertEqual(reconstruction["reverse_apply_on_candidate"], "pass")
        patch = SOURCE_PATCH.read_text(encoding="utf-8")
        for token in (
            "stderr-v2-parent-child-closed",
            "exact_g4_qualification_parent",
            "g4_qualification_parent_tool_allowed",
            "exact_g4_qualification_parent_has_direct_closed_tool_catalog",
        ):
            self.assertIn(token, patch)

    def test_exact_runtime_identity_uses_native_openai_parent_and_child(self):
        runtime = self.receipt["runtime"]
        identity = self.receipt["identity"]
        self.assertEqual(runtime["parent_model_provider"], "openai")
        self.assertEqual(runtime["child_model_provider"], "openai")
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["credential_value_observed"])
        self.assertEqual(runtime["candidate_exit_code"], 0)
        self.assertEqual(identity["parent_thread_id"], identity["runtime_session_id"])
        self.assertNotEqual(identity["parent_thread_id"], identity["child_thread_id"])
        self.assertEqual(identity["requested_task_name"], "g4_parent_closed_catalog_1")
        self.assertEqual(
            identity["canonical_agent_path"], "/root/g4_parent_closed_catalog_1"
        )

    def test_parent_and_child_final_catalogs_are_closed_and_stable(self):
        catalogs = self.receipt["runtime_tool_catalog"]
        parent = catalogs["parent"]
        child = catalogs["child"]
        self.assertEqual(catalogs["total_receipt_count"], 8)
        self.assertEqual(parent["receipt_count"], 6)
        self.assertEqual(child["receipt_count"], 2)
        self.assertTrue(parent["receipts_byte_identical"])
        self.assertTrue(child["receipts_byte_identical"])
        self.assertRegex(parent["canonical_receipt_sha256"], SHA256_RE)
        self.assertRegex(child["canonical_receipt_sha256"], SHA256_RE)
        self.assertEqual(parent["tool_mode"], "direct")
        self.assertEqual(child["tool_mode"], "direct")
        self.assertEqual(parent["code_mode_tool_names"], {})
        self.assertEqual(child["code_mode_tool_names"], {})
        self.assertTrue(parent["can_manage_children"])
        self.assertFalse(child["can_manage_children"])
        self.assertEqual(
            parent["registered_tools"],
            [
                "apply_patch",
                "g4_assignment.close_agent",
                "g4_assignment.followup_task",
                "g4_assignment.interrupt_agent",
                "g4_assignment.list_agents",
                "g4_assignment.send_message",
                "g4_assignment.spawn_agent",
                "g4_assignment.wait_agent",
                "view_image",
            ],
        )
        self.assertEqual(
            child["registered_tools"],
            ["apply_patch", "g4_assignment.list_agents", "view_image"],
        )
        for removed in ("exec_command", "write_stdin", "code_mode", "MCP/app"):
            self.assertIn(removed, catalogs["removed_from_both"])

    def test_parent_denial_is_inside_exact_child_writer_lease(self):
        chain = self.receipt["hook_chain"]
        sequences = chain["sequences"]
        self.assertEqual(
            list(sequences.values()),
            list(range(sequences["spawn_pretool"], sequences["subagent_stop"] + 1)),
        )
        self.assertEqual(
            chain["child_pretool_tool_use_id"],
            chain["child_posttool_tool_use_id"],
        )
        self.assertTrue(chain["parent_denial_before_child_posttool"])
        self.assertTrue(chain["parent_denial_before_child_release"])
        conflict = self.receipt["parent_conflict"]
        writer = self.receipt["writer_receipt"]
        self.assertEqual(conflict["failure_code"], "TASK.WRITER_LEASE_BLOCKED")
        self.assertTrue(conflict["pre_execution"])
        self.assertEqual(conflict["conflicting_kinds"], ["writer_claim", "active"])
        self.assertLess(
            datetime.fromisoformat(conflict["observed_at"]),
            datetime.fromisoformat(writer["released_at"]),
        )
        self.assertEqual(conflict["parent_retry_count"], 0)

    def test_posttool_stop_callback_and_disk_barrier_are_hash_bound(self):
        writer = self.receipt["writer_receipt"]
        terminal = self.receipt["terminal_and_callback"]
        disk = self.receipt["probe_root_final_disk"]
        self.assertEqual(
            writer["receipt_sha256"], writer["final_derivation_receipt_sha256"]
        )
        self.assertEqual(
            terminal["child_final_sha256"],
            terminal["parent_callback_envelope_sha256"],
        )
        self.assertTrue(terminal["parent_child_final_exactly_equal"])
        self.assertTrue(terminal["accepted_subagentstop_present"])
        self.assertEqual(disk["target_bytes"], 25)
        self.assertEqual(
            disk["target_sha256"],
            "4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c",
        )
        self.assertEqual(disk["candidate_process_exact_match_count"], 0)
        self.assertEqual(disk["candidate_open_file_count"], 0)
        self.assertEqual(disk["matching_live_assignment_count"], 0)
        self.assertEqual(disk["matching_writer_claim_count"], 0)
        self.assertFalse(disk["late_write_observed"])
        self.assertFalse(disk["strong_global_quiescence_claimed"])

    def test_fresh_owner_consumed_exact_immutable_receipt(self):
        adjudication = self.adjudication
        self.assertEqual(
            adjudication["input"]["sha256"],
            hashlib.sha256(RECEIPT.read_bytes()).hexdigest(),
        )
        self.assertEqual(set(adjudication["fresh_owner"].values()), {"pass"})
        self.assertEqual(adjudication["state_transition"]["before"], "reported")
        self.assertEqual(adjudication["state_transition"]["after"], "consumed")
        self.assertFalse(
            adjudication["state_transition"]["reported_exists_after_adjudication"]
        )
        self.assertFalse(adjudication["authority"]["global_direct_write_promoted"])

    def test_status_and_receipts_remain_fail_closed(self):
        source_verdict = self.source["verdict"]
        live_verdict = self.receipt["verdict"]
        self.assertTrue(source_verdict["source_parent_final_catalog_absence_qualified"])
        self.assertTrue(
            live_verdict["runtime_final_parent_catalog_absence_qualified_for_this_exact_run"]
        )
        self.assertTrue(live_verdict["catalog_closed_actor_set_for_this_run"])
        self.assertFalse(live_verdict["strong_global_quiescence_qualified"])
        self.assertFalse(live_verdict["all_mutation_surfaces_qualified"])
        self.assertFalse(live_verdict["phase1_complete"])
        self.assertFalse(live_verdict["direct_write_qualified"])
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        self.assertFalse(status["phase1"]["declared_complete"])
        self.assertFalse(status["phase1"]["declared_direct_write_qualified"])
        gates = {gate["id"]: gate for gate in status["phase1"]["gates"]}
        lifecycle_evidence = {
            str(RECEIPT.relative_to(ROOT)),
            str(ADJUDICATION.relative_to(ROOT)),
            "tests/test_g4_live_parent_child_closed_catalog.py",
        }
        catalog_evidence = lifecycle_evidence | {
            str(SOURCE.relative_to(ROOT)),
            str(SOURCE_PATCH.relative_to(ROOT)),
        }
        for gate_id in ("P4", "P5b", "P7"):
            gate = gates[gate_id]
            self.assertTrue(catalog_evidence.issubset(set(gate["evidence"])))
        self.assertEqual(gates["P5b"]["state"], "qualified")
        for gate_id in ("P4", "P7"):
            self.assertEqual(gates[gate_id]["state"], "partial")
        for gate_id in ("P6", "P6a", "P6b"):
            gate = gates[gate_id]
            self.assertTrue(lifecycle_evidence.issubset(set(gate["evidence"])))
        for gate_id in ("P6", "P6a", "P6b"):
            self.assertEqual(gates[gate_id]["state"], "qualified")


if __name__ == "__main__":
    unittest.main()
