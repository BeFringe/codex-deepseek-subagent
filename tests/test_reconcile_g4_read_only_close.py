import importlib.util
import json
from pathlib import Path
import sys
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
    "reconcile_g4_read_only_close",
    ROOT / "probes" / "reconcile_g4_read_only_close.py",
)


class G4ReadOnlyCloseReconciliationTests(unittest.TestCase):
    parent_thread = "parent-thread"
    child_thread = "child-thread"
    agent_path = "/root/g4_p5b_termination_test"
    spawn_id = "spawn-call"
    assignment = "exact read-only assignment"

    def capsule(self):
        return {
            "runtime_session_id": self.parent_thread,
            "parent_thread_id": self.parent_thread,
            "spawn_tool_use_id": self.spawn_id,
            "requested_task_name": "g4_p5b_termination_test",
            "canonical_agent_path": self.agent_path,
        }

    def binding(self):
        return {"child_thread_id": self.child_thread}

    @staticmethod
    def call(name, call_id, arguments, timestamp):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": name,
                "namespace": "g4_assignment",
                "arguments": json.dumps(arguments, separators=(",", ":")),
                "call_id": call_id,
            },
        }

    @staticmethod
    def output(call_id, output, timestamp):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(output, separators=(",", ":")),
            },
        }

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

    def parent_records(self, close=None):
        close = close or self.close_receipt()
        spawn_arguments = {
            "agent_type": "g4_qualification_probe_worker",
            "task_name": "g4_p5b_termination_test",
            "fork_turns": "none",
            "message": self.assignment,
        }
        pre_agents = {
            "agents": [
                {"agent_name": "/root", "agent_status": "running"},
                {"agent_name": self.agent_path, "agent_status": "running"},
            ]
        }
        post_agents = {"agents": [{"agent_name": "/root", "agent_status": "running"}]}
        return [
            self.call("spawn_agent", self.spawn_id, spawn_arguments, "2026-09-09T00:00:00Z"),
            self.output(self.spawn_id, {"task_name": self.agent_path}, "2026-09-09T00:00:01Z"),
            self.call("list_agents", "pre-list", {}, "2026-09-09T00:00:02Z"),
            self.output("pre-list", pre_agents, "2026-09-09T00:00:03Z"),
            self.call("close_agent", "close-call", {"target": self.agent_path}, "2026-09-09T00:00:04Z"),
            self.output("close-call", close, "2026-09-09T00:00:05Z"),
            self.call("list_agents", "post-list", {}, "2026-09-09T00:00:06Z"),
            self.output("post-list", post_agents, "2026-09-09T00:00:07Z"),
        ]

    def child_records(self):
        return [
            {
                "timestamp": "2026-09-09T00:00:01Z",
                "type": "event_msg",
                "payload": {"type": "task_started"},
            },
            {
                "timestamp": "2026-09-09T00:00:04.5Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "developer", "content": []},
            },
            {
                "timestamp": "2026-09-09T00:00:04.6Z",
                "type": "event_msg",
                "payload": {"type": "turn_aborted", "reason": "interrupted"},
            },
        ]

    def hook_chain(self):
        return {
            "events": [
                {
                    "sequence": 40,
                    "hook_event_name": "PreToolUse",
                    "scope": "target_spawn",
                    "tool_use_id": self.spawn_id,
                    "actor": {
                        "runtime_session_id": self.parent_thread,
                        "thread_id": self.parent_thread,
                        "canonical_agent_path": "/root",
                        "agent_type": "root",
                    },
                },
                {
                    "sequence": 41,
                    "hook_event_name": "SubagentStart",
                    "scope": "target_child",
                    "tool_use_id": None,
                    "actor": {
                        "runtime_session_id": self.parent_thread,
                        "thread_id": self.child_thread,
                        "canonical_agent_path": self.agent_path,
                        "agent_type": "g4_qualification_probe_worker",
                    },
                },
            ]
        }

    def test_exact_running_close_is_accepted_without_global_overclaim(self):
        lifecycle = reconciler.validate_parent_lifecycle(
            self.capsule(),
            self.binding(),
            self.assignment,
            self.parent_records(),
        )
        child = reconciler.validate_child_lifecycle(
            self.child_records(), lifecycle["terminated_at"]
        )
        hooks = reconciler.validate_hook_chain(
            self.hook_chain(), self.capsule(), self.binding()
        )

        self.assertEqual(lifecycle["close_tool_use_id"], "close-call")
        self.assertFalse(lifecycle["close_receipt"]["process_tree_quiescence_claimed"])
        self.assertEqual(child["turn_aborted_at"].isoformat(), "2026-09-09T00:00:04.600000+00:00")
        self.assertEqual([event["sequence"] for event in hooks], [40, 41])

    def test_unconfirmed_process_fails_closed(self):
        close = self.close_receipt()
        close["tracked_process_ids_by_thread"] = {self.child_thread: [77]}
        close["unconfirmed_exit_process_ids_by_thread"] = {self.child_thread: [77]}
        close["tracked_process_termination_confirmed"] = False
        close["closed_catalog_actor_quiescence_claimed"] = False

        with self.assertRaisesRegex(
            reconciler.ReconciliationError,
            "bounded actor barrier",
        ):
            reconciler.validate_parent_lifecycle(
                self.capsule(),
                self.binding(),
                self.assignment,
                self.parent_records(close),
            )

    def test_child_tool_or_final_fails_closed(self):
        records = self.child_records()
        records.insert(
            1,
            self.call("apply_patch", "child-write", {}, "2026-09-09T00:00:03Z"),
        )
        with self.assertRaisesRegex(reconciler.ReconciliationError, "called a tool"):
            reconciler.validate_child_lifecycle(
                records,
                reconciler.parse_timestamp("2026-09-09T00:00:05Z", "close"),
            )

        records = self.child_records()
        records.insert(
            1,
            {
                "timestamp": "2026-09-09T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": []},
            },
        )
        with self.assertRaisesRegex(reconciler.ReconciliationError, "produced a message"):
            reconciler.validate_child_lifecycle(
                records,
                reconciler.parse_timestamp("2026-09-09T00:00:05Z", "close"),
            )

    def test_missing_or_noncontiguous_subagentstart_fails_closed(self):
        chain = self.hook_chain()
        chain["events"][1]["sequence"] = 42
        with self.assertRaisesRegex(reconciler.ReconciliationError, "bind"):
            reconciler.validate_hook_chain(
                chain,
                self.capsule(),
                self.binding(),
            )

        chain = self.hook_chain()
        chain["events"].pop()
        with self.assertRaisesRegex(reconciler.ReconciliationError, "one spawn"):
            reconciler.validate_hook_chain(
                chain,
                self.capsule(),
                self.binding(),
            )


if __name__ == "__main__":
    unittest.main()
