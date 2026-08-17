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
writer_lease_guard = load_module(
    "writer_lease_guard", REPO / "hooks" / "writer_lease_guard.py"
)
hook_event_receipts = load_module(
    "hook_event_receipts", REPO / "hooks" / "hook_event_receipts.py"
)
hook_schema_observation_arm = load_module(
    "hook_schema_observation_arm", REPO / "hooks" / "hook_schema_observation_arm.py"
)
pretool_schema_observation = load_module(
    "pretool_schema_observation", REPO / "hooks" / "pretool_schema_observation.py"
)
subagentstart_schema_observation = load_module(
    "subagentstart_schema_observation",
    REPO / "hooks" / "subagentstart_schema_observation.py",
)
compatibility_hook = load_module(
    "compatibility_hook", REPO / "hooks" / "compatibility_hook.py"
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
            thread_id="runtime-session",
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
            "cli_version": "0.148.0-alpha.9",
            "source": "vscode",
            "model_provider": "fixture-provider",
        }
        if parent_thread_id is not None:
            payload.update(
                {
                    "parent_thread_id": parent_thread_id,
                    "agent_role": agent_role,
                    "agent_path": agent_path,
                }
            )
            payload["source"] = {
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": parent_thread_id,
                        "depth": 1,
                        "agent_path": agent_path,
                        "agent_nickname": None,
                        "agent_role": agent_role,
                    }
                }
            }
        item = {
            "timestamp": "2026-08-12T00:00:00.070Z",
            "type": "session_meta",
            "payload": payload,
        }
        path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    def message(self, *, authority=None):
        value = authority or {
            "schema": 1,
            "assignment_mutation_mode": "write",
            "parent_recorded_user_write_intent": "allow",
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

    def parent_patch_hook(
        self,
        path="owned/result.txt",
        *,
        event="PreToolUse",
        tool_use_id="parent-patch",
        move_to=None,
        transcript_path=None,
    ):
        if move_to is None:
            command = (
                "*** Begin Patch\n"
                f"*** Add File: {path}\n"
                "+parent bytes\n"
                "*** End Patch"
            )
        else:
            command = (
                "*** Begin Patch\n"
                f"*** Update File: {path}\n"
                f"*** Move to: {move_to}\n"
                "@@\n"
                "-baseline\n"
                "+parent bytes\n"
                "*** End Patch"
            )
        value = {
            "hook_event_name": event,
            "session_id": "runtime-session",
            "turn_id": "parent-turn",
            "transcript_path": str(transcript_path or self.parent_transcript),
            "cwd": str(self.repository),
            "tool_name": "apply_patch",
            "tool_use_id": tool_use_id,
            "tool_input": {"command": command},
        }
        if event == "PostToolUse":
            value["tool_response"] = {"status": "completed"}
        return value

    def child_hook(self, task_name="bounded_task", *, parent_path="/root"):
        child = self.root / f"child-{task_name}.jsonl"
        self.write_meta(
            child,
            session_id="runtime-session",
            thread_id=f"child-{task_name}",
            parent_thread_id="runtime-session",
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
        self.assertEqual(capsule["parent_thread_id"], "runtime-session")
        self.assertEqual(capsule["canonical_agent_path"], "/root/bounded_task")
        self.assertEqual(capsule["root"]["path"], str(self.repository.resolve()))
        self.assertEqual(capsule["assignment_mutation_mode"], "write")
        self.assertEqual(
            capsule["parent_recorded_user_write_intent"], "allow"
        )
        self.assertEqual(
            capsule["trusted_host_user_write_consent"],
            {
                "schema": 1,
                "status": "unavailable",
                "source": None,
                "receipt_sha256": None,
            },
        )

    def test_parent_capture_accepts_current_native_agent_hook_alias(self):
        hook = self.spawn_hook(tool_name="Agent", tool_use_id="agent-alias-spawn")

        result = self.capture(hook)

        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        envelope = json.loads(
            next((self.store.root / "pending").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            envelope["capsule"]["spawn_tool_use_id"], "agent-alias-spawn"
        )

    def test_parent_capture_accepts_observed_collaboration_hook_name(self):
        hook = self.spawn_hook(
            tool_name="collaborationspawn_agent",
            tool_use_id="collaboration-spawn",
        )

        result = self.capture(hook)

        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        envelope = json.loads(
            next((self.store.root / "pending").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            envelope["capsule"]["spawn_tool_use_id"], "collaboration-spawn"
        )

    def test_parent_capture_accepts_exact_plaintext_compatibility_hook_name(self):
        hook = self.spawn_hook(
            tool_name=assignment_transport.PLAINTEXT_COMPAT_SPAWN_TOOL_NAME,
            tool_use_id="plaintext-compat-spawn",
        )

        result = self.capture(hook)

        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        envelope = json.loads(
            next((self.store.root / "pending").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            envelope["capsule"]["spawn_tool_use_id"], "plaintext-compat-spawn"
        )
        self.assertNotIn(
            "g4_assignment_evilspawn_agent", assignment_transport.SPAWN_TOOL_NAMES
        )

    def test_write_spawn_requires_parent_recorded_explicit_user_intent(self):
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["parent_recorded_user_write_intent"] = "deny"

        result = self.capture(
            self.spawn_hook(
                "no_recorded_user_intent",
                tool_input={"message": self.message(authority=authority)},
            )
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "parent-recorded explicit user intent",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )
        self.assertFalse((self.store.root / "pending").exists())

    def test_parent_recorded_intent_never_fabricates_trusted_host_consent(self):
        result = self.capture(self.spawn_hook("intent_is_not_host_consent"))

        self.assertNotIn("permissionDecision", result["hookSpecificOutput"])
        capsule = json.loads(
            next((self.store.root / "pending").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )["capsule"]
        self.assertEqual(capsule["parent_recorded_user_write_intent"], "allow")
        self.assertEqual(
            capsule["trusted_host_user_write_consent"]["status"], "unavailable"
        )

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

    def test_parent_feasibility_gate_blocks_unbounded_direct_write_before_staging(self):
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        feasibility = authority["execution_contract"]["capsule_feasibility_attestation"]
        feasibility["bounded_completion"]["mechanism_satisfies"] = False
        feasibility["owner_decision"] = "block"

        result = self.capture(
            self.spawn_hook(tool_input={"message": self.message(authority=authority)})
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("feasibility", result["hookSpecificOutput"]["permissionDecisionReason"])
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
        authority["assignment_mutation_mode"] = "read_only"
        authority["parent_recorded_user_write_intent"] = "deny"
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
            "capsule_feasibility_attestation": None,
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
        authority["assignment_mutation_mode"] = "read_only"
        authority["parent_recorded_user_write_intent"] = "deny"
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
            "capsule_feasibility_attestation": None,
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
        authority["assignment_mutation_mode"] = "read_only"
        authority["parent_recorded_user_write_intent"] = "deny"
        authority["execution_contract"].update(
            {
                "posture": "strict_read_only",
                "capsule_feasibility_attestation": None,
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
        seed_text = context.split(
            "BEGIN CODEX WORKER FINAL ATTESTATION SEED\n", 1
        )[1].split("\nEND CODEX WORKER FINAL ATTESTATION SEED", 1)[0]
        seed = json.loads(seed_text)
        self.assertEqual(seed["recovery_count"], 0)
        self.assertEqual(seed["canonical_agent_path"], "/root/bounded_task")
        self.assertNotIn("assigned_slice_complete", seed)
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

    def test_parent_patch_over_active_child_path_is_blocked_and_audited(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())

        result = writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook(),
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("overlap", result["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 0)
        evidence = json.loads(
            next((self.store.root / "writer_conflict").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            evidence["classification"],
            "foreign_actor_writer_lease_conflict",
        )
        self.assertEqual(evidence["conflicts"][0]["kind"], "active")

    def test_exact_quiescence_barrier_allows_parent_reclaim_in_new_claim(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())
        prior_assignment_id, _ = self.freeze_active_and_record_barrier()

        result = writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook(),
        )

        self.assertIn("WRITER.LEASED", result["hookSpecificOutput"]["additionalContext"])
        claim = json.loads(
            next((self.store.root / "writer_claim").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            claim["ownership_handover"][0]["prior_assignment_id"],
            prior_assignment_id,
        )

    def test_parent_reclaim_blocks_disk_drift_after_quiescence_barrier(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())
        self.freeze_active_and_record_barrier()
        (self.repository / "owned").mkdir()
        (self.repository / "owned" / "late.txt").write_text(
            "late bytes\n",
            encoding="utf-8",
        )

        result = writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook(),
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        evidence = json.loads(
            next((self.store.root / "writer_conflict").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["conflicts"][0]["kind"], "unresolved")

    def test_inflight_parent_patch_blocks_overlapping_child_until_exact_post(self):
        pre = self.parent_patch_hook()
        leased = writer_lease_guard.pre_tool_use(self.store, pre)
        self.assertIn("WRITER.LEASED", leased["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 1)

        blocked = self.capture(self.spawn_hook())
        self.assertEqual(blocked["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("in-flight", blocked["hookSpecificOutput"]["permissionDecisionReason"])

        released = writer_lease_guard.post_tool_use(
            self.store,
            self.parent_patch_hook(event="PostToolUse"),
        )
        self.assertEqual(released, {})
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 0)
        self.assertEqual(len(list((self.store.root / "writer_receipt").glob("*.json"))), 1)

        accepted = self.capture(self.spawn_hook("after_parent_patch"))
        self.assertNotIn("permissionDecision", accepted["hookSpecificOutput"])

    def test_disjoint_parent_patch_and_child_ownership_remain_concurrent(self):
        leased = writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook("other/result.txt"),
        )
        self.assertIn("WRITER.LEASED", leased["hookSpecificOutput"]["additionalContext"])

        accepted = self.capture(self.spawn_hook())
        self.assertNotIn("permissionDecision", accepted["hookSpecificOutput"])

    def test_concurrent_parent_claims_allow_only_one_overlapping_writer(self):
        hooks = [
            self.parent_patch_hook(tool_use_id="parent-race-one"),
            self.parent_patch_hook(tool_use_id="parent-race-two"),
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda hook: writer_lease_guard.pre_tool_use(self.store, hook),
                    hooks,
                )
            )

        decisions = [
            result["hookSpecificOutput"].get("permissionDecision", "pass")
            for result in results
        ]
        self.assertEqual(sorted(decisions), ["deny", "pass"])
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 1)
        self.assertEqual(len(list((self.store.root / "writer_conflict").glob("*.json"))), 1)

    def test_concurrent_disjoint_parent_claims_both_persist(self):
        hooks = [
            self.parent_patch_hook("one/result.txt", tool_use_id="parent-disjoint-one"),
            self.parent_patch_hook("two/result.txt", tool_use_id="parent-disjoint-two"),
        ]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda hook: writer_lease_guard.pre_tool_use(self.store, hook),
                    hooks,
                )
            )

        self.assertTrue(
            all("permissionDecision" not in result["hookSpecificOutput"] for result in results)
        )
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 2)

    def test_strict_read_only_capture_requires_no_inflight_parent_writer(self):
        writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook("other/result.txt"),
        )
        head = self.git("rev-parse", "HEAD").stdout.strip()
        authority = json.loads(
            self.message().split("BEGIN CODEX WORKER AUTHORITY\n", 1)[1].split(
                "\nEND CODEX WORKER AUTHORITY", 1
            )[0]
        )
        authority["owned_paths"] = []
        authority["excluded_paths"] = []
        authority["assignment_mutation_mode"] = "read_only"
        authority["parent_recorded_user_write_intent"] = "deny"
        authority["execution_contract"]["posture"] = "strict_read_only"
        authority["execution_contract"]["review_range"] = {
            "base_oid": head,
            "head_oid": head,
        }
        authority["execution_contract"]["capsule_feasibility_attestation"] = None

        blocked = self.capture(
            self.spawn_hook(
                "read_only_during_parent_patch",
                tool_input={"message": self.message(authority=authority)},
            )
        )

        self.assertEqual(blocked["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("in-flight", blocked["hookSpecificOutput"]["permissionDecisionReason"])

    def test_symlink_alias_cannot_bypass_active_child_ownership(self):
        (self.repository / "owned").mkdir()
        (self.repository / "alias").symlink_to("owned", target_is_directory=True)
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())

        result = writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook("alias/result.txt"),
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        evidence = json.loads(
            next((self.store.root / "writer_conflict").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["paths"], ["owned/result.txt"])

    def test_move_destination_cannot_bypass_active_child_ownership(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())

        result = writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook("baseline.txt", move_to="owned/moved.txt"),
        )

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        evidence = json.loads(
            next((self.store.root / "writer_conflict").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["paths"], ["baseline.txt", "owned/moved.txt"])

    def test_parent_patch_absolute_dotdot_and_excluded_aliases_are_blocked(self):
        self.capture(self.spawn_hook())
        assignment_transport.subagent_start(self.store, self.child_hook())
        paths = (
            str(self.repository / "owned" / "absolute.txt"),
            "other/../owned/dotdot.txt",
            "owned/excluded/result.txt",
        )

        for index, path in enumerate(paths):
            with self.subTest(path=path):
                result = writer_lease_guard.pre_tool_use(
                    self.store,
                    self.parent_patch_hook(path, tool_use_id=f"alias-{index}"),
                )
                self.assertEqual(
                    result["hookSpecificOutput"]["permissionDecision"],
                    "deny",
                )

        evidence = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (self.store.root / "writer_conflict").glob("*.json")
        ]
        self.assertEqual(len(evidence), 3)
        self.assertEqual(
            {item["paths"][0] for item in evidence},
            {
                "owned/absolute.txt",
                "owned/dotdot.txt",
                "owned/excluded/result.txt",
            },
        )

    def test_wrong_post_identity_does_not_release_parent_writer_claim(self):
        writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook("other/result.txt"),
        )
        other_transcript = self.root / "other-parent.jsonl"
        self.write_meta(
            other_transcript,
            session_id="runtime-session",
            thread_id="other-parent",
            agent_path=None,
            parent_thread_id=None,
            agent_role=None,
        )

        result = writer_lease_guard.post_tool_use(
            self.store,
            self.parent_patch_hook(
                "other/result.txt",
                event="PostToolUse",
                transcript_path=other_transcript,
            ),
        )

        self.assertIn("TASK.WRITER_LEASE_UNRESOLVED", result["systemMessage"])
        self.assertIs(result["continue"], False)
        self.assertEqual(result["stopReason"], result["systemMessage"])
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 1)

    def test_executable_hook_persists_and_releases_parent_writer_claim(self):
        pre = self.invoke_hook_cli(self.parent_patch_hook("other/result.txt"))
        self.assertEqual(pre.returncode, 0, pre.stderr)
        self.assertIn(
            "WRITER.LEASED",
            json.loads(pre.stdout)["hookSpecificOutput"]["additionalContext"],
        )
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 1)

        post = self.invoke_hook_cli(
            self.parent_patch_hook("other/result.txt", event="PostToolUse")
        )

        self.assertEqual(post.returncode, 0, post.stderr)
        self.assertEqual(json.loads(post.stdout), {})
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 0)
        self.assertEqual(len(list((self.store.root / "writer_receipt").glob("*.json"))), 1)

    def test_patch_target_resolves_git_root_when_hook_cwd_is_repo_parent(self):
        hook = self.parent_patch_hook(str(self.repository / "other" / "result.txt"))
        hook["cwd"] = str(self.root)

        leased = writer_lease_guard.pre_tool_use(self.store, hook)

        self.assertIn("WRITER.LEASED", leased["hookSpecificOutput"]["additionalContext"])
        claim = json.loads(
            next((self.store.root / "writer_claim").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(claim["root"], str(self.repository.resolve()))
        self.assertEqual(claim["paths"], ["other/result.txt"])

        released = writer_lease_guard.post_tool_use(
            self.store,
            dict(hook, hook_event_name="PostToolUse", tool_response={"status": "completed"}),
        )
        self.assertEqual(released, {})
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 0)

    def test_relative_patch_target_can_enter_one_child_repo_from_parent_cwd(self):
        hook = self.parent_patch_hook("repository/other/result.txt")
        hook["cwd"] = str(self.root)

        leased = writer_lease_guard.pre_tool_use(self.store, hook)

        self.assertIn("WRITER.LEASED", leased["hookSpecificOutput"]["additionalContext"])
        claim = json.loads(
            next((self.store.root / "writer_claim").glob("*.json")).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(claim["paths"], ["other/result.txt"])

    def test_patch_targets_cannot_span_git_root_and_foreign_path(self):
        hook = self.parent_patch_hook(str(self.repository / "other" / "result.txt"))
        hook["cwd"] = str(self.root)
        hook["tool_input"]["command"] = (
            "*** Begin Patch\n"
            f"*** Add File: {self.repository / 'other' / 'result.txt'}\n"
            "+inside\n"
            f"*** Add File: {self.root / 'foreign.txt'}\n"
            "+outside\n"
            "*** End Patch"
        )

        denied = writer_lease_guard.pre_tool_use(self.store, hook)

        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("escapes the Git root", denied["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 0)

    def test_tampered_writer_claim_is_quarantined_and_blocks_capture(self):
        writer_lease_guard.pre_tool_use(
            self.store,
            self.parent_patch_hook(),
        )
        claim_path = next((self.store.root / "writer_claim").glob("*.json"))
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        claim["paths"] = ["other/result.txt"]
        claim_path.write_text(json.dumps(claim), encoding="utf-8")

        blocked = self.capture(self.spawn_hook())

        self.assertEqual(blocked["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("hash does not match", blocked["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 0)
        self.assertEqual(len(list((self.store.root / "quarantine").glob("*.json"))), 1)
        self.assertEqual(len(list((self.store.root / "pending").glob("*.json"))), 0)

    def test_unknown_apply_patch_shape_fails_closed_without_claim(self):
        hook = self.parent_patch_hook("other/result.txt")
        hook["tool_input"] = {"command": "not a structured patch"}

        result = writer_lease_guard.pre_tool_use(self.store, hook)

        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("envelope is not exact", result["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(len(list((self.store.root / "writer_claim").glob("*.json"))), 0)

    def test_nested_parent_path_derives_exact_child_agent_path(self):
        self.write_meta(
            self.parent_transcript,
            session_id="runtime-session",
            thread_id="parent-thread",
            parent_thread_id="runtime-session",
            agent_role="default",
            agent_path="/root/parent_task",
        )
        hook = self.spawn_hook(agent_id="parent-thread", agent_type="default")

        self.capture(hook)
        pending = next((self.store.root / "pending").glob("*.json"))
        capsule = json.loads(pending.read_text(encoding="utf-8"))["capsule"]

        self.assertEqual(capsule["canonical_agent_path"], "/root/parent_task/bounded_task")

    def test_executable_pretooluse_identity_failure_returns_explicit_deny(self):
        child = self.child_hook()
        child.update(
            {
                "hook_event_name": "PreToolUse",
                "transcript_path": str(self.root / "missing-child.jsonl"),
                "tool_name": "view_image",
                "tool_input": {},
                "tool_use_id": "missing-child-read",
            }
        )

        completed = self.invoke_hook_cli(child)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertIn(
            "TASK.AUTHORITY_BLOCKED",
            output["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_executable_precompact_failure_stops_before_compaction(self):
        child = self.child_hook()
        child.update(
            {
                "hook_event_name": "PreCompact",
                "transcript_path": str(self.root / "missing-child.jsonl"),
                "trigger": "auto",
            }
        )

        completed = self.invoke_hook_cli(child)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertIs(output["continue"], False)
        self.assertIn("TASK.AUTHORITY_BLOCKED", output["stopReason"])

    def test_executable_subagentstop_identity_failure_requests_continuation(self):
        completed = self.invoke_hook_cli(
            {
                "hook_event_name": "SubagentStop",
                "session_id": "runtime-session",
                "agent_id": "missing-child",
                "agent_type": "fixture_worker",
                "transcript_path": str(self.parent_transcript),
                "agent_transcript_path": str(self.root / "missing-child.jsonl"),
                "last_assistant_message": None,
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("TASK.FINAL_ATTESTATION_REQUIRED", output["reason"])

    def test_executable_subagentstart_identity_failure_is_context_lost(self):
        child = self.child_hook()
        child["transcript_path"] = str(self.root / "missing-child.jsonl")

        completed = self.invoke_hook_cli(child)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TASK.CONTEXT_LOST", context)
        self.assertIn("Do not call tools or claim completion", context)
        self.assertIn(
            "Return exactly TASK.CONTEXT_LOST and no other text", context
        )

    def test_executable_invalid_json_uses_blocking_exit_code(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(HOOK_SCRIPT),
                "--state-directory",
                str(self.store.root),
                "--plaintext-agent-type",
                "fixture_worker",
            ],
            input="not-json",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid JSON", completed.stderr)

    def test_top_level_failure_shapes_are_event_specific(self):
        error = compatibility_state.StateError("fixture state failure")

        pre_tool = compatibility_hook.fail_closed_output("PreToolUse", error)
        self.assertEqual(
            pre_tool["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        pre_compact = compatibility_hook.fail_closed_output("PreCompact", error)
        self.assertIs(pre_compact["continue"], False)
        post_tool = compatibility_hook.fail_closed_output("PostToolUse", error)
        self.assertIs(post_tool["continue"], False)
        stop = compatibility_hook.fail_closed_output("SubagentStop", error)
        self.assertEqual(stop["decision"], "block")
        start = compatibility_hook.fail_closed_output("SubagentStart", error)
        self.assertIn(
            "SubagentStart cannot itself cancel this child",
            start["hookSpecificOutput"]["additionalContext"],
        )
        self.assertIn(
            "return exactly TASK.CONTEXT_LOST and no other text",
            start["hookSpecificOutput"]["additionalContext"],
        )

    def test_executable_hook_runs_capture_claim_recovery_and_final_lifecycle(self):
        spawn = self.spawn_hook(tool_name="collaborationspawn_agent")
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
            dict(
                child,
                hook_event_name="PreToolUse",
                tool_name="view_image",
                tool_use_id="child-read-one",
                tool_input={},
            )
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        checked_output = json.loads(checked.stdout)
        checked_context = checked_output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("recovery_count=1", checked_context)
        self.assertIn("BEGIN CODEX WORKER FINAL ATTESTATION SEED", checked_context)
        self.assertIn('"recovery_count":1', checked_context)
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
        chain = hook_event_receipts.load_chain(self.store.root)
        events = chain["events"]
        self.assertEqual(
            [(event["hook_event_name"], event["scope"]) for event in events],
            [
                ("PreToolUse", "target_spawn"),
                ("SubagentStart", "target_child"),
                ("PreCompact", "target_child"),
                ("PreToolUse", "target_child"),
                ("SubagentStop", "target_child"),
            ],
        )
        self.assertEqual(events[0]["actor"]["canonical_agent_path"], "/root")
        for event in events[1:]:
            self.assertEqual(
                event["actor"]["canonical_agent_path"],
                "/root/bounded_task",
            )
        serialized_chain = compatibility_state.canonical_json(chain)
        self.assertNotIn(spawn["tool_input"]["message"].encode(), serialized_chain)
        self.assertNotIn(message.encode(), serialized_chain)


if __name__ == "__main__":
    unittest.main()
