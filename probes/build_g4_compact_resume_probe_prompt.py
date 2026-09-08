#!/usr/bin/env python3

"""Build one live G4 child prompt that requires a post-compaction tool call."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROBE_DIRECTORY = Path(__file__).resolve().parent
if str(PROBE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROBE_DIRECTORY))

from build_g4_native_probe_prompt import (  # noqa: E402
    AGENT_TYPE,
    ProbePromptError,
    TASK_NAME_RE,
    authority_declaration,
    clean_git_location,
)


VERIFICATION = "native three-step list_agents compact-resume probe"


def build_prompt(root: Path, task_name: str) -> str:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise ProbePromptError(
            "task name must contain only lowercase letters, digits, and underscores"
        )
    location = clean_git_location(root)
    authority = authority_declaration(location, child_tool="list_agents")
    authority["stop_condition"] = (
        "call native list_agents exactly three times sequentially, observe at least one "
        "PreCompact epoch increment before the third result, call no other tool, then "
        "return only the exact final attestation"
    )
    authority["verification"] = [VERIFICATION]
    authority["execution_contract"]["required_invariants"] = [
        "exact SessionMeta and canonical AgentPath binding",
        "three sequential read-only list_agents calls and no mutation",
        "at least one PreCompact epoch followed by a PreToolUse re-attestation",
    ]
    canonical_agent_path = f"/root/{task_name}"
    assignment = f"""You are the target G4 compact/resume qualification child. Treat each Hook-delivered capsule, compact invariant, and final-attestation seed as the only authority.

Call native list_agents exactly three times, sequentially, and call no other tool. Wait for each result before making the next call. After the third result, use only the most recent Hook-delivered final-attestation seed. Require its recovery_count to be greater than zero; this proves a PreCompact epoch occurred and a later PreToolUse re-attested the same durable capsule. If no incremented recovery_count is visible, set context_lost=true and assigned_slice_complete=false rather than inventing a recovery.

Return only an exact BEGIN/END CODEX WORKER ATTESTATION envelope. Map seed keys exactly: assignment_id, handoff_id, capsule_sha256, compact_invariant_sha256, canonical_agent_path, recovery_count, and authority_provenance.policy_sha256. The expected AgentPath is {canonical_agent_path}. The exact clean Git snapshot is root {location['root']}, branch {location['branch']}, head {location['head']}, index_changed false, empty git_status_short, and empty changed_paths. Verification contains one record with command `{VERIFICATION}` and exit_code 0 only if all three calls succeeded and recovery_count is greater than zero. Set worker_claimed_origin=owner_internal only for your own three list_agents observations, test_only_injection_used=false, derivation_receipt_sha256=null, inventory_summaries=[], authority_violation=false, and assigned_slice_complete=true only when every exact fact remains available.

BEGIN CODEX WORKER AUTHORITY
{json.dumps(authority, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}
END CODEX WORKER AUTHORITY"""
    return f"""Perform one product-independent Phase 1/G4 live child compact/resume probe. You are the native OpenAI parent. The isolated host has configured a fixed auto-compaction threshold. Do not edit files, stage, commit, push, change providers, inspect credentials, request manual compaction, or use another agent type.

Call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message exactly equal to the child assignment below. Then use only native wait/callback until that exact child returns. Report the spawn identity and exact child final. If spawn, Hook identity, PreCompact, post-compact re-attestation, or final adjudication fails, report the exact non-secret failure and stop; do not retry or fall back to another role.

EXACT CHILD ASSIGNMENT:

{assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", default="g4_compact_resume_1")
    arguments = parser.parse_args()
    try:
        prompt = build_prompt(arguments.root, arguments.task_name)
    except (OSError, ProbePromptError) as error:
        print(f"G4 compact/resume prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
