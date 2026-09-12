import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "probes" / "run_appserver_quiescence_negative_probe.py"
RECEIPT = (
    ROOT / "probes" / "g4-isolated-appserver-quiescence-negative-20260907.json"
)

SPEC = importlib.util.spec_from_file_location(
    "run_appserver_quiescence_negative_probe", SCRIPT
)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


class AppServerQuiescenceNegativeProbeTests(unittest.TestCase):
    def test_detached_late_writer_is_explicit_and_has_no_thread_identity(self):
        root = Path("/isolated-root")
        message = probe.detached_late_writer_message(
            root, root / "ready", root / "late", 0.8
        )

        self.assertEqual(message["method"], "process/spawn")
        self.assertNotIn("threadId", message["params"])
        self.assertNotIn("thread_id", message["params"])
        child_code = message["params"]["command"][2]
        self.assertIn("os.setsid()", child_code)
        self.assertIn("signal.SIG_IGN", child_code)

    def test_nonpositive_delay_is_rejected(self):
        with self.assertRaisesRegex(probe.ProbeError, "delay must be positive"):
            probe.detached_late_writer_message(
                Path("/isolated-root"), Path("/ready"), Path("/late"), 0
            )

    def test_frozen_receipt_proves_post_exit_late_write_but_not_native_child(self):
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        configuration = probe.probe_configuration()

        self.assertEqual(receipt["runtime_role"], configuration["runtime_role"])
        self.assertEqual(receipt["codex_version"], configuration["identity"]["codex_version"])
        self.assertEqual(receipt["source_commit"], configuration["identity"]["source_commit"])
        self.assertEqual(receipt["binary_sha256"], configuration["binary_sha256"])
        self.assertFalse(receipt["late_write_exists_before_eof"])
        self.assertFalse(receipt["late_write_exists_at_server_exit"])
        self.assertTrue(receipt["late_write_exists_after_observation"])
        self.assertTrue(receipt["late_write_after_app_server_exit_observed"])
        self.assertTrue(receipt["external_process_tree_quiescence_barrier_required"])
        self.assertFalse(
            receipt["app_server_exit_strong_process_tree_barrier_proven"]
        )
        self.assertFalse(receipt["native_child_termination_quiescence_proven"])
        self.assertFalse(receipt["phase1_complete"])
        self.assertFalse(receipt["direct_write_qualified"])

    def test_observation_window_must_exceed_child_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "unused.json"
            with self.assertRaisesRegex(probe.ProbeError, "must exceed"):
                probe.run_probe(
                    index,
                    delay_seconds=1.0,
                    post_exit_observation_seconds=1.0,
                )


if __name__ == "__main__":
    unittest.main()
