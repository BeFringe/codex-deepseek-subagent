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

Codex 0.147.0 source establishes a version-specific enforcement opportunity:

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
- owned and excluded paths;
- explicit stage/commit/branch/push authority;
- stop condition and exact verification contract;
- an authority-provenance policy naming authoritative input owners/roots,
  forbidden caller-supplied derived facts, explicit test-only seams, and the
  required owner-internal recomputation boundary;
- pre-existing dirty statuses, file kinds, and content hashes (null only for a
  deleted path);
- assignment hash, timestamps, and a canonical capsule hash.

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

SubagentStop requires a machine-checkable attestation containing assignment and
handoff ids, capsule hash, canonical path, recovery count, resolved Git state,
compact-invariant hash,
exact changed-path hashes, verification commands/exit codes, violation status,
Git index-change status, and `assigned_slice_complete`. The child cannot promote that last field into a
parent-task or feature-completion claim.
It also returns a small provenance claim: the policy hash, claimed derived-fact
origin, whether a test-only seam was used, and an optional receipt digest.

If a final narrative says no assignment or no writes while consumed transport
state and disk hashes prove owned-path changes, classify it as return-context
loss. Freeze and freshly verify the contribution. Parent/disk/capsule evidence
outranks narrative, but missing attestation is never a completion proof.

Successful SubagentStop adjudication advances only to `reported`. The parent
separately decides location integrity, mutation-scope integrity, verification
freshness, and derivation/provenance integrity. A self-consistent digest over
caller-chosen derived facts can still self-authorize a false PASS. Only fresh
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
| P6 final gate | context-loss narrative, slice overclaim, disk-hash mismatch | wrong final must be blocked |
| P6a causal provenance | digest-valid forged facts, real-mode test seam, owner-internal shared derivation | caller self-authorization must fail |
| P7 parity/regression | POSIX/Windows and existing DeepSeek route | all green before Phase 2 |

Phase 2 cannot start until P1–P7 and live evidence close the Phase 1 gate. Phase
3 cannot start before Phase 2.

## Baseline and rollback

The workflow checkout began at `main@1377b76`. The repository and live Hook are
schema 1, role-single-slot, manually staged, and delete the claimed state after
initial delivery. Live Hook/skill/state remain untouched during Phase 0/1
development. Schema 2 uses an isolated state directory and configuration until
qualified. Rollback selects the recorded schema 1 adapter baseline without
claiming durable continuity; it never changes the OpenAI parent provider or
deletes quarantine/unresolved evidence.

The following pre-existing dirty files belong to the user/prior work and are
preserved: `README.md`, `README.en.md`, `docs/advanced.md`,
`docs/advanced.en.md`, and `tests/test_plaintext_handoff.py`. Their audited
hashes are recorded in the Chinese document.

## Version-locked Codex evidence

Local CLI: `codex-cli 0.147.0`. The official `rust-v0.147.0` tag peels to
`be6e8eac029b183056b7e4402879f15d2c85f61b`.

- [Hook schemas](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/hooks/src/schema.rs)
- [startup-only SubagentStart dispatch](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/hook_runtime.rs)
- [compact Hook behavior](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/hooks/src/events/compact.rs)
- [SubagentStop continuation gate](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/hooks/src/events/stop.rs)
- [requested name to AgentPath](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/tools/handlers/multi_agents_common.rs)
- [V2 canonical-path return](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [SessionMeta identity](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/protocol/src/protocol.rs)
- [Hook session id is shared by root and descendants](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/session/session.rs)
- [transcript materialization test](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/session/tests.rs)

No official documentation was found that promotes all of these source behaviors
to a long-term API guarantee. Re-run the probes for every minimum supported
Codex baseline and fail closed on contract drift.
