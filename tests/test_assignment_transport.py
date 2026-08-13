import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = REPO / "hooks" / "compatibility_hook.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compatibility_state = load_module(
    "compatibility_state", REPO / "hooks" / "compatibility_state.py"
)
runtime_guard = load_module("runtime_guard", REPO / "hooks" / "runtime_guard.py")
assignment_transport = load_module(
    "assignment_transport", REPO / "hooks" / "assignment_transport.py"
)


StateStore = compatibility_state.StateStore


class AssignmentTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        (self.repository / "deleted.txt").write_text("delete me\n", encoding="utf-8")
        self.git("add", "baseline.txt", "deleted.txt")
        self.git("commit", "-m", "baseline")
        self.store = StateStore(self.root / "state")
        self.parent_transcript = self.root / "parent.jsonl"
        self.write_meta(
            self.parent_transcript,
            session_id="runtime-session",
            thread_id="parent-thread",
            agent_path=None,
            parent_thread_id=None,
            agent_role=None,
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

    def write_meta(
        self,
        path,
        *,
        session_id,
        thread_id,
        agent_path,
        parent_thread_id,
        agent_role,
    ):
        payload = {
            "session_id": session_id,
            "id": thread_id,
            "timestamp": "2026-08-12T00:00:00Z",
            "cwd": str(self.repository),
            "originator": "fixture",
            "cli_version": "0.147.0",
            "source": "sub_agent" if parent_thread_id else "cli",
            "model_provider": "fixture-provider",
        }
        if parent_thread_id is not None:
            payload["parent_thread_id"] = parent_thread_id
        if agent_role is not None:
            payload["agent_role"] = agent_role
        if agent_path is not None:
            payload["agent_path"] = agent_path
        item = {"timestamp": payload["timestamp"], "type": "session_meta", "payload": payload}
        path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    def message(self, *, authority=None):
        value = authority or {
            "schema": 1,
            "owned_paths": ["owned"],
            "excluded_paths": ["owned/excluded"],
            "git_authority": {
                "stage": False,
                "commit": False,
                "branch": False,
                "push": False,
            },
            "stop_condition": "finish only the assigned slice",
            "verification": ["fixture verification"],
            "authority_provenance": {
                "authoritative_input_owners": ["fixture.owner"],
                "authoritative_input_roots": ["inputs"],
                "forbidden_caller_supplied_derived_facts": ["oracle_obligations"],
                "test_only_injection_seams": ["fixture.inject_oracle"],
                "required_derivation_boundary": "fixture.owner.derive",
            },
            "ttl_seconds": 300,
        }
        return (
            "Implement the bounded slice.\n\n"
            "BEGIN CODEX WORKER AUTHORITY\n"
            + json.dumps(value, separators=(",", ":"))
            + "\nEND CODEX WORKER AUTHORITY"
        )

    def spawn_hook(self, task_name="bounded_task", **overrides):
        tool_input = {
            "message": self.message(),
            "task_name": task_name,
            "agent_type": "fixture_worker",
            "fork_turns": "none",
        }
        tool_input.update(overrides.pop("tool_input", {}))
        value = {
            "hook_event_name": "PreToolUse",
            "session_id": "runtime-session",
            "turn_id": "parent-turn",
            "transcript_path": str(self.parent_transcript),
            "cwd": str(self.repository),
            "tool_name": "spawn_agent",
            "tool_use_id": f"spawn-{task_name}",
            "tool_input": tool_input,
        }
        value.update(overrides)
        return value

    def child_hook(self, task_name="bounded_task", *, parent_path="/root"):
        child = self.root / f"child-{task_name}.jsonl"
        self.write_meta(
            child,
            session_id="runtime-session",
            thread_id=f"child-{task_name}",
            parent_thread_id="parent-thread",
            agent_role="fixture_worker",
            agent_path=f"{parent_path}/{task_name}",
        )
        return {
            "hook_event_name": "SubagentStart",
            "session_id": "runtime-session",
            "agent_id": f"child-{task_name}",
            "agent_type": "fixture_worker",
            "transcript_path": str(child),
            "cwd": str(self.repository),
        }

    def capture(self, hook):
        return assignment_transport.capture_spawn(
            self.store,
            hook,
            plaintext_agent_types={"fixture_worker"},
            now=dt.datetime.now(dt.timezone.utc),
        )

    def invoke_hook_cli(self, hook):
        return subprocess.run(
            [
                sys.executable,
                str(HOOK_SCRIPT),
                "--state-directory",
                str(self.store.root),
                "--plaintext-agent-type",
                "fixture_worker",
            ],
            input=json.dumps(hook),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_non_target_worker_passes_without_state_or_input_rewrite(self):
        hook = self.spawn_hook(tool_input={"agent_type": "default"})

        result = self.capture(hook)

        self.assertEqual(result, {})
        self.assertFalse((self.store.root / "pending").exists())

    def test_parent_pre_tool_use_captures_exact_spawn_message_and_runtime_facts(self):
        hook = self.spawn_hook()

        result = self.capture(hook)

        self.assertNotIn("updatedInput", json.dumps(result))
        pending = list((self.store.root / "pending").glob("*.json"))
        self.assertEqual(len(pending), 1)
        envelope = json.loads(pending[0].read_text(encoding="utf-8"))
        capsule = envelope["capsule"]
        self.assertEqual(envelope["assignment"], hook["tool_input"]["message"])
        self.assertEqual(capsule["runtime_session_id"], "runtime-session")
        self.assertEqual(capsule["parent_thread_id"], "parent-thread")
        self.assertEqual(capsule["canonical_agent_path"], "/root/bounded_task")
        self.assertEqual(capsule["root"]["path"], str(self.repository.resolve()))

    def test_invalid_authority_or_fork_mode_blocks_spawn(self):
        invalid = self.message(authority={"schema": 1, "credentials": "forbidden"})
        cases = [
            self.spawn_hook(tool_input={"message": invalid}),
            self.spawn_hook(tool_input={"fork_turns": "all"}),
        ]
        for hook in cases:
            with self.subTest(tool_input=hook["tool_input"]):
                result = self.capture(hook)
                self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertFalse((self.store.root / "pending").exists())

    def test_capture_records_modified_and_deleted_dirty_baselines(self):
        (self.repository / "baseline.txt").write_text("user change\n", encoding="utf-8")
        (self.repository / "deleted.txt").unlink()

        self.capture(self.spawn_hook())
        pending = next((self.store.root / "pending").glob("*.json"))
        dirty = {
            item["path"]: item
            for item in json.loads(pending.read_text(encoding="utf-8"))["capsule"][
                "preexisting_dirty"
            ]
        }

        self.assertEqual(dirty["baseline.txt"]["kind"], "file")
        self.assertRegex(dirty["baseline.txt"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(dirty["deleted.txt"]["kind"], "deleted")
        self.assertIsNone(dirty["deleted.txt"]["sha256"])

    def test_parent_session_mismatch_blocks_without_staging(self):
        result = self.capture(self.spawn_hook(session_id="different-session"))

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertFalse((self.store.root / "pending").exists())

    def test_subagent_start_claims_exact_capsule_and_retains_active_authority(self):
        hook = self.spawn_hook()
        self.capture(hook)

        result = assignment_transport.subagent_start(self.store, self.child_hook())

        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("BEGIN CODEX WORKER CAPSULE", context)
        self.assertIn(hook["tool_input"]["message"], context)
        self.assertEqual(len(list((self.store.root / "active").glob("*.json"))), 1)
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 0)

    def test_wrong_child_path_does_not_consume_pending(self):
        self.capture(self.spawn_hook())

        wrong_child = self.child_hook("different_task")
        result = assignment_transport.subagent_start(
            self.store, wrong_child
        )

        self.assertIn("TASK.CONTEXT_LOST", result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 1)
        self.assertEqual(len(list((self.store.root / "lost").glob("*.json"))), 1)

        denied = runtime_guard.pre_tool_use(
            self.store,
            dict(wrong_child, hook_event_name="PreToolUse", tool_name="view_image"),
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        stopped = runtime_guard.subagent_stop(
            self.store,
            {
                "hook_event_name": "SubagentStop",
                "session_id": "runtime-session",
                "agent_id": "child-different_task",
                "agent_type": "fixture_worker",
                "transcript_path": str(self.parent_transcript),
                "agent_transcript_path": wrong_child["transcript_path"],
                "last_assistant_message": "TASK.CONTEXT_LOST",
            },
        )
        self.assertEqual(stopped, {})

    def test_concurrent_distinct_spawns_bind_to_their_own_children(self):
        tasks = ["task_one", "task_two", "task_three"]
        with ThreadPoolExecutor(max_workers=3) as executor:
            captured = list(executor.map(lambda task: self.capture(self.spawn_hook(task)), tasks))
        self.assertTrue(all("updatedInput" not in json.dumps(item) for item in captured))

        with ThreadPoolExecutor(max_workers=3) as executor:
            started = list(
                executor.map(
                    lambda task: assignment_transport.subagent_start(
                        self.store, self.child_hook(task)
                    ),
                    reversed(tasks),
                )
            )

        self.assertTrue(all("BEGIN CODEX WORKER CAPSULE" in item["hookSpecificOutput"]["additionalContext"] for item in started))
        self.assertEqual(len(list((self.store.root / "active").glob("*.json"))), 3)
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 0)

    def test_nested_parent_path_derives_exact_child_agent_path(self):
        self.write_meta(
            self.parent_transcript,
            session_id="runtime-session",
            thread_id="parent-thread",
            parent_thread_id="root-thread",
            agent_role="default",
            agent_path="/root/parent_task",
        )
        hook = self.spawn_hook(agent_id="parent-thread", agent_type="default")

        self.capture(hook)
        pending = next((self.store.root / "pending").glob("*.json"))
        capsule = json.loads(pending.read_text(encoding="utf-8"))["capsule"]

        self.assertEqual(capsule["canonical_agent_path"], "/root/parent_task/bounded_task")

    def test_executable_hook_runs_capture_claim_recovery_and_final_lifecycle(self):
        spawn = self.spawn_hook()
        captured = self.invoke_hook_cli(spawn)
        self.assertEqual(captured.returncode, 0, captured.stderr)
        self.assertNotIn(spawn["tool_input"]["message"], captured.stdout)

        child = self.child_hook()
        started = self.invoke_hook_cli(child)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("BEGIN CODEX WORKER CAPSULE", started.stdout)

        compact = dict(child, hook_event_name="PreCompact", trigger="auto")
        compacted = self.invoke_hook_cli(compact)
        self.assertEqual(compacted.returncode, 0, compacted.stderr)

        checked = self.invoke_hook_cli(
            dict(child, hook_event_name="PreToolUse", tool_name="view_image", tool_input={})
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        checked_output = json.loads(checked.stdout)
        checked_context = checked_output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("recovery_count=1", checked_context)
        self.assertIn(spawn["tool_input"]["message"], checked_context)

        active_path = next((self.store.root / "active").glob("*.json"))
        envelope = json.loads(active_path.read_text(encoding="utf-8"))
        capsule = envelope["capsule"]
        snapshot = runtime_guard.collect_git_snapshot(str(self.repository))
        attestation = {
            "assignment_id": capsule["assignment_id"],
            "handoff_id": capsule["handoff_id"],
            "capsule_sha256": capsule["capsule_sha256"],
            "compact_invariant_sha256": compatibility_state.compact_invariant_sha256(
                capsule
            ),
            "authority_provenance": {
                "policy_sha256": compatibility_state.provenance_policy_sha256(capsule),
                "worker_claimed_origin": "owner_internal",
                "test_only_injection_used": False,
                "derivation_receipt_sha256": "d" * 64,
            },
            "canonical_agent_path": capsule["canonical_agent_path"],
            "recovery_count": 1,
            "context_lost": False,
            **snapshot,
            "verification": [{"command": "fixture verification", "exit_code": 0}],
            "authority_violation": False,
            "assigned_slice_complete": True,
        }
        message = (
            "BEGIN CODEX WORKER ATTESTATION\n"
            + json.dumps(attestation)
            + "\nEND CODEX WORKER ATTESTATION"
        )
        stopped = self.invoke_hook_cli(
            {
                "hook_event_name": "SubagentStop",
                "session_id": "runtime-session",
                "agent_id": "child-bounded_task",
                "agent_type": "fixture_worker",
                "transcript_path": str(self.parent_transcript),
                "agent_transcript_path": child["transcript_path"],
                "last_assistant_message": message,
            }
        )

        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(json.loads(stopped.stdout), {})
        self.assertEqual(len(list((self.store.root / "reported").glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
