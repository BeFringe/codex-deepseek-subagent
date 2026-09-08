from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


message_probe = load_module(
    "build_p1_plaintext_message_probe_prompt",
    ROOT / "probes" / "build_p1_plaintext_message_probe_prompt.py",
)


class P1PlaintextMessageProbePromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "repository"
        self.root.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "phase1-evidence.md").write_text(
            "fixture evidence\n", encoding="utf-8"
        )
        (self.root / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        self.git("add", "baseline.txt", "docs/phase1-evidence.md")
        self.git("commit", "-m", "baseline")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def test_prompt_keeps_payload_preimages_out_of_initial_child_assignment(self) -> None:
        head = self.git("rev-parse", "HEAD").stdout.strip()
        task_name = "p1_plaintext_message_test"
        child_path = f"/root/{task_name}"
        send_payload = f"P1-PLAINTEXT-SEND-V1-{head}"
        followup_payload = f"P1-PLAINTEXT-FOLLOWUP-V1-{head}"
        prompt = message_probe.build_prompt(self.root, task_name)
        child_assignment = prompt.split("CHILD ASSIGNMENT:\n\n", 1)[1]

        self.assertIn(f"agent_type=explorer", prompt)
        self.assertIn(f"task_name={task_name}", prompt)
        self.assertIn("fork_turns=none", prompt)
        self.assertEqual(prompt.count(send_payload), 1)
        self.assertEqual(prompt.count(followup_payload), 1)
        self.assertNotIn(send_payload, child_assignment)
        self.assertNotIn(followup_payload, child_assignment)
        self.assertIn(f"P1.PLAINTEXT.READY path={child_path}", child_assignment)
        self.assertIn(f"P1.PLAINTEXT.CALLBACK path={child_path}", child_assignment)
        self.assertIn("native send_message once", prompt)
        self.assertIn("native followup_task once", prompt)
        self.assertIn("queue-only", prompt)
        self.assertIn("rollout item types and exact new user-message bytes", prompt)
        self.assertNotIn("API_KEY", prompt)

    def test_dirty_root_and_noncanonical_task_name_fail_closed(self) -> None:
        with self.assertRaisesRegex(message_probe.ProbePromptError, "task name"):
            message_probe.build_prompt(self.root, "bad/name")

        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(message_probe.ProbePromptError, "clean worktree"):
            message_probe.build_prompt(self.root, "p1_plaintext_message_test")


if __name__ == "__main__":
    unittest.main()
