#!/usr/bin/env python3

"""Build the separated parent and Hook-staged inputs for one P7 DeepSeek probe."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys


TASK_NAME_RE = re.compile(r"^[a-z0-9_]+$")
MARKER_RE = re.compile(r"^[0-9a-f]{32}$")


class PromptError(RuntimeError):
    pass


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise PromptError(result.stderr.strip() or "Git preflight failed")
    return result.stdout.rstrip("\n")


def preflight(root_value: Path) -> tuple[Path, str, str, str]:
    root = root_value.resolve()
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise PromptError("probe root must be the exact Git top level")
    branch = git(root, "symbolic-ref", "--short", "HEAD")
    head = git(root, "rev-parse", "HEAD")
    if not branch or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise PromptError("probe requires an attached branch and full HEAD")
    if git(root, "status", "--short", "--untracked-files=all"):
        raise PromptError("probe root must be clean")
    fixture = root / "fixtures" / "smoke-input.txt"
    if not fixture.is_file() or fixture.is_symlink():
        raise PromptError("smoke fixture is unavailable")
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    return root, branch, head, digest


def build_inputs(root_value: Path, task_name: str, marker: str) -> dict[str, str]:
    if not TASK_NAME_RE.fullmatch(task_name):
        raise PromptError("task name must be lowercase alphanumeric with underscores")
    if not MARKER_RE.fullmatch(marker):
        raise PromptError("marker must be exactly 32 lowercase hexadecimal characters")
    root, branch, head, fixture_sha256 = preflight(root_value)
    read_command = (
        "python3 -c \"import hashlib,pathlib; "
        "p=pathlib.Path('fixtures/smoke-input.txt'); b=p.read_bytes(); "
        "print([line for line in b.decode('utf-8').splitlines() if line][2]); "
        "print(hashlib.sha256(b).hexdigest())\""
    )
    assignment = f"""You are the distinct spawned v4_flash_worker child. Execute only this product-independent read-only regression assignment.

Call exec_command exactly once in workdir {root} with cmd exactly `{read_command}`. The first output line is the exact third non-empty line of the fixture. The second output line is the SHA-256 of the entire fixture file, including all newlines; do not hash only the third line. Do not call another tool. Do not edit, stage, commit, push, change configuration, inspect credential values, manage agents, or use another provider. The immutable baseline is root={root}, branch={branch}, full_head={head}. Stop after this one read-only observation.

Return exactly these three lines and no prose:
marker={marker}
third_line=<observed third non-empty line>
sha256=<observed lowercase SHA-256 of the entire fixture; expected digest is {fixture_sha256}>"""
    parent_prompt = f"""Perform one product-independent P7 DeepSeek regression. You are the native OpenAI parent. The controlling root already loaded and followed the required v4 worker skill and successfully staged the complete assignment in isolated parent-owned state before this turn. Do not reload the skill or call a file-reading tool. Do not read the fixture, calculate its digest, inspect credentials, mutate files, change your provider/model, or substitute another worker.

Call native spawn_agent exactly once with agent_type=v4_flash_worker, task_name={task_name}, fork_turns=none, and message exactly `Execute the assignment supplied by the trusted one-shot SubagentStart Hook.` If staging, Hook delivery, role discovery, provider authentication, spawn, child execution, or callback fails, report that exact non-secret boundary and stop without retry or fallback. If spawn succeeds, wait through the native callback until that exact child finishes. Then report the spawn result, canonical AgentPath, and the child's exact three-line final result. Do not solve or repair the child task yourself."""
    return {
        "assignment": assignment,
        "parent_prompt": parent_prompt,
        "fixture_sha256": fixture_sha256,
        "branch": branch,
        "head": head,
        "root": str(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--kind", choices=("assignment", "parent"), required=True)
    arguments = parser.parse_args()
    try:
        value = build_inputs(arguments.root, arguments.task_name, arguments.marker)
    except (OSError, PromptError) as error:
        print(f"P7 DeepSeek prompt denied: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(value["assignment" if arguments.kind == "assignment" else "parent_prompt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
