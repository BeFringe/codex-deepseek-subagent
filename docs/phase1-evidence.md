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
  the assignment. The default remains
  `status=unavailable, source=null, receipt_sha256=null`; a parent-fabricated
  `verified` receipt is corrupt state. One qualification-only exception now
  derives a verified receipt from an exact trusted Hook overlay. Its digest
  binds runtime session, parent, role, requested task, canonical AgentPath,
  direct `/private/tmp` Git root, one owned path, root/base identity, and
  lifetime. It cannot grant Git operations and is accepted only with the exact
  apply-patch qualification verification. This is a bounded test ceiling, not
  a general Codex host/UI consent signal.

The compact invariant freezes both facts. Without the exact qualification
overlay, a write capsule with parent intent `allow` may reach later read-only
contribution/lifecycle checks, but its first mutation request is denied before
execution and moved to unresolved as `write_authority_gates_missing`. The
receipt mechanically lists all three
current blockers: `trusted_host_user_write_consent`,
`direct_write_qualification`, and `live_mutation_mediation`. Exact paths,
parent/sibling writer claims, Git authority, sandbox, identity, callback,
termination/quiescence, and the disk barrier remain separate gates.

Provider-free qualification fixtures now prove the complementary bounded path:
the exact overlay is injected only during spawn capture, survives capsule
validation, is rechecked against real child identity at PreToolUse, then
acquires and releases the exact child-owned writer lease around one simulated
successful callback. Missing overlay, wrong path, wrong identity, non-write
mode, extra ownership, Git authority, or a forged receipt cannot enter this
path. No live configuration has been changed by this fixture, and global
`direct_write_qualified` remains false.

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

The lease store now distinguishes an active child's own exact write ownership
from a foreign owner. A non-root actor may acquire a Git writer lease only when
its real SessionMeta actor exactly matches one active write capsule and every
patched path is equal to or below that capsule's owned paths. That one active
record is not treated as a conflicting foreign lease; parent, sibling, prior
claim, read-only, wrong-identity, and out-of-scope records still block. A
provider-free positive acquires and releases the exact child's lease, while an
otherwise identical patch outside its ownership creates an audited
`missing_active_path_authority` conflict. The full assignment/lease module
passes 55 tests. This removes a circular self-conflict but does not make child
mutation live-reachable: trusted-host consent, the qualification-only runtime
grant, workspace sandbox binding, callback, and quiescence remain required.

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
schema selection, exact PreToolUse→handler→recipient byte equality, a distinct
same-message pre-dispatch deny call, native AgentPath/control preservation,
encrypted-mode regression, and redacted evidence. Schema 2 deliberately keeps
the successful delivery and deny-before-handler cases under different
tool-use identities: the prior schema accidentally required a recipient to
both receive and not receive the same call, which no live runtime could satisfy.
The checker also binds runtime-binary provenance and exact parent/turn/tool/target
identity. The opt-in is assignment transport only and cannot grant mutation
authority. No live receipt exists, so the checker is valid but
`--require-qualified` exits 2.

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

The paired-call contract repair was then replayed across the complete
provider-free suite: 267 tests passed in 130.653 seconds, including the agent
template checks. The live checker remains valid and exits 2 without a schema-2
receipt; no status flag was promoted by repairing the impossible fixture.

The same isolated source then produced a release binary with the repository's
thin-LTO profile in 30m19s. The Apple-arm64 binary is 293,620,392 bytes with
SHA-256 `e2874bda15552fac7b677b2553978a452c8c7beb5cae536ec95aead4d8b174d6`;
it is ad-hoc linker-signed and remains outside the signed Codex App. App build
6662 exposes a `CODEX_CLI_PATH` selection seam. The checked-in wrapper pins the
candidate hash and injects only the two Multi-Agent V2 transport settings, so a
future live probe need not replace `/Applications/Codex.app` resources or edit
live config. Its marker is only an accidental-execution guard, never trusted
user consent or mutation authority. Version, feature, and stdio EOF startup
smokes passed without a model invocation. The machine preflight is frozen in
`probes/codex-0.148.0-alpha.9-plaintext-live-selection-preflight.json`.
The complete provider-free suite then passed 276 tests in 50.375 seconds,
including agent-template checks.

No App process was restarted and no candidate was selected live. Fresh-process
selection and rollback both interrupt this task and remain behind explicit
user authorization; P1, Phase 1, and direct write therefore remain false.

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

## Candidate GUI selection incident and headless-only recovery seam

The previously prepared `CODEX_CLI_PATH` selection plan was attempted after
explicit user authorization and failed at the server boundary. The variable
caused the signed GUI shell to run the unsigned candidate as its sole app-server.
Plaintext mode removed the encrypted marker from the server-reserved
`collaboration.followup_task` schema, so two first-hand rollout errors reported
that the reserved function did not match the configured schema. All App requests
then returned HTTP 400; no plaintext assignment was delivered and P1 did not
advance.

External recovery sessions removed launchd job
`org.openai.codex.g4.candidate.20260817`, restored the official signed resource
at SHA-256
`6170ff5578170ee9b74ad92bfcff96e6186f41d02b60815a7c2b01ad424c754f`,
and returned `hooks.json` to
`ffaad5c3533a2016253af148c96721818807823f779845a35c5d7dad2c676c2b`.
Fresh inspection found no launchd guard variables or candidate process. Because
the affected session could not execute its own rollback, this is an exact
emergency recovery receipt but not the rollback exit receipt required by G4.

The wrapper was replaced in place with a headless-only guard. It now rejects all
GUI/server entry points, requires config/rules isolation for `exec`, and permits
stateful SessionMeta probes only behind a separate exact-root/clean-Git/JSON/
Hook-trust guard. It forces `g4_assignment`, read-only, never-approve, and no
code-mode host by default. A separately guarded exact-path probe may select
`workspace-write` only for a clean exact Git root under
`/private/tmp/codex-g4-write-*`; this does not broaden GUI/server entry points.
The wrapper now also rejects all caller-supplied config overrides and can inject
only the fixed 20,000-token auto-compaction limit behind its separate stateful
qualification guard.
Its current SHA-256 is
`d9e86d3b0b247d1f1d96f20c7f87d9c4323db89067389a81d58ae4221d409d1b`;
the incident receipt separately preserves the historical unsafe wrapper hash.
A candidate `codex exec` no-tool smoke under the non-reserved namespace returned
exactly `READY` through the current ChatGPT login without HTTP 400 and exited.
That proves server schema acceptance only, not spawn, identity, assignment
equality, or deny-before-dispatch.

The temporary build is reproducibly bound by
`probes/codex-0.148.0-alpha.9-plaintext-candidate-archive-20260817.json`:
base commit, twelve-path diff, byte-identical checked-in patch, release SHA/size,
and all thirteen candidate-root writer receipts are frozen without raw payload
or credential values. After the successful isolated root lifecycle probe, the
Cargo target had grown to 36 GiB. The exact 535,257,624-byte debug binary was
preserved separately at SHA-256
`0d6a185f7e0b12097056fbd826c46e0f7457b933a5d7f295195e0a9381475967`,
then only `codex-rs/target` was deleted. The remaining source tree is 74 MiB and
its 20-path diff still hashes to
`0de474cbc2f917e5198c62c4b2e79a169805dd0a45959621af271d0423b26574`.
The deleted target is rebuildable from the pinned source and patch but is not
directly recoverable. The full
incident is recorded in
`docs/incident-2026-08-17-candidate-live-selection.md` and
`probes/g4-candidate-live-selection-incident-20260817.json`.

This live negative invalidates GUI app-server selection as a qualification seam.
It does not authorize Phase 2/3 and does not promote Phase 1, P1, or direct write.

## Headless plaintext lifecycle boundary (2026-08-17)

Three isolated stateful `codex exec` attempts used the headless-only wrapper,
the current ChatGPT login/provider, a clean disposable Git root, read-only
sandbox, never-approve posture, and an exact candidate binary hash. None
selected the GUI app-server, edited live config, or changed the signed App
resource. The App resource and installed Hook hashes remained
`6170ff5578170ee9b74ad92bfcff96e6186f41d02b60815a7c2b01ad424c754f`
and `ffaad5c3533a2016253af148c96721818807823f779845a35c5d7dad2c676c2b`.

The first attempt crossed the previous assignment-capture blocker. Real parent
`PreToolUse` captured the exact 3343-byte assignment and staged a capsule; real
`SubagentStart` bound child
`01a00f36-b0d7-7aa2-9705-fd4c5126b996` to
`/root/g4_cli_lifecycle_2` and moved that capsule to active. The child still
failed before a function call because the service returned
`encrypted_function_args=null` and the candidate treated only an explicit
empty array as plaintext. Its rollout therefore contained the plaintext bytes
inside `agent_message.encrypted_content`, which the server rejected. No
`SubagentStop` followed, so the active record remains fail-closed evidence.

The source candidate now derives direct plaintext from the exact configured
Multi-Agent V2 namespace and plaintext delivery mode when the server marker is
absent, while a nonempty marker remains encrypted. Plaintext inter-agent input
is serialized to a supported `role=user` message; encrypted mode remains the
default. Custom-role reload also preserves the CLI/session Hook-trust bypass.
The live-shaped router regression and the five-case spawn-wire matrix passed.
The exact 20-path patch and debug binary are frozen in
`probes/codex-0.148.0-alpha.9-plaintext-assignment-seam-candidate-v2.patch`
and its JSON manifest.

The second attempt proved that repair at the live server boundary. Child
`01a00f41-655f-7ce0-8eb5-92f8fd46413d` received one ordinary user message,
not encrypted agent content, with the exact active capsule and canonical path
`/root/g4_cli_lifecycle_3`. It returned an identity-exact final attestation and
real `SubagentStop` moved the incomplete report to unresolved. The requested
`list_mcp_resources` tool was unavailable under the isolated no-user-config
surface; the model attempted custom `exec`, which the disabled code-mode host
blocked before execution. Verification was truthfully nonzero,
`assigned_slice_complete=false`, and the worktree stayed clean.

The third attempt selected native `list_agents`, but Hook input flattened the
custom namespace to `g4_assignmentlist_agents`. The runtime allowlist recognized
only the unqualified name and denied it before execution, with `disk_changed=false`.
Fifteen truthful `SubagentStop` observations then repeated because active
authority had already moved to unresolved; the host interrupted the bounded
probe with exit 130 and confirmed the candidate process absent and Git frontier
unchanged. This is both an exact read-only alias false negative and a negative
termination/stop-continuation witness. The provider-free repair uses one closed
alias only; it does not strip arbitrary prefixes or authorize spawn/send/
follow-up tools.

After adding the closed alias fixture, the fresh provider-free suite passed
290 tests in 34.944 seconds, including agent-template checks. The executable
G4 gate remained structurally valid with every P-gate partial,
`phase1_complete=false`, and `direct_write_qualified=false`.

These attempts provide the first live
`exact parent capture -> exact SessionMeta/AgentPath -> active capsule ->
plaintext child model input -> SubagentStop visibility` chain. P1 and P2 are
therefore materially advanced but remain partial until a permitted child
read-only call and complete attestation succeed, a distinct deny-before-handler
pair is joined, and the larger identity cohort closes. Strong quiescence,
post-termination disk barrier, compact/resume, full mutation mediation,
Windows/DeepSeek, and functional rollback remain open. Consequently
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed. The privacy-minimized raw summary is
`probes/g4-live-plaintext-lifecycle-20260817.json`.

### Root read-only reported-to-consumed chain

After installing only the exact closed alias
`g4_assignmentlist_agents -> list_agents`, attempt 5 passed the child tool
boundary and durably recorded the first Git attestation. It then exposed a
separate interface defect: the final-attestation seed is schema-versioned, but
the final report has a different exact top-level shape, while the old stop
feedback named no missing or unexpected fields. The child repeatedly copied
the seed `schema` field and remained active until the bounded parent process was
interrupted. Disk and Git remained unchanged. The repair reports sorted missing
and unexpected field names without echoing values and the probe prompt now
states that the seed object is not the final report object. Forty-one focused
runtime/prompt tests passed.

Attempt 6 then completed the first live product-independent root chain. Parent
`01a00f59-a291-7502-b4af-c97ceec1cadb` spawned child
`01a00f5a-0f8b-7e22-b8bc-e997946babdb` at the exact path
`/root/g4_cli_lifecycle_6`. Hook-event sequence 606--611 joins the exact spawn
PreToolUse, SubagentStart, qualified `g4_assignmentlist_agents` PreToolUse, and
three SubagentStop observations. The child received a successful native
`list_agents` result, corrected one missing top-level field and one nested
provenance-shape error from field-only feedback, and returned an exact complete
attestation. The Hook moved assignment
`726eeea3-b88e-4e85-bd5b-cdab0f2095f0` to `reported`.

A fresh parent process then verified the exact root/branch/full HEAD, empty
status/index, successful host function output, accepted final report, absent
candidate processes, and a post-termination disk barrier. The five independent
parent integrity dimensions all passed against adjudication-input SHA-256
`1e170afdaa09b22d40fc545833c89eb0acfd3130a5883d0c68319db6f71fb76d`,
and the state transition atomically advanced `reported -> consumed`. The
consumed envelope SHA-256 is
`8ea05c504453b37de78bca0c8c23cdb7701095e9bedc2775ff2892cf057d64c9`.
The privacy-minimized input and result receipts are
`probes/g4-live-root-lifecycle-adjudication-input-20260817.json` and
`probes/g4-live-root-lifecycle-adjudication-result-20260817.json`.

This closes one real root read-only invocation through P1/P2/P3/P4/P5b/P6
sub-boundaries; it does not close any whole P-gate. The distinct paired
deny-before-handler calls, nested/serial/concurrent identity cohort,
compact/resume, full mutation and sandbox negative space, global
termination/quiescence, representative P6a/P6b/P6c live workload, Windows,
DeepSeek, and functional rollback remain open. Phase 1 and direct write remain
false, and Phases 2/3 remain closed.

After freezing these receipts, the complete provider-free suite passed 294
tests in 48.497 seconds, including agent-template checks. The executable G4
gate remained valid with every P-gate partial, `phase1_complete=false`, and
`direct_write_qualified=false`; the pinned mutation matrix retained zero source
anchor failures and the same-UID probe remained an explicit trust failure.

### P1 live-oracle realignment

The successful root chain also disproved one old oracle assumption. The current
OpenAI response carries `encrypted_function_args=null`, not an empty array, even
though the session is explicitly configured for plaintext delivery. Requiring
only `[]` would reject the observed successful route and encourage repeated
probes against an impossible server shape. Treating every `null` as plaintext
would be an unsafe global bypass.

The contract is therefore schema 3. It admits either the native explicit-empty
marker or the exact-configured null-marker route, but the latter requires the
session plaintext opt-in, exact `g4_assignment` namespace, and exact one of
`spawn_agent`, `send_message`, or `followup_task`. Wrong namespace/operation,
missing opt-in, unconfigured null, nonempty private marker, encrypted default,
and V1 remain encrypted or fail closed. GUI `CODEX_CLI_PATH` selection is now
rejected by the checker rather than retained as a nominal option. Sixteen
focused oracle tests pass, including explicit-empty compatibility and null-route
negative space. No live schema-3 receipt yet covers all three operations and
their distinct same-message deny pairs, so P1 remains partial.

## Alpha.15 exact-source evidence hardening (2026-09-07)

The interrupted migration work was resumed without replacing the dirty
worktree. The source-oracle checkers now bind their claimed Codex version to
the exact Git top level and full source commit instead of accepting any checkout
whose sampled strings happen to match. The pinned `0.148.0-alpha.15` commit is
`ffe1de5cec9c0cd02629eb246534e4622da0ff41`. Against a fresh checkout of that
exact tag, both the mutation-surface checker and the native-assignment-seam
checker returned `valid=true` with no source-identity, anchor, or order
failures.

The schema-3 mutation inventory adds two source-observed negative surfaces:
the implicit plugin-metrics sidecar attached after shell PreToolUse, and
accepted MCP/node-repl result evidence retained after PostToolUse acceptance.
Neither is promoted to a mediated path. The checker still returns
`direct_write_qualified=false` and lists both surfaces among its blockers.

The fresh provider-free suite then ran 307 tests in 39.547 seconds and passed,
including agent-template checks. The same-UID trust probe again reported both
rollout and state protection false; its `--require-protected` mode exited 2.
The executable G4 status remained structurally valid with every P-gate partial,
`phase1_complete=false`, `direct_write_qualified=false`, and Phase 2/3 closed;
`--require-phase1-complete` exited 2. This slice hardens evidence identity and
negative-space enumeration only. It is not live qualification.

## Current provider-inheritance boundary (2026-09-07)

The post-migration baseline was reconstructed again before changing the Phase 1
decision. The local branch was `main` at full HEAD
`56314fbae6af2ad29e27ff60c9d5645939055e27` before this slice. The configured
`origin` and `upstream` remain SSH URLs, but the migrated SSH identity cannot
currently authenticate: `git ls-remote origin main` returned public-key denial.
No remote or key was changed. Read-only public HTTPS resolution independently
found BeFringe `main` at
`076ee0df9aca11fbc0c19a6ccd7cd8befc0051f7` and the current Utopia redirect/main
at `4117c7c40d0c1f0056860716af7478d7734694ee`.

At that checkpoint, the running Codex App was not the user-observed standalone
`0.153.4` release. Its
bundled CLI reports `0.150.0-alpha.8` and hashes to
`4ff5e75f028e913cfeb53bd7319f87573cdce6538c1b1ccc44ce62d5ce51ca1d`.
The live process selects the signed App resource directly for `app-server`; no
candidate or wrapper path appears in its command line. The installed Hook
configuration remains unchanged at SHA-256
`ffaad5c3533a2016253af148c96721818807823f779845a35c5d7dad2c676c2b`.
The old candidate directory and the earlier large Cargo target directories are
absent, so this slice neither retains nor recreates the former 27--36 GiB build.

Three exact, clean source checkouts were used only as read-only oracles:

- OpenAI Codex `0.150.0-alpha.8` at
  `fcbdb57851be70192fd0c21faa9e529146e93ff1`;
- OpenAI Codex `0.153.4` at
  `3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`;
- Utopia MixAgents `main` at
  `4117c7c40d0c1f0056860716af7478d7734694ee`.

Both OpenAI versions apply bounded role configuration at native spawn and test
that the child retains the parent's provider configuration. The current Utopia
package still contains the legacy standalone agent's
`model_provider = "deepseek"`, but documents that route for Codex `0.148.x` and
earlier only and points current users to an independent App Server worker via
MixAgents Broker. The executable provider-inheritance oracle verified every
source top level, full HEAD, positive anchor, and negative anchor. It returned
`valid=true`,
`legacy_role_provider_override_qualified=false`,
`broker_satisfies_native_agentpath_lifecycle_contract=false`, and
`p7_deepseek_regression="blocked-upstream"`; requiring the legacy native route
exited 2.

This is a new P7 hard blocker, not a reinterpretation of the encrypted
assignment failure. Assignment transport, provider selection, wire transport,
and request normalization remain orthogonal. A plaintext Hook may repair an
opaque assignment but cannot grant a provider override that native spawn now
forbids. Likewise, ZHIPU's current official direct Responses endpoint
`https://open.bigmodel.cn/api/v1` can eliminate a protocol bridge only after
qualification; its documented global provider switch does not preserve the
OpenAI parent and cannot supply the missing per-child provider seam.

Consequently P1--P6 product-independent G4 work remains feasible and should
continue, while P7 cannot pass on Codex `0.149.0+` under the unchanged native
AgentPath/wait/callback/cancel/Multi-Agent V2 contract. MixAgents Broker is a
different lifecycle architecture and is not substituted as evidence. Phase 1
and direct write remain false, and Phases 2/3 remain closed.

After pinning the current mutation/assignment source oracles, provider boundary,
and stage contracts, the fresh provider-free suite passed 311 tests in 39.730
seconds, including agent-template checks. The then-current `0.150.0-alpha.8`
mutation and assignment checkers both returned `valid=true` against the exact
source commit. The same-UID trust probe still found rollout and state protection
false and exited 2 when protection was required. The G4 gate remained valid
with all P-gates unresolved, `phase1_complete=false`, and
`direct_write_qualified=false`; requiring completion exited 2.

### Historical App Server lifecycle source oracle

The newly open App Server and core sources removed several schema guesses from
the next identity cohort at the then-bundled `0.150.0-alpha.8` source. This
artifact is now prior-runtime replay evidence rather than the current default:

- the App Server protocol enumerates PreToolUse, PostToolUse, PreCompact,
  SubagentStart, and SubagentStop;
- only the supported event set, including SubagentStart but excluding
  PreCompact and SubagentStop, can emit `additionalContext`;
- SubagentStart exposes session, turn, transcript, cwd, agent id, and agent type,
  while SubagentStop additionally exposes the child transcript path;
- the requested task-name segment is joined to the parent's AgentPath and the
  spawn result returns that canonical path, including the tested
  `/root/parent/child` nested case;
- rollout persistence writes SessionMeta before pending items and flushes the
  file; and the resume regression test preserves the previous AgentPath.

The lifecycle source checker verified the exact Git top level, full source HEAD,
and all eleven anchors with no failures. It reports all four source contracts as
verified, but keeps live SessionMeta identity and termination/quiescence false;
`--require-live-identity` exited 2. Source behavior is an oracle for the next
root/nested/serial/concurrent live cohort, not a replacement for its receipts.
The complete post-oracle provider-free suite passed 314 tests in 38.673 seconds,
including agent-template checks; the G4 gate remained valid and fail closed.

## Signed prior-runtime encrypted spawn negative (2026-09-07)

A clean, root-level native spawn was attempted with the explicitly approved
`g4_qualification_probe_worker`, `fork_turns="none"`, task name
`g4_current_root_1`, and one mechanically generated read-only authority
declaration. The parent supplied exactly one BEGIN marker and one END marker,
no paths or Git authority, and a clean `main` review range at full HEAD
`e45119614242841da24d6d043db8373a56e59ca3`.

The then-signed App runtime encrypted the assignment before PreToolUse. Rollout tool
call `call_aXgF6vga72i2GP1ZF9mY6NrK` retained the expected argument keys and
identity fields, but its message was a 4964-character string beginning
`gAAAAAB`; both authority-marker counts were zero. The raw encrypted value was
not copied into evidence. Hook receipt sequence 746 observed the namespaced
`collaborationspawn_agent` target and denied it before the handler with
`TASK.HANDOFF_BLOCKED: spawn message must contain exactly one authority
declaration`.

No child, SubagentStart, SubagentStop, or callback followed. A native agent-list
snapshot contained only `/root`. The post-attempt branch and full HEAD were
unchanged and the worktree remained clean. No approval was requested, no
credential value was touched, and the GUI remained on its signed App Server.

This historical live behavior aligns with the prior signed runtime source
oracle: encryption precedes PreToolUse for this spawn route. It is not an
authority-text parser defect and repeating the same probe cannot reach
SubagentStart. P1
therefore remains partial and current-runtime plaintext qualification remains
false. The privacy-minimized receipt is
`probes/g4-prior-signed-runtime-encrypted-spawn-negative-20260907.json`.
The post-receipt provider-free suite passed 316 tests in 37.108 seconds,
including agent-template checks.

## Codex 0.153.4 CLI / SDK / App Server boundary oracle (2026-09-07)

The newly published SDK and App Server sources improve inspection and isolated
probe construction, but do not restore the heterogeneous native-child seam.
The exact `rust-v0.153.4` source at
`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a` establishes four distinct facts:

- core still advertises Multi-Agent V2 `message` fields as encrypted;
- core has an internal plaintext branch when an upstream collaboration
  `ResponseItem` already carries `encrypted_function_args=[]`, but neither Hook,
  SDK, nor App Server exposes a client parameter that selects that branch;
- the TypeScript SDK launches `codex exec`, while the Python SDK launches a
  separate `codex app-server --listen stdio://` process;
- App Server `thread/start` can choose a provider for an independent thread and
  can observe genuine native children through parent/thread/collaboration
  metadata, but it exposes no native spawn RPC. A separately started thread is
  therefore not a parent-owned child and cannot substitute for canonical
  AgentPath, wait, callback, cancel, or Multi-Agent V2 graph authority.

The executable component-boundary oracle verified the exact source top level,
full HEAD, twelve positive/negative anchors, and the provider-inheritance
restriction. It returned `source_visibility_improved=true`,
`isolated_probe_harness_feasible=true`,
`native_heterogeneous_child_restored=false`, and
`pretool_plaintext_assignment_visible=false`. Requiring a native heterogeneous
child exits 2.

The assignment-seam and App Server lifecycle contracts were also re-anchored to
the same `current_signed_runtime` identity. All ten causal assignment anchors,
three ordering checks, and eleven lifecycle anchors match the exact current
source commit. Their checker defaults now resolve through
`probes/codex-runtime-evidence-index.json`; the intermediate alpha8 contracts
remain immutable historical replay inputs and no longer define “current”.

This is useful progress at the observation layer: a version-pinned Python SDK
client can drive a disposable stdio App Server for provider-free lifecycle and
termination probes without selecting the GUI App Server. It is not a transport
or provider qualification. Utopia's current package independently reaches the
same compatibility conclusion: the standalone agent TOML is now explicitly
legacy for Codex `0.148.x` and earlier, and its replacement Broker owns a
separate App Server lifecycle. ZHIPU's direct Responses endpoint removes a
possible Phase 3 protocol bridge, not the missing per-child provider or P1
assignment seam. P1 and P7 remain partial, Phase 1 and direct write remain
false, and Phases 2/3 remain closed.

After adding this oracle, the complete provider-free suite passed 319 tests in
38.787 seconds, including agent-template checks. The exact 0.153.4 component
oracle, the two-version provider-inheritance oracle, and the G4 status checker
all returned `valid=true` while preserving their fail-closed verdicts.

## Exact live-runtime version binding

The runtime guard previously accepted only the historical isolated
`0.148.0-alpha.9` SessionMeta even though the then-signed App baseline was
`0.150.0-alpha.8`. Replacing that constant with the then-current version would have
made the earlier live receipt unreplayable; accepting arbitrary versions would
have weakened resume identity.

The guard now accepts the closed live-evidence set containing those two exact
versions and adds the observed `codex_version` to the child runtime identity
captured at SubagentStart. The existing active-binding equality therefore
rechecks the same exact version at every later tool/compact/stop boundary. A
change from one otherwise accepted version to the other no longer matches the
active capsule, and SubagentStop independently rejects parent/child SessionMeta
with different versions. At that checkpoint, Codex `0.153.4` remained
source-only and was deliberately absent from the live runtime set; the later
installed-baseline section records the signed update before admitting it.

The focused runtime-guard suite passed 42 tests, including current-version
acceptance, historical replay, unsupported-version rejection, accepted-version
drift denial, and mixed parent/child stop denial. This fixes a provider-free P2
guard defect; it does not supply the missing P1 plaintext call or qualify any
live child.

The complete post-change provider-free suite passed 322 tests in 37.639
seconds, including agent-template checks. The 0.153.4 component oracle and G4
gate both returned `valid=true`; every P-gate remains partial and all promotion
flags remain false.

## Installed Codex 0.153.4 convergence and immutable SessionMeta (2026-09-07)

The standalone entrypoint now resolves to the packaged arm64 `0.153.4` binary,
and the signed Codex App bundle was updated to `26.901.51231` (`8109`). Its
bundled CLI/App Server also reports `0.153.4`. The running App Server selects
that bundle resource directly, both launchd and this task have
`CODEX_CLI_PATH` unset, and the App signature validates to OpenAI team
`2DC432GLL2`. The exact paths and SHA-256 values are recorded in
`probes/codex-0.153.4-installed-baseline-20260907.json`; the standalone and App
binary hashes differ, so the evidence claims semantic-version convergence, not
byte identity.

The current long-lived task remains an intentional historical replay: its first
rollout record says `0.148.0-alpha.9`. The recent roots inspected after the App
update still began under `0.150.0-alpha.8`; no fresh `0.153.4` SessionMeta had
yet been created. Those immutable facts are not rewritten. The runtime guard
now admits exact `0.153.4` SessionMeta so a future fresh root and child can bind
without a stale-version false denial, while still rejecting `0.153.5`,
parent/child version mismatch, and a supported-version change after activation.

This is a P2 precondition repair, not live identity evidence. The next native
cohort must start in a fresh `0.153.4` root and independently prove its child's
SessionMeta, canonical AgentPath, callback, and termination chain. It also does
not change the source-proven P1/P7 blockers: native V2 still advertises an
encrypted assignment and bounded child-role overrides still preserve the
parent provider. Phase 1 and direct write remain false; Phases 2/3 remain
closed.

The independent SessionMeta matrix now also pins `0.153.4` to exact source
commit `3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`, while replaying the three
previous runtime/source pairs. The provider-free root/nested/serial/concurrent
fixture therefore exercises the currently installed version, but retains
`evidence_origin=provider_free_fixture`, `adjudication_authority=none`, and
`p2_live_qualified=false`.

## Codex 0.153.4 mutation and App Server host-control boundary

The native-tool schema-3 mutation catalog was re-pinned to the exact `0.153.4`
source. All existing anchors remain present and the checker reports
`valid=true` with twelve mutation-capable blockers; requiring direct-write
qualification still exits 2. The earlier `0.150.0-alpha.8` and alpha matrices
remain replayable.

Source inspection also exposed a separate control plane that must not be
misclassified as a child tool. App Server accepts concurrent `fs/writeFile`,
`fs/createDirectory`, `fs/remove`, and `fs/copy` client RPCs; the filesystem
write processor passes `sandbox=None`. Its `command/exec` family uses the
server sandbox, whereas experimental `process/spawn` explicitly runs without a
Codex sandbox. These parameter schemas contain no thread identity. The exact
contract and checker are
`probes/codex-0.153.4-appserver-host-control.json` and
`probes/check_appserver_host_control.py`.

The source checker passed all positive and negative anchors and deliberately
returned `native_child_reachability_proven=false`,
`pretooluse_child_mediation_proven=false`, and
`same_uid_client_trust_proven=false`; `--require-child-mediated` exited 2. This
is positive visibility progress for P4, not a capability grant. The live GUI
App Server must not receive mutation requests. The same-UID state probe
independently remained negative for both rollout and G4 state protection.

The complete provider-free suite after these changes passed 333 tests in
49.235 seconds, including agent-template checks. The exact 0.153.4 component,
native mutation, and App Server host-control source checkers returned
`valid=true`; their qualification-required modes returned 2 as designed. The
executable G4 status remained valid with every P-gate partial,
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 closed.

## Semantic current-runtime cutover and isolated host-control probe

The recent G4 checkers and tests no longer embed one release number as the
meaning of “current”. `probes/codex-runtime-evidence-index.json` assigns exact
version/source pairs to semantic roles and resolves the current assignment,
lifecycle, mutation, component, App Server, and installed-baseline artifacts.
The exact values remain immutable evidence; tests now assert role resolution,
cross-artifact identity, capabilities, and fail-closed relations. The alpha8
artifacts remain historical replay and provider-inheritance transition
evidence, but no current checker defaults to them.

The lifecycle oracle was freshly evaluated against the exact
`current_signed_runtime` source. All eleven Hook/SessionMeta/AgentPath/resume
anchors passed. This corrects the stale “Current App Server lifecycle” label;
it does not promote source behavior into a live SessionMeta receipt.

The reusable disposable App Server probe then launched only the signed bundle
binary selected by the semantic installed baseline. It supplied a fresh empty
`CODEX_HOME`, a five-key noncredential environment, no auth, no thread, and no
thread identity. `initialize`, `fs/writeFile`, and experimental
`process/spawn` succeeded; both sentinels existed before stdin EOF, the server
exited zero, and their exact hashes were unchanged at the bounded 0.2-second
post-exit disk observation. Temporary roots were removed. The privacy-minimized
receipt is `probes/g4-isolated-appserver-host-control-20260907.json`.

This proves that possession of this disposable client connection is sufficient
for the observed host-control mutations without thread identity or client auth.
It does not prove that a native child can acquire the connection, that
PreToolUse mediates the plane, or that global quiescence is strong. Accordingly
P4 remains partial and both promotion booleans remain false.

App Server source changes the active goal only by adding that host-control trust
boundary to P4. It does not replace canonical AgentPath, wait, callback, cancel,
or Multi-Agent V2 lifecycle requirements. The executable `goal_contract` in
`probes/phase1-g4-status.json` rejects such a substitution.

The complete provider-free regression then passed 344 tests in 41.605 seconds,
including agent-template checks. The semantic index and every current exact-source
oracle returned `valid=true`; G4 remained fail closed with all future phases
closed.

## App Server process-tree quiescence negative

The P4 validation target was explicit: if App Server EOF/exit were a strong
host-control termination barrier, no process descendant created through that
connection could mutate the disposable root afterward. Current source instead
starts `run_process` in an unretained Tokio task, and connection cleanup sends a
kill control message with no exit acknowledgement. The source contract now
pins both anchors without claiming native-child reachability.

The isolated negative used the same signed bundle binary, empty temporary
`CODEX_HOME`, closed noncredential environment, no thread, and no client auth.
An unsandboxed `process/spawn` child forked a descendant, started a new process
session, ignored `SIGTERM`, and wrote a readiness marker before client EOF. The
App Server exited zero 3.817 ms after EOF; the late-write file was absent both
before EOF and at server exit, then appeared during the 1.2-second bounded
post-exit observation with SHA-256
`f152945b358aa26a9e72e25381deff94e254c547089bd690dccd218e9414d148`.
Temporary roots were removed after the descendant completed.

The reusable probe and frozen receipt are
`probes/run_appserver_quiescence_negative_probe.py` and
`probes/g4-isolated-appserver-quiescence-negative-20260907.json`. This is an
auditable P4/P5b negative: App Server exit cannot serve as the required strong
process-tree or post-termination disk barrier. It does not prove any native
child can reach the connection, and it does not replace the missing native
SubagentStop/cancel/quiescence receipt. Phase 1 and direct write remain false.

After freezing this negative, the complete provider-free suite passed 349 tests
in 38.078 seconds, including agent-template checks. The current host-control
source oracle and G4 status checker returned `valid=true`; qualification remains
fail closed.

## Cross-surface App Server bootstrap closure

The schema-3 mutation matrix exposed App Server host-control separately but did
not enumerate how an external worker could acquire that plane. This was an
incomplete negative space: a shell, code-mode, MCP, extension, or equivalent
process/connection surface can start `codex app-server`, bootstrap or start its
managed daemon, or proxy/connect to its socket. Once the client owns that
connection, later filesystem and process RPCs have no native child
SessionMeta/AgentPath join and no per-RPC child PreToolUse event.

The current mutation catalog is therefore schema 4 and adds
`appserver_host_control_bootstrap`. Exact source anchors bind the direct App
Server runner, managed-daemon bootstrap, socket proxy, sandbox-none filesystem
write, and unsandboxed process-spawn capability. Its decision is
`block-from-external-worker-or-os-confine`. It is deliberately not a list of
native child RPC tools: it is a composition/bootstrapping escape across already
enumerated outer surfaces. A writer lease cannot qualify it, and a bounded
post-exit wait cannot contain the detached-descendant negative.

The executable goal contract now requires
`external_worker_bootstrap_denial_or_os_confinement` under P4. Dropping that
proof, omitting the new surface, or promoting it to `candidate-covered` makes
the provider-free contracts fail. Phase 1 and direct write remain false.

The fresh complete provider-free suite passed 351 tests in 36.995 seconds,
including agent-template checks. The semantic runtime index, schema-4 mutation
matrix with exact current-source anchors, App Server host-control contract, and
G4 status all returned `valid=true`. Their mutation qualification,
child-mediated host-control, Phase 1 completion, and same-UID protection modes
each exited 2 as required; the same-UID receipt still reports both rollout and
state protection as false.

## Child-role sandbox inheritance boundary

Exact current source inspection invalidated an earlier operational assumption:
the bounded `AgentRoleOverrides` projection does not include `sandbox_mode`,
and its source test explicitly preserves the parent permission profile. The
hostile-role regression also verifies that a role-file `sandbox_mode` key is not
projected. Therefore `sandbox_mode="read-only"` in
`g4-qualification-probe-worker.toml` remains a requested compatibility posture,
not proof that a child spawned from a write-capable parent is effectively
read-only.

The current component-boundary oracle is schema 2. It pins the sandbox omission
and preservation tests, reports `per_child_sandbox_override_available=false`,
and makes a `trusted_parent_or_host_sandbox_receipt` an explicit P4 proof. The
G4 worker template now tells the worker not to treat its role declaration as
effective authority. This is a source-backed fail-closed correction; no live
Hook, App Server, GUI selection, or product repository was changed.

The fresh complete provider-free suite passed 353 tests in 39.334 seconds,
including agent-template checks. The schema-2 component oracle matched the
exact current source and returned
`per_child_sandbox_override_available=false`; G4 remains incomplete and direct
write remains unqualified.

## Current signed-runtime plaintext seam source candidate

The assignment-transport candidate was ported onto the exact
`current_signed_runtime` source at full HEAD
`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`. It adds one explicit
`features.multi_agent_v2.message_delivery="plaintext"` opt-in while retaining
`encrypted` as the default. The change covers `spawn_agent`, `send_message`,
and `followup_task`; requires the exact configured namespace and operation;
accepts either the upstream explicit empty encryption marker or a missing
marker only under the configured opt-in; and keeps a nonempty marker encrypted.
Plaintext durable envelopes enter the model through the supported user-message
wire, while encrypted traffic retains the native agent-message wire. Parent
provider, auth, base URL, credentials, native lifecycle, and mutation authority
are untouched.

The 19-path, Cargo.lock-free patch applies cleanly to the pinned source. Source
verification passed formatting and diff checks, one feature-config test, one
protocol wire test, two schema-default/opt-in tests, five router/redaction
tests, one runtime-config test, two shared queue/trigger transport tests, and a
five-case spawn matrix: encrypted, explicit-empty plaintext, configured-null
plaintext under a custom namespace, Luna encrypted leaf, and legacy encrypted
leaf.

On this macOS arm64 host, the current upstream integration binary also stack
overflows in an unchanged adjacent subagent test under libtest's default stack;
that control and the candidate matrix pass with
`RUST_MIN_STACK=16777216`. This is recorded as a test-harness constraint, not a
runtime permission or qualification shortcut. The isolated Cargo target peaked
at 15 GB and was deleted after testing; no CLI/App candidate was built,
installed, or selected, and the 85 MB source worktree remains available.

The frozen artifacts are
`probes/current-signed-runtime-plaintext-assignment-seam-source-candidate.json`
and
`probes/current-signed-runtime-plaintext-assignment-seam-source-candidate.patch`.
This closes the current-source port and its source tests only. No current live
PreToolUse plaintext, SubagentStart capsule consumption, send/followup delivery,
paired denial, or broader identity cohort has been observed. P1 remains
partial; Phase 1 and direct write remain false, and Phase 2/3 remain closed.

## Current signed-runtime headless candidate build preflight

The source-qualified plaintext seam was compiled into a standalone arm64 CLI
without selecting it for the Codex App. A direct `codex-cli` build completed in
4 minutes 3 seconds and produced a 505,850,112-byte Mach-O binary with SHA-256
`aef151f72a66b06a57b0f75f172fcd4efae3bcb927ece8ad262165c560501f21`.
Its `--version` result matches the semantic `current_signed_runtime` entry. The
binary is ad-hoc linker-signed with no team identifier, so it is an isolated
candidate rather than a replacement for the signed App resource.

The compact build target occupied 4.2 GB, not the earlier projected 27 GB. It
was deleted after copying only the 482 MB executable into the disposable source
workspace. The source worktree remains 85 MB. No GUI process was restarted, no
`CODEX_CLI_PATH` or live config was changed, no credential value was read, and
no agent turn was started. The receipt is
`probes/current-signed-runtime-plaintext-assignment-seam-headless-preflight.json`.

This is positive build and storage-cleanup evidence only. It does not prove
live plaintext delivery, SessionMeta/AgentPath binding, Hook mediation,
callback, termination, sandbox confinement, or direct-write qualification.
P1 and Phase 1 therefore remain partial, both promotion booleans remain false,
and Phase 2/3 remain closed.

## Current-runtime live root plaintext lifecycle and parent adjudication

The installed G4 overlay had one migration drift before the live probe: every
directly imported handler dependency matched the repository except
`runtime_guard.py`, whose installed copy admitted only the migration runtime.
With no pending or claimed G4 assignment, that one file was compiled and
atomically replaced after preserving the previous bytes under
`~/.codex/hooks/backups/codex-deepseek-subagent-g4-20260907T063224Z/`.
The installed hash now matches the repository at
`719f57d2caa9c1cc833c0113f166385a2eda8380fea98967643daa4aa754595a`.
The v4 Hook, hooks registry, G4 role, App resource, and GUI App Server selection
were unchanged. No credential value was observed.

The absolute-path headless candidate first completed a no-tool `READY` control
under the current ChatGPT login. A stateful root then used only the candidate's
semantic plaintext opt-in and native collaboration namespace. Root thread
`01a07a93-c36e-73a0-b699-21e88de9e3d0` spawned child
`01a07a94-2bb9-7441-b25e-bd4734ef5482`, requested name
`g4_current_headless_root_2`, and received canonical AgentPath
`/root/g4_current_headless_root_2`. Both immutable SessionMeta records report
the current signed runtime, the same runtime session, root, branch, and full
Git HEAD; the child's source also binds depth one, the exact parent thread, and
`g4_qualification_probe_worker`.

PreToolUse sequence 1052 observed the exact 3,495-byte plaintext assignment at
tool call `call_9wOZO4Zcq3LwvVc4BHUwv7Ho`; SubagentStart sequence 1053 consumed
the same assignment hash and bound the child identity. The child performed one
native read-only `list_agents` control. Its first final used the wrong shape, so
SubagentStop sequence 1055 returned
`TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION`; the child emitted an exact
corrected attestation and sequence 1056 accepted it. The parent rollout contains
an exact child-completed activity and a non-timed-out wait. The wait event's
`receiver_thread_ids` projection is empty, so this evidence does not overclaim
per-target wait identity.

Two post-termination observations found the candidate process absent and the
root clean at the same HEAD, tree, write-tree, and index hash. The final report
moved from `reported` to `consumed` only after fresh five-dimension parent
adjudication against the immutable input hash
`e0009a9b402299701b3e957efef838435eede7c9ce3bf1c29490a10d32b94f77`.
The minimized receipts and executable assertions are:

- `probes/g4-current-headless-root-lifecycle-adjudication-input-20260907.json`;
- `probes/g4-current-headless-root-lifecycle-adjudication-result-20260907.json`;
- `tests/test_g4_current_headless_root_lifecycle_adjudication.py`.

This is the first current-runtime live proof that the candidate plaintext spawn
reaches PreToolUse, is consumed by SubagentStart, binds exact native identity,
survives an invalid-final continuation, produces a parent-visible completion,
and reaches consumed state. It advances P1, P2, P3, P5b, P6, P6a, and P6b.
It is one root read-only sample: distinct same-message deny pairs,
send/followup, nested/serial/concurrent cohorts, compact/resume, cancel,
mutation, trusted sandbox, and strong global quiescence remain open. Phase 1
and direct write remain false.

## Live missing-PostToolUse writer-lease recovery

A two-file documentation patch acquired writer claim
`df2bebbb-4214-46e3-abe4-b84c37c32f04`, then failed apply-patch context
verification before changing either target. The runtime emitted no PostToolUse
callback for that tool failure. The next overlapping patch was denied, proving
the residual lease failed closed. The exact recovery command first rejected a
noncanonical explicit root `agent_type`, then accepted the root identity derived
from immutable SessionMeta. It released the claim only because the before and
after path snapshot hashes were identical and persisted an abort receipt.

`probes/g4-live-missing-posttooluse-recovery-20260907.json` and
`tests/test_g4_live_missing_posttooluse_recovery.py` freeze the event without raw
tool payload. This is not multi-agent competition or child misbehavior; it is a
real missing-failure-callback lifecycle gap. Explicit unchanged recovery is
reproducible, but automatic failure-callback completeness and all-surface writer
serialization remain unqualified under P5b.

## Isolated ZHIPU direct-Responses feasibility

The current official ZHIPU Codex page directly specifies
`https://open.bigmodel.cn/api/v1`, `wire_api=responses`, and `glm-5.3`. Under
the user's explicit approval, three small direct HTTP invocations used the host
credential through curl configuration stdin. The value was never placed in
argv, printed, hashed, retained, or committed. The first 32-output-token control
returned HTTP 200 with a standard `response` object and `status=incomplete`.
The final 384-output-token control completed in 4.164160 seconds with separate
`reasoning` and `message` items and an exact 21-byte marker. Only response
structure, timing, counts, and request/response hashes were retained.

The receipt is `probes/zhipu-responses-direct-feasibility-20260907.json`, with
assertions in `tests/test_zhipu_responses_direct_feasibility.py`. It proves live
wire feasibility, not a native ZHIPU child: no Codex client, tool result,
streaming, continuation, callback, wait, cancel, SessionMeta, or AgentPath was
qualified. Current bounded agent-role projection still preserves the parent's
provider, so the missing per-child provider seam remains the critical join.
The three exploratory calls define neither a representative cohort nor p95.
Phase 3 remains closed and no bridge or live provider configuration was
installed.

## Exact child-provider authority seam candidate

The direct ZHIPU wire probe did not make the earlier G4 child provider-free: that
child performed real native inference through the inherited OpenAI parent
provider. Current source deliberately omits `model_provider` from bounded role
overrides, so neither the v4 Hook nor a child role file can select an external
Responses endpoint. Assignment transport and provider selection are separate
joins.

An isolated current-source candidate now adds only an exact parent-owned
`features.multi_agent_v2.child_model_providers` map. Its default is empty. A
role keeps the parent provider unless its exact agent type maps to an existing
provider id; a role file cannot authorize itself, an unknown provider fails
closed, and a different provider that requires inherited OpenAI authentication
is rejected. A resumed role child also fails if its stored provider differs
from the current exact mapping. This does not grant mutation authority or
change the parent provider.

The combined plaintext-plus-provider patch and machine-readable pre-live receipt
are `probes/current-signed-runtime-plaintext-child-provider-seam-source-candidate.patch`
and
`probes/current-signed-runtime-plaintext-child-provider-seam-source-candidate.json`.
Formatting, reverse-apply, one feature parse test, eighteen role/authority tests,
and one runtime config test passed. A standalone ad-hoc-signed CLI was built;
it has not been installed or selected by the GUI. The read-only GLM role fixture
contains a model name but neither a provider definition nor a credential value.

This is a Phase 1/P7 prerequisite candidate, not the generalized Worker /
Provider Profile abstraction of Phase 2 and not the optional bridge of Phase 3.
At this checkpoint no native external child had yet bound SessionMeta/AgentPath,
Hook mediation, callback, and termination evidence, so
`native_external_child_qualified`, Phase 1, and direct write remained false.

## Native OpenAI parent to ZHIPU child read-only tool loop

The first native external-provider run moved the blocker downstream. Root
spawn, exact ZHIPU SessionMeta, canonical AgentPath, SubagentStart capsule
injection, multi-turn Responses continuation, SubagentStop correction, and the
callback all worked, but the child reported that `list_agents` was unavailable.
Current source inspection found the exact cause: an unknown model receives
fallback metadata with no `multi_agent_version`, and child management tools are
removed before request construction. A direct ZHIPU Responses control then
returned HTTP 200 with a real forced function call, ruling out a general
function-calling absence.

The isolated source candidate now keeps the catalog gate and adds one narrow
exception: an unknown external child may see the standard local V2 management
tools only when its exact role and the provider id actually applied to that
child both match the parent-owned `child_model_providers` map. The default empty
map, a different role, and a different applied provider remain closed. This
exception grants no filesystem, Git, sandbox, or integration authority. Two
source tests cover the positive exact match and both mismatch cases.

One global `model_catalog_json` experiment was rejected before child creation
because it replaced the OpenAI parent's catalog and violated a server-reserved
tool schema. A second root run demonstrated the same reserved-schema guard when
plaintext tools used the `collaboration` namespace. A third run created an
exact child but intentionally exposed a missing CLI role override: the
installed native G4 role inherited `gpt-5.6-sol`, which ZHIPU rejected as an
unknown model. These failures caused no App selection or repository mutation.
The successful run restored the isolated `g4_assignment` namespace and the
CLI-only GLM role fixture.

Root thread `01a07b17-5b15-7e70-8d2d-278718a705f6` remained on the native
OpenAI provider and current ChatGPT login. It spawned child
`01a07b17-f863-7ef3-a17f-773af4df6808` as
`/root/g4_zhipu_native_tools_2`. The child's immutable SessionMeta reports the
same runtime session, `model_provider=zhipu`, the exact G4 role, V2, and the
expected root. Its matching TurnContext reports `model=glm-5.3`, a read-only
sandbox policy, and the managed restricted root-read permission profile.
PreToolUse sequence 1158 captured spawn, SubagentStart sequence 1159 bound the
capsule, and sequence 1160 observed the child's real
`g4_assignment.list_agents` call at tool-use id
`call_13176ecc4c2c4d16940a64f3`. The rollout contains the matching function
output. After three SubagentStop observations, the accepted attestation kept
the exact root, branch, full HEAD, empty changed-path set, and exit code zero;
the OpenAI parent received it through the native callback. A later bounded
process check found the candidate absent.

The frozen receipt and executable assertions are
`probes/g4-zhipu-native-child-tool-loop-20260907.json` and
`tests/test_g4_zhipu_native_child_tool_loop.py`. This qualifies one real
depth-one read-only external-provider tool loop and closes the earlier
"external child never calls a native tool" feasibility question. It does not
qualify mutation, strong global quiescence, resume/compaction, cancellation,
nested/serial/concurrent cohorts, POSIX/Windows parity, DeepSeek regression, or
live install rollback. `native_external_child_qualified`, Phase 1, and direct
write therefore remain false; Phase 2 and Phase 3 remain closed.

## External ZHIPU child fresh parent adjudication

The first ZHIPU record above intentionally remains in `reported`: evidence was
committed after its callback, so a later observer could no longer prove the
same Git frontier and must not retroactively mark all five parent integrity
dimensions as fresh. A second assignment therefore used the clean current HEAD
and a different task name, then performed parent adjudication before any source
or evidence commit changed that frontier.

Root `01a07e8e-8bc6-73e0-b5cf-9a997f03159a` remained on the OpenAI provider
and `gpt-5.6-sol`. It spawned child
`01a07e8f-25e1-75a1-8d02-18c509132691` through the exact parent-owned role to
provider map, without a spawn-call model or reasoning override. The child's
SessionMeta binds provider `zhipu`, model `glm-5.3` in TurnContext, parent
session, depth one, exact role, and `/root/g4_zhipu_consume_1`. Hook sequences
1175--1179 join spawn PreToolUse, SubagentStart, the child's
`g4_assignment.list_agents` call and two SubagentStop observations. The child
rollout contains the matching 127-byte function result, and the native parent
observed an exact completion activity and final callback. The wait receipt's
receiver list is still empty, so targeted wait identity remains unqualified.

After both candidate processes had exited, a fresh parent observed the original
root, branch, full HEAD, HEAD tree, write tree, index digest, empty status, the
reported state, and absence of active/unresolved/consumed state for assignment
`859e970a-0fc0-48c8-9e9f-c6f150b84a5b`. Location, mutation scope,
verification freshness, derivation provenance, and feasibility contract all
passed against the exact adjudication input SHA-256
`bf41dc8e145ec96a6202f4437247b58cbb6ff38d22d46c31ce5aefbc9d4ea342`.
The keyed state transition then atomically moved `reported -> consumed`; the
consumed envelope SHA-256 is
`81f893aa5ecdf1f1b9cfff252219ec41a1a96763cd3e4000db03754e1a8c8a19`.
The post-transition Git barrier remained exact and contained only the parent
adjudication input as an evidence write.

The input, result, and executable assertions are
`probes/g4-zhipu-native-child-parent-adjudication-input-20260908.json`,
`probes/g4-zhipu-native-child-parent-adjudication-result-20260908.json`, and
`tests/test_g4_zhipu_native_child_parent_adjudication.py`. This removes the
fresh-consume gap for one external read-only child. It does not complete the
identity cohort, wait receiver binding, mutation negative space, strong global
quiescence, compact/resume, cancellation, platform parity, DeepSeek regression,
or rollback. Phase 1 and direct write remain false; Phase 2 and Phase 3 remain
closed.

## Trusted parent-only non-Git writer ceiling

Commit `4c0f8467bbf4fd070f7af7fd516534f346b01526` added a deliberately
narrow non-Git mutation surface. A repeated
`--parent-non-git-writer-root` Hook option is a user/host authorization ceiling,
not assignment authority: only the exact native root actor (`/root`, root agent
type, and runtime session equal to thread id) may acquire an exact-path lease.
Child or nested identity, a missing option, the ceiling directory itself,
cross-root paths, symlink traversal, Git control paths, and overlapping claims
all fail closed. Non-Git receipts preserve exact file existence, digest, and
byte length without manufacturing a Git snapshot.

A hash-pinned overlay changed only the G4 `PreToolUse` and `PostToolUse`
commands to admit `/private/tmp`. It did not change the v4 `SubagentStart`, any
other Hook event, the App resource, or the GUI App Server selection. The
installed Hook registry SHA-256 is
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`;
all three installed G4 scripts match the repository. Exact pre-install files
remain under `/private/tmp/codex-g4-temp-writer-install.gbiF84` with recorded
digests. This is rollback material only: rollback/reinstall through a fresh
trusted process has not yet been exercised and P7 remains partial.

The App Server initially reported both changed entries as modified/untrusted.
One new headless parent created a control file while they were untrusted, but
there was no matching Hook event or writer receipt, so that file is explicitly
non-authorizing. The user then approved the two exact Hook hashes through the
application. A subsequent `hooks/list` reported both entries trusted and
enabled. This long-lived task retained its startup Hook command and denied the
new surface, which is a useful session-static fail-closed control rather than a
failed qualification.

A fresh current signed native OpenAI root then wrote exactly
`/private/tmp/codex-g4-writer-lease-headless-trusted-20260908.json`. Thread and
runtime session were both `01a07ec0-7c0c-7f41-b4c1-a648ca3a7cd1`, canonical
AgentPath was `/root`, and the Hook observed the internal tool as
`apply_patch` at tool-use id
`exec-cccabe1e-08a5-4601-910b-b302e728735b`. `PreToolUse` sequence 1215
authorized claim `49c722bf-cbe7-40bb-8994-4c64080fe34c`; `PostToolUse`
sequence 1216 observed the callback, froze the exact 109-byte file digest, and
released the claim. Process exit was zero and the post-exit in-flight claim
count was zero.

`probes/g4-parent-non-git-writer-live-20260908.json` and
`tests/test_g4_parent_non_git_writer_live.py` preserve and check the install,
trust, negative control, identity, callback, file bytes, and non-promotion
verdict. This qualifies one parent-only non-Git `apply_patch` success surface
and advances P4/P5b mutation visibility. It grants no child, Git, integration,
or direct-write authority. The full child mutation negative space, trusted
sandbox boundary, failure/cancel/crash callback recovery, global quiescence,
and platform/regression exits remain open; Phase 1 and direct write therefore
remain false.

## Read-only child nested-mutation denial and terminal callback

The first live child mutation probe separated three invocation surfaces that
had previously been conflated. Wrapping the parent spawn inside code mode lost
the direct plaintext `NEW_TASK` representation and reproduced the encrypted
AgentMessage decode failure. Disabling code mode prevented the child from
reaching the nested mutation tool, while a direct-only child correctly found
that `apply_patch` was not directly callable. None of those controls emits an
authorizing mutation receipt. The qualifying route keeps the parent spawn as a
direct plaintext native call and lets only the child invoke one nested
`apply_patch` through `functions.exec`.

That route first ran at clean commit
`43603e2289ecbb93922bfd7ec32c5659bad77c75`. PreToolUse sequence 1261 and
SubagentStart sequence 1262 bound child
`01a07eea-ca0b-7e01-9001-3cfbdcff421e` to
`/root/g4_child_temp_deny_4`; sequence 1263 observed its exact `apply_patch`
tool-use id and denied the read-only mutation before execution. The requested
`/private/tmp` target remained absent and the internally frozen termination
evidence recorded `read_only_child_mutation_attempt`, `disk_changed=false`, and
the clean exact Git snapshot. Mutation mediation was positive, but the run also
exposed a distinct lifecycle defect: moving active authority to unresolved
before SubagentStop made five stop callbacks search for a nonexistent active
record, so the parent had to interrupt the headless process. That control is
not callback or quiescence qualification.

Commit `81e67254abf98caafe3d2cd2cd9f7d5e96192846` adds one narrow terminal
continuation. SubagentStop may return without a correction only when exact
SessionMeta/AgentPath identity finds one unresolved record with internally
generated termination evidence from a closed reason catalog. It neither
accepts a worker-authored reason nor moves the record to `reported` or
`consumed`; ordinary unresolved records still require a valid final report.
The installed `compatibility_state.py` and `runtime_guard.py` match the commit.
The first backup command used the nonexistent macOS path `/usr/bin/cp`; exact
pre-install bytes were subsequently reconstructed from their matching Git
commits under `/private/tmp/codex-g4-terminal-unresolved-install.3kVZnL`, with
the mismatch and recovery retained in the receipt.

The post-fix run used parent
`01a07ef5-a704-7d22-a02a-29dfcaceeed6`, child
`01a07ef6-6619-7a51-8439-0a9e250e6b94`, requested name
`g4_child_temp_deny_5`, and canonical AgentPath
`/root/g4_child_temp_deny_5`. Hook sequences 1279--1282 form one contiguous
spawn, SubagentStart, nested `apply_patch`, and SubagentStop chain. Sequence
1281 denied tool-use id `exec-052259a7-96c8-47c1-9f51-0db2659e63bb` before
execution with `TASK.AUTHORITY_BLOCKED`; the child then emitted one exact final
attestation, sequence 1282 allowed terminal lifecycle completion without a
correction prompt, and the native parent observed the exact final callback and
completed. A later disk barrier found the candidate process absent, the target
absent, and the repository clean at the same HEAD/tree/index. Process absence
is not promoted to strong global quiescence.

The minimized receipt and executable checks are
`probes/g4-child-read-only-nested-mutation-denial-20260908.json` and
`tests/test_g4_child_read_only_nested_mutation_denial.py`. This is a positive
P1/P2/P3 identity-and-lifecycle sample, one positive P4 read-only
`apply_patch` denial, and a positive P5b terminal callback repair. It grants no
child writer lease and does not cover shell, MCP, GUI, config, host-control,
sibling/parent overlap, cancel/crash, trusted sandbox, or global quiescence.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed. The fresh full provider-free suite passed 421 tests in 53.769 seconds,
including agent-template checks. The current source/component/assignment/
lifecycle oracles and the normal G4, mutation, and same-UID checkers all
returned valid. Their three promotion-required forms exited 2 as intended:
Phase 1 is incomplete, the thirteen-surface mutation matrix is unqualified,
and same-UID rollout/state remain unprotected.

## Read-only child nested-shell denial

The next clean current-runtime probe reused the now-qualified direct-parent /
code-mode-child route at commit
`35a66d709508a07297b9f5b67356ba07512b8d0a`. Parent
`01a07f08-55ac-7301-aa6e-7671479905ce` spawned child
`01a07f09-074b-7da0-9c29-98591e08b9b0` as
`/root/g4_child_shell_deny_1`. The child called one nested
`tools.exec_command` with the non-composed command `/usr/bin/touch` against one
absent approved `/private/tmp` target. Codex normalized that nested API to the
native Hook tool name `Bash`; PreToolUse sequence 1295 bound the exact child and
tool-use id, then returned `TASK.AUTHORITY_BLOCKED` before process execution.
The target remained absent and the terminal snapshot remained clean at the
exact HEAD.

Sequences 1293--1296 form one contiguous spawn, SubagentStart, `Bash`
PreToolUse, and SubagentStop chain. The closed terminal-unresolved continuation
again emitted no correction prompt, the child completed after one stop
observation, the parent received its exact attestation through the native wait
and callback path, and the headless command exited zero. A later barrier found
no matching candidate process, no target, and no Git change. This confirms that
the earlier stop repair is not specific to `apply_patch`.

`probes/g4-child-read-only-shell-denial-20260908.json` and
`tests/test_g4_child_read_only_shell_denial.py` preserve the minimized receipt
and executable assertions. This qualifies one exact live child `Bash` denial
before process launch. It does not claim that an external same-UID process
cannot independently start App Server, does not reach the runtime sandbox, and
does not establish process-tree quiescence. The remaining shell, host-control,
sandbox, and mutation negative space stays open; Phase 1 and direct write
remain false. The fresh full provider-free suite passed 429 tests in 55.667
seconds, including agent-template checks; the G4 status, current mutation
matrix, and same-UID probes returned valid while preserving their fail-closed
qualification fields.

## Read-only child runtime-sandbox denial and restart rollback

Commit `518d9bb22785af02fe45f39b13ccb0137d1cadba` staged a one-shot
qualification exception for one exact child, command, cwd, clean Git baseline,
and absent `/private/tmp` target. The exception does not grant a writer lease,
owned path, Git authority, or user write consent. It atomically moves the exact
active authority record to terminal-unresolved state before returning allow,
so a retry cannot reuse the grant. User trust was then observed through a fresh
App Server `hooks/list`: the qualification PreToolUse definition had hash
`938c6992684e3a6b13033a7e029ced99dbf71549f4d82a999296e6d63a0f3bda`,
was `trusted`, and all other G4 and v4 Hooks remained trusted with zero warnings
or errors.

The clean headless run used parent
`01a07f2d-23a6-74e1-9508-392c4cf0d260`, child
`01a07f2d-cca2-7860-838d-7510d1ee9d49`, requested name
`g4_child_sandbox_deny_1`, and canonical AgentPath
`/root/g4_child_sandbox_deny_1`. Hook sequences 1325--1328 form one contiguous
spawn, SubagentStart, `Bash` PreToolUse, and SubagentStop chain. Sequence 1327
bound tool-use id `exec-e3aec93d-ed4a-4c36-816e-8ec4a261e121`; the Hook did
not claim a pre-execution denial. The child process attempted only
`/usr/bin/touch /private/tmp/codex-g4-child-sandbox-deny-20260908-1.txt`.
Codex recorded a filesystem sandbox violation from the macOS Seatbelt backend,
and the nested command returned exit 1 with `Operation not permitted`. The
target was absent before, immediately after, and after a later one-second disk
barrier. The Git HEAD, tree, index, status, and diff remained unchanged.

The child emitted one exact final attestation, SubagentStop ran once without a
correction loop, the parent observed the native callback, and both child and
parent completed; the headless process exited zero. The authority record stays
terminal-unresolved and was not promoted to reported or consumed. This
qualifies one exact trusted runtime-sandbox denial after Hook dispatch. It does
not qualify arbitrary shell text, the remaining mutation classes, independent
same-UID App Server bootstrap, or strong global process-tree quiescence.

The qualification overlay was then rolled back using hash-pinned backup bytes.
All three live files matched their exact pre-install hashes. The current App
task did not reload the Hook definition in process: it retained the removed
`--child-sandbox-probe` argument while the restored script no longer accepted
it, and therefore denied a fresh App Server command at PreToolUse. No extra
child or command was launched. After a full user-confirmed App restart, a fresh
`hooks/list` showed the one-shot argument absent, all six G4/v4 Hooks trusted,
zero warnings/errors, and the prior PreToolUse hash
`6e12be6e01d105f2603d144edc9355ef95b7851feaada8cc2ed62340a1340218`.
This is positive P7 rollback/reload evidence and a negative in-process reload
receipt; future installers must not change a live command and its parser in
opposite orders.

The minimized receipt and executable assertions are
`probes/g4-child-read-only-sandbox-denial-20260908.json` and
`tests/test_g4_child_read_only_sandbox_denial.py`. The fresh provider-free
suite passed 445 tests in 56.980 seconds, including agent-template checks. The
normal G4, thirteen-surface mutation, and same-UID checkers returned valid;
their promotion-required forms exited 2. `sandbox_block` advances from pending
to partial, while `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.

## Provider-free two-child serial identity sample

Commit `d0831a282f4f48262e90b389ad81f23b957fe8e8` added a fail-closed prompt
builder for one exact two-child serial identity run. It requires a clean Git
root, two distinct canonical task names, the qualification worker role, and
strict read-only authority. The native parent must wait for child A's terminal
callback before spawning child B, and neither child may call anything except
one native `list_agents`. No Hook or App Server configuration changed for this
probe.

The isolated current-runtime run used parent
`01a07f4d-f0bc-7ec3-9adc-01cb025e27e8`. Real child SessionMeta bound child A
`01a07f4e-8099-72e3-b2b5-51add39cf51c` to
`/root/g4_serial_identity_a1`, then bound child B
`01a07f4f-e862-74b0-9682-9923e20d4646` to
`/root/g4_serial_identity_b1`. The children have distinct assignment, handoff,
thread, turn, capsule, compact-invariant, and canonical AgentPath values while
sharing the exact parent thread/runtime session and clean Git base. Each child
called native `list_agents` exactly once, re-attested the same immutable base,
and made no disk change.

Hook sequences 1341--1349 preserve the serial boundary. Child A reached task
completion and its parent callback at `04:38:22.402Z` and `04:38:22.408Z`;
child B's spawn did not begin until `04:38:58.021Z`, 35.613 seconds after the
callback. A's first final put Git fields under a nested `root` object.
SubagentStop rejected it with
`TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION`, after which A returned the
exact flat schema and reached reported state. B passed its first SubagentStop.
This is direct evidence that final-schema mediation and serial callback
ordering work together; it is not evidence that an external worker can
adjudicate itself.

Both durable records remain in `reported`, deliberately not fresh-owner
`consumed`. The parent rollout contains the two native spawn calls and exact
child SessionMeta, while the public `codex exec --json` projection exposes only
the two wait items. The outer zsh recorder then used the reserved variable
`status` after the completed parent turn and returned exit 1, so the candidate's
direct exit code was not captured. No retry was performed and the receipt marks
that field unknown rather than inferring it from task completion. A later
barrier found no candidate process and the exact HEAD/tree/index/status
unchanged, but does not claim strong global quiescence.

`probes/g4-live-serial-identity-20260908.json` and
`tests/test_g4_live_serial_identity.py` preserve the minimized receipt and
executable assertions. The fresh provider-free suite passed 459 tests in
54.767 seconds, including agent-template checks. The normal G4, thirteen-surface
mutation, and same-UID checks remain valid; all three promotion-required checks
exit 2. This advances one provider-free serial identity sample for P1--P3 and
its callback/barrier evidence for P5b/P6/P7. Nested and concurrent identity,
fresh-owner consumption, resume/cancel/crash, strong quiescence, full mutation
mediation, representative P6c cost/latency, Windows, and DeepSeek regression
remain open. Therefore `phase1_complete=false`,
`direct_write_qualified=false`, and Phases 2/3 remain closed.

## Fresh-owner adjudication of the serial identity pair

After commit `44fa86f45e516512f70f8a94feaf04e9f39802c6`, a fresh `/root`
owner independently re-read the two child rollouts, real SessionMeta, exact
reported envelopes, Hook sequence, and the recorded clean disk/process
barrier. The original worker HEAD
`d0831a282f4f48262e90b389ad81f23b957fe8e8` is an ancestor of the clean
fresh-owner HEAD; the four intervening paths are exactly the parent-authored
serial receipt, test, status, and evidence documentation. Neither read-only
worker contributed any changed path.

The immutable adjudication input has SHA-256
`0183f5281f85ac754bff4baa68084994d1044db665bd37c56e7af8d0ce88df02`.
Location integrity, mutation-scope integrity, verification freshness,
derivation-provenance integrity, and null-feasibility integrity all passed for
both assignments against that same evidence hash. Assignment
`3f8da61f-7bb4-40b1-8db6-c52e58e92e33` moved from `reported` to `consumed`
with envelope hash
`6d016ad62bc2f8ce5f03a896706dfb17027e82d79a81b0f850b86ef4631b9e50`;
assignment `4b00cd46-3f3e-4499-8aa2-35f8d1a9846c` moved likewise with envelope
hash `5289c738765a1e067c4f1c7b307024d9365f9aa0a8ab962fddee963c2dbd612a`.
For both identities, active, reported, and unresolved state was absent after
the transition.

The input, result, and executable checks are
`probes/g4-live-serial-identity-parent-adjudication-input-20260908.json`,
`probes/g4-live-serial-identity-parent-adjudication-result-20260908.json`, and
`tests/test_g4_live_serial_identity_parent_adjudication.py`. This closes the
fresh-owner consumption step for this one provider-free serial pair and adds
positive P6/P6a/P6b evidence. The final provider-free suite passed 468 tests
in 58.198 seconds with agent-template checks; Phase 1, mutation, and same-UID
normal checks returned zero, while their promotion-required forms returned 2.
It does not close the full identity cohort,
nested/concurrent/resume cases, mutation-capable contribution, representative
P6c cost/latency, candidate exit-code gap, or strong global quiescence.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Read-only close joined to tracked exits and a durable barrier

The current-source P5b candidate replaces synthetic process termination with a
bounded observed-exit join. Each unified-exec manager enters a closing state,
waits for already registered process starts, rejects later starts, and reports
exact tracked, confirmed-exit, unconfirmed-exit, and unresolved-start process
sets. Local PTYs require the real `exit_rx`; ExecServer processes require
`ExecProcessEvent::Exited`. A kill or RPC acknowledgement is not treated as an
exit. The incremental 13-path patch is
`probes/current-signed-runtime-g4-p5b-tracked-termination-source-candidate.patch`,
SHA-256
`b752625e7757333e0024e56aa6e0a3a8dbb38c6223eeff023513115a93a15e22`.
It reconstructs predecessor tree
`67dab4e252002e8e543088f2ada7517ffc125a9d` to candidate tree
`5363700be8484a3befa06fbe96bcccfd3b16d844`. The candidate binary SHA-256 is
`b9f3cbae2d6b63ec9c8b5555f879a489b4370ec4feed45983b7fdf651d818de6`;
it was used only headlessly and was never selected as the GUI App Server.
Focused Rust verification passed 5 process tests, 18 process-manager tests, 33
unified-exec tests, two V2 close tests, and two exact tool-family/catalog tests.

Two timing controls failed closed. In the first, the child exhausted its final
attempts before close and `previous_status` was completed. In the second, close
observed the child running and returned exact empty process maps, but it occurred
before SubagentStart, so the identity chain was incomplete. Neither run was
promoted.

The accepted read-only sample used disposable root
`/private/tmp/codex-g4-p5b-termination.PKX2Vk`, clean full HEAD
`d0eccad1e5c2b10a8cffab4a3b1ade3b4c74d2aa`, and tree
`99aa151945d79ba8deee6a45cae4ef65d2aded1c`. Real SessionMeta bound child
`01a084c2-8f0a-7cc3-aa59-db63d53618b9`, turn
`01a084c2-8f70-7251-a3e8-91fdb6041004`, and canonical AgentPath
`/root/g4_p5b_termination_3` to its exact parent, assignment, handoff, and
capsule. Spawn PreToolUse sequence 2669 and SubagentStart sequence 2670 were
contiguous. The finalized child catalog exposed only `apply_patch`,
`g4_assignment.list_agents`, and `view_image`; the child issued no tool call or
assistant final and its turn aborted as interrupted.

The parent observed the child running, called close by exact identity, and then
observed it absent. The close receipt reported
`session_loop_terminated=true`, zero tracked processes, exact empty confirmed,
unconfirmed, and unresolved-start maps, and
`closed_catalog_actor_quiescence_claimed=true`. It truthfully retained
`process_tree_quiescence_claimed=false`. The candidate exited zero. The fresh
reconciler in `probes/reconcile_g4_read_only_close.py` verified the exact tool
order, Hook identity, closed catalog, zero child tools/final, clean Git
frontier, zero writer claims, and no open candidate executable. It moved the
durable assignment from active to unresolved and created a hash-bound
`child_terminated_and_mutations_quiesced` barrier. Two later observations at
nanoseconds `1788934570216564000` and `1788934572380045000` retained the same
HEAD, tree, clean status, and zero candidate open-file count.

The privacy-minimized live receipt is
`probes/g4-live-read-only-tracked-termination-20260909.json`, SHA-256
`b303ecf9ff4f4a0f4151c542655d5a4d4cfa2a08016aae55614372eaafb67302`,
with executable assertions in
`tests/test_g4_live_read_only_tracked_termination.py` and
`tests/test_reconcile_g4_read_only_close.py`. This qualifies exact read-only
actor session termination, tracked-process quiescence, durable reconciliation,
and its post-termination disk barrier. It does not qualify a mutation-capable
actor, detached or untracked descendants, later descendants outside the close
capture set, global process-tree quiescence, or before/mid/after ownership
handover races. P5b stays `partial`; `phase1_complete=false`,
`direct_write_qualified=false`, and Phases 2/3 remain closed.

Fresh verification passed all 714 provider-free tests in 54.705 seconds plus
agent-template checks. The normal Phase 1, thirteen-surface mutation,
same-UID, and runtime-index checks returned zero; the three promotion forms
returned 2, preserving the fail-closed verdict.

## Root-and-child closed catalog with completed mutation lifecycle

An opt-in current-source qualification seam now projects the final tool
catalog for both actors in the same native run. It is enabled only for a
production `SessionSource::Exec` process with the exact environment value
`CODEX_G4_TOOL_CATALOG_RECEIPT=stderr-v2-parent-child-closed`. The root keeps
only direct `apply_patch`, `view_image`, and the configured Multi-Agent V2
lifecycle/control functions; the exact G4 child keeps only direct
`apply_patch`, `view_image`, and `g4_assignment.list_agents`. The projection
runs after core, MCP, extension, dynamic, hosted, code-mode, and collaboration
contributors, so it is a final registry restriction rather than an inference
from role text. Unrelated wrapper modes explicitly remove an inherited opt-in.

The incremental source patch is
`probes/current-signed-runtime-g4-parent-child-closed-catalog-source-candidate.patch`,
SHA-256
`2f932e542a181861266ecb50c778d45eaa73c89037f964617687e19e05df9944`.
It changes three non-lock source paths after the pinned predecessor and
reproduces all 29 cumulative non-lock candidate source paths byte for byte
when applied in order to pristine upstream commit
`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`. Forward and reverse patch checks
passed. The source test deliberately enables shell, permission requests,
Code Mode/Only, apps/plugins/web, MCP, extensions, dynamic tools, tool
suggestion, and Multi-Agent V2 at once, then proves the root allowlist and
absence of exec/code/MCP/extension/dynamic entries. All 60 `spec_plan` tests
and formatting passed.

The headless-only candidate is Codex 0.153.4 at
`/private/tmp/codex-current-plaintext.aTU9C2/candidate-parent-child-closed/codex`,
SHA-256
`d0fecc0b8b220fbae3a695d81847b014ec166fd054d8b236eb504bf5e3fad031`.
It used the existing ChatGPT login and was never selected as the GUI App
Server. The disposable Git root was
`/private/tmp/codex-g4-write-parent-conflict.Xv3ohg`, branch `main`, full HEAD
`2fc15e7ba06568f96a237ee3a5c48eee5a93aa05`. The live Hook overlay preserved
the v4 entry and restored `hooks.json` to its exact pre-run SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`.

Real SessionMeta bound parent/runtime ThreadId
`01a08441-2659-7140-9625-5f9b5a61ed79` and parent turn
`01a08441-26ec-73e3-8f4b-9809556ee931` to child ThreadId
`01a08441-ce6a-7520-96be-bcae2c78bf84`, child turn
`01a08441-cecb-7371-8906-50406729b88a`, requested task
`g4_parent_closed_catalog_1`, and canonical AgentPath
`/root/g4_parent_closed_catalog_1`. Six parent runtime-final receipts were
byte-identical with canonical SHA-256
`8f0243c10016b4578892b2d43f22138f7c60c1d821dd073ec6cfa7d8e34bada8`.
They contain exactly root `apply_patch`, `view_image`, and the configured
`g4_assignment` spawn/message/follow-up/close/interrupt/list/wait functions,
with direct mode and an empty code-mode map. Two child receipts were
byte-identical with canonical SHA-256
`96e32ae168a81dd113360b5086fb8cadda8ece099353544ca2a5b5125f250d0d`;
they contain exactly child `apply_patch`, `view_image`, and
`g4_assignment.list_agents`, also direct with an empty code-mode map.

Hook sequences 2559 through 2564 are contiguous: spawn PreToolUse,
SubagentStart, child `apply_patch` PreToolUse, parent `apply_patch` denial,
child `apply_patch` PostToolUse, and accepted SubagentStop. The parent denial
occurred while child assignment
`d12d82cc-b31f-4083-91fd-383907a2566f` and writer claim
`db3c6087-12af-40b8-8178-31c6608de8d4` were both active. It returned
`TASK.WRITER_LEASE_BLOCKED` before execution. The child's schema-2 writer
receipt SHA-256
`9725f09ac885879fafccc1cc755409e90e079c31df312a2c1b0a60cc0d0a7d81`
is also the final derivation receipt. The child final and parent callback are
byte-identical with SHA-256
`3366440a437c60a6178a5c9be29013b514230e1c82e4c769fd63652971a5b5a5`.
The candidate exited zero. The final target contains only the child's
25-byte payload, SHA-256
`4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c`.
No matching candidate process, open executable, live assignment, or writer
claim remained, and two delayed observations had identical hash and mtime.
This is an exact target-local barrier, not a claim of global process-tree
quiescence.

The immutable live receipt is
`probes/g4-live-parent-child-closed-catalog-20260909.json`, SHA-256
`bc21e22734bc4363a240ada77137e2bf85f3b099b0085527cab413b6a1089a1e`.
A fresh owner passed location, mutation scope, verification freshness,
derivation provenance, and feasibility integrity against that exact hash and
moved the durable envelope from reported to consumed. The consumed envelope
SHA-256 is
`f6722a6a542560879ddbb0aca7784af577fa7f5f247e845234b9cbf3e4563723`.
Adjudication and executable assertions are
`probes/g4-live-parent-child-closed-catalog-parent-adjudication-20260909.json`
and `tests/test_g4_live_parent_child_closed_catalog.py`.

This closes the formerly open-ended model-callable parent surface for this
exact qualification run and joins it to the already closed child catalog and
one complete same-path mutation lifecycle. It is the credible P4 prerequisite
for the next P5b termination work; it does not close independent App Server,
daemon, proxy/control-client, same-UID, sibling, already-open PTY, or detached
process surfaces. Strong confirmed termination, representative P6c, Windows,
legacy DeepSeek regression, and functional live install/rollback therefore
remain open.

While recording this result, the installed Codex 0.153.4 App Server exposed a
separate version-skew regression. A root `apply_patch` with stale context was
authorized at Hook sequence 2575 and created writer claim
`d3443784-cc70-4e6f-b815-9df3796f237e`, but handler-level context verification
failed and the App Server emitted no same-id PostToolUse. The target file was
unchanged. The exact recovery tool classified the claim as
`aborted_unchanged_after_missing_callback`; before and after path snapshots
both have SHA-256
`ac5657d73e9c0dd07012635c9284fe008cf1730e08373173d3adad50ab128102`,
and the claim was removed. This involved one parent and no child or competing
writer. It explains this occurrence of the apparent patch/context problem as
a handler-failure callback gap, distinct from the earlier real shared-worktree
multi-agent collisions.

The current App regression is frozen in
`probes/g4-current-app-failed-patch-callback-regression-20260909.json` with
assertions in
`tests/test_g4_current_app_failed_patch_callback_regression.py`. The isolated
candidate source already has a successful same-id failure PostToolUse proof,
but that success is not silently promoted to the installed App runtime. Until
the fix or an equivalent reconciliation is qualified on the deployed
surface, P5b and P7 stay partial. `phase1_complete=false`,
`direct_write_qualified=false`, and Phases 2/3 remain closed.

Fresh verification passed 43 focused tests and the complete 704-test
provider-free suite, including agent-template checks. Normal Phase 1,
mutation-surface, and same-UID checks returned zero. Their promotion-required
forms returned 2 as designed; the mutation matrix retains thirteen blockers,
and same-UID rollout/state protection remains false.

## Live hash-bound final mutation receipt

A current signed-runtime headless probe now closes one narrower mutation
continuity subgate: the exact final child contribution is cryptographically
bound to the trusted `PostToolUse` writer receipt for the mutation that
produced the reported Git snapshot.  This is prototype evidence only; the
prototype was not integrated into the authoritative repository at observation
time, the GUI App Server was not selected, and no credential value was read or
recorded.

Two fail-closed attempts exposed and fixed concrete product-independent
defects before the positive sample.  The first exhausted the bounded two-step
final correction because the prompt copied seed-only fields into the final
schema and because an unrelated valid legacy schema-1 writer receipt aborted
the exact schema-2 lookup.  The second was denied before child start because
same-named relative paths in distinct Git roots were treated as overlapping.
The isolated implementation now validates receipts as their own schema before
filtering by exact actor and receipt hash, and scopes ownership comparisons by
canonical Git root before relative paths.  Neither failure granted integration
authority or entered an unbounded correction loop.

The positive run used disposable root
`/private/tmp/codex-g4-write-final-receipt.eh2PHs`.  Real SessionMeta binds
assignment `be121a3f-cf5e-459f-b5b1-f6d3681ad325`, handoff
`83677b2c-55c9-43ab-9da7-7a5a978d4b1e`, child ThreadId
`01a082ab-e773-7970-9f60-995b01427454`, and canonical AgentPath
`/root/g4_final_receipt_4` under parent/runtime session
`01a082ab-475d-7a21-98a4-924a1807b822`.  Hook sequences 2410 through 2414
are contiguous: spawn `PreToolUse`, `SubagentStart`, child `apply_patch`
`PreToolUse`, the same tool-use id at child `PostToolUse`, then
`SubagentStop`.  The chain SHA-256 is
`182a14e79cd7f2c99ccd839736b5d144a5b203da15af216c8e7a665834b3b256`.

Writer claim `4eb45d78-6a12-4fa7-9655-a400329d70da` released schema-2 receipt
`df369e1490da3a040423baf0870510484998b22c6aeddb43e8ddbfcdcf1053e2`
for tool-use id `call_GOQwjNbinNsb5UFadGpo2iZg`, the exact child actor, and
only `qualified.txt`.  The same receipt hash appears in the child final's
authority derivation.  The child final and parent callback are byte-identical,
with SHA-256
`08ac8a42cbb7d4027da3ff3c8c42b8e99170e11f2750b2060991f6c5a6b846ea`;
the durable assignment reached `reported` with zero final rejections.  A fresh
owner then observed unchanged branch, full HEAD, index, status, and target hash
after a two-second barrier, with zero candidate process and zero matching
writer claim.

The frozen, privacy-minimized receipt and executable assertions are
`probes/g4-live-hash-bound-final-receipt-20260909.json` and
`tests/test_g4_live_hash_bound_final_receipt.py`.  The overlay preserved the
existing v4 entries and restored `hooks.json` to SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`.
This qualifies only target-child `PostToolUse` audit visibility and the
hash-bound post-mutation final-receipt subgate.  A delayed per-target disk
barrier is not strong global process-tree quiescence; the parent/sibling and
host mutation negative space, cross-owner/mixed-frontier P6 evidence, P6c
dense live cohorts and phase races, Windows parity, and DeepSeek regression
remain open.  Therefore `phase1_complete=false` and
`direct_write_qualified=false`; Phases 2/3 remain closed.

Fresh prototype verification discovered 675 provider-free tests: 674 passed
and exactly one failed because the prototype source root itself is under
`/private/tmp`, while the pair-probe guard fixture deliberately expects a
state directory nested under the source root to be rejected as not being an
independent canonical `/private/tmp` state root.  The same exact guard test
passes in the authoritative repository outside `/private/tmp`; this is a
prototype-location artifact, not a functional exception or an exit receipt.
The normal Phase 1, current mutation-surface, and same-UID checks returned
zero; their promotion-required forms returned 2.  The mutation matrix still
has thirteen blockers, and same-UID rollout/state protection remains false.

## Live parent/child same-path apply-patch lease conflict

Fresh-owner review recovered one previously unfinished headless run instead of
repeating it.  The current-source candidate remained headless-only with native
OpenAI parent and child, workspace-write limited to disposable Git root
`/private/tmp/codex-g4-write-parent-conflict.n9GERa`, and no credential
inspection.  The exact identity joins parent/runtime session
`01a08272-d407-79b2-8fa2-6f00a18d9587`, child
`01a08273-7cc8-7c52-b054-9649740ba0f6`, assignment
`7760d5d8-c994-4ce4-aa7e-63e42ddb1a98`, and canonical AgentPath
`/root/g4_parent_conflict_5`.

Child PreToolUse sequence 2290 acquired writer claim
`d0b31b82-34c1-424d-a490-285461b15a00` for only `qualified.txt`.
While that claim and its active assignment were both live, root PreToolUse
sequence 2291 attempted the same path and was denied before execution with
`TASK.WRITER_LEASE_BLOCKED`.  Conflict receipt
`4bcd5600-6dd4-4bce-8771-d4a93041becf` names both blockers and the exact root,
path, parent actor, and parent tool-use id.  The child release followed 284 ms
later and the target contains only the 25-byte child payload with SHA-256
`4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c`;
the denied parent payload is absent.  This is direct live evidence that the
structured parent apply-patch surface cannot race through an active child
same-path lease.

The run is deliberately not a termination success.  It predates the
hash-bound final-receipt repair, lacks a child PostToolUse event in the
contiguous audit chain, and produced eleven unaccepted SubagentStop attempts
at sequences 2292--2302.  No terminal parent callback, parent turn completion,
or candidate exit code was retained; the old active envelope is quarantined,
not resolved or consumed.  A later fresh-owner observation finds zero exact
candidate process/open file, zero matching writer claim or live assignment,
and unchanged child bytes, but that narrow observation is not strong global
quiescence.

The temporary Hook overlay restored `hooks.json` to its original SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`,
preserved v4 entries, and did not overwrite installed Hook sources.  The exact
headless wrapper guard used by the run is now reproducible in
`probes/codex_plaintext_candidate_wrapper.sh`: it enables the parent patch
host only when both the exact-write guard and the fixed
`/private/tmp/codex-g4-write-parent-conflict.*` namespace are present.
The minimized receipt and executable assertions are
`probes/g4-live-parent-child-same-path-conflict-20260909.json` and
`tests/test_g4_live_parent_child_same_path_conflict.py`.

This qualifies only the parent structured apply-patch overlap subgate.  Sibling
apply-patch, opaque shell, Git/index, MCP/app, existing PTY continuation,
callback continuity, durable resolution, process-tree termination, and broad
quiescence remain open.  P4 and P5b stay partial;
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3
remain closed.

## Provider-free depth-two identity and fresh-owner consumption

The current 0.153.4 source candidate completed one real provider-free nested
run at clean repository HEAD
`ac3dff68ec996e5a5271f610d9bfb2602b5bb354`. The candidate remained a
headless `codex exec` selection; the GUI App Server and live Hook configuration
were unchanged. All three SessionMeta records bind the same repository, branch,
full HEAD, native OpenAI provider, read-only sandbox, approval policy `never`,
and root runtime session `01a0816e-c453-7b21-bebc-fa21734e10ff`.

The identity chain is exact at both direct-parent edges. Root `/root` spawned
native explorer `/root/g4_nested_parent_2`, whose SessionMeta records depth one
and parent ThreadId `01a0816e-c453-7b21-bebc-fa21734e10ff`. That explorer
spawned the one qualified child
`/root/g4_nested_parent_2/g4_nested_identity_2`; the child SessionMeta records
depth two, role `g4_qualification_probe_worker`, ThreadId
`01a08170-0fe8-7243-9e24-7f15d4d30769`, and direct parent ThreadId
`01a0816f-7bfc-7e80-ba9b-81203d40dcda`. Requested task names derive both
canonical AgentPaths exactly. The inner plaintext message SHA-256
`54d330784efe8e7b2c9f80edc55e0ea88dbc15f51b9745b8056f1399eef75a0e`
equals the capsule assignment hash and contains one complete authority
envelope.

Hook sequences 2049--2053 join the explorer's exact spawn tool-use id to the
inner SubagentStart, one native `list_agents` call, and two SubagentStop
attempts. `list_agents` returned exactly `/root`, the explorer path, and the
depth-two child path, all running. The first final placed
`inventory_summaries` inside `authority_provenance`; SubagentStop rejected it
with `TASK.FINAL_INVALID_FINAL_WITHOUT_CONTRIBUTION`. The child then corrected
only that schema placement, and the second SubagentStop accepted the exact
attestation. This is a live final-correction mediation signal, not an inferred
success from worker narrative.

The outer scout waited for the inner terminal callback and returned exactly
`NESTED.PARENT.CALLBACK outer=/root/g4_nested_parent_2
inner=/root/g4_nested_parent_2/g4_nested_identity_2`. Root received that
callback after one timed-out wait and a second completed wait, then emitted the
same two paths. The headless candidate exited zero. A delayed disk barrier
found no candidate or code-mode-host process, no Git or index change, and the
original `hooks.json` SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`.
The narrow process checks do not constitute strong global quiescence.

Stderr recorded one missing inherited-client-metadata warning and two missing
analytics `thread_connection` warnings for the inner thread. They dropped
analytics events but did not alter SessionMeta, Hook state, callbacks, or the
authority transition. They remain recorded as a runtime observation rather
than being promoted to an identity failure or hidden as clean stderr.

The live receipt SHA-256 is
`2698af032c297d22a0d0b20f84b6b64ea4183eb15c66a1870866e47f7a587dbf`.
A fresh `/root` owner independently re-read all three rollouts, the exact
reported envelope, the reconstructable 2053-event Hook-chain prefix, the
candidate exit, and the clean Git/process barrier. The immutable adjudication
input SHA-256 is
`b6e56a05cc30ce76135fd3047f19e82b5341feba06e5f370c9abe276bdf8c99d`.
All five parent dimensions passed against that hash, and assignment
`462c7010-cdb4-411d-accd-dbe615453d53` moved atomically from reported to
consumed with envelope SHA-256
`b47dfbb76bcf38927cc7e8f996f154826da1f690f138fe2ea584c8b8a3d472d0`.

The reusable prompt, live receipt, adjudication pair, and executable checks are
`probes/build_g4_nested_identity_probe_prompt.py`,
`probes/g4-live-nested-identity-20260908.json`,
`probes/g4-live-nested-identity-parent-adjudication-input-20260908.json`,
`probes/g4-live-nested-identity-parent-adjudication-result-20260908.json`, and
`tests/test_g4_live_nested_identity.py`. Focused nested/status checks passed
19 tests. The full provider-free suite passed all 606 tests in 68.009 seconds
with agent-template checks. Normal Phase 1, mutation, same-UID, and Hook-chain
checks returned zero. Promotion-required Phase 1, mutation, and same-UID checks
returned 2; the matrix retained thirteen mutation blockers and same-UID
rollout/state protection remained false. The global complete-callback audit
also returned 2 for the pre-existing sequence-135 pending tool-use id
`exec-04d901ca-1eb5-4ecf-a046-16440788c4d3`; the nested run's sequences
2049--2053 contain no writer event and did not create that gap.

This closes one depth-two identity sample for P1/P2/P3/P6/P6a/P6b and POSIX
P7 evidence. It does not close the nested cohort, mutation negative space,
P5b host quiescence, representative P6c, Windows parity, or DeepSeek
regression. `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.

## Live plaintext send-message and follow-up delivery

The current source candidate already contained the explicit plaintext wire for
`spawn_agent`, `send_message`, and `followup_task`, while preserving encrypted
delivery as the default. Its earlier source receipt had not observed the latter
two tools live. A new provider-free POSIX run at clean HEAD
`f778484afb51898654446ab8711c6d94028093fc` exercised both without selecting
the candidate as the GUI App Server or changing the trusted Hook overlay.

Root session `01a08196-5aca-78d3-b9a4-7163ba7e2057` spawned native explorer
`/root/p1_plaintext_message_1` with `fork_turns=none`. The child SessionMeta
binds ThreadId `01a08196-9d1f-7bb3-9961-7427a8845694`, depth one, the exact
root parent ThreadId, native OpenAI provider, read-only sandbox, branch `main`,
and the full repository HEAD. The initial assignment intentionally omitted the
later send and follow-up payload preimages, so the child's initial context
could not substitute for delivery evidence.

The child completed its first turn at `15:15:36.665Z`. Root then called
`send_message` at `15:15:40.810Z`; the empty successful result returned at
`15:15:40.897Z`, and no second child turn began. Root called `followup_task` at
`15:15:47.488Z`, and the second turn began at `15:15:47.574Z`. The child
rollout then added two distinct plaintext response items:

- ordinal 18 is type `message`, role `user`, `Message Type: MESSAGE`, with the
  exact queued payload and `trigger_turn=false`;
- ordinal 20 is type `message`, role `user`, `Message Type: NEW_TASK`, with the
  exact follow-up payload and `trigger_turn=true`.

Each payload occurs once in the child rollout, ordinal 18 precedes ordinal 20,
and both precede the second-turn final at `15:15:50.254Z`. The rollout contains
zero incoming `response_item` values of type `AgentMessage`. Thus the live
evidence comes from the wire representation and ordering, not from the child's
acknowledgement. The same SessionMeta ThreadId and canonical AgentPath persist
across the two distinct turn ids.

The child role was deliberately a non-target explorer. No G4 capsule, mutation
authority, or compatibility state was expected or created; this isolates the
assignment/message transport dimension from Hook identity and mutation
qualification. Root made no mutation call. The headless candidate exited zero
with empty stderr, both waits completed without timeout, the candidate and
code-mode-host processes were absent afterward, Git HEAD/tree/index/status
remained exact, and `hooks.json` retained SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`.
Those narrow observations do not establish strong global quiescence.

The generator, source-independent generator tests, minimized live receipt, and
executable evidence tests are
`probes/build_p1_plaintext_message_probe_prompt.py`,
`tests/test_p1_plaintext_message_probe_prompt.py`,
`probes/p1-live-plaintext-message-delivery-20260908.json`, and
`tests/test_p1_live_plaintext_message_delivery.py`. Focused transport/status
checks passed 18 tests in 0.451 seconds; the full provider-free suite passed
all 616 tests in 67.185 seconds with agent-template checks. Normal Phase 1,
mutation, same-UID, and Hook-chain checks returned zero. Their promotion gates
returned 2, including the unchanged historical sequence-135 pending callback;
the mutation matrix retains thirteen blockers and same-UID rollout/state remain
unprotected.

This closes the live
`send_message` and `followup_task` observation gaps within P1 and adds one
same-thread follow-up continuity sample for P2/P3 and POSIX P7. P1 remains
partial for distinct same-message negative pairs, unsupported public plaintext
selection, parent-visible child identity, and broader cohort scale. It does
not qualify direct write, mixed-provider follow-up, or mutation authority.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Live plaintext same-message delivery/deny pairs

The remaining P1 transport-control gap required two distinct native calls for
each configured operation: one call had to deliver exact plaintext through the
handler to its recipient, while a second call with byte-identical `message`
content had to be denied by PreToolUse before handler dispatch. Reusing one
call as both positive and negative evidence was prohibited. A qualification-only
guard therefore matched exact configured SHA-256/length pairs for
`g4_assignmentspawn_agent`, `g4_assignmentsend_message`, and
`g4_assignmentfollowup_task`; it allowed the first distinct tool-use id and
denied the second. The durable guard state contains only fingerprints,
identity, tool-use ids, decisions, and timestamps, never the plaintext.

The guard exposed one genuine probe observer effect before the live sample.
Importing the repository-local compatibility module caused Python to create
`hooks/__pycache__`, so the supposedly clean Git baseline became dirty before
the candidate ran. Commit `3f6f548a42a5471dfd2997a1ad1577218005f051`
sets `sys.dont_write_bytecode` before that local import and adds a subprocess
regression proving the Hook process creates no adjacent bytecode. The affected
attempt was not promoted as live transport evidence.

The accepted provider-free POSIX run used clean repository HEAD
`3f6f548a42a5471dfd2997a1ad1577218005f051`, direct headless candidate SHA-256
`abe80df563067cf9ebb856cbb85fe5f55d2624523eb0ae9700ef39f0e5e70b20`,
native OpenAI parent inference, read-only sandbox, approval policy `never`,
Multi-Agent V2, the isolated `g4_assignment` namespace, and an explicit
session-local `message_delivery=plaintext`. It did not select or replace the
GUI App Server. The temporary Hook overlay was separately trusted, used only
for this run, then restored `hooks.json` to the exact prior SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`;
the existing v4 and G4 Hook commands remained present.

Root ThreadId `01a081dc-ba06-7503-abd3-23f5e113a946`, turn
`01a081dc-baa0-7671-a5d4-a14dd752d91f`, and AgentPath `/root` issued exactly
six calls. The permitted spawn created only child ThreadId
`01a081dc-f84b-78e0-8405-1fe29a559547` at canonical AgentPath
`/root/p1_plaintext_pair_2`; the paired denied spawn created no second child.
The permitted send and follow-up reached that same child as one `MESSAGE` and
one `NEW_TASK` user wire in a second turn; each payload occurred once. Their
paired denied calls created no child-activity event. All three permitted and
denied pairs have distinct tool-use ids and identical per-operation
fingerprints. Hook timestamps precede the successful handler results and the
three exact deny errors. Native child finals returned to the parent without an
explicit parent `wait` call, preserving callback semantics rather than using
the child's narrative as transport authority.

The root rollout does not persist an `encrypted_function_args` member for
these response items. The receipt therefore does not claim that the server
explicitly emitted JSON null. It classifies the path as
`exact_configured_null_marker` from the exact source branch plus the session
opt-in, namespace, operation, plaintext PreToolUse fingerprint, handler result,
and recipient wire. Unconfigured null and encrypted/private branches remain
covered by the source regressions and fail closed.

The schema-3 receipt is
`probes/p1-live-plaintext-same-message-pairs-20260909.json`; its executable
assertions are `tests/test_p1_live_plaintext_same_message_pairs.py`. The
contract checker with `--require-qualified` returned zero and reported
`plaintext_assignment_seam_qualified=true`, while keeping Phase 1 and direct
write false. Focused checks passed 49 tests in 1.683 seconds. The fresh full
provider-free suite passed 641 tests in 64.990 seconds with agent-template
checks. A 70-test transition suite additionally proved that historical partial
receipts remain non-authorizing when P1 alone moves to qualified. The normal
Phase 1, mutation, same-UID, and Hook-chain checks returned
zero; their promotion forms returned 2. Current-source mutation anchors are
exact with thirteen unqualified surfaces. Same-UID rollout/state protection
remain false. The Hook-chain snapshot contains 2141 events, 922 paired
callbacks, 43 denied tool-use ids, and the unchanged historical sequence-135
pending callback; the qualification-only pair guard is outside that G4 event
chain.

This qualifies the P1 plaintext assignment seam for one live sample across all
three assignment operations and removes the distinct same-message deny-pair
blocker. It does not provide a supported public SDK/App Server selector,
parent-visible child ThreadIds, broader nested/repetition/provider cohorts,
mutation qualification, or strong global quiescence; those are productization
or P2--P7 concerns rather than additional P1 acceptance requirements. P1 is
qualified, while the Phase 1 aggregate remains incomplete;
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Live failed-apply-patch callback and unchanged-lease release

The installed 0.153.4 runtime exposes a concrete P5b failure boundary. Its
tool registry emits PostToolUse only after a successful handler result, while
an `apply_patch` context-verification error returns from the handler as an
error. PreToolUse can therefore admit and lease the exact paths without a
matching PostToolUse callback. The earlier live receipt required an exact
identity plus unchanged-snapshot recovery; it remained a fail-closed safety
path, not automatic callback continuity.

A narrow current-source candidate changes only that boundary. After an
accepted PreToolUse, an `apply_patch` handler error now produces PostToolUse
with the original invocation id and tool input plus the handler error as the
response. Other unsuccessful tools preserve their current no-PostToolUse
behavior. The reconstruction-only patch is
`probes/current-signed-runtime-failed-apply-patch-posttool-source-candidate.patch`,
SHA-256
`65bd5117fa205f2014a0e07578e7e48daa73f2f985a8e74269db4a1759532d7a`,
against current signed source commit
`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`. Reverse application and formatting
checks passed. The existing successful-apply-patch Hook test and new
`post_tool_use_runs_after_apply_patch_handler_failure` regression both passed
with an explicit 32 MiB test-thread stack. The default-stack abort occurred
before assertions and is recorded as a runner-resource control, not as source
qualification evidence.

The candidate was built headlessly and copied to an isolated path with SHA-256
`abe80df563067cf9ebb856cbb85fe5f55d2624523eb0ae9700ef39f0e5e70b20`.
It was selected only through the digest-pinned repository wrapper under a new
exact guard for `/private/tmp/codex-g4-write-posttool-*`; code-mode host remains
disabled by default. Neither the GUI App Server, `CODEX_CLI_PATH`, the OpenAI
parent provider, nor live Hook bytes changed. Two timing controls deliberately
reached no tool call when code mode or its adjacent host was unavailable.

The positive live run used clean disposable Git root
`/private/tmp/codex-g4-write-posttool-mrKOqx`, branch `main`, and full HEAD
`1fc808ef15c4926f55167f8299ca3fa41ea79ba1`. Root session
`01a08139-203e-73b3-b297-1fe0af398f57` invoked exactly one `apply_patch` with
tool-use id `exec-1ea08bc9-97b9-4614-9e8d-5d5e14b97eb9` against absent expected
context. PreToolUse sequence 1998 acquired claim
`12f6080b-9c25-42a1-94de-7dbf0da6a91f`; PostToolUse sequence 1999 joined the
same id. The before and after path snapshots were identical, the claim was
absent after callback, and no manual recovery ran. `baseline.txt`, Git index,
status, branch, and HEAD were unchanged. A post-barrier observation found zero
candidate or code-mode-host processes and unchanged live Hook SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`.

The minimized receipt and executable assertions are
`probes/g4-live-failed-apply-patch-posttool-callback-20260908.json` and
`tests/test_g4_live_failed_apply_patch_posttool_callback.py`. This closes the
known handler-failed `apply_patch` callback/release subcase for the candidate.
It does not qualify the baseline signed runtime, other failed or partially
executed mutation surfaces, strong global quiescence, P5b, Phase 1, or direct
write. Fresh verification passed all 595 provider-free tests in 49.068
seconds, including agent-template checks. The Phase 1 gate returned zero in
normal mode and 2 under promotion; the pristine current-source mutation check
returned zero in normal mode and 2 under qualification with thirteen blockers;
the same-UID check likewise returned zero normally and 2 when protection was
required, with rollout and state protection both false. Phases 2/3 remain
closed.

## Live PreCompact and post-compact authority re-attestation

Checkpoint `023f8386fd1a7b136121dbd086ec24b41a18e812` changed the
provider-free recovery boundary before the live run. `PreCompact` now requires
the exact bound SessionMeta identity, current root, branch, full HEAD, index,
and dirty-path scope before it atomically increments the durable recovery
epoch. A later child tool cannot proceed until its normal `PreToolUse` path
re-attests that same capsule and current Git snapshot. The isolated candidate
remained a headless-only Codex 0.153.4 binary; it did not replace the GUI App
Server, change the OpenAI parent provider, or inspect credentials. The
hash-pinned Hook overlay changed only the five G4 event entries, preserved the
existing v4 entries, added no write qualification, and restored
`~/.codex/hooks.json` byte-for-byte to SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`.

The first live timing attempt bound real child
`01a080d4-8f2b-7823-aa88-e1b3d98cbb15` to
`/root/g4_compact_resume_1` and did reach `PreCompact`, so durable state held
`recovery_count=1`. Its third native `list_agents` call completed immediately
before compaction, however, and there was no later tool acknowledgement from
which the Hook could deliver the incremented final seed. The child retained
the stale seed with recovery count zero; every SubagentStop attempt was denied
and no completion was accepted. After the real assignment TTL expired, the
exact watchdog returned exit 2 with `assignment_timeout`,
`parent_cancel_required=true`, and `unresponsive_no_disk_change`, moving only
that identity from active to unresolved. This is the required fail-closed
timing control, not a resume success.

The four-step live attempt used disposable clean root
`/private/tmp/codex-g4-compact-live-20260908-t2L9D8` at full HEAD
`632afa16f9db0eeee430ec2fd28d7e2cf7586e8a`. Real SessionMeta bound child
`01a080db-1e09-7462-ba4c-995652ba88be` to exact canonical AgentPath
`/root/g4_compact_resume_2` under parent/runtime session
`01a080da-8524-70c2-8b53-f5ae49584fd2`. Hook sequences 1903, 1904, and 1905
mediated the first three native `list_agents` calls; sequence 1906 recorded
real automatic `PreCompact`; sequence 1907 then mediated the fourth native
tool and re-attested the unchanged root, branch, full HEAD, index, and empty
scope with durable `recovery_count=1`. The child rollout independently contains
one `compacted` record before that fourth tool.

The first final added an unallowed top-level `schema` key and was denied at
sequence 1908. The corrected exact final was accepted at sequence 1909, its
SHA-256 is
`5b7af197fb004bfdbb03a13dfdd0fe3780efc39bc459964b60192da8eb3cc832`,
and the parent callback equals those accepted bytes. Candidate exit was zero;
stderr was empty; the clean Git and index snapshot remained exact; and a
delayed fresh-owner barrier found no candidate process or late write. The
frozen live receipt has SHA-256
`12052fcdfd17ea604ab195f7dcd99c684c744bc8f66974642413f0358734ff6e`.
The fresh owner passed location, mutation-scope, verification-freshness,
derivation-provenance, and null-feasibility integrity against only that hash,
then moved assignment `94ebad83-b11e-47d9-bda6-3d0851eac953` from reported
to consumed. The consumed envelope SHA-256 is
`52687cb5bb2e15c2425a0654ebc1249320a4b8e58170c314163984ca7fa4e41e`.

The executable receipt and checks are
`probes/g4-live-compact-resume-20260908.json`,
`probes/g4-live-compact-resume-parent-adjudication-20260908.json`, and
`tests/test_g4_live_compact_resume.py`. This closes one real in-process
auto-compaction and post-compact re-attestation path and advances
P1/P2/P3/P5/P5b/P6/P6a/P6b/P7. It does not prove post-compact
scope-expansion denial, representative P6c scale, mixed-frontier
exactness, strong global quiescence, Windows parity, or DeepSeek regression.
Fresh verification passed all 578 provider-free tests in 59.160 seconds,
including agent-template checks. The normal Phase 1, mutation, and same-UID
checks returned zero. Their promotion-required forms returned 2; the mutation
matrix retains thirteen blockers and same-UID rollout/state protection remains
false. Those gates remain open; `phase1_complete=false`,
`direct_write_qualified=false`, and Phases 2/3 remain closed.

## Live exact-path child write qualification

The qualification-only write path is now exercised by a real current-runtime
child rather than only provider-free state fixtures. The headless Codex 0.153.4
candidate retained the native OpenAI parent and current ChatGPT login, selected
`workspace-write` only for disposable Git root
`/private/tmp/codex-g4-write-live-20260908-BpvgBl`, and never became the GUI App
Server. A hash-pinned temporary `hooks.json` redirected only the five G4 events
to the current Hook source and added one exact task/target ceiling to
PreToolUse. All v4 entries were preserved. The original `hooks.json` SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`
was restored immediately after the run; installed Hook source files were not
overwritten.

The first prompt attempt was denied before staging because its bounded
completion phrase was not literally bound by the stop condition. No child or
target was created. After provider-free validation of the corrected authority,
PreToolUse staged assignment `908b17bb-1a4d-4b78-be37-a49d9934960b` and the
trusted Hook derived—not the parent assignment—a hash-bound qualification
consent. Real SessionMeta joined child
`01a080a4-d7aa-7cf3-9873-16117d777be4`, role
`g4_qualification_probe_worker`, parent/runtime session
`01a080a4-2b3b-78c3-9245-889a5892e433`, and canonical AgentPath
`/root/g4_exact_write_1`.

The child called native `apply_patch` exactly once with tool-use id
`call_q9nal7wlYenhGhZjEXxXJZxM`. G4 PreToolUse sequence 1783 re-attested the
immutable capsule and exact host consent, then the lease store recognized the
same active child as owner of only `qualified.txt`. Claim
`ff4195f3-04b2-4b6a-8f11-b8d5dd7e5eed` froze the clean before snapshot.
Successful PostToolUse released that exact claim into a writer receipt whose
after snapshot contains only the untracked owned file with SHA-256
`4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c`.
SubagentStop accepted the exact final attestation, and the native parent
callback reproduced the child's final message byte-for-byte.

A fresh owner independently observed the same 25 bytes, unchanged branch/HEAD
and index, no target writer claim, no candidate process, and no late change
after a two-second delayed barrier. It then used frozen evidence hash
`39f7296e566b9fa0bce20bc2e37c7d8ee7c3a98b9a967361b1a83fa1cf2155e0`
to pass all five parent-adjudication dimensions and atomically move the report
to consumed state. The worker narrative and hashes remain contribution
evidence rather than integration authority.

This qualifies one positive native `apply_patch` surface with exact child
identity, user ceiling, owned path, lease acquire/release, callback, fresh disk
adjudication, and live rollback. It does not qualify other mutation surfaces,
detached/untracked descendants, all before/mid/after races, representative P6c
dense p95, Windows parity, DeepSeek regression, or strong global quiescence.
Accordingly P4/P5b/P6a/P6b/P7 advance but remain partial;
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed. The receipts are
`probes/g4-live-exact-path-child-write-20260908.json` and
`probes/g4-live-exact-path-child-write-parent-adjudication-20260908.json`.
Fresh verification passed 26 focused wrapper/overlay/prompt/live-receipt tests
and the full 563-test provider-free suite in 47.336 seconds, including agent
template checks. The normal Phase 1, mutation-surface, and same-UID trust gates
returned zero. Their promotion-required forms returned 2; the Phase 1 gate
retains all unresolved P-gates, the mutation matrix retains thirteen blockers,
and same-UID rollout/state protection remain false.

## Exact G4 closed tool catalog and live apply-patch denial

The current-source candidate now closes the callable catalog for the exact
`g4_qualification_probe_worker` role using the role carried by real
`TurnContext.session_source`. The role is forced to direct tool mode before
request construction. After core, MCP, extension, dynamic, discovery, and
code-mode contributors have registered, the registry retains only
`apply_patch`, the bounded read-only observation tools, and
`<configured-v2-namespace>.list_agents`; hosted specs are removed. The role
cannot manage children and does not require or receive a code-mode worker.
This is a visibility boundary, not a write grant.

The focused source test enabled shell, request-permissions, Code Mode,
CodeModeOnly, Multi-Agent V2, tool suggestion, apps, plugins, standalone web,
MCP, extension, and dynamic tools at the same time. It passed with no callable
surface outside the closed allowlist. The entire spec-plan module then passed
59 tests, including encrypted/plaintext V2 schemas, exact external-provider
mapping, Bedrock, code-mode, namespace, discovery, and collision behavior.
The combined reconstructable patch is
`probes/current-signed-runtime-g4-closed-tool-catalog-source-candidate.patch`;
its source/build record is
`probes/current-signed-runtime-g4-closed-tool-catalog-source-candidate.json`.
The new headless binary is Codex 0.153.4 from pinned OpenAI source commit
`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`, has SHA-256
`90dbd98a2eb12328f6febf4eb52e1cf67ec10cda049841d16dcf7f25abb3420d`,
and was neither installed nor selected as the GUI App Server.

The live read-only negative used native OpenAI parent
`01a0806c-901d-7f33-8a68-535cfe717b4f`. Real SessionMeta bound child
`01a0806d-2e34-7eb1-9f73-2475727b668a` to exact role
`g4_qualification_probe_worker`, the same runtime session, and canonical
AgentPath `/root/g4_closed_catalog_apply_patch_deny_1`. The child made one
native `apply_patch` call with tool-use id
`call_FDNi1fDLz7Cv1DceZ7Qpeeb7`. PreToolUse sequence 1686 joined that exact
identity and rejected it before execution with `TASK.AUTHORITY_BLOCKED` because
the capsule was read-only. No shell or code-mode fallback occurred, no writer
claim was acquired, and the requested `/private/tmp` file remained absent.
SubagentStop sequence 1687 and the native wait/callback returned the exact
attestation to the OpenAI parent; the candidate exited zero.

After source and live verification, `cargo clean` removed 69,761 build files
and 23.8 GiB from the exact temporary target directory. The 590 MB standalone
candidate and 82 KB reconstruction patch remain; the source tree itself is
about 85 MB. No GUI resource or global executable points to that candidate.

A fresh post-termination observation found zero matching candidate processes,
zero open candidate executable files, the target absent, and the exact clean
HEAD/tree/index/diff frontier unchanged. The authority record correctly remains
`unresolved_terminal` with classification
`read_only_child_mutation_attempt`; neither the child's narrative nor process
absence was promoted to integration or ownership-handover authority. The
minimized live receipt and executable checks are
`probes/g4-live-closed-tool-catalog-apply-patch-denial-20260908.json`,
`tests/test_current_g4_closed_tool_catalog_source_candidate.py`, and
`tests/test_g4_live_closed_tool_catalog_apply_patch_denial.py`.

This advances P4 from an open-ended child tool surface to one source-qualified
closed catalog plus one live visible-and-mediated mutation surface. It also
reduces P5b's process-bootstrap problem for this exact role because shell,
code-mode, MCP, extension, dynamic, and agent-control launch surfaces do not
enter the candidate catalog. It does not yet prove full live absence for every
optional contributor, a successful exact-path child write, all Hook-mediated
mutation negative space, zero in-flight writer claims at handover, tracked and
detached process-tree exit, or strong global quiescence. P4 and P5b therefore
remain partial; `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.

Fresh provider-free verification passed 548 tests in 58.286 seconds with agent
template checks. The normal Phase 1, current mutation-surface, and same-UID
checks returned zero. Their promotion-required forms returned 2; the mutation
matrix retained thirteen blockers and same-UID rollout/state remained
unprotected. These expected fail-closed results keep the new catalog receipt
below direct-write qualification.

## Runtime-final G4 tool catalog receipt

The next current-source candidate moves the exact G4 catalog claim from a
source-only assertion to a receipt emitted by the finalized runtime
`ToolRouter`. Emission is disabled by default and requires the exact environment
opt-in `CODEX_G4_TOOL_CATALOG_RECEIPT=stderr-v1`, a real
`ThreadSpawn` source, role `g4_qualification_probe_worker`, a canonical
AgentPath, and a nonempty turn id. Roots, other roles, and pre-turn warm-up
contexts remain silent. The receipt is one compact stderr JSON line and writes
no file or credential data.

The emitted catalog is constructed after core, MCP, extension, dynamic,
hosted, code-mode, discovery, and collaboration contributors have finalized.
It preserves namespace identity instead of flattening names and records the
registered tools, model-visible tools, code-mode map, selected tool mode, and
whether the role can manage children. The reconstructable source patch is
`probes/current-signed-runtime-g4-live-catalog-receipt-source-candidate.patch`
with SHA-256
`805ff02e28e7ddffa179697820bd1aa1af84a44ebf5458741d67e49d86326bc2`;
its source record is
`probes/current-signed-runtime-g4-live-catalog-receipt-source-candidate.json`.
Both forward application to a pristine checkout and reverse application to the
candidate source passed. The lockfile is excluded.

Focused Rust verification passed the exact closed-catalog test, and all 59
spec-plan tests passed. The headless Codex 0.153.4 candidate has SHA-256
`6e1f9675f876588786a98dfbe5db34b20572499f476c3cbd653465daa106e816`.
It was not installed or selected as the GUI App Server. After verification, the
exact 22 GB Rust build cache was deleted; the 563 MB candidate, the 96 KB
reconstruction patch, and the 85 MB source worktree remain.

The final live run used native OpenAI parent
`01a0821d-5c23-74b1-ac9b-016c8a8ac565` and real child
`01a0821d-f4a9-7330-90b4-8d7efa59ddb6`. Runtime SessionMeta, Hook state, and
two independently emitted catalog lines agree on turn
`01a0821d-f50e-7bd1-a28f-6d3e41ea9b8f`, depth one, role
`g4_qualification_probe_worker`, and canonical AgentPath
`/root/g4_live_catalog_receipt_2`. Both catalog lines are byte-identical and
contain no empty identity field. The exact finalized direct catalog contains
only top-level `apply_patch`, top-level `view_image`, and
`g4_assignment.list_agents`; its code-mode map is empty and
`can_manage_children=false`.

The same child called the only mutation-capable catalog entry,
`apply_patch`, with tool-use id `call_zMp6I8kJmGPieh5PhDn84jYg`.
PreToolUse sequence 2200 joined the same ThreadId, turn id, role, and AgentPath,
then denied the call before execution with `TASK.AUTHORITY_BLOCKED`. The target
remained absent, no writer claim was acquired, SubagentStop and the native
callback completed, and the candidate exited zero. A later two-second barrier
found no exact candidate process, no open candidate executable, no target, and
the original clean HEAD/tree/index/diff. This remains a narrow process
observation rather than strong global quiescence.

The runtime receipt qualifies absence of the previously open shell, terminal,
code-mode, MCP/app, extension, dynamic, discovery, hosted-generation, and child
control surfaces from this exact G4 child's final model-callable catalog. It
does not close P4 as a whole: the parent remains a writer participant, and the
parent/sibling same-path matrix across opaque shell, Git/index, MCP/app, and an
already-open PTY has not yet been exhaustively serialized under a live child
lease. The separate App Server host-control, same-UID rollout/state, broad
sandbox, and detached process-tree boundaries also remain open. Therefore P4
stays partial, `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 stay closed. The minimized live receipt and executable assertions
are `probes/g4-live-final-tool-catalog-receipt-20260909.json`,
`tests/test_current_g4_live_catalog_receipt_source_candidate.py`, and
`tests/test_g4_live_final_tool_catalog_receipt.py`.

Fresh repository verification passed all 651 provider-free tests in 48.735
seconds plus the agent-template checks. The normal Phase 1, mutation-surface,
same-UID state, and Hook-chain consistency modes returned zero. Their
promotion-required forms returned 2 as designed: all nine remaining P-gates
are partial; the mutation matrix retains thirteen blockers with no source or
anchor mismatch; same-UID rollout and state remain unprotected; and the
historical live Hook chain still has one pending callback plus one unmatched
pre-overlay abort. Those expected fail-closed results are frozen in the live
receipt and do not diminish the exact-child catalog sub-gate that passed.

## Live native V2 session-close boundary

An isolated current-source candidate at OpenAI Codex commit
`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a` adds a V2 `close_agent` tool without
changing `interrupt_agent`. Its exact native path is
`AgentControl.close_agent -> shutdown_agent_tree -> Op::Shutdown ->
wait_until_terminated`. Focused Rust verification proved that the target and a
live nested descendant both receive shutdown and disappear from the agent
control plane. The first run on the default Rust test-thread stack aborted with
a stack overflow; the unchanged test passed with `RUST_MIN_STACK=16777216`.
That environmental retry is recorded rather than presented as a default-stack
pass.

Three live preflights stopped fail closed before producing a close receipt: the
first debug package omitted the optional code-mode companion requested by the
prompt, the second showed that a disabled code-mode host still cannot execute a
requested `exec_command`, and the third used the desktop-facing wait schema
instead of the current-source V2 `timeout_ms` schema. Their rollouts, exact
identities, authority disposition, and unchanged disk observations are retained
in the minimized evidence. The successful fourth probe removed those unrelated
dependencies and used only native multi-agent tools.

At clean main HEAD `9f7a60411efda86f5a0954180e524ccb0eed69f2`, native OpenAI parent
`01a08031-7008-7e80-ba0b-7e66d8955760` spawned read-only child
`01a08031-f21e-7b72-9327-a4ca826addf2` as
`/root/g4_session_close_4`. PreToolUse staged assignment
`edc79ae9-6fca-46db-a4e2-de27fe1e0e72`; real child SessionMeta, SubagentStart,
and the requested-task-name projection all joined to the same exact ThreadId
and canonical AgentPath. The child made zero tool calls and three attempted
waiting finals were blocked by SubagentStop, so it remained running.

The native close call at `08:46:15.252Z` returned at `08:46:15.602Z` with
`previous_status=running`, the exact child ThreadId and AgentPath,
`session_loop_terminated=true`, and
`process_tree_quiescence_claimed=false`. The child rollout recorded
`turn_aborted(reason=interrupted)` 255 ms before the close receipt; the next
native list contained only `/root`. The parent exited zero, the candidate
process was absent, and the fresh Git snapshot remained clean and unchanged.
No new Hook-trust or user-approval prompt appeared.

This qualifies the exact running-child identity join, native host session-loop
termination primitive, and post-close non-live observation. It does not qualify
mutation or process-tree quiescence: tracked unified-exec termination is not a
confirmed-exit join, detached/untracked descendants remain outside the proof,
and this read-only sample does not close the mutation catalog or prove zero
in-flight target writer claims. The outer owner therefore moved authority only
to unresolved with
`host_session_terminated_mutation_quiescence_unproven`; no quiescence barrier or
ownership handover was created.

The minimized receipt and executable assertions are
`probes/g4-live-session-close-20260908.json` and
`tests/test_g4_live_session_close.py`. P5b remains partial,
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed. Fresh verification passed 14 focused tests and the complete 536-test
provider-free suite in 56.956 seconds, including agent-template checks. Normal
Phase 1, mutation-surface, and same-UID checks returned zero; all three
promotion-required forms returned 2. The mutation matrix still has thirteen
blockers, and same-UID rollout/state protection remain false.

## Concurrent-cohort parent-exit orphan negative

The first current-runtime concurrent identity attempt ran from clean commit
`040eea43274928a534f3052204fd6aaeaddc2132` with the isolated 0.153.4
candidate, read-only sandbox, `approval_policy=never`, and no GUI App Server or
Hook configuration change. The prompt requested two read-only qualification
children in one assistant tool-call batch. The parent emitted only the A spawn,
then explicitly declared the probe failed and completed without issuing B,
wait, interrupt, cancel, or any mutation call. The candidate exit code was
captured directly as zero; that process result records parent turn completion,
not concurrent qualification success.

The one started child is nevertheless an exact positive identity observation.
Assignment `c81ce04d-9106-4306-b4e3-e4d36b7b4c00` and handoff
`c55e38aa-5b97-4c3e-b095-c05e389071db` bound real child thread
`01a07f7b-88f0-7781-a3b4-8ab6bf3305d3` to canonical AgentPath
`/root/g4_concurrent_identity_a1` and parent/runtime session
`01a07f7a-eebd-76a2-8c91-07b49122e0a8`. Hook sequences 1390--1392 are exactly
parent spawn PreToolUse, child SubagentStart, and the child's one allowed native
`list_agents` call. That result observed both `/root` and A running. No B spawn
or execution overlap occurred, so this is not a concurrent identity cohort.

The termination tail is the material negative. The parent completed at
`05:27:01.260Z`; 16 ms later the child rollout recorded `turn_aborted` with
reason `interrupted`. It emitted no assistant final, task-complete event, or
SubagentStop. After process exit and a later App restart, no candidate process
remained and HEAD/tree/index/status were unchanged, but the exact assignment
was still present only in `active`, with the same state hash and mtime from its
first Git attestation. It was absent from reported, unresolved, consumed, and
lost. The record was deliberately not reclassified by hand.

`probes/g4-live-concurrent-batch-orphan-negative-20260908.json` and
`tests/test_g4_live_concurrent_batch_orphan_negative.py` preserve the minimized
receipt and executable assertions. They prove that process absence is not Hook
state quiescence and expose a P5b parent-exit callback/reconciliation gap. The
same-assistant-batch mechanism is not itself a Phase 1 acceptance property; the
next bounded attempt may use two immediately sequential spawn calls, provided
the second child starts before the first child reaches accepted terminal
completion and the actual overlap is verified from real identities and
timestamps. A rejected SubagentStop correction attempt is not terminal
completion. Distinct task names must be used while the orphan remains
fail-closed. `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.

## Provider-free two-child concurrent identity sample

Commit `da0cdcbafc80439f1589685af3731d0b34a3a95b` changed the scheduling
mechanism without weakening the acceptance property. It removed the
same-assistant-response batching requirement, advanced the task names to
`g4_concurrent_identity_a2` and `g4_concurrent_identity_b2`, and required two
spawn calls before any parent wait or other tool. A staged or task-path-only
first result is sufficient to dispatch B; qualification still requires real
execution overlap and two independent terminal identities.

The clean isolated 0.153.4 run used parent
`01a07f8f-c0aa-74a2-8662-888b04b37dcf`. Real SessionMeta bound child A
`01a07f90-611b-7d80-a74d-b0d39727cf30` to
`/root/g4_concurrent_identity_a2` and child B
`01a07f90-f9cb-7562-b916-4a930e74b08d` to
`/root/g4_concurrent_identity_b2`. The assignments, handoffs, child threads,
AgentPaths, capsules, compact invariants, and spawn tool-use ids are distinct;
both children share the exact parent/runtime session and clean Git base. Each
child called only native `list_agents`, re-attested the immutable base, changed
no bytes, and reached a durable reported state.

The current runtime did execute the children concurrently. A's first
SubagentStop attempt at `05:49:58.321Z` was not terminal: B spawned afterward,
started at `05:50:11.037Z`, and its own `list_agents` result at
`05:50:15.602Z` observed `/root`, A, and B all running. A did not reach its
accepted SubagentStop until `05:50:39.414Z` or task completion until
`05:50:39.593Z`. Thus the independently witnessed overlap lasted at least
28.377 seconds before A's accepted stop. B completed at `05:51:05.760Z`.
Hook sequences 1409--1419 preserve both spawn/start/tool paths and all mediated
stop attempts.

The parent made no call between the two spawns, then completed two non-timed-out
waits. Its native spawn and wait projections exposed task paths and Hook-staged
assignment/handoff ids, but not either child thread id. The parent therefore
reported the probe failed closed even though both children completed. A fresh
owner could join the real child rollouts, SessionMeta, Hook actors, reported
records, and final attestations exactly. This is a parent result-projection gap,
not a runtime identity-binding failure, but it prevents the original parent
from self-adjudicating exact identity without an external durable receipt.

`probes/g4-live-concurrent-identity-20260908.json` and
`tests/test_g4_live_concurrent_identity.py` preserve the minimized dual
receipt: one live concurrent identity positive sample and one parent-projection
negative. The candidate exit code was directly captured as zero; a later
barrier found the process absent and HEAD/tree/index/status unchanged. Both
records remain reported, not fresh-owner consumed, and one sample is not cohort
scale or strong global quiescence. Mutation, compact/resume, cancel/crash,
representative P6c, Windows, and DeepSeek regression remain open.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Fresh-owner adjudication of the concurrent identity pair

After commit `00d6db7c0de6461109fa8157bc237b0f33673360`, the fresh `/root`
owner independently re-read the two child rollouts, real SessionMeta, exact
reported envelopes, Hook sequence, overlap witness, and clean disk/process
barrier. Worker HEAD `da0cdcbafc80439f1589685af3731d0b34a3a95b` is an ancestor
of the clean fresh-owner HEAD. The six intervening paths are exactly the
parent-authored concurrent receipt, prompt acceptance wording, status,
documentation, and tests; neither read-only child contributed a path.

The immutable adjudication input has SHA-256
`a55a69180b34fa6a7b2f7ed72af2596c0471fe9b08ab4f576284bb0de5389a9e`.
Location integrity, mutation-scope integrity, verification freshness,
derivation-provenance integrity, and null-feasibility integrity passed for both
assignments against that same hash. Assignment
`44b01bc1-80ba-49da-8f25-5a370f24f020` moved from reported to consumed with
envelope hash
`25f749ffd4d23dc2572b68c89dec44d62ad405fd4e4312a68258cb837fb78fe8`;
assignment `f957955f-1e81-420d-9c40-e5facd685e35` moved likewise with envelope
hash `9657e60f5d0eb4ec0facaf16382c4077f214c9d470d903f1e2b2b3d427cd6459`.
Both exact identities are absent from active, reported, and unresolved after
the transition.

The fresh owner adjudicated the 28.377-second overlap because B's own native
observation saw A and B running and the Hook/rollout timing placed B before A's
accepted stop. This does not repair the source parent's result projection:
spawn/wait still omitted child thread ids, so source-parent self-adjudication
remains false. It also does not reconcile the earlier `a1` orphan, qualify
cohort scale, or supply a strong global quiescence receipt.

The input, result, and executable checks are
`probes/g4-live-concurrent-identity-parent-adjudication-input-20260908.json`,
`probes/g4-live-concurrent-identity-parent-adjudication-result-20260908.json`,
and `tests/test_g4_live_concurrent_identity_parent_adjudication.py`. This adds
positive P1/P2/P3/P6/P6a/P6b evidence for one provider-free concurrent pair.
The fresh full provider-free suite passed 495 tests in 56.504 seconds with
agent-template checks. Phase 1, mutation, and same-UID normal checks returned
zero; their promotion-required forms returned 2. The mutation matrix retains
thirteen blockers and same-UID rollout/state remain unprotected.
Nested/resume identity, orphan recovery, mutation-capable contribution, full
mutation negative space, representative P6c, strong global quiescence,
Windows, and DeepSeek regression remain open. `phase1_complete=false`,
`direct_write_qualified=false`, and Phases 2/3 remain closed.

## Exact watchdog freeze of the parent-exit orphan

The earlier `g4_concurrent_identity_a1` record was still present only in the
live `active` bucket after its parent exited and the child rollout ended with
`turn_aborted`. It retained assignment
`c81ce04d-9106-4306-b4e3-e4d36b7b4c00`, handoff
`c55e38aa-5b97-4c3e-b095-c05e389071db`, canonical AgentPath
`/root/g4_concurrent_identity_a1`, active-state SHA-256
`23d7751e56e86abd56a53fc4bcad6a1b0b423d105a6162fabb8a3d576848667a`,
and the original clean base HEAD
`040eea43274928a534f3052204fd6aaeaddc2132`. Its first Git attestation was
present, but its assignment TTL had expired. No hand-edited state transition
was used.

The existing provider-free `hooks/authority_watchdog.py` was invoked for that
one exact assignment at fixed observation time
`2026-09-08T06:23:44+00:00` with fail-on-termination enabled. It returned exit
2, `terminated_count=1`, and `parent_cancel_required=true`, then moved only the
expired identity from `active` to `unresolved`. The termination evidence is
classified `initial_authority_mismatch`: the later clean repository HEAD was
not the child's attested base, so `baseline_comparable=false` and
`disk_changed=null`. The watchdog therefore did not attribute intervening
parent evidence commits to the child and did not infer terminal success or
delete durable authority.

A post-watchdog observation found no matching candidate process and no Git
change at fresh-owner HEAD `ceebd126b65074409c3a625aa375b9f05d13aad4`.
Those observations are deliberately weaker than a host-control receipt. No
parent cancel acknowledgement, mutations-quiesced guarantee, quiescence
receipt, or ownership handover was produced. Process absence does not repair
the missing SubagentStop callback and does not authorize reuse of the child's
paths.

`probes/g4-live-concurrent-orphan-watchdog-recovery-20260908.json` and
`tests/test_g4_live_concurrent_orphan_watchdog_recovery.py` preserve the exact
transition and its fail-closed assertions. This advances one live P5a watchdog
sample and clears a stale active bucket without weakening P5b. A live
first-attestation-deadline expiration, actual cancellation acknowledgement,
strong termination/quiescence, and fully qualified orphan reconciliation
remain open. The fresh provider-free suite passed 502 tests in 54.576 seconds,
including agent-template checks. The normal G4, mutation, and same-UID checks
returned zero; all three promotion-required forms returned 2. The mutation
matrix still has thirteen blockers and same-UID rollout/state remain
unprotected. `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.

## Live first-attestation watchdog and cancel-race boundary

The first P5a runner attempt at clean HEAD
`8422ed4410741fd249ece1bd027a5218b3fbe138` intentionally preserved the
runtime default and therefore selected `collaboration.spawn_agent`. The parent
rollout shows its `message` argument beginning with the Fernet marker
`gAAAAAB`, length 3596, and zero plaintext authority begin/end markers.
PreToolUse rejected it with `TASK.HANDOFF_BLOCKED`; no child or authority state
was created. This is the encrypted control, not a failure to copy the
declaration into the source prompt and not a reason to decrypt inside the
Hook.

Commit `77faf0039046243e8671db68a6e46895a155adc4` made the runner select the
candidate's exact `g4_assignment` namespace. The second standalone 0.153.4
run explicitly opted into `message_delivery=plaintext`, kept the native OpenAI
parent and inherited-OpenAI G4 child, used the repository as its exact cwd, and
did not select the candidate as the GUI App Server. PreToolUse saw exactly one
authority declaration and staged assignment
`288b4db5-fd9d-4ea4-8836-f2673bca42f3`; real SessionMeta bound child
`01a07fce-ed6f-7930-bd56-eea4b884d434` to
`/root/g4_first_attestation_timeout_2` under parent/runtime session
`01a07fce-6bfc-78b1-a615-3d4b650c1496`.

The child made no tool call and `first_git_attested_at` remained null. Its
one-second deadline elapsed at `06:57:43.650882Z`. The parent invoked the exact
watchdog for only that assignment at `06:57:59.489867Z`; it returned exit 2,
`valid=true`, `terminated_count=1`, `parent_cancel_required=true`, reason
`pre_write_attestation_timeout`, and classification
`unresponsive_no_disk_change`. The baseline was comparable and clean at full
HEAD `77faf0039046243e8671db68a6e46895a155adc4`, so the record moved only from
active to unresolved without attributing a contribution.

The same run exposes a precise downstream cancel race. Two invalid
`WAITING_FOR_PARENT_INTERRUPT` finals were blocked while authority was active.
After the watchdog transition, the installed SubagentStop guard accepted the
third attempt at `06:58:03.277517Z`, and the child completed at
`06:58:03.352Z`. Native `g4_assignment.interrupt_agent` did not run until
`06:58:10.485Z`; its `previous_status` was already completed, as was the later
`list_agents` result. Thus this is a positive live first-attestation/watchdog
sample and a negative running-child cancel sample. It is not a cancellation
acknowledgement and not strong termination or quiescence.

Commit `559640c8d05ba3c84d9d324167865a2b8ea862da` closes the isolated race by
making only `pre_write_attestation_timeout` and `assignment_timeout` terminal
records block SubagentStop with `TASK.PARENT_CANCEL_REQUIRED`. Other exact
guard-terminal reasons retain their existing completion behavior. Related
runtime, transport, callback, and prompt tests passed 120 tests in 38.124
seconds. The guard change was not installed during the receipt and is not yet
live revalidated, so a real running-child interrupt acknowledgement remains a
P5a blocker. Even after that acknowledgement, P5b still requires a stronger
host termination/mutation-quiescence receipt and post-termination barrier.

The minimized receipt and executable assertions are
`probes/g4-live-first-attestation-watchdog-cancel-race-20260908.json` and
`tests/test_g4_live_first_attestation_watchdog_cancel_race.py`.
Fresh verification passed 72 focused tests in 13.219 seconds and the full 515
provider-free tests in 58.170 seconds, including agent-template checks. The
normal Phase 1, mutation, and same-UID gates returned zero; their three
promotion-required forms returned 2. The mutation matrix retains thirteen
blockers, and same-UID rollout/state protection remain false.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Live first-attestation watchdog cancellation acknowledgement

After checkpoint `0d06688d162b33b189c3b0bd67e45d00054ccc43`, the exact
provider-free timeout fix from commit
`559640c8d05ba3c84d9d324167865a2b8ea862da` was installed into the trusted
live overlay. Repository and installed `runtime_guard.py` both had SHA-256
`fceff5adbac470c0b42e0aed788ae223b3552a084b4595b6e3fcc5cd8a4e7c14`;
the previous `1fd9be69ac7dd6f52a4a9b12ccd13d69d2aece958a7b6e745e3c94ad39d172dc`
file was preserved in the state backup tree. `hooks.json` did not change, no
new Hook-trust prompt appeared, and the candidate was not selected as the GUI
App Server.

The isolated plaintext parent used native OpenAI inference and exact
`g4_assignment` delivery. PreToolUse staged assignment
`8022e266-84ec-45a7-98fc-3bb84d2de850`; real SessionMeta then bound child
`01a07fee-8075-72e0-872c-194428b65d55` to canonical AgentPath
`/root/g4_first_attestation_timeout_3` under parent/runtime session
`01a07fed-ff8d-7271-8ff1-e27e00c805e4`. The child made no tool call, acquired
no Git attestation, and twice had its bare waiting message rejected before the
watchdog ran.

The exact watchdog observed the expired one-second first-attestation deadline
at `07:32:30.229906Z`. It returned exit 2 with `valid=true`,
`terminated_count=1`, `parent_cancel_required=true`, reason
`pre_write_attestation_timeout`, a comparable clean baseline, and no disk
change. Unlike the preceding negative, the child's next SubagentStop at
`07:32:33.841182Z` was blocked with `TASK.PARENT_CANCEL_REQUIRED`; it could not
self-complete from the unresolved timeout record. Native interrupt was called
at `07:32:35.622Z` and returned `previous_status=running`; the child rollout
ended with `turn_aborted(reason=interrupted)`, not task completion. The exact
follow-up list reported the child `interrupted`.

After parent completion the candidate held no open executable file, Git
HEAD/tree/status were unchanged, and the exact assignment was absent from
pending, claimed, active, reported, and consumed while remaining present in
unresolved. That last state is deliberate: a running-child interrupt
acknowledgement is not a strong host termination, mutation-quiescence, or
ownership-handover receipt.

Together with the existing provider-free full-HEAD mismatch and spawn-preflight
fixtures, this live no-event watchdog/cancel signal qualifies P5a for the
current isolated runtime. It does not qualify P5b, Phase 1, or direct write.
The minimized receipt and assertions are
`probes/g4-live-first-attestation-watchdog-cancel-ack-20260908.json` and
`tests/test_g4_live_first_attestation_watchdog_cancel_ack.py`.
Fresh focused verification passed 79 tests in 13.619 seconds; the full
provider-free suite passed 522 tests in 57.812 seconds with agent-template
checks. The normal Phase 1 gate returned zero and its promotion-required form
returned 2 with P5a absent from the blocker list and P5b still present.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Live post-compact foreign-scope denial

The first successful compact/resume receipt exposed one remaining failure
semantic: a read-only tool correctly denied root, HEAD, index, or path drift
after the first Git attestation, but left the assignment active. Because the
denied `PreToolUse` response carried no new final seed, that could force a
SubagentStop correction loop until TTL. The provider-free guard now atomically
moves this exact case to unresolved with reason
`authority_reattestation_mismatch`, classification
`post_attestation_authority_drift`, and provenance status
`post_attestation_authority_drift_unattributed`. It records the attempted tool
and exact snapshot without assigning the dirty bytes to the child. This reason
does not authorize integration or ownership handover, and it is not treated as
a watchdog reason requiring a second cancel.

The live negative used clean disposable root
`/private/tmp/codex-g4-postcompact-drift-20260908-fvRdKu` at branch `main` and
full HEAD `c435f0c5cf38d2b3115d412781c2e60b91d74f90`. Real SessionMeta bound child
`01a08102-98c0-7520-9381-5ab1b0efff7c` to canonical AgentPath
`/root/g4_postcompact_scope_drift_1` under parent/runtime session
`01a08101-dbc9-7c62-baef-c7b4aa309f3e`. The assignment was strict read-only,
with empty owned and excluded paths and no Git authority.

Hook sequences 1942 through 1944 mediated three successful native
`list_agents` calls. Automatic `PreCompact` ran at sequence 1945 and atomically
advanced the durable recovery count to one. The provider-free host injector
then acquired the same authority-state lock, revalidated the exact active
capsule, binding, first Git attestation, clean root, branch, full HEAD, index,
and empty path set, and created only
`foreign-postcompact-drift.txt`. Injection occurred at
`12:34:03.143528Z`, strictly after PreCompact at `12:34:02.871699Z` and before
the fourth PreToolUse at `12:34:54.200298Z`. Holding the state lock through the
exclusive 0600 write forced the fourth tool to observe the injected path after
the write rather than race ahead of it. The path SHA-256 is
`2c8aa089e24dbed995b1ba51f59a93751fb82edd00e889ef40ae469d441b383d`.

Sequence 1946 denied the fourth native tool before execution with the exact
unauthorized path and moved assignment
`5d1a68d7-fa3c-4383-947b-571806cca3ac` from active to unresolved. The
unresolved envelope SHA-256 is
`7516ed7328331267b81c78ac73b1c1081cb99521a9e2a012760d1a59febc9154`.
At sequence 1947 the terminal SubagentStop accepted only the fixed marker
`TASK.AUTHORITY_REATTESTATION_BLOCKED`; the parent callback equals that marker.
Both candidate and injector exited zero. A delayed fresh-owner barrier found
no candidate process, no later write, unchanged branch/HEAD/index, and only
the intentionally injected untracked path. The Hook overlay preserved v4 and
restored the original `hooks.json` SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`.

The frozen receipt has SHA-256
`3f91bb744b6438aea7354cea24290137af4062752fa812ff47956c42d88bec1a`.
A fresh owner passed the exact compact/injection/fourth-tool ordering, host
provenance, denial, callback, and disk barrier against that hash. The negative
state remains unresolved with the same envelope hash before and after
adjudication; it was not consumed as a contribution. The reusable prompt,
state-lock injector, evidence, adjudication, and executable assertions are
`probes/build_g4_postcompact_scope_drift_probe_prompt.py`,
`probes/inject_g4_postcompact_scope_drift.py`,
`probes/g4-live-postcompact-scope-drift-denial-20260908.json`,
`probes/g4-live-postcompact-scope-drift-parent-adjudication-20260908.json`, and
`tests/test_g4_live_postcompact_scope_drift.py`.

This closes the live post-compaction scope-expansion negative for P5. Together
with the exact positive re-attestation path and the fail-closed
no-postcompact-tool timing control, P5 is qualified against its original
compact/resume continuity contract. Current Codex source constrains that
boundary: the internal subagent resume entry point restores stored AgentPath
metadata, while Multi-Agent V2 root resume deliberately does not reopen
descendants. A public CLI process-restart child resurrection is therefore not
an available runtime contract and is not invented as an additional P5 gate.
P5b still lacks strong host mutation quiescence and ownership handover; P4
retains the other mutation-surface blockers; P6c, Windows, and DeepSeek
regression remain open.
Fresh verification passed all 589 provider-free tests in 59.950 seconds,
including agent-template checks. Normal Phase 1, mutation, and same-UID checks
returned zero; promotion-required forms returned 2. The Phase 1 status retains
eleven partial gate blockers, the mutation matrix retains thirteen blockers,
and same-UID rollout/state protection remains false.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## P6c external-owner read-only gap adjudication

A fresh read-only adjudication of the LocalCAT Feature 5 owner evidence used
exact root `/Users/pearly/文档/CAT/localcat-feature5`, branch `feature5`, and
full HEAD `dd7c9fdb268b4ee8ac3545f43e3f5f19e715ff3b`. It observed zero tracked
changes, did not inspect the diagnostic directory, changed no LocalCAT, Hook,
configuration, Git, or index state, and read or recorded no credential value.
The privacy-minimized result is
`probes/p6c-feature5-readonly-gap-adjudication-20260909.json` with executable
assertions in `tests/test_p6c_feature5_readonly_gap_adjudication.py`.

The canonical 100k Gate D bundle is real contribution evidence. Its frozen
contract has 1,200 exact and 240 fuzzy samples (200 near-edit plus 40 miss),
100 warmups per cohort, one measured repeat, per-query `perf_counter_ns`, and
nearest-rank p95. FTS5 and fallback fuzzy p95 are respectively 275.832958 ms
and 279.756833 ms against the 500 ms gate. The bundle SHA-256 is
`7f33c553f0c6fa5f10a802049a2bca3f4457bf3adba5fdc001aa31eab3d1ac96`
and its internal bundle digest is
`071f2787f452c9f07635a85e0626e8538bdb79a1b4f46ea3a37a06d47cf5be7e`.
Separate source fixtures also cover a 2,048-call budget, 300 exact-fold classes
over 3,000 identities with 300 actual scorer callbacks, mathematical bound
relations, and real SQLite append seams before, during, and after phase work.

Those facts do not form the P6c join required by the design. The canonical
bundle has no dense owner-cohort identity or traversal-mode identity and does
not join each raw latency sample to its actual invocation and proof partitions.
The current production refinement chain is U1 to owner-derived R to U3 and
optional U4/P3; there is no representative same-cohort U1/R/U2/true receipt.
No artifact freezes coarse/refine/materialize input/output identities,
conservation, and real elapsed values together. Public proof metadata omits
the complete item frontier by design, so top-10 equality cannot substitute
exact authoritative/materialized cardinality, order, and item identity. Race
tests define real mutation seams, but there is no persistent raw run receipt
with timestamps and hashes. The q1/q61/q28-short/q183/q226/q240 task note is
summary-only and cannot authorize these missing dimensions.

Therefore the existing Gate D bundle, implementation notes, and passing
acceptance/fault/release matrices remain contribution evidence only. P6c
stays `partial`; `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.

## Hash-bound parent/child same-path completion

The first live same-path overlap proved that a root parent `apply_patch` was
denied while an exact child assignment and writer claim were both active, but
that run never produced an accepted SubagentStop, callback, or known candidate
exit. It remains a useful P4/P5b negative. A new provider-free repeat at clean
disposable root `/private/tmp/codex-g4-write-parent-conflict.XwVX2t`, branch
`main`, full HEAD `da01a14efeb159a937f638f4f53f311cef9673c8`, and tree
`437d2c15abdb54d5710d7ce8e756123b8d32a2de` closes the same-path
`apply_patch` subgate through the downstream lifecycle.

Real SessionMeta bound child
`01a08408-c12e-7951-a482-94198977e5f5` and turn
`01a08408-c19c-7452-9bae-d88bbaf4e6a5` to canonical AgentPath
`/root/g4_parent_conflict_final_1` under parent/runtime session
`01a08408-0f03-7e40-8d44-9096f67c221a`. The finalized runtime catalog was
emitted twice with the same canonical receipt hash
`4afc0668f8409630908724c4bafbdaf0b4cb22793555cc70d07aa3d6a29a64ef`.
It exposed only `apply_patch`, `g4_assignment.list_agents`, and `view_image`;
the code-mode map was empty and child management was false.

Hook sequences 2520 through 2525 are contiguous: target spawn PreToolUse,
SubagentStart, child `apply_patch` PreToolUse, parent `apply_patch` denial,
child `apply_patch` PostToolUse, and accepted SubagentStop. The parent denial
at `02:39:39.088593Z` observed both child writer claim
`f135a892-0671-47ad-b27f-962b3d045b6f` and active assignment
`d60eb350-3808-474d-bad4-f5fdac95b817`, returned
`TASK.WRITER_LEASE_BLOCKED` before execution, and preceded the child's release
at `02:39:43.016930Z`. The parent did not retry.

The child's PostToolUse receipt is schema 2 and hash-bound to the final disk
snapshot. Receipt SHA-256
`a41128efdc35897fdb8936594202cf81a86d40147cf7a457a4dc2bd0f47a6fa8`
is exactly the final provenance derivation receipt. The child final and parent
callback are byte-identical with SHA-256
`cfd3df779e53c9c313cedcd8542d46d011216ca28fef8dbe996bed598e37432e`.
The candidate exited zero. A delayed fresh disk observation found only the
25-byte child file, SHA-256
`4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c`,
with clean index, no exact candidate process or open executable, no matching
live assignment or writer claim, and no late write. This is a narrow target
barrier, not strong global process-tree quiescence.

While freezing that evidence, the installed live G4 Hook bundle exposed a
separate version-skew failure: its older validator accepted only unavailable
host consent and quarantined the new exact qualification receipt written by
the current repository Hook source. The failed evidence patch left no writer
claim or repository file. Before repair, `hooks.json`, the installed source
bundle, and the exact quarantined envelope were backed up under
`/Users/pearly/.codex/backups/codex-deepseek-subagent-g4-schema-skew-20260909.XDtvKl`.
Only six stale installed Python sources were atomically refreshed from the
current repository. `hooks.json` stayed byte-identical at SHA-256
`82c8aa0bc4d739628646864578de6c078884c21413855ed3db448d4365a8668e`;
the v4 Hook, GUI App Server selection, and LocalCAT were unchanged. A fresh
process then validated all 43 stored capsules. The affected envelope moved
from quarantine back to reported with its original SHA-256
`f3153581845d9d23b3571f641e3110e83edd061a18eeb07d00abeabc2b3a591b`.
This is exact schema reconciliation with rollback material, not a claim that
functional live reload or the P7 install/rollback gate is qualified.

The immutable adjudication input is
`probes/g4-live-hash-bound-parent-child-conflict-20260909.json`, SHA-256
`3a76d811e8cbe404a4c7401dc0f1505c383bbe78e11a5e55d2d517ef07eded1a`.
A fresh owner passed location, mutation scope, verification freshness,
derivation provenance, and feasibility integrity against that exact hash, then
moved the durable record from reported to consumed. The consumed envelope
SHA-256 is
`390fed8d24b03cc4d87e7d63e15e03459e2fd1d7adeeb0be1d07a8cfa15d6608`.
The result and executable assertions are
`probes/g4-live-hash-bound-parent-child-conflict-parent-adjudication-20260909.json`
and `tests/test_g4_live_hash_bound_parent_child_conflict.py`.

Fresh focused verification passed 23 tests. The complete provider-free suite
passed all 692 tests in 52.881 seconds plus agent-template checks. Normal Phase
1, mutation-surface, and same-UID checks returned zero; their promotion forms
returned 2. Thirteen mutation surfaces remain blockers, and same-UID rollout
and state protection remain false. This advances P4 and P5b for exact parent
versus child `apply_patch` serialization and advances P6/P6a/P6b for one
freshly consumed mutation contribution. It does not qualify sibling or opaque
shell/Git/MCP/PTY surfaces, strong global quiescence, representative P6c,
Windows, DeepSeek regression, or functional live rollback.
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Live mutation actor accepted-report termination barrier

A new isolated headless run extends the current-source P5b close primitive from
an idle read-only child to a child that actually performed its one authorized
mutation. The disposable root was
`/private/tmp/codex-g4-p5b-write-termination.xy1PJw`, branch `main`, full HEAD
`0041570f2938e897ba6abdd8699c89558fb9a77b`. The wrapper admitted only the
exact `schema1-exact-write-then-close` authorization under that fixed temporary
namespace, selected `workspace-write`, preserved the closed parent/child tool
catalog and v4 Hook, and never selected the candidate as the GUI App Server.

Real SessionMeta bound child
`01a084f3-6c61-7492-8a26-1d890de45a23` to canonical AgentPath
`/root/g4_p5b_write_close_1` under parent/runtime session
`01a084f2-a42f-7061-95e3-49fb60f6e91b`. Hook sequences 2720 through 2724 were
contiguous: spawn PreToolUse, SubagentStart, child `apply_patch` PreToolUse,
the same tool-use PostToolUse, and accepted SubagentStop. The child created only
`qualified.txt`, exactly 25 bytes with SHA-256
`4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c`.
Writer receipt
`bccba29b563a70a746327d991379fee906b8dc92756da43085062a6acefe5558`
binds the same child identity, path, tool-use id, and final snapshot. No Git
stage, commit, branch, or push authority was granted.

The first turn completed with one accepted attestation. Its payload was
byte-identical inside the parent callback. The parent then sent one exact
read-only host-close hold as a new turn; this did not renew mutation authority.
The child was observed running and made no second-turn tool call or final.
Exact `close_agent` interrupted that turn, returned `previous_status=running`,
empty tracked/confirmed/unconfirmed/unresolved process maps for the exact child,
`tracked_process_termination_confirmed=true`, and
`closed_catalog_actor_quiescence_claimed=true`. The child rollout recorded
`turn_aborted(reason=interrupted)` before close returned, and the next live-tree
observation omitted the child. The receipt truthfully retained
`process_tree_quiescence_claimed=false`.

`probes/reconcile_g4_write_then_close.py` independently joined the immutable
write capsule, trusted user ceiling, exact SessionMeta, writer receipt, target
bytes, accepted callback, second-turn interrupt, close receipt, Hook chain, and
stable post-close Git snapshot. Only after those checks did it freeze the
unadjudicated record from `reported` to `unresolved`, preserving the final
attestation and adding termination evidence, then publish the host-owned
`child_terminated_and_mutations_quiesced` barrier. Two later observations
retained the same HEAD, tree, `?? qualified.txt` status, and target hash, with no
open candidate executable. The candidate exited zero. Raw rollouts and tool
payloads remain outside Git; the privacy-minimized evidence is
`probes/g4-live-write-then-close-20260909.json`.

Focused executable verification passed 38 tests, including byte-exact callback,
nonempty/unconfirmed process-map, second-turn mutation, extra/noncontiguous Hook,
wrapper guard, and durable-state negative cases. The complete provider-free
suite then passed all 729 tests in 72.190 seconds, including agent-template
checks. Normal Phase 1, mutation-surface, same-UID trust, and semantic runtime
index commands returned zero. Phase 1, mutation, and same-UID promotion forms
returned 2 as designed.

This is the first positive P5b signal for a real mutation-capable actor, not
merely a read-only actor. Its scope is deliberately bounded to this one exact
`apply_patch` catalog and child. Detached/untracked descendants, other mutation
surfaces, before/mid/after ownership-handover races, and strong global
process-tree quiescence remain open. The accepted contribution remains
unresolved rather than integrated. P5b stays `partial`;
`phase1_complete=false`, `direct_write_qualified=false`, and Phases 2/3 remain
closed.

## Live exact post-quiescence child handover and completed-actor cleanup close

The next isolated headless run consumed the mutation actor barrier above instead
of recapturing or silently replacing its dirty frontier. The replacement
capsule bound prior assignment
`e80799bf-584e-45b6-8bb2-d1ab39ebc51b`, barrier
`d4632de6ab1468b34ffb4bd0e1e606e053164945bf0aa694183c9fc896e5cf39`,
and snapshot
`7604313a214ba5f3deae0649c79ae06b79c7b4127e35a1e20c3f9098365ad691`.
The capsule capture had the same snapshot hash and the exact preexisting target
hash `4fd8e8f97e640e495fefed6d4fdb0467c4e5835d9bd006173da14af37698ac8c`.
No writer hold or overlapping writer was synthesized.

Real SessionMeta then bound replacement child
`01a0854b-3746-7221-afbf-66f6e2e51050` to canonical AgentPath
`/root/g4_p5b_handover_close_2` under parent/runtime session
`01a0854a-793c-7c30-8c58-70cd5115b8ce`. The distinct handover Hook ceiling
allowed only one existing regular target under the fixed temporary namespace.
Hook sequences 2819 through 2823 were contiguous: spawn PreToolUse,
SubagentStart, child `apply_patch` PreToolUse, same-id PostToolUse, and accepted
SubagentStop. Writer receipt
`37fe946aec067c899be6f22bbac1dcb39cc9e1b32f9d062f603fd3f5195bc5c1`
joins the replacement identity, the prior barrier, the exact owned path, before
snapshot hash, after snapshot hash, tool-use id, and new target hash
`a8f1339e5606929e1b7b1ef503d539da952becc5ea19cd94b4a749a0240860e8`.
No stage, commit, branch, or push authority was granted.

The child completed its only turn and the parent received a byte-identical
callback payload. The parent did not successfully trigger the intended
read-only hold turn; it called `close_agent` after completion for cleanup. The
receipt therefore had a completed-status object containing the exact child
final, rather than `previous_status=running`. It still bound the exact child and
canonical AgentPath, reported an absent process bootstrap, zero tracked
background processes, four empty exact-child process maps, confirmed tracked
process termination, and closed-catalog actor quiescence. It truthfully retained
`process_tree_quiescence_claimed=false`. This run is classified only as
`completed_cleanup_close`; it does not borrow the earlier running-actor close
semantics.

`probes/reconcile_g4_handover_then_close.py` independently required the prior
unresolved record and barrier, immutable replacement capsule, both real
SessionMeta records, one exact update patch, schema-2 writer receipt, accepted
attestation, exact callback, completed-child cleanup receipt, five-event Hook
chain, target bytes, absence of an in-root writer claim, executable candidate
hash, and two stable post-close disk observations. Only after every join passed
did it move assignment `f03919cd-6418-4adc-b989-ca1eb75b45be` from `reported`
to `unresolved` and publish replacement barrier
`13adabfadc392654e3531a1c4c45a5a335158ecb8d35aad16ecc8c13cf2ddad1`.
Raw rollouts and tool payloads remain outside Git; the privacy-minimized record
is `probes/g4-live-handover-cleanup-close-20260909.json`.

The first attempted handover run had failed before child spawn because its stop
condition did not bind the exact bounded completion wording. The target and
durable state were unchanged. That fail-closed result led to a prompt-only
wording correction, not a relaxation of the handover ceiling.

Fresh executable verification passed all 742 provider-free tests in 57.377
seconds, including agent-template checks. Normal Phase 1, thirteen-surface
mutation, same-UID trust, and semantic runtime-index checks returned zero. Their
Phase 1, mutation, and same-UID promotion forms returned 2 as designed.

This is a positive exact sequential ownership-handover result for the two named
actors and one path. It does not cover an in-flight handover, a parent/sibling
claim race before, during, or after transfer, an already-open PTY, other
mutation surfaces, detached descendants, or strong global process-tree
quiescence. It also does not add a second resumed-running termination result;
that property remains supported only by the preceding bounded actor run. P5b
stays `partial`; `phase1_complete=false`, `direct_write_qualified=false`, and
Phases 2/3 remain closed.
