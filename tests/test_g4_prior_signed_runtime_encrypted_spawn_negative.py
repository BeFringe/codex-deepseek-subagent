import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = (
    ROOT
    / "probes"
    / "g4-prior-signed-runtime-encrypted-spawn-negative-20260907.json"
)
STATUS = ROOT / "probes" / "phase1-g4-status.json"
RUNTIME_INDEX = ROOT / "probes" / "codex-runtime-evidence-index.json"


class PriorSignedRuntimeEncryptedSpawnNegativeTests(unittest.TestCase):
    def test_receipt_is_privacy_minimized_and_fail_closed(self):
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        runtime_index = json.loads(RUNTIME_INDEX.read_text(encoding="utf-8"))
        prior_identity = runtime_index["runtime_roles"]["prior_signed_runtime"]

        self.assertEqual(receipt["schema"], 1)
        self.assertEqual(receipt["codex"]["runtime_role"], "prior_signed_runtime")
        self.assertEqual(receipt["codex"]["cli_version"], prior_identity["codex_version"])
        self.assertEqual(receipt["codex"]["source_commit"], prior_identity["source_commit"])
        self.assertFalse(receipt["codex"]["gui_candidate_selected"])
        self.assertEqual(receipt["invocation"]["caller_plaintext_authority_begin_count"], 1)
        self.assertEqual(receipt["invocation"]["caller_plaintext_authority_end_count"], 1)
        self.assertEqual(receipt["invocation"]["rollout_message"]["prefix"], "gAAAAAB")
        self.assertEqual(receipt["invocation"]["rollout_message"]["authority_begin_count"], 0)
        self.assertEqual(receipt["invocation"]["rollout_message"]["authority_end_count"], 0)
        self.assertFalse(receipt["invocation"]["rollout_message"]["raw_value_stored"])
        self.assertTrue(receipt["result"]["blocked_before_handler"])
        self.assertFalse(receipt["result"]["child_started"])
        self.assertFalse(receipt["result"]["subagent_start_observed"])
        self.assertEqual(receipt["result"]["post_attempt_agent_paths"], ["/root"])
        self.assertFalse(receipt["git_barrier"]["disk_changed"])
        self.assertFalse(receipt["security"]["credential_values_read_or_recorded"])
        self.assertFalse(receipt["verdict"]["pretool_plaintext_assignment_visible"])
        self.assertFalse(receipt["verdict"]["phase1_complete"])
        self.assertFalse(receipt["verdict"]["direct_write_qualified"])

    def test_p1_status_names_the_prior_signed_runtime_negative(self):
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        p1 = next(gate for gate in status["phase1"]["gates"] if gate["id"] == "P1")

        self.assertIn(
            "probes/g4-prior-signed-runtime-encrypted-spawn-negative-20260907.json",
            p1["evidence"],
        )
        self.assertEqual(p1["state"], "qualified")
        self.assertIn(
            "probes/p1-live-plaintext-same-message-pairs-20260909.json",
            p1["evidence"],
        )
        self.assertTrue(status["phase1"]["declared_complete"])


if __name__ == "__main__":
    unittest.main()
