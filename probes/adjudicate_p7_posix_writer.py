#!/usr/bin/env python3

"""Consume one fully checked closed macOS writer run without widening authority."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from verify_p7_posix_mutation_outcome import verify
from adjudicate_g4_sibling_admission_live import one, read_json, require
from compatibility_state import StateStore, compact_invariant_sha256, provenance_policy_sha256
from private_output import open_private_output
from run_p7_posix_mutation import sha256_file
from runtime_guard import collect_git_snapshot, parse_attestation, validate_complete_write_observation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        require(not arguments.output.exists(), "owner receipt already exists")
        require(
            arguments.output.parent.resolve(strict=True)
            == arguments.manifest.parent.resolve(strict=True),
            "owner receipt must stay inside the verified private run directory",
        )
        manifest = read_json(arguments.manifest)
        require(
            manifest.get("mutation_case") == "positive"
            and manifest.get("feasibility_receipt") is not None
            and manifest.get("root_preparation_receipt") is not None,
            "complete bounded writer inputs are absent",
        )
        outcome = verify(arguments.manifest)
        store = StateStore(Path(manifest["state"]))
        report = one(list((store.root / "reported").glob("*.json")), "writer report")
        envelope = store._validated_envelope(report)
        capsule = envelope["capsule"]
        binding = envelope["binding"]
        final = envelope["final_attestation"]
        parsed = parse_attestation(
            "BEGIN CODEX WORKER ATTESTATION\n"
            + json.dumps(final, separators=(",", ":"), sort_keys=True)
            + "\nEND CODEX WORKER ATTESTATION"
        )
        current = collect_git_snapshot(capsule["root"]["path"])
        expected = {
            "assignment_id": capsule["assignment_id"],
            "handoff_id": capsule["handoff_id"],
            "capsule_sha256": capsule["capsule_sha256"],
            "compact_invariant_sha256": compact_invariant_sha256(capsule),
            "canonical_agent_path": binding["canonical_agent_path"],
            "recovery_count": envelope["runtime"]["recovery_count"],
            **current,
            "context_lost": False,
            "authority_violation": False,
            "assigned_slice_complete": True,
            "inventory_summaries": [],
            "verification": [
                {"command": command, "exit_code": 0}
                for command in capsule["verification"]
            ],
        }
        require(all(parsed[key] == value for key, value in expected.items()), "fresh writer attestation mismatch")
        require(
            parsed["authority_provenance"]["policy_sha256"]
            == provenance_policy_sha256(capsule)
            and parsed["authority_provenance"]["worker_claimed_origin"] == "owner_internal"
            and parsed["authority_provenance"]["test_only_injection_used"] is False
            and envelope["runtime"]["first_git_attested_at"] is not None,
            "writer provenance is not independently admissible",
        )
        feasibility = read_json(Path(manifest["feasibility_receipt"]))
        require(
            capsule["execution_contract"]["capsule_feasibility_attestation"]
            == feasibility["attestation"]
            and feasibility["attestation"]["owner_decision"] == "dispatch"
            and feasibility["attestation"]["counterexample_probe"]["executed"] is True
            and feasibility["attestation"]["counterexample_probe"]["counterexample_found"] is False
            and feasibility["attestation"]["bounded_completion"]["mechanism_satisfies"] is True,
            "parent-owned feasibility contract mismatch",
        )
        validate_complete_write_observation(store, binding, capsule, parsed, current)
        require(
            not list((store.root / "writer_claim").glob("*.json"))
            and not list((store.root / "active").glob("*.json"))
            and not list((store.root / "pending").glob("*.json"))
            and not list((store.root / "claimed").glob("*.json")),
            "in-flight authority remains",
        )
        adjudication = {
            key: "pass"
            for key in (
                "location_integrity",
                "mutation_scope_integrity",
                "verification_freshness",
                "derivation_provenance_integrity",
                "feasibility_contract_integrity",
            )
        }
        adjudication["evidence_sha256"] = sha256_file(arguments.manifest)
        consumed = store.adjudicate_parent(capsule["assignment_id"], adjudication)
        require(
            consumed == store.path("consumed", capsule["assignment_id"])
            and consumed.is_file()
            and not report.exists(),
            "authority consumption failed",
        )
        result = {
            "schema": 1,
            "classification": "fresh_owner_exact_closed_macos_writer",
            "fresh_adjudicator_pid": os.getpid(),
            "manifest_sha256": sha256_file(arguments.manifest),
            "assignment_id": capsule["assignment_id"],
            "consumed_sha256": sha256_file(consumed),
            "adjudication": adjudication,
            "outcome": outcome,
            "authority_consumed": True,
            "exact_closed_writer_run_qualified": True,
            "scope": "one native OpenAI parent, one DeepSeek child, one exact owned addition, then bounded close",
            "native_parent_writer_exclusion_qualified": False,
            "native_sibling_live_qualified": False,
            "direct_write_qualified": False,
            "phase1_complete": False,
            "p7_complete": False,
            "global_process_tree_qualified": False,
            "phase2_state": "closed",
            "phase3_state": "closed",
        }
        descriptor = open_private_output(arguments.output)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"authority_consumed": True, "output": str(arguments.output)}))
        return 0
    except Exception as error:
        print(json.dumps({"authority_consumed": False, "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
