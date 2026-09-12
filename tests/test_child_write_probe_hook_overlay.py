import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from private_output_assertions import assert_private_output


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
            prefix="codex-g4-write-overlay-", dir=(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp")
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

    def run_builder(
        self,
        *,
        expected=None,
        output=None,
        writer_hold_seconds=0,
        handover=False,
    ):
        command = [
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
            ]
        if writer_hold_seconds:
            command.extend(["--writer-hold-seconds", str(writer_hold_seconds)])
        if handover:
            command.append("--handover")
        return subprocess.run(
            command,
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
        assert_private_output(self, self.output)

    def test_overlay_can_add_one_bounded_child_lease_hold(self):
        result = self.run_builder(writer_hold_seconds=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["writer_hold_seconds"], 8)
        overlay = json.loads(self.output.read_text(encoding="utf-8"))
        commands = [
            command["command"]
            for matcher in overlay["hooks"]["PreToolUse"]
            for command in matcher["hooks"]
            if "g4_qualification_probe_worker" in command.get("command", "")
        ]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].count("--qualification-writer-hold-seconds"), 1)
        for event in ("SubagentStart", "PostToolUse", "PreCompact", "SubagentStop"):
            self.assertNotIn(
                "--qualification-writer-hold-seconds",
                json.dumps(overlay["hooks"][event]),
            )

    def test_overlay_rejects_out_of_range_writer_hold(self):
        for seconds in (-1, 11):
            with self.subTest(seconds=seconds):
                output = self.root / f"hold-{seconds}.json"
                result = self.run_builder(
                    output=output,
                    writer_hold_seconds=seconds,
                )
                self.assertEqual(result.returncode, 2)
                self.assertFalse(output.exists())

    def test_handover_overlay_uses_a_distinct_existing_target_ceiling(self):
        self.target.write_text("G4_CHILD_WRITE_QUALIFIED\n", encoding="utf-8")
        result = self.run_builder(handover=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["handover"])
        self.assertEqual(
            report["authorization_ceiling"],
            "exact_post_quiescence_handover",
        )
        overlay = json.loads(self.output.read_text(encoding="utf-8"))
        command = next(
            command["command"]
            for matcher in overlay["hooks"]["PreToolUse"]
            for command in matcher["hooks"]
            if "g4_qualification_probe_worker" in command.get("command", "")
        )
        self.assertIn("--child-handover-write-probe", command)
        self.assertNotIn(" --child-write-probe ", f" {command} ")

        rejected = self.run_builder(
            output=self.root / "handover-hold.json",
            writer_hold_seconds=2,
            handover=True,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertFalse((self.root / "handover-hold.json").exists())

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
