# Native Codex Heterogeneous-Worker Compatibility Model

[简体中文](compatibility-model.md)

Status: v1 control-plane design, 2026-08-12. Phase 0 evidence and probe-driven
Phase 1 implementation are approved, but Phase 1 has not passed G4. Phases 2
and 3 are not approved for implementation yet.

## Boundary

This repository is a removable compatibility layer, not a global model router.
The OpenAI parent remains on native OpenAI. Codex continues to own discovery,
spawn, canonical AgentPath, parent relationships, permissions, lifecycle,
wait/callback, cancellation, and the Multi-Agent V2 graph.

The repository owns only assignment representation compatibility, authority
continuity for an external worker, and worker-specific provider wire
compatibility. Assignment transport, wire transport, and request normalization
are orthogonal and must remain independently replaceable.

Authority continuity and artifact causal provenance are also orthogonal.
SessionMeta, Git state, paths, and content hashes prove where and when bytes
changed; they do not prove that a PASS was derived from the authoritative input
owner instead of caller-injected, internally self-consistent derived facts.

## Four compatibility layers

### A. Agent/runtime identity

Qualify discover, spawn, requested task name, canonical AgentPath, parent
relation, role, lifecycle, wait/callback, and cancellation. A
`requested_task_name` is the parent-provided path segment. A
`canonical_agent_path` is the runtime identity derived by Codex. Never overload
one `task_name` field with both meanings.

### B. Assignment transport

A worker selects `native` or `plaintext-v2`. Plaintext v2 captures the real,
self-contained `spawn_agent.message` in a trusted `PreToolUse(spawn_agent)`
Hook without rewriting spawn arguments. A `handoff_id` identifies one transport
instance; it is not a logical task identity.

### C. Authority continuity

Initial delivery does not prove that the worker retains the same authority for
the whole turn. An active immutable capsule must survive compact/resume. Any
ambiguous recovery, identity mismatch, owned-path expansion, Git-authority
expansion, or stop-condition expansion fails closed.

Codex 0.148.0-alpha.9 source establishes a version-specific enforcement opportunity:

- `SubagentStart` runs only for a thread-spawn child at startup; child compact
  and resume do not rerun it.
- `PreCompact` and `PostCompact` expose child identity but cannot inject
  additional context.
- child `PreToolUse` exposes session/turn/agent identity, tool input, and the
  tool-use id, and can inject context or block a tool.
- `SubagentStop` receives the final message and parent/child transcript paths,
  and can block completion with a continuation prompt.

The Phase 1 candidate is therefore a durable active capsule plus a PreToolUse
guard for every mutation-capable tool and a SubagentStop final-attestation
gate. Until live probes prove complete write-path coverage, direct-write
authority continuity is not qualified and the worker must remain read-only.

### D. Wire/provider

A worker independently selects `native`, `responses-direct`, or
`responses-bridge`, then a request profile. Use `glm-thinking` for the candidate
GLM-family normalization profile; ZHIPU is the provider, not the model family.
Credentials never enter a handoff, capsule, log, or commit. A profile cannot
enlarge the live Codex permission boundary.

A Phase 2 profile may only declare whether a worker/provider supports this
provenance contract and the required runtime posture. Authoritative owners,
derived facts, and the real/test boundary remain assignment-capsule authority;
the provider profile must not default, infer, or normalize them. Wire conversion
cannot promote a provider-returned digest or PASS into provenance proof.

## Immutable boundary capsule

The schema 2 capsule contains at least:

- `assignment_id`, `handoff_id`, shared runtime session, direct parent thread,
  turn, and tool-use identity;
- worker profile, role, requested task name, and proven canonical AgentPath;
- resolved Git root, branch, base commit, and descendant-HEAD policy;
- initial index/status facts and an optional narrowing-only capture preflight
  over expected root, branch, and the complete Git object id;
- owned and excluded paths;
- explicit stage/commit/branch/push authority;
- ownership-handover references to trusted host termination/quiescence barriers
  for every overlapping prior assignment;
- stop condition and exact verification contract;
- an authority-provenance policy naming authoritative input owners/roots,
  forbidden caller-supplied derived facts, explicit test-only seams, and the
  required owner-internal recomputation boundary;
- an execution contract declaring `strict_read_only` or
  `direct_write_unqualified`, an exact full-OID review range, required
  invariants, diagnostic-code fidelity, expensive-rerun authority, and any
  hash-bound non-authorizing replay baselines;
- pre-existing dirty statuses, file kinds, and content hashes (null only for a
  deleted path);
- assignment hash, timestamps, and a canonical capsule hash.
- a bounded first-Git-attestation deadline.

`assignment_id` is immutable authority; `handoff_id` is one delivery attempt.
The canonical path is bound only after runtime metadata proves it. Recovery may
create a new, explicitly linked assignment over a frozen dirty baseline; it may
not replay a consumed handoff or mutate the old capsule to expand authority.
A digest over attacker-selected derived inputs is necessary consistency
evidence, never sufficient provenance evidence.

Recovery context starts with a deterministic compact invariant containing exact
runtime/child/parent identity, root/base, owned and excluded paths, Git
authority, authoritative input roots, stop condition, and completion predicate.
The full capsule and assignment remain in durable state; the compact copy cannot
replace or expand them.
The optional capture preflight compares parent-supplied expected location facts
with the Hook's current actual Git snapshot and blocks spawn on any difference.
It cannot authorize a commit/branch, change path ownership, infer a replacement
task, or accept a matching HEAD prefix in place of the full object id.
Ownership handover is not a child- or assignment-supplied permission. It only
references a host-owned barrier created after old authority is frozen and does
not erase mixed provenance.

`strict_read_only` requires a clean captured worktree, an exact committed
base/head range, no owned or excluded paths, and no Git authority. It therefore
does not consume a mutation handover. A proven input baseline binds an
authoritative owner, repository-relative manifest, actual file hash, and
known-true stable failure code, while requiring `non_authorizing=true` and
`reuse_without_authority_expansion`. It cannot create path, Git, derivation, or
completion authority. Stable owner failure codes pass through unchanged; only
missing or unclassified codes may map to the generic fallback. A prohibition on
literal expensive reruns remains authority even when a review is long-running.
Each stable failure code must explicitly allow `overall`, `per_item`, or both
diagnostic localities. Moving a code between declared localities is not missing
behavior; an undeclared locality is not silently relabelled generic. The parent
still freshly adjudicates behavior instead of inferring it from nesting.

A crash claim binds a closed boundary id/seam/ordinal catalog, the literal
`os._exit` primitive, and an expected durable resolution from `UNJOURNALED`,
`BLOCKED`, `CANCELLED`, `COMPLETED`, or `TERMINAL_NOOP`. KeyboardInterrupt,
exceptions, and finally unwinding are not process-death evidence. Every result
must be observed by an owner-internal fresh process. The public fixture accepts
an owner observer callback, not caller-precomputed crash reports that could
recreate shallow self-attestation.

An evidence runner preflights that executed checkout, hashed checkout, Git
source identity, and canonical output share one authority before expensive
execution. It walks root to output with no-follow dirfds and re-proves that the
terminal is the same regular-file identity afterwards.

A review follow-up is a new assignment, not authority inherited from thread
continuity. It freezes the prior assignment, cumulative base, old review
base/tip, fresh corrected tip, prior-finding digest, unresolved finding ids,
exact narrowed objective, and clean-worktree requirement. The isolated adapter currently captures only trusted
`PreToolUse(spawn_agent)`; no equivalent trusted native follow-up/send-input
capture is proven. The continuation fields are therefore schema/capture
fixtures, not a claim that live same-child follow-up authority is qualified.

Worker-enumerated item or test ids may be high-volume contribution evidence,
but a narrative aggregate count has no authority. A closed registry freezes the
exact ids; SubagentStop recomputes cardinality and checks exact order, uniqueness,
and canonical digest. A strict per-row codec is also insufficient for
closed-world integrity. Relation contracts bind both object schemas,
nonterminal one-to-one cardinality, missing/orphan-as-error absence semantics,
and the sole tombstone/clear terminal-absence exception. The parent/owner still
freshly recomputes relation closure.

Before a direct implementation reaches pending state, a parent-owned
`capsule_feasibility_attestation` freezes the exact claimed invariant, a cheap
executable counterexample probe, the bounded completion condition and work
budget, the exact budget unit and cardinality domain, the proposed mechanism,
and unresolved assumptions. Its owner id must
be an authoritative input owner; a child or provider cannot author or repair
these derived decisions.

An executed falsification probe is an active attempt, not proof. Dispatch is
self-consistent only when the current probe finds no counterexample, an
owner-internal assessor shows that the proposed mechanism satisfies its own
completion condition inside the frozen budget, and no unresolved assumption is
blocking. A mathematically safe but empirically too-loose mechanism therefore
blocks dispatch until independently strengthened. Freezing a narrative cannot
turn it into a feasible proof boundary.

The owner assessor also freezes the mechanism's measured unit/cardinality
domain and a lower bound on required expensive invocations. Any mismatch with
the budget domain blocks dispatch even when both counts are individually below
the numeric limit. A small green cohort supports a scale claim only through a
frozen monotonicity proof or an adversarial multiplicity/scale witness. Proposed
equivalence compression must use owner-derived grouping, keep evaluated-class
and proven-identity counts separate, and conserve the full fan-out; a
caller-supplied or non-conserving grouping is non-dispatchable even when its
digest is self-consistent. The builder invokes an owner derivation callback and
stamps owner/origin itself; it exposes no precomputed-grouping seam and does not
trust a caller-reported `grouping_origin` label.

Recovery may freeze the exact identity of reusable generated artifacts together
with dirty tracked hashes. Such an identity is a baseline, not ownership: it
does not add to `owned_paths`, and any out-of-scope artifact mutation remains
blocked.

An invocation budget and an end-to-end latency gate are independent authorities;
one number or one `mechanism_satisfies` flag cannot stand for both. The cost
contract must separately freeze the actual cost unit, limit/statistic,
multiplicity/equivalence-class distribution digest, representative worst dense
witness, sample count, the p95 window/calculation definition, phase timings,
and the full completion stop condition. A small cohort, storage-query-only
spike, or local phase benchmark is contribution evidence, not authority for an
end-to-end scale or deliverability claim, unless monotonicity is proven.

A multi-phase conservative refinement is derived by the authoritative owner
inside a frozen phase catalog. It obtains a coarse upper bound `U1`, derives a
refinement set `R`, obtains `U2`, and mechanically proves
`true <= U2 <= U1`. Every phase re-proves input/output identity, root/source
binding, and authority epoch. Closed registries and owner-declared set
equations mechanically prove cross-phase conservation. The final mixed-frontier
response must match the authoritative result in exact cardinality, canonical
order, and item identity; aggregate counts or self-consistent digests are not
enough.

Mutation races before a phase, during refinement/owner calls, and after final
materialization are separate failure seams. If several phases run inside one
opaque tool call, a Hook cannot infer the invisible intermediate boundaries
from an assignment prompt. An owner-internal operation or stronger host
mediation must re-attest and fail closed at every seam; otherwise P6c remains
open. Runtime convenience assumptions or local optimizations cannot let the
child rewrite the frozen cost unit, distribution, completion condition, phase
authority, or stop condition. A changed mechanism requires a new parent-owned
feasibility capsule.

The provider-free builder invokes owner callbacks and has no parameter for
precomputed probe or budget outcomes. Isolated capture validates the structure,
owner provenance, and dispatch decision. A future live Hook integration of an
arbitrary executable probe would need separate proof that the probe is cheap,
read-only, credential-safe, and not a new mutation surface.

## State lifecycle

```text
pending/<handoff_id>.json
  -> claimed/<handoff_id>.json
  -> active/<assignment_id>.json
  -> reported/<assignment_id>.json
  -> consumed/<assignment_id>.json
```

All transitions use an OS-owned lock. Identity mismatch rejects one claimant
without consuming or quarantining valid state. Only corrupt/untrusted state is
quarantined. The active authority copy remains until an accepted final
attestation or safe expiry; an expired capsule with writes becomes unresolved
evidence rather than being silently deleted.
`reported` means only that the callback and contribution were recorded. Only a
trusted parent adjudication can move it to `consumed`.

### Interrupt/cancel and ownership handover

An `interrupt_agent`/cancel return acknowledges a control request; it does not
prove that the child process, existing PTY, outer executor, MCP call, or every
other mutation source is quiescent. An interrupt acknowledgement alone cannot
authorize immediate reassignment of the same owned paths.

While a mutation-capable assignment is pending, claimed, active, reported, or
unresolved, its `owned_paths` must be in one single-writer domain that includes
the parent and every sibling child. A parent `apply_patch`, shell command, or
other write to the same or hierarchically overlapping path is a competing
ownership claim, not implicit integration authority. Declaring ownership in an
assignment, warning that other agents exist, or refreshing the capsule before
each write is not filesystem exclusion: a TOCTOU window remains between the
refresh and the mutation. To take those paths back, the parent must stop its own
overlapping writes, freeze child authority, obtain the strong termination plus
quiescence receipt and post-termination disk barrier below, and acquire the
writer lease in a new authority epoch. Direct write remains unqualified unless
both parent and child mutation dispatch can be jointly mediated or serialized.

Overlapping ownership requires this order: freeze old active authority into
unresolved state; obtain a host-owned
`child_terminated_and_mutations_quiesced` receipt; then capture exact
root/branch/HEAD/index/status/path hashes after termination. The barrier binds
the prior assignment and child ThreadId. New pending staging rechecks state
conflicts under the state lock, takes a fresh pre-stage snapshot, matches its
`capture_snapshot_sha256` and the barrier snapshot, and stores the barrier digest
in the new capsule. Active/pending/claimed/reported conflicts, a missing barrier, or any
snapshot drift block reassignment.

Any later PreToolUse from the frozen child is denied for lack of active binding.
A late mutation before re-spawn records `late_mutation_after_interrupt` and
`overlapping_assignment_provenance` and blocks capture. A mutation after new
capture is caught by the replacement child's exact first-attestation baseline
and freezes the new authority with the same mixed-provenance status. If the host
cannot prove termination plus quiescence, the new assignment cannot claim the
same paths; elapsed time and ordinary interrupt acknowledgement are not proof.

Mixed bytes remain frozen for parent review of barrier hashes, source causality,
and fresh tests. A later child's attestation cannot attribute all bytes solely
to the later assignment.
A state lock is not a filesystem transaction. The replacement child's exact
first attestation covers the remaining window after the fresh pre-stage
snapshot; neither check becomes strong proof without a host quiescence
guarantee.
Likewise, that lock only serializes capsule transitions. It cannot stop the
parent from changing an owned file between or during active-child tool calls.
A later hash mismatch can freeze mixed provenance, but cannot retroactively make
interleaved writes safe; live qualification still needs host dispatch
serialization or an independent sandbox/block.

A committed-range strict read-only review claims no mutation ownership and does
not use this handover lifecycle. It still re-attests its compact invariant,
clean snapshot, and exact review range at every tool event and final return;
disk drift stops the task rather than upgrading the read-only capsule.
Nor may a read-only child “clean up,” restore, check out, reset, delete, or patch
foreign dirty bytes created by the parent or another writer back to the captured
or HEAD content. Even when the final digest equals the committed baseline and
Git status changes from dirty to clean, the operation is an unauthorized
mutation that may erase an authoritative parent contribution. A read-only
narrative or claim refresh cannot grant that write. The guard must reject every
mutation surface before execution and leave adjudication of the foreign bytes
to the parent as the sole writer.

## Exact runtime binding

Parent PreToolUse captures the real `session_id`, `turn_id`, `tool_use_id`,
message, requested task name, role, fork mode, transcript path, and cwd. Stage
failure blocks spawn. Non-plaintext workers pass unchanged. The Hook does not
return `updatedInput`.

`SubagentStart` does not directly expose the parent, task name, or AgentPath.
The claimant must read the first `SessionMeta` from the materialized child
transcript and jointly prove:

- Hook `session_id == SessionMeta.session_id` for the root/descendant shared
  runtime session;
- Hook `agent_id == SessionMeta.id` for the child ThreadId;
- direct parent thread id, role, and canonical path match the pending capsule;
- the requested task name has one unique logical relation to the actual path;
- any precomputed expected path exactly matches.

Zero or multiple matches fail closed. A bounded retry is allowed only if a live
probe demonstrates a transient flush race followed by a unique identity.

### Why an assignment cannot repair outer-runtime invisibility

An assignment or capsule is model input, not outer runtime mediation. It cannot
make `write_stdin` emit a missing second PreToolUse, decompose opaque Bash into
complete path/Git effects, add a trustworthy side-effect schema to arbitrary
MCP/dynamic/custom/freeform tools, wrap the code-mode outer executor, or protect
same-UID writable rollout/state files. Repeating “do not write or commit” states
intent but cannot prove or block a mutation the control plane cannot see, and
the narrative can be lost after compaction. Any uncovered negative space keeps
direct write unqualified/read-only until a runtime or sandbox boundary proves a
block.

## Compact/resume and final gates

Prompt-level `TASK.CONTEXT_LOST` is not the runtime guarantee. PreCompact records
a recovery epoch without deleting active state. Every mutation-capable tool
must re-resolve one active capsule and re-attest root, branch/base, owned paths,
Git authority, and epoch before execution. Missing, ambiguous, or corrupt state
blocks new writes and scope expansion.

The capsule carries a short bounded first-attestation deadline. Before the first
tool execution, the guard compares actual root, branch, full HEAD, index, status,
and path hashes with immutable state. Any exact mismatch or elapsed deadline
terminates active authority into unresolved evidence before mutation.

A Hook event is not a wall-clock timer. If a child performs long computation
without emitting an event, PreToolUse cannot wake itself or cancel the child.
Bounded fast-stop therefore also requires a parent/host scheduler to invoke the
isolated watchdog and interrupt/cancel when it returns
`parent_cancel_required=true`. Without that outer evidence the adapter proves
only that the next event is denied, not that the provider turn stopped exactly
at the deadline. An assignment prompt cannot repair this limitation.
The current isolated API models the trusted receipt shape and transitions only;
Codex 0.148.0-alpha.9 has not yet been proven to expose a receipt with this strong
guarantee. Live direct-write handover therefore remains unqualified.

SubagentStop requires a machine-checkable attestation containing assignment and
handoff ids, capsule hash, canonical path, recovery count, resolved Git state,
compact-invariant hash,
exact changed-path hashes, verification commands/exit codes, violation status,
Git index-change status, closed-registry inventory summaries, and
`assigned_slice_complete`. SubagentStop requires each summary to exactly cover
one capsule registry and verifies declared count equals item cardinality plus
the canonical item digest. The child cannot promote the last field or a summary
count into a
parent-task or feature-completion claim.
It also returns a small provenance claim: the policy hash, claimed derived-fact
origin, whether a test-only seam was used, and an optional receipt digest.

If a final narrative says no assignment or no writes while consumed transport
state and disk hashes prove owned-path changes, classify it as return-context
loss. Freeze and freshly verify the contribution. Parent/disk/capsule evidence
outranks narrative, but missing attestation is never a completion proof.

Watchdog evidence for no final return has separate classes. An exact unchanged
baseline is `unresponsive_no_disk_change`; a delta before first attestation is
`unresponsive_with_disk_change_before_attestation`; an attested contribution
without return is `unresponsive_with_contribution`. Only a returned lost/invalid
narrative plus a real contribution is
`return_context_loss_with_contribution`. None is completion proof, and they are
not interchangeable.
If capsule location/base is itself untrusted, the adapter must not force a disk
delta from that baseline. It reports `initial_authority_mismatch`,
`baseline_comparable=false`, and `disk_changed=null`; the parent must use an
independent trusted baseline rather than misclassifying HEAD mismatch as a
contribution.

Successful SubagentStop adjudication advances only to `reported`. The parent
separately decides location integrity, mutation-scope integrity, verification
freshness, derivation/provenance integrity, and feasibility-contract integrity.
A self-consistent digest over caller-chosen derived facts can still self-authorize
a false PASS, and a green cohort cannot repair a budget unit/cardinality-domain
mismatch or missing scale evidence. Only fresh
verification plus source-level causal review of an owner-internal real-mode
derivation can advance to `consumed`. Expensive authoritative derivation may be
computed once and shared across outputs only inside that owner boundary;
test-only injection seams remain explicitly non-final. Worker tests and hashes
are contribution evidence, not integration authority.
The provenance output is still a worker claim. The Hook can match its policy
hash and reject an explicit caller/test-only completion, but cannot prove the
child is truthful; the parent must revalidate any receipt at the owner boundary.

## Phase 1 probes and gates

| Probe | Required evidence | Failure action |
|---|---|---|
| P1 spawn capture | exact message, pass/block, non-target pass, no input rewrite | block Phase 1 |
| P2 identity/flush | root/nested, serial/concurrent, POSIX and Windows-equivalent evidence | no weak next-role fallback |
| P3 lifecycle | pending→claimed→active→reported→consumed, expiry and crash recovery | no deletion after initial delivery |
| P4 write guard | shell, patch, code-mode nested tools, MCP/write apps, Git | read-only posture if any bypass exists |
| P5 recovery | compact after a correct initial write; path/Git expansion attempts | any unauthorized write fails the gate |
| P5a pre-write deadline | same-prefix wrong full HEAD, capture preflight, no-event watchdog/cancel signal | mismatch/timeout must not reach expensive mutation |
| P5b ownership handover | interrupt ack, strong termination receipt, post-termination barrier, late writes before/after re-spawn | overlapping claim without quiescence fails |
| P6 final gate | context-loss narrative, slice overclaim, disk-hash mismatch | wrong final must be blocked |
| P6a causal provenance | digest-valid forged facts, real-mode test seam, owner-internal shared derivation | caller self-authorization must fail |
| P6b feasibility contract | budget/measurement domain drift, scale witness, owner-derived equivalence fan-out, recovery artifact baseline | mismatch, forged grouping, and artifact authority expansion must fail |
| P6c end-to-end cost/phase continuity | dense-case p95, U1→R→U2, phase binding/conservation, mixed-frontier exactness, before/mid/after races | small-cohort extrapolation, phase drift, or an unblocked race fails |
| P7 parity/regression | POSIX/Windows and existing DeepSeek route | all green before Phase 2 |

Phase 2 cannot start until P1–P7 and live evidence close the Phase 1 gate. Phase
3 cannot start before Phase 2.

## Baseline and rollback

The workflow checkout is now
`main@076ee0df9aca11fbc0c19a6ccd7cd8befc0051f7`, equal to `origin/main` after
the 2026-08-15 fresh fetch. At the user's explicit request, the migrated legacy
v4 agent/skill/schema-1 plaintext Hook has been restored; the G4 candidate/schema
2 has not been installed, and a new Codex process still requires user Hook trust
review. Schema 2 continues to use only isolated state and configuration until
qualified. Rollback selects the recorded schema 1 adapter baseline without
claiming durable continuity; it never changes the OpenAI parent provider or
deletes quarantine/unresolved evidence.

The following pre-existing dirty files belong to the user/prior work and are
preserved: `README.md`, `README.en.md`, `docs/advanced.md`,
`docs/advanced.en.md`, and `tests/test_plaintext_handoff.py`. Their audited
hashes are recorded in the Chinese document.

## Version-locked Codex evidence

Local CLI: `codex-cli 0.148.0-alpha.9`. The official
`rust-v0.148.0-alpha.9` tag peels to
`9392c3fa5bcda342b5b96a1a04d67b2f781617c2`.

- [Hook schemas](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/hooks/src/schema.rs)
- [subagent and compact runtime binding](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/hook_runtime.rs)
- [compact Hook behavior](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/hooks/src/events/compact.rs)
- [SubagentStop continuation gate](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/hooks/src/events/stop.rs)
- [requested name to AgentPath](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/tools/handlers/multi_agents_common.rs)
- [V2 canonical-path return](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [SessionMeta identity](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/protocol/src/protocol.rs)
- [Hook session id is shared by root and descendants](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/session/session.rs)
- [transcript materialization and persist/flush distinction](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/rollout/src/recorder.rs)

No official documentation was found that promotes all of these source behaviors
to a long-term API guarantee. Re-run the probes for every minimum supported
Codex baseline and fail closed on contract drift.
