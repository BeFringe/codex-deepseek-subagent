# Phase 1 Evidence Log

Status: in progress. This file records provider-free evidence only. It does not
qualify direct write and does not describe a live installation.

## Codex 0.147.0 mutation-surface matrix

The executable matrix is
[`probes/codex-0.147.0-mutation-surfaces.json`](../probes/codex-0.147.0-mutation-surfaces.json),
validated by [`probes/check_mutation_surfaces.py`](../probes/check_mutation_surfaces.py).
It is pinned to official source commit
`be6e8eac029b183056b7e4402879f15d2c85f61b`.

Current result: **direct write is unqualified**. The important negative space is:

- `write_stdin` deliberately emits no second PreToolUse event, so a child can
  drive an already-running mutable process after recovery;
- shell input receives PreToolUse as `Bash`, but an opaque command does not
  prove owned-path or Git confinement;
- MCP, dynamic, and agent-control function calls receive PreToolUse, but their
  arbitrary schemas have no provider-independent side-effect contract;
- extension custom/freeform payloads do not inherit the default function-only
  PreToolUse payload;
- code-mode nested calls return to normal dispatch, but the outer custom
  executor has no PreToolUse payload and its isolation still needs a live probe.

Consequently the compatibility layer must deny unknown tools and use a proven
read-only allowlist until each mutation class has an exact guard or a stronger
sandbox boundary. A catch-all matcher alone is not sufficient.

## Schema-v2 state-core fixture

`hooks/compatibility_state.py` is an isolated, provider-independent library; it
is not referenced by the installed or repository schema-v1 Hook. Its tests
currently prove:

- canonical assignment/capsule hashes detect authority mutation;
- pending state is keyed by handoff id and supports concurrent staging;
- identity mismatch preserves a valid pending assignment;
- corrupt/untrusted state is quarantined;
- initial delivery retains active authority for recovery;
- recovery-time re-attestation blocks owned-path and Git expansion;
- expired active authority becomes unresolved evidence rather than disappearing.

SessionMeta parsing, Hook event adapters, compact/resume fixtures, and
SubagentStop disk adjudication remain open and must not be inferred from these
state-core tests.

## Isolated runtime-guard fixture

`hooks/runtime_guard.py` now exercises the version-locked Hook shapes without
installing them. The fixture reads only the first rollout `SessionMeta` and
requires exact Hook session/agent id, parent id, role, and canonical AgentPath.
Every synthetic PreToolUse re-reads that metadata and re-resolves exactly one
active capsule. PreCompact increments a durable recovery epoch; a changed
parent or AgentPath after that point is denied.

Each synthetic PreToolUse also derives the actual Git top level, branch, HEAD,
status, changed paths, and content hashes from the Hook cwd. Tests mutate HEAD
and an out-of-scope path after recovery and prove the next otherwise read-only
tool call is denied; the guard does not accept capsule values as self-evidence.

The probe corrected an earlier identity assumption: Hook `session_id` is the
runtime session shared by root and descendants, not the child ThreadId. Exact
binding therefore keeps `runtime_session_id`, direct `parent_thread_id`, and
child `agent_id == SessionMeta.id` as separate fields.

The current guard intentionally allows only a small read-only tool set. All
mutation tools, including `apply_patch`, remain blocked because the complete
mutation surface is not qualified.

The synthetic SubagentStop gate accepts only an exact, standalone JSON
attestation envelope. It computes the actual Git top level, branch, HEAD,
short status, changed-path set, file kind, and SHA-256 hashes. Extra completion
claims, unauthorized commits, stale hashes, out-of-scope paths, and identity
mismatch block the final return and retain active evidence. Verification command
identity must exactly match the capsule, and a complete claim requires zero exit
codes.

A truthful incomplete, context-lost, or authority-violation attestation is not
promoted to completion: it returns to the parent with the actual disk snapshot
and moves the capsule to unresolved evidence. Only an exact, complete,
non-violating attestation reaches consumed state.

This is still not a live guarantee. In particular, SessionMeta and capsule
state are trustworthy only if the child permission boundary cannot modify the
rollout or state directory. POSIX mode bits do not isolate two processes using
the same OS account. Until a live sandbox probe proves that boundary, direct
write remains unqualified/read-only.
