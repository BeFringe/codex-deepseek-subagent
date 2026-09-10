from pathlib import Path
import hashlib
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "probes" / "current-signed-runtime-g4-cumulative-source-candidate.json"


class CurrentG4CumulativeSourceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        cls.patch_path = ROOT / cls.receipt["patch"]["path"]
        cls.patch_bytes = cls.patch_path.read_bytes()
        cls.patch_text = cls.patch_bytes.decode("utf-8")

    def test_binds_exact_current_source_base(self):
        source = self.receipt["source"]
        self.assertEqual(source["repository"], "https://github.com/openai/codex")
        self.assertEqual(source["tag"], "rust-v0.153.4")
        self.assertEqual(source["semantic_version"], "0.153.4")
        self.assertEqual(
            source["base_commit"],
            "3d2ee51ca2d5db578f328aa75e20aa22c0197c9a",
        )

    def test_patch_bytes_and_complete_path_set_are_bound(self):
        patch = self.receipt["patch"]
        self.assertEqual(hashlib.sha256(self.patch_bytes).hexdigest(), patch["sha256"])
        self.assertEqual(len(self.patch_bytes), patch["bytes"])
        self.assertEqual(len(self.patch_text.splitlines()), patch["lines"])
        paths = re.findall(r"(?m)^diff --git a/(.+) b/(.+)$", self.patch_text)
        self.assertEqual(len(paths), patch["changed_paths"])
        self.assertTrue(all(left == right for left, right in paths))
        names = {left for left, _ in paths}
        self.assertIn("codex-rs/core/src/agent/control/spawn.rs", names)
        self.assertIn("codex-rs/core/src/client.rs", names)
        self.assertIn("codex-rs/core/src/tools/g4_catalog_receipt.rs", names)
        self.assertIn("codex-rs/core/src/tools/handlers/multi_agents_v2/close_agent.rs", names)
        self.assertIn("codex-rs/hooks/src/events/pre_tool_use.rs", names)
        self.assertIn("codex-rs/model-provider-info/src/lib.rs", names)
        self.assertIn("codex-rs/model-provider/src/provider.rs", names)
        self.assertIn("codex-rs/protocol/src/protocol.rs", names)
        self.assertIn("supports_namespace_tools", self.patch_text)
        self.assertIn("requires_function_call_output_adjacency", self.patch_text)

    def test_fresh_replay_is_exact_but_not_windows_evidence(self):
        replay = self.receipt["fresh_replay"]
        self.assertTrue(replay["detached_exact_base"])
        self.assertTrue(replay["git_apply_check_passed"])
        self.assertTrue(replay["git_apply_index_passed"])
        self.assertTrue(replay["canonical_diff_byte_exact"])
        self.assertEqual(replay["replayed_patch_sha256"], self.receipt["patch"]["sha256"])
        self.assertEqual(replay["changed_paths"], self.receipt["patch"]["changed_paths"])

        boundary = self.receipt["portable_boundary"]
        self.assertTrue(boundary["product_independent"])
        self.assertFalse(boundary["credential_values_included"])
        self.assertFalse(boundary["incremental_patch_order_required"])
        self.assertTrue(boundary["windows_build_input_ready"])
        self.assertFalse(boundary["windows_native_binary_built"])
        self.assertFalse(boundary["windows_live_runtime_observed"])
        self.assertFalse(boundary["windows_live_qualified"])
        self.assertFalse(boundary["phase1_complete"])
        self.assertFalse(boundary["direct_write_qualified"])
        self.assertEqual(boundary["phase2_state"], "closed")
        self.assertEqual(boundary["phase3_state"], "closed")

    def test_patch_contains_no_originating_host_checkout_path(self):
        self.assertIsNone(
            re.search(r"(?m)(?:^|[\"' (])/(?:Users|home)/[^/\s]+/", self.patch_text)
        )
        self.assertNotIn("/private/tmp", self.patch_text.lower())


if __name__ == "__main__":
    unittest.main()
