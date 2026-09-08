import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid


MODULE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "compatibility_state.py"
SPEC = importlib.util.spec_from_file_location("compatibility_state", MODULE_PATH)
compatibility_state = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(compatibility_state)


AuthorityViolation = compatibility_state.AuthorityViolation
CorruptState = compatibility_state.CorruptState
IdentityMismatch = compatibility_state.IdentityMismatch
StateStore = compatibility_state.StateStore
capsule_sha256 = compatibility_state.capsule_sha256
sha256_bytes = compatibility_state.sha256_bytes
git_snapshot_sha256 = compatibility_state.git_snapshot_sha256
validate_capsule = compatibility_state.validate_capsule


def capsule(assignment, **overrides):
    now = dt.datetime.now(dt.timezone.utc)
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
        "canonical_agent_path": None,
        "root": {
            "path": "/workspace/repository",
            "branch": "main",
            "base_commit": "a" * 64,
            "allow_descendant_head": False,
            "base_index_changed": False,
            "base_git_status_short": "",
        },
        "capture_preflight": None,
        "capture_snapshot_sha256": "e" * 64,
        "assignment_mutation_mode": "write",
        "parent_recorded_user_write_intent": "allow",
        "trusted_host_user_write_consent": {
            "schema": 1,
            "status": "unavailable",
            "source": None,
            "receipt_sha256": None,
        },
        "owned_paths": ["owned"],
        "excluded_paths": ["owned/excluded"],
        "git_authority": {
            "stage": False,
            "commit": False,
            "branch": False,
            "push": False,
        },
        "ownership_handover": [],
        "stop_condition": "assigned slice completion only",
        "verification": ["run the provider-free fixture"],
        "authority_provenance": {
            "authoritative_input_owners": ["fixture.owner"],
            "authoritative_input_roots": ["inputs"],
            "forbidden_caller_supplied_derived_facts": ["oracle_obligations"],
            "test_only_injection_seams": ["fixture.inject_oracle"],
            "required_derivation_boundary": "fixture.owner.derive",
        },
        "execution_contract": {
            "posture": "direct_write_unqualified",
            "review_range": None,
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
            "capsule_feasibility_attestation": {
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
        "preexisting_dirty": [
            {
                "path": "owned/user.txt",
                "status": " M",
                "kind": "file",
                "sha256": "b" * 64,
            }
        ],
        "assignment_sha256": sha256_bytes(assignment.encode("utf-8")),
        "created_at": now.isoformat(),
        "pre_write_attestation_deadline": (now + dt.timedelta(seconds=30)).isoformat(),
        "expires_at": (now + dt.timedelta(minutes=5)).isoformat(),
    }
    value.update(overrides)
    value["capsule_sha256"] = capsule_sha256(value)
    return value


def identity(**overrides):
    value = {
        "runtime_session_id": "runtime-session",
        "child_thread_id": "child-thread",
        "agent_id": "child-thread",
        "parent_thread_id": "parent-thread",
        "agent_type": "fixture_worker",
        "canonical_agent_path": "/root/bounded_task",
    }
    value.update(overrides)
    return value


class CompatibilityStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temporary_directory.name) / "state")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def activate(self, assignment="implement the bounded slice"):
        value = capsule(assignment)
        self.store.stage(value, assignment)
        self.store.claim(value["handoff_id"], identity())
        return value, self.store.activate(value["handoff_id"])

    def test_capsule_hash_is_canonical_and_tamper_evident(self):
        assignment = "bounded task"
        value = capsule(assignment)
        reordered = dict(reversed(list(value.items())))

        self.assertEqual(capsule_sha256(value), capsule_sha256(reordered))
        validate_capsule(reordered, assignment)

        reordered["git_authority"] = dict(reordered["git_authority"], commit=True)
        with self.assertRaisesRegex(CorruptState, "capsule_sha256"):
            validate_capsule(reordered, assignment)

    def test_parent_intent_cannot_fabricate_trusted_host_consent(self):
        assignment = "bounded task"
        value = capsule(assignment)
        value["trusted_host_user_write_consent"] = {
            "schema": 1,
            "status": "verified",
            "source": "parent_claim",
            "receipt_sha256": "f" * 64,
        }
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(CorruptState, "unavailable in isolated schema 2"):
            validate_capsule(value, assignment)

    def test_compact_invariant_preserves_diagnostics_and_non_authorizing_baselines(self):
        assignment = "strict read-only review"
        execution = {
            "posture": "strict_read_only",
            "review_range": {"base_oid": "a" * 64, "head_oid": "a" * 64},
            "required_invariants": ["failure code remains stable"],
            "diagnostics": {
                "stable_failure_codes": ["OWNER.QUERY_FAILED"],
                "known_true_failure_codes": ["OWNER.QUERY_FAILED"],
                "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED",
                "allow_literal_expensive_rerun": False,
                "allowed_failure_code_localities": {
                    "OWNER.QUERY_FAILED": ["overall", "per_item"]
                },
            },
            "proven_input_baselines": [
                {
                    "baseline_id": "replay-v1",
                    "owner": "fixture.owner",
                    "manifest_path": "inputs/replay.json",
                    "sha256": "c" * 64,
                    "proven_failure_code": "OWNER.QUERY_FAILED",
                    "non_authorizing": True,
                    "replay_policy": "reuse_without_authority_expansion",
                }
            ],
            "termination_contract": {"catalog_closed": True, "boundary_catalog": []},
            "evidence_binding": None,
            "review_continuation": None,
            "closed_registries": [],
            "relation_contracts": [],
            "capsule_feasibility_attestation": None,
        }
        value = capsule(
            assignment,
            assignment_mutation_mode="read_only",
            parent_recorded_user_write_intent="deny",
            trusted_host_user_write_consent={
                "schema": 1,
                "status": "unavailable",
                "source": None,
                "receipt_sha256": None,
            },
            owned_paths=[],
            excluded_paths=[],
            preexisting_dirty=[],
            execution_contract=execution,
        )
        value["capsule_sha256"] = capsule_sha256(value)

        validate_capsule(value, assignment)
        invariant = compatibility_state.compact_invariant(value)

        self.assertEqual(invariant["execution_contract"], execution)
        self.assertEqual(invariant["assignment_mutation_mode"], "read_only")
        self.assertEqual(invariant["parent_recorded_user_write_intent"], "deny")
        self.assertEqual(
            invariant["trusted_host_user_write_consent"],
            {
                "schema": 1,
                "status": "unavailable",
                "source": None,
                "receipt_sha256": None,
            },
        )
        self.assertTrue(
            invariant["execution_contract"]["proven_input_baselines"][0][
                "non_authorizing"
            ]
        )

    def test_strict_read_only_contract_rejects_owned_paths_or_authorizing_baseline(self):
        assignment = "reject authority smuggling"
        value = capsule(assignment)
        value["assignment_mutation_mode"] = "read_only"
        value["parent_recorded_user_write_intent"] = "deny"
        value["execution_contract"] = {
            "posture": "strict_read_only",
            "review_range": {"base_oid": "a" * 64, "head_oid": "a" * 64},
            "required_invariants": [],
            "diagnostics": {
                "stable_failure_codes": ["OWNER.FAILURE"],
                "known_true_failure_codes": ["OWNER.FAILURE"],
                "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED",
                "allow_literal_expensive_rerun": False,
                "allowed_failure_code_localities": {
                    "OWNER.FAILURE": ["overall"]
                },
            },
            "proven_input_baselines": [],
            "termination_contract": {"catalog_closed": True, "boundary_catalog": []},
            "evidence_binding": None,
            "review_continuation": None,
            "closed_registries": [],
            "relation_contracts": [],
            "capsule_feasibility_attestation": None,
        }
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(CorruptState, "cannot claim path ownership"):
            validate_capsule(value, assignment)

        value["owned_paths"] = []
        value["excluded_paths"] = []
        value["execution_contract"]["proven_input_baselines"] = [
            {
                "baseline_id": "replay-v1",
                "owner": "fixture.owner",
                "manifest_path": "inputs/replay.json",
                "sha256": "c" * 64,
                "proven_failure_code": "OWNER.FAILURE",
                "non_authorizing": False,
                "replay_policy": "reuse_without_authority_expansion",
            }
        ]
        value["capsule_sha256"] = capsule_sha256(value)
        with self.assertRaisesRegex(CorruptState, "explicitly non-authorizing"):
            validate_capsule(value, assignment)

    def test_review_continuation_freezes_base_tip_findings_and_evidence_identity(self):
        assignment = "review only the corrected immutable tip"
        prior_assignment_id = str(uuid.uuid4())
        value = capsule(
            assignment,
            assignment_mutation_mode="read_only",
            parent_recorded_user_write_intent="deny",
            trusted_host_user_write_consent={
                "schema": 1,
                "status": "unavailable",
                "source": None,
                "receipt_sha256": None,
            },
            owned_paths=[],
            excluded_paths=[],
            preexisting_dirty=[],
        )
        execution = value["execution_contract"]
        execution.update(
            {
                "posture": "strict_read_only",
                "capsule_feasibility_attestation": None,
                "review_range": {"base_oid": "9" * 64, "head_oid": "a" * 64},
                "required_invariants": ["prior P1 findings receive a fresh adjudication"],
                "review_continuation": {
                    "prior_assignment_id": prior_assignment_id,
                    "frozen_cumulative_base_oid": "9" * 64,
                    "prior_review_base_oid": "9" * 64,
                    "prior_review_tip_oid": "7" * 64,
                    "corrected_tip_oid": "a" * 64,
                    "prior_findings_sha256": "d" * 64,
                    "unresolved_finding_ids": ["P1-1", "P1-2"],
                    "exact_narrowed_objective": "recheck only P1-1 and P1-2",
                    "require_clean_worktree": True,
                },
                "evidence_binding": {
                    "executed_root": "/workspace/repository",
                    "hashed_root": "/workspace/repository",
                    "source_identity": {"kind": "git_commit", "value": "a" * 64},
                    "canonical_output": "evidence/review.json",
                    "no_follow_dirfd_walk": True,
                    "terminal_regular_file_reproof": True,
                    "preflight_before_expensive_execution": True,
                },
            }
        )
        value["stop_condition"] = "recheck only P1-1 and P1-2; no broader completion claim"
        value["capsule_sha256"] = capsule_sha256(value)

        validate_capsule(value, assignment)

        execution["review_continuation"]["corrected_tip_oid"] = "8" * 64
        value["capsule_sha256"] = capsule_sha256(value)
        with self.assertRaisesRegex(CorruptState, "tip does not match"):
            validate_capsule(value, assignment)

    def test_crash_catalog_rejects_exception_as_process_death_primitive(self):
        assignment = "reject finally-unwinding crash claim"
        value = capsule(assignment)
        value["execution_contract"]["termination_contract"] = {
            "catalog_closed": True,
            "boundary_catalog": [
                {
                    "boundary_id": "before-journal",
                    "seam": "owner.transition",
                    "ordinal": 0,
                    "termination_primitive": "KeyboardInterrupt",
                    "expected_durable_resolution": "UNJOURNALED",
                }
            ],
        }
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(CorruptState, "os._exit"):
            validate_capsule(value, assignment)

    def test_relation_contract_freezes_schema_cardinality_absence_and_terminal_exception(self):
        assignment = "validate closed owner relation"
        value = capsule(assignment)
        value["execution_contract"]["relation_contracts"] = [
            {
                "relation_id": "owner-handoff",
                "owner_schema_fields": ["owner_id", "terminal_state"],
                "handoff_schema_fields": ["handoff_id", "owner_id", "terminal_state"],
                "owner_id_field": "owner_id",
                "handoff_id_field": "handoff_id",
                "handoff_owner_id_field": "owner_id",
                "terminal_state_field": "terminal_state",
                "referential_cardinality": "exactly_one_to_one_nonterminal",
                "absence_semantics": "missing_or_orphan_relation_is_error",
                "allowed_terminal_absence": "tombstone_or_clear_only",
            }
        ]
        value["capsule_sha256"] = capsule_sha256(value)

        validate_capsule(value, assignment)

        value["execution_contract"]["relation_contracts"][0][
            "absence_semantics"
        ] = "missing_is_ok"
        value["capsule_sha256"] = capsule_sha256(value)
        with self.assertRaisesRegex(CorruptState, "absence semantics"):
            validate_capsule(value, assignment)

    def test_direct_write_feasibility_decision_must_match_probe_budget_and_assumptions(self):
        assignment = "implement the bounded assigned slice"
        value = capsule(assignment)
        feasibility = value["execution_contract"]["capsule_feasibility_attestation"]
        feasibility["counterexample_probe"]["counterexample_found"] = True
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(CorruptState, "contradicts executable evidence"):
            validate_capsule(value, assignment)

        feasibility["counterexample_probe"]["counterexample_found"] = False
        feasibility["unresolved_assumptions"] = [
            {"assumption": "finite registry is complete", "blocking": True}
        ]
        value["capsule_sha256"] = capsule_sha256(value)
        with self.assertRaisesRegex(CorruptState, "contradicts executable evidence"):
            validate_capsule(value, assignment)

    def test_capsule_rejects_budget_and_mechanism_cardinality_domain_drift(self):
        assignment = "implement only under the frozen invocation budget"
        value = capsule(assignment)
        bounded = value["execution_contract"]["capsule_feasibility_attestation"][
            "bounded_completion"
        ]
        bounded["mechanism_measurement"]["cardinality_domain"] = "object-identity"
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(CorruptState, "budget-domain evidence"):
            validate_capsule(value, assignment)

    def test_capsule_rejects_forged_equivalence_fanout_as_satisfying(self):
        assignment = "implement only with owner-derived equivalence"
        value = capsule(assignment)
        bounded = value["execution_contract"]["capsule_feasibility_attestation"][
            "bounded_completion"
        ]
        bounded["equivalence_compression"] = {
            "authoritative_owner_id": "fixture.owner",
            "equivalence_rule": "owner semantic equality",
            "grouping_origin": "caller_supplied",
            "class_cardinality_domain": "fixture-object",
            "identity_cardinality_domain": "object-identity",
            "evaluated_class_count": 3,
            "proven_identity_count": 30,
            "fanout_identity_count": 30,
            "evidence_sha256": "5" * 64,
        }
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(CorruptState, "budget-domain evidence"):
            validate_capsule(value, assignment)

    def test_keyed_pending_assignments_can_be_staged_concurrently(self):
        assignments = [f"assignment {index}" for index in range(8)]
        capsules = [capsule(assignment) for assignment in assignments]

        with ThreadPoolExecutor(max_workers=4) as executor:
            paths = list(executor.map(lambda item: self.store.stage(*item), zip(capsules, assignments)))

        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 8)

    def test_identity_mismatch_preserves_valid_pending_assignment(self):
        assignment = "preserve on wrong parent"
        value = capsule(assignment)
        pending = self.store.stage(value, assignment)

        with self.assertRaises(IdentityMismatch):
            self.store.claim(
                value["handoff_id"],
                identity(parent_thread_id="different-parent"),
            )

        self.assertTrue(pending.exists())
        self.assertFalse((self.store.root / "quarantine").exists())

    def test_corrupt_pending_assignment_is_quarantined(self):
        assignment = "quarantine hash corruption"
        value = capsule(assignment)
        pending = self.store.stage(value, assignment)
        pending.write_text('{"schema":2,"capsule":', encoding="utf-8")

        with self.assertRaises(CorruptState):
            self.store.claim(value["handoff_id"], identity())

        self.assertFalse(pending.exists())
        quarantined = list((self.store.root / "quarantine").glob("*.json"))
        self.assertEqual(len(quarantined), 1)

    def test_initial_delivery_retains_active_authority_for_recovery(self):
        value, active = self.activate()

        self.assertTrue(active.exists())
        self.assertFalse(self.store.path("pending", value["handoff_id"]).exists())
        self.assertFalse(self.store.path("claimed", value["handoff_id"]).exists())
        self.assertEqual(
            self.store.mark_recovery(
                value["assignment_id"],
                identity(),
                root="/workspace/repository",
                branch="main",
                head="a" * 64,
            ),
            1,
        )
        self.assertTrue(active.exists())

    def test_recovery_epoch_requires_exact_bound_identity_and_location(self):
        value, active = self.activate()
        wrong_identity = identity()
        wrong_identity["child_thread_id"] = "wrong-child"
        wrong_identity["agent_id"] = "wrong-child"

        with self.assertRaises(IdentityMismatch):
            self.store.mark_recovery(
                value["assignment_id"],
                wrong_identity,
                root="/workspace/repository",
                branch="main",
                head="a" * 64,
            )
        with self.assertRaises(AuthorityViolation):
            self.store.mark_recovery(
                value["assignment_id"],
                identity(),
                root="/workspace/repository",
                branch="main",
                head="b" * 64,
            )

        envelope = json.loads(active.read_text(encoding="utf-8"))
        self.assertEqual(envelope["runtime"]["recovery_count"], 0)

    def test_post_recovery_reattestation_blocks_path_and_git_expansion(self):
        value, _ = self.activate()
        self.store.mark_recovery(
            value["assignment_id"],
            identity(),
            root="/workspace/repository",
            branch="main",
            head="a" * 64,
        )

        self.store.attest_tool_use(
            value["assignment_id"],
            identity(),
            root="/workspace/repository",
            branch="main",
            head="a" * 64,
            changed_paths=["owned/result.txt"],
        )
        with self.assertRaises(AuthorityViolation):
            self.store.attest_tool_use(
                value["assignment_id"],
                identity(),
                root="/workspace/repository",
                branch="main",
                head="a" * 64,
                changed_paths=["outside/result.txt"],
            )
        with self.assertRaises(AuthorityViolation):
            self.store.attest_tool_use(
                value["assignment_id"],
                identity(),
                root="/workspace/repository",
                branch="main",
                head="a" * 64,
                git_operation="commit",
            )

    def test_wrong_child_cannot_reuse_active_authority(self):
        value, _ = self.activate()

        with self.assertRaises(IdentityMismatch):
            self.store.attest_tool_use(
                value["assignment_id"],
                identity(child_thread_id="other", agent_id="other"),
                root="/workspace/repository",
                branch="main",
                head="a" * 64,
            )

    def test_expired_active_state_becomes_unresolved_evidence(self):
        assignment = "retain expired evidence"
        now = dt.datetime.now(dt.timezone.utc)
        value = capsule(
            assignment,
            created_at=now.isoformat(),
            expires_at=(now + dt.timedelta(minutes=1)).isoformat(),
        )
        value["capsule_sha256"] = capsule_sha256(value)
        self.store.stage(value, assignment)
        self.store.claim(value["handoff_id"], identity())
        self.store.activate(value["handoff_id"])

        unresolved = self.store.expire_active(
            value["assignment_id"], now=now + dt.timedelta(minutes=2)
        )

        self.assertIsNotNone(unresolved)
        self.assertTrue(unresolved.exists())
        self.assertFalse(self.store.path("active", value["assignment_id"]).exists())

    def test_expired_capsule_cannot_be_staged(self):
        assignment = "do not replay expired authority"
        now = dt.datetime.now(dt.timezone.utc)
        value = capsule(
            assignment,
            created_at=(now - dt.timedelta(minutes=2)).isoformat(),
            pre_write_attestation_deadline=(
                now - dt.timedelta(seconds=90)
            ).isoformat(),
            expires_at=(now - dt.timedelta(minutes=1)).isoformat(),
        )
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(compatibility_state.StateError, "expired"):
            self.store.stage(value, assignment)

        self.assertFalse(self.store.path("pending", value["handoff_id"]).exists())

    def test_parent_adjudication_requires_feasibility_contract_dimension(self):
        value, _ = self.activate()
        self.store.finalize(value["assignment_id"], {}, complete=True)

        with self.assertRaisesRegex(
            compatibility_state.StateError, "fields are not exact"
        ):
            self.store.adjudicate_parent(
                value["assignment_id"],
                {
                    "location_integrity": "pass",
                    "mutation_scope_integrity": "pass",
                    "verification_freshness": "pass",
                    "derivation_provenance_integrity": "pass",
                    "evidence_sha256": "c" * 64,
                },
            )

    def test_parent_adjudication_blocks_any_failed_integrity_dimension(self):
        value, _ = self.activate()
        reported = self.store.finalize(value["assignment_id"], {}, complete=True)
        self.assertEqual(reported.parent.name, "reported")

        unresolved = self.store.adjudicate_parent(
            value["assignment_id"],
            {
                "location_integrity": "pass",
                "mutation_scope_integrity": "pass",
                "verification_freshness": "pass",
                "derivation_provenance_integrity": "fail",
                "feasibility_contract_integrity": "pass",
                "evidence_sha256": "c" * 64,
            },
        )

        self.assertEqual(unresolved.parent.name, "unresolved")
        self.assertFalse(self.store.path("consumed", value["assignment_id"]).exists())

    def test_parent_adjudication_promotes_only_all_pass_report(self):
        value, _ = self.activate("integrate only after fresh parent evidence")
        self.store.finalize(value["assignment_id"], {}, complete=True)

        consumed = self.store.adjudicate_parent(
            value["assignment_id"],
            {
                "location_integrity": "pass",
                "mutation_scope_integrity": "pass",
                "verification_freshness": "pass",
                "derivation_provenance_integrity": "pass",
                "feasibility_contract_integrity": "pass",
                "evidence_sha256": "d" * 64,
            },
        )

        self.assertEqual(consumed.parent.name, "consumed")

    def test_atomic_stage_recheck_rejects_capture_snapshot_drift(self):
        assignment = "stage only if the capture snapshot remains exact"
        baseline = {
            "root": "/workspace/repository",
            "branch": "main",
            "head": "a" * 64,
            "index_changed": False,
            "git_status_short": "",
            "changed_paths": [],
        }
        value = capsule(
            assignment,
            capture_snapshot_sha256=git_snapshot_sha256(baseline),
        )
        value["capsule_sha256"] = capsule_sha256(value)
        drifted = dict(baseline, git_status_short="?? owned/late.txt")

        with self.assertRaisesRegex(
            AuthorityViolation,
            "capture snapshot changed",
        ):
            self.store.stage_with_ownership_recheck(
                value,
                assignment,
                drifted,
                observed_at=dt.datetime.now(dt.timezone.utc),
            )

        self.assertFalse(self.store.path("pending", value["handoff_id"]).exists())


if __name__ == "__main__":
    unittest.main()
