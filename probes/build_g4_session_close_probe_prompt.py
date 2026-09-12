#!/usr/bin/env python3

"""Build one provider-free live native session-close prompt."""

from __future__ import annotations

import argparse
import json
import os
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


DEFAULT_TASK_NAME = "g4_session_close_1"
PLAINTEXT_TOOL_NAMESPACE = "g4_assignment"
PRE_WRITE_TIMEOUT_SECONDS = 1
AUTHORITY_TTL_SECONDS = 120


def _state_directory(value: Path) -> Path:
    if not value.is_absolute():
        raise ProbePromptError("session-close state directory must be absolute")
    resolved = value.resolve(strict=True)
    if not resolved.is_dir():
        raise ProbePromptError("session-close state directory must be a directory")
    return resolved


def idle_authority(location: dict[str, object]) -> dict[str, object]:
    authority = authority_declaration(location, child_tool="list_agents")
    authority["stop_condition"] = (
        "remain in the first turn without calling tools until the parent "
        "immediately closes this session"
    )
    authority["verification"] = [
        "parent observes an exact host session-close receipt immediately after spawn"
    ]
    authority["execution_contract"]["required_invariants"] = [
        "exact SessionMeta and canonical AgentPath binding",
        "no child tool call or accepted final before parent close after one live-tree observation",
    ]
    authority["pre_write_attestation_timeout_seconds"] = PRE_WRITE_TIMEOUT_SECONDS
    authority["ttl_seconds"] = AUTHORITY_TTL_SECONDS
    return authority


def build_session_close_prompt(root: Path, state_directory: Path, task_name: str) -> str:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise ProbePromptError(
            "task name must contain only lowercase letters, digits, and underscores"
        )
    location = clean_git_location(root)
    resolved_root = Path(str(location["root"]))
    resolved_state = _state_directory(state_directory)
    canonical_agent_path = f"/root/{task_name}"
    authority = idle_authority(location)
    child_assignment = f"""You are the target product-independent Phase 1/G4 P5b session-close child. Remain strictly read-only. Do not call any tool, do not edit, stage, commit, or push, do not inspect credentials, and do not access unrelated product files. Keep this first turn active while the parent observes the live tree once and immediately closes your session. Do not return an accepted worker attestation. If the runtime forces a response before closure, return only WAITING_FOR_PARENT_CLOSE so SubagentStop rejects it, then continue without tools. Treat the Hook-delivered capsule and canonical AgentPath {canonical_agent_path} as the only authority.

BEGIN CODEX WORKER AUTHORITY
{json.dumps(authority, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}
END CODEX WORKER AUTHORITY"""

    return f"""Perform one product-independent Phase 1/G4 live native session-close probe. You are the native OpenAI parent. Do not edit files, stage, commit, push, change providers, inspect credentials, compact, or substitute another agent type. The repository must remain clean and the GUI App Server must not be replaced.

Run exactly this lifecycle:

1. Call the exact {PLAINTEXT_TOOL_NAMESPACE}.spawn_agent tool exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message equal to EXACT CHILD ASSIGNMENT below, including its one terminating authority declaration. Do not call collaboration.spawn_agent.
2. Require the spawn result to expose the staged assignment_id and canonical task path {canonical_agent_path}. If either is absent, report the non-secret failure and stop without guessing an identity.
3. Without any wait_agent call, call {PLAINTEXT_TOOL_NAMESPACE}.list_agents once and require the exact child to be running. Treat this only as a live-tree observation, not a termination or SubagentStart receipt.
4. Immediately after that observation, call the exact {PLAINTEXT_TOOL_NAMESPACE}.close_agent tool exactly once with target={canonical_agent_path}. Require an exact target_thread_id, target_agent_path={canonical_agent_path}, session_loop_terminated=true, tracked_process_ids_by_thread with exactly the target thread mapped to an empty list, confirmed_exit_process_ids_by_thread with exactly the target thread mapped to an empty list, unconfirmed_exit_process_ids_by_thread with exactly the target thread mapped to an empty list, unresolved_start_process_ids_by_thread with exactly the target thread mapped to an empty list, tracked_process_termination_confirmed=true, closed_catalog_actor_quiescence_claimed=true, and process_tree_quiescence_claimed=false. This proves the captured closed-catalog actor had no tracked or pending unified-exec process at shutdown and its session loop terminated. It is not filesystem, later-spawned, detached, untracked, or global process-tree quiescence proof.
5. Call {PLAINTEXT_TOOL_NAMESPACE}.list_agents once more. Require the exact child to be absent or non-live, then finish without resuming, messaging, following up, waiting, interrupting, or spawning another child.

The child must make no tool call and reach no accepted final before closure. Do not infer mutation quiescence, ownership handover, detached/global process-tree quiescence, or Phase 1 completion from the close receipt. A trusted outer owner will reconcile the durable assignment state separately; do not run a watchdog or synthesize a quiescence receipt inside this session. If the exact plaintext namespace or close_agent is unavailable, Hook trust is inactive, capture or binding fails, the parent inserts a wait before close, the pre-close live-tree observation does not show the child running, any tracked/pending process set is non-empty, tracked termination is unconfirmed, the child completes before closure, the exact assignment cannot be selected, or user approval is requested, report the exact non-secret blocker and stop. Do not fall back to collaboration, default, explorer, worker, or v4.

EXACT CHILD ASSIGNMENT:

{child_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        prompt = build_session_close_prompt(
            arguments.root,
            arguments.state_directory,
            arguments.task_name,
        )
    except (OSError, ProbePromptError) as error:
        print(f"G4 session-close prompt denied: {error}", file=sys.stderr)
        return 2
    if arguments.output is None:
        sys.stdout.write(prompt)
    else:
        try:
            descriptor = os.open(
                arguments.output,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(prompt)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            print(f"G4 session-close prompt was not written: {error}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
