import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


session_close_prompt = load_module(
    "build_g4_session_close_probe_prompt",
    REPO / "probes" / "build_g4_session_close_probe_prompt.py",
)


class G4SessionCloseProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.root = temporary_root / "repository"
        self.state = temporary_root / "state"
        self.root.mkdir()
        self.state.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "phase1-evidence.md").write_text(
            "fixture evidence\n", encoding="utf-8"
        )
        (self.root / "hooks").mkdir()
        (self.root / "hooks" / "authority_watchdog.py").write_text(
            "# fixture\n", encoding="utf-8"
        )
        self.git("add", "docs/phase1-evidence.md", "hooks/authority_watchdog.py")
        self.git("commit", "-m", "baseline")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def build(self, task_name="g4_session_close_test"):
        return session_close_prompt.build_session_close_prompt(
            self.root,
            self.state,
            task_name,
        )

    def declaration(self, prompt):
        matches = re.findall(
            r"BEGIN CODEX WORKER AUTHORITY\n(.+?)\nEND CODEX WORKER AUTHORITY",
            prompt,
            flags=re.DOTALL,
        )
        self.assertEqual(len(matches), 1)
        return json.loads(matches[0])

    def test_prompt_orders_native_wait_close_and_post_close_observation(self):
        prompt = self.build()
        spawn = prompt.index("g4_assignment.spawn_agent tool exactly once")
        wait = prompt.index("g4_assignment.wait_agent tool exactly once")
        close = prompt.index("g4_assignment.close_agent tool exactly once")
        listing = prompt.index("g4_assignment.list_agents tool exactly once")

        self.assertLess(spawn, wait)
        self.assertLess(wait, close)
        self.assertLess(close, listing)
        self.assertIn("timeout_ms=5000", prompt)
        self.assertIn("has no target list", prompt)
        self.assertIn("session_loop_terminated=true", prompt)
        self.assertIn("process_tree_quiescence_claimed=false", prompt)
        self.assertIn("not filesystem or detached-process quiescence proof", prompt)
        self.assertIn("Do not infer mutation quiescence", prompt)
        self.assertIn("do not run a watchdog", prompt)
        self.assertNotIn("exec_command exactly once", prompt)
        self.assertNotIn("API_KEY", prompt)

    def test_capsule_is_short_lived_read_only_and_exactly_bound(self):
        task_name = "g4_session_close_exact"
        prompt = self.build(task_name)
        declaration = self.declaration(prompt)

        self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
        self.assertEqual(declaration["parent_recorded_user_write_intent"], "deny")
        self.assertEqual(declaration["owned_paths"], [])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(
            declaration["pre_write_attestation_timeout_seconds"],
            session_close_prompt.PRE_WRITE_TIMEOUT_SECONDS,
        )
        self.assertIn("without calling tools", declaration["stop_condition"])
        self.assertIn(f"task_name={task_name}", prompt)
        self.assertIn(f"target=/root/{task_name}", prompt)
        self.assertIn("expose the staged assignment_id", prompt)
        self.assertIn("WAITING_FOR_PARENT_CLOSE", prompt)

    def test_invalid_task_and_dirty_root_fail_closed(self):
        with self.assertRaisesRegex(session_close_prompt.ProbePromptError, "lowercase"):
            self.build("G4/invalid")
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(session_close_prompt.ProbePromptError, "clean worktree"):
            self.build()


if __name__ == "__main__":
    unittest.main()
