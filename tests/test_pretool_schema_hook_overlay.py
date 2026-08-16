import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_pretool_schema_hook_overlay.py"


class PreToolSchemaHookOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.observed_root = self.root / "observed repository"
        self.observed_root.mkdir()
        self.input = self.root / "hooks.json"
        self.output = self.root / "overlay.json"
        self.config = {
            "hooks": {
                "SubagentStart": [
                    {
                        "matcher": "^v4_flash_worker$",
                        "hooks": [{"type": "command", "command": "v4-hook --mode hook"}],
                    },
                    {
                        "matcher": "^g4_qualification_probe_worker$",
                        "hooks": [{"type": "command", "command": "g4-hook --event start"}],
                    },
                ],
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    "g4-hook --state-directory state "
                                    "--plaintext-agent-type g4_qualification_probe_worker"
                                ),
                            }
                        ],
                    }
                ],
                "PostToolUse": [
                    {"matcher": "apply_patch", "hooks": [{"type": "command", "command": "g4-hook"}]}
                ],
                "PreCompact": [],
                "SubagentStop": [],
            }
        }
        self.input.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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
                "--observation-root",
                str(self.observed_root),
                "--expected-input-sha256",
                expected_hash or self.sha256(self.input),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_hash_pinned_builder_changes_only_one_pretool_command(self):
        built = self.run_builder()

        self.assertEqual(built.returncode, 0, built.stderr)
        report = json.loads(built.stdout)
        self.assertEqual(report["changed_event"], "PreToolUse")
        self.assertEqual(report["changed_command_count"], 1)
        self.assertTrue(report["other_hook_events_unchanged"])
        overlay = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(
            overlay["hooks"]["SubagentStart"],
            self.config["hooks"]["SubagentStart"],
        )
        command = overlay["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("--pretool-schema-observation-root", command)
        self.assertIn("'" + str(self.observed_root.resolve()) + "'", command)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_hash_drift_fails_without_output(self):
        rejected = self.run_builder(expected_hash="0" * 64)

        self.assertEqual(rejected.returncode, 2)
        self.assertIn("does not match", rejected.stderr)
        self.assertFalse(self.output.exists())

    def test_ambiguous_target_and_existing_overlay_fail_closed(self):
        duplicate = self.config["hooks"]["PreToolUse"][0]["hooks"][0].copy()
        self.config["hooks"]["PreToolUse"][0]["hooks"].append(duplicate)
        self.input.write_text(json.dumps(self.config), encoding="utf-8")
        ambiguous = self.run_builder()
        self.assertEqual(ambiguous.returncode, 2)
        self.assertIn("found 2", ambiguous.stderr)

        self.config["hooks"]["PreToolUse"][0]["hooks"] = [duplicate]
        self.config["hooks"]["PreToolUse"][0]["hooks"][0]["command"] += (
            " --pretool-schema-observation-root /tmp/root"
        )
        self.input.write_text(json.dumps(self.config), encoding="utf-8")
        already_enabled = self.run_builder(output=self.root / "second.json")
        self.assertEqual(already_enabled.returncode, 2)
        self.assertIn("already enabled", already_enabled.stderr)


if __name__ == "__main__":
    unittest.main()
