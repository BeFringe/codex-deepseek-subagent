#!/usr/bin/env python3

"""Build one provider-free live first-attestation watchdog/cancel prompt."""

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


DEFAULT_TASK_NAME = "g4_first_attestation_timeout_1"
PLAINTEXT_TOOL_NAMESPACE = "g4_assignment"
PRE_WRITE_TIMEOUT_SECONDS = 1
WATCHDOG_DELAY_SECONDS = 2
AUTHORITY_TTL_SECONDS = 120


def _state_directory(value: Path) -> Path:
    if not value.is_absolute():
        raise ProbePromptError("watchdog state directory must be absolute")
    resolved = value.resolve(strict=True)
    if not resolved.is_dir():
        raise ProbePromptError("watchdog state directory must be a directory")
    return resolved


def idle_authority(location: dict[str, object]) -> dict[str, object]:
    authority = authority_declaration(location, child_tool="list_agents")
    authority["stop_condition"] = (
        "remain in the first turn without calling tools until the parent "
        "interrupts after exact watchdog timeout"
    )
    authority["verification"] = [
        "parent observes pre-write-attestation timeout and interrupt acknowledgement"
    ]
    authority["execution_contract"]["required_invariants"] = [
        "exact SessionMeta and canonical AgentPath binding",
        "no child tool call or accepted final before parent watchdog and interrupt",
    ]
    authority["pre_write_attestation_timeout_seconds"] = PRE_WRITE_TIMEOUT_SECONDS
    authority["ttl_seconds"] = AUTHORITY_TTL_SECONDS
    return authority


def build_watchdog_prompt(root: Path, state_directory: Path, task_name: str) -> str:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise ProbePromptError(
            "task name must contain only lowercase letters, digits, and underscores"
        )
    location = clean_git_location(root)
    resolved_root = Path(str(location["root"]))
    resolved_state = _state_directory(state_directory)
    canonical_agent_path = f"/root/{task_name}"
    watchdog = resolved_root / "hooks" / "authority_watchdog.py"
    if not watchdog.is_file() or watchdog.is_symlink():
        raise ProbePromptError("authority watchdog is unavailable or not a regular file")
    authority = idle_authority(location)
    child_assignment = f"""You are the target product-independent Phase 1/G4 P5a first-attestation-timeout child. Remain strictly read-only. Do not call any tool, do not edit, stage, commit, or push, do not inspect credentials, and do not access unrelated product files. Keep this first turn active while the parent runs the exact authority watchdog and interrupts you. Do not return an accepted worker attestation. If the runtime forces a response before interruption, return only WAITING_FOR_PARENT_INTERRUPT so SubagentStop rejects it, then continue without tools. Treat the Hook-delivered capsule and canonical AgentPath {canonical_agent_path} as the only authority.

BEGIN CODEX WORKER AUTHORITY
{json.dumps(authority, ensure_ascii=False, separators=(',', ':'), sort_keys=True)}
END CODEX WORKER AUTHORITY"""

    return f"""Perform one product-independent Phase 1/G4 live first-attestation watchdog/cancel probe. You are the native OpenAI parent. Do not edit files, stage, commit, push, change providers, inspect credentials, compact, or substitute another agent type. The repository must remain clean and the GUI App Server must not be replaced.

Run exactly this lifecycle:

1. Call the exact {PLAINTEXT_TOOL_NAMESPACE}.spawn_agent tool exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message equal to EXACT CHILD ASSIGNMENT below, including its one terminating authority declaration. Do not call collaboration.spawn_agent: its message wire is encrypted and cannot carry this plaintext capsule to PreToolUse.
2. Require the spawn result to expose the staged assignment_id and canonical task path {canonical_agent_path}. If either is absent, report the non-secret failure and stop without guessing an identity.
3. Call exec_command exactly once with cmd `/bin/sleep {WATCHDOG_DELAY_SECONDS}`, workdir `{resolved_root}`, and no shell composition.
4. Call exec_command exactly once with cmd `PYTHONDONTWRITEBYTECODE=1 python3 {watchdog} --state-directory {resolved_state} --assignment-id <the exact staged assignment_id> --fail-on-termination`, workdir `{resolved_root}`. The expected result is exit 2 with valid=true, selection=exact, terminated_count=1, reason=pre_write_attestation_timeout, classification=unresponsive_no_disk_change, and parent_cancel_required=true. Any other result fails the probe closed.
5. Immediately call the exact {PLAINTEXT_TOOL_NAMESPACE}.interrupt_agent tool exactly once with target={canonical_agent_path}. Record its exact previous_status; this is only an interrupt acknowledgement, not termination or mutation-quiescence proof.
6. Call the exact {PLAINTEXT_TOOL_NAMESPACE}.list_agents tool exactly once. Require the exact child to be interrupted or otherwise non-running, then finish without resuming, messaging, following up, waiting, or spawning another child.

The child must make no tool call and reach no accepted final before the watchdog transition. Do not infer strong termination, process-tree quiescence, ownership handover, or Phase 1 completion from interrupt acknowledgement or process absence. If the exact plaintext namespace is unavailable, Hook trust is inactive, capture or binding fails, the child completes before timeout, the exact assignment cannot be selected, or user approval is requested, report the exact non-secret blocker and stop. Do not fall back to collaboration, default, explorer, worker, or v4.

EXACT CHILD ASSIGNMENT:

{child_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    arguments = parser.parse_args()
    try:
        prompt = build_watchdog_prompt(
            arguments.root,
            arguments.state_directory,
            arguments.task_name,
        )
    except (OSError, ProbePromptError) as error:
        print(f"G4 first-attestation watchdog prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
