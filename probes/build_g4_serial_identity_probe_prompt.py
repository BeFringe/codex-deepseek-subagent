#!/usr/bin/env python3

"""Build a provider-free prompt for one two-child serial G4 identity probe."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROBE_DIRECTORY = Path(__file__).resolve().parent
if str(PROBE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROBE_DIRECTORY))

from build_g4_native_probe_prompt import (  # noqa: E402
    AGENT_TYPE,
    ProbePromptError,
    TASK_NAME_RE,
    build_prompt,
    clean_git_location,
)


DEFAULT_TASK_NAMES = (
    "g4_serial_identity_a1",
    "g4_serial_identity_b1",
)
CHILD_ASSIGNMENT_MARKER = "\nEXACT CHILD ASSIGNMENT:\n\n"


def _child_assignment(root: Path, task_name: str) -> str:
    prompt = build_prompt(root, task_name, child_tool="list_agents")
    try:
        assignment = prompt.split(CHILD_ASSIGNMENT_MARKER, 1)[1]
    except IndexError as error:
        raise ProbePromptError("single-child prompt has no exact assignment") from error
    return assignment.rstrip("\n")


def build_serial_prompt(root: Path, task_names: tuple[str, str]) -> str:
    if len(task_names) != 2:
        raise ProbePromptError("serial identity probe requires exactly two task names")
    if len(set(task_names)) != len(task_names):
        raise ProbePromptError("serial identity task names must be distinct")
    for task_name in task_names:
        if not TASK_NAME_RE.fullmatch(task_name):
            raise ProbePromptError(
                "task names must contain only lowercase letters, digits, and underscores"
            )

    location = clean_git_location(root)
    resolved_root = Path(str(location["root"]))
    first_name, second_name = task_names
    first_assignment = _child_assignment(resolved_root, first_name)
    second_assignment = _child_assignment(resolved_root, second_name)

    return f"""Perform one product-independent Phase 1/G4 live serial identity probe. You are the native OpenAI parent. Do not edit files, stage, commit, push, change providers, inspect credentials, compact intentionally, or substitute another agent type.

Run exactly this serial lifecycle and call no other tool:

1. Call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={first_name}, fork_turns=none, and message equal to SERIAL CHILD A below, including its terminating authority declaration.
2. Use the native wait/callback path until exactly /root/{first_name} reaches terminal completion and returns its exact final attestation. Do not spawn child B before this callback.
3. Only after child A is terminal, call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={second_name}, fork_turns=none, and message equal to SERIAL CHILD B below, including its terminating authority declaration.
4. Use the native wait/callback path until exactly /root/{second_name} reaches terminal completion and returns its exact final attestation.
5. Report both spawn results, child thread ids, canonical AgentPaths, and exact final results. Do not issue follow-up, send-message, interrupt, cancel, or mutation calls.

If either custom-agent spawn, Hook capture, identity binding, wait, callback, or final attestation fails, report the exact non-secret failure and stop. Never reuse the first child's task name, thread id, assignment id, handoff id, capsule hash, compact hash, or final result for the second child. Do not fall back to default, explorer, worker, or v4.

SERIAL CHILD A ({first_name}):

{first_assignment}

SERIAL CHILD B ({second_name}):

{second_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--task-name",
        action="append",
        dest="task_names",
        help="repeat exactly twice; defaults to the fixed serial qualification pair",
    )
    arguments = parser.parse_args()
    task_names = tuple(arguments.task_names or DEFAULT_TASK_NAMES)
    try:
        prompt = build_serial_prompt(arguments.root, task_names)
    except (OSError, ProbePromptError) as error:
        print(f"G4 serial identity probe prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
