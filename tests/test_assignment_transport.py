import datetime as dt
from concurrent.futures import ThreadPoolExecutor
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
HOOK_SCRIPT = REPO / "hooks" / "compatibility_hook.py"


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
assignment_transport = load_module(
    "assignment_transport", REPO / "hooks" / "assignment_transport.py"
)


StateStore = compatibility_state.StateStore


class AssignmentTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        (self.repository / "deleted.txt").write_text("delete me\n", encoding="utf-8")
        self.git("add", "baseline.txt", "deleted.txt")
        self.git("commit", "-m", "baseline")
        self.store = StateStore(self.root / "state")
        self.parent_transcript = self.root / "parent.jsonl"
        self.write_meta(
            self.parent_transcript,
            session_id="runtime-session",
            thread_id="parent-thread",
            agent_path=None,
            parent_thread_id=None,
            agent_role=None,
        )

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

    def write_meta(
        self,
        path,
        *,
        session_id,
        thread_id,
        agent_path,
        parent_thread_id,
        agent_role,
    ):
        payload = {
            "session_id": session_id,
            "id": thread_id,
            "timestamp": "2026-08-12T00:00:00Z",
            "cwd": str(self.repository),
            "originator": "fixture",
            "cli_version": "0.147.0",
            "source": "sub_agent" if parent_thread_id else "cli",
            "model_provider": "fixture-provider",
        }
        if parent_thread_id is not None:
            payload["parent_thread_id"] = parent_thread_id
        if agent_role is not None:
            payload["agent_role"] = agent_role
        if agent_path is not None:
            payload["agent_path"] = agent_path
        item = {"timestamp": payload["timestamp"], "type": "session_meta", "payload": payload}
        path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    def message(self, *, authority=None):
        value = authority or {
            "schema": 1,
            "owned_paths": ["owned"],
            "excluded_paths": ["owned/excluded"],
            "git_authority": {
                "stage": False,
                "commit": False,
                "branch": False,
                "push": False,
            },
            "stop_condition": "finish only the assigned slice",
            "verification": ["fixture verification"],
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
            },
            "location_preflight": None,
            "pre_write_attestation_timeout_seconds": 30,
            "ttl_seconds": 300,
        }
        return (
            "Implement the bounded slice.\n\n"
            "BEGIN CODEX WORKER AUTHORITY\n"
            + json.dumps(value, separators=(",", ":"))
            + "\nEND CODEX WORKER AUTHORITY"
        )

    def spawn_hook(self, task_name="bounded_task", **overrides):
        tool_input = {
            "message": self.message(),
            "task_name": task_name,
            "agent_type": "fixture_worker",
            "fork_turns": "none",
        }
        tool_input.update(overrides.pop("tool_input", {}))
        value = {
            "hook_event_name": "PreToolUse",
            "session_id": "runtime-session",
            "turn_id": "parent-turn",
            "transcript_path": str(self.parent_transcript),
            "cwd": str(self.repository),
            "tool_name": "spawn_agent",
            "tool_use_id": f"spawn-{task_name}",
            "tool_input": tool_input,
        }
        value.update(overrides)
        return value

    def child_hook(self, task_name="bounded_task", *, parent_path="/root"):
        child = self.root / f"child-{task_name}.jsonl"
        self.write_meta(
            child,
            session_id="runtime-session",
            thread_id=f"child-{task_name}",
            parent_thread_id="parent-thread",
            agent_role="fixture_worker",
            agent_path=f"{parent_path}/{task_name}",
        )
        return {
            "hook_event_name": "SubagentStart",
            "session_id": "runtime-session",
            "agent_id": f"child-{task_name}",
            "agent_type": "fixture_worker",
            "transcript_path": str(child),
            "cwd": str(self.repository),
        }

    def capture(self, hook):
        return assignment_transport.capture_spawn(
            self.store,
            hook,
            plaintext_agent_types={"fixture_worker"},
            now=dt.datetime.now(dt.timezone.utc),
        )

    def invoke_hook_cli(self, hook):
        return subprocess.run(
            [
                sys.executable,
                str(HOOK_SCRIPT),
                "--state-directory",
                str(self.store.root),
                "--plaintext-agent-type",
                "fixture_worker",
            ],
            input=json.dumps(hook),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def freeze_active_and_record_barrier(self, task_name="bounded_task"):
        active_path = next((self.store.root / "active").glob("*.json"))
        envelope = json.loads(active_path.read_text(encoding="utf-8"))
        assignment_id = envelope["capsule"]["assignment_id"]
        snapshot = runtime_guard.collect_git_snapshot(str(self.repository))
        self.store.terminate_active(
            assignment_id,
            {
                "schema": 1,
                "reason": "parent_interrupt_requested",
                "classification": (
                    "unresponsive_with_contribution"
                    if snapshot["changed_paths"]
                    else "unresponsive_no_disk_change"
                ),
            },
        )
        observed_at = dt.datetime.now(dt.timezone.utc)
        barrier = self.store.record_quiescence_barrier(
            assignment_id,
            {
                "receipt_id": f"terminated-{task_name}",
                "runtime_session_id": "runtime-session",
                "child_thread_id": f"child-{task_name}",
                "guarantee": "child_terminated_and_mutations_quiesced",
                "terminated_at": observed_at.isoformat(),
            },
            snapshot,
            observed_at=observed_at,
        )
        return assignment_id, barrier

    def test_non_target_worker_passes_without_state_or_input_rewrite(self):
        hook = self.spawn_hook(tool_input={"agent_type": "default"})

        result = self.capture(hook)

        self.assertEqual(result, {})
        self.assertFalse((self.store.root / "pending").exists())

    def test_parent_pre_tool_use_captures_exact_spawn_message_and_runtime_facts(self):
        hook = self.spawn_hook()

        result = self.capture(hook)

        self.assertNotIn("updatedInput", json.dumps(result))
        pending = list((self.store.root / "pending").glob("*.json"))
        self.assertEqual(len(pending), 1)
        envelope = json.loads(pending[0].read_text(encoding="utf-8"))
        capsule = envelope["capsule"]
        self.assertEqual(envelope["assignment"], hook["tool_input"]["message"])
        self.assertEqual(capsule["runtime_session_id"], "runtime-session")
        self.assertEqual(capsule["parent_thread_id"], "parent-thread")
        self.assertEqual(capsule["canonical_agent_path"], "/root/bounded_task")
        self.assertEqual(capsule["root"]["path"], str(self.repository.resolve()))

    def test_invalid_authority_or_fork_mode_blocks_spawn(self):
        invalid = self.message(authority={"schema": 1, "credentials": "forbidden"})
        cases = [
            self.spawn_hook(tool_input={"message": invalid}),
            self.spawn_hook(tool_input={"fork_turns": "all"}),
        ]
        for hook in cases:
            with self.subTest(tool_input=hook["tool_input"]):
                result = self.capture(hook)
                self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertFalse((self.store.root / "pending").exists())

    def test_capture_records_modified_and_deleted_dirty_baselines(self):
        (self.repository / "baseline.txt").write_text("user change\n", encoding="utf-8")
        (self.repository / "deleted.txt").unlink()

        self.capture(self.spawn_hook())
        pending = next((self.store.root / "pending").glob("*.json"))
        dirty = {
            item["path"]: item
            for item in json.loads(pending.read_text(encoding="utf-8"))["capsule"][
                "preexisting_dirty"
            ]
        }

        self.assertEqual(dirty["baseline.txt"]["kind"], "file")
        self.assertRegex(dirty["baseline.txt"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(dirty["deleted.txt"]["kind"], "deleted")
        self.assertIsNone(dirty["deleted.txt"]["sha256"])

    def test_parent_session_mismatch_blocks_without_staging(self):
        result = self.capture(self.spawn_hook(session_id="different-session"))

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertFalse((self.store.root / "pending").exists())

    def test_optional_location_preflight_blocks_same_prefix_wrong_full_head(self):
        actual_head = self.git("rev-parse", "HEAD").stdout.strip()
        wrong_head = actual_head[:12] + ("0" if actual_head[12] != "0" else "1") + actual_head[13:]
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["location_preflight"] = {
            "expected_root": str(self.repository.resolve()),
            "expected_branch": "main",
            "expected_base_head": wrong_head,
        }

        result = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("does not exactly match", result["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertFalse((self.store.root / "pending").exists())
        self.assertEqual(runtime_guard.collect_git_snapshot(str(self.repository))["changed_paths"], [])

    def test_optional_location_preflight_accepts_exact_current_location(self):
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["location_preflight"] = {
            "expected_root": str(self.repository.resolve()),
            "expected_branch": "main",
            "expected_base_head": self.git("rev-parse", "HEAD").stdout.strip(),
        }

        result = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )

        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 1)

    def test_location_preflight_rejects_abbreviated_head_format(self):
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["location_preflight"] = {
            "expected_root": str(self.repository.resolve()),
            "expected_branch": "main",
            "expected_base_head": self.git("rev-parse", "HEAD").stdout.strip()[:12],
        }

        result = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("full Git object id", result["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertFalse((self.store.root / "pending").exists())

    def test_strict_read_only_capture_binds_clean_exact_range_and_replay_baseline(self):
        head = self.git("rev-parse", "HEAD").stdout.strip()
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["owned_paths"] = []
        authority["excluded_paths"] = []
        authority["authority_provenance"]["authoritative_input_roots"] = ["baseline.txt"]
        authority["execution_contract"] = {
            "posture": "strict_read_only",
            "review_range": {"base_oid": head, "head_oid": head},
            "required_invariants": ["known failure remains reproducible without literal rerun"],
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
                    "manifest_path": "baseline.txt",
                    "sha256": hashlib.sha256(
                        (self.repository / "baseline.txt").read_bytes()
                    ).hexdigest(),
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
        }

        result = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )

        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        capsule = json.loads(
            next((self.store.root / "pending").glob("*.json")).read_text(encoding="utf-8")
        )["capsule"]
        self.assertEqual(capsule["execution_contract"], authority["execution_contract"])
        self.assertEqual(capsule["ownership_handover"], [])

    def test_strict_read_only_capture_blocks_dirty_state_and_bad_replay_hash(self):
        head = self.git("rev-parse", "HEAD").stdout.strip()
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["owned_paths"] = []
        authority["excluded_paths"] = []
        authority["authority_provenance"]["authoritative_input_roots"] = ["baseline.txt"]
        authority["execution_contract"] = {
            "posture": "strict_read_only",
            "review_range": {"base_oid": head, "head_oid": head},
            "required_invariants": [],
            "diagnostics": {
                "stable_failure_codes": ["OWNER.QUERY_FAILED"],
                "known_true_failure_codes": ["OWNER.QUERY_FAILED"],
                "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED",
                "allow_literal_expensive_rerun": False,
                "allowed_failure_code_localities": {
                    "OWNER.QUERY_FAILED": ["overall"]
                },
            },
            "proven_input_baselines": [
                {
                    "baseline_id": "replay-v1",
                    "owner": "fixture.owner",
                    "manifest_path": "baseline.txt",
                    "sha256": "0" * 64,
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
        }
        authority["execution_contract"]["review_range"]["head_oid"] = head[:12]
        abbreviated = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )
        self.assertEqual(abbreviated["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("full Git object id", abbreviated["hookSpecificOutput"]["permissionDecisionReason"])

        authority["execution_contract"]["review_range"]["head_oid"] = head
        bad_hash = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )
        self.assertEqual(bad_hash["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("manifest hash", bad_hash["hookSpecificOutput"]["permissionDecisionReason"])

        authority["execution_contract"]["proven_input_baselines"] = []
        (self.repository / "baseline.txt").write_text("dirty\n", encoding="utf-8")
        dirty = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )
        self.assertEqual(dirty["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("clean captured worktree", dirty["hookSpecificOutput"]["permissionDecisionReason"])

    def test_review_followup_contract_binds_frozen_base_fresh_tip_and_output_authority(self):
        base = self.git("rev-parse", "HEAD").stdout.strip()
        (self.repository / "corrected.txt").write_text("corrected\n", encoding="utf-8")
        self.git("add", "corrected.txt")
        self.git("commit", "-m", "corrected tip")
        tip = self.git("rev-parse", "HEAD").stdout.strip()
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["owned_paths"] = []
        authority["excluded_paths"] = []
        authority["execution_contract"].update(
            {
                "posture": "strict_read_only",
                "review_range": {"base_oid": base, "head_oid": tip},
                "required_invariants": ["freshly adjudicate every unresolved finding"],
                "review_continuation": {
                    "prior_assignment_id": str(uuid.uuid4()),
                    "frozen_cumulative_base_oid": base,
                    "prior_review_base_oid": base,
                    "prior_review_tip_oid": base,
                    "corrected_tip_oid": tip,
                    "prior_findings_sha256": "f" * 64,
                    "unresolved_finding_ids": ["P1-1", "P1-2"],
                    "exact_narrowed_objective": "recheck only P1-1 and P1-2",
                    "require_clean_worktree": True,
                },
                "evidence_binding": {
                    "executed_root": str(self.repository.resolve()),
                    "hashed_root": str(self.repository.resolve()),
                    "source_identity": {"kind": "git_commit", "value": tip},
                    "canonical_output": "evidence/review.json",
                    "no_follow_dirfd_walk": True,
                    "terminal_regular_file_reproof": True,
                    "preflight_before_expensive_execution": True,
                },
            }
        )
        authority["stop_condition"] = (
            "recheck only P1-1 and P1-2; do not claim broader completion"
        )

        accepted = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )
        self.assertNotIn("permissionDecision", accepted["hookSpecificOutput"])

        wrong_tip = tip[:12] + ("0" if tip[12] != "0" else "1") + tip[13:]
        authority["execution_contract"]["review_continuation"][
            "corrected_tip_oid"
        ] = wrong_tip
        typo = self.capture(
            self.spawn_hook(
                task_name="typo_review",
                tool_input={"message": self.message(authority=authority)},
            )
        )
        self.assertEqual(typo["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("does not exactly match", typo["hookSpecificOutput"]["permissionDecisionReason"])
        authority["execution_contract"]["review_continuation"][
            "corrected_tip_oid"
        ] = tip

        other_root = self.root / "other"
        other_root.mkdir()
        authority["execution_contract"]["evidence_binding"]["hashed_root"] = str(other_root)
        rejected = self.capture(
            self.spawn_hook(
                task_name="different_review",
                tool_input={"message": self.message(authority=authority)},
            )
        )
        self.assertEqual(rejected["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("roots must be identical", rejected["hookSpecificOutput"]["permissionDecisionReason"])

    def test_subagent_start_claims_exact_capsule_and_retains_active_authority(self):
        hook = self.spawn_hook()
        self.capture(hook)

        result = assignment_transport.subagent_start(self.store, self.child_hook())

        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("BEGIN CODEX WORKER CAPSULE", context)
        self.assertIn(hook["tool_input"]["message"], context)
        self.assertEqual(len(list((self.store.root / "active").glob("*.json"))), 1)
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 0)

    def test_wrong_child_path_does_not_consume_pending(self):
        self.capture(self.spawn_hook())

        wrong_child = self.child_hook("different_task")
        result = assignment_transport.subagent_start(
            self.store, wrong_child
        )

        self.assertIn("TASK.CONTEXT_LOST", result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 1)
        self.assertEqual(len(list((self.store.root / "lost").glob("*.json"))), 1)

        denied = runtime_guard.pre_tool_use(
            self.store,
            dict(wrong_child, hook_event_name="PreToolUse", tool_name="view_image"),
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        stopped = runtime_guard.subagent_stop(
            self.store,
            {
                "hook_event_name": "SubagentStop",
                "session_id": "runtime-session",
                "agent_id": "child-different_task",
                "agent_type": "fixture_worker",
                "transcript_path": str(self.parent_transcript),
                "agent_transcript_path": wrong_child["transcript_path"],
                "last_assistant_message": "TASK.CONTEXT_LOST",
            },
        )
        self.assertEqual(stopped, {})

    def test_interrupt_ack_without_quiescence_cannot_reassign_overlapping_paths(self):
        self.capture(self.spawn_hook())
        child = self.child_hook()
        assignment_transport.subagent_start(self.store, child)
        active_path = next((self.store.root / "active").glob("*.json"))
        assignment_id = json.loads(active_path.read_text(encoding="utf-8"))["capsule"][
            "assignment_id"
        ]
        self.store.terminate_active(
            assignment_id,
            {"schema": 1, "reason": "interrupt_ack", "classification": "unresponsive_no_disk_change"},
        )

        with self.assertRaisesRegex(
            compatibility_state.AuthorityViolation,
            "not mutation quiescence",
        ):
            self.store.record_quiescence_barrier(
                assignment_id,
                {
                    "receipt_id": "interrupt-only",
                    "runtime_session_id": "runtime-session",
                    "child_thread_id": "child-bounded_task",
                    "guarantee": "interrupt_acknowledged",
                    "terminated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
                runtime_guard.collect_git_snapshot(str(self.repository)),
            )

        replacement = self.capture(self.spawn_hook("replacement_task"))
        self.assertEqual(replacement["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("no host termination", replacement["hookSpecificOutput"]["permissionDecisionReason"])

    def test_frozen_old_child_is_blocked_and_barrier_allows_linked_reassignment(self):
        self.capture(self.spawn_hook())
        old_child = self.child_hook()
        assignment_transport.subagent_start(self.store, old_child)
        prior_assignment_id, _ = self.freeze_active_and_record_barrier()

        denied = runtime_guard.pre_tool_use(
            self.store,
            dict(old_child, hook_event_name="PreToolUse", tool_name="view_image"),
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")

        replacement = self.capture(self.spawn_hook("replacement_task"))
        self.assertNotIn("permissionDecision", replacement["hookSpecificOutput"])
        pending = next((self.store.root / "pending").glob("*.json"))
        capsule = json.loads(pending.read_text(encoding="utf-8"))["capsule"]
        self.assertEqual(
            capsule["ownership_handover"][0]["prior_assignment_id"],
            prior_assignment_id,
        )

    def test_quiesced_prior_dirty_bytes_are_linked_not_attributed_to_replacement(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())
        (self.repository / "owned").mkdir()
        prior_path = self.repository / "owned" / "prior.txt"
        prior_path.write_text("prior child contribution\n", encoding="utf-8")
        prior_assignment_id, _ = self.freeze_active_and_record_barrier()

        replacement = self.capture(self.spawn_hook("replacement_task"))

        self.assertNotIn("permissionDecision", replacement["hookSpecificOutput"])
        pending = next((self.store.root / "pending").glob("*.json"))
        capsule = json.loads(pending.read_text(encoding="utf-8"))["capsule"]
        self.assertEqual(
            capsule["ownership_handover"][0]["prior_assignment_id"],
            prior_assignment_id,
        )
        dirty = {item["path"]: item for item in capsule["preexisting_dirty"]}
        self.assertIn("owned/prior.txt", dirty)
        self.assertEqual(
            dirty["owned/prior.txt"]["sha256"],
            hashlib.sha256(prior_path.read_bytes()).hexdigest(),
        )

    def test_late_mutation_after_barrier_blocks_new_child_and_marks_mixed_provenance(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())
        self.freeze_active_and_record_barrier()
        self.capture(self.spawn_hook("replacement_task"))
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "late.txt").write_text("late old-child write\n", encoding="utf-8")
        replacement_child = self.child_hook("replacement_task")
        assignment_transport.subagent_start(self.store, replacement_child)

        denied = runtime_guard.pre_tool_use(
            self.store,
            dict(replacement_child, hook_event_name="PreToolUse", tool_name="view_image"),
        )

        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        unresolved = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (self.store.root / "unresolved").glob("*.json")
            if "termination_evidence" in json.loads(path.read_text(encoding="utf-8"))
        ]
        latest = next(
            item
            for item in unresolved
            if item["capsule"]["requested_task_name"] == "replacement_task"
        )
        self.assertEqual(
            latest["termination_evidence"]["classification"],
            "late_mutation_after_interrupt",
        )
        self.assertEqual(
            latest["termination_evidence"]["provenance_status"],
            "overlapping_assignment_provenance",
        )

    def test_late_mutation_before_reassignment_is_recorded_and_spawn_is_blocked(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())
        self.freeze_active_and_record_barrier()
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "late.txt").write_text("late old-child write\n", encoding="utf-8")

        replacement = self.capture(self.spawn_hook("replacement_task"))

        self.assertEqual(replacement["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("late mutation", replacement["hookSpecificOutput"]["permissionDecisionReason"])
        overlap = next((self.store.root / "overlap").glob("*.json"))
        evidence = json.loads(overlap.read_text(encoding="utf-8"))
        self.assertEqual(
            evidence["classifications"],
            ["late_mutation_after_interrupt", "overlapping_assignment_provenance"],
        )

    def test_concurrent_distinct_spawns_bind_to_their_own_children(self):
        tasks = ["task_one", "task_two", "task_three"]
        def distinct_spawn(task):
            authority = json.loads(
                self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                    "\nEND CODEX WORKER AUTHORITY", 1
                )[0]
            )
            authority["owned_paths"] = [f"owned/{task}"]
            authority["excluded_paths"] = []
            return self.spawn_hook(
                task,
                tool_input={"message": self.message(authority=authority)},
            )
        with ThreadPoolExecutor(max_workers=3) as executor:
            captured = list(executor.map(lambda task: self.capture(distinct_spawn(task)), tasks))
        self.assertTrue(all("updatedInput" not in json.dumps(item) for item in captured))

        with ThreadPoolExecutor(max_workers=3) as executor:
            started = list(
                executor.map(
                    lambda task: assignment_transport.subagent_start(
                        self.store, self.child_hook(task)
                    ),
                    reversed(tasks),
                )
            )

        self.assertTrue(all("BEGIN CODEX WORKER CAPSULE" in item["hookSpecificOutput"]["additionalContext"] for item in started))
        self.assertEqual(len(list((self.store.root / "active").glob("*.json"))), 3)
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 0)

    def test_concurrent_overlapping_spawns_atomically_allow_only_one_owner(self):
        tasks = ["overlap_one", "overlap_two"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(lambda task: self.capture(self.spawn_hook(task)), tasks)
            )

        decisions = [
            result["hookSpecificOutput"].get("permissionDecision", "pass")
            for result in results
        ]
        self.assertEqual(sorted(decisions), ["deny", "pass"])
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 1)

    def test_nested_parent_path_derives_exact_child_agent_path(self):
        self.write_meta(
            self.parent_transcript,
            session_id="runtime-session",
            thread_id="parent-thread",
            parent_thread_id="root-thread",
            agent_role="default",
            agent_path="/root/parent_task",
        )
        hook = self.spawn_hook(agent_id="parent-thread", agent_type="default")

        self.capture(hook)
        pending = next((self.store.root / "pending").glob("*.json"))
        capsule = json.loads(pending.read_text(encoding="utf-8"))["capsule"]

        self.assertEqual(capsule["canonical_agent_path"], "/root/parent_task/bounded_task")

    def test_executable_hook_runs_capture_claim_recovery_and_final_lifecycle(self):
        spawn = self.spawn_hook()
        captured = self.invoke_hook_cli(spawn)
        self.assertEqual(captured.returncode, 0, captured.stderr)
        self.assertNotIn(spawn["tool_input"]["message"], captured.stdout)

        child = self.child_hook()
        started = self.invoke_hook_cli(child)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("BEGIN CODEX WORKER CAPSULE", started.stdout)

        compact = dict(child, hook_event_name="PreCompact", trigger="auto")
        compacted = self.invoke_hook_cli(compact)
        self.assertEqual(compacted.returncode, 0, compacted.stderr)

        checked = self.invoke_hook_cli(
            dict(child, hook_event_name="PreToolUse", tool_name="view_image", tool_input={})
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        checked_output = json.loads(checked.stdout)
        checked_context = checked_output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("recovery_count=1", checked_context)
        self.assertIn(spawn["tool_input"]["message"], checked_context)

        active_path = next((self.store.root / "active").glob("*.json"))
        envelope = json.loads(active_path.read_text(encoding="utf-8"))
        capsule = envelope["capsule"]
        snapshot = runtime_guard.collect_git_snapshot(str(self.repository))
        attestation = {
            "assignment_id": capsule["assignment_id"],
            "handoff_id": capsule["handoff_id"],
            "capsule_sha256": capsule["capsule_sha256"],
            "compact_invariant_sha256": compatibility_state.compact_invariant_sha256(
                capsule
            ),
            "authority_provenance": {
                "policy_sha256": compatibility_state.provenance_policy_sha256(capsule),
                "worker_claimed_origin": "owner_internal",
                "test_only_injection_used": False,
                "derivation_receipt_sha256": "d" * 64,
            },
            "canonical_agent_path": capsule["canonical_agent_path"],
            "recovery_count": 1,
            "context_lost": False,
            **snapshot,
            "verification": [{"command": "fixture verification", "exit_code": 0}],
            "authority_violation": False,
            "assigned_slice_complete": True,
            "inventory_summaries": [],
        }
        message = (
            "BEGIN CODEX WORKER ATTESTATION\n"
            + json.dumps(attestation)
            + "\nEND CODEX WORKER ATTESTATION"
        )
        stopped = self.invoke_hook_cli(
            {
                "hook_event_name": "SubagentStop",
                "session_id": "runtime-session",
                "agent_id": "child-bounded_task",
                "agent_type": "fixture_worker",
                "transcript_path": str(self.parent_transcript),
                "agent_transcript_path": child["transcript_path"],
                "last_assistant_message": message,
            }
        )

        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(json.loads(stopped.stdout), {})
        self.assertEqual(len(list((self.store.root / "reported").glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
