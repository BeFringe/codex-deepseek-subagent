#!/usr/bin/env python3

"""Reset one verified isolated positive fixture to its exact clean baseline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from private_output import open_private_output
from run_p7_posix_mutation import sha256_file, snapshot


class ResetError(RuntimeError):
    pass


def require(value: object, message: str) -> None:
    if not value:
        raise ResetError(message)


def read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} is not an object")
    return value


def reset(manifest_path: Path, outcome_path: Path) -> dict[str, object]:
    manifest = read_object(manifest_path)
    outcome = read_object(outcome_path)
    require(
        manifest.get("classification") == "p7_macos_mutation_raw_attempt"
        and manifest.get("mutation_case") == "positive"
        and manifest.get("direct_write_qualified") is False,
        "manifest is not an unqualified positive calibration",
    )
    require(
        outcome.get("classification") == "fresh_macos_mutation_outcome_only"
        and outcome.get("case") == "positive"
        and outcome.get("outcome_verified") is True
        and outcome.get("authority_consumed") is False
        and outcome.get("manifest_sha256") == sha256_file(manifest_path),
        "fresh outcome does not bind the calibration manifest",
    )
    root = Path(manifest["root"]).resolve(strict=True)
    require(root.parent == Path("/private/tmp") and root.name.startswith("codex-g4-write-macos-"), "root escaped isolated boundary")
    before = snapshot(root)
    require(before == manifest["barrier_second"]["snapshot"], "calibration frontier drifted before reset")
    target = root / "qualified.txt"
    status = target.lstat()
    require(stat.S_ISREG(status.st_mode) and not target.is_symlink(), "calibration target is not an exact regular file")
    require(sha256_file(target) == before["files"]["qualified.txt"], "calibration target bytes drifted")
    os.unlink(target)
    directory = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    after = snapshot(root)
    require(after == manifest["baseline"], "reset did not restore exact calibration baseline")
    return {
        "schema": 1,
        "classification": "parent_reset_verified_macos_calibration_fixture",
        "parent_owner_id": "phase1.parent",
        "manifest_sha256": sha256_file(manifest_path),
        "outcome_sha256": sha256_file(outcome_path),
        "root": str(root),
        "removed_path": "qualified.txt",
        "before": before,
        "after": after,
        "phase1_complete": False,
        "direct_write_qualified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        receipt = reset(arguments.manifest, arguments.outcome)
        descriptor = open_private_output(arguments.output)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"reset": "verified", "output": str(arguments.output)}))
        return 0
    except (OSError, json.JSONDecodeError, KeyError, ResetError) as error:
        print(json.dumps({"reset": "blocked", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
