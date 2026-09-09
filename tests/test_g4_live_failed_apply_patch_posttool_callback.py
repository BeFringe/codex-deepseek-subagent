from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    ROOT
    / "probes"
    / "g4-live-failed-apply-patch-posttool-callback-20260908.json"
)
RUNTIME_INDEX_PATH = ROOT / "probes" / "codex-runtime-evidence-index.json"
STATUS_PATH = ROOT / "probes" / "phase1-g4-status.json"
WRAPPER_PATH = ROOT / "probes" / "codex_plaintext_candidate_wrapper.sh"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G4LiveFailedApplyPatchPostToolCallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        cls.runtime_index = json.loads(
            RUNTIME_INDEX_PATH.read_text(encoding="utf-8")
        )
        cls.status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        patch_name = cls.receipt["source_candidate"]["patch"]
        cls.patch_path = ROOT / patch_name
        cls.patch_bytes = cls.patch_path.read_bytes()
        cls.patch_text = cls.patch_bytes.decode("utf-8")

    def test_runtime_identity_tracks_current_semantic_role(self) -> None:
        runtime = self.receipt["runtime"]
        current_role = self.runtime_index["current_runtime_role"]
        current = self.runtime_index["runtime_roles"][current_role]

        self.assertEqual(runtime["runtime_role"], current_role)
        self.assertEqual(runtime["codex_version"], current["codex_version"])
        self.assertEqual(runtime["base_source_commit"], current["source_commit"])
        self.assertRegex(runtime["candidate_sha256"], SHA256)
        self.assertRegex(runtime["code_mode_host_sha256"], SHA256)
        self.assertFalse(runtime["parent_provider_changed"])
        self.assertFalse(runtime["gui_app_server_selected"])
        self.assertFalse(runtime["codex_cli_path_modified"])
        self.assertFalse(runtime["credential_values_read_or_stored"])

    def test_source_candidate_is_narrow_and_reconstructable(self) -> None:
        source = self.receipt["source_candidate"]

        self.assertEqual(
            hashlib.sha256(self.patch_bytes).hexdigest(), source["patch_sha256"]
        )
        self.assertEqual(source["git_apply_reverse_check_exit_code"], 0)
        self.assertEqual(source["cargo_fmt_check_exit_code"], 0)
        self.assertIn("apply_patch handler error", source["scope"])
        self.assertIn("preserve all other unsuccessful-tool behavior", source["scope"])
        self.assertEqual(
            [test["exit_code"] for test in source["rust_tests"]], [0, 0]
        )
        self.assertIn("post_tool_use_runs_after_apply_patch_handler_failure", self.patch_text)
        self.assertIn('payload.tool_name.name() == "apply_patch"', self.patch_text)
        self.assertNotIn("Cargo.lock", self.patch_text)
        self.assertFalse(
            source["default_test_stack_control"]["qualified_as_source_failure"]
        )

    def test_live_probe_joins_failed_tool_callbacks_by_exact_identity(self) -> None:
        probe = self.receipt["probe"]
        chain = self.receipt["hook_chain"]

        self.assertEqual(probe["canonical_agent_path"], "/root")
        self.assertEqual(probe["branch"], "main")
        self.assertRegex(probe["full_head"], re.compile(r"^[0-9a-f]{40}$"))
        self.assertEqual(probe["target"], "baseline.txt")
        self.assertEqual(
            probe["target_sha256_before"], probe["target_sha256_after"]
        )
        self.assertIn("verification failed", probe["failure"])
        self.assertEqual(probe["candidate_exit_code"], 0)
        self.assertEqual(probe["raw_stdout_lines"], 7)
        self.assertEqual(probe["raw_stdout_bytes"], 862)
        self.assertEqual(probe["raw_stderr_lines"], 3)
        self.assertEqual(probe["raw_stderr_bytes"], 255)
        self.assertRegex(probe["raw_stdout_sha256"], SHA256)
        self.assertRegex(probe["raw_stderr_sha256"], SHA256)
        self.assertEqual(len(probe["no_tool_timing_controls"]), 2)

        self.assertEqual(chain["tool_name"], "apply_patch")
        self.assertEqual(chain["posttool_sequence"], chain["pretool_sequence"] + 1)
        self.assertEqual(chain["event_count_before"] + 1, chain["pretool_sequence"])
        self.assertRegex(chain["tool_use_id"], re.compile(r"^exec-[0-9a-f-]+$"))
        self.assertRegex(chain["pretool_receipt_sha256"], SHA256)
        self.assertRegex(chain["posttool_receipt_sha256"], SHA256)
        self.assertRegex(chain["chain_file_sha256_at_event_count_1999"], SHA256)
        self.assertFalse(chain["raw_payload_stored"])

    def test_failed_patch_releases_unchanged_lease_without_manual_recovery(self) -> None:
        lease = self.receipt["writer_lease"]
        barrier = self.receipt["post_barrier"]
        build = self.receipt["build"]

        self.assertRegex(lease["claim_id"], re.compile(r"^[0-9a-f-]{36}$"))
        self.assertRegex(lease["claim_sha256"], SHA256)
        self.assertRegex(lease["receipt_sha256"], SHA256)
        self.assertEqual(
            lease["before_snapshot_sha256"], lease["after_snapshot_sha256"]
        )
        self.assertTrue(lease["claim_absent_after_callback"])
        self.assertFalse(lease["manual_recovery_required"])
        self.assertEqual(barrier["git_status_short"], "")
        self.assertFalse(barrier["index_changed"])
        self.assertEqual(barrier["candidate_or_code_mode_host_process_count"], 0)
        self.assertRegex(barrier["hooks_sha256"], SHA256)
        self.assertFalse(barrier["live_hooks_modified"])
        self.assertTrue(build["cargo_target_removed_after_evidence_freeze"])
        self.assertEqual(build["candidate_copy_size_after_cleanup"], "622M")
        self.assertTrue(build["disposable_candidate_copy_preserved"])

    def test_wrapper_guard_and_status_keep_qualification_bounded(self) -> None:
        wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
        evidence = str(RECEIPT_PATH.relative_to(ROOT))
        patch = str(self.patch_path.relative_to(ROOT))

        self.assertIn("CODEX_G4_FAILED_PATCH_CALLBACK_PROBE_AUTHORIZED", wrapper)
        self.assertIn("schema1-root-failed-apply-patch", wrapper)
        self.assertIn("/private/tmp/codex-g4-write-posttool-*", wrapper)
        self.assertIn("code_mode_host=false", wrapper)

        for gate_id in ("P4", "P5b"):
            gate = next(
                item for item in self.status["phase1"]["gates"]
                if item["id"] == gate_id
            )
            self.assertIn(evidence, gate["evidence"])
            self.assertIn(patch, gate["evidence"])
        self.assertEqual(
            next(item for item in self.status["phase1"]["gates"] if item["id"] == "P4")["state"],
            "partial",
        )
        self.assertEqual(
            next(item for item in self.status["phase1"]["gates"] if item["id"] == "P5b")["state"],
            "qualified",
        )

        verdict = self.receipt["verdict"]
        self.assertTrue(verdict["failed_apply_patch_posttool_callback_qualified"])
        self.assertTrue(verdict["same_tool_use_id_joined"])
        self.assertTrue(verdict["unchanged_disk_release_qualified"])
        self.assertFalse(verdict["other_failed_mutation_surfaces_qualified"])
        self.assertFalse(verdict["strong_global_quiescence_qualified"])
        self.assertFalse(verdict["p5b_complete"])
        self.assertFalse(verdict["phase1_complete"])
        self.assertFalse(verdict["direct_write_qualified"])
        self.assertEqual(verdict["phase2_state"], "closed")
        self.assertEqual(verdict["phase3_state"], "closed")


if __name__ == "__main__":
    unittest.main()
