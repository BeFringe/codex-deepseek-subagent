#!/usr/bin/env python3
"""Fail-closed Phase 1 promotion adjudication across the final source pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "status": ROOT / "probes" / "phase1-g4-status.json",
    "source": ROOT
    / "probes"
    / "current-signed-runtime-g4-explicit-plaintext-delivery-source-candidate.json",
    "complete_source": ROOT
    / "probes"
    / "current-signed-runtime-g4-complete-source-tree-20260912.json",
    "rust": ROOT
    / "probes"
    / "current-signed-runtime-g4-complete-source-rust-validation-20260912.json",
    "macos": ROOT
    / "probes"
    / "p7-macos-complete-source-writer-live-20260912.json",
    "sibling": ROOT
    / "probes"
    / "g4-live-sibling-spawn-admission-parent-adjudication-20260909.json",
    "deepseek": ROOT / "probes" / "p7-live-deepseek-regression-20260910.json",
    "rollback": ROOT / "probes" / "p7-live-isolated-install-rollback-20260910.json",
}

REQUIRED_GATES = {
    "P1",
    "P2",
    "P3",
    "P4",
    "P5",
    "P5a",
    "P5b",
    "P6",
    "P6a",
    "P6b",
    "P6c",
    "P7",
}
REQUIRED_RECEIPTS = {
    "sessionmeta_identity",
    "mutation_visibility",
    "sandbox_block",
    "callback_continuity",
    "termination_quiescence",
    "posix_live",
    "windows_live",
    "deepseek_regression",
    "install_rollback",
}
SOURCE_IDENTITY_KEYS = (
    "base_commit",
    "semantic_version",
    "patch_sha256",
    "cumulative_replay_sha256",
    "patch_chain_receipt_sha256",
    "complete_tree",
    "complete_replay_sha256",
    "complete_source_receipt_sha256",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
HOST_PATH = re.compile(r"(?:[A-Za-z]:\\\\|/(?:Users|home|private/tmp)/)")


class AdjudicationError(ValueError):
    """The supplied evidence cannot authorize Phase 1 promotion."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdjudicationError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} must contain an object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_sha256(value: Any, label: str) -> str:
    require(isinstance(value, str) and SHA256.fullmatch(value) is not None, f"{label} must be a SHA-256")
    return value


def require_true(value: dict[str, Any], keys: tuple[str, ...], label: str) -> None:
    for key in keys:
        require(value.get(key) is True, f"{label}.{key} must be true")


def expected_source_identity(
    source_path: Path,
    source: dict[str, Any],
    complete_source_path: Path,
    complete_source: dict[str, Any],
) -> dict[str, str]:
    patch_chain = source.get("patch_chain")
    require(isinstance(patch_chain, list) and patch_chain, "source patch chain is empty")
    final_patch = patch_chain[-1]
    require(isinstance(final_patch, dict), "final source patch entry is invalid")
    require(
        complete_source.get("classification")
        == "current_signed_runtime_g4_complete_source_tree",
        "complete source classification drifted",
    )
    require(
        complete_source.get("source") == {
            **source["source"],
            "base_tree": complete_source.get("source", {}).get("base_tree"),
        },
        "complete source descriptor drifted",
    )
    base_tree = complete_source.get("source", {}).get("base_tree")
    require(
        isinstance(base_tree, str) and GIT_OID.fullmatch(base_tree) is not None,
        "complete source base tree must be a full Git object ID",
    )
    predecessor = complete_source.get("predecessor_receipt", {})
    require(
        predecessor.get("sha256") == sha256_file(source_path),
        "complete source predecessor receipt drifted",
    )
    complete_chain = complete_source.get("ordered_patch_chain")
    require(
        isinstance(complete_chain, list) and len(complete_chain) == len(patch_chain),
        "complete source patch chain length drifted",
    )
    for prior, complete in zip(patch_chain, complete_chain, strict=True):
        require(
            complete.get("path") == prior.get("path")
            and complete.get("sha256") == prior.get("sha256"),
            "complete source patch chain drifted",
        )
        patch_path = ROOT / complete["path"]
        require(
            sha256_file(patch_path) == complete["sha256"],
            f"complete source patch bytes drifted at {patch_path.name}",
        )
    reconstruction = complete_source.get("complete_reconstruction", {})
    require(
        reconstruction.get("method")
        == "temporary_index_read_tree_then_apply_cached_in_order",
        "complete source reconstruction method drifted",
    )
    require_true(
        reconstruction,
        ("git_apply_cached_passed", "git_diff_check_passed"),
        "complete source reconstruction",
    )
    require(
        reconstruction.get("working_tree_mutated") is False,
        "complete source reconstruction mutated the working tree",
    )
    complete_tree = reconstruction.get("tree")
    require(
        isinstance(complete_tree, str) and GIT_OID.fullmatch(complete_tree) is not None,
        "complete source tree must be a full Git object ID",
    )
    complete_replay_sha256 = require_sha256(
        reconstruction.get("binary_full_index_diff_sha256"),
        "complete source binary diff",
    )
    legacy = complete_source.get("legacy_tracked_only_observation", {})
    require(
        legacy.get("sha256")
        == source["fresh_replay"]["canonical_cumulative_diff_sha256"],
        "legacy tracked-only observation drifted",
    )
    require(
        legacy.get("complete_source_identity") is False,
        "legacy tracked-only observation must not be complete",
    )
    identity = {
        "base_commit": source["source"]["base_commit"],
        "semantic_version": source["source"]["semantic_version"],
        "patch_sha256": final_patch["sha256"],
        "cumulative_replay_sha256": source["fresh_replay"][
            "canonical_cumulative_diff_sha256"
        ],
        "patch_chain_receipt_sha256": sha256_file(source_path),
        "complete_tree": complete_tree,
        "complete_replay_sha256": complete_replay_sha256,
        "complete_source_receipt_sha256": sha256_file(complete_source_path),
    }
    require(
        isinstance(identity["base_commit"], str)
        and GIT_OID.fullmatch(identity["base_commit"]) is not None,
        "source identity base_commit must be a full Git object ID",
    )
    for key in (
        "patch_sha256",
        "cumulative_replay_sha256",
        "patch_chain_receipt_sha256",
        "complete_replay_sha256",
        "complete_source_receipt_sha256",
    ):
        require_sha256(identity[key], f"source identity {key}")
    require(source["fresh_replay"].get("detached_exact_base") is True, "source base is not exact")
    require(source["fresh_replay"].get("git_apply_check_passed") is True, "source patch did not replay")
    require(source["fresh_replay"].get("git_diff_check_passed") is True, "source diff check failed")
    return identity


def require_source_identity(
    actual: dict[str, Any], expected: dict[str, str], label: str
) -> None:
    for key in SOURCE_IDENTITY_KEYS:
        require(actual.get(key) == expected[key], f"{label} source identity drifted at {key}")


def validate_status(status: dict[str, Any]) -> dict[str, Any]:
    phase1 = status.get("phase1")
    require(isinstance(phase1, dict), "Phase 1 status is missing")
    gates = {item["id"]: item["state"] for item in phase1.get("gates", [])}
    receipts = {
        item["id"]: item["state"] for item in phase1.get("exit_receipts", [])
    }
    require(set(gates) == REQUIRED_GATES, "Phase 1 gate set drifted")
    require(set(receipts) == REQUIRED_RECEIPTS, "Phase 1 receipt set drifted")
    require(
        all(gates[item] == "qualified" for item in REQUIRED_GATES - {"P7"}),
        "a non-P7 gate is not qualified",
    )
    require(
        all(
            receipts[item] == "qualified"
            for item in REQUIRED_RECEIPTS - {"windows_live"}
        ),
        "a non-Windows exit receipt is not qualified",
    )
    require(gates["P7"] in {"partial", "qualified"}, "P7 state is invalid")
    require(
        receipts["windows_live"] in {"pending", "qualified"},
        "Windows receipt state is invalid",
    )
    require(status.get("phase2", {}).get("state") == "closed", "Phase 2 must stay closed")
    require(status.get("phase3", {}).get("state") == "closed", "Phase 3 must stay closed")
    promoted = gates["P7"] == receipts["windows_live"] == "qualified"
    require(
        phase1.get("declared_complete") is promoted,
        "declared Phase 1 completion does not match P7/Windows state",
    )
    require(
        phase1.get("declared_direct_write_qualified") is promoted,
        "declared direct-write state does not match P7/Windows state",
    )
    return {
        "p7": gates["P7"],
        "windows_live": receipts["windows_live"],
        "promoted": promoted,
    }


def validate_rust(
    rust: dict[str, Any], expected_source: dict[str, str], source_candidate_sha: str
) -> None:
    require(
        rust.get("classification")
        == "current_signed_runtime_g4_complete_source_rust_validation",
        "Rust validation classification drifted",
    )
    rust_source = dict(rust.get("source", {}))
    require_source_identity(rust_source, expected_source, "Rust validation")
    require(
        rust.get("source", {}).get("candidate_sha256") == source_candidate_sha,
        "Rust validation candidate drifted",
    )
    require(rust.get("targeted_current_source", {}).get("all_passed") is True, "targeted Rust tests failed")
    require(
        rust.get("current_source_serial_core", {}).get("patch_regressions") == 0,
        "full Rust comparison found a patch regression",
    )
    require(
        rust.get("decision", {}).get("callback_patch_regression_observed") is False,
        "callback regression is still present",
    )


def validate_macos(
    macos_path: Path,
    macos: dict[str, Any],
    expected_source: dict[str, str],
    source_candidate_sha: str,
) -> None:
    require(
        macos.get("classification") == "p7_macos_current_candidate_writer_live_evidence",
        "macOS classification drifted",
    )
    require_source_identity(macos.get("source", {}), expected_source, "macOS")
    require(
        macos.get("source", {}).get("candidate_sha256") == source_candidate_sha,
        "macOS candidate drifted",
    )
    require(macos.get("platform", {}).get("system") == "Darwin", "macOS platform is not Darwin")
    require(
        macos.get("provider_boundary", {}).get("credential_values_recorded") is False,
        "macOS receipt recorded credential values",
    )
    negative = macos.get("negative_calibration", {})
    require(negative.get("pretool_decision") == "deny", "macOS foreign path was not denied")
    require(negative.get("posttool_observation_count") == 0, "macOS denied tool emitted PostToolUse")
    require_true(
        negative,
        (
            "disk_barriers_verified",
            "session_loop_terminated",
            "tracked_process_termination_confirmed",
            "closed_catalog_actor_quiescence_claimed",
            "child_absent_after_close",
        ),
        "macOS negative",
    )
    positive = macos.get("final_positive", {})
    require_true(
        positive,
        (
            "callback_exact",
            "custom_tool_call_output_paired",
            "feasibility_bound_before_dispatch",
            "disk_barriers_exact_and_stable",
            "session_loop_terminated",
            "tracked_process_termination_confirmed",
            "closed_catalog_actor_quiescence_claimed",
            "child_absent_after_close",
            "in_flight_authority_empty",
            "authority_consumed",
            "exact_closed_writer_run_qualified",
        ),
        "macOS positive",
    )
    require(
        positive.get("post_termination_barrier_interval_ns", 0) >= 2_000_000_000,
        "macOS disk barrier is too short",
    )
    require(HOST_PATH.search(macos_path.read_text(encoding="utf-8")) is None, "macOS compact receipt leaks a host path")


def validate_windows(
    windows_path: Path, windows: dict[str, Any], expected_source: dict[str, str]
) -> str:
    require(
        windows.get("classification")
        == "p7_windows_current_candidate_writer_live_evidence",
        "Windows classification drifted",
    )
    require_source_identity(windows.get("source", {}), expected_source, "Windows")
    candidate_sha = require_sha256(
        windows.get("source", {}).get("candidate_sha256"), "Windows candidate"
    )
    require(windows.get("platform", {}).get("system") == "Windows", "Windows platform is not Windows")
    require(
        windows.get("provider_boundary", {}).get("credential_values_recorded") is False,
        "Windows receipt recorded credential values",
    )
    rust = windows.get("rust_validation", {})
    require(rust.get("targeted_all_passed") is True, "Windows targeted Rust tests failed")
    require(rust.get("patch_regressions") == 0, "Windows Rust comparison found a patch regression")
    schedules = windows.get("deterministic_schedules", {})
    require(schedules.get("all_passed") is True, "Windows deterministic schedules failed")
    require(schedules.get("schedule_count", 0) >= 6, "Windows deterministic schedule cohort is incomplete")
    require(schedules.get("unexplained_negative_count") == 0, "Windows has unexplained deterministic negatives")
    parent_negative = windows.get("parent_same_path_negative", {})
    require(parent_negative.get("pretool_decision") == "deny", "Windows parent same-path request was not denied")
    require(parent_negative.get("posttool_observation_count") == 0, "Windows denied parent tool emitted PostToolUse")
    require_true(
        parent_negative,
        ("durable_conflict_observed", "child_writer_claim_preserved"),
        "Windows parent negative",
    )
    foreign_negative = windows.get("foreign_path_negative", {})
    require(foreign_negative.get("pretool_decision") == "deny", "Windows foreign path was not denied")
    require(foreign_negative.get("posttool_observation_count") == 0, "Windows denied foreign tool emitted PostToolUse")
    require_true(
        foreign_negative,
        (
            "foreign_dirty_bytes_preserved",
            "authority_revoked",
            "disk_barriers_verified",
            "session_loop_terminated",
            "tracked_process_termination_confirmed",
            "closed_catalog_actor_quiescence_claimed",
            "child_absent_after_close",
        ),
        "Windows foreign negative",
    )
    positive = windows.get("final_positive", {})
    require_true(
        positive,
        (
            "callback_exact",
            "custom_tool_call_output_paired",
            "feasibility_bound_before_dispatch",
            "disk_barriers_exact_and_stable",
            "session_loop_terminated",
            "tracked_process_termination_confirmed",
            "closed_catalog_actor_quiescence_claimed",
            "child_absent_after_close",
            "in_flight_authority_empty",
            "authority_consumed",
            "exact_closed_writer_run_qualified",
        ),
        "Windows positive",
    )
    require(
        positive.get("post_termination_barrier_interval_ns", 0) >= 2_000_000_000,
        "Windows disk barrier is too short",
    )
    regression = windows.get("provider_free_regression", {})
    require(regression.get("failed") == 0, "Windows provider-free suite failed")
    require(
        regression.get("tests_run") == regression.get("passed", -1) + regression.get("skipped", -1),
        "Windows provider-free counts are inconsistent",
    )
    require(
        regression.get("windows_equivalence_cases", 0) >= 85
        and regression.get("windows_equivalence_passed")
        == regression.get("windows_equivalence_cases"),
        "Windows equivalence cohort is incomplete",
    )
    decision = windows.get("scope_decision", {})
    require_true(decision, ("windows_current_candidate_qualified",), "Windows decision")
    for key in ("p7_complete", "phase1_complete", "direct_write_qualified"):
        require(decision.get(key) is False, f"Windows receipt must not self-promote {key}")
    require(decision.get("phase2_state") == "closed", "Windows receipt opened Phase 2")
    require(decision.get("phase3_state") == "closed", "Windows receipt opened Phase 3")
    text = windows_path.read_text(encoding="utf-8")
    require(HOST_PATH.search(text) is None, "Windows compact receipt leaks a host path")
    require("LocalCAT" not in text, "Windows receipt is product-coupled")
    return candidate_sha


def validate_supporting_evidence(
    sibling: dict[str, Any], deepseek: dict[str, Any], rollback: dict[str, Any]
) -> None:
    require(
        all(value == "pass" for value in sibling.get("fresh_owner", {}).values()),
        "native sibling admission is not closed",
    )
    deepseek_verdict = deepseek.get("verdict", {})
    require_true(
        deepseek_verdict,
        (
            "native_openai_parent_preserved",
            "native_deepseek_child_observed",
            "native_tool_result_observed",
            "native_wait_and_callback_observed",
            "deepseek_regression_qualified",
        ),
        "DeepSeek regression",
    )
    for key, value in deepseek.get("credential_boundary", {}).items():
        if key.startswith("credential_value_"):
            require(value is False, f"DeepSeek credential boundary failed at {key}")
    rollback_verdict = rollback.get("verdict", {})
    require_true(
        rollback_verdict,
        (
            "isolated_install_reload_rollback_qualified",
            "installed_failed_posttool_callback_regression_qualified",
            "install_rollback_exit_receipt_qualified",
        ),
        "install rollback",
    )
    for key, value in rollback.get("credential_boundary", {}).items():
        if key.startswith("credential_value_"):
            require(value is False, f"rollback credential boundary failed at {key}")


def adjudicate(paths: dict[str, Path]) -> dict[str, Any]:
    required = set(DEFAULTS) | {"windows"}
    require(set(paths) == required, "adjudication path set drifted")
    values = {name: read_json(path) for name, path in paths.items()}
    status_state = validate_status(values["status"])
    expected_source = expected_source_identity(
        paths["source"],
        values["source"],
        paths["complete_source"],
        values["complete_source"],
    )
    source_candidate_sha = require_sha256(
        values["rust"].get("source", {}).get("candidate_sha256"),
        "source candidate",
    )
    validate_rust(values["rust"], expected_source, source_candidate_sha)
    validate_macos(paths["macos"], values["macos"], expected_source, source_candidate_sha)
    windows_candidate_sha = validate_windows(paths["windows"], values["windows"], expected_source)
    require(
        windows_candidate_sha != source_candidate_sha,
        "Windows and macOS candidate hashes must identify distinct binaries",
    )
    validate_supporting_evidence(values["sibling"], values["deepseek"], values["rollback"])
    evidence_sha256 = {name: sha256_file(path) for name, path in paths.items()}
    return {
        "schema": 1,
        "classification": "phase1_cross_platform_promotion_adjudication",
        "promotion_ready": True,
        "status_already_promoted": status_state["promoted"],
        "source_identity": expected_source,
        "candidate_sha256": {
            "darwin_arm64": source_candidate_sha,
            "windows_amd64": windows_candidate_sha,
        },
        "evidence_sha256": evidence_sha256,
        "phase2_state": "closed",
        "phase3_state": "closed",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name, default in DEFAULTS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=default)
    parser.add_argument("--windows", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    paths = {name: getattr(arguments, name) for name in DEFAULTS}
    paths["windows"] = arguments.windows
    try:
        result = adjudicate(paths)
    except (AdjudicationError, KeyError, json.JSONDecodeError, OSError) as error:
        print(json.dumps({"promotion_ready": False, "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
