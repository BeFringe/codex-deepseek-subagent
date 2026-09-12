#!/usr/bin/env python3

"""Build a provider-free root -> native scout -> G4 child identity probe."""

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


OUTER_AGENT_TYPE = "explorer"
DEFAULT_OUTER_TASK_NAME = "g4_nested_parent_1"
DEFAULT_INNER_TASK_NAME = "g4_nested_identity_1"
CHILD_ASSIGNMENT_MARKER = "\nEXACT CHILD ASSIGNMENT:\n\n"


def _inner_assignment(root: Path, outer_task_name: str, inner_task_name: str) -> str:
    prompt = build_prompt(
        root,
        inner_task_name,
        parent_agent_path=f"/root/{outer_task_name}",
        child_tool="list_agents",
    )
    try:
        assignment = prompt.split(CHILD_ASSIGNMENT_MARKER, 1)[1]
    except IndexError as error:
        raise ProbePromptError("nested child prompt has no exact assignment") from error
    return assignment.rstrip("\n")


def build_nested_prompt(
    root: Path,
    outer_task_name: str = DEFAULT_OUTER_TASK_NAME,
    inner_task_name: str = DEFAULT_INNER_TASK_NAME,
) -> str:
    for label, value in (
        ("outer task name", outer_task_name),
        ("inner task name", inner_task_name),
    ):
        if not TASK_NAME_RE.fullmatch(value):
            raise ProbePromptError(
                f"{label} must contain only lowercase letters, digits, and underscores"
            )
    if outer_task_name == inner_task_name:
        raise ProbePromptError("outer and inner task names must be distinct")

    location = clean_git_location(root)
    resolved_root = Path(str(location["root"]))
    outer_agent_path = f"/root/{outer_task_name}"
    inner_agent_path = f"{outer_agent_path}/{inner_task_name}"
    inner_assignment = _inner_assignment(
        resolved_root,
        outer_task_name,
        inner_task_name,
    )

    outer_assignment = f"""You are the native read-only parent scout for one nested identity probe. Your exact expected canonical AgentPath is {outer_agent_path}. Do not edit files, stage, commit, push, change providers, inspect credentials, compact intentionally, or perform product work.

Call native spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={inner_task_name}, fork_turns=none, and message equal to NESTED G4 CHILD below, including its terminating authority declaration. Then use only the native wait/callback path until exact child {inner_agent_path} reaches terminal completion. Do not send follow-ups, interrupt, cancel, spawn another child, or call any mutation tool. Return exactly `NESTED.PARENT.CALLBACK outer={outer_agent_path} inner={inner_agent_path}` only after receiving that child's final attestation. If spawn, Hook capture, SessionMeta binding, native tool use, final attestation, or callback fails, report the exact non-secret failure and stop without substitution.

NESTED G4 CHILD ({inner_task_name}):

{inner_assignment}"""

    return f"""Perform one product-independent Phase 1/G4 live nested identity probe. You are the native OpenAI root parent at /root. Do not edit files, stage, commit, push, change providers, inspect credentials, compact intentionally, or perform product work.

Call native spawn_agent exactly once with agent_type={OUTER_AGENT_TYPE}, task_name={outer_task_name}, fork_turns=none, and message equal to NESTED PARENT SCOUT below. Then use only the native wait/callback path until exact scout {outer_agent_path} reaches terminal completion. Do not send follow-ups, interrupt, cancel, spawn another root child, or call any mutation tool. Report the outer spawn result and exact callback. If the scout cannot spawn its one G4 child, report the exact non-secret failure and stop; do not perform the inner spawn yourself and do not substitute another role.

NESTED PARENT SCOUT ({outer_task_name}):

{outer_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--outer-task-name", default=DEFAULT_OUTER_TASK_NAME)
    parser.add_argument("--inner-task-name", default=DEFAULT_INNER_TASK_NAME)
    arguments = parser.parse_args()
    try:
        prompt = build_nested_prompt(
            arguments.root,
            arguments.outer_task_name,
            arguments.inner_task_name,
        )
    except (OSError, ProbePromptError) as error:
        print(f"G4 nested identity probe prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
