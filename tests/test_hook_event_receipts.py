import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))

import compatibility_hook
import hook_event_receipts


# Some older test modules intentionally reload the executable Hook modules under
# their production names. Bind exceptions and the store to the modules under
# test so full-suite discovery cannot create same-named, unequal class objects.
AuthorityViolation = hook_event_receipts.AuthorityViolation
CorruptState = hook_event_receipts.CorruptState
StateError = compatibility_hook.StateError
StateStore = compatibility_hook.StateStore


class HookEventReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        self.git("add", "baseline.txt")
        self.git("commit", "-m", "baseline")
        self.state = self.root / "state"
        self.transcript = self.root / "parent.jsonl"
        self.transcript.write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-12T00:00:00.070Z",
                    "type": "session_meta",
                    "payload": {
                        "session_id": "runtime-session",
                        "id": "runtime-session",
                        "timestamp": "2026-08-12T00:00:00Z",
                        "cwd": str(self.repository),
                        "originator": "fixture",
                        "cli_version": "0.148.0-alpha.9",
                        "source": "vscode",
                        "model_provider": "fixture-provider",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def hook(self, event="PreToolUse", tool_use_id="patch-one"):
        value = {
            "hook_event_name": event,
            "session_id": "runtime-session",
            "turn_id": "turn-one",
            "transcript_path": str(self.transcript),
            "cwd": str(self.root),
            "tool_name": "apply_patch",
            "tool_use_id": tool_use_id,
            "tool_input": {
                "command": (
                    "*** Begin Patch\n"
                    f"*** Add File: {self.repository / 'result.txt'}\n"
                    "+private-patch-sentinel\n"
                    "*** End Patch"
                )
            },
        }
        if event == "PostToolUse":
            value["tool_response"] = {"status": "completed", "private": "response-sentinel"}
        return value

    def invoke(self, hook):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "hooks" / "compatibility_hook.py"),
                "--state-directory",
                str(self.state),
                "--plaintext-agent-type",
                "fixture_worker",
            ],
            input=json.dumps(hook),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def verify(self, *, require_complete):
        command = [
            sys.executable,
            str(ROOT / "probes" / "check_hook_event_chain.py"),
            "--state-directory",
            str(self.state),
        ]
        if require_complete:
            command.append("--require-complete-callbacks")
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def recover(self, claim_id, *, session_id="runtime-session"):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "probes" / "recover_writer_claim.py"),
                "--state-directory",
                str(self.state),
                "--claim-id",
                claim_id,
                "--session-id",
                session_id,
                "--transcript-path",
                str(self.transcript),
                "--recovery-reason",
                "missing_posttooluse_after_tool_failure",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_chain_joins_authorized_pre_and_observed_post_without_raw_payload(self):
        pre = self.invoke(self.hook())
        self.assertEqual(pre.returncode, 0, pre.stderr)
        self.assertIn("WRITER.LEASED", pre.stdout)

        pending = self.verify(require_complete=True)
        self.assertEqual(pending.returncode, 2)
        self.assertIn("no observed PostToolUse", pending.stderr)

        post = self.invoke(self.hook(event="PostToolUse"))
        self.assertEqual(post.returncode, 0, post.stderr)
        self.assertEqual(json.loads(post.stdout), {})

        completed = self.verify(require_complete=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["callbacks"][0]["status"], "callback_observed")
        self.assertEqual(report["pending_tool_use_ids"], [])
        chain_bytes = (self.state / "hook_event_chain" / "current.json").read_bytes()
        self.assertNotIn(b"private-patch-sentinel", chain_bytes)
        self.assertNotIn(b"response-sentinel", chain_bytes)
        chain = hook_event_receipts.load_chain(self.state)
        for event in chain["events"]:
            self.assertNotIn("tool_input", event)
            self.assertNotIn("tool_response", event)
            self.assertNotIn("last_assistant_message", event)
            self.assertFalse(event["raw_payload_stored"])

    def test_post_without_pre_fails_closed_before_release(self):
        result = self.invoke(self.hook(event="PostToolUse", tool_use_id="orphan"))

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIs(output["continue"], False)
        self.assertIn("no preceding PreToolUse", output["stopReason"])
        self.assertFalse((self.state / "hook_event_chain" / "current.json").exists())

    def test_duplicate_post_fails_closed_and_preserves_two_event_chain(self):
        self.invoke(self.hook())
        self.invoke(self.hook(event="PostToolUse"))

        duplicate = self.invoke(self.hook(event="PostToolUse"))

        output = json.loads(duplicate.stdout)
        self.assertIs(output["continue"], False)
        chain = hook_event_receipts.load_chain(self.state)
        self.assertEqual(chain["event_count"], 2)

    def test_tampered_chain_is_detected_and_quarantined_on_append(self):
        self.invoke(self.hook())
        path = self.state / "hook_event_chain" / "current.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["events"][0]["turn_id"] = "tampered"
        path.write_text(json.dumps(value), encoding="utf-8")

        with self.assertRaisesRegex(CorruptState, "receipt hash"):
            hook_event_receipts.load_chain(self.state)

        denied = self.invoke(self.hook(tool_use_id="patch-two"))
        output = json.loads(denied.stdout)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertTrue(any((self.state / "quarantine").glob("current.*.json")))

    def test_receipt_failure_after_writer_claim_denies_and_leaves_claim(self):
        original = hook_event_receipts.record_from_hook

        def fail_record(*args, **kwargs):
            raise StateError("fixture receipt write failed")

        hook_event_receipts.record_from_hook = fail_record
        compatibility_hook.record_from_hook = fail_record
        try:
            output = compatibility_hook.run_dispatch(
                StateStore(self.state),
                self.hook(),
                plaintext_agent_types={"fixture_worker"},
            )
        finally:
            hook_event_receipts.record_from_hook = original
            compatibility_hook.record_from_hook = original

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("receipt write failed", output["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(len(list((self.state / "writer_claim").glob("*.json"))), 1)

    def test_direct_audit_rejects_pending_callback_at_quiescent_boundary(self):
        self.invoke(self.hook())
        chain = hook_event_receipts.load_chain(self.state)

        with self.assertRaisesRegex(AuthorityViolation, "no observed PostToolUse"):
            hook_event_receipts.audit_apply_patch_callbacks(
                chain,
                require_complete=True,
            )

    def test_missing_callback_claim_can_abort_only_with_claimed_paths_unchanged(self):
        self.invoke(self.hook())
        claim = next((self.state / "writer_claim").glob("*.json"))
        (self.repository / "baseline.txt").write_text(
            "disjoint parent change\n", encoding="utf-8"
        )

        recovered = self.recover(claim.stem)

        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        report = json.loads(recovered.stdout)
        self.assertEqual(
            report["classification"],
            "aborted_unchanged_after_missing_callback",
        )
        self.assertEqual(
            report["before_path_snapshot_sha256"],
            report["after_path_snapshot_sha256"],
        )
        self.assertFalse(list((self.state / "writer_claim").glob("*.json")))
        self.assertEqual(len(list((self.state / "writer_abort").glob("*.json"))), 1)
        verified = self.verify(require_complete=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        callback = json.loads(verified.stdout)["callbacks"][0]
        self.assertEqual(callback["status"], "aborted_unchanged")
        self.assertIsNone(callback["post_sequence"])
        self.assertEqual(callback["abort_claim_id"], claim.stem)

    def test_missing_callback_abort_rejects_claimed_path_mutation(self):
        self.invoke(self.hook())
        claim = next((self.state / "writer_claim").glob("*.json"))
        (self.repository / "result.txt").write_text(
            "private-mutation-sentinel\n", encoding="utf-8"
        )

        recovered = self.recover(claim.stem)

        self.assertEqual(recovered.returncode, 2)
        self.assertIn("claimed path", recovered.stderr)
        self.assertTrue(claim.exists())
        self.assertFalse((self.state / "writer_abort").exists())

    def test_missing_callback_abort_rejects_wrong_session_identity(self):
        self.invoke(self.hook())
        claim = next((self.state / "writer_claim").glob("*.json"))

        recovered = self.recover(claim.stem, session_id="wrong-session")

        self.assertEqual(recovered.returncode, 2)
        self.assertIn("session does not match SessionMeta", recovered.stderr)
        self.assertTrue(claim.exists())

    def test_missing_callback_abort_rejects_disjoint_index_mutation(self):
        self.invoke(self.hook())
        claim = next((self.state / "writer_claim").glob("*.json"))
        (self.repository / "baseline.txt").write_text(
            "disjoint staged change\n", encoding="utf-8"
        )
        self.git("add", "baseline.txt")

        recovered = self.recover(claim.stem)

        self.assertEqual(recovered.returncode, 2)
        self.assertIn("Git frontier", recovered.stderr)
        self.assertTrue(claim.exists())


if __name__ == "__main__":
    unittest.main()
