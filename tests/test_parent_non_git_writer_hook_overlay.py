import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from private_output_assertions import assert_private_output


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_parent_non_git_writer_hook_overlay.py"


class ParentNonGitWriterHookOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.non_git_root = self.root / "non-git root"
        self.non_git_root.mkdir()
        self.input = self.root / "hooks.json"
        self.output = self.root / "overlay.json"
        g4_command = (
            "g4-hook --state-directory state "
            "--plaintext-agent-type g4_qualification_probe_worker"
        )
        self.config = {
            "hooks": {
                "SubagentStart": [
                    {
                        "matcher": "^v4_flash_worker$",
                        "hooks": [{"type": "command", "command": "v4-hook --mode hook"}],
                    },
                    {
                        "matcher": "^g4_qualification_probe_worker$",
                        "hooks": [{"type": "command", "command": g4_command}],
                    },
                ],
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": g4_command}],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "apply_patch",
                        "hooks": [{"type": "command", "command": g4_command}],
                    }
                ],
                "PreCompact": [],
                "SubagentStop": [],
            }
        }
        self.input.write_text(json.dumps(self.config) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def sha256(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run_builder(self, *, expected_hash=None, output=None):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(self.input),
                "--output",
                str(output or self.output),
                "--non-git-root",
                str(self.non_git_root),
                "--expected-input-sha256",
                expected_hash or self.sha256(self.input),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_hash_pinned_overlay_changes_only_pre_and_post_tool_use(self):
        built = self.run_builder()

        self.assertEqual(built.returncode, 0, built.stderr)
        report = json.loads(built.stdout)
        self.assertEqual(report["authorization_ceiling"], "parent_only")
        self.assertEqual(report["changed_command_count"], 2)
        self.assertEqual(report["changed_events"], ["PostToolUse", "PreToolUse"])
        self.assertTrue(report["other_hook_events_unchanged"])
        overlay = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(
            overlay["hooks"]["SubagentStart"],
            self.config["hooks"]["SubagentStart"],
        )
        for event in ("PreToolUse", "PostToolUse"):
            command = overlay["hooks"][event][0]["hooks"][0]["command"]
            self.assertIn("--parent-non-git-writer-root", command)
            self.assertIn("'" + str(self.non_git_root) + "'", command)
        assert_private_output(self, self.output)

    def test_hash_drift_and_duplicate_target_fail_without_output(self):
        drift = self.run_builder(expected_hash="0" * 64)
        self.assertEqual(drift.returncode, 2)
        self.assertFalse(self.output.exists())

        duplicate = self.config["hooks"]["PreToolUse"][0]["hooks"][0].copy()
        self.config["hooks"]["PreToolUse"][0]["hooks"].append(duplicate)
        self.input.write_text(json.dumps(self.config), encoding="utf-8")
        ambiguous = self.run_builder(output=self.root / "second.json")
        self.assertEqual(ambiguous.returncode, 2)
        self.assertIn("found 2", ambiguous.stderr)

    def test_existing_ceiling_fails_closed(self):
        self.config["hooks"]["PostToolUse"][0]["hooks"][0]["command"] += (
            " --parent-non-git-writer-root /private/tmp"
        )
        self.input.write_text(json.dumps(self.config), encoding="utf-8")

        result = self.run_builder()

        self.assertEqual(result.returncode, 2)
        self.assertIn("already configured", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
