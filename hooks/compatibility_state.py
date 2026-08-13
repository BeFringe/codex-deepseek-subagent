#!/usr/bin/env python3

"""Provider-independent schema-v2 authority state primitives.

This module is intentionally not wired into the live Hook yet.  It provides the
state and validation core used by isolated Phase 1 probes.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import uuid
from typing import Iterator, Mapping, Sequence

if os.name == "posix":
    import fcntl
else:  # pragma: no cover - exercised by the Windows parity harness later
    fcntl = None


SCHEMA = 2
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
PROVENANCE_FIELDS = {
    "authoritative_input_owners",
    "authoritative_input_roots",
    "forbidden_caller_supplied_derived_facts",
    "test_only_injection_seams",
    "required_derivation_boundary",
}
PARENT_ADJUDICATION_FIELDS = {
    "location_integrity",
    "mutation_scope_integrity",
    "verification_freshness",
    "derivation_provenance_integrity",
    "evidence_sha256",
}
STATE_KINDS = (
    "pending",
    "claimed",
    "active",
    "reported",
    "consumed",
    "expired",
    "lost",
    "quarantine",
    "unresolved",
)


class StateError(RuntimeError):
    """Base class for fail-closed state errors."""


class CorruptState(StateError):
    """Serialized state is malformed, untrusted, or hash-invalid."""


class IdentityMismatch(StateError):
    """A valid assignment was presented to the wrong child."""


class AuthorityViolation(StateError):
    """A child requested authority outside its immutable capsule."""


class MissingState(StateError):
    """No state record matched an otherwise valid identity."""


class AmbiguousState(StateError):
    """More than one state record matched an identity."""


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def capsule_sha256(capsule: Mapping[str, object]) -> str:
    unsigned = dict(capsule)
    unsigned.pop("capsule_sha256", None)
    return sha256_bytes(canonical_json(unsigned))


def compact_invariant(capsule: Mapping[str, object]) -> dict:
    """Derive the small authority subset that must survive context recovery."""
    return {
        "assignment_id": capsule["assignment_id"],
        "handoff_id": capsule["handoff_id"],
        "runtime_session_id": capsule["runtime_session_id"],
        "parent_thread_id": capsule["parent_thread_id"],
        "agent_type": capsule["agent_type"],
        "requested_task_name": capsule["requested_task_name"],
        "canonical_agent_path": capsule["canonical_agent_path"],
        "root": capsule["root"],
        "owned_paths": capsule["owned_paths"],
        "excluded_paths": capsule["excluded_paths"],
        "git_authority": capsule["git_authority"],
        "stop_condition": capsule["stop_condition"],
        "pre_write_attestation_deadline": capsule["pre_write_attestation_deadline"],
        "authority_provenance": capsule["authority_provenance"],
    }


def compact_invariant_sha256(capsule: Mapping[str, object]) -> str:
    return sha256_bytes(canonical_json(compact_invariant(capsule)))


def provenance_policy_sha256(capsule: Mapping[str, object]) -> str:
    return sha256_bytes(canonical_json(capsule["authority_provenance"]))


def _timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise CorruptState(f"{field} must be a timestamp string")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as error:
        raise CorruptState(f"{field} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CorruptState(f"{field} must include a UTC offset")
    return parsed


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise CorruptState(f"{field} must be a UUID string")
    try:
        uuid.UUID(value)
    except ValueError as error:
        raise CorruptState(f"{field} must be a UUID string") from error
    return value


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CorruptState(f"{field} must be a non-empty string")
    return value


def _relative_paths(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CorruptState(f"{field} must be a list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or "\\" in item:
            raise CorruptState(f"{field} contains an invalid path")
        path = pathlib.PurePosixPath(item)
        if item == "." or path.is_absolute() or item != path.as_posix() or ".." in path.parts:
            raise CorruptState(f"{field} contains a non-canonical relative path")
        normalized.append(item)
    if len(set(normalized)) != len(normalized):
        raise CorruptState(f"{field} contains duplicate paths")
    return tuple(normalized)


def validate_capsule(capsule: object, assignment: str) -> dict:
    if not isinstance(capsule, dict):
        raise CorruptState("capsule must be a JSON object")
    if type(capsule.get("schema")) is not int or capsule["schema"] != SCHEMA:
        raise CorruptState("capsule has an invalid schema")

    _uuid(capsule.get("assignment_id"), "assignment_id")
    _uuid(capsule.get("handoff_id"), "handoff_id")
    for field in (
        "runtime_session_id",
        "parent_thread_id",
        "parent_turn_id",
        "spawn_tool_use_id",
        "worker_profile",
        "agent_type",
        "requested_task_name",
        "stop_condition",
    ):
        _nonempty_string(capsule.get(field), field)
    if "/" in str(capsule["requested_task_name"]) or "\\" in str(capsule["requested_task_name"]):
        raise CorruptState("requested_task_name must be one path segment")

    canonical_path = capsule.get("canonical_agent_path")
    if canonical_path is not None:
        _nonempty_string(canonical_path, "canonical_agent_path")

    root = capsule.get("root")
    if not isinstance(root, dict):
        raise CorruptState("root must be a JSON object")
    root_path = pathlib.Path(_nonempty_string(root.get("path"), "root.path"))
    if not root_path.is_absolute():
        raise CorruptState("root.path must be absolute")
    branch = root.get("branch")
    base_commit = root.get("base_commit")
    if branch is not None and not isinstance(branch, str):
        raise CorruptState("root.branch must be a string or null")
    if base_commit is not None and not GIT_OID_RE.fullmatch(base_commit):
        raise CorruptState("root.base_commit must be a full lowercase hash or null")
    if type(root.get("allow_descendant_head")) is not bool:
        raise CorruptState("root.allow_descendant_head must be boolean")
    if type(root.get("base_index_changed")) is not bool:
        raise CorruptState("root.base_index_changed must be boolean")
    if not isinstance(root.get("base_git_status_short"), str):
        raise CorruptState("root.base_git_status_short must be a string")

    capture_preflight = capsule.get("capture_preflight")
    if capture_preflight is not None:
        if not isinstance(capture_preflight, dict) or set(capture_preflight) != {
            "expected_root",
            "expected_branch",
            "expected_base_head",
        }:
            raise CorruptState("capture_preflight fields are not exact")
        expected_root = pathlib.Path(
            _nonempty_string(capture_preflight["expected_root"], "capture_preflight.expected_root")
        )
        if not expected_root.is_absolute():
            raise CorruptState("capture_preflight.expected_root must be absolute")
        if capture_preflight["expected_branch"] is not None and not isinstance(
            capture_preflight["expected_branch"], str
        ):
            raise CorruptState("capture_preflight.expected_branch is invalid")
        if not GIT_OID_RE.fullmatch(str(capture_preflight["expected_base_head"])):
            raise CorruptState("capture_preflight.expected_base_head is invalid")
        if expected_root.resolve() != root_path.resolve():
            raise CorruptState("capture_preflight.expected_root does not match root.path")
        if capture_preflight["expected_branch"] != branch:
            raise CorruptState("capture_preflight.expected_branch does not match root.branch")
        if capture_preflight["expected_base_head"] != base_commit:
            raise CorruptState(
                "capture_preflight.expected_base_head does not match root.base_commit"
            )

    _relative_paths(capsule.get("owned_paths"), "owned_paths")
    _relative_paths(capsule.get("excluded_paths"), "excluded_paths")
    git_authority = capsule.get("git_authority")
    if not isinstance(git_authority, dict):
        raise CorruptState("git_authority must be a JSON object")
    for operation in ("stage", "commit", "branch", "push"):
        if type(git_authority.get(operation)) is not bool:
            raise CorruptState(f"git_authority.{operation} must be boolean")

    verification = capsule.get("verification")
    if not isinstance(verification, list) or any(
        not isinstance(item, str) or not item.strip() for item in verification
    ):
        raise CorruptState("verification must contain only non-empty strings")

    provenance = capsule.get("authority_provenance")
    if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_FIELDS:
        raise CorruptState("authority_provenance fields are not exact")
    for field in (
        "authoritative_input_owners",
        "forbidden_caller_supplied_derived_facts",
    ):
        values = provenance[field]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or len(values) != len(set(values))
        ):
            raise CorruptState(f"authority_provenance.{field} is invalid")
    _relative_paths(
        provenance["authoritative_input_roots"],
        "authority_provenance.authoritative_input_roots",
    )
    if not provenance["authoritative_input_roots"]:
        raise CorruptState("authority_provenance.authoritative_input_roots is empty")
    seams = provenance["test_only_injection_seams"]
    if (
        not isinstance(seams, list)
        or any(not isinstance(item, str) or not item.strip() for item in seams)
        or len(seams) != len(set(seams))
    ):
        raise CorruptState("authority_provenance.test_only_injection_seams is invalid")
    _nonempty_string(
        provenance["required_derivation_boundary"],
        "authority_provenance.required_derivation_boundary",
    )

    dirty = capsule.get("preexisting_dirty")
    if not isinstance(dirty, list):
        raise CorruptState("preexisting_dirty must be a list")
    for item in dirty:
        if not isinstance(item, dict):
            raise CorruptState("preexisting_dirty entries must be objects")
        _relative_paths([item.get("path")], "preexisting_dirty.path")
        _nonempty_string(item.get("status"), "preexisting_dirty.status")
        if item.get("kind") not in {"file", "symlink", "deleted"}:
            raise CorruptState("preexisting_dirty.kind is invalid")
        digest = item.get("sha256")
        if item["kind"] == "deleted":
            if digest is not None:
                raise CorruptState("deleted preexisting_dirty.sha256 must be null")
        elif not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise CorruptState("preexisting_dirty.sha256 must be lowercase SHA-256")

    created_at = _timestamp(capsule.get("created_at"), "created_at")
    pre_write_deadline = _timestamp(
        capsule.get("pre_write_attestation_deadline"),
        "pre_write_attestation_deadline",
    )
    expires_at = _timestamp(capsule.get("expires_at"), "expires_at")
    if pre_write_deadline <= created_at or pre_write_deadline > expires_at:
        raise CorruptState("pre_write_attestation_deadline is outside capsule lifetime")
    if expires_at <= created_at:
        raise CorruptState("expires_at must be later than created_at")

    if not isinstance(assignment, str) or not assignment.strip():
        raise CorruptState("assignment must be a non-empty string")
    if capsule.get("assignment_sha256") != sha256_bytes(assignment.encode("utf-8")):
        raise CorruptState("assignment_sha256 does not match the assignment")
    digest = capsule.get("capsule_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise CorruptState("capsule_sha256 must be lowercase SHA-256")
    if digest != capsule_sha256(capsule):
        raise CorruptState("capsule_sha256 does not match the capsule")
    return capsule


def _path_is_owned(path: str, owned_paths: Sequence[str]) -> bool:
    candidate = pathlib.PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or path != candidate.as_posix():
        return False
    return any(candidate == pathlib.PurePosixPath(owner) or pathlib.PurePosixPath(owner) in candidate.parents for owner in owned_paths)


class StateStore:
    """Keyed lifecycle store. Every transition is serialized by an OS lock."""

    def __init__(self, root: pathlib.Path | str):
        self.root = pathlib.Path(root).resolve()

    def path(self, kind: str, identity: str) -> pathlib.Path:
        if kind not in STATE_KINDS:
            raise ValueError(f"unknown state kind: {kind}")
        return self.root / kind / f"{identity}.json"

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        if fcntl is None:
            raise StateError("schema-v2 locking is not qualified on this platform")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.root / ".compatibility-state.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _publish(self, target: pathlib.Path, value: object, *, replace: bool = False) -> None:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists() and not replace:
            raise StateError(f"state already exists: {target.name}")
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _read(self, path: pathlib.Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CorruptState(f"cannot decode {path.name}") from error
        if not isinstance(value, dict):
            raise CorruptState(f"{path.name} must contain a JSON object")
        return value

    def _validated_envelope(self, path: pathlib.Path) -> dict:
        envelope = self._read(path)
        if envelope.get("schema") != SCHEMA:
            raise CorruptState("envelope has an invalid schema")
        assignment = envelope.get("assignment")
        validate_capsule(envelope.get("capsule"), assignment)
        return envelope

    def _quarantine(self, source: pathlib.Path) -> pathlib.Path:
        target = self.path("quarantine", f"{source.stem}.{uuid.uuid4().hex}")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source.rename(target)
        return target

    def stage(self, capsule: dict, assignment: str) -> pathlib.Path:
        validate_capsule(capsule, assignment)
        if _timestamp(capsule["expires_at"], "expires_at") <= dt.datetime.now(dt.timezone.utc):
            raise StateError("refusing to stage an expired capsule")
        target = self.path("pending", capsule["handoff_id"])
        with self.locked():
            self._publish(target, {"schema": SCHEMA, "capsule": capsule, "assignment": assignment})
        return target

    def claim(self, handoff_id: str, identity: Mapping[str, str]) -> pathlib.Path:
        _uuid(handoff_id, "handoff_id")
        pending = self.path("pending", handoff_id)
        with self.locked():
            try:
                envelope = self._validated_envelope(pending)
            except CorruptState:
                if pending.exists():
                    self._quarantine(pending)
                raise
            capsule = envelope["capsule"]
            if _timestamp(capsule["expires_at"], "expires_at") <= dt.datetime.now(dt.timezone.utc):
                expired = self.path("expired", handoff_id)
                self._publish(expired, envelope)
                pending.unlink()
                raise StateError("pending capsule expired before child binding")
            self._assert_identity(capsule, identity)
            claimed = self.path("claimed", handoff_id)
            envelope["binding"] = dict(identity)
            self._publish(claimed, envelope)
            pending.unlink()
            return claimed

    def claim_unique(self, identity: Mapping[str, str]) -> tuple[str, pathlib.Path]:
        matches: list[tuple[str, pathlib.Path, dict]] = []
        now = dt.datetime.now(dt.timezone.utc)
        with self.locked():
            pending_directory = self.root / "pending"
            if not pending_directory.exists():
                raise MissingState("expected one pending authority capsule, found 0")
            for pending in sorted(pending_directory.glob("*.json")):
                try:
                    envelope = self._validated_envelope(pending)
                except CorruptState:
                    self._quarantine(pending)
                    continue
                capsule = envelope["capsule"]
                if _timestamp(capsule["expires_at"], "expires_at") <= now:
                    expired = self.path("expired", capsule["handoff_id"])
                    self._publish(expired, envelope)
                    pending.unlink()
                    continue
                try:
                    self._assert_identity(capsule, identity)
                except IdentityMismatch:
                    continue
                matches.append((capsule["handoff_id"], pending, envelope))
            if not matches:
                raise MissingState("expected one pending authority capsule, found 0")
            if len(matches) > 1:
                raise AmbiguousState(
                    f"expected one pending authority capsule, found {len(matches)}"
                )
            handoff_id, pending, envelope = matches[0]
            envelope["binding"] = dict(identity)
            claimed = self.path("claimed", handoff_id)
            self._publish(claimed, envelope)
            pending.unlink()
            return handoff_id, claimed

    def activate(self, handoff_id: str) -> pathlib.Path:
        claimed = self.path("claimed", handoff_id)
        with self.locked():
            envelope = self._validated_envelope(claimed)
            if not isinstance(envelope.get("binding"), dict):
                raise CorruptState("claimed envelope has no binding")
            capsule = envelope["capsule"]
            if _timestamp(capsule["expires_at"], "expires_at") <= dt.datetime.now(dt.timezone.utc):
                unresolved = self.path("unresolved", capsule["assignment_id"])
                self._publish(unresolved, envelope)
                claimed.unlink()
                raise StateError("claimed capsule expired before activation")
            envelope["runtime"] = {
                "recovery_count": 0,
                "context_lost": False,
                "first_git_attested_at": None,
            }
            active = self.path("active", capsule["assignment_id"])
            self._publish(active, envelope)
            claimed.unlink()
            return active

    def mark_recovery(self, assignment_id: str) -> int:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            runtime = envelope.get("runtime")
            if not isinstance(runtime, dict) or type(runtime.get("recovery_count")) is not int:
                raise CorruptState("active runtime metadata is invalid")
            runtime["recovery_count"] += 1
            self._publish(active, envelope, replace=True)
            return runtime["recovery_count"]

    def attest_tool_use(
        self,
        assignment_id: str,
        identity: Mapping[str, str],
        *,
        root: str,
        branch: str | None,
        head: str | None,
        changed_paths: Sequence[str] = (),
        git_operation: str | None = None,
        now: dt.datetime | None = None,
    ) -> dict:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            capsule = envelope["capsule"]
            observed_at = now or dt.datetime.now(dt.timezone.utc)
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise AuthorityViolation("attestation time must include a UTC offset")
            if _timestamp(capsule["expires_at"], "expires_at") <= observed_at:
                unresolved = self.path("unresolved", assignment_id)
                self._publish(unresolved, envelope)
                active.unlink()
                raise AuthorityViolation("active authority expired")
            runtime = envelope.get("runtime")
            if not isinstance(runtime, dict):
                raise CorruptState("active runtime metadata is invalid")
            if (
                runtime.get("first_git_attested_at") is None
                and observed_at > _timestamp(
                    capsule["pre_write_attestation_deadline"],
                    "pre_write_attestation_deadline",
                )
            ):
                raise AuthorityViolation("first Git attestation deadline elapsed")
            self._assert_identity(capsule, identity, envelope.get("binding"))
            expected_root = capsule["root"]
            if pathlib.Path(root).resolve() != pathlib.Path(expected_root["path"]).resolve():
                raise AuthorityViolation("root expansion is not authorized")
            if branch != expected_root["branch"]:
                raise AuthorityViolation("branch change is not authorized")
            if not expected_root["allow_descendant_head"] and head != expected_root["base_commit"]:
                raise AuthorityViolation("HEAD change is not authorized")
            if git_operation is not None:
                if git_operation not in capsule["git_authority"]:
                    raise AuthorityViolation("unknown Git operation")
                if not capsule["git_authority"][git_operation]:
                    raise AuthorityViolation(f"Git {git_operation} is not authorized")
            excluded = capsule["excluded_paths"]
            for path in changed_paths:
                if not _path_is_owned(path, capsule["owned_paths"]):
                    raise AuthorityViolation(f"path is outside owned_paths: {path}")
                if _path_is_owned(path, excluded):
                    raise AuthorityViolation(f"path is excluded: {path}")
            if runtime.get("first_git_attested_at") is None:
                runtime["first_git_attested_at"] = observed_at.isoformat()
                self._publish(active, envelope, replace=True)
            return envelope

    def list_active(self) -> list[tuple[str, dict]]:
        values: list[tuple[str, dict]] = []
        with self.locked():
            directory = self.root / "active"
            if not directory.exists():
                return values
            for path in sorted(directory.glob("*.json")):
                try:
                    envelope = self._validated_envelope(path)
                except CorruptState:
                    self._quarantine(path)
                    continue
                values.append((envelope["capsule"]["assignment_id"], envelope))
        return values

    def terminate_active(
        self,
        assignment_id: str,
        termination_evidence: Mapping[str, object],
    ) -> pathlib.Path:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            envelope["termination_evidence"] = dict(termination_evidence)
            unresolved = self.path("unresolved", assignment_id)
            self._publish(unresolved, envelope)
            active.unlink()
            return unresolved

    def expire_active(self, assignment_id: str, *, now: dt.datetime) -> pathlib.Path | None:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            expires_at = _timestamp(envelope["capsule"]["expires_at"], "expires_at")
            if expires_at > now:
                return None
            unresolved = self.path("unresolved", assignment_id)
            self._publish(unresolved, envelope)
            active.unlink()
            return unresolved

    def find_active(self, identity: Mapping[str, str]) -> tuple[str, dict]:
        matches: list[tuple[str, dict]] = []
        with self.locked():
            active_directory = self.root / "active"
            if not active_directory.exists():
                raise MissingState("expected one active authority capsule, found 0")
            for path in sorted(active_directory.glob("*.json")):
                try:
                    envelope = self._validated_envelope(path)
                except CorruptState:
                    self._quarantine(path)
                    continue
                try:
                    self._assert_identity(
                        envelope["capsule"], identity, envelope.get("binding")
                    )
                except IdentityMismatch:
                    continue
                matches.append((envelope["capsule"]["assignment_id"], envelope))
            if not matches:
                raise MissingState("expected one active authority capsule, found 0")
            if len(matches) > 1:
                raise AmbiguousState(
                    f"expected one active authority capsule, found {len(matches)}"
                )
            return matches[0]

    def finalize(
        self,
        assignment_id: str,
        attestation: Mapping[str, object],
        *,
        complete: bool,
    ) -> pathlib.Path:
        active = self.path("active", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(active)
            envelope["final_attestation"] = dict(attestation)
            disposition = "reported" if complete else "unresolved"
            final = self.path(disposition, assignment_id)
            self._publish(final, envelope)
            active.unlink()
            return final

    def adjudicate_parent(
        self,
        assignment_id: str,
        adjudication: Mapping[str, object],
    ) -> pathlib.Path:
        """Promote a report only from the trusted parent integration boundary."""
        if not isinstance(adjudication, Mapping) or set(adjudication) != PARENT_ADJUDICATION_FIELDS:
            raise StateError("parent adjudication fields are not exact")
        integrity_fields = PARENT_ADJUDICATION_FIELDS - {"evidence_sha256"}
        for field in integrity_fields:
            if adjudication[field] not in {"pass", "fail", "unverified"}:
                raise StateError(f"parent adjudication {field} is invalid")
        evidence_sha256 = adjudication["evidence_sha256"]
        if not isinstance(evidence_sha256, str) or not SHA256_RE.fullmatch(evidence_sha256):
            raise StateError("parent adjudication evidence_sha256 is invalid")
        reported = self.path("reported", assignment_id)
        with self.locked():
            envelope = self._validated_envelope(reported)
            envelope["parent_adjudication"] = dict(adjudication)
            complete = all(adjudication[field] == "pass" for field in integrity_fields)
            final = self.path("consumed" if complete else "unresolved", assignment_id)
            self._publish(final, envelope)
            reported.unlink()
            return final

    def record_context_lost(
        self,
        identity: Mapping[str, str],
        reason: str,
    ) -> pathlib.Path:
        if not reason.strip():
            raise StateError("context-lost reason must not be blank")
        marker_id = sha256_bytes(canonical_json(dict(identity)))
        target = self.path("lost", marker_id)
        marker = {
            "schema": 1,
            "identity": dict(identity),
            "reason": reason,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        with self.locked():
            self._publish(target, marker, replace=True)
        return target

    def context_lost_for(self, identity: Mapping[str, str]) -> dict | None:
        marker_id = sha256_bytes(canonical_json(dict(identity)))
        target = self.path("lost", marker_id)
        with self.locked():
            if not target.exists():
                return None
            marker = self._read(target)
            if (
                marker.get("schema") != 1
                or marker.get("identity") != dict(identity)
                or not isinstance(marker.get("reason"), str)
                or not marker["reason"].strip()
            ):
                self._quarantine(target)
                raise CorruptState("context-lost marker is invalid")
            return marker

    @staticmethod
    def _assert_identity(
        capsule: Mapping[str, object],
        identity: Mapping[str, str],
        binding: object | None = None,
    ) -> None:
        runtime_session_id = identity.get("runtime_session_id")
        child_thread_id = identity.get("child_thread_id")
        if not runtime_session_id:
            raise IdentityMismatch("runtime session id is missing")
        if not child_thread_id or child_thread_id != identity.get("agent_id"):
            raise IdentityMismatch("child thread id and agent_id do not match")
        if runtime_session_id != capsule["runtime_session_id"]:
            raise IdentityMismatch("runtime session does not match")
        if identity.get("parent_thread_id") != capsule["parent_thread_id"]:
            raise IdentityMismatch("direct parent thread does not match")
        if identity.get("agent_type") != capsule["agent_type"]:
            raise IdentityMismatch("agent type does not match")
        canonical = identity.get("canonical_agent_path")
        if not canonical or canonical.rstrip("/").split("/")[-1] != capsule["requested_task_name"]:
            raise IdentityMismatch("canonical AgentPath does not match requested task name")
        expected_canonical = capsule.get("canonical_agent_path")
        if expected_canonical is not None and canonical != expected_canonical:
            raise IdentityMismatch("canonical AgentPath does not match the capsule")
        if binding is not None and dict(identity) != binding:
            raise IdentityMismatch("child identity does not match the active binding")
