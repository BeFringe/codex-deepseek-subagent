#!/usr/bin/env python3

"""No-follow evidence-output binding for provider-free isolated fixtures."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import os
from pathlib import Path, PurePosixPath
import stat


class EvidenceBindingViolation(RuntimeError):
    pass


def _canonical_relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise EvidenceBindingViolation("canonical output path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or ".." in path.parts:
        raise EvidenceBindingViolation("canonical output path is invalid")
    return path


def preflight(
    binding: Mapping[str, object],
    *,
    executed_root: str,
    hashed_root: str,
    source_identity: Mapping[str, str],
) -> tuple[Path, PurePosixPath]:
    declared_executed = Path(str(binding["executed_root"])).resolve()
    declared_hashed = Path(str(binding["hashed_root"])).resolve()
    actual_executed = Path(executed_root).resolve()
    actual_hashed = Path(hashed_root).resolve()
    if not (
        declared_executed
        == declared_hashed
        == actual_executed
        == actual_hashed
    ):
        raise EvidenceBindingViolation("executed and hashed checkouts are not the same authority")
    if binding["source_identity"] != dict(source_identity):
        raise EvidenceBindingViolation("source identity does not match the evidence contract")
    for field in (
        "no_follow_dirfd_walk",
        "terminal_regular_file_reproof",
        "preflight_before_expensive_execution",
    ):
        if binding.get(field) is not True:
            raise EvidenceBindingViolation(f"{field} is not enabled")
    return actual_executed, _canonical_relative(binding["canonical_output"])


def run_bound_evidence(
    binding: Mapping[str, object],
    *,
    executed_root: str,
    hashed_root: str,
    source_identity: Mapping[str, str],
    expensive_runner: Callable[[int], None],
) -> dict:
    """Preflight identity, create output by no-follow dirfd walk, run, and reprove identity."""
    root, output = preflight(
        binding,
        executed_root=executed_root,
        hashed_root=hashed_root,
        source_identity=source_identity,
    )
    if os.name == "nt":
        from windows_evidence_binding import run_bound_windows_evidence

        try:
            run_bound_windows_evidence(root, output, expensive_runner)
        except OSError as error:
            raise EvidenceBindingViolation(f"no-follow output walk failed: {error}") from error
        return {
            "root": str(root),
            "output": output.as_posix(),
            "source_identity": dict(source_identity),
            "terminal_identity_reproved": True,
        }
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | nofollow
    directory_fds: list[int] = []
    output_fd = -1
    try:
        current_fd = os.open(root, directory_flags)
        directory_fds.append(current_fd)
        for component in output.parts[:-1]:
            current_fd = os.open(component, directory_flags, dir_fd=current_fd)
            directory_fds.append(current_fd)
        terminal = output.parts[-1]
        output_fd = os.open(
            terminal,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            0o600,
            dir_fd=current_fd,
        )
        initial = os.fstat(output_fd)
        if not stat.S_ISREG(initial.st_mode):
            raise EvidenceBindingViolation("evidence output terminal is not a regular file")
        expensive_runner(output_fd)
        os.fsync(output_fd)
        opened = os.fstat(output_fd)
        named = os.stat(terminal, dir_fd=current_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino)
            or (named.st_dev, named.st_ino) != (initial.st_dev, initial.st_ino)
        ):
            raise EvidenceBindingViolation("evidence output terminal identity changed")
        return {
            "root": str(root),
            "output": output.as_posix(),
            "source_identity": dict(source_identity),
            "terminal_identity_reproved": True,
        }
    except OSError as error:
        raise EvidenceBindingViolation(f"no-follow output walk failed: {error.strerror}") from error
    finally:
        if output_fd >= 0:
            os.close(output_fd)
        for descriptor in reversed(directory_fds):
            os.close(descriptor)
