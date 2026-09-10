import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "hooks" / "plaintext_pair_probe_guard.py"
if str(SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("plaintext_pair_probe_guard", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(guard)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PlaintextPairProbeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="codex-p1-pair-guard-", dir=(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp")
        )
        self.state = Path(self.temporary.name) / "state"
        self.messages = {
            "spawn_agent": "same spawn assignment",
            "send_message": "same queued message",
            "followup_task": "same follow-up message",
        }
        self.configured = {
            operation: digest(message)
            for operation, message in self.messages.items()
        }

    def tearDown(self):
        self.temporary.cleanup()

    def hook(self, operation: str, tool_use_id: str, *, message: str | None = None):
        return {
            "hook_event_name": "PreToolUse",
            "session_id": "01a00147-39cb-7b50-b78d-7baed910eb45",
            "turn_id": "01a00148-39cb-7b50-b78d-7baed910eb45",
            "agent_path": "/root",
            "tool_name": guard.TOOL_NAMES[operation],
            "tool_use_id": tool_use_id,
            "tool_input": {
                "message": self.messages[operation] if message is None else message
            },
        }

    def state_value(self):
        return json.loads(
            (self.state / "plaintext_pair_probe" / "state.json").read_text(
                encoding="utf-8"
            )
        )

    def test_first_distinct_call_allows_and_second_denies_for_each_operation(self):
        for operation in guard.OPERATIONS:
            first = guard.run_guard(
                self.state, self.hook(operation, f"{operation}-1"), self.configured
            )
            second = guard.run_guard(
                self.state, self.hook(operation, f"{operation}-2"), self.configured
            )

            self.assertEqual(first, {})
            specific = second["hookSpecificOutput"]
            self.assertEqual(specific["hookEventName"], "PreToolUse")
            self.assertEqual(specific["permissionDecision"], "deny")
            self.assertIn(operation, specific["permissionDecisionReason"])

        state = guard._validate_state(self.state_value(), self.configured)
        for operation, entries in state["calls"].items():
            self.assertEqual([entry["decision"] for entry in entries], ["allow", "deny"])
            self.assertEqual(
                {entry["message_sha256"] for entry in entries},
                {self.configured[operation]},
            )
        encoded = json.dumps(state, sort_keys=True)
        self.assertNotIn("same spawn assignment", encoded)
        self.assertNotIn("same queued message", encoded)
        self.assertNotIn("same follow-up message", encoded)
        self.assertFalse(state["raw_plaintext_stored"])

    def test_repeated_tool_use_id_is_idempotent(self):
        first = guard.run_guard(
            self.state, self.hook("send_message", "same-id"), self.configured
        )
        repeated = guard.run_guard(
            self.state, self.hook("send_message", "same-id"), self.configured
        )

        self.assertEqual(first, {})
        self.assertEqual(repeated, {})
        self.assertEqual(len(self.state_value()["calls"]["send_message"]), 1)

    def test_unconfigured_fingerprint_passes_without_creating_state(self):
        output = guard.run_guard(
            self.state,
            self.hook("followup_task", "unmatched", message="different message"),
            self.configured,
        )

        self.assertEqual(output, {})
        self.assertFalse(self.state.exists())

    def test_non_target_tool_and_event_pass_through(self):
        hook = self.hook("spawn_agent", "spawn-1")
        hook["tool_name"] = "list_agents"
        self.assertEqual(guard.run_guard(self.state, hook, self.configured), {})
        hook["hook_event_name"] = "PostToolUse"
        self.assertEqual(guard.run_guard(self.state, hook, self.configured), {})

    def test_configuration_requires_all_operations_once(self):
        with self.assertRaisesRegex(guard.ProbeGuardError, "one exact spec"):
            guard.validate_specs([("spawn_agent", "a" * 64)])
        with self.assertRaisesRegex(guard.ProbeGuardError, "one exact spec"):
            guard.validate_specs(
                [
                    ("spawn_agent", "a" * 64),
                    ("spawn_agent", "b" * 64),
                    ("send_message", "c" * 64),
                    ("followup_task", "d" * 64),
                ]
            )

    def test_tampered_state_fails_closed(self):
        guard.run_guard(
            self.state, self.hook("spawn_agent", "spawn-1"), self.configured
        )
        state = self.state_value()
        state["calls"]["spawn_agent"][0]["message_length"] += 1
        target = self.state / "plaintext_pair_probe" / "state.json"
        target.write_text(json.dumps(state), encoding="utf-8")

        with self.assertRaisesRegex(guard.ProbeGuardError, "state hash is invalid"):
            guard.run_guard(
                self.state, self.hook("spawn_agent", "spawn-2"), self.configured
            )

    def test_state_directory_must_be_canonical_private_tmp_descendant(self):
        with self.assertRaisesRegex(guard.ProbeGuardError, "/private/tmp"):
            guard.validate_state_directory(ROOT / "state")

    def test_hook_process_does_not_create_bytecode_beside_its_source(self):
        runtime = Path(self.temporary.name) / "runtime"
        runtime.mkdir()
        shutil.copy2(SCRIPT, runtime / SCRIPT.name)
        shutil.copy2(
            ROOT / "hooks" / "compatibility_state.py",
            runtime / "compatibility_state.py",
        )
        arguments = [
            sys.executable,
            str(runtime / SCRIPT.name),
            "--state-directory",
            str(Path(self.temporary.name) / "subprocess-state"),
        ]
        for operation in guard.OPERATIONS:
            arguments.extend(
                ["--deny-second", f"{operation}={self.configured[operation]}"]
            )

        result = subprocess.run(
            arguments,
            input=json.dumps(self.hook("spawn_agent", "spawn-subprocess")),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})
        self.assertFalse((runtime / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
