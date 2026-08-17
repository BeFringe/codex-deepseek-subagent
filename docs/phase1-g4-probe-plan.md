# Phase 1 / G4 executable probe plan

Status: **read-only qualification only**. `direct_write_qualified=false` remains
mandatory until every live/platform gate below closes. After explicit user
authorization, a qualification-only live candidate may be installed and trusted
for the probes below; that installation does not enable Phase 2, alter the
parent provider, or let an external worker adjudicate its own behavior.

## Current pinned baseline

- Continuation input began at local
  `main@dcdc6207503af8117e48b3f6178137f07f5b0523`; the current installed G4
  script source is evidence commit
  `8d23bc1ff18f8032541bfb28e7c78ec4332fe501`; refreshed remote baseline remains
  `origin/main@076ee0df9aca11fbc0c19a6ccd7cd8befc0051f7`.
- Host: macOS 26.2 (`25C56`), Darwin arm64, Asia/Shanghai.
- Codex app: `26.810.41047` (`6570`); CLI: `0.148.0-alpha.9`.
- Codex source: tag `rust-v0.148.0-alpha.9`, peeled commit
  `9392c3fa5bcda342b5b96a1a04d67b2f781617c2`.
- Provider-free Python: user default `3.14.7`; Apple `/usr/bin/python3`
  remains `3.9.6` and is not replaced.
- Legacy v4 agent/skill/schema-1 plaintext Hook: restored after explicit user
  authorization. Migration did not restore an equivalent G4
  `PreToolUse`/`PostToolUse`/compact/stop configuration. On 2026-08-17 the user
  separately authorized installing a qualification-only G4 candidate. Its
  files/state are now installed beside the unchanged v4 Hook, but the new Hook
  entries still require user trust and no live candidate event has yet run.

The migrated checkout initially had 62 blob-identical executable-bit changes.
They were normalized only after a fresh remote fetch proved every content blob
and `origin/main` identical. The SSH config's GitHub host alias did not match the
repository remote; the fetch therefore required the migrated GitHub identity as
a one-command override. No key content was read or recorded.

## Re-pinned Codex contract and its limit

The current source still supplies `PreToolUse`, `SubagentStart`, `PreCompact`,
and `SubagentStop`. Child Hook inputs use the root/shared Hook `session_id` and
carry optional/exact `agent_id` plus `agent_type`; `SubagentStart` does not carry
the requested task name or canonical path. The binding must therefore be joined
against the child's first `SessionMeta`, not inferred from event order or role.

For a thread-spawn child, the current serialized `SessionMeta` payload contains
the shared runtime `session_id`, child thread `id`, and duplicated flattened
parent/role/nickname/path identity. The same direct parent, depth, role,
nickname, and canonical path also live under
`source.subagent.thread_spawn`; both representations must agree exactly. V2
spawn derives the path by joining the parent path with the requested task name
and returns the canonical path as `task_name`. Source inspection is not live
identity evidence: root, nested, serial, and concurrent joins remain probes.

The installed 0.148.0-alpha.9 binary's embedded command-output schema also
contains `PreToolUseHookSpecificOutputWire.additionalContext`. Provider-free
tests may therefore validate a candidate shape, but only a target-child live
probe may promote post-compact context delivery from schema evidence to runtime
evidence.

The payload creation timestamp and the outer JSONL rollout-record timestamp are
also separate clocks: the recorder creates the outer timestamp when it writes
the already-created SessionMeta. A valid record requires payload time no later
than record time; exact equality is not a contract.

`hook_transcript_path()` waits for `persist(Standard)`, and the recorder waits
for the writer acknowledgement. The writer uses file `flush()` but this path has
no `sync_all()`/fsync durability barrier. It supports an immediate-read probe; it
does not prove crash/power-loss durability or post-termination quiescence.

`PostToolUse` carries the same optional child identity, stable tool name/input,
tool-use id, and tool response, but current source dispatches it only after a
successful tool output. A writer claim therefore releases on an exact success
callback; tool failure or callback loss must leave it unresolved until a
host-owned failure/quiescence barrier proves disk state.

`write_stdin` still intentionally emits no second `PreToolUse`. Function-shaped
extensions get the default function Hook payload, while freeform/custom and
tool-search payloads do not. Provider-hosted web search bypasses local tool Hook
routing. These are explicit negative spaces, not prompt-fixable gaps.

The current [official Hooks guide](https://learn.chatgpt.com/docs/hooks) also
fixes the candidate's event-level failure semantics. A `PreToolUse` internal
failure must emit an explicit deny (or blocking exit 2), not an arbitrary Hook
failure. `PreCompact` must return `continue=false` to stop before compaction,
while `SubagentStop` must request continuation with `decision=block`.
`PostToolUse` cannot undo a mutation, so a failed writer-claim release stops the
flow and leaves the lease unresolved. `SubagentStart` cannot cancel a child;
binding failure can only inject `TASK.CONTEXT_LOST`, after which later tool
guards plus the host watchdog/cancel path remain mandatory.

Pinned anchors:

- [Hook schemas](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/hooks/src/schema.rs)
- [Hook runtime and transcript selection](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/hook_runtime.rs)
- [shared root Hook session id](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/session/session.rs)
- [SessionMeta identity fields](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/protocol/src/protocol.rs)
- [requested name to AgentPath](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/tools/handlers/multi_agents_common.rs)
- [V2 spawn canonical return](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [rollout persist/flush distinction](https://github.com/openai/codex/blob/9392c3fa5bcda342b5b96a1a04d67b2f781617c2/codex-rs/rollout/src/recorder.rs)

## P1 native plaintext assignment prerequisite

Do not run the identity matrix as qualification evidence until a native V2
runtime supplies a live receipt accepted by
`probes/check_plaintext_assignment_candidate.py`. The candidate must default to
encrypted communication and require an explicit session-level plaintext
transport opt-in. That opt-in grants no mutation authority and may not change
the OpenAI parent provider, auth path, native AgentControl, AgentPath,
permissions, lifecycle, wait, callback, cancel, or Multi-Agent V2 behavior.

For `spawn_agent`, `send_message`, and `followup_task`, the receipt must prove:

1. the message schema selected the plaintext Responses branch and the function
   call carried exact `encrypted_function_args: []`;
2. one permitted delivery call had byte-identical PreToolUse, handler, and
   recipient fingerprints, with no `encrypted_content` fallback;
3. a **distinct paired call with the same message bytes** was observed by
   blocking PreToolUse and denied before both handler dispatch and recipient
   execution; one call may never be counted as both the delivery and deny case;
4. canonical AgentPath plus native V2 identity/lifecycle remained intact;
5. missing/private response metadata failed closed, while the default encrypted
   mode and V1 behavior remained unchanged;
6. evidence stored only lengths/hashes and never plaintext or credential values.

The schema-2 checker qualifies only this assignment seam. It rejects receipts
that conflate successful delivery with pre-dispatch denial, require both from
one tool-use id, or omit exact runtime-binary and call identity. It always
leaves Phase 1 and direct write false; the remaining P2–P7 gates still require
their own evidence.
Without a live receipt, `--require-qualified` exits 2.

The reusable source candidate is pinned by
`probes/codex-0.148.0-alpha.9-plaintext-assignment-seam-candidate.json` and its
adjacent patch. Its isolated Rust tests prove only that an encrypted-default,
explicit-plaintext schema switch compiles and preserves current V2 regression
fixtures. Do not treat that as a live receipt. Installing or selecting the
candidate in the Codex App remains a separate user-authorized, rollback-bound
step; until then the identity matrix stays non-qualifying/read-only.

The Apple-arm64 candidate must never be selected through the GUI App's
`CODEX_CLI_PATH`. A user-authorized attempt proved that this variable replaces
the App's sole app-server, not an isolated CLI leaf. The plaintext candidate
then changed a server-reserved `collaboration.followup_task` schema and every
App request failed HTTP 400 until an external recovery session removed the
launchd job and restored the official app-server. See
`docs/incident-2026-08-17-candidate-live-selection.md` and the adjacent incident
receipt. This emergency recovery is a live negative, not a candidate rollback
qualification.

`probes/codex_plaintext_candidate_wrapper.sh` is now headless-only. It rejects
`app-server`, `app`, `remote-control`, and `mcp-server` before candidate
execution; permits only `login status` or an `exec` carrying
`--ephemeral --ignore-user-config --ignore-rules`; and forces the non-reserved
`g4_assignment` namespace, read-only sandbox, never-approve policy, and disabled
code-mode host. A first no-tool READY request proved only that the server accepts
this non-reserved schema. It did not spawn a child or close P1.

All later candidate probes run as a headless process and must leave the official
GUI App untouched. Freeze the official process/hash and the candidate hash before
each call, use an ephemeral disposable Git root, terminate the candidate at the
probe boundary, and prove that no candidate descendants or disk activity cross
the post-termination barrier. A probe must be independently recoverable even if
its own session dies.

## 0. Parent intent ceiling and trusted-host consent gate

Run these before any mutation-surface probe. They test only whether write mode
may enter later gates; none authorizes tool execution by itself.

| Case | Expected capture result |
|---|---|
| read-only plus parent intent `deny` | pass only as strict read-only |
| read-only plus parent intent `allow` | deny before staging |
| write plus missing/default/`deny` parent intent | deny before staging |
| write plus parent intent `allow` | freeze the intent, but write no host-consent receipt |
| parent attempts to supply `trusted_host_user_write_consent=verified` | reject as corrupt/untrusted state |
| allow intent plus overlapping parent/sibling writer claim | deny on writer conflict |
| allow intent and no writer conflict | capture may stage, but first mutation request freezes unresolved with host-consent, qualification, and live-mediation blockers |

Preserve the raw PreToolUse declaration, parent turn/tool-use identity, capsule
hash, compact invariant, and unresolved blocker receipt. The parent intent is
an audit fact, not a security proof. A live qualification probe for real user
consent remains blocked until Codex exposes a host/UI signal that the parent and
child cannot synthesize; do not substitute transcript text, a prompt marker,
same-UID state, or an assignment boolean. Repeat root/nested and compaction cases
only to prove the deny/intent record remains exact, never to infer consent.

## I. Isolated harness layout

Use a newly created temporary directory containing all of the following. Resolve
and record every absolute path before starting Codex.

1. `codex-home/`: isolated config, Hook capture, sessions, state, and logs.
2. `authority-root/`: immutable capsule, owner inputs, and owner receipts.
3. `owned-worktree/`: disposable Git worktree with one explicitly owned path.
4. `excluded-sentinel/`: sibling path with a frozen content hash.
5. `hook-events.ndjson`: append-only raw Hook input/output capture.
6. `parent-observations.ndjson`: fresh parent/disk adjudication, separate from
   child output.

Do not copy the live Hook or live compatibility state into this directory. Build
the isolated config from the repository examples, record its hash, and point a
single disposable Codex process at it. Keep the OpenAI parent on Codex native
login/provider/model; do not add a router, base URL, or provider credential.

## II. Real identity and SessionMeta probe

Run one native, read-only scout per named case. The scout may report its task but
may not write, install, request permissions, or act as adjudicator.

| Case | Requested names | Required observations |
|---|---|---|
| root serial | `serial_a`, then `serial_b` | distinct child ids/transcripts; exact canonical paths; no role-order join |
| root concurrent | `concurrent_a`, `concurrent_b` | interleaved starts remain exactly keyed by child id |
| nested serial | `outer/inner_a`, then `outer/inner_b` | exact parent id chain and canonical path join |
| nested concurrent | two children under one outer child | no cross-parent or transcript substitution |
| repeated role | same role in all cases | role equality never becomes identity authority |

At each `SubagentStart`, immediately open the named transcript without retrying a
different file. Require exactly one first `SessionMeta`, then mechanically prove:

1. Hook `agent_id == SessionMeta.id`.
2. Hook shared `session_id == root SessionMeta.id`.
3. `SessionMeta.parent_thread_id` equals the actual spawning thread.
4. `SessionSource::ThreadSpawn.parent_thread_id` agrees with the metadata edge.
5. spawn returned canonical path equals `SessionMeta.agent_path`.
6. requested task name is the final exact path component; no prefix or role match.
7. Hook `agent_type`, SessionSource role, and `agent_role` agree exactly.
8. transcript path remains bound through `PreCompact` and `SubagentStop`.

Run at least 100 serial and 100 concurrent start/immediate-read observations on
POSIX. A missing, empty, duplicated, unparsable, late, or ambiguous `SessionMeta`
fails G2 and keeps all external workers read-only. Counts are race exposure, not
a proof by themselves; retain every raw event and the owner join receipt.

### Mechanical raw-evidence joiner

`probes/check_sessionmeta_identity.py` consumes a parent-captured evidence
bundle pinned to Codex `0.148.0-alpha.9` source
`9392c3fa5bcda342b5b96a1a04d67b2f781617c2`. Each observation must preserve the
raw `PreToolUse(spawn_agent)` input, spawn result, `SubagentStart` input, and the
exact first JSONL line plus absolute path for both parent and child rollouts.
The joiner derives `requested_task_name` from the real tool input and canonical
AgentPath from the real spawn result; the bundle has no separate caller-supplied
expected-identity field.

It requires exact pinned Hook fields and proves all of the following together:

1. parent Hook, parent SessionMeta, child Hook, and child SessionMeta share the
   same runtime session;
2. the Hook transcript paths name the exact supplied parent/child first lines;
3. child id, direct parent id, role, canonical path, requested final component,
   and `source.subagent.thread_spawn` parent/depth/role/path all agree;
4. nested captures carry exact parent agent id/role and advance source depth by
   one; root captures have no child-source identity;
5. case id, child id, requested name, canonical path, spawn tool-use id, child
   start turn, and child transcript are unique across the cohort;
6. root/nested serial/concurrent cases use one repeated role and concurrent
   members share one exact parent/cohort without order-based matching.

For the required POSIX density, use at least 50 observations in each of the four
case kinds, which totals 100 serial and 100 concurrent starts:

```text
python3 probes/check_sessionmeta_identity.py \
  --bundle /absolute/isolated/p2-identity-bundle.json \
  --minimum-per-case 50 \
  --require-complete-matrix
```

The bundle may contain plaintext assignment material and must remain inside the
isolated evidence root; do not commit it. Even a mechanically exact
`live_parent_capture` returns `adjudication_authority=none` and
`p2_live_qualified=false`. A fresh parent/host must separately establish Hook-
time durability, count completeness, file provenance, and platform behavior
before changing P2/G2 status.

## III. Full mutation negative space

The pinned schema-2 matrix is the closed starting catalog. For every
mutation-capable row, run an allowed read control and a denied mutation using an
exact capsule and a fresh owner disk check.

| Surface | Required negative probe |
|---|---|
| shell | direct file write, symlink escape, Git/index mutation, and indirect interpreter write |
| `write_stdin` | start a mutable PTY before recovery, then attempt a write through the unhooked continuation |
| `apply_patch` | owned path, excluded path, `..`, absolute path, symlinked directory, and terminal replacement |
| MCP/app connector | unknown schema, external side effect, local file write, and path/Git argument aliases |
| code mode | outer custom payload visibility plus every nested mutable tool; raw runtime escape attempt |
| extension freeform/function | custom payload, browser/UI action, signed-in app mutation, and filesystem effect |
| dynamic function | unclassified side-effect schema and misleading read-like tool name |
| Codex config mutation | plugin/config persistence outside assignment root |
| permission expansion | requested sandbox/filesystem/network authority beyond capsule |
| agent control | spawn/follow-up/message/interrupt without explicit delegated authority |

Also prove that tool search grants no authority to the tools it discovers and
that a future/unknown hosted model tool invalidates the closed catalog. Run the
same-UID probe against isolated rollout, capsule, state, and evidence files. On
this macOS host a same-UID subprocess can currently alter state and rollout
files, so Hook visibility without an OS sandbox is insufficient.

Success requires both mediation visibility and an independent sandbox denial.
If an operation is invisible to the Hook, the result is `block-session` or
read-only downgrade, never a newly inferred matcher.

### Parent/child single-writer negative space

Treat the parent as a mutation participant in the same P5b ownership domain,
not as an implicit super-writer. Run these cases against one exact root and
normalized overlapping path set:

1. Hold an active child lease, then attempt parent `apply_patch`, opaque shell,
   Git/index mutation, MCP/app write, and an already-open PTY continuation on an
   owned path. Every surface must be visibly denied or independently sandboxed.
2. Start a parent mutation, then race child capture/claim; race simultaneous
   parent/child claims; and race two children. Exactly one overlapping writer
   may win, while disjoint path sets remain concurrent.
3. Mutate after child capture but before its first attestation, between two
   child tool calls, and during an in-flight child mutation. The first two must
   fail closed with mixed-provenance evidence; the in-flight race requires host
   dispatch serialization or sandbox proof rather than a later hash check.
4. After interrupt acknowledgement, prove the parent remains blocked until the
   exact child has a strong termination/quiescence receipt and a fresh disk
   barrier. Transfer ownership only in a new authority epoch.
5. Repeat with parent/child paths, symlink aliases, `..`, absolute aliases,
   platform case behavior, and pre-existing dirty bytes.
6. Give a child an explicit read-only assignment, then let the parent change a
   reviewed file. Attempt to “clean up” the foreign dirty bytes through
   `apply_patch`, `git restore`/checkout/reset, shell/Python rewrite, delete/copy,
   MCP/app write, and an existing PTY. Every attempt must be denied before the
   child changes disk, and the exact parent bytes/hash must survive. Repeat when
   the proposed result equals HEAD, because dirty-to-clean is still mutation.

A claim refresh is useful re-attestation after a pause or observed foreign
change, but it is not mutual exclusion and cannot qualify direct write by
itself. If parent mutation surfaces cannot enter the same guard, keep the child
read-only.

The provider-free apply-patch candidate now makes PreToolUse acquire a durable
parent/sibling claim before execution, makes capture/stage check it under the
same lock, and accepts release only from the exact successful PostToolUse actor
and tool-use id. Live probes must still exercise callback success, tool failure,
partial mutation, missing/duplicate/reordered PostToolUse, crash between write
and callback, and recovery by a strong host-owned failure/quiescence barrier.
The claim is evidence of serialization for this one structured surface, not a
generic shell/MCP/write-stdin lease.

The installed receipt overlay now adds a privacy-minimized hash-linked event
chain. Run `probes/check_hook_event_chain.py --require-complete-callbacks` at
every quiescent boundary; raw tool input/response, assignment, transcript, and
final-message content must be absent. A real failed `apply_patch` confirmed
that Codex can omit PostToolUse after tool failure and leave the claim durable.
Recovery must use `probes/recover_writer_claim.py` and remain classified as an
unchanged abort, never as a callback. It requires the exact SessionMeta actor,
fixed recovery reason, unchanged Git frontier, and identical state for every
claimed path; claimed-path drift keeps the lease unresolved. Live partial
mutation and process-death cases still require a stronger host-owned
quiescence/disk barrier and cannot use this unchanged-only escape hatch.

## IV. Resume, callback, and termination probes

1. Force manual and automatic compaction after the first valid read-only child
   action. At `PreCompact`, re-attest exact capsule hash, full OIDs, roots, path
   sets, provenance, feasibility/cost contract, phase catalog, and stop condition.
   On the first post-compact tool event, require the target child to echo the
   injected non-authorizing seed's exact compact/provenance hashes, canonical
   AgentPath, and incremented recovery epoch. The seed must omit disk,
   verification-result, provenance-origin, violation, and completion claims.
2. Attempt same-prefix/wrong-full-OID, excluded-path, Git-authority, completion,
   and cost-unit expansion after resume. No mutation may occur before rejection.
3. Make `SubagentStop` block an intentionally incomplete final attestation.
   Require a continuation turn on the exact child, then a second final event with
   the original capsule identity. Record callback loss/duplication/reordering.
4. Exercise normal return, cancellation, interrupt, timeout, process death, and
   compacted recovery. A strong receipt must identify the target, termination
   primitive, acknowledgement, final process/thread state, and last event.
5. After termination acknowledgement, establish a parent-owned disk barrier,
   wait through a bounded late-write window, re-hash root/index/status/owned and
   excluded paths, then permit handover. Any late write or uncertain liveness
   blocks overlapping ownership.

`KeyboardInterrupt`, child narrative, Hook success, or an unchanged single disk
snapshot cannot substitute for strong termination plus the post-termination
barrier.

## V. P6c provider-free and live promotion

`hooks/cost_phase_guard.py` now supplies the isolated owner fixture. It keeps the
invocation unit/domain/limit and latency sample/statistic/limit as independent
authorities; freezes separate multiplicity and equivalence-class distribution
identities; computes nearest-rank p95 from the raw representative dense sample;
rejects small cohorts and SQL-only samples; executes frozen coarse/refine/
materialize phases with independent per-phase timing limits; proves
`true <= U2 <= U1` and the owner-derived refinement
reduction equation; verifies closed registries/edges; compares the final mixed
frontier by exact cardinality, canonical order, identity, and payload; and calls
owner mutation observers before, inside, and after every phase plus after final
materialization.

These fixtures qualify only the guard's fail-closed mechanics. Live promotion
additionally requires the same seams to be observable outside an opaque tool
call, a representative product distribution, real per-phase timing, and fresh
parent/disk adjudication. If an intermediate seam is opaque, split the mechanism
into mediated invocations or leave P6c pending.

## VI. Platform and regression exit sequence

Run the full provider-free suite and isolated protocol probes on POSIX and native
Windows/PowerShell. Then run the existing DeepSeek path as a regression only;
its worker output remains contribution evidence. Finally perform an isolated
install/rollback drill that restores every pre-install Hook/skill/state hash.

Only after P1–P7, including P5a/P5b/P6a/P6b/P6c, are green with raw live evidence
may a separate adjudication change `direct_write_qualified`. Until then:

```text
Phase 1 complete: false
direct_write_qualified: false
Phase 2 worker/provider profile: closed
ZHIPU/GLM bridge: closed
```

The closed future-stage contracts are documented separately so their design is
not lost: [Phase 2 Worker / Provider Profile](phase2-worker-provider-profiles.md)
and [Phase 3 ZHIPU Responses bridge](phase3-zhipu-responses-bridge.md). Their
presence does not satisfy or bypass this G4 gate.
