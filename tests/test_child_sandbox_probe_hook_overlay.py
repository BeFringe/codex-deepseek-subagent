import hashlib
import json
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import unittest
from private_output_assertions import assert_private_output


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_child_sandbox_probe_hook_overlay.py"


class ChildSandboxProbeHookOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.input = self.root / "hooks.json"
        self.output = self.root / "overlay.json"
        self.target = Path(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp").resolve() / (
            "codex-g4-sandbox-overlay-" + self.root.name
        )
        g4_command = (
            "g4-hook --state-directory state "
            "--plaintext-agent-type g4_qualification_probe_worker "
            "--parent-non-git-writer-root /private/tmp"
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
                        "hooks": [{"type": "command", "command": "g4-hook"}],
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

    def run_builder(self, *, expected_hash=None, output=None, task_name="g4_sandbox_1"):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(self.input),
                "--output",
                str(output or self.output),
                "--task-name",
                task_name,
                "--target",
                str(self.target),
                "--expected-input-sha256",
                expected_hash or self.sha256(self.input),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_overlay_changes_only_exact_g4_pretooluse_command(self):
        built = self.run_builder()

        self.assertEqual(built.returncode, 0, built.stderr)
        report = json.loads(built.stdout)
        self.assertEqual(
            report["authorization_ceiling"], "qualification_sandbox_probe_only"
        )
        self.assertEqual(report["changed_events"], ["PreToolUse"])
        self.assertEqual(report["changed_command_count"], 1)
        self.assertTrue(report["authority_consumed_before_execution"])
        overlay = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(
            overlay["hooks"]["SubagentStart"], self.config["hooks"]["SubagentStart"]
        )
        self.assertEqual(
            overlay["hooks"]["PostToolUse"], self.config["hooks"]["PostToolUse"]
        )
        command = overlay["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("--parent-non-git-writer-root /private/tmp", command)
        arguments = shlex.split(command)
        self.assertEqual(arguments[arguments.index("--child-sandbox-probe") + 1],
                         f"g4_sandbox_1={self.target}")
        assert_private_output(self, self.output)

    def test_hash_drift_bad_task_and_duplicate_option_fail_closed(self):
        drift = self.run_builder(expected_hash="0" * 64)
        self.assertEqual(drift.returncode, 2)
        self.assertFalse(self.output.exists())

        bad_task = self.run_builder(
            output=self.root / "bad-task.json", task_name="G4/sandbox"
        )
        self.assertEqual(bad_task.returncode, 2)
        self.assertIn("task name", bad_task.stderr)

        self.config["hooks"]["PreToolUse"][0]["hooks"][0]["command"] += (
            f" --child-sandbox-probe old_task={self.target}"
        )
        self.input.write_text(json.dumps(self.config), encoding="utf-8")
        duplicate = self.run_builder(output=self.root / "duplicate.json")
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn("already configured", duplicate.stderr)


if __name__ == "__main__":
    unittest.main()
