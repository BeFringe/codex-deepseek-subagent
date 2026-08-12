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
