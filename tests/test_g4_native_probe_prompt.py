import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


probe_prompt = load_module(
    "build_g4_native_probe_prompt",
    REPO / "probes" / "build_g4_native_probe_prompt.py",
)


class G4NativeProbePromptTests(unittest.TestCase):
    def setUp(self):
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
        self.git("add", "docs/phase1-evidence.md")
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

    def test_prompt_binds_clean_full_head_and_non_mutating_authority(self):
        head = self.git("rev-parse", "HEAD").stdout.strip()
        prompt = probe_prompt.build_prompt(self.root, "g4_root_1")
        declaration_text = prompt.split(
            "BEGIN CODEX WORKER AUTHORITY\n", 1
        )[1].split("\nEND CODEX WORKER AUTHORITY", 1)[0]
        declaration = json.loads(declaration_text)

        self.assertIn("agent_type=g4_qualification_probe_worker", prompt)
        self.assertIn("task_name=g4_root_1", prompt)
        self.assertIn("/root/g4_root_1", prompt)
        self.assertIn("final attestation JSON is not the seed object", prompt)
        self.assertIn("do not copy the seed's schema", prompt)
        self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
        self.assertEqual(declaration["parent_recorded_user_write_intent"], "deny")
        self.assertEqual(declaration["owned_paths"], [])
        self.assertFalse(any(declaration["git_authority"].values()))
        self.assertEqual(
            declaration["execution_contract"]["review_range"],
            {"base_oid": head, "head_oid": head},
        )
        self.assertEqual(
            declaration["location_preflight"],
            {
                "expected_root": str(self.root.resolve()),
                "expected_branch": "main",
                "expected_base_head": head,
            },
        )
        self.assertNotIn("API_KEY", prompt)
        self.assertNotIn("read-only positive control", prompt)

        controlled = probe_prompt.build_prompt(
            self.root,
            "g4_root_2",
            pretool_schema_control=True,
        )
        self.assertIn("call exec_command exactly once", controlled)
        self.assertIn("cmd `/bin/pwd`", controlled)
        self.assertIn(str(self.root.resolve()), controlled)
        self.assertIn("task_name=g4_root_2", controlled)

        lifecycle = probe_prompt.build_prompt(
            self.root,
            "g4_root_3",
            child_tool="list_mcp_resources",
        )
        lifecycle_declaration = json.loads(
            lifecycle.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        self.assertIn("Call native list_mcp_resources exactly once", lifecycle)
        self.assertEqual(
            lifecycle_declaration["verification"],
            ["native list_mcp_resources read-only lifecycle probe"],
        )
        self.assertNotIn("Call native list_agents exactly once", lifecycle)

    def test_dirty_worktree_and_noncanonical_task_name_fail_closed(self):
        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(
            probe_prompt.ProbePromptError, "clean worktree"
        ):
            probe_prompt.build_prompt(self.root, "g4_root_1")
        with self.assertRaisesRegex(
            probe_prompt.ProbePromptError, "task name"
        ):
            probe_prompt.build_prompt(self.root, "G4/root")

    def test_negative_mutation_prompt_is_read_only_and_requires_absent_target(self):
        target = Path(self.temporary_directory.name) / "child-deny.txt"
        with mock.patch.object(
            probe_prompt, "NON_GIT_PROBE_ROOT", target.parent
        ):
            prompt = probe_prompt.build_prompt(
                self.root,
                "g4_child_deny_1",
                child_tool="apply_patch_negative",
                negative_mutation_path=target,
            )
            declaration = json.loads(
                prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                    "\nEND CODEX WORKER AUTHORITY", 1
                )[0]
            )
            self.assertIn(f"create {target}", prompt)
            self.assertIn("denied before execution", prompt)
            self.assertIn("Do not retry or call another tool", prompt)
            self.assertEqual(declaration["assignment_mutation_mode"], "read_only")
            self.assertEqual(declaration["parent_recorded_user_write_intent"], "deny")
            self.assertEqual(declaration["owned_paths"], [])
            self.assertFalse(any(declaration["git_authority"].values()))

            code_mode_prompt = probe_prompt.build_prompt(
                self.root,
                "g4_child_deny_code_1",
                child_tool="code_mode_apply_patch_negative",
                negative_mutation_path=target,
            )
            code_mode_declaration = json.loads(
                code_mode_prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                    "\nEND CODEX WORKER AUTHORITY", 1
                )[0]
            )
            self.assertIn("Call functions.exec exactly once", code_mode_prompt)
            self.assertIn("one nested tools.apply_patch call", code_mode_prompt)
            self.assertIn(
                "code-mode nested apply_patch read-only denial probe",
                code_mode_declaration["verification"],
            )
            self.assertEqual(
                code_mode_declaration["assignment_mutation_mode"], "read_only"
            )
            self.assertEqual(code_mode_declaration["owned_paths"], [])
            self.assertFalse(any(code_mode_declaration["git_authority"].values()))

            target.write_text("unexpected preexisting byte\n", encoding="utf-8")
            with self.assertRaisesRegex(
                probe_prompt.ProbePromptError, "target must be absent"
            ):
                probe_prompt.build_prompt(
                    self.root,
                    "g4_child_deny_2",
                    child_tool="apply_patch_negative",
                    negative_mutation_path=target,
                )
            with self.assertRaisesRegex(
                probe_prompt.ProbePromptError, "target must be absent"
            ):
                probe_prompt.build_prompt(
                    self.root,
                    "g4_child_deny_code_2",
                    child_tool="code_mode_apply_patch_negative",
                    negative_mutation_path=target,
                )

            with self.assertRaisesRegex(
                probe_prompt.ProbePromptError, "absolute path"
            ):
                probe_prompt.build_prompt(
                    self.root,
                    "g4_child_deny_3",
                    child_tool="apply_patch_negative",
                    negative_mutation_path=Path("relative.txt"),
                )


if __name__ == "__main__":
    unittest.main()
