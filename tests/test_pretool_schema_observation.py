import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))

import compatibility_hook
import pretool_schema_observation


CorruptState = pretool_schema_observation.CorruptState
StateStore = compatibility_hook.StateStore


class PreToolSchemaObservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        subprocess.run(
            ["git", "-C", str(self.repository), "init", "-b", "main"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.state = self.root / "state"
        self.transcript = self.root / "parent.jsonl"
        self.transcript.write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-17T00:00:00Z",
                    "type": "session_meta",
                    "payload": {
                        "id": "runtime-session",
                        "session_id": "runtime-session",
                        "timestamp": "2026-08-16T23:59:59Z",
                        "cwd": str(self.repository),
                        "originator": "fixture",
                        "cli_version": "0.148.0-alpha.9",
                        "model_provider": "fixture-provider",
                        "source": "exec",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def hook(self, *, cwd=None, session_id="runtime-session"):
        return {
            "hook_event_name": "PreToolUse",
            "session_id": session_id,
            "turn_id": "turn-one",
            "transcript_path": str(self.transcript),
            "cwd": str(cwd or self.repository),
            "tool_name": "Agent",
            "tool_use_id": "agent-control-one",
            "tool_input": {
                "agent_type": "default",
                "fork_turns": None,
                "message": "private-assignment-sentinel",
                "metadata": {"credential": "private-credential-sentinel"},
                "task_name": "bounded_task",
            },
        }

    def test_scoped_receipt_records_only_names_and_types(self):
        target = pretool_schema_observation.record_from_hook(
            StateStore(self.state),
            self.hook(),
            observation_root=self.repository,
        )

        self.assertIsNotNone(target)
        encoded = target.read_bytes()
        self.assertNotIn(b"private-assignment-sentinel", encoded)
        self.assertNotIn(b"private-credential-sentinel", encoded)
        receipt = pretool_schema_observation.load_receipts(self.state)[0]
        self.assertEqual(receipt["actor"]["canonical_agent_path"], "/root")
        self.assertEqual(receipt["tool_name"], "Agent")
        self.assertEqual(
            receipt["tool_input_shape"],
            [
                {"key": "agent_type", "value_type": "string"},
                {"key": "fork_turns", "value_type": "null"},
                {"key": "message", "value_type": "string"},
                {"key": "metadata", "value_type": "object"},
                {"key": "task_name", "value_type": "string"},
            ],
        )
        fingerprint = receipt["selected_string_fingerprints"][0]
        self.assertEqual(fingerprint["key"], "message")
        self.assertEqual(fingerprint["length"], len("private-assignment-sentinel"))
        self.assertEqual(fingerprint["authority_begin_count"], 0)
        self.assertEqual(fingerprint["authority_end_count"], 0)
        self.assertEqual(len(fingerprint["sha256"]), 64)
        self.assertFalse(receipt["raw_payload_stored"])

    def test_existing_schema_one_receipt_remains_replayable(self):
        receipt = pretool_schema_observation.observation_from_hook(self.hook())
        receipt.pop("selected_string_fingerprints")
        receipt["schema"] = 1
        receipt["receipt_sha256"] = pretool_schema_observation.receipt_sha256(receipt)

        accepted = pretool_schema_observation.validate_receipt(receipt)

        self.assertEqual(accepted["schema"], 1)

    def test_observer_uses_realpath_equality_and_ignores_other_root(self):
        alias = self.repository / ".." / "repository"
        self.assertTrue(
            pretool_schema_observation.observes_root(self.hook(cwd=alias), self.repository)
        )
        result = pretool_schema_observation.record_from_hook(
            StateStore(self.state),
            self.hook(cwd=self.root),
            observation_root=self.repository,
        )
        self.assertIsNone(result)
        self.assertEqual(pretool_schema_observation.load_receipts(self.state), [])

    def test_tampered_receipt_is_rejected(self):
        path = pretool_schema_observation.record_from_hook(
            StateStore(self.state),
            self.hook(),
            observation_root=self.repository,
        )
        value = json.loads(path.read_text(encoding="utf-8"))
        value["cwd"] += "/tampered"
        path.write_text(json.dumps(value), encoding="utf-8")

        with self.assertRaisesRegex(CorruptState, "hash does not match"):
            pretool_schema_observation.load_receipts(self.state)

    def test_enabled_observer_fails_closed_on_unverifiable_actor(self):
        output = compatibility_hook.run_dispatch(
            StateStore(self.state),
            self.hook(session_id="wrong-session"),
            plaintext_agent_types={"fixture_worker"},
            pretool_schema_observation_root=self.repository,
        )

        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn("does not match SessionMeta", specific["permissionDecisionReason"])
        self.assertEqual(pretool_schema_observation.load_receipts(self.state), [])

    def test_checker_reports_shape_and_rejects_missing_tool(self):
        pretool_schema_observation.record_from_hook(
            StateStore(self.state),
            self.hook(),
            observation_root=self.repository,
        )
        command = [
            sys.executable,
            str(ROOT / "probes" / "check_pretool_schema_observations.py"),
            "--state-directory",
            str(self.state),
            "--runtime-session-id",
            "runtime-session",
            "--require-observation",
        ]
        accepted = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        report = json.loads(accepted.stdout)
        self.assertEqual(report["observation_count"], 1)
        self.assertFalse(report["raw_payload_stored"])

        rejected = subprocess.run(
            command + ["--require-tool-name", "spawn_agent"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("missing tool names", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
