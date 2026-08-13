import importlib.util
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[1]


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
closed_world_guard = load_module(
    "closed_world_guard", REPO / "hooks" / "closed_world_guard.py"
)


class ClosedWorldGuardTests(unittest.TestCase):
    def setUp(self):
        self.registry = {
            "registry_id": "test-id-inventory",
            "closed_item_ids": [
                "group-a-1",
                "group-a-2",
                "group-b-1",
                "group-c-1",
            ],
            "count_authority": "mechanical_cardinality_only",
        }
        self.relation = {
            "relation_id": "owner-handoff",
            "owner_schema_fields": ["owner_id", "terminal_state", "payload"],
            "handoff_schema_fields": [
                "handoff_id",
                "owner_id",
                "terminal_state",
                "payload",
            ],
            "owner_id_field": "owner_id",
            "handoff_id_field": "handoff_id",
            "handoff_owner_id_field": "owner_id",
            "terminal_state_field": "terminal_state",
            "referential_cardinality": "exactly_one_to_one_nonterminal",
            "absence_semantics": "missing_or_orphan_relation_is_error",
            "allowed_terminal_absence": "tombstone_or_clear_only",
        }

    def test_declared_count_is_mechanically_recomputed_from_closed_items(self):
        summary = closed_world_guard.mechanical_registry_summary(
            self.registry, self.registry["closed_item_ids"]
        )

        self.assertEqual(summary["declared_count"], 4)
        self.assertEqual(summary["item_ids"], self.registry["closed_item_ids"])

    def test_valid_item_ids_with_drifted_aggregate_are_not_accepted(self):
        narrative_declared_count = 3
        summary = closed_world_guard.mechanical_registry_summary(
            self.registry, self.registry["closed_item_ids"]
        )

        self.assertNotEqual(narrative_declared_count, summary["declared_count"])

    def test_row_codecs_can_pass_while_missing_relation_fails(self):
        owners = [
            {"owner_id": "owner-1", "terminal_state": None, "payload": "valid"},
            {"owner_id": "owner-2", "terminal_state": None, "payload": "valid"},
        ]
        handoffs = [
            {
                "handoff_id": "handoff-1",
                "owner_id": "owner-1",
                "terminal_state": None,
                "payload": "valid",
            }
        ]
        closed_world_guard.validate_object_rows(
            owners, self.relation["owner_schema_fields"]
        )
        closed_world_guard.validate_object_rows(
            handoffs, self.relation["handoff_schema_fields"]
        )

        with self.assertRaisesRegex(
            closed_world_guard.ClosedWorldViolation, "orphaned"
        ):
            closed_world_guard.validate_closed_relation(
                self.relation, owners=owners, handoffs=handoffs
            )

    def test_missing_owner_and_many_to_one_relations_fail_closed(self):
        owners = [
            {"owner_id": "owner-1", "terminal_state": None, "payload": "valid"}
        ]
        missing = [
            {
                "handoff_id": "handoff-1",
                "owner_id": "missing-owner",
                "terminal_state": None,
                "payload": "valid",
            }
        ]
        with self.assertRaisesRegex(
            closed_world_guard.ClosedWorldViolation, "missing owner"
        ):
            closed_world_guard.validate_closed_relation(
                self.relation, owners=owners, handoffs=missing
            )

        many = [
            {
                "handoff_id": f"handoff-{index}",
                "owner_id": "owner-1",
                "terminal_state": None,
                "payload": "valid",
            }
            for index in (1, 2)
        ]
        with self.assertRaisesRegex(
            closed_world_guard.ClosedWorldViolation, "not one-to-one"
        ):
            closed_world_guard.validate_closed_relation(
                self.relation, owners=owners, handoffs=many
            )

    def test_only_tombstone_or_clear_can_exempt_absent_terminal_relation(self):
        owners = [
            {"owner_id": "owner-1", "terminal_state": "tombstone", "payload": "valid"}
        ]
        handoffs = [
            {
                "handoff_id": "handoff-1",
                "owner_id": None,
                "terminal_state": "clear",
                "payload": "valid",
            }
        ]

        result = closed_world_guard.validate_closed_relation(
            self.relation, owners=owners, handoffs=handoffs
        )
        self.assertTrue(result["closed"])

        handoffs[0]["terminal_state"] = "deleted"
        with self.assertRaisesRegex(
            closed_world_guard.ClosedWorldViolation, "not allowed"
        ):
            closed_world_guard.validate_closed_relation(
                self.relation, owners=owners, handoffs=handoffs
            )


if __name__ == "__main__":
    unittest.main()
