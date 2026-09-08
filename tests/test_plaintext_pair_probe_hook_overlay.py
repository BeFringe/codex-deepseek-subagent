import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_plaintext_pair_probe_hook_overlay.py"
GUARD = ROOT / "hooks" / "plaintext_pair_probe_guard.py"
SPEC = importlib.util.spec_from_file_location("pair_overlay", SCRIPT)
overlay_builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(overlay_builder)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PlaintextPairProbeHookOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="codex-p1-pair-overlay-", dir="/private/tmp"
        )
        self.root = Path(self.temporary.name)
        self.input = self.root / "hooks.json"
        self.output = self.root / "overlay.json"
        self.state = self.root / "pair-state"
        self.config = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": (
                                    "/usr/bin/python3 /existing/compatibility_hook.py "
                                    "--state-directory /existing/state"
                                ),
                                "timeout": 15,
                            }
                        ],
                    }
                ],
                "PostToolUse": [{"matcher": "*", "hooks": []}],
                "SubagentStart": [{"matcher": "*", "hooks": []}],
                "PreCompact": [{"matcher": "*", "hooks": []}],
                "SubagentStop": [{"matcher": "*", "hooks": []}],
            }
        }
        self.input.write_text(json.dumps(self.config), encoding="utf-8")
        self.specs = {
            "spawn_agent": "a" * 64,
            "send_message": "b" * 64,
            "followup_task": "c" * 64,
        }

    def tearDown(self):
        self.temporary.cleanup()

    def arguments(self):
        values = [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(self.input),
            "--output",
            str(self.output),
            "--expected-input-sha256",
            overlay_builder.file_sha256(self.input),
            "--guard-script",
            str(GUARD),
            "--state-directory",
            str(self.state),
        ]
        for operation in overlay_builder.OPERATIONS:
            values.extend(
                ["--message-sha256", f"{operation}={self.specs[operation]}"]
            )
        return values

    def test_overlay_adds_only_one_pretool_guard_and_preserves_existing_hooks(self):
        result = subprocess.run(
            self.arguments(), capture_output=True, text=True, check=False
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        value = json.loads(self.output.read_text(encoding="utf-8"))
        before = self.config["hooks"]["PreToolUse"][0]["hooks"]
        after = value["hooks"]["PreToolUse"][0]["hooks"]
        self.assertEqual(after[:-1], before)
        self.assertEqual(len(after), len(before) + 1)
        command = after[-1]["command"]
        self.assertIn(str(GUARD), command)
        self.assertIn(str(self.state), command)
        for operation, expected in self.specs.items():
            self.assertIn(f"{operation}={expected}", command)
        for event in ("PostToolUse", "SubagentStart", "PreCompact", "SubagentStop"):
            self.assertEqual(value["hooks"][event], self.config["hooks"][event])
        self.assertEqual(report["changed_events"], ["PreToolUse"])
        self.assertTrue(report["existing_hooks_preserved"])
        self.assertTrue(report["v4_entries_preserved"])
        self.assertTrue(report["g4_authority_hook_preserved"])
        self.assertFalse(report["grants_mutation_authority"])

    def test_input_hash_drift_fails_closed_without_output(self):
        arguments = self.arguments()
        hash_index = arguments.index("--expected-input-sha256") + 1
        arguments[hash_index] = "d" * 64

        result = subprocess.run(arguments, capture_output=True, text=True, check=False)

        self.assertEqual(result.returncode, 2)
        self.assertIn("input Hooks hash drifted", result.stderr)
        self.assertFalse(self.output.exists())

    def test_duplicate_or_incomplete_specs_fail_closed(self):
        with self.assertRaisesRegex(overlay_builder.OverlayError, "one exact"):
            overlay_builder.validate_specs([("spawn_agent", "a" * 64)])
        with self.assertRaisesRegex(overlay_builder.OverlayError, "one exact"):
            overlay_builder.validate_specs(
                [
                    ("spawn_agent", "a" * 64),
                    ("spawn_agent", "b" * 64),
                    ("send_message", "c" * 64),
                    ("followup_task", "d" * 64),
                ]
            )

    def test_nonempty_state_directory_fails_closed(self):
        self.state.mkdir()
        (self.state / "foreign").write_text("foreign", encoding="utf-8")

        result = subprocess.run(
            self.arguments(), capture_output=True, text=True, check=False
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("absent or empty", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
