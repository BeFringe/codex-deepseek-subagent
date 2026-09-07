#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import sys


REQUIRED_GATES = {
    "P1",
    "P2",
    "P3",
    "P4",
    "P5",
    "P5a",
    "P5b",
    "P6",
    "P6a",
    "P6b",
    "P6c",
    "P7",
}
REQUIRED_EXIT_RECEIPTS = {
    "sessionmeta_identity",
    "mutation_visibility",
    "sandbox_block",
    "callback_continuity",
    "termination_quiescence",
    "posix_live",
    "windows_live",
    "deepseek_regression",
    "install_rollback",
}
PROGRESS_STATES = {"pending", "partial", "qualified"}
PROVIDER_FREE_STATES = {"pending", "partial", "pass"}
PHASE_STATES = {"closed", "open", "complete"}
REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GOAL_CONTRACT = {
    "state": "active_fail_closed",
    "terminal_acceptance_unchanged": True,
    "app_server_source_adjustment": {
        "gate": "P4",
        "surface": "host_control_plane",
        "required_proofs": [
            "client_connection_authority",
            "native_child_reachability_or_separation",
            "sandbox_and_mutation_mediation",
            "trusted_parent_or_host_sandbox_receipt",
            "external_worker_bootstrap_denial_or_os_confinement",
            "process_tree_quiescence_barrier",
        ],
        "may_substitute_native_child_lifecycle": False,
    },
    "unchanged_native_lifecycle_requirements": [
        "canonical_agentpath",
        "wait",
        "callback",
        "cancel",
        "multi_agent_v2",
    ],
}


def _index_exact(values, required, label):
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list")
    if any(not isinstance(value, dict) for value in values):
        raise ValueError(f"{label} entries must be objects")
    if any(not isinstance(value.get("id"), str) or not value["id"] for value in values):
        raise ValueError(f"{label} entries must have string ids")
    by_id = {value.get("id"): value for value in values}
    if len(by_id) != len(values):
        raise ValueError(f"{label} contains duplicate ids")
    if set(by_id) != required:
        missing = sorted(required - set(by_id))
        extra = sorted(set(by_id) - required)
        raise ValueError(f"{label} mismatch: missing={missing}, extra={extra}")
    return by_id


def _validate_evidence(entries, label):
    for entry in entries.values():
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{label} {entry['id']} must name evidence")
        if any(not isinstance(value, str) or not value for value in evidence):
            raise ValueError(f"{label} {entry['id']} has invalid evidence")


def load_status(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("phase gate has an invalid schema")
    if value.get("goal_contract") != EXPECTED_GOAL_CONTRACT:
        raise ValueError("Phase 1 goal contract drifted or substituted App Server authority")

    phase1 = value.get("phase1")
    phase2 = value.get("phase2")
    phase3 = value.get("phase3")
    if not all(isinstance(phase, dict) for phase in (phase1, phase2, phase3)):
        raise ValueError("phase gate is missing a phase object")

    gates = _index_exact(phase1.get("gates"), REQUIRED_GATES, "Phase 1 gates")
    receipts = _index_exact(
        phase1.get("exit_receipts"), REQUIRED_EXIT_RECEIPTS, "Phase 1 exit receipts"
    )
    _validate_evidence(gates, "gate")
    _validate_evidence(receipts, "exit receipt")

    for gate in gates.values():
        if gate.get("state") not in PROGRESS_STATES:
            raise ValueError(f"gate {gate['id']} has an invalid state")
        if gate.get("provider_free") not in PROVIDER_FREE_STATES:
            raise ValueError(f"gate {gate['id']} has an invalid provider-free state")
        if gate["state"] != "qualified" and not gate.get("blocker"):
            raise ValueError(f"gate {gate['id']} must name its unresolved blocker")

    for receipt in receipts.values():
        if receipt.get("state") not in PROGRESS_STATES:
            raise ValueError(f"exit receipt {receipt['id']} has an invalid state")

    phase1_complete = all(
        gate["state"] == "qualified" and gate["provider_free"] == "pass"
        for gate in gates.values()
    ) and all(receipt["state"] == "qualified" for receipt in receipts.values())
    direct_write_qualified = phase1_complete

    if phase1.get("declared_complete") is not phase1_complete:
        raise ValueError("declared Phase 1 completion disagrees with required gates")
    if phase1.get("declared_direct_write_qualified") is not direct_write_qualified:
        raise ValueError("declared direct-write qualification disagrees with G4")

    if phase2.get("state") not in PHASE_STATES or phase3.get("state") not in PHASE_STATES:
        raise ValueError("future phase has an invalid state")
    if phase2.get("requires") != "phase1_complete":
        raise ValueError("Phase 2 must require Phase 1 completion")
    if phase3.get("requires") != "phase2_complete":
        raise ValueError("Phase 3 must require Phase 2 completion")
    if not phase1_complete and phase2["state"] != "closed":
        raise ValueError("Phase 2 must remain closed until Phase 1 completes")
    if phase2["state"] != "complete" and phase3["state"] != "closed":
        raise ValueError("Phase 3 must remain closed until Phase 2 completes")

    for name, phase in (("Phase 2", phase2), ("Phase 3", phase3)):
        contract = phase.get("contract")
        if not isinstance(contract, str) or not (REPO_ROOT / contract).is_file():
            raise ValueError(f"{name} contract is missing")

    return value, gates, receipts, phase1_complete, direct_write_qualified


def qualification(path):
    value, gates, receipts, phase1_complete, direct_write_qualified = load_status(path)
    blockers = [
        {"id": gate["id"], "state": gate["state"], "blocker": gate.get("blocker")}
        for gate in gates.values()
        if gate["state"] != "qualified" or gate["provider_free"] != "pass"
    ]
    receipt_blockers = [
        {"id": receipt["id"], "state": receipt["state"]}
        for receipt in receipts.values()
        if receipt["state"] != "qualified"
    ]
    return {
        "valid": True,
        "as_of": value.get("as_of"),
        "phase1_complete": phase1_complete,
        "direct_write_qualified": direct_write_qualified,
        "phase2": value["phase2"]["state"],
        "phase3": value["phase3"]["state"],
        "gate_blockers": blockers,
        "exit_receipt_blockers": receipt_blockers,
    }


def main():
    default_status = Path(__file__).with_name("phase1-g4-status.json")
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", type=Path, default=default_status)
    parser.add_argument("--require-phase1-complete", action="store_true")
    arguments = parser.parse_args()

    try:
        result = qualification(arguments.status)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1

    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if arguments.require_phase1_complete and not result["phase1_complete"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
