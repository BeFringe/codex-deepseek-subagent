#!/usr/bin/env python3

"""Build a provider-free prompt for one two-child concurrent G4 identity probe."""

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
    "g4_concurrent_identity_a1",
    "g4_concurrent_identity_b1",
)
CHILD_ASSIGNMENT_MARKER = "\nEXACT CHILD ASSIGNMENT:\n\n"


def _child_assignment(root: Path, task_name: str) -> str:
    prompt = build_prompt(root, task_name, child_tool="list_agents")
    try:
        assignment = prompt.split(CHILD_ASSIGNMENT_MARKER, 1)[1]
    except IndexError as error:
        raise ProbePromptError("single-child prompt has no exact assignment") from error
    return assignment.rstrip("\n")


def build_concurrent_prompt(root: Path, task_names: tuple[str, str]) -> str:
    if len(task_names) != 2:
        raise ProbePromptError("concurrent identity probe requires exactly two task names")
    if len(set(task_names)) != len(task_names):
        raise ProbePromptError("concurrent identity task names must be distinct")
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

    return f"""Perform one product-independent Phase 1/G4 live concurrent identity probe. You are the native OpenAI parent. Do not edit files, stage, commit, push, change providers, inspect credentials, compact intentionally, or substitute another agent type.

Run exactly this concurrent lifecycle and call no other tool:

1. In one assistant tool-call batch, emit exactly two native spawn_agent calls and no other call. The first must use agent_type={AGENT_TYPE}, task_name={first_name}, fork_turns=none, and message equal to CONCURRENT CHILD A below, including its terminating authority declaration. The second must use agent_type={AGENT_TYPE}, task_name={second_name}, fork_turns=none, and message equal to CONCURRENT CHILD B below, including its terminating authority declaration.
2. Do not call wait_agent until both spawn_agent calls have returned. Do not intentionally serialize the children and do not wait for either child before spawning the other.
3. After both spawn results, use only the native wait/callback path until both exact children have reached terminal completion and returned their exact final attestations. If the first wait returns while one child remains running, call wait_agent again for the remaining callback.
4. Report both spawn results, child thread ids, canonical AgentPaths, and exact final results. Do not issue follow-up, send-message, list-agents, interrupt, cancel, or mutation calls from the parent.

If either custom-agent spawn, Hook capture, identity binding, wait, callback, final attestation, or concurrent overlap fails, report the exact non-secret failure and stop. Never reuse either child's task name, thread id, assignment id, handoff id, capsule hash, compact hash, or final result for the other child. Do not fall back to default, explorer, worker, or v4.

CONCURRENT CHILD A ({first_name}):

{first_assignment}

CONCURRENT CHILD B ({second_name}):

{second_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--task-name",
        action="append",
        dest="task_names",
        help="repeat exactly twice; defaults to the fixed concurrent qualification pair",
    )
    arguments = parser.parse_args()
    task_names = tuple(arguments.task_names or DEFAULT_TASK_NAMES)
    try:
        prompt = build_concurrent_prompt(arguments.root, task_names)
    except (OSError, ProbePromptError) as error:
        print(f"G4 concurrent identity probe prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
