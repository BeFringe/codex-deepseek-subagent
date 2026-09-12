# Phase 3: ZHIPU Child Responses Qualification and Optional Bridge Fallback

[简体中文](phase3-zhipu-responses-bridge.md) ·
[Phase 2](phase2-worker-provider-profiles.en.md) ·
[Phase 1 / G4 probe plan](phase1-g4-probe-plan.md)

Status: **closed and not approved for productization or installation**. Isolated
direct-Responses feasibility and a native cross-provider child have each been
established, but they are not yet one end-to-end Phase 3 qualification and do
not open Phase 3. Passing Phase 1 G4 is not sufficient. Work may start only after
the Phase 2 profile is stable, its regression and rollback evidence closes, and
a separate adjudication marks it complete. This file contains no credential or
runnable bridge configuration.

## Target topology

Qualify ZHIPU Responses compatibility for the candidate `zhipu_plan_worker`.
At implementation start, first determine whether the current ZHIPU endpoint
directly satisfies the Responses semantics Codex needs. If so, select
`responses-direct` and deploy no bridge. Only when direct is insufficient and
translation semantics can be proven should Phase 3 provide an optional local
Responses bridge for this child alone:

The current official ZHIPU Coding Plan instructions for Codex now specify a
direct Responses configuration: `base_url = "https://open.bigmodel.cn/api/v1"`
and `wire_api = "responses"`. This removes “a protocol bridge is necessarily
required” as a default assumption, but establishes only a candidate wire. The
official manual configuration switches the global `model_provider`, which by
itself does not satisfy this project's unchanged-OpenAI-parent boundary. The
current source candidate now uses a parent-owned exact-child provider seam for
one isolated native ZHIPU child path. Phase 3 remains closed because that seam
and direct Responses have not yet passed one joined streaming/tool
continuation/cancellation/termination/platform/rollback qualification, not
because a provider entry is categorically absent.

```text
OpenAI parent ─────────────────────────────→ native OpenAI
                                             unchanged

spawn ZHIPU child
  ├─ Phase 1 plaintext assignment capture
  ▼
zhipu_plan_worker
  │ Responses
  ▼
127.0.0.1 local Responses bridge
  ▼
LiteLLM: Responses → Chat Completions
  ▼
thin GLM request profile / credential forwarder
  ▼
ZHIPU Coding Plan
```

The bridge may only be the local upstream selected by
`zhipu_plan_worker.model_provider.base_url`. It must not alter the OpenAI parent
base URL, intercept parent traffic, merge the native Codex model catalog, proxy
Voice/Realtime/images/background turns, or turn this project into a global
router. DeepSeek remains on `responses-direct`; a native OpenAI worker also
bypasses the bridge.

A qualified `responses-direct` result makes the bridge an unnecessary adapter,
not a Phase 3 failure. Both routes preserve assignment transport and the parent
lifecycle unchanged.

## Endpoint and configuration boundary

The current official Codex candidate endpoint is:

```text
https://open.bigmodel.cn/api/v1
```

This value comes from the
[ZHIPU Coding Plan instructions for Codex](https://docs.bigmodel.cn/cn/coding-plan/tool/codex).
Before implementation, still re-check current official ZHIPU Coding Plan docs,
account/region differences, and live behavior. Differences such as
`open.bigmodel.cn`, `api.z.ai`, or a future endpoint belong in Phase 2 provider
profile/config/environment selection, never in the assignment-transport core.
This file records a candidate; it does not claim that an endpoint, model name,
or account permission is currently qualified.

### 2026-09-07 isolated wire feasibility

The current official Codex page was directly retrievable but was absent from
the same-day `llms.txt` index. Its SHA-256 and the exact request/response hashes,
latencies, and structure-only summaries for three independent invocations are
frozen in
[`../probes/zhipu-responses-direct-feasibility-20260907.json`](../probes/zhipu-responses-direct-feasibility-20260907.json).
The official example now uses `glm-5.3`. A first 32-output-token request returned
a standard `response` object with `status=incomplete`. The final
384-output-token control returned HTTP 200, `status=completed`, separate
`reasoning` and `message` items, and the exact 21-byte marker.

This advances “does the endpoint actually speak Responses?” from a documented
candidate to live wire feasibility. It does not qualify the Codex client,
streaming, tool calls/results, continuation, normalization, callbacks,
cancellation, or a native child. In particular, Codex's bounded role projection
still prevents a child role from selecting a provider different from the
parent's provider, so this direct HTTP result is not evidence for
`OpenAI parent -> native ZHIPU child`. The host credential participated only by
presence and never entered argv, output, a hash, retained response data, or Git.
The three exploratory calls are not a representative latency cohort and define
no p95.

## Bridge and normalization responsibilities

Prefer LiteLLM for generic Responses to OpenAI-compatible Chat Completions
translation. Evaluate a narrower patch only if live evidence proves LiteLLM
cannot satisfy required semantics; do not independently reimplement the full
Responses protocol. The bridge must qualify:

- streaming and interrupted-stream recovery;
- tool calls, tool results, function arguments, and streaming argument assembly;
- usage, reasoning/thinking, and continued conversation;
- native Codex callback, cancellation, timeout, and error propagation.

The outer `glm-thinking` profile performs only normalization proven necessary by
official docs and live probes. Investigate the thinking-enable parameter,
supported `reasoning_effort` levels and high/max mapping, whether thinking mode
requires removing `temperature`/`top_p`, forced/auto `tool_choice`, tool-call
stability, maximum context, and Responses replay. Do not infer GLM degradation
from a DeepSeek/Qwen limitation.

## Security and isolation

- The bridge listens on loopback by default and cannot silently widen to a
  non-local listener.
- Provider credentials never enter logs, handoffs, capsules, transcripts, or
  Git.
- When implementation is approved, `ZHIPU_API_KEY` is only a host-owned
  credential source for the child provider/bridge. Probes record present/missing
  only and never read, print, hash, or commit its value.
- Parent ChatGPT authentication is never forwarded to an external provider.
- Enabling GLM does not modify the native OpenAI provider.
- The existing external-provider data boundary for plaintext assignments still
  applies.
- If the bridge or normalization fails, only the ZHIPU worker may fail; the
  parent, native workers, and DeepSeek direct worker remain available.

## Qualification requirements

A successful chat `curl`, SQL-only spike, small cohort, or provider-reported
PASS is insufficient. Obtain real end-to-end evidence for:

```text
OpenAI parent
→ native spawn_agent
→ exact SessionMeta/canonical AgentPath binding
→ zhipu_plan_worker
→ plaintext handoff
→ Responses bridge
→ ZHIPU Coding Plan
→ required tool call/results
→ native Codex callback
→ parent wait/result
→ strong termination/quiescence and disk barrier
```

The matrix includes at least:

- a read-only text/code task and local search/read tool;
- forced/auto tool behavior, streaming arguments, and continued conversation;
- failure propagation, bridge unavailable, timeout, and cancellation;
- concurrent DeepSeek and ZHIPU workers without identity/callback crossover;
- unchanged parent provider/auth/base URL throughout;
- exact continuity of the Phase 1 authority/provenance/cost/phase capsule across
  the bridge;
- POSIX/Windows parity, install/uninstall, and complete rollback.

## Phase 3 exit conditions

- Phase 2 has independently passed and the profile abstraction contains no
  ZHIPU-specific assignment-transport branch.
- A native per-child provider seam exists while the parent provider, auth, and
  base URL remain unchanged.
- Current official material and live evidence establish endpoint, model, and
  request normalization.
- Real end-to-end tests qualify protocol, tool/callback/cancel/error semantics.
- Independent host evidence establishes credential, loopback, and parent
  isolation.
- DeepSeek direct, native OpenAI, and bridge-down failure-isolation regressions
  are green.
- Every installed artifact can be fully rolled back without deleting diagnostic
  evidence.

The final criterion is not merely “ZHIPU answers.” The bridge remains an
independently replaceable/removable child wire adapter, while the OpenAI parent
and Codex-native Multi-Agent V2 lifecycle are never proxied.
