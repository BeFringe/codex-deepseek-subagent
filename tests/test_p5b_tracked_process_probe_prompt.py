import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "probes" / "build_p5b_tracked_process_probe_prompt.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prompt_builder = load_module("p5b_tracked_process_prompt", SCRIPT)


class P5bTrackedProcessProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="codex-g4-p5b-tracked-process.", dir=(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp")
        )
        self.root = Path(self.temporary.name).resolve()
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git", "-C", str(self.root), "-c", "user.name=Phase1 Probe",
                "-c", "user.email=phase1-probe@invalid", "commit", "--allow-empty",
                "-m", "initial",
            ],
            check=True,
            capture_output=True,
        )
        self.head = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.marker = "codex-g4-p5b-tracked-0123456789abcdef"

    def tearDown(self):
        self.temporary.cleanup()

    def test_prompt_binds_one_nonwriting_process_and_exact_close_receipt(self):
        prompt = prompt_builder.build_prompt(
            self.root,
            "p5b_tracked_process_1",
            self.marker,
        )

        self.assertIn(f"full HEAD {self.head}", prompt)
        self.assertIn("agent_type=worker", prompt)
        self.assertIn("/root/p5b_tracked_process_1", prompt)
        self.assertIn(
            "python3 -c 'import time; time.sleep(120)' " + self.marker,
            prompt,
        )
        self.assertIn("exactly one nested tools.exec_command call", prompt)
        self.assertIn("exactly one nested tools.write_stdin call", prompt)
        self.assertIn("yield_time_ms=60000", prompt)
        self.assertNotIn("yield_time_ms=300000", prompt)
        self.assertEqual(prompt.count("Call functions.exec exactly once."), 1)
        self.assertEqual(prompt.count("call functions.exec exactly once more"), 1)
        self.assertIn("wait_agent exactly once", prompt)
        self.assertIn("has no target argument", prompt)
        self.assertNotIn("wait_agent exactly once with target=", prompt)
        self.assertIn("native parent projection may omit the child ThreadId", prompt)
        self.assertIn("fresh owner will later join it to the real child SessionMeta", prompt)
        self.assertIn(
            "do not infer the standard worker child's eventual code-mode catalog",
            prompt,
        )
        self.assertIn("wrapper enables code-mode hosting only", prompt)
        self.assertIn("tracked_process_ids_by_thread", prompt)
        self.assertIn("confirmed_exit_process_ids_by_thread", prompt)
        self.assertIn("model_callable_process_bootstrap_absent=false", prompt)
        self.assertIn("process_tree_quiescence_claimed=false", prompt)
        self.assertNotIn("apply_patch", prompt)
        self.assertNotIn("agent_type=g4_qualification_probe_worker", prompt)

    def test_dirty_root_bad_identity_and_existing_output_fail_closed(self):
        with self.assertRaisesRegex(
            prompt_builder.ProbePromptError, "exact bounded form"
        ):
            prompt_builder.build_prompt(
                self.root,
                "p5b_tracked_process_1",
                "unbounded marker",
            )

        with self.assertRaisesRegex(
            prompt_builder.ProbePromptError, "lowercase letters"
        ):
            prompt_builder.build_prompt(self.root, "Wrong-Task", self.marker)

        dirty = self.root / "unexpected.txt"
        dirty.write_text("unexpected\n", encoding="utf-8")
        with self.assertRaisesRegex(prompt_builder.ProbePromptError, "clean worktree"):
            prompt_builder.build_prompt(
                self.root,
                "p5b_tracked_process_1",
                self.marker,
            )
        dirty.unlink()

        output = self.root.parent / f"{self.root.name}-prompt.txt"
        output.write_text("occupied\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--process-marker",
                self.marker,
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        try:
            self.assertEqual(result.returncode, 2)
            self.assertIn("was not written", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "occupied\n")
        finally:
            output.unlink()


if __name__ == "__main__":
    unittest.main()
