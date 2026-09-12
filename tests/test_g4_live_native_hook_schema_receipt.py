import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "probes" / "g4-live-native-hook-schema-20260817.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OID = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")


class G4LiveNativeHookSchemaReceiptTests(unittest.TestCase):
    def test_live_schema_receipt_is_exact_and_fail_closed(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))

        self.assertEqual(record["schema"], 1)
        self.assertEqual(record["codex_version"], "0.148.0-alpha.9")
        self.assertEqual(record["branch"], "main")
        self.assertEqual(record["model_provider"], "openai")

        control = record["pretool_positive_control"]
        self.assertTrue(control["hook_scope_exact"])
        self.assertFalse(control["raw_payload_stored"])
        tools = {value["tool_name"]: value for value in control["observed_tools"]}
        self.assertEqual(tools["Bash"]["input_shape"], {"command": "string"})
        self.assertEqual(
            tools["collaborationspawn_agent"]["input_shape"],
            {
                "agent_type": "string",
                "fork_turns": "string",
                "message": "string",
                "task_name": "string",
            },
        )
        self.assertEqual(
            tools["collaborationwait_agent"]["input_shape"],
            {"timeout_ms": "integer"},
        )

        opaque = record["opaque_spawn_message"]
        hook = opaque["hook_message_fingerprint"]
        rollout = opaque["rollout_function_call_message_fingerprint"]
        plaintext = opaque["generator_plaintext_assignment_fingerprint"]
        self.assertEqual(hook, rollout)
        self.assertNotEqual(hook["sha256"], plaintext["sha256"])
        self.assertNotEqual(hook["length"], plaintext["length"])
        self.assertEqual(
            (hook["authority_begin_count"], hook["authority_end_count"]),
            (0, 0),
        )
        self.assertEqual(
            (
                plaintext["authority_begin_count"],
                plaintext["authority_end_count"],
            ),
            (1, 1),
        )
        self.assertFalse(opaque["raw_message_stored"])
        self.assertEqual(
            opaque["capture_result_with_strict_matcher"],
            "blocked_missing_exact_authority_declaration",
        )

        start = record["subagentstart_schema"]
        self.assertEqual(
            start["parent_runtime_session_id"], start["parent_thread_id"]
        )
        self.assertEqual(
            start["canonical_agent_path"], "/root/g4_cli_root_identity_10"
        )
        self.assertEqual(start["child_final_result"], "TASK.CONTEXT_LOST")
        self.assertEqual(start["child_function_call_count"], 0)
        self.assertEqual(start["plaintext_assignment_fields_present"], [])
        self.assertNotIn("message", start["hook_input_shape"])
        self.assertNotIn("prompt", start["hook_input_shape"])
        self.assertIn("agent_id", start["hook_input_shape"])
        self.assertIn("session_id", start["hook_input_shape"])
        self.assertIn("transcript_path", start["hook_input_shape"])
        lifecycle = start["lifecycle_receipts"]
        self.assertEqual(
            [(value["sequence"], value["hook_event_name"]) for value in lifecycle],
            [(230, "SubagentStart"), (231, "SubagentStop")],
        )
        self.assertTrue(all(value["scope"] == "target_child" for value in lifecycle))

        arm = record["diagnostic_arm"]
        self.assertEqual(arm["enabled_events"], ["SubagentStart"])
        self.assertFalse(arm["current_arm_present_after_probe"])
        restoration = record["live_restoration"]
        self.assertFalse(restoration["trusted_hook_command_changed_after_probe"])
        self.assertFalse(restoration["temporary_observer_overlay_active"])

        privacy = record["privacy"]
        self.assertTrue(all(value is False for value in privacy.values()))
        verification = record["fresh_verification"]
        self.assertEqual(
            verification["provider_free_tests"]["status"], "passed"
        )
        self.assertEqual(verification["provider_free_tests"]["count"], 251)
        self.assertEqual(
            verification["phase1_g4_gate"]["require_complete_exit_code"], 2
        )
        self.assertEqual(
            verification["mutation_surface_matrix"]["anchor_failure_count"], 0
        )
        self.assertEqual(
            verification["mutation_surface_matrix"]["require_qualified_exit_code"],
            2,
        )
        self.assertFalse(verification["same_uid_trust"]["rollout_protected"])
        self.assertFalse(verification["same_uid_trust"]["state_protected"])
        callback = verification["global_callback_audit"]
        self.assertEqual(callback["pending_callback_count"], 1)
        self.assertFalse(callback["belongs_to_current_runtime_session"])
        self.assertEqual(callback["require_complete_callbacks_exit_code"], 2)
        verdict = record["verdict"]
        self.assertTrue(verdict["pretool_agent_control_visible"])
        self.assertTrue(verdict["exact_sessionmeta_identity_visible"])
        self.assertFalse(verdict["plaintext_assignment_visible_pretool"])
        self.assertFalse(verdict["plaintext_assignment_visible_subagentstart"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2"], "closed")
        self.assertEqual(verdict["phase3"], "closed")

        self.assertTrue(
            all(GIT_OID.fullmatch(value) for value in record["source_heads"].values())
        )
        self.assertTrue(
            GIT_OID.fullmatch(
                verification["mutation_surface_matrix"]["source_commit"]
            )
        )
        hashes = [
            control["rollout_sha256"],
            *[
                value[key]
                for value in control["observed_tools"]
                for key in ("receipt_sha256", "receipt_file_sha256")
            ],
            hook["sha256"],
            rollout["sha256"],
            plaintext["sha256"],
            opaque["schema_receipt_sha256"],
            opaque["schema_receipt_file_sha256"],
            opaque["parent_rollout_sha256"],
            start["schema_receipt_sha256"],
            start["schema_receipt_file_sha256"],
            start["parent_rollout_sha256"],
            start["child_rollout_sha256"],
            *[value["receipt_sha256"] for value in lifecycle],
            start["lost_record_file_sha256"],
            arm["arm_sha256"],
            arm["history_file_sha256"],
            restoration["hooks_json_sha256"],
            *restoration["source_matches_installed_sha256"].values(),
            verification["global_callback_audit"]["chain_sha256"],
        ]
        self.assertTrue(all(SHA256.fullmatch(value) for value in hashes))


if __name__ == "__main__":
    unittest.main()
