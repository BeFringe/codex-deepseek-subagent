import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


REPO = Path(__file__).resolve().parents[1]
WATCHDOG = REPO / "hooks" / "authority_watchdog.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compatibility_state = load_module(
    "compatibility_state", REPO / "hooks" / "compatibility_state.py"
)
runtime_guard = load_module("runtime_guard", REPO / "hooks" / "runtime_guard.py")


StateStore = compatibility_state.StateStore
capsule_sha256 = compatibility_state.capsule_sha256
sha256_bytes = compatibility_state.sha256_bytes


class RuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        self.git("add", "baseline.txt")
        self.git("commit", "-m", "baseline")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.store = StateStore(self.root / "state")
        self.child_transcript = self.root / "child.jsonl"
        self.parent_transcript = self.root / "parent.jsonl"
        self.write_parent_session_meta()
        self.write_session_meta()
        self.assignment = "implement only the assigned slice"
        self.capsule = self.make_capsule()
        self.store.stage(self.capsule, self.assignment)
        identity = runtime_guard.child_identity_from_hook(self.child_hook("SubagentStart"))
        self.store.claim(self.capsule["handoff_id"], identity)
        self.store.activate(self.capsule["handoff_id"])

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def write_session_meta(self, **overrides):
        payload = {
            "session_id": "runtime-session",
            "id": "child-thread",
            "parent_thread_id": "parent-thread",
            "timestamp": "2026-08-12T00:00:00Z",
            "cwd": str(self.repository),
            "originator": "fixture",
            "cli_version": "0.147.0",
            "source": "sub_agent",
            "agent_role": "fixture_worker",
            "agent_path": "/root/bounded_task",
            "model_provider": "fixture-provider",
        }
        payload.update(overrides)
        item = {"timestamp": payload["timestamp"], "type": "session_meta", "payload": payload}
        self.child_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

    def write_parent_session_meta(self, **overrides):
        payload = {
            "session_id": "runtime-session",
            "id": "parent-thread",
            "timestamp": "2026-08-12T00:00:00Z",
            "cwd": str(self.repository),
            "originator": "fixture",
            "cli_version": "0.147.0",
            "source": "sub_agent",
            "model_provider": "fixture-provider",
        }
        payload.update(overrides)
        item = {"timestamp": payload["timestamp"], "type": "session_meta", "payload": payload}
        self.parent_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

    def make_capsule(self, *, mutation_mode="write"):
        now = dt.datetime.now(dt.timezone.utc)
        read_only = mutation_mode == "read_only"
        value = {
            "schema": 2,
            "assignment_id": str(uuid.uuid4()),
            "handoff_id": str(uuid.uuid4()),
            "runtime_session_id": "runtime-session",
            "parent_thread_id": "parent-thread",
            "parent_turn_id": "parent-turn",
            "spawn_tool_use_id": "spawn-tool-use",
            "worker_profile": "fixture-worker",
            "agent_type": "fixture_worker",
            "requested_task_name": "bounded_task",
            "canonical_agent_path": "/root/bounded_task",
            "root": {
                "path": str(self.repository.resolve()),
                "branch": "main",
                "base_commit": self.base,
                "allow_descendant_head": False,
                "base_index_changed": False,
                "base_git_status_short": "",
            },
            "capture_preflight": None,
            "capture_snapshot_sha256": "e" * 64,
            "assignment_mutation_mode": mutation_mode,
            "user_child_write_authorization": (
                {
                    "schema": 1,
                    "decision": "not_required",
                    "authorizing_turn_id": None,
                    "user_prompt_sha256": None,
                }
                if read_only
                else {
                    "schema": 1,
                    "decision": "allow",
                    "authorizing_turn_id": "parent-turn",
                    "user_prompt_sha256": "f" * 64,
                }
            ),
            "owned_paths": [] if read_only else ["owned"],
            "excluded_paths": [] if read_only else ["owned/excluded"],
            "git_authority": {"stage": False, "commit": False, "branch": False, "push": False},
            "ownership_handover": [],
            "stop_condition": "assigned slice completion only",
            "verification": ["fixture verification"],
            "authority_provenance": {
                "authoritative_input_owners": ["fixture.owner"],
                "authoritative_input_roots": ["inputs"],
                "forbidden_caller_supplied_derived_facts": ["oracle_obligations"],
                "test_only_injection_seams": ["fixture.inject_oracle"],
                "required_derivation_boundary": "fixture.owner.derive",
            },
            "execution_contract": {
                "posture": "strict_read_only" if read_only else "direct_write_unqualified",
                "review_range": (
                    {"base_oid": self.base, "head_oid": self.base}
                    if read_only
                    else None
                ),
                "required_invariants": [],
                "diagnostics": {
                    "stable_failure_codes": [],
                    "known_true_failure_codes": [],
                    "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED",
                    "allow_literal_expensive_rerun": False,
                    "allowed_failure_code_localities": {},
                },
                "proven_input_baselines": [],
                "termination_contract": {"catalog_closed": True, "boundary_catalog": []},
                "evidence_binding": None,
                "review_continuation": None,
                "closed_registries": [],
                "relation_contracts": [],
                "capsule_feasibility_attestation": None if read_only else {
                    "parent_owner_id": "fixture.owner",
                    "exact_claimed_invariant": "the assigned slice closes within budget",
                    "counterexample_probe": {
                        "probe_id": "fixture-negative-probe",
                        "probe_input_sha256": "1" * 64,
                        "executed": True,
                        "counterexample_found": False,
                        "evidence_sha256": "2" * 64,
                    },
                    "bounded_completion": {
                        "completion_condition": "assigned slice",
                        "work_budget": {
                            "unit": "fixture-step",
                            "cardinality_domain": "fixture-object",
                            "limit": 10,
                        },
                        "proposed_mechanism": "bounded fixture mechanism",
                        "mechanism_measurement": {
                            "unit": "fixture-step",
                            "cardinality_domain": "fixture-object",
                            "required_lower_bound": 9,
                        },
                        "scale_evidence": {
                            "basis": "proven_monotonicity",
                            "witness_input_sha256": None,
                            "evidence_sha256": "4" * 64,
                        },
                        "equivalence_compression": None,
                        "mechanism_satisfies": True,
                        "evidence_sha256": "3" * 64,
                    },
                    "unresolved_assumptions": [],
                    "owner_decision": "dispatch",
                },
            },
            "preexisting_dirty": [],
            "assignment_sha256": sha256_bytes(self.assignment.encode("utf-8")),
            "created_at": now.isoformat(),
            "pre_write_attestation_deadline": (now + dt.timedelta(seconds=30)).isoformat(),
            "expires_at": (now + dt.timedelta(minutes=5)).isoformat(),
        }
        value["capsule_sha256"] = capsule_sha256(value)
        return value

    def replace_active_capsule(self, capsule):
        self.store.finalize(self.capsule["assignment_id"], {}, complete=False)
        self.capsule = capsule
        self.store.stage(self.capsule, self.assignment)
        identity = runtime_guard.child_identity_from_hook(self.child_hook("SubagentStart"))
        self.store.claim(self.capsule["handoff_id"], identity)
        self.store.activate(self.capsule["handoff_id"])

    def child_hook(self, event, **overrides):
        value = {
            "hook_event_name": event,
            "session_id": "runtime-session",
            "agent_id": "child-thread",
            "agent_type": "fixture_worker",
            "transcript_path": str(self.child_transcript),
            "cwd": str(self.repository),
        }
        value.update(overrides)
        return value

    def stop_hook(self, message):
        return {
            "hook_event_name": "SubagentStop",
            "session_id": "runtime-session",
            "agent_id": "child-thread",
            "agent_type": "fixture_worker",
            "transcript_path": str(self.parent_transcript),
            "agent_transcript_path": str(self.child_transcript),
            "last_assistant_message": message,
        }

    def attestation(self, **overrides):
        snapshot = runtime_guard.collect_git_snapshot(str(self.repository))
        value = {
            "assignment_id": self.capsule["assignment_id"],
            "handoff_id": self.capsule["handoff_id"],
            "capsule_sha256": self.capsule["capsule_sha256"],
            "compact_invariant_sha256": compatibility_state.compact_invariant_sha256(
                self.capsule
            ),
            "authority_provenance": {
                "policy_sha256": compatibility_state.provenance_policy_sha256(
                    self.capsule
                ),
                "worker_claimed_origin": "owner_internal",
                "test_only_injection_used": False,
                "derivation_receipt_sha256": "d" * 64,
            },
            "canonical_agent_path": "/root/bounded_task",
            "recovery_count": 0,
            "context_lost": False,
            **snapshot,
            "verification": [{"command": "fixture verification", "exit_code": 0}],
            "authority_violation": False,
            "assigned_slice_complete": True,
            "inventory_summaries": [],
        }
        value.update(overrides)
        return "BEGIN CODEX WORKER ATTESTATION\n" + json.dumps(value) + "\nEND CODEX WORKER ATTESTATION"

    def bind_closed_registry(self, item_ids):
        active = self.store.path("active", self.capsule["assignment_id"])
        envelope = json.loads(active.read_text(encoding="utf-8"))
        envelope["capsule"]["execution_contract"]["closed_registries"] = [
            {
                "registry_id": "test-id-inventory",
                "closed_item_ids": item_ids,
                "count_authority": "mechanical_cardinality_only",
            }
        ]
        envelope["capsule"]["capsule_sha256"] = capsule_sha256(envelope["capsule"])
        active.write_text(json.dumps(envelope), encoding="utf-8")
        self.capsule = envelope["capsule"]

    def test_session_meta_exactly_binds_parent_role_and_canonical_path(self):
        identity = runtime_guard.child_identity_from_hook(self.child_hook("PreToolUse"))

        self.assertEqual(identity["runtime_session_id"], "runtime-session")
        self.assertEqual(identity["child_thread_id"], "child-thread")
        self.assertEqual(identity["parent_thread_id"], "parent-thread")
        self.assertEqual(identity["agent_type"], "fixture_worker")
        self.assertEqual(identity["canonical_agent_path"], "/root/bounded_task")

    def test_root_parent_meta_needs_no_child_role_or_agent_path(self):
        identity = runtime_guard.child_identity_from_stop(
            self.stop_hook(self.attestation())
        )

        self.assertEqual(identity["parent_thread_id"], "parent-thread")

    def test_every_pre_tool_use_revalidates_session_meta(self):
        first = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )
        self.write_session_meta(parent_thread_id="wrong-parent")
        second = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertIn("AUTHORITY.REATTESTED", first["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(second["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_corrupt_active_runtime_metadata_fails_closed(self):
        active = self.store.path("active", self.capsule["assignment_id"])
        envelope = json.loads(active.read_text(encoding="utf-8"))
        del envelope["runtime"]["first_git_attested_at"]
        active.write_text(json.dumps(envelope), encoding="utf-8")

        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("runtime metadata", result["hookSpecificOutput"]["permissionDecisionReason"])

    def test_compaction_increments_epoch_and_post_compaction_mismatch_blocks(self):
        runtime_guard.pre_compact(self.store, self.child_hook("PreCompact"))
        allowed = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )
        self.write_session_meta(agent_path="/root/expanded_task")
        blocked = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertIn("recovery_count=1", allowed["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(blocked["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_pre_tool_use_reads_actual_head_and_blocks_unauthorized_commit(self):
        runtime_guard.pre_compact(self.store, self.child_hook("PreCompact"))
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "result.txt").write_text("result\n", encoding="utf-8")
        self.git("add", "owned/result.txt")
        self.git("commit", "-m", "unauthorized child commit")

        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("HEAD", result["hookSpecificOutput"]["permissionDecisionReason"])

    def test_first_git_attestation_exact_base_mismatch_fast_stops(self):
        self.store.finalize(self.capsule["assignment_id"], {}, complete=False)
        wrong = self.make_capsule()
        wrong["root"]["base_commit"] = self.base[:12] + (
            "0" if self.base[12] != "0" else "1"
        ) + self.base[13:]
        wrong["capsule_sha256"] = capsule_sha256(wrong)
        self.store.stage(wrong, self.assignment)
        identity = runtime_guard.child_identity_from_hook(self.child_hook("SubagentStart"))
        self.store.claim(wrong["handoff_id"], identity)
        self.store.activate(wrong["handoff_id"])

        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("HEAD", result["hookSpecificOutput"]["permissionDecisionReason"])
        unresolved = json.loads(
            self.store.path("unresolved", wrong["assignment_id"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            unresolved["termination_evidence"]["classification"],
            "initial_authority_mismatch",
        )
        self.assertIsNone(unresolved["termination_evidence"]["disk_changed"])
        self.assertFalse(unresolved["termination_evidence"]["baseline_comparable"])
        self.assertEqual(runtime_guard.collect_git_snapshot(str(self.repository))["changed_paths"], [])

    def test_pre_tool_use_reads_actual_paths_and_blocks_scope_expansion(self):
        runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )
        runtime_guard.pre_compact(self.store, self.child_hook("PreCompact"))
        (self.repository / "outside.txt").write_text("unauthorized\n", encoding="utf-8")

        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("outside.txt", result["hookSpecificOutput"]["permissionDecisionReason"])

    def test_user_authorized_mutation_is_blocked_while_direct_write_is_unqualified(self):
        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="apply_patch")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "direct_write_qualified=false",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )
        self.assertFalse(self.store.path("active", self.capsule["assignment_id"]).exists())
        unresolved = json.loads(
            self.store.path("unresolved", self.capsule["assignment_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            unresolved["termination_evidence"]["classification"],
            "direct_write_qualification_missing",
        )
        self.assertTrue(
            unresolved["termination_evidence"]["mutation_blocked_before_execution"]
        )

    def test_read_only_child_cannot_restore_foreign_parent_dirty_bytes(self):
        self.replace_active_capsule(self.make_capsule(mutation_mode="read_only"))
        target = self.repository / "baseline.txt"
        target.write_text("parent-owned update\n", encoding="utf-8")
        before = hashlib.sha256(target.read_bytes()).hexdigest()

        result = runtime_guard.pre_tool_use(
            self.store,
            self.child_hook(
                "PreToolUse",
                tool_name="apply_patch",
                tool_input={
                    "patch": (
                        "*** Begin Patch\n"
                        "*** Update File: baseline.txt\n"
                        "@@\n"
                        "-parent-owned update\n"
                        "+baseline\n"
                        "*** End Patch"
                    )
                },
            ),
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("read-only allowlist", result["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(target.read_text(encoding="utf-8"), "parent-owned update\n")
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), before)
        self.assertIn(" M baseline.txt", self.git("status", "--short").stdout)
        unresolved = json.loads(
            self.store.path("unresolved", self.capsule["assignment_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            unresolved["termination_evidence"]["provenance_status"],
            "pre_attempt_disk_drift_unattributed",
        )
        self.assertEqual(
            unresolved["termination_evidence"]["attempted_tool_name"],
            "apply_patch",
        )

    def test_ambiguous_active_capsules_fail_closed(self):
        second = self.make_capsule()
        self.store.stage(second, self.assignment)
        identity = runtime_guard.child_identity_from_hook(self.child_hook("SubagentStart"))
        self.store.claim(second["handoff_id"], identity)
        self.store.activate(second["handoff_id"])

        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("found 2", result["hookSpecificOutput"]["permissionDecisionReason"])

    def test_subagent_stop_accepts_exact_disk_attestation_as_untrusted_report(self):
        runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "result.txt").write_text("result\n", encoding="utf-8")
        message = self.attestation()

        result = runtime_guard.subagent_stop(self.store, self.stop_hook(message))

        self.assertEqual(result, {})
        self.assertFalse(self.store.path("active", self.capsule["assignment_id"]).exists())
        self.assertTrue(self.store.path("reported", self.capsule["assignment_id"]).exists())

    def test_subagent_stop_mechanically_recomputes_inventory_count(self):
        item_ids = [f"test-{index:02d}" for index in range(18)]
        self.bind_closed_registry(item_ids)
        runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )
        drifted = {
            "registry_id": "test-id-inventory",
            "declared_count": 15,
            "item_ids": item_ids,
            "items_sha256": compatibility_state.registry_items_sha256(item_ids),
        }

        blocked = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook(self.attestation(inventory_summaries=[drifted])),
        )

        self.assertEqual(blocked["decision"], "block")
        self.assertIn("declared count", blocked["reason"])
        self.assertTrue(self.store.path("active", self.capsule["assignment_id"]).exists())

        corrected = dict(drifted, declared_count=len(item_ids))
        accepted = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook(self.attestation(inventory_summaries=[corrected])),
        )
        self.assertEqual(accepted, {})

    def test_subagent_stop_blocks_complete_claim_without_first_git_attestation(self):
        result = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook(self.attestation()),
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("no durable first Git attestation", result["reason"])

    def test_subagent_stop_blocks_slice_overclaim_shape(self):
        message = self.attestation()
        parsed = json.loads(message.split("\n", 1)[1].rsplit("\n", 1)[0])
        parsed["parent_task_complete"] = True
        overclaim = "BEGIN CODEX WORKER ATTESTATION\n" + json.dumps(parsed) + "\nEND CODEX WORKER ATTESTATION"

        result = runtime_guard.subagent_stop(self.store, self.stop_hook(overclaim))

        self.assertEqual(result["decision"], "block")
        self.assertIn("fields are not exact", result["reason"])

    def test_subagent_stop_blocks_complete_claim_using_test_only_provenance(self):
        message = self.attestation()
        parsed = json.loads(message.split("\n", 1)[1].rsplit("\n", 1)[0])
        parsed["authority_provenance"]["test_only_injection_used"] = True
        claim = (
            "BEGIN CODEX WORKER ATTESTATION\n"
            + json.dumps(parsed)
            + "\nEND CODEX WORKER ATTESTATION"
        )

        result = runtime_guard.subagent_stop(self.store, self.stop_hook(claim))

        self.assertEqual(result["decision"], "block")
        self.assertIn("inadmissible provenance claim", result["reason"])

    def test_subagent_stop_blocks_no_assignment_narrative_and_retains_active_state(self):
        result = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("I received no assignment and made no changes."),
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("INVALID_FINAL_WITHOUT_CONTRIBUTION", result["reason"])
        self.assertTrue(self.store.path("active", self.capsule["assignment_id"]).exists())

    def test_disk_mutation_without_durable_capsule_cannot_be_completed_by_narrative(self):
        self.store.finalize(self.capsule["assignment_id"], {}, complete=True)
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "long-run-result.txt").write_text(
            "real bytes after one-shot authority was lost\n",
            encoding="utf-8",
        )

        result = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("Implementation complete; hashes and tests passed."),
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("expected one active authority capsule", result["reason"])
        self.assertTrue((self.repository / "owned" / "long-run-result.txt").exists())
        self.assertFalse(self.store.path("consumed", self.capsule["assignment_id"]).exists())

    def test_return_context_loss_with_contribution_is_classified_separately(self):
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "result.txt").write_text("real contribution\n", encoding="utf-8")

        result = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("I no longer have the assignment, but the work is complete."),
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("RETURN_CONTEXT_LOSS_WITH_CONTRIBUTION", result["reason"])
        self.assertTrue(self.store.path("active", self.capsule["assignment_id"]).exists())

    def test_watchdog_classifies_prewrite_timeout_without_disk_change(self):
        deadline = dt.datetime.fromisoformat(self.capsule["pre_write_attestation_deadline"])

        terminated = runtime_guard.sweep_deadlines(
            self.store,
            now=deadline + dt.timedelta(seconds=1),
        )

        self.assertEqual(terminated[0]["classification"], "unresponsive_no_disk_change")
        self.assertFalse(terminated[0]["disk_changed"])
        self.assertTrue(self.store.path("unresolved", self.capsule["assignment_id"]).exists())

    def test_watchdog_distinguishes_prewrite_timeout_with_disk_change(self):
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "partial.txt").write_text("partial\n", encoding="utf-8")
        deadline = dt.datetime.fromisoformat(self.capsule["pre_write_attestation_deadline"])

        terminated = runtime_guard.sweep_deadlines(
            self.store,
            now=deadline + dt.timedelta(seconds=1),
        )

        self.assertEqual(
            terminated[0]["classification"],
            "unresponsive_with_disk_change_before_attestation",
        )
        self.assertTrue(terminated[0]["disk_changed"])

    def test_watchdog_classifies_attested_contribution_without_return(self):
        runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "result.txt").write_text("contribution\n", encoding="utf-8")
        expires = dt.datetime.fromisoformat(self.capsule["expires_at"])

        terminated = runtime_guard.sweep_deadlines(
            self.store,
            now=expires + dt.timedelta(seconds=1),
        )

        self.assertEqual(
            terminated[0]["classification"],
            "unresponsive_with_contribution",
        )
        self.assertTrue(terminated[0]["disk_changed"])

    def test_executable_watchdog_requests_parent_cancel_on_deadline(self):
        deadline = dt.datetime.fromisoformat(self.capsule["pre_write_attestation_deadline"])

        completed = subprocess.run(
            [
                sys.executable,
                str(WATCHDOG),
                "--state-directory",
                str(self.store.root),
                "--now",
                (deadline + dt.timedelta(seconds=1)).isoformat(),
                "--fail-on-termination",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertTrue(result["parent_cancel_required"])
        self.assertEqual(
            result["terminated"][0]["classification"],
            "unresponsive_no_disk_change",
        )

    def test_context_lost_attestation_returns_unresolved_evidence(self):
        message = self.attestation(
            context_lost=True,
            assigned_slice_complete=False,
        )

        result = runtime_guard.subagent_stop(self.store, self.stop_hook(message))

        self.assertEqual(result, {})
        self.assertFalse(self.store.path("active", self.capsule["assignment_id"]).exists())
        self.assertTrue(self.store.path("unresolved", self.capsule["assignment_id"]).exists())

    def test_subagent_stop_blocks_actual_head_and_status_mismatch(self):
        claimed_before_commit = self.attestation()
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "result.txt").write_text("result\n", encoding="utf-8")
        self.git("add", "owned/result.txt")
        self.git("commit", "-m", "unauthorized child commit")

        result = runtime_guard.subagent_stop(
            self.store, self.stop_hook(claimed_before_commit)
        )

        self.assertEqual(result["decision"], "block")
        self.assertTrue(
            "authority_violation" in result["reason"]
            or "attestation mismatch" in result["reason"]
        )

    def test_subagent_stop_blocks_unauthorized_staging(self):
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "result.txt").write_text("result\n", encoding="utf-8")
        self.git("add", "owned/result.txt")

        result = runtime_guard.subagent_stop(
            self.store, self.stop_hook(self.attestation(authority_violation=False))
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("authority_violation", result["reason"])

    def test_truthful_authority_violation_returns_unresolved_evidence(self):
        (self.repository / "outside.txt").write_text("unauthorized\n", encoding="utf-8")
        message = self.attestation(
            authority_violation=True,
            assigned_slice_complete=False,
        )

        result = runtime_guard.subagent_stop(self.store, self.stop_hook(message))

        self.assertEqual(result, {})
        self.assertTrue(self.store.path("unresolved", self.capsule["assignment_id"]).exists())

    def test_subagent_stop_blocks_path_hash_mismatch(self):
        (self.repository / "owned").mkdir()
        result_path = self.repository / "owned" / "result.txt"
        result_path.write_text("first\n", encoding="utf-8")
        stale_message = self.attestation()
        result_path.write_text("second\n", encoding="utf-8")

        result = runtime_guard.subagent_stop(self.store, self.stop_hook(stale_message))

        self.assertEqual(result["decision"], "block")
        self.assertIn("changed_paths", result["reason"])

    def test_subagent_stop_blocks_verification_contract_drift(self):
        result = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook(
                self.attestation(
                    verification=[{"command": "different verification", "exit_code": 0}]
                )
            ),
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("verification commands", result["reason"])

    def test_subagent_stop_blocks_complete_claim_with_failed_verification(self):
        result = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook(
                self.attestation(
                    verification=[{"command": "fixture verification", "exit_code": 1}]
                )
            ),
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("failed verification", result["reason"])

    def test_subagent_stop_blocks_out_of_scope_disk_change(self):
        outside = self.repository / "outside.txt"
        outside.write_text("unauthorized\n", encoding="utf-8")

        result = runtime_guard.subagent_stop(
            self.store, self.stop_hook(self.attestation())
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("authority_violation", result["reason"])

    def test_recovery_artifact_identity_does_not_expand_mutation_authority(self):
        artifact = self.repository / "reusable-evidence.json"
        artifact.write_text('{"owner":"parent"}\n', encoding="utf-8")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.capsule["preexisting_dirty"] = [
            {
                "path": "reusable-evidence.json",
                "status": "??",
                "kind": "file",
                "sha256": digest,
            }
        ]

        unchanged = runtime_guard.collect_git_snapshot(str(self.repository))
        self.assertEqual(
            runtime_guard._snapshot_authority_violations(unchanged, self.capsule), []
        )

        artifact.write_text('{"owner":"child"}\n', encoding="utf-8")
        changed = runtime_guard.collect_git_snapshot(str(self.repository))
        self.assertIn(
            "final disk contains unauthorized change: reusable-evidence.json",
            runtime_guard._snapshot_authority_violations(changed, self.capsule),
        )


if __name__ == "__main__":
    unittest.main()
