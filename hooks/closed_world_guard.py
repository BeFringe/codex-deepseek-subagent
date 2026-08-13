#!/usr/bin/env python3

"""Mechanical closed-registry and cross-object relation adjudication fixtures."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from compatibility_state import registry_items_sha256


class ClosedWorldViolation(RuntimeError):
    pass


def mechanical_registry_summary(
    registry: Mapping[str, object], item_ids: Sequence[str]
) -> dict:
    expected = registry["closed_item_ids"]
    if list(item_ids) != expected:
        raise ClosedWorldViolation("returned item ids do not exactly match the closed registry")
    return {
        "registry_id": registry["registry_id"],
        "declared_count": len(expected),
        "item_ids": list(expected),
        "items_sha256": registry_items_sha256(expected),
    }


def validate_object_rows(rows: Sequence[Mapping[str, object]], schema_fields: Sequence[str]) -> None:
    expected = set(schema_fields)
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != expected:
            raise ClosedWorldViolation("object row does not match its exact schema")


def validate_closed_relation(
    contract: Mapping[str, object],
    *,
    owners: Sequence[Mapping[str, object]],
    handoffs: Sequence[Mapping[str, object]],
) -> dict:
    """Validate row codecs first, then enforce the closed one-to-one relation."""
    validate_object_rows(owners, contract["owner_schema_fields"])
    validate_object_rows(handoffs, contract["handoff_schema_fields"])
    owner_id_field = contract["owner_id_field"]
    handoff_id_field = contract["handoff_id_field"]
    handoff_owner_id_field = contract["handoff_owner_id_field"]
    terminal_field = contract["terminal_state_field"]
    allowed_terminal = {"tombstone", "clear"}

    owner_ids = [row[owner_id_field] for row in owners]
    handoff_ids = [row[handoff_id_field] for row in handoffs]
    if any(not isinstance(value, str) or not value for value in owner_ids + handoff_ids):
        raise ClosedWorldViolation("relation object id is invalid")
    if len(owner_ids) != len(set(owner_ids)) or len(handoff_ids) != len(set(handoff_ids)):
        raise ClosedWorldViolation("relation object id is duplicated")

    active_owners = {}
    for row in owners:
        terminal = row[terminal_field]
        if terminal is None:
            active_owners[row[owner_id_field]] = row
        elif terminal not in allowed_terminal:
            raise ClosedWorldViolation("owner terminal absence state is not allowed")

    references = Counter()
    for row in handoffs:
        terminal = row[terminal_field]
        owner_id = row[handoff_owner_id_field]
        if terminal is None:
            if not isinstance(owner_id, str) or owner_id not in active_owners:
                raise ClosedWorldViolation("nonterminal handoff has a missing owner relation")
            references[owner_id] += 1
        else:
            if terminal not in allowed_terminal:
                raise ClosedWorldViolation("handoff terminal absence state is not allowed")
            if owner_id is not None:
                raise ClosedWorldViolation("terminal handoff absence exception must clear its owner relation")

    orphaned = sorted(owner_id for owner_id in active_owners if references[owner_id] == 0)
    multiply_linked = sorted(owner_id for owner_id, count in references.items() if count != 1)
    if orphaned:
        raise ClosedWorldViolation(f"nonterminal owner relation is orphaned: {orphaned}")
    if multiply_linked:
        raise ClosedWorldViolation(f"nonterminal owner cardinality is not one-to-one: {multiply_linked}")
    return {
        "relation_id": contract["relation_id"],
        "owner_count": len(owners),
        "handoff_count": len(handoffs),
        "active_relation_count": len(active_owners),
        "closed": True,
    }
