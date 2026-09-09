import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "probes" / "current-signed-runtime-g4-sibling-admission-source-candidate.json"
SOURCE_PATCH = ROOT / "probes" / "current-signed-runtime-g4-sibling-admission-source-candidate.patch"
LIVE = ROOT / "probes" / "g4-live-sibling-spawn-admission-20260909.json"
ADJUDICATION = ROOT / "probes" / "g4-live-sibling-spawn-admission-parent-adjudication-20260909.json"
WRAPPER = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"


class G4LiveSiblingSpawnAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.live = json.loads(LIVE.read_text(encoding="utf-8"))
        cls.adjudication = json.loads(ADJUDICATION.read_text(encoding="utf-8"))

    def test_incremental_source_patch_is_narrow_and_hash_bound(self):
        reconstruction = self.source["reconstruction"]
        self.assertEqual(reconstruction["changed_path_count"], 2)
        self.assertFalse(reconstruction["cargo_lock_included"])
        self.assertEqual(reconstruction["forward_apply_check"], "pass")
        self.assertEqual(reconstruction["reverse_apply_check"], "pass")
        self.assertEqual(
            reconstruction["patch_sha256"],
            hashlib.sha256(SOURCE_PATCH.read_bytes()).hexdigest(),
        )
        patch = SOURCE_PATCH.read_text(encoding="utf-8")
        self.assertIn("exact_g4_qualification_parent", patch)
        self.assertIn("role_name != Some(G4_QUALIFICATION_PROBE_ROLE)", patch)
        self.assertIn(
            "qualification_parent_rejects_default_and_non_g4_sibling_spawns",
            patch,
        )

    def test_native_negative_has_no_child_and_positive_preserves_exact_identity(self):
        negative = self.live["ordinary_sibling_negative"]
        identity = self.live["identity"]
        positive = self.live["exact_child_positive"]
        self.assertEqual(negative["requested_agent_type"], "worker")
        self.assertFalse(negative["denial_returned_child_thread_id"])
        self.assertFalse(negative["denial_returned_agent_path"])
        self.assertEqual(
            negative["post_denial_agent_list"],
            [{"agent_name": "/root", "agent_status": "running"}],
        )
        self.assertFalse(negative["ordinary_child_activity_event_present"])
        self.assertEqual(identity["agent_type"], "g4_qualification_probe_worker")
        self.assertEqual(identity["canonical_agent_path"], "/root/g4_sibling_admission_1")
        self.assertEqual(identity["runtime_session_id"], identity["parent_thread_id"])
        self.assertNotEqual(identity["parent_thread_id"], identity["child_thread_id"])
        self.assertTrue(positive["parent_child_final_exactly_equal"])
        self.assertTrue(positive["assigned_slice_complete"])
        self.assertFalse(positive["authority_violation"])

    def test_parent_and_child_catalogs_are_closed_for_the_exact_actor_set(self):
        catalogs = self.live["runtime_tool_catalog"]
        parent = catalogs["parent"]
        child = catalogs["child"]
        self.assertEqual(catalogs["total_receipt_count"], 7)
        self.assertTrue(parent["receipts_byte_identical"])
        self.assertTrue(child["receipts_byte_identical"])
        self.assertEqual(parent["code_mode_tool_names"], {})
        self.assertEqual(child["code_mode_tool_names"], {})
        self.assertTrue(parent["can_manage_children"])
        self.assertFalse(child["can_manage_children"])
        self.assertEqual(
            child["registered_tools"],
            ["apply_patch", "g4_assignment.list_agents", "view_image"],
        )
        for forbidden in ("exec_command", "write_stdin", "MCP", "code_mode"):
            self.assertNotIn(forbidden, parent["registered_tools"])
            self.assertNotIn(forbidden, child["registered_tools"])

    def test_hook_and_disk_receipts_do_not_depend_on_a_business_workload(self):
        hook_slice = self.live["hook_identity_slice"]
        disk = self.live["probe_root_final_disk"]
        verdict = self.live["verdict"]
        self.assertEqual(
            list(range(hook_slice["sequence_start"], hook_slice["sequence_end"] + 1)),
            [3257, 3258, 3259, 3260],
        )
        self.assertTrue(hook_slice["same_runtime_session_and_exact_child_identity"])
        self.assertEqual(disk["status_porcelain_v1"], "")
        self.assertFalse(disk["ordinary_sibling_created_files"])
        self.assertFalse(disk["target_child_created_files"])
        self.assertFalse(verdict["localcat_or_business_workload_used"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])

    def test_fresh_owner_consumes_only_the_hash_bound_live_receipt(self):
        self.assertEqual(
            self.adjudication["input"]["sha256"],
            hashlib.sha256(LIVE.read_bytes()).hexdigest(),
        )
        self.assertEqual(set(self.adjudication["fresh_owner"].values()), {"pass"})
        transition = self.adjudication["state_transition"]
        self.assertEqual((transition["before"], transition["after"]), ("reported", "consumed"))
        self.assertFalse(transition["reported_exists_after"])
        authority = self.adjudication["authority"]
        self.assertFalse(authority["localcat_or_business_workload_used"])
        self.assertFalse(authority["independent_same_uid_hostile_process_qualified"])
        self.assertFalse(authority["global_direct_write_promoted"])

    def test_wrapper_guard_is_read_only_and_narrow(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("CODEX_G4_SIBLING_SPAWN_ADMISSION_PROBE_AUTHORIZED", wrapper)
        self.assertIn("schema1-exact-g4-only", wrapper)
        self.assertIn("/private/tmp/codex-g4-sibling-admission.*", wrapper)
        self.assertIn("cannot combine with a write probe", wrapper)


if __name__ == "__main__":
    unittest.main()
