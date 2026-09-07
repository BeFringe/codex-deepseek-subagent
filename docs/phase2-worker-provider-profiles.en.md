# Phase 2: Worker / Provider Profile Contract

[简体中文](phase2-worker-provider-profiles.md) ·
[Phase 1 / G4 probe plan](phase1-g4-probe-plan.md) ·
[Phase 3](phase3-zhipu-responses-bridge.en.md)

Status: **closed and not approved for implementation**. This file preserves the
future-stage design contract. It is not an implemented feature, installation
guide, or approval to open Phase 2. A separate adjudication may open this phase
only after Phase 1 P1–P7 (including P5a/P5b/P6a/P6b/P6c), live G4 evidence,
platform regressions, and install rollback all close.

## Objective

Extract the configuration currently coupled to `v4_flash_worker`, DeepSeek,
and `deepseek-v4-flash` into a minimal declarative profile so the plaintext
assignment transport itself is product- and provider-neutral:

```text
Worker Profile
├── worker identity
├── assignment transport
├── wire transport
└── request normalization
```

The three transport dimensions remain orthogonal:

| Dimension | Candidate values | Meaning |
| --- | --- | --- |
| `assignment_transport` | `native`, `plaintext-v2` | How the assignment reaches the real Codex child |
| `wire_transport` | `native`, `responses-direct`, `responses-bridge` | How the child reaches its own provider |
| `request_profile` | `none`, `deepseek`, `glm-thinking`, … | Proven provider/model-family request normalization |

ZHIPU is a provider and GLM is a model family. The candidate profile name is
therefore `glm-thinking`; it must not conflate those concepts.

## Current upstream entry blocker

Codex `0.149.0+` agent roles permit bounded model-behavior overrides and
capability reductions only; the child retains the parent's model provider.
Exact-source oracles for `0.150.0-alpha.8` and `0.153.4` both establish this
boundary. The profile model must therefore not assume that `model_provider` in
a standalone agent TOML can still switch a native child's provider.

In addition to complete Phase 1 evidence, entering Phase 2 now requires a new
upstream seam: bounded native per-child provider/profile selection, or explicit
user approval to change this project's architectural contract that Codex-native
lifecycle remains authoritative. Utopia's current MixAgents Broker uses an
independent App Server lifecycle. It is a relevant alternative architecture,
but not an entry seam for this Phase 2 or evidence that P7 passes.

## Invariants

- The OpenAI parent always remains on its current Codex-native OpenAI provider,
  model, and ChatGPT login. A profile never changes or proxies parent traffic.
- Codex natively owns discovery, spawn, canonical AgentPath, permissions,
  lifecycle, wait/callback, cancellation, and the Multi-Agent V2 graph. A
  profile cannot copy or take over those responsibilities.
- A profile declares capabilities and required runtime posture only. It cannot
  grant mutation, Git, path, completion, cost, or provenance authority.
- Authoritative input roots, forbidden derived facts, the real/test boundary,
  owned/excluded paths, verification, stop condition, and feasibility/cost
  contract remain frozen per assignment in the immutable capsule. A profile
  cannot default, infer, or normalize them.
- Credentials never enter committed profile values, handoffs, capsules, Hook
  output, logs, or Git.
- Phase 2 may define only the declaration location for an opaque credential
  source/reference. It must not read or consume a real `ZHIPU_API_KEY`. A
  user-prepared host environment is not a Phase 2 deliverable and opens no
  stage. Only after Phase 3 is approved and `zhipu_plan_worker` qualification
  starts may the host check present/missing and use its owned forwarding path;
  it never reads or records the value.
- Windows and POSIX use one protocol/schema, not provider-specific handoff
  copies.

## Candidate declaration model

This illustrates the design shape only; it is not installable configuration:

```json
{
  "v4_flash_worker": {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "assignment_transport": "plaintext-v2",
    "wire_transport": "responses-direct",
    "request_profile": "deepseek"
  },
  "zhipu_plan_worker": {
    "provider": "zhipu-coding-plan",
    "model": "<qualified GLM model>",
    "assignment_transport": "plaintext-v2",
    "wire_transport": "responses-bridge",
    "request_profile": "glm-thinking"
  },
  "native_worker": {
    "provider": "openai",
    "model": "<native model>",
    "assignment_transport": "native",
    "wire_transport": "native",
    "request_profile": "none"
  }
}
```

Implementation should follow the repository's existing small-file/data style,
not introduce a large framework. The handoff core must stop hard-coding
`AGENT_TYPE = "v4_flash_worker"`, but it must not fork parallel protocols such
as `plaintext_handoff_deepseek` and `plaintext_handoff_zhipu`.

## Implementation order after approval

1. Freeze the complete Phase 1 G4 evidence commit and live install/rollback
   baseline.
2. Define a minimal profile schema, validation, unknown-value fail-closed
   behavior, and stable canonical hash.
3. Derive the installer, Hook matcher, Skill, Agent template, and smoke oracle
   from one profile contract or enforce their consistency with tests.
4. First validate the upstream native per-child provider seam. If the seam is
   still absent, stop Phase 2 at schema research; do not install or migrate a
   worker.
5. Once the seam exists, preserve `$use-v4-flash-worker` as a backward-compatible
   wrapper/alias and migrate the legacy DeepSeek route under an explicit version
   boundary. Do not add the ZHIPU bridge or a real ZHIPU credential in the same
   step.
6. Complete POSIX/Windows provider-free tests, the DeepSeek live regression,
   and full rollback before separately adjudicating Phase 2 complete.

## Qualification matrix

A new worker must independently pass:

### A. Agent/runtime compatibility

Real discovery, spawn, requested-name to canonical-AgentPath binding, parent
relation, tool calls, wait, cancellation, callback, termination/quiescence, and
resume identity must all be exact.

### B. Assignment transport compatibility

Select `native` or `plaintext-v2` explicitly. Do not force the Hook when native
cross-provider V2 collaboration is reliable. A plaintext worker must reuse the
single Phase 1 protocol that passed G4.

### C. Wire/provider compatibility

Select `native`, `responses-direct`, or `responses-bridge`, then declare the
minimal request profile. Replacing only `model` or `base_url` does not qualify
a worker.

### D. Authority/provenance compatibility

The profile declares whether it can satisfy the Phase 1 capsule and runtime
posture. Worker narrative, hashes, or a provider-returned digest/PASS remain
contribution evidence; parent/disk/fresh-owner adjudication retains integration
authority.

## Phase 2 exit conditions

- The profile schema, installer, matcher, Skill, Agent template, and smoke
  artifacts agree.
- The assignment-transport core contains no DeepSeek/ZHIPU product hard-code.
- Current source and live evidence establish a native per-child provider seam
  without changing the parent provider.
- The v4 wrapper remains compatible within an explicit version boundary and the
  DeepSeek direct Responses route is green.
- A native-worker control bypasses both the plaintext Hook and bridge.
- Static and live evidence prove credential and parent-provider isolation.
- POSIX/Windows parity, callback/cancel/termination, concurrency, and rollback
  are green.
- No Phase 3 bridge is opened or preinstalled.

If any condition is missing, Phase 2 stays closed and Phase 3 stays closed.
