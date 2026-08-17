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

    def test_wrapper_injects_only_transport_config_before_app_arguments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            arg_log = directory / "args.txt"
            result = subprocess.run(
                [str(WRAPPER), "-c", "features.code_mode_host=true", "app-server"],
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
                    "features.code_mode_host=true",
                    "app-server",
                ],
            )

    def test_missing_guard_fails_before_candidate_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            candidate, digest = self._fake_candidate(directory)
            arg_log = directory / "args.txt"
            environment = self._environment(candidate, digest, arg_log)
            environment.pop("CODEX_G4_LIVE_SELECTION_AUTHORIZED")

            result = subprocess.run(
                [str(WRAPPER), "app-server"],
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
                [str(WRAPPER), "app-server"],
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
