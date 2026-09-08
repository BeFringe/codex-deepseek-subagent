import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_g4_write_probe_prompt.py"


class G4WriteProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="codex-g4-write-prompt-", dir="/private/tmp"
        )
        self.root = Path(self.directory.name).resolve()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "phase1-evidence.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Fixture"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "docs/phase1-evidence.md"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "baseline"], check=True, capture_output=True)
        self.target = self.root / "qualified.txt"
        self.output = Path(self.directory.name + ".prompt")

    def tearDown(self):
        if self.output.exists():
            self.output.unlink()
        self.directory.cleanup()

    def run_builder(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), "--task-name", "qualified_write", "--target", str(self.target), "--output", str(self.output)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_prompt_binds_exact_write_authority_and_expected_final_snapshot(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self.output.read_text(encoding="utf-8")
        declaration = json.loads(
            prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        self.assertEqual(declaration["assignment_mutation_mode"], "write")
        self.assertEqual(declaration["parent_recorded_user_write_intent"], "allow")
        self.assertEqual(declaration["owned_paths"], ["qualified.txt"])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(declaration["verification"], ["exact-path child apply_patch qualification probe"])
        self.assertIn("one exact owned-path apply_patch", declaration["stop_condition"])
        self.assertIn(str(self.target), prompt)
        self.assertIn("4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c", prompt)

    def test_dirty_root_fails_before_prompt_publication(self):
        (self.root / "foreign.txt").write_text("dirty\n", encoding="utf-8")
        result = self.run_builder()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
