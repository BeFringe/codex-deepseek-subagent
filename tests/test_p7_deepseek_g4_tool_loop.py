from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]
PROBES = REPO / "probes"
SCRIPT = PROBES / "run_p7_deepseek_g4_tool_loop.py"
sys.path.insert(0, str(PROBES))
SPEC = importlib.util.spec_from_file_location("run_p7_deepseek_g4_tool_loop", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def child_rollout(namespace: str | None) -> list[dict[str, object]]:
    call = {
        "type": "function_call",
        "name": "list_agents",
        "arguments": "{}",
        "call_id": "call-test",
    }
    if namespace is not None:
        call["namespace"] = namespace
    return [
        {
            "kind": "child",
            "records": [
                {"type": "response_item", "payload": call},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-test",
                        "output": '{"agents":[]}',
                    },
                },
            ],
        }
    ]


class DeepSeekG4ToolLoopTests(unittest.TestCase):
    def test_accepts_namespaced_baseline_call(self) -> None:
        result = MODULE.observed_tool_loop(
            child_rollout("g4_assignment"),
            expected_namespace="g4_assignment",
        )

        self.assertTrue(result["exact_single_empty_arguments_call"])
        self.assertTrue(result["matching_output_present"])

    def test_accepts_flat_function_wire_call(self) -> None:
        result = MODULE.observed_tool_loop(
            child_rollout(None),
            expected_namespace=None,
        )

        self.assertTrue(result["exact_single_empty_arguments_call"])
        self.assertTrue(result["matching_output_present"])
        self.assertEqual(len(result["matching_call_id_outputs"]), 1)

    def test_rejects_wrong_namespace(self) -> None:
        result = MODULE.observed_tool_loop(
            child_rollout("g4_assignment"),
            expected_namespace=None,
        )

        self.assertFalse(result["exact_single_empty_arguments_call"])
        self.assertTrue(result["matching_output_present"])

    def test_parent_lifecycle_requires_close_and_post_close_absence(self) -> None:
        close_output = {
            "session_loop_terminated": True,
            "tracked_process_termination_confirmed": True,
            "closed_catalog_actor_quiescence_claimed": True,
            "process_tree_quiescence_claimed": False,
            "tracked_process_ids_by_thread": {"child": []},
            "confirmed_exit_process_ids_by_thread": {"child": []},
            "unconfirmed_exit_process_ids_by_thread": {"child": []},
            "unresolved_start_process_ids_by_thread": {"child": []},
        }
        records = [
            {
                "ordinal": 1,
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "close_agent",
                    "call_id": "close",
                },
            },
            {
                "ordinal": 2,
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "close",
                    "output": json.dumps(close_output),
                },
            },
            {
                "ordinal": 3,
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "list_agents",
                    "call_id": "list",
                },
            },
            {
                "ordinal": 4,
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "list",
                    "output": '{"agents":[{"agent_name":"/root"}]}',
                },
            },
        ]

        result = MODULE.observed_parent_lifecycle(
            [{"kind": "parent", "records": records}]
        )

        self.assertTrue(result["close_catalog_quiesced"])
        self.assertTrue(result["post_close_child_absent"])
        self.assertFalse(result["process_tree_quiescence_claimed"])


if __name__ == "__main__":
    unittest.main()
