import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


watchdog_prompt = load_module(
    "build_g4_first_attestation_watchdog_probe_prompt",
    REPO / "probes" / "build_g4_first_attestation_watchdog_probe_prompt.py",
)


class G4FirstAttestationWatchdogProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.root = temporary_root / "repository"
        self.state = temporary_root / "state"
        self.root.mkdir()
        self.state.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "phase1-evidence.md").write_text(
            "fixture evidence\n", encoding="utf-8"
        )
        (self.root / "hooks").mkdir()
        (self.root / "hooks" / "authority_watchdog.py").write_text(
            "# fixture\n", encoding="utf-8"
        )
        self.git("add", "docs/phase1-evidence.md", "hooks/authority_watchdog.py")
        self.git("commit", "-m", "baseline")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def build(self, task_name="g4_first_attestation_timeout_test"):
        return watchdog_prompt.build_watchdog_prompt(
            self.root,
            self.state,
            task_name,
        )

    def declaration(self, prompt):
        matches = re.findall(
            r"BEGIN CODEX WORKER AUTHORITY\n(.+?)\nEND CODEX WORKER AUTHORITY",
            prompt,
            flags=re.DOTALL,
        )
        self.assertEqual(len(matches), 1)
        return json.loads(matches[0])

    def test_prompt_separates_watchdog_interrupt_and_quiescence_claims(self):
        prompt = self.build()
        spawn = prompt.index("g4_assignment.spawn_agent tool exactly once")
        delay = prompt.index("/bin/sleep 2")
        watchdog = prompt.index("authority_watchdog.py")
        interrupt = prompt.index("g4_assignment.interrupt_agent tool exactly once")
        listing = prompt.index("g4_assignment.list_agents tool exactly once")

        self.assertLess(spawn, delay)
        self.assertLess(delay, watchdog)
        self.assertLess(watchdog, interrupt)
        self.assertLess(interrupt, listing)
        self.assertIn("exit 2 with valid=true", prompt)
        self.assertIn("reason=pre_write_attestation_timeout", prompt)
        self.assertIn("classification=unresponsive_no_disk_change", prompt)
        self.assertIn("only an interrupt acknowledgement", prompt)
        self.assertIn("Do not infer strong termination", prompt)
        self.assertIn("Do not call collaboration.spawn_agent", prompt)
        self.assertIn("message wire is encrypted", prompt)
        self.assertNotIn("API_KEY", prompt)

    def test_child_capsule_is_one_short_lived_read_only_no_tool_authority(self):
        declaration = self.declaration(self.build())

        self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
        self.assertEqual(declaration["parent_recorded_user_write_intent"], "deny")
        self.assertEqual(declaration["owned_paths"], [])
        self.assertEqual(declaration["excluded_paths"], [])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(
            declaration["pre_write_attestation_timeout_seconds"],
            watchdog_prompt.PRE_WRITE_TIMEOUT_SECONDS,
        )
        self.assertEqual(declaration["ttl_seconds"], watchdog_prompt.AUTHORITY_TTL_SECONDS)
        self.assertIn("without calling tools", declaration["stop_condition"])
        self.assertEqual(
            declaration["verification"],
            ["parent observes pre-write-attestation timeout and interrupt acknowledgement"],
        )

    def test_prompt_requires_exact_task_path_and_assignment_selector(self):
        task_name = "g4_first_attestation_timeout_exact"
        prompt = self.build(task_name)

        self.assertIn(f"task_name={task_name}", prompt)
        self.assertIn(f"target=/root/{task_name}", prompt)
        self.assertIn("--assignment-id <the exact staged assignment_id>", prompt)
        self.assertIn("selection=exact", prompt)
        self.assertIn("Do not call any tool", prompt)
        self.assertIn("WAITING_FOR_PARENT_INTERRUPT", prompt)

    def test_noncanonical_inputs_and_dirty_root_fail_closed(self):
        with self.assertRaisesRegex(watchdog_prompt.ProbePromptError, "lowercase"):
            self.build("G4/invalid")
        with self.assertRaisesRegex(watchdog_prompt.ProbePromptError, "absolute"):
            watchdog_prompt.build_watchdog_prompt(
                self.root,
                Path("relative-state"),
                "g4_valid",
            )
        missing = Path(self.temporary_directory.name) / "missing-state"
        with self.assertRaises(FileNotFoundError):
            watchdog_prompt.build_watchdog_prompt(self.root, missing, "g4_valid")

        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(watchdog_prompt.ProbePromptError, "clean worktree"):
            self.build()


if __name__ == "__main__":
    unittest.main()
