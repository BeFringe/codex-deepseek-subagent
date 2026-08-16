import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))

from compatibility_state import StateStore
import subagentstart_schema_observation


class SubagentStartSchemaObservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.state = self.root / "state"
        self.transcript = self.root / "child.jsonl"
        payload = {
            "session_id": "runtime-session",
            "id": "child-thread",
            "parent_thread_id": "runtime-session",
            "timestamp": "2026-08-17T00:00:00Z",
            "cwd": str(self.repository),
            "originator": "fixture",
            "cli_version": "0.148.0-alpha.9",
            "source": {
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": "runtime-session",
                        "depth": 1,
                        "agent_path": "/root/bounded_task",
                        "agent_nickname": "Fixture",
                        "agent_role": "fixture_worker",
                    }
                }
            },
            "agent_role": "fixture_worker",
            "agent_path": "/root/bounded_task",
            "agent_nickname": "Fixture",
            "model_provider": "fixture-provider",
        }
        self.transcript.write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-17T00:00:00.070Z",
                    "type": "session_meta",
                    "payload": payload,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def hook(self):
        return {
            "hook_event_name": "SubagentStart",
            "session_id": "runtime-session",
            "agent_id": "child-thread",
            "agent_type": "fixture_worker",
            "transcript_path": str(self.transcript),
            "cwd": str(self.repository),
            "prompt": "private-prompt-sentinel",
            "permission_mode": "read-only",
        }

    def test_receipt_records_shape_and_selected_hash_without_values(self):
        target = subagentstart_schema_observation.record_from_hook(
            StateStore(self.state),
            self.hook(),
            observation_root=self.repository,
        )

        encoded = target.read_bytes()
        self.assertNotIn(b"private-prompt-sentinel", encoded)
        receipt = subagentstart_schema_observation.load_receipts(self.state)[0]
        self.assertEqual(receipt["actor"]["canonical_agent_path"], "/root/bounded_task")
        keys = [item["key"] for item in receipt["hook_input_shape"]]
        self.assertIn("prompt", keys)
        fingerprint = receipt["selected_string_fingerprints"][0]
        self.assertEqual(fingerprint["key"], "prompt")
        self.assertEqual(fingerprint["length"], len("private-prompt-sentinel"))
        self.assertEqual(len(fingerprint["sha256"]), 64)
        self.assertFalse(receipt["raw_payload_stored"])

    def test_wrong_root_is_not_observed(self):
        result = subagentstart_schema_observation.record_from_hook(
            StateStore(self.state),
            self.hook(),
            observation_root=self.root,
        )
        self.assertIsNone(result)
        self.assertEqual(subagentstart_schema_observation.load_receipts(self.state), [])


if __name__ == "__main__":
    unittest.main()
