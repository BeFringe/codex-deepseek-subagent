import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_g4_current_hook_overlay.py"
HOOK = ROOT / "hooks" / "compatibility_hook.py"
EVENTS = ("SubagentStart", "PreToolUse", "PostToolUse", "PreCompact", "SubagentStop")


class G4CurrentHookOverlayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.input = self.root / "hooks.json"
        self.output = self.root / "overlay.json"
        self.config = {"hooks": {}}
        for event in EVENTS:
            self.config["hooks"][event] = [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": f"v4-hook --event {event}"},
                        {
                            "type": "command",
                            "command": (
                                "python /old/compatibility_hook.py --state-directory /state "
                                "--plaintext-agent-type g4_qualification_probe_worker"
                            ),
                        },
                    ],
                }
            ]
        self.input.write_text(json.dumps(self.config), encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def run_builder(self, *, digest=None):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(self.input),
                "--output",
                str(self.output),
                "--expected-input-sha256",
                digest or hashlib.sha256(self.input.read_bytes()).hexdigest(),
                "--hook-script",
                str(HOOK),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_repoints_only_the_five_g4_commands_and_preserves_v4(self):
        result = self.run_builder()

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["changed_events"], list(EVENTS))
        self.assertEqual(report["changed_command_count"], 5)
        self.assertFalse(report["qualification_options_added"])
        self.assertTrue(report["v4_entries_preserved"])
        overlay = json.loads(self.output.read_text(encoding="utf-8"))
        for event in EVENTS:
            before = self.config["hooks"][event][0]["hooks"]
            after = overlay["hooks"][event][0]["hooks"]
            self.assertEqual(after[0], before[0])
            self.assertIn(str(HOOK), after[1]["command"])
            self.assertNotIn("--child-write-probe", after[1]["command"])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_input_drift_and_duplicate_g4_command_fail_closed(self):
        drift = self.run_builder(digest="0" * 64)
        self.assertEqual(drift.returncode, 2)
        self.assertFalse(self.output.exists())

        duplicate = dict(self.config["hooks"]["PreCompact"][0]["hooks"][1])
        self.config["hooks"]["PreCompact"][0]["hooks"].append(duplicate)
        self.input.write_text(json.dumps(self.config), encoding="utf-8")
        duplicate_result = self.run_builder()
        self.assertEqual(duplicate_result.returncode, 2)
        self.assertIn("found 2", duplicate_result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
