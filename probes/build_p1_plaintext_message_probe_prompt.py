#!/usr/bin/env python3

"""Build a provider-free live send_message/followup_task plaintext probe."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROBE_DIRECTORY = Path(__file__).resolve().parent
if str(PROBE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROBE_DIRECTORY))

from build_g4_native_probe_prompt import (  # noqa: E402
    ProbePromptError,
    TASK_NAME_RE,
    clean_git_location,
)


AGENT_TYPE = "explorer"
DEFAULT_TASK_NAME = "p1_plaintext_message_1"


def build_prompt(root: Path, task_name: str = DEFAULT_TASK_NAME) -> str:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise ProbePromptError(
            "task name must contain only lowercase letters, digits, and underscores"
        )

    location = clean_git_location(root)
    resolved_root = str(location["root"])
    branch = str(location["branch"])
    head = str(location["head"])
    child_path = f"/root/{task_name}"
    send_payload = f"P1-PLAINTEXT-SEND-V1-{head}"
    followup_payload = f"P1-PLAINTEXT-FOLLOWUP-V1-{head}"
    ready = f"P1.PLAINTEXT.READY path={child_path}"
    callback = f"P1.PLAINTEXT.CALLBACK path={child_path}"

    child_assignment = f"""You are a native read-only plaintext message transport witness. Your exact expected canonical AgentPath is {child_path}. Do not call tools, edit files, stage, commit, push, inspect credentials, change providers, or perform product work.

On this initial turn, return only `{ready}`. If a later turn is triggered, return only `{callback}`. Do not infer or restate any incoming message payload and do not add commentary."""

    return f"""Perform one product-independent Phase 1 live plaintext message-delivery probe from native OpenAI root `/root` in exact clean Git root `{resolved_root}`, branch `{branch}`, full HEAD `{head}`. Do not edit files, stage, commit, push, inspect credentials, change providers, compact intentionally, or perform product work.

Follow these steps exactly:
1. Call native spawn_agent once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message equal to CHILD ASSIGNMENT below.
2. Wait until exact child {child_path} completes its initial turn and returns `{ready}`.
3. Call native send_message once with target={child_path} and exact message `{send_payload}`. This queue-only call must occur while the child is idle after its initial completed turn.
4. Call native followup_task once with target={child_path} and exact message `{followup_payload}` to trigger the next turn.
5. Wait until that turn completes and returns `{callback}`.
6. Report only `P1.PLAINTEXT.ROOT spawn={child_path} ready=exact send=accepted followup=accepted callback=exact`.

Do not send either payload before the initial turn completes. Do not send another message, follow-up, or spawn. Do not interrupt or cancel. If any exact native step is unavailable or fails, report the exact non-secret failure and stop without substitution. The later child narrative is not transport evidence; the owner will adjudicate the child's rollout item types and exact new user-message bytes independently.

CHILD ASSIGNMENT:

{child_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    arguments = parser.parse_args()
    try:
        prompt = build_prompt(arguments.root, arguments.task_name)
    except (OSError, ProbePromptError) as error:
        print(f"P1 plaintext message probe prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
