from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "probes" / "codex_deepseek_regression_candidate_wrapper.sh"
WRAPPER_COMMAND = ([sys.executable, str(ROOT / 'probes' / 'windows_candidate_launcher.py'), 'deepseek']
                   if os.name == 'nt' else [str(WRAPPER)])


class DeepSeekRegressionCandidateWrapperTests(unittest.TestCase):
    def setUp(self):
        self.stack = []
        self.probe_tmp = tempfile.TemporaryDirectory(
            prefix="codex-p7-deepseek-regression.", dir=(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp")
        )
        self.handoff_tmp = tempfile.TemporaryDirectory(
            prefix="codex-p7-deepseek-handoff.", dir=(tempfile.gettempdir() if sys.platform == "win32" else "/private/tmp")
        )
        self.stack.extend([self.probe_tmp, self.handoff_tmp])
        self.probe_root = Path(self.probe_tmp.name).resolve()
        subprocess.run(
            ["git", "init", "-b", "main", str(self.probe_root)],
            check=True,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.probe_root),
                "-c",
                "user.name=P7 Probe",
                "-c",
                "user.email=p7-probe@invalid",
                "commit",
                "--allow-empty",
                "-m",
                "initial",
            ],
            check=True,
            stdout=subprocess.PIPE,
        )

        self.runtime_tmp = tempfile.TemporaryDirectory(prefix="p7-wrapper-runtime.")
        self.stack.append(self.runtime_tmp)
        runtime = Path(self.runtime_tmp.name)
        self.argument_log = runtime / "args.txt"
        self.environment_log = runtime / "environment.txt"
        self.candidate = runtime / "candidate"
        self.candidate.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$@\" > \"$ARGUMENT_LOG\"\n"
            "printf '%s\\n' \"${CODEX_DEEPSEEK_HANDOFF_DIR-}\" > \"$ENVIRONMENT_LOG\"\n",
            encoding="utf-8",
        )
        self.candidate.chmod(0o700)
        self.candidate_sha = hashlib.sha256(self.candidate.read_bytes()).hexdigest()
        if os.name == 'nt':
            from windows_launcher_fixture import candidate
            self.candidate, self.candidate_sha = candidate(
                runtime, 'ARGUMENT_LOG', 'ENVIRONMENT_LOG', 'CODEX_DEEPSEEK_HANDOFF_DIR')

        role_dir = runtime / "agents"
        role_dir.mkdir()
        self.role = role_dir / "v4-flash-worker.toml"
        self.role.write_text(
            'name = "v4_flash_worker"\nmodel = "deepseek-v4-flash"\n',
            encoding="utf-8",
        )
        self.role_sha = hashlib.sha256(self.role.read_bytes()).hexdigest()

    def tearDown(self):
        for resource in reversed(self.stack):
            resource.cleanup()

    def environment(self):
        return {
            **os.environ,
            "ARGUMENT_LOG": str(self.argument_log),
            "ENVIRONMENT_LOG": str(self.environment_log),
            "DEEPSEEK_API_KEY": "test-placeholder-not-a-credential",
            "CODEX_P7_DEEPSEEK_REGRESSION_AUTHORIZED": "schema1-native-readonly",
            "CODEX_G4_CANDIDATE_BIN": str(self.candidate),
            "CODEX_G4_CANDIDATE_SHA256": self.candidate_sha,
            "CODEX_P7_DEEPSEEK_ROLE_CONFIG": str(self.role),
            "CODEX_P7_DEEPSEEK_ROLE_SHA256": self.role_sha,
            "CODEX_P7_DEEPSEEK_PROBE_ROOT": str(self.probe_root),
            "CODEX_DEEPSEEK_HANDOFF_DIR": str(Path(self.handoff_tmp.name).resolve()),
        }

    def command(self):
        return [
            *WRAPPER_COMMAND,
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--dangerously-bypass-hook-trust",
            "--json",
            "-C",
            str(self.probe_root),
            "Return READY.",
        ]

    def run_wrapper(self, *, environment=None, command=None):
        return subprocess.run(
            command or self.command(),
            env=environment or self.environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_injects_only_exact_readonly_deepseek_child_configuration(self):
        result = self.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = self.argument_log.read_text(encoding="utf-8").splitlines()
        expected = [
            'features.multi_agent_v2.child_model_providers={v4_flash_worker="deepseek"}',
            'agents.v4_flash_worker.config_file=' + json.dumps(str(self.role)),
            'model_providers.deepseek.base_url="https://api.deepseek.com"',
            'model_providers.deepseek.env_key="DEEPSEEK_API_KEY"',
            'model_providers.deepseek.wire_api="responses"',
            "features.code_mode_host=false",
            "never",
            "read-only",
        ]
        for value in expected:
            self.assertIn(value, arguments)
        self.assertNotIn("app-server", arguments)
        self.assertEqual(
            self.environment_log.read_text(encoding="utf-8").strip(),
            str(Path(self.handoff_tmp.name).resolve()),
        )

    def test_fails_closed_before_execution_for_missing_key_or_digest_drift(self):
        for mutation in ("missing_key", "role_digest"):
            with self.subTest(mutation=mutation):
                if self.argument_log.exists():
                    self.argument_log.unlink()
                environment = self.environment()
                if mutation == "missing_key":
                    environment.pop("DEEPSEEK_API_KEY")
                else:
                    environment["CODEX_P7_DEEPSEEK_ROLE_SHA256"] = "0" * 64
                result = self.run_wrapper(environment=environment)
                self.assertEqual(result.returncode, 78)
                self.assertFalse(self.argument_log.exists())

    def test_fails_closed_for_caller_config_or_non_exec_entry_point(self):
        for command in (
            [*self.command()[:-1], "-c", 'model_provider="deepseek"', "Return READY."],
            [*WRAPPER_COMMAND, "app-server"],
        ):
            with self.subTest(command=command[1]):
                if self.argument_log.exists():
                    self.argument_log.unlink()
                result = self.run_wrapper(command=command)
                self.assertEqual(result.returncode, 78)
                self.assertFalse(self.argument_log.exists())


if __name__ == "__main__":
    unittest.main()
