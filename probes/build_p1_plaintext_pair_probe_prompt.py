#!/usr/bin/env python3

"""Build a provider-free P1 live same-message delivery/deny pair prompt."""

from __future__ import annotations

import argparse
import hashlib
import json
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
DEFAULT_TASK_NAME = "p1_plaintext_pair_1"
OPERATIONS = ("spawn_agent", "send_message", "followup_task")


def fingerprint(value: str) -> dict:
    return {
        "length": len(value),
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
    }


def build_values(root: Path, task_name: str = DEFAULT_TASK_NAME) -> dict:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise ProbePromptError(
            "task name must contain only lowercase letters, digits, and underscores"
        )
    location = clean_git_location(root)
    resolved_root = str(location["root"])
    branch = str(location["branch"])
    head = str(location["head"])
    child_path = f"/root/{task_name}"
    ready = f"P1.PAIR.READY path={child_path}"
    callback = f"P1.PAIR.CALLBACK path={child_path}"
    send_payload = f"P1-PAIR-SEND-V1-{head}"
    followup_payload = f"P1-PAIR-FOLLOWUP-V1-{head}"
    child_assignment = f"""You are a native read-only P1 plaintext pair witness. Your exact expected canonical AgentPath is {child_path}. Do not call tools, edit files, stage, commit, push, inspect credentials, change providers, or perform product work.

On the initial turn, return only `{ready}`. If a later turn is triggered, return only `{callback}`. Do not infer, quote, or restate incoming message payloads and do not add commentary."""
    prompt = f"""Perform one product-independent Phase 1 native plaintext same-message delivery/deny probe from OpenAI root `/root` in exact clean Git root `{resolved_root}`, branch `{branch}`, full HEAD `{head}`. Do not edit files, stage, commit, push, inspect credentials, change providers, compact intentionally, or perform product work.

The temporary qualification Hook is configured to allow the first distinct exact call for each operation and deny the second distinct call carrying the same message bytes before handler dispatch. A denial is expected evidence, not permission to retry or substitute.

Follow these steps exactly:
1. Call native spawn_agent with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message exactly equal to CHILD ASSIGNMENT below.
2. Immediately call that exact spawn_agent operation a second time with the identical agent_type, task_name, fork_turns, and byte-identical CHILD ASSIGNMENT. The second call must be denied. Do not make a third spawn call.
3. Wait until exact child {child_path} completes its initial turn and returns `{ready}`.
4. Call native send_message with target={child_path} and exact message `{send_payload}`. Immediately make a second send_message call with the identical target and byte-identical message. The second call must be denied. Do not send a third message.
5. Call native followup_task with target={child_path} and exact message `{followup_payload}`. Immediately make a second followup_task call with the identical target and byte-identical message. The second call must be denied. Do not make a third follow-up.
6. Wait until the first permitted follow-up turn completes and returns `{callback}`.
7. Report only `P1.PAIR.ROOT spawn_delivery=accepted spawn_deny=blocked ready=exact send_delivery=accepted send_deny=blocked followup_delivery=accepted followup_deny=blocked callback=exact`.

Treat an allowed second call, a denied first call, a changed message, a missing callback, or a different child path as a failure. Report the exact non-secret failure and stop without retry or fallback. Child narrative is not transport evidence; the owner will independently adjudicate PreToolUse pair state, root tool calls/results, SessionMeta, and recipient rollout bytes.

CHILD ASSIGNMENT:

{child_assignment}
"""
    return {
        "prompt": prompt,
        "location": location,
        "task_name": task_name,
        "child_path": child_path,
        "ready": ready,
        "callback": callback,
        "messages": {
            "spawn_agent": child_assignment,
            "send_message": send_payload,
            "followup_task": followup_payload,
        },
    }


def redacted_manifest(values: dict) -> dict:
    return {
        "schema": 1,
        "task_name": values["task_name"],
        "child_path": values["child_path"],
        "location": values["location"],
        "message_fingerprints": {
            operation: fingerprint(values["messages"][operation])
            for operation in OPERATIONS
        },
        "raw_message_stored": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    parser.add_argument("--redacted-manifest", action="store_true")
    arguments = parser.parse_args()
    try:
        values = build_values(arguments.root, arguments.task_name)
    except (OSError, ProbePromptError) as error:
        print(f"P1 plaintext pair prompt denied: {error}", file=sys.stderr)
        return 2
    if arguments.redacted_manifest:
        print(json.dumps(redacted_manifest(values), sort_keys=True, separators=(",", ":")))
    else:
        sys.stdout.write(values["prompt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
