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
The successful PreToolUse context is rebuilt from active state and includes the
complete immutable capsule plus the exact original assignment, not only an id
or narrative reminder.

The probe corrected an earlier identity assumption: Hook `session_id` is the
runtime session shared by root and descendants, not the child ThreadId. Exact
binding therefore keeps `runtime_session_id`, direct `parent_thread_id`, and
child `agent_id == SessionMeta.id` as separate fields.

The current guard intentionally allows only a small read-only tool set. All
mutation tools, including `apply_patch`, remain blocked because the complete
mutation surface is not qualified.

The synthetic SubagentStop gate accepts only an exact, standalone JSON
attestation envelope. It computes the actual Git top level, branch, HEAD,
short status, index-change state, changed-path set, file kind, and SHA-256 hashes. Extra completion
claims, unauthorized commits, stale hashes, out-of-scope paths, and identity
mismatch block the final return and retain active evidence. Verification command
identity must exactly match the capsule, and a complete claim requires zero exit
codes.

A truthful incomplete, context-lost, or authority-violation attestation is not
promoted to completion: it returns to the parent with the actual disk snapshot
and moves the capsule to unresolved evidence. An exact, complete,
non-violating attestation reaches reported state, not integration authority.

This is still not a live guarantee. In particular, SessionMeta and capsule
state are trustworthy only if the child permission boundary cannot modify the
rollout or state directory. POSIX mode bits do not isolate two processes using
the same OS account. Until a live sandbox probe proves that boundary, direct
write remains unqualified/read-only.

`probes/check_state_trust.py` makes that negative result executable without
touching the live install. It creates mode-0700/0600 disposable state and
rollout fixtures, then launches a separate same-UID process. On the current
POSIX host both files were overwritten successfully:

```json
{"direct_write_qualified":false,"same_uid_rollout_protected":false,"same_uid_state_protected":false}
```

This does not claim that a live child will attack those files; it proves that
mode bits alone are not the required trust boundary. `--require-protected`
therefore exits 2.

## Isolated plaintext-v2 capture fixture

`hooks/assignment_transport.py` removes manual staging from the candidate
protocol. A targeted parent PreToolUse captures the actual V2 `spawn_agent`
message, requested task name, agent type, fork mode, shared runtime session,
parent ThreadId/AgentPath, tool-use id, Git root/branch/HEAD, and pre-existing
dirty path kinds/hashes. It never returns `updatedInput`, so the native message
remains the assignment source.

The self-contained spawn message must terminate with one strict, provider-free
`BEGIN/END CODEX WORKER AUTHORITY` JSON declaration. The declaration supplies
only owned/excluded paths, Git authority, stop condition, verification contract,
authority-provenance policy, execution contract, and TTL. Runtime ids, repository facts, assignment/hash ids, and expected child
AgentPath are added by the trusted parent Hook. Unknown fields—including any
credential field—block spawn.

SubagentStart reconstructs child identity from SessionMeta, finds exactly one
keyed pending capsule, and moves it through claimed to active before delivering
the compatibility copy. Wrong child identity preserves pending state. Root,
nested, serial, and concurrent behavior are covered by isolated fixtures; live
flush timing and sandbox trust are still open gates.

Because Codex 0.147.0 treats SubagentStart as context-injection-only, that Hook
cannot cancel a child after a binding failure. The isolated adapter records an
exact child-identity `lost` marker, denies every subsequent tool for lack of an
active capsule, and permits only the literal `TASK.CONTEXT_LOST` final return.
The intended assignment remains pending for its correct child.

Capture now accepts an optional narrowing-only location preflight. The fixture
uses a wrong full HEAD with the same 12-character prefix as the actual HEAD and
proves the parent PreToolUse blocks spawn without creating pending state or disk
changes. The exact current root/branch/full HEAD case stages normally. The Hook
does not derive replacement authority from a failed assertion.

`hooks/compatibility_hook.py` is an executable isolated entry point spanning
parent PreToolUse capture, SubagentStart claim, child PreToolUse re-attestation,
PreCompact recovery epoch, and SubagentStop adjudication. It requires an
explicit state directory and target agent-type list and is not referenced by
the installer or live configuration. Its end-to-end fixture confirms the state
path reaches reported only after an exact post-recovery final attestation.

## Pre-write deadline and unresponsive-run evidence

The capsule freezes a first-Git-attestation deadline plus exact initial
root/branch/full HEAD/index/status/path hashes. A same-prefix but unequal full
HEAD fails the first synthetic PreToolUse, moves the active capsule to
unresolved evidence, and leaves the repository unchanged.
Because a wrong base is not a trustworthy comparison point, its termination
evidence records `baseline_comparable=false` and `disk_changed=null`; it does
not relabel the HEAD mismatch as contribution bytes.

`hooks/authority_watchdog.py` is a one-shot isolated watchdog for the no-event
negative space. A test invokes it just beyond the deadline; it moves authority
to unresolved, returns `parent_cancel_required=true`, and exits 2 under
`--fail-on-termination`. This signal is designed for a parent/host scheduler.
It is not wired into live configuration and does not claim that Hook callbacks
provide their own clock or cancellation.

Disk-first classification distinguishes:

- `unresponsive_no_disk_change`: root/branch/HEAD/index/status/path hashes equal
  the captured baseline;
- `unresponsive_with_disk_change_before_attestation`: a delta exists before the
  first durable Git attestation;
- `unresponsive_with_contribution`: an attested long run has a delta but no
  final return;
- `return_context_loss_with_contribution`: the child returned an invalid/lost
  narrative after real contribution bytes appeared.

The new fixtures cover all four classes. All remain
untrusted contribution/termination evidence, never integration authority.

## Ownership-handover and late-mutation fixtures

The state core now treats an interrupt acknowledgement as insufficient. An
overlapping replacement is blocked until old active authority is unresolved and
a host-owned `child_terminated_and_mutations_quiesced` receipt is followed by an
exact disk snapshot. The receipt binds the old runtime session and child
ThreadId. Handover is rechecked atomically with pending-state publication, so
concurrent overlapping captures allow only one owner; disjoint concurrent
captures remain supported.
The capsule also freezes `capture_snapshot_sha256`; capture takes a fresh second
snapshot immediately before state publication and rejects drift. The state lock
does not claim to lock the filesystem. A late write after that snapshot remains
the replacement child's first-attestation responsibility.

After freeze, a synthetic old-child PreToolUse is denied because no active
binding remains. A late write before replacement capture causes an overlap
evidence record with `late_mutation_after_interrupt` and
`overlapping_assignment_provenance`; spawn is denied. A late write after capture
but before the replacement child's first tool is detected even though the path
is owned: exact baseline equality fails, the replacement authority becomes
unresolved, and mixed provenance is retained.

The replacement capsule links barrier and prior-assignment hashes, so a clean
handover may preserve old dirty bytes without falsely attributing them to the
new child. A fixture freezes a prior dirty file, then proves the replacement
capsule contains both its pre-existing hash and the prior-assignment barrier
link. Parent fresh source review and tests are still required. These are
isolated fixtures: no verified Codex 0.147.0 host termination receipt is yet
available, so the live path must refuse overlapping direct-write reassignment.

The lifecycle now distinguishes a worker report from parent integration. A
trusted parent adjudication must separately pass location integrity,
mutation-scope integrity, verification freshness, and derivation/provenance
integrity before reported state can become consumed. Any fail or unverified
dimension moves the report to unresolved evidence.

## Causal-provenance negative fixtures

`hooks/provenance_guard.py` models a separate owner boundary. Its negative
fixture builds an artifact whose payload, caller-supplied oracle facts, and
digest are all internally self-consistent, then proves real-mode adjudication
still rejects it because the derived-fact origin is the caller. A second
fixture rejects an explicitly test-only injection seam in real mode. The
positive reference computes an expensive authoritative derivation exactly once
and shares it across two outputs only inside one owner-internal operation.

The real-mode API accepts only raw authoritative input; it has no parameter for
precomputed derived facts or a caller-claimed origin. Its owner-internal
operation recomputes derived facts and compares the entire candidate output.
The separate test-only API marks injected artifacts `non_final`. Parsing origin
from a worker narrative would recreate the same self-authorization flaw. The
compatibility capsule freezes owners, input roots, forbidden derived facts,
test-only seams, and the recomputation boundary; parent source-level review and
fresh evidence remain the integration authority.

The long-run context-loss fixture removes the only active capsule, leaves a real
owned-path disk mutation, and presents a completion narrative. SubagentStop
blocks it: real bytes are contribution evidence, but neither the narrative nor
their hashes restore the missing authority chain.

## Strict read-only and diagnostic-fidelity fixtures

The execution contract now distinguishes strict read-only review from
unqualified direct write. Capture of a strict read-only task requires a clean
worktree, exact full-OID base/head range, empty owned/excluded paths, and all Git
authority disabled. A fixture proves this posture stages without an ownership
handover; dirty state, a mismatched range, or replay-manifest hash drift blocks
before pending state is published.

The compact invariant retains required state-machine invariants, stable and
known-true failure codes, the generic fallback, the literal-rerun prohibition,
and hash-bound proven input baselines. Each baseline must name an authoritative
owner, live under an authoritative input root, match the actual regular-file
SHA-256, and remain explicitly non-authorizing. It can prevent reconstructing
an expensive input but cannot grant mutation, Git, derivation, or completion
authority.

`hooks/diagnostic_guard.py` proves stable owner codes are returned unchanged and
only missing or unknown codes use `TASK.FAILURE_UNCLASSIFIED`. A separate
negative fixture rejects literal expensive rerun without explicit authority and
shows that a replay-baseline reference contains no owned-path, Git, or completion
fields. These are provider-free isolated fixtures; they do not qualify live
direct write or alter the mutation/quiescence gates.
