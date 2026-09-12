from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "probes" / "zhipu-responses-direct-feasibility-20260907.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ZhipuResponsesDirectFeasibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))

    def test_official_contract_and_live_wire_agree(self) -> None:
        contract = self.receipt["official_contract"]
        successful = self.receipt["invocations"][-1]

        self.assertEqual(contract["wire_api"], "responses")
        self.assertTrue(contract["base_url"].startswith("https://"))
        self.assertRegex(contract["document_sha256"], SHA256)
        self.assertTrue(contract["document_directly_reachable"])
        self.assertEqual(successful["http_status"], 200)
        self.assertTrue(successful["json_valid"])
        self.assertEqual(successful["response_object"], "response")
        self.assertEqual(successful["response_status"], "completed")
        self.assertEqual(successful["response_model"], contract["example_model"])
        self.assertTrue(successful["exact_marker_observed"])

    def test_exploratory_invocations_are_accounted_without_claiming_latency(self) -> None:
        sample = self.receipt["sample_definition"]
        invocations = self.receipt["invocations"]

        self.assertEqual(sample["invocation_count"], len(invocations))
        self.assertEqual([item["ordinal"] for item in invocations], [1, 2, 3])
        self.assertEqual(invocations[0]["response_status"], "incomplete")
        self.assertEqual(
            invocations[0]["interpretation"], "bounded_max_output_negative"
        )
        self.assertIsNone(invocations[1]["exact_marker_observed"])
        self.assertIn("summary_parser", invocations[1]["interpretation"])
        self.assertFalse(sample["representative_latency_cohort"])
        self.assertFalse(sample["p95_defined"])
        for item in invocations:
            self.assertRegex(item["request_sha256"], SHA256)
            self.assertRegex(item["response_sha256"], SHA256)
            self.assertGreater(item["latency_seconds"], 0)

    def test_credential_value_and_raw_provider_output_are_not_evidence(self) -> None:
        credential = self.receipt["credential_handling"]
        sample = self.receipt["sample_definition"]

        self.assertTrue(credential["environment_variable_present"])
        self.assertFalse(credential["value_read_by_probe_reporter"])
        self.assertFalse(credential["value_in_process_arguments"])
        self.assertFalse(credential["value_printed"])
        self.assertFalse(credential["value_hashed"])
        self.assertFalse(credential["value_stored"])
        self.assertTrue(credential["curl_configuration_delivered_over_stdin"])
        self.assertFalse(sample["raw_response_retained"])

    def test_wire_feasibility_does_not_claim_native_child_or_open_a_phase(self) -> None:
        qualification = self.receipt["qualification"]

        self.assertTrue(qualification["responses_endpoint_reachable"])
        self.assertTrue(qualification["responses_json_shape_observed"])
        self.assertTrue(qualification["completed_exact_text_response_observed"])
        self.assertFalse(qualification["codex_client_end_to_end_qualified"])
        self.assertFalse(qualification["native_zhipu_child_spawned"])
        self.assertFalse(qualification["native_agentpath_or_sessionmeta_bound"])
        self.assertFalse(qualification["tool_call_and_result_qualified"])
        self.assertFalse(qualification["callback_wait_cancel_qualified"])
        self.assertFalse(qualification["representative_latency_qualified"])
        self.assertFalse(qualification["phase1_complete"])
        self.assertFalse(qualification["direct_write_qualified"])
        self.assertEqual(qualification["phase2_state"], "closed")
        self.assertEqual(qualification["phase3_state"], "closed")
        self.assertFalse(qualification["phase3_implementation_opened"])


if __name__ == "__main__":
    unittest.main()
