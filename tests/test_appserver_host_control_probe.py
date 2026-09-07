import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "run_appserver_host_control_probe.py"
RECEIPT = ROOT / "probes" / "g4-isolated-appserver-host-control-20260907.json"

SPEC = importlib.util.spec_from_file_location("run_appserver_host_control_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


class AppServerHostControlProbeTests(unittest.TestCase):
    def test_configuration_resolves_current_semantic_runtime(self):
        configuration = probe.probe_configuration()

        self.assertEqual(configuration["runtime_role"], "current_signed_runtime")
        self.assertTrue(configuration["identity"]["codex_version"])
        self.assertRegex(
            configuration["identity"]["source_commit"], r"^[0-9a-f]{40}$"
        )
        self.assertTrue(configuration["binary"].is_absolute())
        self.assertRegex(configuration["binary_sha256"], r"^[0-9a-f]{64}$")

    def test_isolated_environment_has_only_the_closed_noncredential_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = probe.isolated_environment(Path(directory))

        self.assertEqual(set(environment), probe.SAFE_ENVIRONMENT_KEYS)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("ZHIPU_API_KEY", environment)

    def test_host_control_messages_have_no_thread_identity(self):
        root = Path("/isolated-root")
        messages = (
            probe.fs_write_message(root / "fs", b"payload"),
            probe.process_spawn_message(root, root / "process"),
        )

        for message in messages:
            self.assertNotIn("threadId", message["params"])
            self.assertNotIn("thread_id", message["params"])

    def test_binary_hash_drift_fails_before_app_server_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "codex"
            binary.write_bytes(b"not-a-codex-binary")
            with self.assertRaisesRegex(probe.ProbeError, "SHA-256"):
                probe.run_probe(
                    binary,
                    "0" * 64,
                    {"codex_version": "fixture", "source_commit": "1" * 40},
                )

    def test_frozen_receipt_is_exact_and_non_authorizing(self):
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        configuration = probe.probe_configuration()

        self.assertEqual(receipt["runtime_role"], configuration["runtime_role"])
        self.assertEqual(receipt["codex_version"], configuration["identity"]["codex_version"])
        self.assertEqual(receipt["source_commit"], configuration["identity"]["source_commit"])
        self.assertEqual(receipt["binary_sha256"], configuration["binary_sha256"])
        self.assertTrue(receipt["client_connection_sufficient_for_observed_host_control"])
        self.assertFalse(receipt["native_child_reachability_proven"])
        self.assertFalse(receipt["pretooluse_child_mediation_proven"])
        self.assertFalse(receipt["strong_global_quiescence_proven"])
        self.assertFalse(receipt["phase1_complete"])
        self.assertFalse(receipt["direct_write_qualified"])


if __name__ == "__main__":
    unittest.main()
