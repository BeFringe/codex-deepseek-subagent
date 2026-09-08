import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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

MIGRATION_HANDOFF_VERSION = runtime_guard.LIVE_HOOK_SCHEMA_RUNTIME_ROLES[
    "migration_handoff_runtime"
]
PRIOR_SIGNED_VERSION = runtime_guard.LIVE_HOOK_SCHEMA_RUNTIME_ROLES[
    "prior_signed_runtime"
]
CURRENT_SIGNED_VERSION = runtime_guard.LIVE_HOOK_SCHEMA_RUNTIME_ROLES[
    "current_signed_runtime"
]


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
            "parent_thread_id": "runtime-session",
            "timestamp": "2026-08-12T00:00:00Z",
            "cwd": str(self.repository),
            "originator": "fixture",
            "cli_version": MIGRATION_HANDOFF_VERSION,
            "source": {
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": "runtime-session",
                        "depth": 1,
                        "agent_path": "/root/bounded_task",
                        "agent_nickname": None,
                        "agent_role": "fixture_worker",
                    }
                }
            },
            "agent_role": "fixture_worker",
            "agent_path": "/root/bounded_task",
            "model_provider": "fixture-provider",
        }
        spawn = payload["source"]["subagent"]["thread_spawn"]
        for field in (
            "parent_thread_id",
            "agent_path",
            "agent_nickname",
            "agent_role",
            "depth",
        ):
            if field in overrides:
                spawn[field] = overrides.pop(field)
                if field in {"parent_thread_id", "agent_path", "agent_role"}:
                    payload[field] = spawn[field]
        payload.update(overrides)
        item = {
            "timestamp": "2026-08-12T00:00:00.070Z",
            "type": "session_meta",
            "payload": payload,
        }
        self.child_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

    def write_parent_session_meta(self, **overrides):
        payload = {
            "session_id": "runtime-session",
            "id": "runtime-session",
            "timestamp": "2026-08-12T00:00:00Z",
            "cwd": str(self.repository),
            "originator": "fixture",
            "cli_version": MIGRATION_HANDOFF_VERSION,
            "source": "vscode",
            "model_provider": "fixture-provider",
        }
        payload.update(overrides)
        item = {
            "timestamp": "2026-08-12T00:00:00.070Z",
            "type": "session_meta",
            "payload": payload,
        }
        self.parent_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

    def make_capsule(self, *, mutation_mode="write"):
        now = dt.datetime.now(dt.timezone.utc)
        read_only = mutation_mode == "read_only"
        value = {
            "schema": 2,
            "assignment_id": str(uuid.uuid4()),
            "handoff_id": str(uuid.uuid4()),
            "runtime_session_id": "runtime-session",
            "parent_thread_id": "runtime-session",
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
            "parent_recorded_user_write_intent": "deny" if read_only else "allow",
            "trusted_host_user_write_consent": {
                "schema": 1,
                "status": "unavailable",
                "source": None,
                "receipt_sha256": None,
            },
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
        self.assertEqual(identity["parent_thread_id"], "runtime-session")
        self.assertEqual(identity["agent_type"], "fixture_worker")
        self.assertEqual(identity["canonical_agent_path"], "/root/bounded_task")
        self.assertEqual(identity["codex_version"], MIGRATION_HANDOFF_VERSION)

    def test_previous_signed_codex_version_is_accepted_and_bound(self):
        self.write_session_meta(cli_version=PRIOR_SIGNED_VERSION)
        child_identity = runtime_guard.child_identity_from_hook(
            self.child_hook("SubagentStart")
        )
        self.write_parent_session_meta(cli_version=PRIOR_SIGNED_VERSION)
        stop_identity = runtime_guard.child_identity_from_stop(
            self.stop_hook(self.attestation())
        )

        self.assertEqual(child_identity["codex_version"], PRIOR_SIGNED_VERSION)
        self.assertEqual(stop_identity["codex_version"], PRIOR_SIGNED_VERSION)

    def test_current_signed_codex_version_is_accepted_and_bound(self):
        self.write_session_meta(cli_version=CURRENT_SIGNED_VERSION)
        child_identity = runtime_guard.child_identity_from_hook(
            self.child_hook("SubagentStart")
        )
        self.write_parent_session_meta(cli_version=CURRENT_SIGNED_VERSION)
        stop_identity = runtime_guard.child_identity_from_stop(
            self.stop_hook(self.attestation())
        )

        self.assertEqual(child_identity["codex_version"], CURRENT_SIGNED_VERSION)
        self.assertEqual(stop_identity["codex_version"], CURRENT_SIGNED_VERSION)

    def test_live_hook_schema_versions_match_semantic_evidence_roles(self):
        index = json.loads(
            (REPO / "probes" / "codex-runtime-evidence-index.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {
            role: index["runtime_roles"][role]["codex_version"]
            for role in index["live_hook_schema_roles"]
        }

        self.assertEqual(runtime_guard.LIVE_HOOK_SCHEMA_RUNTIME_ROLES, expected)

    def test_stop_rejects_parent_child_codex_version_mismatch(self):
        self.write_session_meta(cli_version=PRIOR_SIGNED_VERSION)

        with self.assertRaisesRegex(
            compatibility_state.IdentityMismatch,
            "parent and child Codex versions do not match",
        ):
            runtime_guard.child_identity_from_stop(self.stop_hook(self.attestation()))

    def test_root_parent_meta_needs_no_child_role_or_agent_path(self):
        identity = runtime_guard.child_identity_from_stop(
            self.stop_hook(self.attestation())
        )

        self.assertEqual(identity["parent_thread_id"], "runtime-session")

    def test_runtime_parser_rejects_source_duplicate_mismatch(self):
        item = json.loads(self.child_transcript.read_text(encoding="utf-8"))
        item["payload"]["source"]["subagent"]["thread_spawn"]["agent_path"] = (
            "/root/forged"
        )
        self.child_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(
            compatibility_state.IdentityMismatch,
            "agent_path disagrees with thread-spawn source",
        ):
            runtime_guard.read_session_meta(str(self.child_transcript))

    def test_runtime_parser_rejects_cli_version_drift(self):
        item = json.loads(self.child_transcript.read_text(encoding="utf-8"))
        item["payload"]["cli_version"] = "0.148.0-alpha.10"
        self.child_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(
            compatibility_state.IdentityMismatch,
            "cli_version is not in the pinned live set",
        ):
            runtime_guard.read_session_meta(str(self.child_transcript))

    def test_runtime_parser_rejects_unpinned_stable_version(self):
        item = json.loads(self.child_transcript.read_text(encoding="utf-8"))
        item["payload"]["cli_version"] = "0.153.5"
        self.child_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(
            compatibility_state.IdentityMismatch,
            "cli_version is not in the pinned live set",
        ):
            runtime_guard.read_session_meta(str(self.child_transcript))

    def test_supported_codex_version_drift_does_not_match_active_binding(self):
        self.write_session_meta(cli_version=PRIOR_SIGNED_VERSION)

        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="view_image")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "expected one active authority capsule, found 0",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_runtime_parser_rejects_payload_time_after_record(self):
        item = json.loads(self.child_transcript.read_text(encoding="utf-8"))
        item["payload"]["timestamp"] = "2026-08-12T00:00:00.071Z"
        self.child_transcript.write_text(json.dumps(item) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(
            compatibility_state.IdentityMismatch,
            "payload timestamp is later",
        ):
            runtime_guard.read_session_meta(str(self.child_transcript))

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

    def test_final_attestation_seed_is_mechanical_and_non_authorizing(self):
        seed = runtime_guard.final_attestation_seed(self.capsule, 3)

        self.assertEqual(
            set(seed),
            {
                "schema",
                "assignment_id",
                "handoff_id",
                "capsule_sha256",
                "compact_invariant_sha256",
                "authority_provenance_policy_sha256",
                "canonical_agent_path",
                "recovery_count",
                "verification_commands",
            },
        )
        self.assertEqual(seed["recovery_count"], 3)
        self.assertEqual(seed["verification_commands"], self.capsule["verification"])
        self.assertEqual(
            seed["compact_invariant_sha256"],
            compatibility_state.compact_invariant_sha256(self.capsule),
        )
        self.assertEqual(
            seed["authority_provenance_policy_sha256"],
            compatibility_state.provenance_policy_sha256(self.capsule),
        )
        for forbidden in (
            "worker_claimed_origin",
            "test_only_injection_used",
            "derivation_receipt_sha256",
            "root",
            "branch",
            "head",
            "git_status_short",
            "changed_paths",
            "verification",
            "authority_violation",
            "assigned_slice_complete",
        ):
            self.assertNotIn(forbidden, seed)

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

    def test_precompact_rejects_disk_scope_drift_before_epoch_increment(self):
        (self.repository / "outside.txt").write_text("unauthorized\n", encoding="utf-8")

        with self.assertRaisesRegex(
            compatibility_state.AuthorityViolation,
            "outside.txt",
        ):
            runtime_guard.pre_compact(self.store, self.child_hook("PreCompact"))

        active = self.store.path("active", self.capsule["assignment_id"])
        envelope = json.loads(active.read_text(encoding="utf-8"))
        self.assertEqual(envelope["runtime"]["recovery_count"], 0)

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

    def test_parent_recorded_intent_does_not_bypass_write_authority_gates(self):
        result = runtime_guard.pre_tool_use(
            self.store, self.child_hook("PreToolUse", tool_name="apply_patch")
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "direct_write_qualified=false",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )
        self.assertIn(
            "trusted host user consent is unavailable",
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
            "write_authority_gates_missing",
        )
        self.assertEqual(
            unresolved["termination_evidence"]["blocking_gates"],
            [
                "trusted_host_user_write_consent",
                "direct_write_qualification",
                "live_mutation_mediation",
            ],
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

    def test_exact_sandbox_probe_consumes_authority_once_before_runtime_execution(self):
        prior_assignment_id = self.capsule["assignment_id"]
        capsule = self.make_capsule(mutation_mode="read_only")
        capsule["verification"] = [
            runtime_guard.QUALIFICATION_SANDBOX_PROBE_VERIFICATION
        ]
        capsule["capsule_sha256"] = capsule_sha256(capsule)
        self.replace_active_capsule(capsule)
        self.store.path("unresolved", prior_assignment_id).unlink()
        probe_root = self.root / "sandbox-probe-root"
        probe_root.mkdir()
        probe_root = probe_root.resolve()
        target = probe_root / "one-shot.txt"
        hook = self.child_hook(
            "PreToolUse",
            tool_name="Bash",
            tool_input={"command": f"/usr/bin/touch {target}"},
        )

        with mock.patch.object(
            runtime_guard, "QUALIFICATION_SANDBOX_PROBE_ROOT", probe_root
        ):
            allowed = runtime_guard.pre_tool_use(
                self.store,
                hook,
                qualification_sandbox_probes={"bounded_task": target},
            )
            repeated = runtime_guard.pre_tool_use(
                self.store,
                hook,
                qualification_sandbox_probes={"bounded_task": target},
            )

        self.assertEqual(allowed, {})
        self.assertEqual(repeated["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertFalse(self.store.path("active", self.capsule["assignment_id"]).exists())
        unresolved_path = self.store.path("unresolved", self.capsule["assignment_id"])
        unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
        evidence = unresolved["termination_evidence"]
        self.assertEqual(evidence["reason"], "sandbox_probe_dispatched")
        self.assertEqual(
            evidence["classification"], "qualification_sandbox_probe_dispatched"
        )
        self.assertFalse(evidence["disk_changed"])
        self.assertFalse(evidence["mutation_blocked_before_execution"])
        self.assertEqual(evidence["sandbox_probe_target"], str(target))
        self.assertFalse(target.exists())

        stopped = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("sandbox probe terminal narrative"),
        )
        self.assertEqual(stopped, {})
        self.assertTrue(unresolved_path.exists())

    def test_sandbox_probe_wrong_command_falls_back_to_read_only_denial(self):
        prior_assignment_id = self.capsule["assignment_id"]
        capsule = self.make_capsule(mutation_mode="read_only")
        capsule["verification"] = [
            runtime_guard.QUALIFICATION_SANDBOX_PROBE_VERIFICATION
        ]
        capsule["capsule_sha256"] = capsule_sha256(capsule)
        self.replace_active_capsule(capsule)
        self.store.path("unresolved", prior_assignment_id).unlink()
        probe_root = self.root / "sandbox-probe-root"
        probe_root.mkdir()
        probe_root = probe_root.resolve()
        target = probe_root / "one-shot.txt"

        with mock.patch.object(
            runtime_guard, "QUALIFICATION_SANDBOX_PROBE_ROOT", probe_root
        ):
            denied = runtime_guard.pre_tool_use(
                self.store,
                self.child_hook(
                    "PreToolUse",
                    tool_name="Bash",
                    tool_input={"command": f"/usr/bin/touch {target}.different"},
                ),
                qualification_sandbox_probes={"bounded_task": target},
            )

        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        unresolved = json.loads(
            self.store.path("unresolved", self.capsule["assignment_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            unresolved["termination_evidence"]["reason"],
            "read_only_mutation_attempt",
        )
        self.assertTrue(
            unresolved["termination_evidence"]["mutation_blocked_before_execution"]
        )
        self.assertFalse(target.exists())

    def test_subagent_stop_acknowledges_exact_guard_terminated_unresolved(self):
        prior_assignment_id = self.capsule["assignment_id"]
        self.replace_active_capsule(self.make_capsule(mutation_mode="read_only"))
        self.store.path("unresolved", prior_assignment_id).unlink()
        blocked = runtime_guard.pre_tool_use(
            self.store,
            self.child_hook(
                "PreToolUse",
                tool_name="apply_patch",
                tool_input={"patch": "*** Begin Patch\n*** End Patch"},
            ),
        )
        unresolved_path = self.store.path(
            "unresolved", self.capsule["assignment_id"]
        )
        before = hashlib.sha256(unresolved_path.read_bytes()).hexdigest()

        stopped = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("terminal unresolved contribution narrative"),
        )

        self.assertEqual(
            blocked["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(stopped, {})
        self.assertEqual(
            hashlib.sha256(unresolved_path.read_bytes()).hexdigest(), before
        )
        self.assertFalse(
            self.store.path("reported", self.capsule["assignment_id"]).exists()
        )
        self.assertFalse(
            self.store.path("consumed", self.capsule["assignment_id"]).exists()
        )

    def test_subagent_stop_blocks_pre_write_timeout_until_parent_cancel(self):
        assignment_id = self.capsule["assignment_id"]
        deadline = dt.datetime.fromisoformat(
            self.capsule["pre_write_attestation_deadline"]
        )
        terminated = runtime_guard.sweep_deadlines(
            self.store,
            now=deadline + dt.timedelta(microseconds=1),
            assignment_ids={assignment_id},
        )
        unresolved_path = self.store.path("unresolved", assignment_id)
        before = hashlib.sha256(unresolved_path.read_bytes()).hexdigest()

        stopped = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("WAITING_FOR_PARENT_INTERRUPT"),
        )

        self.assertEqual(terminated[0]["reason"], "pre_write_attestation_timeout")
        self.assertEqual(stopped["decision"], "block")
        self.assertIn("TASK.PARENT_CANCEL_REQUIRED", stopped["reason"])
        self.assertIn("reason=pre_write_attestation_timeout", stopped["reason"])
        self.assertIn("native interrupt or cancel", stopped["reason"])
        self.assertIn("does not authorize ownership handover", stopped["reason"])
        self.assertEqual(hashlib.sha256(unresolved_path.read_bytes()).hexdigest(), before)

    def test_subagent_stop_blocks_assignment_timeout_until_parent_cancel(self):
        assignment_id = self.capsule["assignment_id"]
        created_at = dt.datetime.fromisoformat(self.capsule["created_at"])
        allowed = runtime_guard.pre_tool_use(
            self.store,
            self.child_hook("PreToolUse", tool_name="list_agents"),
            now=created_at + dt.timedelta(seconds=1),
        )
        expires_at = dt.datetime.fromisoformat(self.capsule["expires_at"])
        terminated = runtime_guard.sweep_deadlines(
            self.store,
            now=expires_at + dt.timedelta(microseconds=1),
            assignment_ids={assignment_id},
        )

        stopped = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("WAITING_FOR_PARENT_INTERRUPT"),
        )

        self.assertIn("additionalContext", allowed["hookSpecificOutput"])
        self.assertEqual(terminated[0]["reason"], "assignment_timeout")
        self.assertEqual(stopped["decision"], "block")
        self.assertIn("TASK.PARENT_CANCEL_REQUIRED", stopped["reason"])
        self.assertIn("reason=assignment_timeout", stopped["reason"])
        self.assertTrue(self.store.path("unresolved", assignment_id).exists())
        self.assertFalse(self.store.path("reported", assignment_id).exists())

    def test_subagent_stop_rejects_forged_terminal_unresolved_reason(self):
        prior_assignment_id = self.capsule["assignment_id"]
        self.replace_active_capsule(self.make_capsule(mutation_mode="read_only"))
        self.store.path("unresolved", prior_assignment_id).unlink()
        runtime_guard.pre_tool_use(
            self.store,
            self.child_hook("PreToolUse", tool_name="apply_patch"),
        )
        unresolved_path = self.store.path(
            "unresolved", self.capsule["assignment_id"]
        )
        unresolved = json.loads(unresolved_path.read_text(encoding="utf-8"))
        unresolved["termination_evidence"]["reason"] = "caller_forged_reason"
        unresolved_path.write_text(json.dumps(unresolved), encoding="utf-8")

        stopped = runtime_guard.subagent_stop(
            self.store,
            self.stop_hook("terminal unresolved contribution narrative"),
        )

        self.assertEqual(stopped["decision"], "block")
        self.assertIn("expected one active authority capsule", stopped["reason"])

    def test_exact_candidate_namespace_list_agents_alias_is_read_only(self):
        result = runtime_guard.pre_tool_use(
            self.store,
            self.child_hook(
                "PreToolUse",
                tool_name="g4_assignmentlist_agents",
                tool_input={},
            ),
        )

        self.assertIn("additionalContext", result["hookSpecificOutput"])
        self.assertTrue(self.store.path("active", self.capsule["assignment_id"]).exists())

    def test_candidate_namespace_alias_does_not_strip_arbitrary_prefixes(self):
        result = runtime_guard.pre_tool_use(
            self.store,
            self.child_hook(
                "PreToolUse",
                tool_name="g4_assignmentlist_agents_extra",
                tool_input={},
            ),
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertFalse(self.store.path("active", self.capsule["assignment_id"]).exists())
        unresolved = json.loads(
            self.store.path("unresolved", self.capsule["assignment_id"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            unresolved["termination_evidence"]["attempted_tool_name"],
            "g4_assignmentlist_agents_extra",
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

    def test_final_attestation_field_error_names_only_schema_drift(self):
        message = self.attestation()
        attestation = json.loads(message.split("\n", 1)[1].rsplit("\n", 1)[0])
        attestation["schema"] = 1

        with self.assertRaisesRegex(
            runtime_guard.GuardError,
            r'fields are not exact: missing=\[\] unexpected=\["schema"\]',
        ):
            runtime_guard.parse_attestation(
                "BEGIN CODEX WORKER ATTESTATION\n"
                + json.dumps(attestation)
                + "\nEND CODEX WORKER ATTESTATION"
            )

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

    def test_watchdog_exact_selector_ignores_unrelated_invalid_root(self):
        other = self.make_capsule(mutation_mode="read_only")
        other["requested_task_name"] = "stale_task"
        other["canonical_agent_path"] = "/root/stale_task"
        other["root"]["path"] = str(self.root / "missing-repository")
        other["capsule_sha256"] = capsule_sha256(other)
        self.store.stage(other, self.assignment)
        self.store.claim(
            other["handoff_id"],
            {
                "runtime_session_id": "runtime-session",
                "child_thread_id": "stale-child",
                "agent_id": "stale-child",
                "parent_thread_id": "runtime-session",
                "agent_type": "fixture_worker",
                "canonical_agent_path": "/root/stale_task",
                "codex_version": MIGRATION_HANDOFF_VERSION,
            },
        )
        self.store.activate(other["handoff_id"])
        deadline = dt.datetime.fromisoformat(
            self.capsule["pre_write_attestation_deadline"]
        )

        terminated = runtime_guard.sweep_deadlines(
            self.store,
            now=deadline + dt.timedelta(seconds=1),
            assignment_ids={self.capsule["assignment_id"]},
        )

        self.assertEqual(
            [item["assignment_id"] for item in terminated],
            [self.capsule["assignment_id"]],
        )
        self.assertTrue(
            self.store.path("active", other["assignment_id"]).exists()
        )

    def test_watchdog_exact_selector_validates_before_mutation(self):
        deadline = dt.datetime.fromisoformat(
            self.capsule["pre_write_attestation_deadline"]
        )
        missing = str(uuid.uuid4())

        with self.assertRaisesRegex(
            runtime_guard.GuardError, "requested active assignment not found"
        ):
            runtime_guard.sweep_deadlines(
                self.store,
                now=deadline + dt.timedelta(seconds=1),
                assignment_ids={self.capsule["assignment_id"], missing},
            )

        self.assertTrue(
            self.store.path("active", self.capsule["assignment_id"]).exists()
        )

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
                "--assignment-id",
                self.capsule["assignment_id"],
                "--fail-on-termination",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(result["selection"], "exact")
        self.assertEqual(
            result["requested_assignment_ids"], [self.capsule["assignment_id"]]
        )
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
