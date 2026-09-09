from pathlib import Path
import hashlib
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"


class PlaintextCandidateWrapperTests(unittest.TestCase):
    def _fake_candidate(self, directory):
        candidate = directory / "candidate"
        candidate.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$@\" > \"$ARG_LOG\"\n"
            "if [ -n \"${ENV_LOG-}\" ]; then\n"
            "  printf '%s\\n' \"${CODEX_G4_TOOL_CATALOG_RECEIPT-}\" > \"$ENV_LOG\"\n"
            "fi\n",
            encoding="utf-8",
        )
        candidate.chmod(0o700)
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        return candidate, digest

    def _environment(self, candidate, digest, arg_log):
        return {
            **os.environ,
            "ARG_LOG": str(arg_log),
            "CODEX_G4_LIVE_SELECTION_AUTHORIZED": "schema2-paired-probe",
            "CODEX_G4_CANDIDATE_BIN": str(candidate),
            "CODEX_G4_CANDIDATE_SHA256": digest,
        }

    def test_wrapper_injects_isolated_plaintext_probe_posture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            arg_log = directory / "args.txt"
            result = subprocess.run(
                [
                    str(WRAPPER),
                    "exec",
                    "--ephemeral",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--json",
                    "Return READY.",
                ],
                env=self._environment(candidate, digest, arg_log),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                arg_log.read_text(encoding="utf-8").splitlines(),
                [
                    "-c",
                    "features.multi_agent_v2.enabled=true",
                    "-c",
                    'features.multi_agent_v2.message_delivery="plaintext"',
                    "-c",
                    'features.multi_agent_v2.tool_namespace="g4_assignment"',
                    "-c",
                    "features.code_mode_host=false",
                    "-a",
                    "never",
                    "-s",
                    "read-only",
                    "exec",
                    "--ephemeral",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--json",
                    "Return READY.",
                ],
            )

    def test_gui_and_server_entry_points_fail_before_candidate_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            for entry_point in ("app-server", "app", "remote-control", "mcp-server"):
                with self.subTest(entry_point=entry_point):
                    arg_log = directory / f"{entry_point}.txt"
                    result = subprocess.run(
                        [str(WRAPPER), entry_point],
                        env=self._environment(candidate, digest, arg_log),
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 78)
                    self.assertIn("entry points are forbidden", result.stderr)
                    self.assertFalse(arg_log.exists())

    def test_exec_requires_all_isolation_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            complete = ["--ephemeral", "--ignore-user-config", "--ignore-rules"]
            for missing in complete:
                with self.subTest(missing=missing):
                    arg_log = directory / f"missing-{missing[2:]}.txt"
                    arguments = ["exec", *(flag for flag in complete if flag != missing)]
                    result = subprocess.run(
                        [str(WRAPPER), *arguments],
                        env=self._environment(candidate, digest, arg_log),
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 78)
                    self.assertFalse(arg_log.exists())

    def test_stateful_sessionmeta_probe_requires_separate_guard_and_exact_clean_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            root = directory / "worktree"
            root.mkdir()
            root = root.resolve()
            subprocess.run(["git", "init", "-b", "main", str(root)], check=True, stdout=subprocess.PIPE)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Phase1 Probe",
                    "-c",
                    "user.email=phase1-probe@invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "initial",
                ],
                check=True,
                stdout=subprocess.PIPE,
            )
            arg_log = directory / "stateful-args.txt"
            environment = self._environment(candidate, digest, arg_log)
            env_log = directory / "parent-conflict-env.txt"
            environment.update(
                {
                    "ENV_LOG": str(env_log),
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                }
            )

            accepted = subprocess.run(
                [
                    str(WRAPPER),
                    "exec",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--dangerously-bypass-hook-trust",
                    "--json",
                    "-C",
                    str(root),
                    "Return READY.",
                ],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertTrue(arg_log.exists())

            denied_log = directory / "unguarded-args.txt"
            denied_environment = self._environment(candidate, digest, denied_log)
            denied = subprocess.run(
                [
                    str(WRAPPER),
                    "exec",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--dangerously-bypass-hook-trust",
                    "--json",
                    "-C",
                    str(root),
                ],
                env=denied_environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(denied.returncode, 78)
            self.assertFalse(denied_log.exists())

    def test_exact_temporary_write_guard_selects_workspace_write_only_for_that_root(self):
        with tempfile.TemporaryDirectory() as candidate_dir, tempfile.TemporaryDirectory(
            prefix="codex-g4-write-wrapper-", dir="/private/tmp"
        ) as root_dir:
            directory = Path(candidate_dir)
            root = Path(root_dir).resolve()
            candidate, digest = self._fake_candidate(directory)
            subprocess.run(["git", "-C", str(root), "init", "-b", "main"], check=True, capture_output=True)
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Phase1 Probe",
                    "-c", "user.email=phase1-probe@invalid", "commit", "--allow-empty", "-m", "initial",
                ],
                check=True,
                capture_output=True,
            )
            arg_log = directory / "write-args.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.update(
                {
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                    "CODEX_G4_EXACT_WRITE_PROBE_AUTHORIZED": "schema1-exact-temporary-git-root",
                }
            )
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ignore-user-config", "--ignore-rules",
                    "--dangerously-bypass-hook-trust", "--json", "-C", str(root), "Return READY.",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = arg_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(arguments[arguments.index("-s") + 1], "workspace-write")

    def test_failed_patch_callback_guard_narrowly_enables_code_mode_host(self):
        with tempfile.TemporaryDirectory() as candidate_dir, tempfile.TemporaryDirectory(
            prefix="codex-g4-write-posttool-", dir="/private/tmp"
        ) as root_dir:
            directory = Path(candidate_dir)
            root = Path(root_dir).resolve()
            candidate, digest = self._fake_candidate(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "-b", "main"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Phase1 Probe",
                    "-c", "user.email=phase1-probe@invalid", "commit", "--allow-empty",
                    "-m", "initial",
                ],
                check=True,
                capture_output=True,
            )
            arg_log = directory / "failed-patch-args.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.update(
                {
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                    "CODEX_G4_EXACT_WRITE_PROBE_AUTHORIZED": "schema1-exact-temporary-git-root",
                    "CODEX_G4_FAILED_PATCH_CALLBACK_PROBE_AUTHORIZED": (
                        "schema1-root-failed-apply-patch"
                    ),
                }
            )
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ignore-user-config", "--ignore-rules",
                    "--dangerously-bypass-hook-trust", "--json", "-C", str(root),
                    "Return READY.",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = arg_log.read_text(encoding="utf-8").splitlines()
            self.assertIn("features.code_mode_host=true", arguments)
            self.assertEqual(arguments[arguments.index("-s") + 1], "workspace-write")
    def test_parent_child_conflict_guard_is_exact_and_enables_parent_patch_host(self):
        with tempfile.TemporaryDirectory() as candidate_dir, tempfile.TemporaryDirectory(
            prefix="codex-g4-write-parent-conflict.", dir="/private/tmp"
        ) as root_dir:
            directory = Path(candidate_dir)
            root = Path(root_dir).resolve()
            candidate, digest = self._fake_candidate(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "-b", "main"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Phase1 Probe",
                    "-c", "user.email=phase1-probe@invalid", "commit", "--allow-empty",
                    "-m", "initial",
                ],
                check=True,
                capture_output=True,
            )
            arg_log = directory / "parent-conflict-args.txt"
            env_log = directory / "parent-conflict-env.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.update(
                {
                    "ENV_LOG": str(env_log),
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                    "CODEX_G4_EXACT_WRITE_PROBE_AUTHORIZED": (
                        "schema1-exact-temporary-git-root"
                    ),
                    "CODEX_G4_PARENT_CHILD_WRITER_CONFLICT_PROBE_AUTHORIZED": (
                        "schema1-exact-active-child-claim"
                    ),
                }
            )
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ignore-user-config", "--ignore-rules",
                    "--dangerously-bypass-hook-trust", "--json", "-C", str(root),
                    "Return READY.",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = arg_log.read_text(encoding="utf-8").splitlines()
            self.assertIn("features.code_mode_host=true", arguments)
            self.assertEqual(arguments[arguments.index("-s") + 1], "workspace-write")
            self.assertEqual(
                env_log.read_text(encoding="utf-8").strip(),
                "stderr-v2-parent-child-closed",
            )

            denied_log = directory / "missing-exact-write-args.txt"
            denied_environment = self._environment(candidate, digest, denied_log)
            denied_environment.update(
                {
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                    "CODEX_G4_PARENT_CHILD_WRITER_CONFLICT_PROBE_AUTHORIZED": (
                        "schema1-exact-active-child-claim"
                    ),
                }
            )
            denied = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ignore-user-config", "--ignore-rules",
                    "--dangerously-bypass-hook-trust", "--json", "-C", str(root),
                    "Return READY.",
                ],
                env=denied_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(denied.returncode, 78)
            self.assertIn("requires the exact write guard", denied.stderr)
            self.assertFalse(denied_log.exists())

    def test_unrelated_probe_cannot_inherit_parent_catalog_closure_opt_in(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            arg_log = directory / "args.txt"
            env_log = directory / "env.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.update(
                {
                    "ENV_LOG": str(env_log),
                    "CODEX_G4_TOOL_CATALOG_RECEIPT": (
                        "stderr-v2-parent-child-closed"
                    ),
                }
            )
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ephemeral", "--ignore-user-config",
                    "--ignore-rules", "--json", "Return READY.",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(env_log.read_text(encoding="utf-8"), "\n")

    def test_p5b_termination_guard_closes_catalog_without_widening_sandbox(self):
        with tempfile.TemporaryDirectory() as candidate_dir, tempfile.TemporaryDirectory(
            prefix="codex-g4-p5b-termination.", dir="/private/tmp"
        ) as root_dir:
            directory = Path(candidate_dir)
            root = Path(root_dir).resolve()
            candidate, digest = self._fake_candidate(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "-b", "main"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Phase1 Probe",
                    "-c", "user.email=phase1-probe@invalid", "commit", "--allow-empty",
                    "-m", "initial",
                ],
                check=True,
                capture_output=True,
            )
            arg_log = directory / "p5b-args.txt"
            env_log = directory / "p5b-env.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.update(
                {
                    "ENV_LOG": str(env_log),
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                    "CODEX_G4_P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED": (
                        "schema1-exact-idle-child"
                    ),
                }
            )
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ignore-user-config", "--ignore-rules",
                    "--dangerously-bypass-hook-trust", "--json", "-C", str(root),
                    "Return READY.",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = arg_log.read_text(encoding="utf-8").splitlines()
            self.assertIn("features.code_mode_host=false", arguments)
            self.assertEqual(arguments[arguments.index("-s") + 1], "read-only")
            self.assertEqual(
                env_log.read_text(encoding="utf-8").strip(),
                "stderr-v2-parent-child-closed",
            )

    def test_p5b_write_then_close_guard_has_exact_temporary_write_ceiling(self):
        with tempfile.TemporaryDirectory() as candidate_dir, tempfile.TemporaryDirectory(
            prefix="codex-g4-p5b-write-termination.", dir="/private/tmp"
        ) as root_dir:
            directory = Path(candidate_dir)
            root = Path(root_dir).resolve()
            candidate, digest = self._fake_candidate(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "-b", "main"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Phase1 Probe",
                    "-c", "user.email=phase1-probe@invalid", "commit", "--allow-empty",
                    "-m", "initial",
                ],
                check=True,
                capture_output=True,
            )
            arg_log = directory / "p5b-write-args.txt"
            env_log = directory / "p5b-write-env.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.update(
                {
                    "ENV_LOG": str(env_log),
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                    "CODEX_G4_P5B_TRACKED_TERMINATION_PROBE_AUTHORIZED": (
                        "schema1-exact-write-then-close"
                    ),
                }
            )
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ignore-user-config", "--ignore-rules",
                    "--dangerously-bypass-hook-trust", "--json", "-C", str(root),
                    "Return READY.",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = arg_log.read_text(encoding="utf-8").splitlines()
            self.assertIn("features.code_mode_host=false", arguments)
            self.assertEqual(arguments[arguments.index("-s") + 1], "workspace-write")
            self.assertEqual(
                env_log.read_text(encoding="utf-8").strip(),
                "stderr-v2-parent-child-closed",
            )

    def test_auto_compact_guard_injects_fixed_limit_into_stateful_read_only_probe(self):
        with tempfile.TemporaryDirectory() as candidate_dir, tempfile.TemporaryDirectory(
            prefix="codex-g4-compact-wrapper-", dir="/private/tmp"
        ) as root_dir:
            directory = Path(candidate_dir)
            root = Path(root_dir).resolve()
            candidate, digest = self._fake_candidate(directory)
            subprocess.run(
                ["git", "-C", str(root), "init", "-b", "main"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(root), "-c", "user.name=Phase1 Probe",
                    "-c", "user.email=phase1-probe@invalid", "commit", "--allow-empty",
                    "-m", "initial",
                ],
                check=True,
                capture_output=True,
            )
            arg_log = directory / "compact-args.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.update(
                {
                    "CODEX_G4_SESSIONMETA_PROBE_AUTHORIZED": "schema1-headless-stateful",
                    "CODEX_G4_SESSIONMETA_PROBE_ROOT": str(root),
                    "CODEX_G4_AUTO_COMPACT_PROBE_AUTHORIZED": "schema1-post-action-20000",
                }
            )
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ignore-user-config", "--ignore-rules",
                    "--dangerously-bypass-hook-trust", "--json", "-C", str(root),
                    "Return READY.",
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = arg_log.read_text(encoding="utf-8").splitlines()
            self.assertIn("model_auto_compact_token_limit=20000", arguments)
            self.assertEqual(arguments[arguments.index("-s") + 1], "read-only")

    def test_caller_configuration_override_is_denied_before_candidate_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            arg_log = directory / "args.txt"
            result = subprocess.run(
                [
                    str(WRAPPER), "exec", "--ephemeral", "--ignore-user-config",
                    "--ignore-rules", "-c", "features.code_mode_host=true", "Return READY.",
                ],
                env=self._environment(candidate, digest, arg_log),
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 78)
            self.assertIn("may not override candidate configuration", result.stderr)
            self.assertFalse(arg_log.exists())

    def test_login_allows_status_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            status_log = directory / "status.txt"
            status = subprocess.run(
                [str(WRAPPER), "login", "status"],
                env=self._environment(candidate, digest, status_log),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertTrue(status_log.exists())

            logout_log = directory / "logout.txt"
            logout = subprocess.run(
                [str(WRAPPER), "login", "logout"],
                env=self._environment(candidate, digest, logout_log),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(logout.returncode, 78)
            self.assertFalse(logout_log.exists())

    def test_missing_guard_fails_before_candidate_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            arg_log = directory / "args.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.pop("CODEX_G4_LIVE_SELECTION_AUTHORIZED")

            result = subprocess.run(
                [str(WRAPPER), "login", "status"],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 78)
            self.assertFalse(arg_log.exists())

    def test_digest_mismatch_fails_before_candidate_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            arg_log = directory / "args.txt"
            environment = self._environment(candidate, "0" * 64, arg_log)

            result = subprocess.run(
                [str(WRAPPER), "login", "status"],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(digest, "0" * 64)
            self.assertEqual(result.returncode, 78)
            self.assertFalse(arg_log.exists())

    def test_wrapper_has_no_provider_or_credential_configuration(self):
        source = WRAPPER.read_text(encoding="utf-8")
        for forbidden in ("API_KEY", "base_url", "model_provider", "OPENAI_API_KEY"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
