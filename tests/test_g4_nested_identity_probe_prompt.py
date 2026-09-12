from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nested_probe = load_module(
    "build_g4_nested_identity_probe_prompt",
    ROOT / "probes" / "build_g4_nested_identity_probe_prompt.py",
)


class G4NestedIdentityProbePromptTests(unittest.TestCase):
    def setUp(self) -> None:
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

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def test_prompt_binds_root_outer_and_inner_identity_without_write_authority(self) -> None:
        head = self.git("rev-parse", "HEAD").stdout.strip()
        prompt = nested_probe.build_nested_prompt(
            self.root,
            "g4_nested_parent_test",
            "g4_nested_child_test",
        )
        declaration_text = prompt.split(
            "BEGIN CODEX WORKER AUTHORITY\n", 1
        )[1].split("\nEND CODEX WORKER AUTHORITY", 1)[0]
        declaration = json.loads(declaration_text)

        self.assertIn("agent_type=explorer", prompt)
        self.assertIn("agent_type=g4_qualification_probe_worker", prompt)
        self.assertEqual(prompt.count("fork_turns=none"), 2)
        self.assertIn("/root/g4_nested_parent_test", prompt)
        self.assertIn(
            "/root/g4_nested_parent_test/g4_nested_child_test",
            prompt,
        )
        self.assertEqual(prompt.count("BEGIN CODEX WORKER AUTHORITY"), 1)
        self.assertEqual(prompt.count("END CODEX WORKER AUTHORITY"), 1)
        self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
        self.assertEqual(declaration["owned_paths"], [])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(
            declaration["location_preflight"],
            {
                "expected_root": str(self.root.resolve()),
                "expected_branch": "main",
                "expected_base_head": head,
            },
        )
        self.assertNotIn("API_KEY", prompt)
        self.assertIn("do not perform the inner spawn yourself", prompt)

    def test_dirty_root_and_ambiguous_task_names_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            nested_probe.ProbePromptError, "must be distinct"
        ):
            nested_probe.build_nested_prompt(self.root, "same", "same")
        with self.assertRaisesRegex(
            nested_probe.ProbePromptError, "outer task name"
        ):
            nested_probe.build_nested_prompt(self.root, "bad/name", "inner")

        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(nested_probe.ProbePromptError, "clean worktree"):
            nested_probe.build_nested_prompt(self.root, "outer", "inner")


if __name__ == "__main__":
    unittest.main()
