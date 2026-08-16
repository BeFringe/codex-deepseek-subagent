import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))

from compatibility_state import CorruptState, StateStore
import hook_schema_observation_arm


class HookSchemaObservationArmTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.store = StateStore(self.root / "state")
        self.now = dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def publish(self, arm):
        with self.store.locked():
            self.store._publish(
                self.store.path("hook_schema_observation_arm", "current"),
                arm,
            )

    def test_exact_event_and_unexpired_arm_enable_only_bound_root(self):
        arm = hook_schema_observation_arm.build_arm(
            self.repository,
            ["SubagentStart"],
            now=self.now,
            ttl_seconds=60,
        )
        self.publish(arm)

        root = hook_schema_observation_arm.observation_root_for_event(
            self.store,
            {"hook_event_name": "SubagentStart"},
            now=self.now + dt.timedelta(seconds=30),
        )
        disabled = hook_schema_observation_arm.observation_root_for_event(
            self.store,
            {"hook_event_name": "PreToolUse"},
            now=self.now + dt.timedelta(seconds=30),
        )
        expired = hook_schema_observation_arm.observation_root_for_event(
            self.store,
            {"hook_event_name": "SubagentStart"},
            now=self.now + dt.timedelta(seconds=60),
        )

        self.assertEqual(root, self.repository.resolve())
        self.assertIsNone(disabled)
        self.assertIsNone(expired)

    def test_tamper_and_invalid_ttl_fail_closed(self):
        with self.assertRaisesRegex(CorruptState, "between 1 and 900"):
            hook_schema_observation_arm.build_arm(
                self.repository,
                ["SubagentStart"],
                now=self.now,
                ttl_seconds=901,
            )
        arm = hook_schema_observation_arm.build_arm(
            self.repository,
            ["SubagentStart"],
            now=self.now,
            ttl_seconds=60,
        )
        arm["root"] = str(self.root.resolve())
        self.publish(arm)

        with self.assertRaisesRegex(CorruptState, "hash does not match"):
            hook_schema_observation_arm.observation_root_for_event(
                self.store,
                {"hook_event_name": "SubagentStart"},
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
