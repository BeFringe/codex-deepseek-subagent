import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "p6c-feature5-readonly-gap-adjudication-20260909.json"
STATUS = ROOT / "probes" / "phase1-g4-status.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class P6cFeature5ReadonlyGapAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_source_identity_is_exact_and_read_only(self):
        source = self.receipt["source_task"]
        self.assertEqual(source["branch"], "feature5")
        self.assertEqual(
            source["head"], "dd7c9fdb268b4ee8ac3545f43e3f5f19e715ff3b"
        )
        self.assertEqual(source["tracked_change_count"], 0)
        self.assertFalse(source["diagnostic_directory_inspected"])
        self.assertFalse(source["credential_values_observed"])
        for item in self.receipt["canonical_sources"]:
            self.assertTrue(item["path"])
            self.assertRegex(item["sha256"], SHA256_RE)

    def test_gate_d_latency_is_partial_not_dense_authority(self):
        latency = self.receipt["available_partial_evidence"]["end_to_end_latency"]
        self.assertEqual(latency["corpus_record_count"], 100000)
        self.assertEqual(latency["fuzzy_sample_count"], 240)
        self.assertEqual(latency["statistic"], "p95_nearest_rank")
        self.assertLessEqual(latency["fts5_fuzzy_p95_ms"], latency["fuzzy_limit_ms"])
        self.assertLessEqual(
            latency["fallback_fuzzy_p95_ms"], latency["fuzzy_limit_ms"]
        )
        self.assertFalse(latency["dense_owner_cohort_identity_present"])
        self.assertFalse(latency["per_sample_invocation_join_present"])

    def test_all_required_cross_dimension_joins_remain_missing(self):
        self.assertEqual(
            set(self.receipt["missing_required_joins"]),
            {
                "dense_owner_cohort_identity",
                "per_sample_invocation_latency_join",
                "same_cohort_U1_R_U2_true_cardinalities",
                "coarse_refine_materialize_identity_conservation_elapsed_receipts",
                "complete_authoritative_materialized_mixed_frontier_exactness",
                "before_mid_after_mutation_race_raw_receipts",
            },
        )

    def test_summary_evidence_cannot_promote_p6c(self):
        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["existing_gate_d_latency_is_contribution_evidence"])
        self.assertFalse(verdict["tasks_summary_can_authorize"])
        self.assertFalse(verdict["matrix_summary_can_authorize"])
        self.assertFalse(verdict["representative_dense_latency_subgate_qualified"])
        self.assertFalse(verdict["p6c_qualified"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")

    def test_phase1_status_references_gap_without_promotion(self):
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        gate = next(gate for gate in status["phase1"]["gates"] if gate["id"] == "P6c")
        self.assertIn(
            "probes/p6c-feature5-readonly-gap-adjudication-20260909.json",
            gate["evidence"],
        )
        self.assertEqual(gate["state"], "partial")
        self.assertEqual(gate["provider_free"], "pass")
        self.assertIn("dense owner cohort identity", gate["blocker"])


if __name__ == "__main__":
    unittest.main()
