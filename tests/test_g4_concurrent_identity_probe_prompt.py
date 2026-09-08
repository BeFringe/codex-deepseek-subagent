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


concurrent_prompt = load_module(
    "build_g4_concurrent_identity_probe_prompt",
    REPO / "probes" / "build_g4_concurrent_identity_probe_prompt.py",
)


class G4ConcurrentIdentityProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "repository"
        self.root.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "phase1-evidence.md").write_text(
            "fixture evidence\n", encoding="utf-8"
        )
        self.git("add", "docs/phase1-evidence.md")
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

    def declarations(self, prompt):
        return [
            json.loads(value)
            for value in re.findall(
                r"BEGIN CODEX WORKER AUTHORITY\n(.+?)\nEND CODEX WORKER AUTHORITY",
                prompt,
                flags=re.DOTALL,
            )
        ]

    def test_prompt_requires_two_immediate_spawns_before_any_wait(self):
        first = "g4_concurrent_a"
        second = "g4_concurrent_b"
        prompt = concurrent_prompt.build_concurrent_prompt(self.root, (first, second))

        self.assertNotIn("one assistant tool-call batch", prompt)
        self.assertIn("Emit exactly two native spawn_agent calls before any other call", prompt)
        self.assertIn(f"task_name={first}", prompt)
        self.assertIn(f"task_name={second}", prompt)
        self.assertIn("As soon as A's spawn_agent call returns", prompt)
        self.assertIn("A staged or task-path-only spawn result is successful dispatch", prompt)
        self.assertIn("must not prevent B's spawn", prompt)
        self.assertIn("Do not call any other tool", prompt)
        self.assertIn("or wait for A between the two spawn calls", prompt)
        self.assertIn("until both exact children have reached terminal completion", prompt)
        self.assertIn("Qualification requires actual child execution overlap", prompt)
        self.assertIn("B must start before A reaches any terminal callback", prompt)
        self.assertIn("Same-assistant-response batching is not required", prompt)
        self.assertIn("call no other tool", prompt)
        self.assertNotIn("API_KEY", prompt)

    def test_default_names_advance_past_the_frozen_orphan_attempt(self):
        self.assertEqual(
            concurrent_prompt.DEFAULT_TASK_NAMES,
            ("g4_concurrent_identity_a2", "g4_concurrent_identity_b2"),
        )

    def test_each_child_has_one_strict_read_only_identity_capsule(self):
        prompt = concurrent_prompt.build_concurrent_prompt(
            self.root, ("g4_concurrent_a", "g4_concurrent_b")
        )
        declarations = self.declarations(prompt)

        self.assertEqual(len(declarations), 2)
        self.assertEqual(prompt.count("Call native list_agents exactly once"), 2)
        for declaration in declarations:
            self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
            self.assertEqual(declaration["parent_recorded_user_write_intent"], "deny")
            self.assertEqual(declaration["owned_paths"], [])
            self.assertEqual(declaration["excluded_paths"], [])
            self.assertFalse(any(declaration["git_authority"].values()))
            self.assertEqual(
                declaration["verification"], ["native list_agents read-only probe"]
            )

    def test_duplicate_wrong_count_and_noncanonical_names_fail_closed(self):
        with self.assertRaisesRegex(concurrent_prompt.ProbePromptError, "exactly two"):
            concurrent_prompt.build_concurrent_prompt(self.root, ("g4_only_one",))
        with self.assertRaisesRegex(concurrent_prompt.ProbePromptError, "distinct"):
            concurrent_prompt.build_concurrent_prompt(
                self.root, ("g4_same", "g4_same")
            )
        with self.assertRaisesRegex(concurrent_prompt.ProbePromptError, "lowercase"):
            concurrent_prompt.build_concurrent_prompt(
                self.root, ("g4_valid", "G4/invalid")
            )

    def test_dirty_worktree_fails_before_any_concurrent_prompt_is_built(self):
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(concurrent_prompt.ProbePromptError, "clean worktree"):
            concurrent_prompt.build_concurrent_prompt(
                self.root, ("g4_concurrent_a", "g4_concurrent_b")
            )


if __name__ == "__main__":
    unittest.main()
