from pathlib import Path
import hashlib
import importlib.util
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_p7_deepseek_regression_prompt.py"
SPEC = importlib.util.spec_from_file_location("build_p7_deepseek_regression_prompt", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class P7DeepSeekRegressionPromptTests(unittest.TestCase):
    def make_root(self, directory: Path) -> Path:
        root = directory / "probe"
        (root / "fixtures").mkdir(parents=True)
        fixture = root / "fixtures" / "smoke-input.txt"
        fixture.write_text("one\ntwo\nresponses\n", encoding="utf-8")
        subprocess.run(
            ["git", "init", "-b", "main", str(root)],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(root), "add", "fixtures/smoke-input.txt"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=P7 Probe",
                "-c",
                "user.email=p7-probe@invalid",
                "commit",
                "-m",
                "fixture",
            ],
            check=True,
            stdout=subprocess.PIPE,
        )
        return root.resolve()

    def test_keeps_fresh_marker_out_of_parent_and_spawn_message(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_root(Path(temporary))
            marker = "0123456789abcdef0123456789abcdef"
            value = module.build_inputs(root, "p7_deepseek_readonly_1", marker)
            self.assertIn(f"marker={marker}", value["assignment"])
            self.assertNotIn(marker, value["parent_prompt"])
            self.assertIn("already loaded and followed", value["parent_prompt"])
            self.assertIn("Do not reload the skill", value["parent_prompt"])
            self.assertIn("agent_type=v4_flash_worker", value["parent_prompt"])
            self.assertIn("fork_turns=none", value["parent_prompt"])
            self.assertIn(
                "Execute the assignment supplied by the trusted one-shot SubagentStart Hook.",
                value["parent_prompt"],
            )
            self.assertNotIn("responses", value["parent_prompt"])
            self.assertNotIn(value["fixture_sha256"], value["parent_prompt"])

    def test_assignment_binds_clean_root_branch_head_and_expected_fixture_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_root(Path(temporary))
            value = module.build_inputs(
                root, "p7_deepseek_readonly_2", "f" * 32
            )
            expected = hashlib.sha256(
                (root / "fixtures" / "smoke-input.txt").read_bytes()
            ).hexdigest()
            self.assertEqual(value["fixture_sha256"], expected)
            self.assertIn(f"root={root}", value["assignment"])
            self.assertIn("branch=main", value["assignment"])
            self.assertIn(f"full_head={value['head']}", value["assignment"])
            self.assertIn("Do not edit, stage, commit, push", value["assignment"])
            self.assertIn("Call exec_command exactly once", value["assignment"])
            self.assertIn("SHA-256 of the entire fixture file", value["assignment"])
            self.assertNotIn("git_status_short=<", value["assignment"])

    def test_dirty_or_invalid_identity_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_root(Path(temporary))
            (root / "dirty.txt").write_text("dirty", encoding="utf-8")
            with self.assertRaisesRegex(module.PromptError, "must be clean"):
                module.build_inputs(root, "p7_deepseek_readonly_3", "a" * 32)
            with self.assertRaisesRegex(module.PromptError, "task name"):
                module.build_inputs(root, "Not_Canonical", "a" * 32)


if __name__ == "__main__":
    unittest.main()
