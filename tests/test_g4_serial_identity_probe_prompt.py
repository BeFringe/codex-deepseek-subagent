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


serial_prompt = load_module(
    "build_g4_serial_identity_probe_prompt",
    REPO / "probes" / "build_g4_serial_identity_probe_prompt.py",
)


class G4SerialIdentityProbePromptTests(unittest.TestCase):
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

    def test_prompt_requires_two_distinct_serial_children_and_callbacks(self):
        first = "g4_serial_a"
        second = "g4_serial_b"
        prompt = serial_prompt.build_serial_prompt(self.root, (first, second))

        self.assertIn(
            f"1. Call native spawn_agent exactly once with "
            f"agent_type={serial_prompt.AGENT_TYPE}, task_name={first}",
            prompt,
        )
        self.assertIn(
            f"3. Only after child A is terminal, call native spawn_agent exactly once "
            f"with agent_type={serial_prompt.AGENT_TYPE}, task_name={second}",
            prompt,
        )
        self.assertIn(f"task_name={first}", prompt)
        self.assertIn(f"task_name={second}", prompt)
        self.assertIn(f"exactly /root/{first} reaches terminal completion", prompt)
        self.assertIn("Do not spawn child B before this callback", prompt)
        self.assertIn(f"exactly /root/{second} reaches terminal completion", prompt)
        self.assertIn("Never reuse the first child's task name", prompt)
        self.assertIn("call no other tool", prompt)
        self.assertNotIn("API_KEY", prompt)

    def test_each_child_has_an_independent_strict_read_only_capsule(self):
        prompt = serial_prompt.build_serial_prompt(
            self.root, ("g4_serial_a", "g4_serial_b")
        )
        declarations = self.declarations(prompt)

        self.assertEqual(len(declarations), 2)
        self.assertEqual(declarations[0], declarations[1])
        for declaration in declarations:
            self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
            self.assertEqual(declaration["parent_recorded_user_write_intent"], "deny")
            self.assertEqual(declaration["owned_paths"], [])
            self.assertEqual(declaration["excluded_paths"], [])
            self.assertFalse(any(declaration["git_authority"].values()))
            self.assertEqual(declaration["verification"], ["native list_agents read-only probe"])

    def test_duplicate_wrong_count_and_noncanonical_names_fail_closed(self):
        with self.assertRaisesRegex(serial_prompt.ProbePromptError, "exactly two"):
            serial_prompt.build_serial_prompt(self.root, ("g4_only_one",))
        with self.assertRaisesRegex(serial_prompt.ProbePromptError, "distinct"):
            serial_prompt.build_serial_prompt(self.root, ("g4_same", "g4_same"))
        with self.assertRaisesRegex(serial_prompt.ProbePromptError, "lowercase"):
            serial_prompt.build_serial_prompt(self.root, ("g4_valid", "G4/invalid"))

    def test_dirty_worktree_fails_before_any_serial_prompt_is_built(self):
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(serial_prompt.ProbePromptError, "clean worktree"):
            serial_prompt.build_serial_prompt(
                self.root, ("g4_serial_a", "g4_serial_b")
            )


if __name__ == "__main__":
    unittest.main()
