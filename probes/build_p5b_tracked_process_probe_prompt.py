#!/usr/bin/env python3

"""Build one bounded native-worker tracked-process close probe prompt."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


TOOL_NAMESPACE = "g4_assignment"
AGENT_TYPE = "worker"
DEFAULT_TASK_NAME = "p5b_tracked_process_1"
TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")
MARKER_RE = re.compile(r"^codex-g4-p5b-tracked-[0-9a-f]{16}$")
PROCESS_SECONDS = 120
PARENT_WAIT_TIMEOUT_MS = 30_000
CHILD_POLL_TIMEOUT_MS = 60_000


class ProbePromptError(RuntimeError):
    pass


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ProbePromptError(
            f"Git command failed ({' '.join(arguments)}): {result.stderr.strip()}"
        )
    return result.stdout.rstrip("\n")


def clean_git_location(root_value: Path) -> dict[str, str]:
    requested = root_value.resolve(strict=True)
    resolved = Path(_git(requested, "rev-parse", "--show-toplevel")).resolve()
    if resolved != requested:
        raise ProbePromptError("probe root must be the exact Git top level")
    branch = _git(resolved, "symbolic-ref", "--short", "HEAD")
    if not branch:
        raise ProbePromptError("probe requires an attached branch")
    head = _git(resolved, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) is None:
        raise ProbePromptError("probe HEAD is not a full Git object id")
    if _git(resolved, "status", "--short", "--untracked-files=all"):
        raise ProbePromptError("tracked-process probe requires a clean worktree")
    return {"root": str(resolved), "branch": branch, "head": head}


def build_prompt(root: Path, task_name: str, process_marker: str) -> str:
    if TASK_NAME_RE.fullmatch(task_name) is None:
        raise ProbePromptError(
            "task name must contain only lowercase letters, digits, and underscores"
        )
    if MARKER_RE.fullmatch(process_marker) is None:
        raise ProbePromptError("process marker is not the exact bounded form")
    location = clean_git_location(root)
    canonical_path = f"/root/{task_name}"
    process_command = (
        f"python3 -c 'import time; time.sleep({PROCESS_SECONDS})' {process_marker}"
    )

    child_assignment = f"""You are a native OpenAI runtime-termination probe child. This is not a G4 direct-write assignment and grants no filesystem, Git, provider, credential, or integration authority. Work only in the exact disposable root {location['root']} at branch {location['branch']} and full HEAD {location['head']}.

Call functions.exec exactly once. Its JavaScript must make exactly one nested tools.exec_command call with cmd exactly `{process_command}`, workdir exactly `{location['root']}`, yield_time_ms=1000, tty=false, and no approval or sandbox override, then emit only that nested result with text(JSON.stringify(result)). Require the result to contain a still-running numeric session_id. Immediately call functions.exec exactly once more. Its JavaScript must make exactly one nested tools.write_stdin call with that session_id, empty chars, and yield_time_ms={CHILD_POLL_TIMEOUT_MS}, then emit only that nested result with text(JSON.stringify(result)). Make no other outer or nested tool call, do not edit, stage, commit, branch, push, inspect credentials, spawn another process or agent, send a message, or return a final before the parent closes this session. If the command exits before close or either exact nested tool is unavailable, report only the non-secret blocker and do not claim termination qualification."""

    return f"""Perform one product-independent Phase 1/P5b live tracked-process termination probe. You are the native OpenAI parent. This probe exercises the candidate's V2 close receipt only; it does not authorize G4 mutation, integration, provider changes, credential inspection, or GUI App Server selection. Do not edit, stage, commit, branch, push, compact, or start any process yourself. The exact disposable Git baseline is root {location['root']}, branch {location['branch']}, full HEAD {location['head']}.

Run exactly this lifecycle:

1. Call {TOOL_NAMESPACE}.spawn_agent exactly once with agent_type={AGENT_TYPE}, task_name={task_name}, fork_turns=none, and message byte-equal to EXACT CHILD ASSIGNMENT below. Do not use another spawn surface or role.
2. Require the spawn result to expose canonical path {canonical_path}. The current native parent projection may omit the child ThreadId here; do not invent one or treat that known omission as failure. Call {TOOL_NAMESPACE}.wait_agent exactly once with timeout_ms={PARENT_WAIT_TIMEOUT_MS}; this runtime waits over the current child set and has no target argument. Continue only if it times out while the exact child is still running; a completion or final is a failed timing gate.
3. Call {TOOL_NAMESPACE}.list_agents exactly once and require {canonical_path} to be running.
4. Call {TOOL_NAMESPACE}.close_agent exactly once with target={canonical_path}. Require previous_status=running, a nonempty target_thread_id, target_agent_path={canonical_path}, session_loop_terminated=true, model_callable_process_bootstrap_absent=false, tracked_background_processes_before_close=null, and exactly one positive process id under that target_thread_id in tracked_process_ids_by_thread. Require confirmed_exit_process_ids_by_thread to contain that same one id, with empty unconfirmed_exit_process_ids_by_thread and unresolved_start_process_ids_by_thread for the same target. Require tracked_process_termination_confirmed=true, closed_catalog_actor_quiescence_claimed=false, and process_tree_quiescence_claimed=false. Do not infer that target_thread_id from the path: a fresh owner will later join it to the real child SessionMeta.
5. Call {TOOL_NAMESPACE}.list_agents exactly once more and require the child to be absent or non-live. Finish with a compact non-secret report of the spawn path, wait result, close-provided target identity and receipt, and final live-tree observation. Do not retry, follow up, send a message, interrupt, spawn another child, or run a watchdog.

The parent catalog is intentionally closed and therefore does not expose process tools; do not infer the standard worker child's eventual code-mode catalog from the parent's catalog. The exact wrapper enables code-mode hosting only for this bounded read-only child-process probe, while the parent projection remains closed. The child command marker must remain exactly `{process_marker}`. A fresh external host will separately verify that no marked process survives and that the Git baseline stayed unchanged. The close receipt is invalid if the process sets are empty, contain another id, or rely only on terminate acknowledgement. It can prove only the captured tracked-process exit path; it cannot prove detached/untracked/global process-tree quiescence, G4 mutation qualification, Phase 1 completion, or direct write. If the child reports that either required nested process tool is unavailable, the exact child does not start its tracked process before the wait boundary, user approval is requested, or any identity/result field is ambiguous, report the non-secret blocker and stop fail closed.

EXACT CHILD ASSIGNMENT:

{child_assignment}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    parser.add_argument("--process-marker", required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        prompt = build_prompt(
            arguments.root,
            arguments.task_name,
            arguments.process_marker,
        )
    except (OSError, ProbePromptError) as error:
        print(f"P5b tracked-process prompt denied: {error}", file=sys.stderr)
        return 2
    if arguments.output is None:
        sys.stdout.write(prompt)
        return 0
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
        print(f"P5b tracked-process prompt was not written: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
