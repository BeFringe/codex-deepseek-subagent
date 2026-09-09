import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "hooks"
RECOVERY_SCRIPT = REPO / "probes" / "recover_non_git_writer_claim.py"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

import writer_lease_guard  # noqa: E402
from compatibility_state import (  # noqa: E402
    validate_non_git_writer_abort,
    validate_non_git_writer_receipt,
)


# Several legacy test modules deliberately reload compatibility_state under the
# same module name. Use the class object bound by the guard so its StateError
# handler and the store always share one exception hierarchy during discovery.
StateStore = writer_lease_guard.StateStore


class NonGitWriterCeilingTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.non_git_root = self.root / "non-git"
        self.non_git_root.mkdir()
        self.outside_root = self.root / "outside"
        self.outside_root.mkdir()
        self.store = StateStore(self.root / "state")
        self.parent_transcript = self.root / "parent.jsonl"
        self.write_meta(
            self.parent_transcript,
            session_id="runtime-session",
            thread_id="runtime-session",
            parent_thread_id=None,
            agent_role=None,
            agent_path=None,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_meta(
        self,
        path,
        *,
        session_id,
        thread_id,
        parent_thread_id,
        agent_role,
        agent_path,
    ):
        payload = {
            "session_id": session_id,
            "id": thread_id,
            "timestamp": "2026-09-08T00:00:00Z",
            "cwd": str(self.root),
            "originator": "fixture",
            "cli_version": "0.153.4",
            "source": "vscode",
            "model_provider": "fixture-provider",
        }
        if parent_thread_id is not None:
            payload.update(
                {
                    "parent_thread_id": parent_thread_id,
                    "agent_role": agent_role,
                    "agent_path": agent_path,
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": parent_thread_id,
                                "depth": 1,
                                "agent_path": agent_path,
                                "agent_nickname": None,
                                "agent_role": agent_role,
                            }
                        }
                    },
                }
            )
        record = {
            "timestamp": "2026-09-08T00:00:00.001Z",
            "type": "session_meta",
            "payload": payload,
        }
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def patch_hook(
        self,
        path,
        *,
        event="PreToolUse",
        tool_use_id="non-git-patch",
        transcript_path=None,
        extra_path=None,
    ):
        actions = [f"*** Add File: {path}", "+temporary bytes"]
        if extra_path is not None:
            actions.extend([f"*** Add File: {extra_path}", "+other bytes"])
        command = "\n".join(["*** Begin Patch", *actions, "*** End Patch"])
        value = {
            "hook_event_name": event,
            "session_id": "runtime-session",
            "turn_id": "parent-turn",
            "transcript_path": str(transcript_path or self.parent_transcript),
            "cwd": str(self.root),
            "tool_name": "apply_patch",
            "tool_use_id": tool_use_id,
            "tool_input": {"command": command},
        }
        if event == "PostToolUse":
            value["tool_response"] = {"status": "completed"}
        return value

    def test_non_git_write_without_explicit_ceiling_is_denied(self):
        result = writer_lease_guard.pre_tool_use(
            self.store,
            self.patch_hook(self.non_git_root / "probe.txt"),
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("no parent non-Git writer root", json.dumps(result))
        self.assertFalse((self.store.root / "non_git_writer_claim").exists())

    def test_root_parent_claims_and_releases_exact_non_git_paths(self):
        target = self.non_git_root / "probe.txt"
        pre = self.patch_hook(target)

        leased = writer_lease_guard.pre_tool_use(
            self.store,
            pre,
            parent_non_git_writer_roots=[self.non_git_root],
        )

        self.assertIn("surface=non_git_filesystem", json.dumps(leased))
        claim_path = next((self.store.root / "non_git_writer_claim").glob("*.json"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        self.assertEqual(claim["actor"]["canonical_agent_path"], "/root")
        self.assertEqual(claim["authorization_ceiling"]["root"], str(self.non_git_root))
        self.assertEqual(claim["paths"], ["probe.txt"])
        self.assertEqual(
            claim["before_snapshot"]["path_states"][0]["kind"], "missing"
        )

        target.write_text("temporary bytes\n", encoding="utf-8")
        released = writer_lease_guard.post_tool_use(
            self.store,
            self.patch_hook(target, event="PostToolUse"),
            parent_non_git_writer_roots=[self.non_git_root],
        )

        self.assertEqual(released, {})
        self.assertFalse(claim_path.exists())
        receipt_path = next(
            (self.store.root / "non_git_writer_receipt").glob("*.json")
        )
        receipt = validate_non_git_writer_receipt(
            json.loads(receipt_path.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            receipt["after_snapshot"]["path_states"][0]["byte_length"],
            len(b"temporary bytes\n"),
        )

    def test_failed_patch_claim_can_only_abort_with_unchanged_snapshot(self):
        target = self.non_git_root / "failed.txt"
        hook = self.patch_hook(target, tool_use_id="failed-non-git-patch")
        writer_lease_guard.pre_tool_use(
            self.store,
            hook,
            parent_non_git_writer_roots=[self.non_git_root],
        )
        claim_path = next((self.store.root / "non_git_writer_claim").glob("*.json"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        snapshot, _ = writer_lease_guard.collect_patch_non_git_snapshot(
            [str(target)],
            cwd=str(self.root),
            parent_non_git_writer_roots=[self.non_git_root],
        )

        receipt_path = self.store.abort_unchanged_non_git_writer_claim(
            claim["actor"],
            claim_id=claim["claim_id"],
            after_snapshot=snapshot,
            recovery_reason="missing_posttooluse_after_tool_failure",
        )

        self.assertFalse(claim_path.exists())
        receipt = validate_non_git_writer_abort(
            json.loads(receipt_path.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            receipt["before_snapshot_sha256"],
            receipt["after_snapshot_sha256"],
        )

    def test_recovery_cli_validates_parent_identity_and_emits_hash_only_report(self):
        target = self.non_git_root / "cli-failed.txt"
        hook = self.patch_hook(target, tool_use_id="failed-cli-patch")
        writer_lease_guard.pre_tool_use(
            self.store,
            hook,
            parent_non_git_writer_roots=[self.non_git_root],
        )
        claim_path = next((self.store.root / "non_git_writer_claim").glob("*.json"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))

        completed = subprocess.run(
            [
                sys.executable,
                str(RECOVERY_SCRIPT),
                "--state-directory",
                str(self.store.root),
                "--claim-id",
                claim["claim_id"],
                "--session-id",
                "runtime-session",
                "--transcript-path",
                str(self.parent_transcript),
                "--recovery-reason",
                "missing_posttooluse_after_tool_failure",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["classification"],
            "aborted_unchanged_after_missing_callback",
        )
        self.assertEqual(
            report["before_snapshot_sha256"],
            report["after_snapshot_sha256"],
        )
        self.assertIs(report["raw_payload_stored"], False)
        self.assertFalse(claim_path.exists())

    def test_nested_child_cannot_use_parent_non_git_ceiling(self):
        child_transcript = self.root / "child.jsonl"
        self.write_meta(
            child_transcript,
            session_id="runtime-session",
            thread_id="child-thread",
            parent_thread_id="runtime-session",
            agent_role="default",
            agent_path="/root/child",
        )
        hook = self.patch_hook(
            self.non_git_root / "probe.txt",
            transcript_path=child_transcript,
        )
        hook.update({"agent_id": "child-thread", "agent_type": "default"})

        result = writer_lease_guard.pre_tool_use(
            self.store,
            hook,
            parent_non_git_writer_roots=[self.non_git_root],
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("root-parent only", json.dumps(result))
        self.assertFalse((self.store.root / "non_git_writer_claim").exists())

    def test_non_git_ceiling_rejects_symlink_escape_and_cross_root_patch(self):
        (self.non_git_root / "alias").symlink_to(self.outside_root, target_is_directory=True)
        symlink_result = writer_lease_guard.pre_tool_use(
            self.store,
            self.patch_hook(self.non_git_root / "alias" / "escaped.txt"),
            parent_non_git_writer_roots=[self.non_git_root],
        )
        cross_root_result = writer_lease_guard.pre_tool_use(
            self.store,
            self.patch_hook(
                self.non_git_root / "inside.txt",
                tool_use_id="cross-root",
                extra_path=self.outside_root / "outside.txt",
            ),
            parent_non_git_writer_roots=[self.non_git_root],
        )

        self.assertEqual(
            symlink_result["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertIn("symlink", json.dumps(symlink_result))
        self.assertEqual(
            cross_root_result["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertIn("outside the explicit", json.dumps(cross_root_result))

    def test_non_git_ceiling_root_itself_is_not_a_patch_target(self):
        result = writer_lease_guard.pre_tool_use(
            self.store,
            self.patch_hook(self.non_git_root),
            parent_non_git_writer_roots=[self.non_git_root],
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("cannot be the ceiling root", json.dumps(result))

    def test_concurrent_overlapping_non_git_claims_allow_one_writer(self):
        hooks = [
            self.patch_hook(
                self.non_git_root / "race.txt",
                tool_use_id=f"non-git-race-{index}",
            )
            for index in range(2)
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda hook: writer_lease_guard.pre_tool_use(
                        self.store,
                        hook,
                        parent_non_git_writer_roots=[self.non_git_root],
                    ),
                    hooks,
                )
            )

        decisions = [
            result["hookSpecificOutput"].get("permissionDecision", "pass")
            for result in results
        ]
        self.assertEqual(sorted(decisions), ["deny", "pass"])
        self.assertEqual(
            len(list((self.store.root / "non_git_writer_claim").glob("*.json"))),
            1,
        )

    def test_executable_hook_accepts_explicit_non_git_ceiling(self):
        target = self.non_git_root / "cli.txt"
        command = [
            sys.executable,
            str(HOOKS / "compatibility_hook.py"),
            "--state-directory",
            str(self.store.root),
            "--plaintext-agent-type",
            "fixture_worker",
            "--parent-non-git-writer-root",
            str(self.non_git_root),
        ]
        pre = subprocess.run(
            command,
            input=json.dumps(self.patch_hook(target, tool_use_id="cli-temp")),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(pre.returncode, 0, pre.stderr)
        self.assertIn("surface=non_git_filesystem", pre.stdout)
        target.write_text("temporary bytes\n", encoding="utf-8")
        post = subprocess.run(
            command,
            input=json.dumps(
                self.patch_hook(
                    target,
                    event="PostToolUse",
                    tool_use_id="cli-temp",
                )
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(post.returncode, 0, post.stderr)
        self.assertEqual(json.loads(post.stdout), {})


if __name__ == "__main__":
    unittest.main()
