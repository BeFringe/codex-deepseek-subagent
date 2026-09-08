import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_g4_postcompact_scope_drift_probe_prompt.py"


def load_module():
    spec = importlib.util.spec_from_file_location("g4_postcompact_drift_prompt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prompt_builder = load_module()


class G4PostcompactScopeDriftProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="codex-g4-postcompact-drift-prompt-", dir="/private/tmp"
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

    def test_prompt_binds_real_compaction_foreign_path_and_terminal_marker(self):
        prompt = prompt_builder.build_prompt(self.root, "g4_postcompact_drift_test")
        declaration = json.loads(
            re.search(
                r"BEGIN CODEX WORKER AUTHORITY\n(.+?)\nEND CODEX WORKER AUTHORITY",
                prompt,
                flags=re.DOTALL,
            ).group(1)
        )

        self.assertIn("Call native list_agents sequentially exactly four times", prompt)
        self.assertIn(prompt_builder.TARGET_NAME, prompt)
        self.assertIn(prompt_builder.FINAL_MARKER, prompt)
        self.assertIn("task_name=g4_postcompact_drift_test", prompt)
        self.assertIn("/root/g4_postcompact_drift_test", prompt)
        self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
        self.assertEqual(declaration["owned_paths"], [])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(declaration["verification"], [prompt_builder.VERIFICATION])
        self.assertEqual(
            declaration["authority_provenance"]["test_only_injection_seams"],
            ["phase1.host.postcompact_foreign_scope_drift"],
        )
        self.assertIn("before the fourth", declaration["stop_condition"])

    def test_cli_publishes_one_private_hash_bound_prompt(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--task-name",
                "g4_postcompact_drift_test",
                "--output",
                str(self.output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["output"], str(self.output))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertRegex(result["sha256"], r"^[0-9a-f]{64}$")
        duplicate = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--output",
                str(self.output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(duplicate.returncode, 2)


if __name__ == "__main__":
    unittest.main()
