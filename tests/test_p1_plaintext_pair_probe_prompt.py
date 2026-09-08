import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_p1_plaintext_pair_probe_prompt.py"
SPEC = importlib.util.spec_from_file_location("pair_prompt", SCRIPT)
pair_prompt = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pair_prompt)


class P1PlaintextPairProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-p1-pair-clean-")
        self.clean_root = Path(self.temporary.name)
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(self.clean_root)], check=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.clean_root),
                "config",
                "user.email",
                "probe@example.invalid",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.clean_root), "config", "user.name", "Probe"],
            check=True,
        )
        (self.clean_root / "docs").mkdir()
        (self.clean_root / "docs" / "phase1-evidence.md").write_text(
            "fixture evidence\n", encoding="utf-8"
        )
        (self.clean_root / "tracked").write_text("base\n", encoding="utf-8")
        subprocess.run(
            [
                "git",
                "-C",
                str(self.clean_root),
                "add",
                "tracked",
                "docs/phase1-evidence.md",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.clean_root), "commit", "-qm", "base"], check=True
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_prompt_binds_clean_git_location_and_exact_pair_order(self):
        values = pair_prompt.build_values(self.clean_root, "p1_pair_test")
        prompt = values["prompt"]

        self.assertEqual(values["location"]["root"], str(self.clean_root.resolve()))
        self.assertEqual(values["child_path"], "/root/p1_pair_test")
        self.assertIn(f"full HEAD `{values['location']['head']}`", prompt)
        self.assertIn("agent_type=explorer", prompt)
        self.assertIn("fork_turns=none", prompt)
        self.assertIn("second call must be denied", prompt)
        self.assertIn("Do not make a third spawn call", prompt)
        self.assertIn("Do not send a third message", prompt)
        self.assertIn("Do not make a third follow-up", prompt)
        self.assertIn(values["messages"]["spawn_agent"], prompt)
        self.assertIn(values["messages"]["send_message"], prompt)
        self.assertIn(values["messages"]["followup_task"], prompt)
        self.assertNotIn(
            values["messages"]["send_message"], values["messages"]["spawn_agent"]
        )
        self.assertNotIn(
            values["messages"]["followup_task"],
            values["messages"]["spawn_agent"],
        )

    def test_redacted_manifest_has_only_hashes_and_lengths(self):
        values = pair_prompt.build_values(self.clean_root, "p1_pair_test")
        manifest = pair_prompt.redacted_manifest(values)

        self.assertFalse(manifest["raw_message_stored"])
        self.assertEqual(
            set(manifest["message_fingerprints"]), set(pair_prompt.OPERATIONS)
        )
        rendered = str(manifest)
        for operation, message in values["messages"].items():
            self.assertEqual(
                manifest["message_fingerprints"][operation],
                pair_prompt.fingerprint(message),
            )
            self.assertNotIn(message, rendered)

    def test_dirty_repository_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="codex-p1-pair-prompt-") as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "probe@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Probe"], check=True
            )
            (root / "tracked").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=True)
            (root / "tracked").write_text("dirty\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires a clean worktree", result.stderr)

    def test_invalid_task_name_fails_closed(self):
        with self.assertRaisesRegex(pair_prompt.ProbePromptError, "task name"):
            pair_prompt.build_values(self.clean_root, "Bad/Name")


if __name__ == "__main__":
    unittest.main()
