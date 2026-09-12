#!/usr/bin/env python3

"""Bind real positive/negative mutation outcomes into one P7 feasibility packet."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from p7_write_feasibility import derive
from private_output import open_private_output
from run_p7_posix_mutation import sha256_file


class FeasibilityError(RuntimeError):
    pass


def require(value: object, message: str) -> None:
    if not value:
        raise FeasibilityError(message)


def read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} is not an object")
    return value


def build(
    positive_manifest_path: Path,
    positive_outcome_path: Path,
    negative_manifest_path: Path,
    negative_outcome_path: Path,
) -> dict[str, object]:
    positive_manifest = read_object(positive_manifest_path)
    negative_manifest = read_object(negative_manifest_path)
    positive_outcome = read_object(positive_outcome_path)
    negative_outcome = read_object(negative_outcome_path)
    for case, manifest, outcome, manifest_path in (
        ("positive", positive_manifest, positive_outcome, positive_manifest_path),
        ("negative", negative_manifest, negative_outcome, negative_manifest_path),
    ):
        require(
            manifest.get("classification") == "p7_macos_mutation_raw_attempt"
            and manifest.get("mutation_case") == case
            and manifest.get("exit_code") == 0
            and manifest.get("phase1_complete") is False
            and manifest.get("direct_write_qualified") is False,
            f"{case} raw manifest is not an exact unqualified outcome",
        )
        require(
            outcome.get("classification") == "fresh_macos_mutation_outcome_only"
            and outcome.get("case") == case
            and outcome.get("outcome_verified") is True
            and outcome.get("authority_consumed") is False
            and outcome.get("manifest_sha256") == sha256_file(manifest_path),
            f"{case} fresh-owner outcome does not bind its manifest",
        )
    require(
        positive_manifest["candidate_sha256"] == negative_manifest["candidate_sha256"]
        and positive_manifest["source_commit"] == negative_manifest["source_commit"]
        and positive_manifest["source_patch_sha256"] == negative_manifest["source_patch_sha256"]
        and positive_manifest["source_replay_sha256"] == negative_manifest["source_replay_sha256"]
        and positive_manifest.get("source_chain_receipt_sha256")
        == negative_manifest.get("source_chain_receipt_sha256")
        and positive_manifest["provider"] == negative_manifest["provider"] == "deepseek",
        "positive and negative outcomes do not share one runtime/source route",
    )
    root = Path(positive_manifest["root"]).resolve(strict=True)
    authoritative = (root / "docs" / "phase1-evidence.md").read_bytes().decode("utf-8")
    target = root / "qualified.txt"
    inputs = {
        "baseline": positive_manifest["baseline"],
        "authoritative_input_utf8": authoritative,
        "patch": (
            "*** Begin Patch\n"
            f"*** Add File: {target}\n"
            "+G4_CHILD_WRITE_QUALIFIED\n"
            "*** End Patch"
        ),
        "live_outcomes": {
            "positive_manifest_sha256": sha256_file(positive_manifest_path),
            "positive_outcome_sha256": sha256_file(positive_outcome_path),
            "negative_manifest_sha256": sha256_file(negative_manifest_path),
            "negative_outcome_sha256": sha256_file(negative_outcome_path),
            "negative_boundary": negative_outcome["negative_boundary"],
            "candidate_sha256": positive_manifest["candidate_sha256"],
            "source_commit": positive_manifest["source_commit"],
            "source_patch_sha256": positive_manifest["source_patch_sha256"],
            "source_replay_sha256": positive_manifest["source_replay_sha256"],
            "source_chain_receipt_sha256": positive_manifest.get(
                "source_chain_receipt_sha256"
            ),
            "provider": "deepseek",
        },
    }
    packet = derive(inputs)
    require(packet["attestation"]["owner_decision"] == "dispatch", "concrete feasibility rejected")
    return {
        "schema": 1,
        "classification": "parent_owned_live_macos_write_feasibility",
        **packet,
        "authority_consumed": False,
        "direct_write_qualified": False,
        "phase1_complete": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positive-manifest", type=Path, required=True)
    parser.add_argument("--positive-outcome", type=Path, required=True)
    parser.add_argument("--negative-manifest", type=Path, required=True)
    parser.add_argument("--negative-outcome", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        packet = build(
            arguments.positive_manifest,
            arguments.positive_outcome,
            arguments.negative_manifest,
            arguments.negative_outcome,
        )
        descriptor = open_private_output(arguments.output)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(packet, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"feasibility": "dispatch", "output": str(arguments.output)}))
        return 0
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, KeyError, FeasibilityError, ValueError) as error:
        print(json.dumps({"feasibility": "block", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
