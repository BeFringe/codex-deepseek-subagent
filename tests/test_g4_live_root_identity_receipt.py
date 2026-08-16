import json
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / "probes" / "g4-live-root-identity-20260817.json"


class G4LiveRootIdentityReceiptTests(unittest.TestCase):
    def test_real_root_identity_record_remains_non_qualifying(self):
        record = json.loads(RECORD.read_text(encoding="utf-8"))

        self.assertEqual(record["schema"], 1)
        self.assertEqual(record["parent"]["agent_path"], "/root")
        self.assertEqual(
            record["child"]["canonical_agent_path"],
            "/root/g4_cli_root_identity_1",
        )
        self.assertEqual(
            record["child"]["parent_thread_id"], record["parent"]["thread_id"]
        )
        self.assertEqual(
            record["child"]["runtime_session_id"],
            record["parent"]["runtime_session_id"],
        )
        self.assertEqual(record["child"]["function_call_count"], 0)
        self.assertEqual(record["hook_state"]["pending_count"], 0)
        self.assertEqual(record["hook_state"]["active_count"], 0)
        self.assertEqual(record["hook_state"]["lost_count"], 1)
        self.assertIsNone(record["hook_state"]["pretooluse_tool_name_observed"])
        self.assertGreater(record["child"]["stop_continuation_count"], 1)
        self.assertFalse(
            record["parent"]["termination"]["strong_quiescence_receipt"]
        )
        self.assertFalse(record["qualification"]["phase1_complete"])
        self.assertFalse(record["qualification"]["direct_write_qualified"])
        self.assertEqual(record["qualification"]["phase2"], "closed")
        self.assertEqual(record["qualification"]["phase3"], "closed")


if __name__ == "__main__":
    unittest.main()
