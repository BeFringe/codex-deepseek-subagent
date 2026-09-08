import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_g4_compact_resume_probe_prompt.py"


def load_module():
    spec = importlib.util.spec_from_file_location("g4_compact_prompt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compact_prompt = load_module()


class G4CompactResumeProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="codex-g4-compact-prompt-", dir="/private/tmp"
        )
        self.root = Path(self.directory.name).resolve()
        self.output = Path(self.directory.name + ".prompt")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "phase1-evidence.md").write_text(
            "fixture evidence\n", encoding="utf-8"
        )
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Fixture"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "fixture@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "add", "docs/phase1-evidence.md"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", "baseline"],
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        if self.output.exists():
            self.output.unlink()
        self.directory.cleanup()

    def test_prompt_binds_four_calls_and_recovery_without_mutation(self):
        prompt = compact_prompt.build_prompt(self.root, "g4_compact_test")
        declaration = json.loads(
            re.search(
                r"BEGIN CODEX WORKER AUTHORITY\n(.+?)\nEND CODEX WORKER AUTHORITY",
                prompt,
                flags=re.DOTALL,
            ).group(1)
        )

        self.assertEqual(prompt.count("Call native list_agents exactly four times"), 1)
        self.assertIn("recovery_count to be greater than zero", prompt)
        self.assertIn("task_name=g4_compact_test", prompt)
        self.assertIn("/root/g4_compact_test", prompt)
        self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
        self.assertEqual(declaration["owned_paths"], [])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(declaration["verification"], [compact_prompt.VERIFICATION])
        self.assertIn("PreCompact epoch", declaration["stop_condition"])
        self.assertIn("before the fourth result", declaration["stop_condition"])
        self.assertIn("exactly `command` and `exit_code`", prompt)
        self.assertIn("Do not add a top-level `schema` key", prompt)

    def test_cli_can_publish_one_private_hash_bound_prompt(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--task-name",
                "g4_compact_test",
                "--output",
                str(self.output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["output"], str(self.output))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertRegex(report["sha256"], r"^[0-9a-f]{64}$")
        duplicate = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--task-name",
                "g4_compact_test",
                "--output",
                str(self.output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(duplicate.returncode, 2)

    def test_dirty_root_and_noncanonical_task_fail_closed(self):
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(compact_prompt.ProbePromptError, "clean worktree"):
            compact_prompt.build_prompt(self.root, "g4_compact_test")
        with self.assertRaisesRegex(compact_prompt.ProbePromptError, "lowercase"):
            compact_prompt.build_prompt(self.root, "G4/invalid")


if __name__ == "__main__":
    unittest.main()
