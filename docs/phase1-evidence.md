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
requires the Hook session/agent id to match the payload's shared session and
child id, then requires the flattened parent/role/path identity to match the
exact duplicates in `source.subagent.thread_spawn`.
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

The provider-free candidate now also injects a deterministic final-attestation
seed at `SubagentStart` and every successful child `PreToolUse`. It supplies only
mechanical identity/hash/epoch/verification-command inputs that a strict
read-only child cannot calculate with shell access disabled. Focused fixtures
prove the seed excludes provenance origin, test-only status, verification
results, disk state, authority-violation status, and completion. The installed
0.148.0-alpha.9 binary embeds a `PreToolUse` output schema with
`hookSpecificOutput.additionalContext`, consistent with the pinned source.
Neither fact proves that a real compacted child sees the re-injected seed; that
remains a live target-child probe and no qualification status changes here.
The fresh provider-free suite passed 230 tests in 33.519 seconds, including the
new seed contract and initial/post-recovery injection fixtures.
The subsequent native-probe prompt generator adds two fail-closed fixtures for
exact clean Git binding and dirty/invalid-task rejection; the fresh aggregate
suite is therefore 232 tests.

The probe corrected an earlier identity assumption: Hook `session_id` is the
runtime session shared by root and descendants, not the child ThreadId. Current
serialized SessionMeta does duplicate this shared session id. Exact binding
therefore keeps `runtime_session_id`, direct `parent_thread_id`, and child
`agent_id == SessionMeta.id` as separate fields while cross-checking the
thread-spawn source duplicates.

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

### Event-specific Hook failure semantics

The migration-time live configuration is narrower than the candidate: the
installed `/Users/pearly/.codex/hooks.json` SHA-256 is
`e20d6b3c3e70c088ca9e56afd25a3ee52660d16bbfb0d95b427adaa2cd7ba659` and its
only configured event is the trusted v4 `SubagentStart` plaintext handoff. The
user confirmed that the earlier `PreToolUse` configuration was not migrated in
equivalent form. This is an installed-state gap, not a negative runtime result;
no G4 mutation-mediation callback can be inferred from the v4 Hook's trust
entry.

The current official Codex Hooks contract says `PreToolUse` blocks with an
explicit deny JSON shape or exit 2; unsupported generic stop fields instead
make that Hook run fail and allow the tool call to continue. It also says
`SubagentStart` cannot be stopped by `continue=false`, `PreCompact` stops before
compaction with `continue=false`, `SubagentStop` uses `decision=block` to
continue an incomplete child, and `PostToolUse` cannot undo effects that have
already occurred.

The isolated executable previously converted any uncaught `StateError` into
exit 12. It now emits the exact event-level safe shape: deny for `PreToolUse`,
stop-before-compact for `PreCompact`, continuation for `SubagentStop`, explicit
`TASK.CONTEXT_LOST` for the non-blockable `SubagentStart`, and stop-flow while
retaining an unresolved lease for failed `PostToolUse` reconciliation. Invalid
JSON uses exit 2. Six new focused tests exercise these shapes with real CLI
dispatch for all four lifecycle events and direct event-shape checks; the
existing failed writer-release fixture now also requires stop-flow output.

At that checkpoint these tests improved the uninstalled candidate only. They do
not by themselves prove that a live Hook ran, that independent sandboxing
blocked a mutation, that the host cancelled a context-lost child, or that a
`PostToolUse` stop established disk quiescence. P1/P4/P5a/P5b and their exit
receipts remain incomplete.

## Qualification-only live install (2026-08-17)

After explicit user authorization, the source from
`8d23bc1ff18f8032541bfb28e7c78ec4332fe501` was installed beside—rather than
overwriting—the existing v4 handoff. The new role is
`g4_qualification_probe_worker`, omits `model` and `model_provider` so it keeps
the native parent OpenAI route, and fixes `sandbox_mode="read-only"`. The Hook
overlay covers all `PreToolUse`, successful `apply_patch` `PostToolUse`, the
probe role's `SubagentStart`/`SubagentStop`, and all `PreCompact` triggers. The
dispatcher remains fail closed and targets schema-v2 authority only for this
dedicated role; the unchanged v4 matcher stays first in `SubagentStart`.

The pre-install files were copied to the mode-0700 directory
`/Users/pearly/Downloads/codex-g4-live-backup-20260817T002114+0800` before any
replacement. Backup `hooks.json` SHA-256 is
`e20d6b3c3e70c088ca9e56afd25a3ee52660d16bbfb0d95b427adaa2cd7ba659`;
backup `config.toml` SHA-256 is
`15ba59a6e7c4378801ac708636df3e33a15f51e81b613e6b8ee4f7f26068f32a`.
The first state-directory creation exposed that `~/.codex/state` did not yet
exist; the installer then created the exact parent and candidate directories at
mode 0700. This recovered partial-install step is recorded rather than hidden.

Installed hashes are:

- merged `hooks.json`:
  `8c7356e340db49abd86f41f49c09a8b59c5db1b7125e69f8808ab3a9b7720ff7`;
- native read-only probe agent:
  `f67c7c4eb3aaec875704ad1d5754650f1ac8cbecaf163988535c8bcb51d706d9`;
- `compatibility_hook.py`:
  `6cab5b674a7b60609c33d0d2908b028c7e81831d8de68fe2d8d5a2daea3a36e8`;
- `assignment_transport.py`:
  `02fd2c29f261c8417acbc3951668dc89a6e0c9be40b12d172bb7511c7c19ec25`;
- `compatibility_state.py`:
  `02f684ec771710e2a4b0f86ea73537eefff08bea9e9defeb8bdc1bbceff10215`;
- `runtime_guard.py`:
  `479c1081553fc68cbe983fe69c04cf031eb786f7b33b16832a68e1a923fb913f`;
- `writer_lease_guard.py`:
  `7c0fba8fbfc5560b22562562d492102ee5e7a1eeb61d343494c6e190a002551c`.

A host-level manual invocation used the installed command and real root
SessionMeta, acquired/released one synthetic apply-patch lease, executed no
patch, and produced installed-state writer receipt SHA-256
`40777fffcff5c49257e84d482da70b4316359df9c82ef3617690465dcf6ac400`.
Running the same command inside the model shell sandbox was denied before state
write, which confirms event-level fail-closed behavior but does not prove how a
trusted Hook host process is sandboxed.

The user subsequently reviewed and approved all five G4 command definitions in
the Hook UI. No trust hash was forged or copied. A real parent `PreToolUse`
dispatch then failed closed before mutation because the task cwd was the
workspace parent, not a Git root. That is real negative loader/mediation
evidence, not successful mutation qualification. `codex --strict-config doctor
--json` had previously reported `config.load=ok`; its separate
provider-reachability and state-database diagnostics were not changed or treated
as G4 evidence. Phase 1 and `direct_write_qualified` remain false.

A subsequent real file-level rollback moved the new agent, Hook directory, and
state into the backup, restored the old `hooks.json` hash exactly, verified all
three candidate paths absent, and rechecked the unchanged v4 agent/script hashes
`051f0e767415a86fd09b4e125868d3a4e4cf41ba3d2fd81e9018edee62e9ed69` and
`16353e6eb4484412bd7560a10eeae4dcf1533709910a373a4e98d414dc725a49`.
The first move attempt collided because Hook and state directories share the
same basename; state was then preserved under an explicit `state-...` backup
name. No data was deleted. The installed-state receipt retained its exact hash.
Reinstall restored every candidate hash above and the merged Hook hash exactly.

This promotes the install/rollback receipt only from pending to **partial**. It
proves artifact-level recovery and diagnostic preservation, not behavior of an
already trusted/loaded Hook process across reload. That functional rollback,
plus Windows and DeepSeek regression, remains open.

### Trusted-Hook warning and root-resolution repair

The Hook browser reported that `additionalContextLimit` is invalid for
`PreCompact` and `SubagentStop`, because neither event can emit additional
context. The two unsupported fields were removed; the lifecycle hooks remain
because current Codex supports blocking JSON output for both events and G4
requires pre-compaction re-attestation plus final stop adjudication.

The first trusted parent `apply_patch` also exposed an over-broad cwd
assumption. Its exact cwd was `/Users/pearly/文档/CAT`, while all patch
targets were inside the nested `codex-deepseek-subagent` repository. The old
guard ran `git rev-parse --show-toplevel` against the cwd and denied before any
disk mutation or writer claim. Removing the mutation entry from `hooks.json`
did not change the already loaded definition in this task; a second call was
denied identically. This is partial negative reload evidence, not proof of
hot-reload behavior across processes.

The mutation pair was disabled together, preserved in timestamped backups, and
reinstalled only after the guard learned to derive one Git root from the
resolved patch targets. All targets must still normalize beneath that same
root; a cross-root target fails closed. The repaired provider-free suite passed
218 tests. Current live hashes are merged `hooks.json`
`ffaad5c3533a2016253af148c96721818807823f779845a35c5d7dad2c676c2b` and
`writer_lease_guard.py`
`2c6c9aa7cfda1eda7bdbb99f7cf27f7fce16c0c35f31504849b082a27bfce028`.
The v4 script/agent hashes remain exactly
`16353e6eb4484412bd7560a10eeae4dcf1533709910a373a4e98d414dc725a49`
and `051f0e767415a86fd09b4e125868d3a4e4cf41ba3d2fd81e9018edee62e9ed69`.
Because the two lifecycle definitions changed after approval, `PreCompact` and
`SubagentStop` require fresh UI review; no stale trust value is treated as
authority.

The first repaired live `apply_patch` then bound root actor/session/AgentPath
`01a00147-39cb-7b50-b78d-7baed910eb45`/`/root` to the exact nested repository
and five requested paths. `PreToolUse` published claim
`0828d752-de07-4976-9cf8-e551ac2b881f`; the successful `PostToolUse` removed the
claim and published receipt SHA-256
`e93f74ee3b64ee10e59b0d82210e6526dcf382497308cf2777bc1b42c419bd5c`.
This promotes mutation visibility and callback continuity from pending-only to
**partial** positive live evidence. It does not cover shell/MCP/GUI mutation
negative space, child sandbox denial, callback loss, compaction, stop,
termination/quiescence, or cross-platform behavior.

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

## Superseded provider-free rollout-bound child-write ceiling

This subsection records the exact `d2e79f5` experiment and its 180-test result.
It is historical evidence, not the current schema: the next subsection removes
the rollout marker/turn/prompt-hash mechanism after review found that it added a
private user syntax and flush/schema coupling without creating a trusted host
boundary.

At that checkpoint, the authority declaration and immutable capsule separated
five gates that were previously easy to conflate:

| Gate | Provider-free candidate | Remaining qualification gap |
|---|---|---|
| user permission ceiling | a `write` declaration requires `user_child_write_authorized=true`; capture independently finds exactly one current-turn user rollout message ending in the closed authorization block and freezes its turn/content hash | live transcript freshness, same-UID trust, and UI/CLI usability |
| assignment mutation mode | exact `read_only|write`; read-only cannot carry an authorization receipt and write cannot use the strict-review posture | live dispatch and sandbox binding |
| exact ownership | owned/excluded paths remain independently validated and conflict-checked | child-side atomic mediation for every mutation surface |
| writer serialization | parent/sibling structured `apply_patch` claims still block overlapping capture even when user authorization exists | shell, PTY, MCP, code-mode, extension, Git/config, and control surfaces |
| qualification/lifecycle | an authorized write capsule's mutation request is frozen before execution as `direct_write_qualification_missing` | real identity, sandbox, callback, strong termination/quiescence, disk barrier, POSIX/Windows/DeepSeek/live rollback |

The exact user marker is intentionally turn-scoped and terminates the user
message. A parent-authored authority boolean is insufficient: missing marker,
wrong turn, duplicate marker/message, malformed closed fields, or a read-only
mode/authorization contradiction denies spawn. The compact invariant includes
the mutation mode and receipt so compaction cannot erase or expand this ceiling.

Pinned source confirms that current-turn user input is persisted as a
turn-stamped response item before tools and that rollout encodes it as a
`response_item`; this is only a schema/source anchor. It does not prove that a
live Hook sees a fresh, unforgeable record on every supported host. The prior
same-UID result remains negative, so this layer cannot alter the direct-write
decision.

Provider-free negative fixtures cover missing, wrong-turn, duplicate, and
parent-only declarations; read-only non-expansion; compact receipt binding;
authorized capture versus an overlapping parent writer claim; and authorized
runtime mutation versus `direct_write_qualified=false`. The fresh complete
result is:

```text
Ran 180 tests in 25.647s
OK
agent template checks passed
```

The re-pinned mutation matrix reported `valid=true`, zero anchor failures, and
the same ten blocker classes; `direct_write_qualified=false`. The same-UID
probe again reported both rollout and state unprotected and therefore also
returned `direct_write_qualified=false`. These negative qualification results
are the expected evidence, not test failures.

No live candidate was installed and no LocalCAT product file was modified.
`Phase 1 complete=false` and `direct_write_qualified=false` remain unchanged.

## Simplified parent intent and independent trusted-host gate

The current isolated schema replaces the rollout-bound experiment with two
small, explicitly different facts:

- `parent_recorded_user_write_intent=deny|allow` is an auditable statement made
  by the parent from the current instruction. It defaults/fails closed: a write
  assignment with missing or `deny` intent cannot stage. It is not described as
  host-attested user consent and grants no mutation authority.
- `trusted_host_user_write_consent` is written by the Hook, not accepted from
  the assignment. Schema 2 currently permits only
  `status=unavailable, source=null, receipt_sha256=null`; a parent-fabricated
  `verified` receipt is corrupt state. A future verified form requires a new
  schema revision plus a real Codex host/UI consent signal.

The compact invariant freezes both facts. A write capsule with parent intent
`allow` may reach later read-only contribution/lifecycle checks, but its first
mutation request is denied before execution and moved to unresolved as
`write_authority_gates_missing`. The receipt mechanically lists all three
current blockers: `trusted_host_user_write_consent`,
`direct_write_qualification`, and `live_mutation_mediation`. Exact paths,
parent/sibling writer claims, Git authority, sandbox, identity, callback,
termination/quiescence, and the disk barrier remain separate gates.

Provider-free tests prove missing/deny intent blocks write staging, allow intent
does not fabricate host consent, forged host consent fails closed, read-only
cannot carry allow intent, compact recovery preserves both facts, overlapping
writer claims remain effective, and runtime mutation records all three blockers.
The fresh complete result is:

```text
Ran 179 tests in 27.882s
OK
agent template checks passed
```

The post-simplification mutation matrix again reported `valid=true`, zero
anchor failures, the same ten blocker classes, and
`direct_write_qualified=false`. The same-UID probe again reported rollout and
state unprotected and therefore also returned `direct_write_qualified=false`.

This simplification removes rollout parsing from the Hook path and deletes the
obsolete marker-specific negative space while preserving every downstream deny. It
does not alter P4/P5b completion, install state, or the direct-write decision.

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

## Phase roadmap recovery and executable G4 stage gate

On 2026-08-16, a complete `git log --all`/tree audit found that independent
Phase 2 and Phase 3 documents had never been committed to this repository. The
detailed design remained in the original three-stage task record. A separate
read-only scan from the initial design through the end of the migrated rollout,
plus the LocalCAT Feature 5 thread, applied latest-decision-wins and found no
stage reorder: Phase 2 defines the generic Worker / Provider Profile and its
opaque credential-source slot; Phase 3 qualifies `zhipu_plan_worker` using
`responses-direct` when available or an optional loopback Responses bridge when
needed. A pre-existing `ZHIPU_API_KEY` environment variable is host preparation,
not a Phase 2 deliverable or authorization. It never enters the handoff; a later
approved live probe may record presence only, never its value.

The recovered Chinese/English contracts now live in
`docs/phase2-worker-provider-profiles*.md` and
`docs/phase3-zhipu-responses-bridge*.md`. Both explicitly remain closed. The
current Codex configuration reference also establishes `responses` as the only
supported custom-provider `wire_api` value, so `docs/advanced*.md` no longer
describes Chat Completions as a parallel direct Codex wire. A Chat-Completions-
only external provider instead requires the separately qualified, child-local
Phase 3 bridge.

`probes/phase1-g4-status.json` names every required P1–P7 subgate and the live
exit receipts for exact SessionMeta identity, mutation visibility, independent
sandbox denial, callback continuity, termination/quiescence, POSIX/Windows,
DeepSeek regression, and install rollback. `probes/check_phase1_g4.py` derives
completion instead of trusting a boolean. Missing P6c, a premature Phase 2 open,
or a manually asserted completion/direct-write boolean is invalid. The fresh
result was:

```text
valid=true
phase1_complete=false
direct_write_qualified=false
phase2=closed
phase3=closed
12 unresolved P-gates
9 unresolved exit receipts
--require-phase1-complete exit=2
```

The complete fresh provider-free suite based on
`392b21044f6d225b16961ae15e8cfd3a14079946` plus this worktree ran:

```text
Ran 184 tests in 28.771s
OK
agent template checks passed
```

The pinned Codex `0.148.0-alpha.9` mutation matrix revalidated all source
anchors at `9392c3fa5bcda342b5b96a1a04d67b2f781617c2`, retained ten blocker
classes, and returned `direct_write_qualified=false`; its require-qualified
mode exited 2. The same-UID probe again showed both rollout and state
unprotected, returned `direct_write_qualified=false`, and its require-protected
mode exited 2. No live Hook, skill, provider profile, bridge, credential, or
LocalCAT product file was changed. These are fresh negative qualification
results, not a Phase 1 completion claim.

## P2 raw SessionMeta identity joiner

Status: **provider-free join mechanics implemented; live identity qualification
pending.** The prior runtime fixture compared only the top-level shared session,
thread id, parent, role, and path. Current real `0.148.0-alpha.9` JSONL also
duplicates direct parent, depth, role, nickname, and canonical path under
`source.subagent.thread_spawn`; both representations must agree.

`probes/check_sessionmeta_identity.py` now accepts raw parent
`PreToolUse(spawn_agent)`, spawn result, child `SubagentStart`, and exact first
parent/child JSONL lines. It derives the requested name from `tool_input` and
canonical path from the spawn result, then cross-checks Hook identity and the
flattened SessionMeta fields with the exact
`source.subagent.thread_spawn` direct-parent/depth/role/path/nickname identity.
Nested observations must prove their parent source and depth increment; root
observations must not carry child identity. The joiner also treats payload
creation time and the outer JSONL record time as distinct: payload time must be
no later than record time, not exactly equal.

The cohort guard rejects duplicate case ids, child ids, requested names,
canonical paths, spawn tool-use ids, child start turns, or child transcript
paths; it also prevents a root/nested serial/concurrent matrix from mixing
roles, parents, or concurrent cohort ids. Eighteen focused tests cover the full
eight-observation provider-free matrix and wrong child, wrong source parent,
non-UUID identity, prefix-only task match, spawn/path or nickname mismatch,
wrong depth or Codex version, nonzero first ordinal, duplicate child/tool
identity, duplicate SessionMeta lines, mixed roles, and incomplete matrix.

The joiner deliberately returns:

```text
adjudication_authority=none
p2_live_qualified=false
```

even for an input labelled `live_parent_capture`. The label and internally
consistent hashes cannot prove Hook-time durability, parent ownership of the
capture, 100 serial/100 concurrent POSIX coverage, Windows parity, or absence of
a same-UID rewrite. Raw live capture plus fresh host/disk adjudication remains
required before G2 can pass.

### Partial native concurrent observation (2026-08-16)

The parent launched two bounded native read-only explorers concurrently and
then read their first rollout records from disk. Both children used root session
`01a00147-39cb-7b50-b78d-7baed910eb45`, depth 1, role `explorer`, and distinct
canonical paths/ThreadIds:

- `/root/g4_identity_concurrent_a`, nickname `Gauss`, child
  `01a00b44-79c4-7933-913d-7062e01dd948`; payload time
  `2026-08-16T15:50:32.133Z`, record time `2026-08-16T15:50:32.203Z`, first-line
  SHA-256 `e1ba063907895e9ea05037e09d7694f52c9348b4b5e00df104cd98591f6c082c`.
- `/root/g4_identity_concurrent_b`, nickname `Beauvoir`, child
  `01a00b44-9444-7aa2-af7d-466e48c9e7e3`; payload time
  `2026-08-16T15:50:38.917Z`, record time `2026-08-16T15:50:38.982Z`, first-line
  SHA-256 `d7cdcffd8fa2e624992b80a3e7fce30b2b58599c0969fc2ed7e4e9e67176b008`.

The root first-line SHA-256 was
`8dc09a540a2599307eb57247c117ecbef242a0a19c5dde6b46380a4be29ad569`.
No raw `PreToolUse(spawn_agent)` or `SubagentStart` Hook input exists for this
cohort because the migrated live config contained only the v4-specific
`SubagentStart` matcher. The observations therefore prove real on-disk source
shape and distinct concurrent child identities, but not the required Hook ↔
spawn result ↔ SessionMeta join. They do not promote P2 or the
`sessionmeta_identity` exit receipt.

After adapting the runtime parser, an isolated CLI round trip used the real root
SessionMeta and a synthetic `apply_patch` event against temporary state. It
acquired and exactly released one root writer claim without executing the
patch; receipt SHA-256 was
`105392522a71df98753ece56c93c895985f9517af8e872b710504af206ab5253`.
This validates parser/lease mechanics only. It is not evidence that a trusted
live `PreToolUse` ran.

The 2026-08-16 baseline refresh also exposed a migration configuration drift:
the valid GitHub identity is selected by SSH Host `github.com-new`, while the
repository remotes use `github.com`. Default fetch therefore failed public-key
authentication. A one-shot `core.sshCommand` using the existing
`id_ed25519_github2` identity authenticated as the expected GitHub account and
successfully refreshed both remotes without editing SSH config or remote URLs.
The refreshed full refs remained
`origin/main@076ee0df9aca11fbc0c19a6ccd7cd8befc0051f7` and
`upstream/main@c949e8d9b8922a48990b1e08259ad4baefc75f55`.

The fresh host baseline was Codex CLI `0.148.0-alpha.9`, Python `3.14.7`, and
macOS `26.2` on arm64. After the identity joiner, real timestamp/source-duplicate
parser correction, and event-failure fixtures, the complete suite ran on
2026-08-17:

```text
Ran 215 tests in 29.734s
OK
agent template checks passed
```

The executable G4 gate still reported all twelve P-gates and nine exit receipts
unresolved, with `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 closed. The pinned mutation anchors remained valid with the same ten
blockers. The same-UID probe again altered both isolated rollout and state.
Therefore the corrected parser and partial native observation improve the
evidence path but change no live qualification decision.

## Privacy-minimized live Hook receipt overlay and callback-loss recovery

Status: **root writer visibility improved; live child lifecycle and G4 exit
qualification still pending.** With explicit user authorization, the G4
overlay now records a single atomic, hash-linked event chain for qualified
`PreToolUse`, `PostToolUse`, `SubagentStart`, `PreCompact`, and `SubagentStop`
observations. Each receipt binds the SessionMeta-derived runtime session,
thread, agent type, canonical AgentPath, event/stage, and applicable tool-use
identity. It deliberately stores neither raw tool input/response nor assignment,
transcript, or final-assistant content. Missing, duplicate, reordered, corrupt,
or unwritable receipts fail closed. `probes/check_hook_event_chain.py` rejects
an authorized writer event without its exact observed callback.

The installed `SubagentStart` order remains the original
`^v4_flash_worker$` plaintext Hook first and the G4 qualification-only worker
second. The v4 plaintext script hash remains
`16353e6eb4484412bd7560a10eeae4dcf1533709910a373a4e98d414dc725a49`;
the live agent differs from the migration bundle only by the already-authorized
Fedora-to-macOS `writable_roots` repair. The unsupported
`additionalContextLimit` fields were removed from `PreCompact` and
`SubagentStop`; those lifecycle events themselves remain required. No trust
hash was copied or fabricated, and a fresh-process trust reapproval receipt is
still pending.

The first live chain prefix contained eight exact root writer
PreToolUse/PostToolUse pairs, sequences 1–16, with no pending callback and no
raw payload. A separate real negative occurred before receipt installation:
an `apply_patch` whose context did not match acquired claim
`f3ac4aee-f571-451d-884d-4e7643eee014`, returned tool failure, emitted no
observable `PostToolUse`, and left the claim durable. A later overlapping patch
was denied. This confirms that success-only callback semantics cannot be
treated as a universal lease release.

`probes/recover_writer_claim.py` therefore provides an explicit abort path,
not a synthetic callback. It requires exact SessionMeta actor identity, the
fixed `missing_posttooluse_after_tool_failure` reason, an unchanged Git
frontier, and identical before/after identities for every claimed path.
Unrelated dirty paths may progress, but any claimed-path or frontier drift
keeps the claim unresolved. The real orphan was recovered as
`aborted_unchanged_after_missing_callback`; its before/after path digest was
`c943315fdbe2f54374f4d50f848289561df301a6cf28a18e2227b31a54763c00`
and abort digest was
`f214e2b0bb842a3443cd71cd2d5d375540f3d518e65e8be5bafa1a2b597bcbf0`.
The same missing-callback shape then reproduced on a second context-mismatch
failure. Its independent abort was joined by exact actor/tool-use identity and
reported as `aborted_unchanged` with `post_sequence=null`; the earlier
pre-overlay abort remained explicitly unmatched rather than being backfilled
as a Hook callback. The quiescent verifier then returned no pending callbacks.

The final-attestation-seed update reproduced this failure-only path twice more
on mismatched documentation patch contexts. Exact unchanged recovery produced
abort hashes `246ae696267345e0ad9252440c0bced973c4e9a63f05e6e27388b296f8e738cc`
and `ac1166079ebb67e41e7b46b5ff686328c7a5b66579ccce1a5f24341e78fb228f`;
the joined chain prefix reached sequence 74 with zero pending callbacks. These
are explicit aborts, not fabricated `PostToolUse` events, and do not close
partial-mutation or process-death recovery.

Provider-free tests now cover the complete root→child lifecycle receipt order,
exact root/child AgentPaths, payload omission, pending callback, orphan and
duplicate PostToolUse, tamper, receipt-write failure, wrong recovery identity,
claimed-path mutation, and unchanged abort with disjoint worktree drift. The
fresh suite result was:

```text
Ran 229 tests in 37.073s
OK
agent template checks passed
```

The raw non-credential record is
`probes/g4-live-callback-receipts-20260817.json`. These results do not prove a
real target-child lifecycle chain, sandbox confinement, same-UID state trust,
strong termination/quiescence, platform/DeepSeek regression, or rollback after
this overlay. `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.

## First fresh native G4 root child (2026-08-17)

A clean-worktree prompt generated at full HEAD
`9ba75e00b20a1e188c4e4dccca190ae98617c6da` started a fresh persisted
`codex exec` parent with the current OpenAI login/provider, read-only sandbox,
and no Hook-trust bypass. The custom role loaded and native spawn returned
`/root/g4_cli_root_identity_1`. Real SessionMeta exactly bound parent thread
`01a00bbb-851a-7fa1-9a3f-e92e7d389106`, child thread
`01a00bbb-f879-7232-a421-c4696a467e15`, shared runtime session, direct parent,
role, nickname, and canonical AgentPath.

The negative result is equally important: parent capture created no pending
capsule, so `SubagentStart` wrote one lost record with reason `expected one
pending authority capsule, found 0`. The child made zero function calls and
first returned `TASK.CONTEXT_LOST`, but the stop gate accepted only the exact
bare marker and requested continuation 38 times. The host interrupted the
read-only process with exit 130. No strong quiescence receipt or disk barrier
was captured before later parent edits, so this is not termination
qualification.

The parent rollout names `spawn_agent`, while current Codex documentation also
exposes the Hook alias `Agent`; the raw Hook input tool name was not retained.
An alias mismatch is therefore a repair hypothesis, not a claimed observation.
The adapter candidate now accepts both exact names and tells a context-lost
child to return only the bare marker. Provider-free coverage precedes any
reinstall/retry. Raw non-credential hashes and the fail-closed verdict are in
`probes/g4-live-root-identity-20260817.json`.

A second clean, fresh native parent retried after installing exact `Agent` and
`spawn_agent` alias acceptance. Native spawn, exact SessionMeta identity,
wait/callback, and task completion all succeeded for
`/root/g4_cli_root_identity_2`; the child made zero function calls and returned
the exact bare `TASK.CONTEXT_LOST` once. One SubagentStart receipt and one
SubagentStop receipt were joined at sequences 131–132, and the parent process
exited 0. This closes the repeated stop-continuation defect from the first
probe, but not assignment capture: there was still no pending capsule or
target-spawn receipt, and SubagentStart again recorded `expected one pending
authority capsule, found 0`. The alias hypothesis is therefore disproved as a
sufficient repair. No strong quiescence receipt or post-termination disk
barrier exists, so termination remains unqualified.

The next probe adds an explicitly scoped, value-free PreToolUse schema
observer. It records only exact SessionMeta actor identity, cwd, tool name,
tool-use id, and sorted top-level input field names/types. Assignment values,
tool responses, transcript paths, nested values, and credentials are omitted;
receipt hashes make tampering visible. Observation is disabled by default and
must be enabled for one exact root with
`--pretool-schema-observation-root`. Any enabled observation whose actor cannot
be joined to pinned SessionMeta fails closed. Provider-free fixtures prove
scope equality, omission, tamper rejection, and fail-closed identity before a
live retry. The fresh provider-free suite ran 239 tests in 36.069 seconds with
all tests green; the agent-template checks included in that suite also passed.

## Live native Hook schema and assignment-seam blocker (2026-08-17)

Status: **agent-control visibility and exact child identity observed; P1 remains
blocked because neither event exposes the plaintext assignment.** A fresh
read-only parent positive control proved that the trusted PreToolUse Hook was
active for the exact root. Current native tool names were `Bash`,
`collaborationspawn_agent`, and `collaborationwait_agent`; spawn input shape was
`agent_type:string`, `fork_turns:string`, `message:string`, and
`task_name:string`. This replaces the earlier unverified `spawn_agent`/`Agent`
alias hypothesis with a value-free live observation.

The follow-up fingerprint probe stored no message bytes. The Hook-observed
spawn `message` and the rollout function-call value were both 4600 bytes with
SHA-256 `4c68211f0c9834cb5ef88daf3c3633808e5b1085db78acd63e5d91616ec1f1f1`
and zero authority begin/end markers. The exact assignment embedded in the
generator prompt was 3223 bytes with SHA-256
`00f047600048c0140d106f1683ba535aa02d34c3f1f4becf80b286e4720aa8e7`
and one marker pair. The wire value is therefore classified only as an opaque
token-like payload; no cryptographic format is inferred. With the strict
matcher restored, capsule staging blocks before spawn because the opaque value
does not contain the exact authority envelope.

The exact 0.148.0-alpha.9 source commit now makes the host-side boundary
replayable. Multi-Agent V2 constructs the `spawn_agent.message` schema with
`.with_encrypted()` and has a regression fixture requiring that marker.
`ToolRegistry` derives Hook `tool_input` directly from the raw
function-call `arguments` and runs PreToolUse before the tool handler. The V2
spawn handler then reads `message`; unless the response explicitly marks the
collaboration call with an empty `encrypted_function_args` array, it constructs
`InterAgentCommunication::new_encrypted` and sends the same value to the child
as `encrypted_content`. There is no host-side plaintext recovery between the
Hook and child submission. The built-in integration fixture separately covers
the explicit empty-array plaintext branch, but current configuration exposes
no host control that selects it. `hide_spawn_agent_metadata` only changes the
spawn result and is unrelated to assignment transport.

The official upstream main branch still has the encrypted schema and no
observed plaintext configuration switch as of this audit. OpenAI Codex issue
[#33284](https://github.com/openai/codex/issues/33284) tracks the same missing
content-aware pre-execution boundary, and
[#36376](https://github.com/openai/codex/issues/36376) records that the
empty-array plaintext branch does not help when an OpenAI parent actually
returns `encrypted_function_args:null`. Neither issue is treated as a runtime
fix or local qualification.

`probes/check_native_assignment_seam.py` pins these anchors and their causal
ordering to source commit
`9392c3fa5bcda342b5b96a1a04d67b2f781617c2`. Fresh replay returned `valid=true`
with zero anchor failures; `--require-plaintext-seam` returned exit 2. This
narrows P1 to an upstream/runtime seam requirement rather than a Hook trust or
filesystem-permission problem. A runtime-controlled plaintext assignment seam
or separate trusted host staging API must still prove byte equality to the
child-delivered assignment before P1 can qualify.
The post-change provider-free suite ran 254 tests in 32.032 seconds and passed,
including agent-template checks. The current task's five successful file edits
all have paired PreToolUse/PostToolUse events; the global require-complete audit
still exits 2 only for the previously recorded pending callback owned by the
foreign runtime session, which this task does not recover.

The machine-checkable prerequisite is now frozen in
`probes/native-plaintext-assignment-seam-contract.json` and
`probes/check_plaintext_assignment_candidate.py`. It covers native V2
`spawn_agent`, `send_message`, and `followup_task`, requires opt-in plaintext
schema selection, exact PreToolUse→handler→recipient byte equality, a
pre-dispatch deny control, native AgentPath/control preservation, encrypted-mode
regression, and redacted evidence. The opt-in is assignment transport only and
cannot grant mutation authority. No live receipt exists, so the checker is
valid but `--require-qualified` exits 2. The complete provider-free suite now
runs 259 tests and passed in 37.376 seconds, including agent-template checks.

An isolated Codex source candidate now makes that prerequisite executable
without replacing the pinned audit tree or installing a live binary. Against
source commit `9392c3fa5bcda342b5b96a1a04d67b2f781617c2`, it adds
`features.multi_agent_v2.message_delivery = "plaintext"` while preserving
`encrypted` as the default. The setting affects only the `message` schema for
native V2 `spawn_agent`, `send_message`, and `followup_task`; it reuses the
existing `DirectPlaintextMessage` branch and does not change the parent
provider/auth path, AgentPath/control handlers, or V1.

The exact 12-file patch and machine-readable build receipt are frozen in
`probes/codex-0.148.0-alpha.9-plaintext-assignment-seam-candidate.patch` and
`probes/codex-0.148.0-alpha.9-plaintext-assignment-seam-candidate.json`.
On Apple arm64, repository-pinned Rust 1.95.0 passed format checks, 2/2 feature
configuration tests, 2/2 encrypted/plaintext schema tests, 68/68 filtered V2
unit regressions, 19/19 filtered V2 integration regressions, and three direct
schema regressions. The first dependency fetch failed only at Cargo's default
low-speed threshold and succeeded after a bounded low-speed/timeout retry. One
existing async test overflowed the default macOS test-thread stack; the exact
test and the complete filtered regression passed with a 16 MiB test stack.

This is source feasibility, not qualification. No live call has yet exposed
`encrypted_function_args: []`, exact PreToolUse plaintext, deny-before-handler
behavior, or byte-identical recipient delivery through this switch. The
candidate is not installed, so Phase 1, P1, and direct write remain false.

After freezing the artifact, the complete provider-free suite passed 263 tests
in 37.723 seconds and the agent-template checks passed. The Phase 1 gate,
mutation-surface gate, same-UID trust gate, pinned native-seam gate, and live
candidate-receipt gate each remained structurally valid and returned exit 2
for their documented qualification gaps. The mutation source replay still had
zero anchor failures. This confirms the candidate did not silently promote any
later authority.

A separate exact-root, five-minute, tamper-evident diagnostic arm observed one
real `SubagentStart` without changing the trusted Hook command. The event shape
contained `agent_id`, `agent_type`, `cwd`, `hook_event_name`, `model`,
`permission_mode`, `session_id`, `transcript_path`, and `turn_id`, but no
`message`, `prompt`, or other selected plaintext-bearing field. Its SessionMeta
jointly bound parent `01a00bf2-1c5f-7d01-8bba-164bc4c3be04`, child
`01a00bf2-8ff0-7942-bea6-ffa3d53ec36b`, role
`g4_qualification_probe_worker`, and canonical path
`/root/g4_cli_root_identity_10`. Because no pending exact assignment existed,
the child made zero function calls and returned `TASK.CONTEXT_LOST`; the parent
and child completed the native task without promoting authority.
The shared Hook chain recorded the same target child at adjacent sequence 230
`SubagentStart` and sequence 231 `SubagentStop`; that proves one lifecycle
pair's visibility, not pending→active assignment continuity.

The arm was disarmed to immutable history, the trusted Hook config returned to
SHA-256 `ffaad5c3533a2016253af148c96721818807823f779845a35c5d7dad2c676c2b`,
and installed candidate sources match the repository hashes recorded in
`probes/g4-live-native-hook-schema-20260817.json`. These facts close neither P1
nor P2: exact SessionMeta identity cannot be joined to exact assignment bytes
when the only pre-spawn message is opaque, and the startup event has no
plaintext. An explicit parent staging API remains only a design direction
unless a trusted host can prove equality to the child-delivered bytes. Phase 1
and `direct_write_qualified` remain false; Phases 2/3 remain closed.

The exact post-probe provider-free suite ran 251 tests in 36.110 seconds and
passed, including agent-template checks. An earlier full-discovery run exposed
a test-only duplicate `CorruptState` class identity caused by suites reloading
top-level Hook modules; the arm test now binds its exception/store to the same
module instance as the implementation, and the final complete run is green.
The executable G4 gate remained valid
but returned exit 2 with all twelve P-gates and nine exit receipts unresolved.
Pinned mutation-source anchors at
`9392c3fa5bcda342b5b96a1a04d67b2f781617c2` had zero drift and the matrix
retained ten blockers, so require-qualified exited 2. The same-UID trust probe
again showed rollout and state unprotected and exited 2 in require-protected
mode. The global callback chain was structurally valid through sequence 255,
but require-complete exited 2 for one callback pending in foreign runtime
session `01a009f8-d83c-73e2-b960-2cba273d2250`; it is not attributed to or
recovered by this runtime. These are raw fail-closed summaries, not completion
evidence.
