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
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$ARG_LOG\"\n",
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
