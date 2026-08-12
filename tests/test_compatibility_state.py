import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import importlib.util
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
        },
        "owned_paths": ["owned"],
        "excluded_paths": ["owned/excluded"],
        "git_authority": {
            "stage": False,
            "commit": False,
            "branch": False,
            "push": False,
        },
        "stop_condition": "assigned slice completion only",
        "verification": ["run the provider-free fixture"],
        "preexisting_dirty": [
            {"path": "owned/user.txt", "status": " M", "sha256": "b" * 64}
        ],
        "assignment_sha256": sha256_bytes(assignment.encode("utf-8")),
        "created_at": now.isoformat(),
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
        self.assertEqual(self.store.mark_recovery(value["assignment_id"]), 1)
        self.assertTrue(active.exists())

    def test_post_recovery_reattestation_blocks_path_and_git_expansion(self):
        value, _ = self.activate()
        self.store.mark_recovery(value["assignment_id"])

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
            expires_at=(now - dt.timedelta(minutes=1)).isoformat(),
        )
        value["capsule_sha256"] = capsule_sha256(value)

        with self.assertRaisesRegex(compatibility_state.StateError, "expired"):
            self.store.stage(value, assignment)

        self.assertFalse(self.store.path("pending", value["handoff_id"]).exists())


if __name__ == "__main__":
    unittest.main()
