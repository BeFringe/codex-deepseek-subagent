import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from compatibility_state import validate_non_git_writer_receipt  # noqa: E402


RECORD = ROOT / "probes" / "g4-parent-non-git-writer-live-20260908.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4ParentNonGitWriterLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_install_changes_only_parent_writer_hook_events(self):
        installation = self.record["installation"]
        self.assertEqual(installation["authorization_ceiling"], "parent_only")
        self.assertEqual(
            installation["changed_hook_events"], ["PostToolUse", "PreToolUse"]
        )
        self.assertTrue(installation["v4_subagent_start_unchanged"])
        self.assertNotEqual(
            installation["hooks_json_sha256_before"],
            installation["hooks_json_sha256_after"],
        )
        for digest in installation["installed_source_sha256"].values():
            self.assertTrue(SHA256.fullmatch(digest))
        for name, digest in installation["rollback_backup"].items():
            if name.endswith("_sha256"):
                self.assertTrue(SHA256.fullmatch(digest))

    def test_untrusted_control_cannot_be_promoted_from_file_creation(self):
        control = self.record["pre_trust_control"]
        self.assertFalse(control["authorizing"])
        self.assertEqual(control["matching_hook_event_count"], 0)
        self.assertEqual(control["matching_non_git_writer_receipt_count"], 0)
        self.assertIn("did not prove Hook mediation", control["reason_non_authorizing"])

    def test_trusted_smoke_binds_root_identity_callback_and_file_bytes(self):
        smoke = self.record["trusted_live_smoke"]
        self.assertEqual(smoke["thread_id"], smoke["runtime_session_id"])
        self.assertEqual(smoke["canonical_agent_path"], "/root")
        self.assertEqual(smoke["agent_type"], "root")
        self.assertEqual(smoke["process_exit_code"], 0)
        self.assertEqual(smoke["inflight_claim_count_after_exit"], 0)
        chain = smoke["hook_event_chain"]
        self.assertEqual(chain["pre_tool_use"]["sequence"] + 1, chain["post_tool_use"]["sequence"])
        self.assertEqual(chain["pre_tool_use"]["event_stage"], "authorized")
        self.assertEqual(chain["post_tool_use"]["event_stage"], "callback_observed")
        receipt = validate_non_git_writer_receipt(smoke["writer_receipt"])
        self.assertEqual(receipt["actor"]["thread_id"], smoke["thread_id"])
        self.assertEqual(receipt["tool_use_id"], smoke["hook_tool_use_id"])
        state = receipt["after_snapshot"]["path_states"][0]
        self.assertEqual(state["sha256"], smoke["target_sha256"])
        self.assertEqual(state["byte_length"], smoke["target_byte_length"])

    def test_parent_temp_ceiling_does_not_promote_phase_or_child_write(self):
        verdict = self.record["verdict"]
        self.assertTrue(verdict["parent_non_git_apply_patch_surface_qualified"])
        self.assertTrue(verdict["user_authorization_is_only_a_ceiling"])
        for field in (
            "child_mutation_authority_granted",
            "git_authority_granted",
            "direct_write_qualified",
            "phase1_complete",
            "phase2_open",
            "phase3_open",
        ):
            self.assertFalse(verdict[field])


if __name__ == "__main__":
    unittest.main()
