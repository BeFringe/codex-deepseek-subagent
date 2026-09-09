import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reconciler = load_module(
    "reconcile_g4_write_then_close",
    ROOT / "probes" / "reconcile_g4_write_then_close.py",
)
handover_reconciler = load_module(
    "reconcile_g4_handover_then_close",
    ROOT / "probes" / "reconcile_g4_handover_then_close.py",
)


class G4WriteThenCloseReconciliationTests(unittest.TestCase):
    parent_thread = "parent-thread"
    child_thread = "child-thread"
    agent_path = "/root/g4_p5b_write_close_test"
    spawn_id = "spawn-call"
    write_id = "write-call"
    assignment = "exact write assignment"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="codex-g4-p5b-write-termination.",
            dir="/private/tmp",
        )
        self.root = Path(self.directory.name)
        self.target = self.root / "qualified.txt"
        self.target.write_text(reconciler.TARGET_CONTENT, encoding="utf-8")
        self.attestation = {
            "assignment_id": "assignment-id",
            "handoff_id": "handoff-id",
            "capsule_sha256": "a" * 64,
            "compact_invariant_sha256": "b" * 64,
            "authority_provenance": {
                "policy_sha256": "c" * 64,
                "worker_claimed_origin": "owner_internal",
                "test_only_injection_used": False,
                "derivation_receipt_sha256": "d" * 64,
            },
            "canonical_agent_path": self.agent_path,
            "recovery_count": 0,
            "context_lost": False,
            "root": str(self.root),
            "branch": "main",
            "head": "e" * 40,
            "index_changed": False,
            "git_status_short": "?? qualified.txt",
            "changed_paths": [
                {
                    "kind": "file",
                    "path": "qualified.txt",
                    "sha256": reconciler.sha256_file(self.target),
                }
            ],
            "verification": [{"command": "exact probe", "exit_code": 0}],
            "authority_violation": False,
            "assigned_slice_complete": True,
            "inventory_summaries": [],
        }

    def tearDown(self):
        self.directory.cleanup()

    def capsule(self):
        return {
            "runtime_session_id": self.parent_thread,
            "parent_thread_id": self.parent_thread,
            "spawn_tool_use_id": self.spawn_id,
            "requested_task_name": "g4_p5b_write_close_test",
            "canonical_agent_path": self.agent_path,
        }

    def binding(self):
        return {"child_thread_id": self.child_thread}

    @staticmethod
    def call(name, call_id, arguments, timestamp, *, kind="function_call"):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": kind,
                "name": name,
                "namespace": "g4_assignment" if kind == "function_call" else None,
                "arguments": json.dumps(arguments, separators=(",", ":")),
                "call_id": call_id,
            },
        }

    @staticmethod
    def output(call_id, output, timestamp, *, kind="function_call_output"):
        encoded = output if isinstance(output, str) else json.dumps(output, separators=(",", ":"))
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {"type": kind, "call_id": call_id, "output": encoded},
        }

    @staticmethod
    def message(role, text, timestamp):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": text}],
            },
        }

    def final_text(self):
        return (
            "BEGIN CODEX WORKER ATTESTATION\n"
            + json.dumps(self.attestation, separators=(",", ":"), sort_keys=True)
            + "\nEND CODEX WORKER ATTESTATION"
        )

    def close_receipt(self):
        empty = {self.child_thread: []}
        return {
            "previous_status": "running",
            "target_thread_id": self.child_thread,
            "target_agent_path": self.agent_path,
            "session_loop_terminated": True,
            "model_callable_process_bootstrap_absent": True,
            "tracked_background_processes_before_close": 0,
            "tracked_process_ids_by_thread": empty,
            "confirmed_exit_process_ids_by_thread": empty,
            "unconfirmed_exit_process_ids_by_thread": empty,
            "unresolved_start_process_ids_by_thread": empty,
            "tracked_process_termination_confirmed": True,
            "closed_catalog_actor_quiescence_claimed": True,
            "process_tree_quiescence_claimed": False,
        }

    def completed_cleanup_close_receipt(self):
        receipt = self.close_receipt()
        receipt["previous_status"] = {"completed": self.final_text()}
        return receipt

    def parent_records(self, *, close=None, callback=None):
        close = close or self.close_receipt()
        callback = callback or (
            "Message Type: FINAL_ANSWER\n"
            "Task name: /root\n"
            f"Sender: {self.agent_path}\n"
            f"Payload:\n{self.final_text()}"
        )
        spawn_arguments = {
            "agent_type": reconciler.AGENT_TYPE,
            "task_name": "g4_p5b_write_close_test",
            "fork_turns": "none",
            "message": self.assignment,
        }
        pre = {
            "agents": [
                {"agent_name": "/root", "agent_status": "running"},
                {"agent_name": self.agent_path, "agent_status": "running"},
            ]
        }
        post = {"agents": [{"agent_name": "/root", "agent_status": "running"}]}
        return [
            self.call("spawn_agent", self.spawn_id, spawn_arguments, "2026-09-09T00:00:00Z"),
            self.output(self.spawn_id, {"task_name": self.agent_path}, "2026-09-09T00:00:00.1Z"),
            self.call("wait_agent", "wait-call", {"timeout_ms": 60000}, "2026-09-09T00:00:01Z"),
            self.output(
                "wait-call",
                {"message": "Wait completed.", "timed_out": False},
                "2026-09-09T00:00:03.1Z",
            ),
            self.message("user", callback, "2026-09-09T00:00:03.2Z"),
            self.call(
                "followup_task",
                "follow-call",
                {"target": self.agent_path, "message": reconciler.FOLLOWUP_HOLD},
                "2026-09-09T00:00:04Z",
            ),
            self.output("follow-call", "", "2026-09-09T00:00:04.1Z"),
            self.call("list_agents", "pre-list", {}, "2026-09-09T00:00:05Z"),
            self.output("pre-list", pre, "2026-09-09T00:00:05.1Z"),
            self.call("close_agent", "close-call", {"target": self.agent_path}, "2026-09-09T00:00:06Z"),
            self.output("close-call", close, "2026-09-09T00:00:07Z"),
            self.call("list_agents", "post-list", {}, "2026-09-09T00:00:08Z"),
            self.output("post-list", post, "2026-09-09T00:00:08.1Z"),
        ]

    def completed_cleanup_parent_records(self, *, close=None, callback=None):
        close = close or self.completed_cleanup_close_receipt()
        callback = callback or (
            "Message Type: FINAL_ANSWER\n"
            "Task name: /root\n"
            f"Sender: {self.agent_path}\n"
            f"Payload:\n{self.final_text()}"
        )
        spawn_arguments = {
            "agent_type": reconciler.AGENT_TYPE,
            "task_name": "g4_p5b_write_close_test",
            "fork_turns": "none",
            "message": self.assignment,
        }
        return [
            self.call("spawn_agent", self.spawn_id, spawn_arguments, "2026-09-09T00:00:00Z"),
            self.output(self.spawn_id, {"task_name": self.agent_path}, "2026-09-09T00:00:00.1Z"),
            self.call("wait_agent", "wait-call", {"timeout_ms": 60000}, "2026-09-09T00:00:01Z"),
            self.output(
                "wait-call",
                {"message": "Wait completed.", "timed_out": False},
                "2026-09-09T00:00:03.1Z",
            ),
            self.message("user", callback, "2026-09-09T00:00:03.2Z"),
            self.call("close_agent", "close-call", {"target": self.agent_path}, "2026-09-09T00:00:04Z"),
            self.output("close-call", close, "2026-09-09T00:00:05Z"),
        ]

    def writer_receipt(self):
        return {"tool_use_id": self.write_id}

    def child_records(self, *, handover=False, completed_cleanup=False):
        if handover:
            expected_patch = (
                "*** Begin Patch\n"
                f"*** Update File: {self.target}\n"
                "@@\n"
                "-G4_CHILD_WRITE_QUALIFIED\n"
                "+G4_HANDOVER_WRITE_QUALIFIED\n"
                "*** End Patch\n"
            )
        else:
            expected_patch = (
                "*** Begin Patch\n"
                f"*** Add File: {self.target}\n"
                "+G4_CHILD_WRITE_QUALIFIED\n"
                "*** End Patch\n"
            )
        records = [
            {
                "timestamp": "2026-09-09T00:00:00.2Z",
                "type": "event_msg",
                "payload": {"type": "task_started", "turn_id": "first-turn"},
            },
            self.call(
                "apply_patch",
                self.write_id,
                {},
                "2026-09-09T00:00:01.2Z",
                kind="custom_tool_call",
            )
            | {"payload": {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "call_id": self.write_id,
                "input": expected_patch,
            }},
            self.output(
                self.write_id,
                "Success.",
                "2026-09-09T00:00:02Z",
                kind="custom_tool_call_output",
            ),
            self.message("assistant", self.final_text(), "2026-09-09T00:00:03Z"),
            {
                "timestamp": "2026-09-09T00:00:03.05Z",
                "type": "event_msg",
                "payload": {"type": "task_complete", "turn_id": "first-turn"},
            },
        ]
        if completed_cleanup:
            return records
        return records + [
            {
                "timestamp": "2026-09-09T00:00:04.2Z",
                "type": "event_msg",
                "payload": {"type": "task_started", "turn_id": "second-turn"},
            },
            self.message(
                "user",
                "Message Type: NEW_TASK\n"
                f"Task name: {self.agent_path}\n"
                "Sender: /root\n"
                f"Payload:\n{reconciler.FOLLOWUP_HOLD}",
                "2026-09-09T00:00:04.3Z",
            ),
            {
                "timestamp": "2026-09-09T00:00:06.9Z",
                "type": "event_msg",
                "payload": {
                    "type": "turn_aborted",
                    "turn_id": "second-turn",
                    "reason": "interrupted",
                },
            },
        ]

    def hook_chain(self):
        parent = {
            "runtime_session_id": self.parent_thread,
            "thread_id": self.parent_thread,
            "canonical_agent_path": "/root",
        }
        child = {
            "runtime_session_id": self.parent_thread,
            "thread_id": self.child_thread,
            "canonical_agent_path": self.agent_path,
        }
        return {
            "events": [
                {"sequence": 10, "hook_event_name": "PreToolUse", "scope": "target_spawn", "tool_use_id": self.spawn_id, "actor": parent},
                {"sequence": 11, "hook_event_name": "SubagentStart", "scope": "target_child", "tool_use_id": None, "actor": child},
                {"sequence": 12, "hook_event_name": "PreToolUse", "scope": "target_child", "tool_name": "apply_patch", "tool_use_id": self.write_id, "actor": child},
                {"sequence": 13, "hook_event_name": "PostToolUse", "scope": "target_child", "tool_name": "apply_patch", "tool_use_id": self.write_id, "actor": child},
                {"sequence": 14, "hook_event_name": "SubagentStop", "scope": "target_child", "tool_use_id": None, "actor": child},
            ]
        }

    def test_exact_write_report_resume_and_close_is_accepted_without_global_overclaim(self):
        child = self.child_records()
        parent = self.parent_records()
        lifecycle = reconciler.validate_parent_lifecycle(
            parent,
            self.capsule(),
            self.binding(),
            self.assignment,
            self.final_text(),
            dt.datetime.fromisoformat("2026-09-09T00:00:03.050+00:00"),
        )
        child_lifecycle = reconciler.validate_child_lifecycle(
            child,
            self.capsule(),
            self.attestation,
            self.writer_receipt(),
            self.target,
            lifecycle["terminated_at"],
        )
        hooks = reconciler.validate_hook_chain(
            self.hook_chain(),
            self.capsule(),
            self.binding(),
            self.writer_receipt(),
        )

        self.assertEqual(lifecycle["close_tool_use_id"], "close-call")
        self.assertEqual(child_lifecycle["final_text"], self.final_text())
        self.assertEqual([event["sequence"] for event in hooks], [10, 11, 12, 13, 14])
        self.assertFalse(lifecycle["close_receipt"]["process_tree_quiescence_claimed"])

    def test_callback_must_be_byte_identical(self):
        with self.assertRaisesRegex(reconciler.ReconciliationError, "callback"):
            reconciler.validate_parent_lifecycle(
                self.parent_records(callback="Message Type: FINAL_ANSWER\nwrong"),
                self.capsule(),
                self.binding(),
                self.assignment,
                self.final_text(),
                dt.datetime.fromisoformat("2026-09-09T00:00:03.050+00:00"),
            )

    def test_handover_lifecycle_requires_one_exact_update_before_second_close(self):
        self.target.write_text(
            handover_reconciler.TARGET_CONTENT,
            encoding="utf-8",
        )
        self.attestation["changed_paths"][0]["sha256"] = reconciler.sha256_file(
            self.target
        )
        lifecycle = handover_reconciler.validate_child_lifecycle(
            self.child_records(handover=True),
            self.capsule(),
            self.attestation,
            self.writer_receipt(),
            self.target,
            dt.datetime.fromisoformat("2026-09-09T00:00:07+00:00"),
        )
        self.assertEqual(lifecycle["final_text"], self.final_text())

        with self.assertRaisesRegex(
            reconciler.ReconciliationError,
            "replacement apply_patch",
        ):
            handover_reconciler.validate_child_lifecycle(
                self.child_records(),
                self.capsule(),
                self.attestation,
                self.writer_receipt(),
                self.target,
                dt.datetime.fromisoformat("2026-09-09T00:00:07+00:00"),
            )

    def test_completed_handover_cleanup_close_is_distinct_and_exact(self):
        self.target.write_text(
            handover_reconciler.TARGET_CONTENT,
            encoding="utf-8",
        )
        self.attestation["changed_paths"][0]["sha256"] = reconciler.sha256_file(
            self.target
        )
        completed_at = dt.datetime.fromisoformat("2026-09-09T00:00:03.050+00:00")
        parent = handover_reconciler.validate_completed_cleanup_parent_lifecycle(
            self.completed_cleanup_parent_records(),
            self.capsule(),
            self.binding(),
            self.assignment,
            self.final_text(),
            completed_at,
        )
        child = handover_reconciler.validate_child_lifecycle(
            self.child_records(handover=True, completed_cleanup=True),
            self.capsule(),
            self.attestation,
            self.writer_receipt(),
            self.target,
            parent["terminated_at"],
            completed_cleanup_close=True,
        )
        self.assertEqual(parent["close_receipt"]["previous_status"], {"completed": self.final_text()})
        self.assertIsNone(child["second_turn_started_at"])
        self.assertIsNone(child["turn_aborted_at"])

        wrong = self.close_receipt()
        with self.assertRaisesRegex(
            reconciler.ReconciliationError,
            "completed-child cleanup close receipt",
        ):
            handover_reconciler.validate_completed_cleanup_parent_lifecycle(
                self.completed_cleanup_parent_records(close=wrong),
                self.capsule(),
                self.binding(),
                self.assignment,
                self.final_text(),
                completed_at,
            )

        early_wait = self.completed_cleanup_parent_records()
        early_wait[3]["timestamp"] = "2026-09-09T00:00:02.9Z"
        with self.assertRaisesRegex(
            reconciler.ReconciliationError,
            "cleanup ordering",
        ):
            handover_reconciler.validate_completed_cleanup_parent_lifecycle(
                early_wait,
                self.capsule(),
                self.binding(),
                self.assignment,
                self.final_text(),
                completed_at,
            )

    def test_unconfirmed_process_and_second_child_tool_fail_closed(self):
        close = self.close_receipt()
        close["tracked_process_ids_by_thread"] = {self.child_thread: [77]}
        close["unconfirmed_exit_process_ids_by_thread"] = {self.child_thread: [77]}
        close["tracked_process_termination_confirmed"] = False
        close["closed_catalog_actor_quiescence_claimed"] = False
        with self.assertRaisesRegex(reconciler.ReconciliationError, "bounded write actor"):
            reconciler.validate_parent_lifecycle(
                self.parent_records(close=close),
                self.capsule(),
                self.binding(),
                self.assignment,
                self.final_text(),
                dt.datetime.fromisoformat("2026-09-09T00:00:03.050+00:00"),
            )

        child = self.child_records()
        child.insert(
            -1,
            self.call(
                "apply_patch",
                "second-write",
                {},
                "2026-09-09T00:00:05Z",
                kind="custom_tool_call",
            ),
        )
        with self.assertRaisesRegex(reconciler.ReconciliationError, "exactly one"):
            reconciler.validate_child_lifecycle(
                child,
                self.capsule(),
                self.attestation,
                self.writer_receipt(),
                self.target,
                dt.datetime.fromisoformat("2026-09-09T00:00:07+00:00"),
            )

    def test_noncontiguous_or_extra_hook_event_fails_closed(self):
        chain = self.hook_chain()
        chain["events"][3]["sequence"] = 15
        with self.assertRaisesRegex(reconciler.ReconciliationError, "contiguous"):
            reconciler.validate_hook_chain(
                chain,
                self.capsule(),
                self.binding(),
                self.writer_receipt(),
            )

        chain = self.hook_chain()
        chain["events"].append(dict(chain["events"][-1]))
        with self.assertRaisesRegex(reconciler.ReconciliationError, "five exact"):
            reconciler.validate_hook_chain(
                chain,
                self.capsule(),
                self.binding(),
                self.writer_receipt(),
            )


if __name__ == "__main__":
    unittest.main()
