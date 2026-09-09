import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "build_g4_write_probe_prompt.py"


class G4WriteProbePromptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(
            prefix="codex-g4-write-prompt-", dir="/private/tmp"
        )
        self.root = Path(self.directory.name).resolve()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "phase1-evidence.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Fixture"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "docs/phase1-evidence.md"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "baseline"], check=True, capture_output=True)
        self.target = self.root / "qualified.txt"
        self.output = Path(self.directory.name + ".prompt")

    def tearDown(self):
        if self.output.exists():
            self.output.unlink()
        self.directory.cleanup()

    def run_builder(
        self,
        *,
        parent_conflict_probe=False,
        p5b_close_after_write=False,
        p5b_handover_after_barrier=False,
    ):
        command = [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(self.root),
            "--task-name",
            "qualified_write",
            "--target",
            str(self.target),
            "--output",
            str(self.output),
        ]
        if parent_conflict_probe:
            command.append("--parent-conflict-probe")
        if p5b_close_after_write:
            command.append("--p5b-close-after-write")
        if p5b_handover_after_barrier:
            command.append("--p5b-handover-after-barrier")
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_prompt_binds_exact_write_authority_and_trusted_final_observation(self):
        result = self.run_builder()
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self.output.read_text(encoding="utf-8")
        declaration = json.loads(
            prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        self.assertEqual(declaration["assignment_mutation_mode"], "write")
        self.assertEqual(declaration["parent_recorded_user_write_intent"], "allow")
        self.assertEqual(declaration["owned_paths"], ["qualified.txt"])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(declaration["verification"], ["exact-path child apply_patch qualification probe"])
        self.assertIn("one exact owned-path apply_patch", declaration["stop_condition"])
        self.assertIn(str(self.target), prompt)
        self.assertIn(
            "hash-bound trusted PostToolUse observation for final Git snapshot",
            declaration["execution_contract"]["required_invariants"],
        )
        self.assertIn("BEGIN/END CODEX POST-MUTATION OBSERVATION", prompt)
        self.assertIn("derivation_receipt_sha256", prompt)
        self.assertIn("The seed is a construction aid, not the final schema", prompt)
        self.assertIn("Never emit schema", prompt)
        self.assertIn("return exactly TASK.CONTEXT_LOST", prompt)

    def test_parent_conflict_prompt_waits_for_claim_then_attempts_one_denied_patch(self):
        result = self.run_builder(parent_conflict_probe=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self.output.read_text(encoding="utf-8")
        self.assertIn("native wait_agent exactly once with timeout_ms=10000", prompt)
        self.assertNotIn("wait_for_exact_writer_claim.py", prompt)
        self.assertNotIn("--state-directory", prompt)
        self.assertIn("G4_PARENT_CONFLICT_MUST_NOT_WRITE", prompt)
        self.assertIn("must be denied before execution with TASK.WRITER_LEASE_BLOCKED", prompt)
        self.assertIn("G4_CHILD_WRITE_QUALIFIED", prompt)
        self.assertIn("Then use only native wait/callback", prompt)

    def test_p5b_prompt_completes_write_then_reopens_only_for_exact_close(self):
        result = self.run_builder(p5b_close_after_write=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self.output.read_text(encoding="utf-8")
        self.assertIn("native wait_agent exactly once with timeout_ms=60000", prompt)
        self.assertIn("native followup_task exactly once", prompt)
        self.assertIn(
            "P5B.WRITE.CLOSE.HOLD: make no tool call and no final; remain active for exact host close",
            prompt,
        )
        self.assertIn("reported assignment grants no mutation authority", prompt)
        self.assertIn("four exact process-id maps", prompt)
        self.assertIn("tracked_process_termination_confirmed=true", prompt)
        self.assertIn("closed_catalog_actor_quiescence_claimed=true", prompt)
        self.assertIn("process_tree_quiescence_claimed=false", prompt)
        self.assertLess(prompt.index("wait_agent exactly once"), prompt.index("followup_task exactly once"))
        self.assertLess(prompt.index("followup_task exactly once"), prompt.index("close_agent exactly once"))

    def test_p5b_handover_prompt_binds_replacement_and_second_close(self):
        self.target.write_text("G4_CHILD_WRITE_QUALIFIED\n", encoding="utf-8")
        result = self.run_builder(p5b_handover_after_barrier=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self.output.read_text(encoding="utf-8")
        declaration = json.loads(
            prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        self.assertEqual(
            declaration["verification"],
            ["exact-path post-quiescence child handover qualification probe"],
        )
        self.assertIn(
            "exact prior quiescence barrier handover",
            declaration["execution_contract"]["required_invariants"],
        )
        self.assertIn("replace the exact frozen prior", declaration["stop_condition"])
        self.assertEqual(
            declaration["execution_contract"]["capsule_feasibility_attestation"]
            ["bounded_completion"]["proposed_mechanism"],
            "exact Hook handover ceiling plus writer lease",
        )
        self.assertIn("*** Update File:", prompt)
        self.assertIn("-G4_CHILD_WRITE_QUALIFIED", prompt)
        self.assertIn("+G4_HANDOVER_WRITE_QUALIFIED", prompt)
        self.assertNotIn("*** Add File:", prompt)
        self.assertIn("same-path replacement-and-close", prompt)
        self.assertIn("exactly one identical ownership_handover", prompt)
        self.assertIn("native close_agent exactly once", prompt)

    def test_write_modes_are_mutually_exclusive(self):
        result = self.run_builder(
            parent_conflict_probe=True,
            p5b_close_after_write=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

        result = self.run_builder(
            p5b_close_after_write=True,
            p5b_handover_after_barrier=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_handover_requires_exact_prior_frontier(self):
        self.target.write_text("wrong prior bytes\n", encoding="utf-8")
        result = self.run_builder(p5b_handover_after_barrier=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_existing_output_fails_closed(self):
        self.output.write_text("occupied\n", encoding="utf-8")
        result = self.run_builder()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "occupied\n")

    def test_dirty_root_fails_before_prompt_publication(self):
        (self.root / "foreign.txt").write_text("dirty\n", encoding="utf-8")
        result = self.run_builder()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
