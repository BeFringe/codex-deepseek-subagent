#!/usr/bin/env python3

"""Provider-independent causal-provenance owner-boundary fixture."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from compatibility_state import canonical_json, sha256_bytes


class ProvenanceViolation(RuntimeError):
    pass


def artifact_digest(payload: object, derived_facts: object) -> str:
    return sha256_bytes(
        canonical_json({"payload": payload, "derived_facts": derived_facts})
    )


def self_consistent_artifact(payload: object, derived_facts: object) -> dict:
    """Build digest-valid bytes; this helper confers no real-mode authority."""
    return {
        "payload": payload,
        "derived_facts": derived_facts,
        "digest": artifact_digest(payload, derived_facts),
    }


class OwnerInternalOperation:
    """Own authoritative derivation and multi-output construction.

    Real-mode methods never accept precomputed derived facts.  The only
    injection method is explicitly test-only and marks every artifact non-final.
    """

    def __init__(
        self,
        policy: Mapping[str, object],
        *,
        input_owner: str,
        input_roots: Sequence[str],
        derivation_boundary: str,
        derive: Callable[[object], object],
        build_payloads: Callable[[object, object], Sequence[object]],
    ) -> None:
        if input_owner not in policy["authoritative_input_owners"]:
            raise ProvenanceViolation("authoritative input owner does not match the capsule")
        if list(input_roots) != policy["authoritative_input_roots"]:
            raise ProvenanceViolation("authoritative input roots do not match the capsule")
        if derivation_boundary != policy["required_derivation_boundary"]:
            raise ProvenanceViolation("derivation boundary does not match the capsule")
        self._policy = policy
        self._input_owner = input_owner
        self._input_roots = list(input_roots)
        self._derivation_boundary = derivation_boundary
        self._derive = derive
        self._build_payloads = build_payloads

    def _real_artifacts(self, raw_authoritative_input: object) -> list[dict]:
        derived_facts = self._derive(raw_authoritative_input)
        payloads = self._build_payloads(raw_authoritative_input, derived_facts)
        return [
            self_consistent_artifact(payload, derived_facts)
            for payload in payloads
        ]

    def build_real(self, raw_authoritative_input: object) -> tuple[list[dict], dict]:
        artifacts = self._real_artifacts(raw_authoritative_input)
        return artifacts, self._receipt(artifacts)

    def verify_real(
        self,
        raw_authoritative_input: object,
        candidate_artifacts: Sequence[Mapping[str, object]],
    ) -> dict:
        expected = self._real_artifacts(raw_authoritative_input)
        if canonical_json(list(candidate_artifacts)) != canonical_json(expected):
            raise ProvenanceViolation(
                "candidate output was not derived from authoritative owner input"
            )
        return self._receipt(expected)

    def build_test_only(
        self,
        raw_input: object,
        *,
        injection_seam: str,
        injected_derived_facts: object,
    ) -> list[dict]:
        if injection_seam not in self._policy["test_only_injection_seams"]:
            raise ProvenanceViolation("test-only injection seam is not declared")
        payloads = self._build_payloads(raw_input, injected_derived_facts)
        return [
            {
                **self_consistent_artifact(payload, injected_derived_facts),
                "non_final": True,
                "test_only_injection_seam": injection_seam,
            }
            for payload in payloads
        ]

    def _receipt(self, artifacts: Sequence[Mapping[str, object]]) -> dict:
        evidence = {
            "schema": 1,
            "artifact_digests": [artifact["digest"] for artifact in artifacts],
            "input_owner": self._input_owner,
            "input_roots": self._input_roots,
            "derived_fact_origin": "owner_internal",
            "derivation_boundary": self._derivation_boundary,
        }
        evidence["evidence_sha256"] = sha256_bytes(canonical_json(evidence))
        return evidence
