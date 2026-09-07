#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


PROBE_DIRECTORY = Path(__file__).resolve().parent
if str(PROBE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROBE_DIRECTORY))

from check_runtime_evidence_index import load_index, runtime_identity  # noqa: E402


GIT_OID = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_CODEX_SOURCE_ROLES = {"prior_signed_runtime", "current_signed_runtime"}
REQUIRED_VERDICT = {
    "assignment_transport_orthogonal": True,
    "legacy_role_provider_override_qualified": False,
    "broker_satisfies_native_agentpath_lifecycle_contract": False,
    "p7_deepseek_regression": "blocked-upstream",
    "phase1_complete": False,
    "direct_write_qualified": False,
    "phase2_state": "closed",
    "phase3_state": "closed",
}


def _validate_anchors(anchors, label):
    if not isinstance(anchors, list) or not anchors:
        raise ValueError(f"{label} anchors must be a non-empty list")
    for anchor in anchors:
        if not isinstance(anchor, dict) or not all(
            isinstance(anchor.get(key), str) and anchor[key]
            for key in ("path", "contains")
        ):
            raise ValueError(f"{label} has an invalid source anchor")
        if "not_contains" in anchor and (
            not isinstance(anchor["not_contains"], str) or not anchor["not_contains"]
        ):
            raise ValueError(f"{label} has an invalid negative source anchor")


def load_contract(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("provider inheritance contract has an invalid schema")

    upstream = value.get("upstream_change")
    if not isinstance(upstream, dict) or GIT_OID.fullmatch(
        str(upstream.get("commit", ""))
    ) is None:
        raise ValueError("provider inheritance contract has an invalid upstream commit")

    sources = value.get("openai_sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError("provider inheritance contract needs at least two Codex sources")
    runtime_index = load_index()
    versions = set()
    roles = set()
    for source in sources:
        version = source.get("codex_version") if isinstance(source, dict) else None
        role = source.get("runtime_role") if isinstance(source, dict) else None
        if not isinstance(version, str) or not version or version in versions:
            raise ValueError("Codex source versions are missing or duplicated")
        versions.add(version)
        if not isinstance(role, str) or role in roles:
            raise ValueError("Codex source semantic roles are missing or duplicated")
        roles.add(role)
        expected_identity = runtime_identity(runtime_index, role)
        if any(source.get(key) != expected_identity[key] for key in expected_identity):
            raise ValueError(f"Codex source {role} disagrees with its runtime identity")
        if GIT_OID.fullmatch(str(source.get("source_commit", ""))) is None:
            raise ValueError(f"Codex source {version} has an invalid commit")
        _validate_anchors(source.get("anchors"), f"Codex source {version}")
    if roles != REQUIRED_CODEX_SOURCE_ROLES:
        raise ValueError("provider inheritance source roles are incomplete")

    utopia = value.get("utopia_source")
    if not isinstance(utopia, dict) or GIT_OID.fullmatch(
        str(utopia.get("source_commit", ""))
    ) is None:
        raise ValueError("provider inheritance contract has an invalid Utopia source")
    _validate_anchors(utopia.get("anchors"), "Utopia source")
    if utopia.get("legacy_native_route_supported_from_0_149") is not False:
        raise ValueError("legacy native route must remain fail closed from Codex 0.149")

    verdict = value.get("verdict")
    if not isinstance(verdict, dict):
        raise ValueError("provider inheritance contract is missing its verdict")
    for key, expected in REQUIRED_VERDICT.items():
        if verdict.get(key) != expected:
            raise ValueError(f"provider inheritance verdict cannot promote {key}")
    if not isinstance(verdict.get("blocker"), str) or not verdict["blocker"]:
        raise ValueError("provider inheritance verdict is missing its blocker")
    return value


def _git_identity(source_root):
    try:
        requested = source_root.resolve(strict=True)
    except OSError as error:
        return None, None, [f"cannot resolve source root: {error}"]

    values = {}
    failures = []
    for label, args in {
        "root": ["rev-parse", "--show-toplevel"],
        "head": ["rev-parse", "--verify", "HEAD^{commit}"],
    }.items():
        result = subprocess.run(
            ["git", "-C", str(requested), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            failures.append(f"cannot resolve source {label}")
        else:
            values[label] = result.stdout.strip()
    root = values.get("root")
    if root is not None and Path(root).resolve() != requested:
        failures.append("source path is not the exact Git top level")
    return requested, values.get("head"), failures


def verify_source(source, source_root, label):
    root, head, failures = _git_identity(source_root)
    if head is not None and head != source["source_commit"]:
        failures.append(
            f"{label} HEAD drifted: expected={source['source_commit']} actual={head}"
        )
    if root is None or failures:
        return head, failures

    for anchor in source["anchors"]:
        try:
            text = (root / anchor["path"]).read_text(encoding="utf-8")
        except OSError as error:
            failures.append(f"{label}: cannot read {anchor['path']}: {error}")
            continue
        if anchor["contains"] not in text:
            failures.append(f"{label}: source anchor drifted in {anchor['path']}")
        forbidden = anchor.get("not_contains")
        if forbidden is not None and forbidden in text:
            failures.append(f"{label}: forbidden source anchor found in {anchor['path']}")
    return head, failures


def _parse_codex_source(value):
    role, separator, path = value.partition("=")
    if not separator or not role or not path:
        raise argparse.ArgumentTypeError("expected RUNTIME_ROLE=PATH")
    return role, Path(path)


def qualification(contract):
    verdict = contract["verdict"]
    return {
        "legacy_role_provider_override_qualified": verdict[
            "legacy_role_provider_override_qualified"
        ],
        "broker_satisfies_native_agentpath_lifecycle_contract": verdict[
            "broker_satisfies_native_agentpath_lifecycle_contract"
        ],
        "p7_deepseek_regression": verdict["p7_deepseek_regression"],
        "phase1_complete": verdict["phase1_complete"],
        "direct_write_qualified": verdict["direct_write_qualified"],
        "phase2_state": verdict["phase2_state"],
        "phase3_state": verdict["phase3_state"],
        "blocker": verdict["blocker"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(__file__).with_name("provider-inheritance-boundary-20260907.json"),
    )
    parser.add_argument(
        "--codex-source",
        action="append",
        type=_parse_codex_source,
        default=[],
        metavar="RUNTIME_ROLE=PATH",
    )
    parser.add_argument("--utopia-source", type=Path, required=True)
    parser.add_argument("--require-legacy-native-route", action="store_true")
    args = parser.parse_args()

    try:
        contract = load_contract(args.contract)
        expected = {source["runtime_role"]: source for source in contract["openai_sources"]}
        supplied = dict(args.codex_source)
        if set(supplied) != set(expected) or len(supplied) != len(args.codex_source):
            raise ValueError(
                "Codex source roles must match the contract exactly: "
                f"expected={sorted(expected)} actual={sorted(supplied)}"
            )

        observed = {}
        failures = []
        for role, source in expected.items():
            head, source_failures = verify_source(
                source, supplied[role], f"Codex {role}"
            )
            observed[role] = head
            failures.extend(source_failures)
        utopia_head, utopia_failures = verify_source(
            contract["utopia_source"], args.utopia_source, "Utopia"
        )
        failures.extend(utopia_failures)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
        return 1

    result = qualification(contract)
    result.update(
        {
            "valid": not failures,
            "observed_codex_heads": observed,
            "observed_utopia_head": utopia_head,
            "source_failures": failures,
        }
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if failures:
        return 1
    if args.require_legacy_native_route and not result[
        "legacy_role_provider_override_qualified"
    ]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
