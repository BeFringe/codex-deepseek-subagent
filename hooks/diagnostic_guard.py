#!/usr/bin/env python3

"""Provider-independent diagnostic fidelity and replay-baseline fixtures."""

from __future__ import annotations

from collections.abc import Mapping


class DiagnosticViolation(RuntimeError):
    pass


def classify_owner_failure(execution_contract: Mapping[str, object], owner_code: object) -> dict:
    """Preserve declared owner codes and use generic only for unclassified failures."""
    diagnostics = execution_contract["diagnostics"]
    if not isinstance(diagnostics, Mapping):
        raise DiagnosticViolation("diagnostic contract is missing")
    stable = diagnostics["stable_failure_codes"]
    generic = diagnostics["generic_unclassified_failure_code"]
    if isinstance(owner_code, str) and owner_code in stable:
        return {
            "owner_failure_code": owner_code,
            "returned_failure_code": owner_code,
            "used_generic_fallback": False,
        }
    return {
        "owner_failure_code": owner_code if isinstance(owner_code, str) else None,
        "returned_failure_code": generic,
        "used_generic_fallback": True,
    }


def require_literal_rerun_authority(execution_contract: Mapping[str, object]) -> None:
    diagnostics = execution_contract["diagnostics"]
    if not isinstance(diagnostics, Mapping) or diagnostics.get(
        "allow_literal_expensive_rerun"
    ) is not True:
        raise DiagnosticViolation("literal expensive rerun is not authorized")


def baseline_reference(execution_contract: Mapping[str, object], baseline_id: str) -> dict:
    """Return evidence metadata without converting it into mutation or completion authority."""
    baselines = execution_contract["proven_input_baselines"]
    matches = [item for item in baselines if item.get("baseline_id") == baseline_id]
    if len(matches) != 1:
        raise DiagnosticViolation("proven input baseline is not uniquely declared")
    baseline = dict(matches[0])
    if baseline.get("non_authorizing") is not True:
        raise DiagnosticViolation("proven input baseline is not non-authorizing")
    return {
        "baseline_id": baseline["baseline_id"],
        "manifest_path": baseline["manifest_path"],
        "sha256": baseline["sha256"],
        "proven_failure_code": baseline["proven_failure_code"],
        "non_authorizing": True,
    }
