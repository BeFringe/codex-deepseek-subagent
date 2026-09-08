import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_child_write_probe_hook_overlay.py"
HOOK = ROOT / "hooks" / "compatibility_hook.py"
EVENTS = ("SubagentStart", "PreToolUse", "PostToolUse", "PreCompact", "SubagentStop")


class ChildWriteProbeHookOverlayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.input = self.root / "hooks.json"
        self.output = self.root / "overlay.json"
        self.git_directory = tempfile.TemporaryDirectory(
            prefix="codex-g4-write-overlay-", dir="/private/tmp"
        )
        self.git_root = Path(self.git_directory.name).resolve()
        subprocess.run(["git", "-C", str(self.git_root), "init", "-b", "main"], check=True, capture_output=True)
        self.target = self.git_root / "qualified.txt"
        self.config = {"hooks": {}}
        for event in EVENTS:
            matcher = "apply_patch" if event == "PostToolUse" else "*"
            self.config["hooks"][event] = [
                {
                    "matcher": matcher,
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
        self.git_directory.cleanup()

    def digest(self):
        return hashlib.sha256(self.input.read_bytes()).hexdigest()

    def run_builder(self, *, expected=None, output=None):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(self.input),
                "--output",
                str(output or self.output),
                "--expected-input-sha256",
                expected or self.digest(),
                "--task-name",
                "qualified_write",
                "--target",
                str(self.target),
                "--hook-script",
                str(HOOK),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_overlay_repoints_only_g4_commands_and_adds_one_exact_ceiling(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["changed_command_count"], 5)
        self.assertEqual(report["changed_events"], sorted(EVENTS))
        self.assertTrue(report["v4_entries_preserved"])
        overlay = json.loads(self.output.read_text(encoding="utf-8"))
        option_count = 0
        for event in EVENTS:
            before = self.config["hooks"][event][0]["hooks"]
            after = overlay["hooks"][event][0]["hooks"]
            self.assertEqual(after[0], before[0])
            self.assertIn(str(HOOK), after[1]["command"])
            option_count += after[1]["command"].count("--child-write-probe")
        self.assertEqual(option_count, 1)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_hash_drift_and_existing_target_fail_closed(self):
        drift = self.run_builder(expected="0" * 64)
        self.assertEqual(drift.returncode, 2)
        self.assertFalse(self.output.exists())
        self.target.write_text("occupied\n", encoding="utf-8")
        occupied = self.run_builder(output=self.root / "occupied.json")
        self.assertEqual(occupied.returncode, 2)
        self.assertIn("absent", occupied.stderr)


if __name__ == "__main__":
    unittest.main()
