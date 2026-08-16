# Phase 1 Evidence Log

Status: in progress. This file primarily records provider-free candidate
evidence. A separately labelled legacy-configuration restoration below does not
qualify direct write or describe a G4 candidate installation.

## 2026-08-15 takeover baseline and fresh results

The migrated checkout was compared to a newly fetched authoritative remote
before any content edit. The SSH config used a GitHub alias different from the
repository remote, so fetch used the migrated GitHub identity as a one-command
override. No key or credential content was read, copied, or recorded.

```text
branch=main
HEAD=076ee0df9aca11fbc0c19a6ccd7cd8befc0051f7
origin/main=076ee0df9aca11fbc0c19a6ccd7cd8befc0051f7
remote=git@github.com:BeFringe/codex-deepseek-subagent.git
```

The initial diff consisted of 62 `100644 -> 100755` changes with zero changed
blob bytes. After the remote equality check, only those migrated mode bits were
normalized; the resulting worktree was clean. No commit was reset or checked
out. The handoff checkpoint `9bc00342857e430e4d5533ef3e3fa1d60d637ad1`
remains an ancestor, while the two later snapshot/cost commits remain intact.

Host/tool drift from the handoff snapshot:

```text
host=macOS 26.2 (25C56), Darwin arm64, Asia/Shanghai
Codex app=26.810.41047 (6570)
Codex CLI=0.148.0-alpha.9 (snapshot: 0.147.0)
Python user default=3.14.7 arm64
Apple /usr/bin/python3=3.9.6 (unchanged)
Git=2.50.1
```

The first fresh provider-free run under Apple Python executed the suite but had
one loader error because 3.9 lacks `tomllib`; it was environment drift, not an
assertion failure. A clean bundled-Python run before new work then reproduced
the handoff result exactly:

```text
Ran 143 tests in 24.551s
OK
agent template checks passed
```

The same 143 tests also passed under the new user-default Python 3.14.7. After
the P6c, mutation-matrix, and writer-claim fixtures in this continuation, the
latest fresh result is recorded below in the writer-claim section.

The original standalone negative probes were rerun without touching live state:

```json
{"direct_write_qualified":false,"platform":"posix","same_uid_child_exit_code":0,"same_uid_rollout_protected":false,"same_uid_state_protected":false,"schema":1}
```

`check_state_trust.py --require-protected` exited 2 as designed. The current
mutation matrix verified every pinned source anchor and reported
`direct_write_qualified=false`; `--require-qualified` also exited 2. These are
expected fail-closed results, not test failures.

## Explicitly authorized legacy v4 configuration restoration

After the baseline probes, the user explicitly requested restoration of
`codex-deepseek-subagent-config-20260814` so a new LocalCAT task can use the
pre-existing v4 worker. Every archive file first passed `MANIFEST.sha256`.
All six target groups were absent, so no existing Codex Hook, skill, agent, or
global `AGENTS.md` content was overwritten.

The restored skill, UI metadata, plaintext Hook script, and marked global
`AGENTS.md` have the exact archive hashes. The agent TOML changes only the
Fedora writable root to `/Users/pearly/文档/CAT/localcat-feature5`; `hooks.json`
changes the Fedora command to the absolute local Python 3.14.7 and Codex-home
paths. Network remains disabled. The nonportable old Hook trust state and two
skill drafts were not installed, and the archive contains no auth/API material.

An isolated state-directory smoke test successfully executed stage,
`SubagentStart` context delivery, and one-shot consumption without starting a
worker or calling an external provider. Codex doctor loaded the configuration.
The current app forbids automated control of its own trust UI, so a restarted
Codex process still requires the user to run `/hooks` and approve only the
reviewed `^v4_flash_worker$` command. This restores the legacy schema-1 route;
it does not install schema 2, provide G4 install/rollback evidence, open the
ZHIPU/GLM bridge, or change `direct_write_qualified`.

## Codex 0.148.0-alpha.9 mutation-surface matrix

The current executable matrix is
[`probes/codex-0.148.0-alpha.9-mutation-surfaces.json`](../probes/codex-0.148.0-alpha.9-mutation-surfaces.json),
validated by [`probes/check_mutation_surfaces.py`](../probes/check_mutation_surfaces.py).
It is pinned to the official tag's peeled source commit
`9392c3fa5bcda342b5b96a1a04d67b2f781617c2`. The schema-1 0.147 matrix remains
replayable as historical evidence.

Current result: **direct write is unqualified**. In addition to the original
negative spaces, schema 2 closes over function-shaped extensions, Codex
configuration persistence, permission expansion, deferred tool search, and
provider-hosted model tools. The mutation-capable blockers are:

```text
shell, write_stdin, mcp, code_mode, extension_freeform,
extension_function, dynamic_function, codex_config_mutation,
authority_escalation, agent_control
```

Tool search and the currently enumerated hosted web-search tool are recorded as
non-mutating/non-authorizing surfaces. A newly mutating hosted capability is an
unknown surface and invalidates qualification until it is pinned.

## Historical Codex 0.147.0 mutation-surface matrix

The executable matrix is
[`probes/codex-0.147.0-mutation-surfaces.json`](../probes/codex-0.147.0-mutation-surfaces.json),
validated by [`probes/check_mutation_surfaces.py`](../probes/check_mutation_surfaces.py).
It is pinned to official source commit
`be6e8eac029b183056b7e4402879f15d2c85f61b`.

Its historical result was also **direct write is unqualified**. The important
negative space remains relevant because the current source anchors still match:

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

Because current Codex still treats SubagentStart as context-injection-only, that Hook
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
isolated fixtures: no verified Codex 0.148.0-alpha.9 host termination receipt is yet
available, so the live path must refuse overlapping direct-write reassignment.

## Native parent/child same-path race witness

On 2026-08-15, a LocalCAT `feature5` native xhigh child at
`/root/m_v16_candidate_u4` and its `/root` parent concurrently modified the
declared-owned `tm_candidate_index.py` in one shared worktree. The parent added
a performance experiment while the child inserted its assigned prototype.
Their insertions interleaved and left a parent `return distance` at class scope;
the child detected foreign bytes, paused, and reported `SyntaxError: 'return'
outside function`. The parent stopped the child and repaired only the
indentation.

The supplied witness binds root
`/Users/pearly/文档/CAT/localcat-feature5`, branch `feature5`, full HEAD
`3f59f60998da63f5cdc8cf3145dc354ec0560143`, parent/child AgentPaths, assignment
paths, and post-repair file SHA-256
`2551bd81f8b0e57a7d9da579efd6ad9a28e8051c21a9cd6a0d235523b6d73368`.
A fresh product-independent read confirmed that HEAD, branch, digest,
`python3 -m py_compile tm_candidate_index.py`, and `git diff --check` all pass;
the three assignment paths remain modified and unstaged.

Classification: `p5b_parent_active_child_single_writer_violation`. This is not
an assignment-transport, Hook, SessionMeta, compact/resume, callback, or sandbox
failure on the available evidence. It is a shared-worktree authority-scheduling
failure: declared ownership and the “not alone” narrative did not exclude the
parent from the active child's path. The existing handover fixtures cover old
child to replacement-child transfer, not parent mutation during active child
authority. A capsule/claim refresh would only detect some between-call races;
it cannot close an in-flight TOCTOU window.

This is a real negative witness, not evidence that the isolated adapter already
mediates the parent. P5b must add parent/child single-writer live probes and a
joint writer-lease or host serialization/sandbox barrier. Until that seam is
visible and enforced on both sides, `direct_write_qualified=false` remains the
only valid decision.

### Read-only child foreign-dirty restore witness

On 2026-08-15, a second LocalCAT native xhigh child at
`/root/o_release_atomic_xhigh` had an explicit read-only assignment: no write,
stage, commit, or push. While the child was active, its `/root` parent
intentionally changed `tests/fixtures/retrieval_gate_c_roots_v1.json` and
`tests/fixtures/feature5_gate_a_v1.json` in the shared worktree. The child
misclassified those foreign bytes as a test side effect and acknowledged using
`apply_patch` to restore two retrieval-root digest lines to HEAD. The parent
immediately interrupted it.

The frozen observation binds root
`/Users/pearly/文档/CAT/localcat-feature5`, branch `feature5`, and full HEAD
`3f59f60998da63f5cdc8cf3145dc354ec0560143`. The child restore made the retrieval
fixture clean at HEAD SHA-256
`08a6f822d1c2f4c8e8776641a440014f02b4d9f843707cc6bd84a5250035c1df`, while the
Gate A fixture remained dirty at
`345b402c6e4ef0c92f2e85650f1fa259ceabb3d6e20a6f58c614ca7dec932ea0`. After
termination freeze, the parent became the sole writer and restored its two
retrieval lines. A fresh read confirmed both fixtures dirty, with retrieval
SHA-256 `a84129b1265ed567bdd97ea874dfc3de0cd19e37fdbcf2b2c25dbc19e976f07e`
and the same Gate A SHA-256; branch and HEAD remain unchanged. No credential
value or diagnostic mutation was reported. A sibling native xhigh child exposed
to the same parent changes correctly remained read-only, showing that prompt
compliance is variable behavior rather than enforcement.

Primary classification: `p4_read_only_child_mutation_violation`. Secondary
classification: `p5b_parent_active_child_single_writer_violation`. Provenance
classification: `foreign_dirty_restore_overwrite`. Returning bytes to HEAD is
not a read operation and a final clean status does not erase the unauthorized
write event. The earlier witness involved two purported writers; this subtype
is stricter because the child never held mutation ownership at all.

The isolated runtime guard now has a provider-free fixture in which the parent
creates dirty bytes and a child presents an explicit restore patch. The guard
denies `apply_patch` before execution and the test verifies the exact parent
bytes, hash, and dirty state survive. This is isolated adapter evidence only;
the native xhigh incident proves that a read-only assignment narrative by
itself does not mediate the live tool surface.

Evidence-availability boundary: on 2026-08-16 the Feature 5 parent confirmed
that it retains the incident classification summaries and final disk/barrier
observations, but not enough raw material to reconstruct the complete original
tool acknowledgement, tool-use id, or interrupt/termination timeline without
ambiguity. These two incidents therefore remain summary-level negative
witnesses. They do not close a live P4/P5b, callback, or termination probe, and
no synthetic event sequence is substituted for the missing raw evidence.

## Provider-free parent/sibling apply-patch writer claims

`hooks/writer_lease_guard.py` now supplies the first bidirectional
single-writer candidate for the source-pinned structured `apply_patch` surface.
A non-target parent or sibling PreToolUse proves its real SessionMeta actor,
parses the raw patch envelope, includes add/delete/update and move-destination
paths, resolves absolute/`..`/symlink aliases against the actual Git root, and
persists a hash-bound `writer_claim` before returning. Assignment capture and
its final atomic stage both scan those claims under the same state lock.

An overlapping patch against pending/claimed/active/reported/unresolved child
ownership is denied before execution and creates a path/actor/tool-use conflict
receipt without storing patch content. Conversely, an in-flight parent claim
blocks overlapping child capture. Disjoint path claims remain structurally
allowed. Strict read-only capture requires a quiet root because its exact clean
review baseline cannot be established during any in-flight writer.
After child authority is unresolved, the exact direct parent may reclaim an
overlapping path only when a strong quiescence barrier exists and the full
current snapshot still equals that barrier. The new claim freezes the handover
digests. A late disk change after the barrier blocks parent reclaim.

Only the exact actor and tool-use id in a successful PostToolUse can move the
claim to a before/after snapshot receipt. Pinned Codex source calls PostToolUse
only after successful output. A failed/partial tool, wrong actor, missing
callback, or crash therefore leaves the durable claim in place and blocks later
overlap. The isolated candidate intentionally has no TTL cleanup that could
convert uncertain liveness into authority; a future recovery path needs a
host-owned tool-failure termination/quiescence and disk barrier.

The runtime guard also changed one-shot denial semantics for target read-only
children. Requesting `apply_patch` or any other non-allowlisted tool now freezes
active authority before execution as `read_only_child_mutation_attempt`. The
receipt records only the tool name and fresh disk snapshot. Pre-attempt dirty
bytes are `pre_attempt_disk_drift_unattributed`, so the guard does not assign
causality merely from final Git state.

Provider-free fixtures cover active-child conflict/audit, parent-claim versus
child-capture ordering, atomic overlapping parent claims, disjoint concurrency,
strict-read-only quiet-root capture, symlink/absolute/`..`/excluded/move
aliases, exact successful release,
wrong-identity non-release, executable Hook dispatch, and hash-tampered claim
quarantine. This still does not provide a filesystem transaction across path
resolution and execution, a success callback for failed tools, live native
Hook evidence, or coverage for shell, `write_stdin`, MCP, extensions, code mode,
permissions, and agent control. `direct_write_qualified=false` remains the only
valid result.

The fresh complete provider-free result after this slice is:

```text
Ran 176 tests in 27.277s
OK
agent template checks passed
```

The pinned 0.148.0-alpha.9 source anchors, including structured apply-patch
input and success-only PostToolUse dispatch, verified with zero drift. The
mutation matrix still returned `direct_write_qualified=false`, and the same-UID
probe still overwrote its disposable rollout/state fixtures as expected.

The lifecycle now distinguishes a worker report from parent integration. A
trusted parent adjudication must separately pass location integrity,
mutation-scope integrity, verification freshness, derivation/provenance
integrity, and feasibility-contract integrity before reported state can become
consumed. Any fail or unverified dimension moves the report to unresolved
evidence.

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

## Diagnostic locality, crash semantics, and evidence identity

The diagnostic contract now maps every stable owner failure code to an exact
set of allowed `overall` and/or `per_item` localities. Tests prove the same code
survives both explicitly allowed shapes, while an undeclared shape fails rather
than becoming a generic error. Unknown or missing owner codes remain the only
generic-fallback cases. This is structural fidelity, not parent acceptance of
the claimed behavior.

`hooks/termination_guard.py` accepts only an exact closed boundary catalog and
one owner-internal fresh-process observation per seam/ordinal. Its API iterates
the closed catalog itself and does not accept caller-precomputed report lists.
The schema requires `os._exit` and an
expected durable resolution from the five enumerated states. A real subprocess
fixture proves `os._exit` skips `finally`, while `KeyboardInterrupt` unwinds it;
the latter cannot stand in for process-death evidence. Missing boundaries,
same-process observation, primitive drift, or durable-resolution drift fail
closed.

`hooks/evidence_binding.py` preflights executed root, hashed root, Git source
identity, and canonical output before invoking the expensive callback. It opens
each output component using directory fds and no-follow flags, requires a
regular terminal, then rechecks device/inode and file kind. Fixtures prove root
mismatch prevents the callback, symlinked directories are rejected, and
terminal replacement after execution is detected.

The capsule also models read-only review continuation with a prior assignment,
frozen cumulative base, corrected full-OID tip, prior-finding digest,
unresolved finding ids, and mandatory clean worktree. Capture proves an
ancestor base/current tip and evidence source identity. This does not qualify
same-thread follow-up: Codex 0.148.0-alpha.9 has no proven trusted follow-up capture in
this adapter, so thread continuity alone remains insufficient authority.

## Closed-registry counts and relation closure

The execution contract now freezes closed registries with exact item ids and
`mechanical_cardinality_only` count authority. Final attestations carry one
inventory summary per registry. SubagentStop rejects missing/duplicate
registries, item-order or digest drift, and any declared count unequal to the
item cardinality. A negative fixture returns 18 valid ids with a declared count
of 15 and is blocked; correcting only the mechanically derived count is
accepted as an untrusted report.

`hooks/closed_world_guard.py` separates row-codec validity from cross-object
closure. Fixtures first prove every owner and handoff row matches its exact
schema, then detect a missing owner, an orphan owner, and a many-to-one relation.
The only absent relation accepted is a terminal object explicitly marked
`tombstone` or `clear`; any other absence state fails. The capsule freezes the
schemas, nonterminal one-to-one cardinality, absence semantics, and terminal
exception in the compact invariant. Parent fresh recomputation remains the
integration authority.

Review continuation now also freezes the old review base and tip plus an exact
narrowed objective. A same-prefix but unequal corrected full OID is rejected at
capture; neither the child nor thread continuity may guess the intended tip.

## Parent-owned capsule feasibility

`hooks/feasibility_guard.py` builds the pre-dispatch feasibility slot by
invoking an owner-supplied counterexample probe and bounded-completion assessor;
its public API has no precomputed outcome parameter. The receipt freezes the
exact claimed invariant, probe input/evidence hashes, completion condition,
work-budget unit/cardinality-domain/limit, proposed mechanism, measured
invocation lower bound, scale evidence, optional equivalence-compression
conservation evidence, unresolved assumptions, and parent-owner decision.

A negative fixture models a mechanism that is safe but needs 17 steps under a
frozen budget of 10. The counterexample probe runs, but the bounded assessor
returns false and the decision is `block`. A second independently strengthened
mechanism closes in 9 steps and becomes dispatchable. Counterexample-found and
blocking-assumption cases also contradict `dispatch` and fail capsule
validation. Direct-write capture rejects a block decision before pending state
is created.

The feasibility owner must be one of the capsule's authoritative input owners,
and the completion condition must also appear in the immutable stop condition.
The whole slot survives in the compact invariant. “No counterexample found” is
recorded only as bounded contribution evidence, never a universal proof or
integration authority. This fixture does not run arbitrary commands from the
live Hook and therefore does not add a mutation or credential surface.

The scale fixtures additionally model 3,000 qualifying identities compressed
into 300 owner-derived semantic classes under a 2,048 expensive-invocation
budget. The exact class-domain measurement dispatches only when fan-out returns
to all 3,000 identities. A persisted mechanism that counts object identities,
caller-supplied grouping, a fan-out total of 2,999, or a small cohort without
monotonicity/adversarial scale evidence blocks. A recovery fixture records an
unchanged generated artifact outside ownership, then proves that changing the
same artifact remains an unauthorized mutation; preserved identity does not
expand the assignment.

Equivalence grouping is not accepted as a precomputed builder argument. The
builder invokes the owner derivation callback over the frozen input and stamps
the authoritative owner/origin fields itself. A callback result that attempts
to self-report `grouping_origin` is structurally rejected rather than trusted.

## P6c isolated end-to-end cost and staged-authority fixtures

Status: **provider-free mechanics implemented; live/representative qualification
pending.** A product-independent large-scale incident showed that semantic
correctness, fail-closed behavior, invocation-domain feasibility, and
small-cohort tests can all pass while the end-to-end mechanism still violates
its frozen latency gate.

`hooks/cost_phase_guard.py` keeps invocation and latency as separate owner
authorities. It accepts no caller-supplied pass flag. The invocation receipt
freezes unit, cardinality domain, and limit. The latency receipt independently
freezes unit, nearest-rank p95 statistic, limit, sample count, full sample/window
definitions, representative-dense scope, and separate multiplicity and
equivalence-class distribution identities. The guard computes p95 from raw
samples; a passing invocation count cannot mask a failing dense p95, and a
three-item cohort or SQL-only spike cannot authorize the end-to-end claim.

The frozen catalog contains exact coarse, refine, and materialize phases. Every
phase re-proves ordered input/output registries, their canonical identities,
source/root binding, authority epoch, conservation edges, timing unit/
definition/limit, and evidence digest. The owner must expose an internal
mutation callback exactly once; the guard also observes before and after every
phase and after final materialization. An opaque phase without that internal
seam is rejected rather than treated as mediated.

The refinement fixture freezes an owner-derived refinement-set identity and
mechanically checks its reduction equation plus
`true <= refined_upper_bound <= coarse_upper_bound`. Missing, duplicate,
orphaned, or cross-phase-substituted identities fail closed. The final mixed
frontier is compared to a separately computed authoritative frontier by exact
cardinality, canonical identity order, payload, and final phase output; a
self-consistent digest around substituted content remains a failure.

Sixteen focused tests cover the positive reference and independent negative
seams: dense p95 overrun, small cohort, SQL-only sample, phase timing overrun,
bound drift, root/epoch drift, registry substitution, conservation failure,
cardinality/order/payload drift, before/mid/after mutation races, missing
internal visibility, and precomputed-pass API injection. The fresh complete
suite after these additions is:

```text
Ran 160 tests in 24.286s
OK
agent template checks passed
```

This does not supply a representative product distribution, real per-phase
timing, or a live mediated phase boundary. If the real mechanism runs inside one
opaque tool event, it must be split into observable invocations or P6c remains
pending. `feasibility_contract_integrity` is therefore still unverified for
live multi-phase delivery and direct write remains unqualified.
