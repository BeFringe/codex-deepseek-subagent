import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "probes" / "run_p6c_product_independent_live.py"
ADJUDICATOR = REPO / "probes" / "adjudicate_p6c_product_independent_live.py"
CHECKER = REPO / "probes" / "check_p6c_live_bundle.py"
FROZEN_BUNDLE = REPO / "probes" / "p6c-product-independent-live-bundle-20260909.json"
FROZEN_ADJUDICATION = REPO / "probes" / "p6c-product-independent-live-adjudication-20260909.json"
ENVIRONMENT = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
sys.path.insert(0, str(REPO / "probes"))

import adjudicate_p6c_product_independent_live as live_adjudicator  # noqa: E402


def run_live(directory: Path) -> tuple[Path, Path, dict]:
    work_root = directory / "work"
    bundle_path = directory / "bundle.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--work-root",
            str(work_root),
            "--bundle",
            str(bundle_path),
        ],
        cwd=REPO,
        env=ENVIRONMENT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return work_root, bundle_path, json.loads(bundle_path.read_text(encoding="utf-8"))


def run_adjudicator(bundle_path: Path, receipt_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(ADJUDICATOR),
            "--bundle",
            str(bundle_path),
            "--receipt",
            str(receipt_path),
            "--require-qualified",
        ],
        cwd=REPO,
        env=ENVIRONMENT,
        capture_output=True,
        text=True,
        check=False,
    )


class P6CProductIndependentLiveTests(unittest.TestCase):
    def test_frozen_live_bundle_and_adjudication_are_exactly_bound(self):
        bundle = json.loads(FROZEN_BUNDLE.read_text(encoding="utf-8"))
        receipt = json.loads(FROZEN_ADJUDICATION.read_text(encoding="utf-8"))
        mechanics = live_adjudicator.checker.qualification(bundle)

        self.assertTrue(mechanics["provider_free_bundle_dispatchable"])
        self.assertEqual(mechanics["attestation"]["owner_decision"], "dispatch")
        self.assertEqual(
            receipt["bundle_canonical_sha256"],
            live_adjudicator.checker.bundle_sha256(bundle),
        )
        self.assertEqual(
            receipt["bundle_file_sha256"],
            live_adjudicator.runner.file_sha256(FROZEN_BUNDLE),
        )
        self.assertEqual(
            receipt["root_identity"], bundle["frozen_contract"]["root_identity"]
        )
        self.assertEqual(
            receipt["authority_epoch"], bundle["frozen_contract"]["authority_epoch"]
        )
        self.assertEqual(
            receipt["producer_pid"],
            bundle["representative_dense_cohort"]["selection_evidence"]["producer_pid"],
        )
        self.assertNotEqual(receipt["producer_pid"], receipt["adjudicator_pid"])
        self.assertEqual(receipt["transactions"]["sample_count"], 20)
        self.assertEqual(receipt["transactions"]["invocation_count"], 20)
        self.assertEqual(receipt["phase_and_seam_recomputation"]["mutation_seam_count"], 10)
        self.assertEqual(receipt["p6b_state"], "qualified")
        self.assertEqual(receipt["p6c_state"], "qualified")
        self.assertFalse(receipt["phase1_complete"])
        self.assertFalse(receipt["direct_write_qualified"])

    def test_real_runner_and_distinct_fresh_disk_owner_close_finite_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            work_root, bundle_path, bundle = run_live(directory)
            receipt_path = directory / "receipt.json"
            result = run_adjudicator(bundle_path, receipt_path)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertTrue(receipt["distinct_process"])
            self.assertEqual(receipt["p6b_state"], "qualified")
            self.assertEqual(receipt["p6c_state"], "qualified")
            self.assertFalse(receipt["phase1_complete"])
            self.assertFalse(receipt["direct_write_qualified"])
            self.assertEqual(receipt["transactions"]["sample_count"], 20)
            self.assertEqual(receipt["transactions"]["invocation_count"], 20)
            self.assertEqual(
                receipt["transactions"]["multiplicity_counts"],
                {"8": 5, "16": 5, "24": 5, "32": 5},
            )
            self.assertEqual(
                receipt["phase_and_seam_recomputation"]["mutation_seam_count"],
                10,
            )
            self.assertEqual(
                bundle["representative_dense_cohort"]["selection_policy"],
                "exhaustive frozen population; no sampled or omitted cases",
            )
            self.assertEqual(len(bundle["phase_results"]), 3)
            self.assertEqual(len(bundle["mutation_observations"]), 10)
            self.assertTrue(all(sample["elapsed"] > 0 for sample in bundle["latency_sample_receipts"]))
            self.assertTrue((work_root / "source" / ".git").is_dir())

            mechanics = subprocess.run(
                [sys.executable, str(CHECKER), "--bundle", str(bundle_path), "--require-dispatchable"],
                cwd=REPO,
                env=ENVIRONMENT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(mechanics.returncode, 0, mechanics.stdout + mechanics.stderr)
            mechanics_result = json.loads(mechanics.stdout)
            self.assertTrue(mechanics_result["provider_free_bundle_dispatchable"])
            self.assertFalse(mechanics_result["p6c_live_qualified"])

    def test_fresh_owner_rejects_timing_that_is_not_clock_derived(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, bundle_path, bundle = run_live(directory)
            bundle["latency_sample_receipts"][0]["evidence"]["elapsed_ns"] += 1
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            result = run_adjudicator(bundle_path, directory / "receipt.json")

            self.assertEqual(result.returncode, 1)
            self.assertIn("elapsed time is not clock-derived", result.stdout)

    def test_fresh_owner_rejects_source_or_materialized_disk_drift(self):
        cases = ("source", "materialized")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                work_root, bundle_path, _ = run_live(directory)
                if case == "source":
                    (work_root / "source" / "protocol.json").write_text("{}\n", encoding="utf-8")
                    expected = "source root is dirty"
                else:
                    (work_root / "output" / "materialized-frontier.json").write_text(
                        '{"schema":1,"items":[]}\n', encoding="utf-8"
                    )
                    expected = "materialized mixed frontier is not exact"

                result = run_adjudicator(bundle_path, directory / "receipt.json")

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stdout)

    def test_fresh_owner_rejects_same_process_self_adjudication_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, bundle_path, bundle = run_live(directory)
            bundle["representative_dense_cohort"]["selection_evidence"]["producer_pid"] = os.getpid()
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

            with self.assertRaisesRegex(
                live_adjudicator.AdjudicationError, "not a distinct process"
            ):
                live_adjudicator.adjudicate(bundle_path)


if __name__ == "__main__":
    unittest.main()
