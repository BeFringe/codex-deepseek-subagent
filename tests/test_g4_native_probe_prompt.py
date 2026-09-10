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
        self.assertIn(
            '"assigned_slice_complete","inventory_summaries"]',
            prompt,
        )
        self.assertIn(
            '["policy_sha256","worker_claimed_origin",'
            '"test_only_injection_used","derivation_receipt_sha256"]',
            prompt,
        )
        self.assertIn(
            "Keep inventory_summaries, context_lost, authority_violation, and "
            "assigned_slice_complete only at the top level",
            prompt,
        )
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

        sibling_controlled = probe_prompt.build_prompt(
            self.root,
            "g4_root_2b",
            sibling_admission_control=True,
        )
        self.assertIn("agent_type=worker", sibling_controlled)
        self.assertIn("task_name=ordinary_sibling_denied", sibling_controlled)
        self.assertIn(
            "Qualification parent may spawn only the exact "
            "g4_qualification_probe_worker role",
            sibling_controlled,
        )
        self.assertIn("no child ThreadId or AgentPath", sibling_controlled)
        self.assertIn("call native list_agents exactly once", sibling_controlled)
        self.assertIn("task_name=g4_root_2b", sibling_controlled)

        exact_empty_close = probe_prompt.build_prompt(
            self.root,
            "g4_empty_args_close_1",
            exact_list_agents_empty_arguments=True,
            close_after_callback=True,
        )
        self.assertIn(
            "Call native list_agents exactly once with arguments exactly `{}`",
            exact_empty_close,
        )
        self.assertIn("do not supply path_prefix", exact_empty_close)
        self.assertIn(
            "one read-only list_agents call with exact empty arguments and no mutation",
            exact_empty_close,
        )
        self.assertIn(
            "Treat either a successful child return or an errored child return as the final callback",
            exact_empty_close,
        )
        self.assertIn(
            "call native close_agent exactly once with target=/root/g4_empty_args_close_1",
            exact_empty_close,
        )

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

        nested = probe_prompt.build_prompt(
            self.root,
            "g4_nested_child_1",
            parent_agent_path="/root/g4_nested_parent_1",
        )
        self.assertIn(
            "/root/g4_nested_parent_1/g4_nested_child_1",
            nested,
        )

    def test_dirty_worktree_and_noncanonical_task_name_fail_closed(self):
        with self.assertRaisesRegex(
            probe_prompt.ProbePromptError,
            "exact empty list_agents arguments require the list_agents child tool",
        ):
            probe_prompt.build_prompt(
                self.root,
                "g4_invalid_empty_args_1",
                child_tool="list_mcp_resources",
                exact_list_agents_empty_arguments=True,
            )

        (self.root / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(
            probe_prompt.ProbePromptError, "clean worktree"
        ):
            probe_prompt.build_prompt(self.root, "g4_root_1")
        with self.assertRaisesRegex(
            probe_prompt.ProbePromptError, "task name"
        ):
            probe_prompt.build_prompt(self.root, "G4/root")
        with self.assertRaisesRegex(
            probe_prompt.ProbePromptError, "parent AgentPath"
        ):
            probe_prompt.build_prompt(
                self.root,
                "g4_root_2",
                parent_agent_path="/root//not-canonical",
            )

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

            shell_prompt = probe_prompt.build_prompt(
                self.root,
                "g4_child_deny_shell_1",
                child_tool="code_mode_exec_command_negative",
                negative_mutation_path=target,
            )
            shell_declaration = json.loads(
                shell_prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                    "\nEND CODEX WORKER AUTHORITY", 1
                )[0]
            )
            self.assertIn("one nested tools.exec_command call", shell_prompt)
            self.assertIn(f"cmd `/usr/bin/touch {target}`", shell_prompt)
            self.assertIn("no shell composition", shell_prompt)
            self.assertIn(
                "code-mode nested exec_command read-only denial probe",
                shell_declaration["verification"],
            )
            self.assertEqual(shell_declaration["assignment_mutation_mode"], "read_only")
            self.assertEqual(shell_declaration["owned_paths"], [])
            self.assertFalse(any(shell_declaration["git_authority"].values()))

            sandbox_prompt = probe_prompt.build_prompt(
                self.root,
                "g4_child_sandbox_1",
                child_tool="code_mode_bash_sandbox_negative",
                negative_mutation_path=target,
            )
            sandbox_declaration = json.loads(
                sandbox_prompt.split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                    "\nEND CODEX WORKER AUTHORITY", 1
                )[0]
            )
            self.assertIn("exact qualification Hook grant", sandbox_prompt)
            self.assertIn("runtime read-only sandbox", sandbox_prompt)
            self.assertEqual(
                sandbox_declaration["verification"],
                ["code-mode nested Bash read-only sandbox denial probe"],
            )
            self.assertEqual(sandbox_declaration["assignment_mutation_mode"], "read_only")
            self.assertEqual(sandbox_declaration["parent_recorded_user_write_intent"], "deny")
            self.assertEqual(sandbox_declaration["owned_paths"], [])
            self.assertFalse(any(sandbox_declaration["git_authority"].values()))

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
                probe_prompt.ProbePromptError, "target must be absent"
            ):
                probe_prompt.build_prompt(
                    self.root,
                    "g4_child_deny_shell_2",
                    child_tool="code_mode_exec_command_negative",
                    negative_mutation_path=target,
                )
            with self.assertRaisesRegex(
                probe_prompt.ProbePromptError, "target must be absent"
            ):
                probe_prompt.build_prompt(
                    self.root,
                    "g4_child_sandbox_2",
                    child_tool="code_mode_bash_sandbox_negative",
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
