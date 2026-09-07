[Back to quick install](../README.en.md) · [简体中文](advanced.md)

# Advanced notes

This page is for users who want to inspect the implementation, change the
compatibility strategy, or contribute platform evidence. To install and use the
worker, follow the [three-step README](../README.en.md).

## Composition boundary

The original route targeted an unchanged OpenAI parent model, provider, and
ChatGPT login, with DeepSeek only in the standalone `v4_flash_worker` child.
Codex would retain native ownership of child creation, identity, permissions,
lifecycle, cancellation, waiting, and callbacks; this repository would repair
assignment transport only.

That standalone custom-agent route now has historical evidence only for Codex
`0.148.x` and earlier. Starting in `0.149.0`, OpenAI Codex bounds agent-role
overrides: the child retains the parent's model provider, so
`model_provider = "deepseek"` in the role can no longer form an OpenAI parent
→ DeepSeek child. A `SubagentStart` plaintext Hook can repair assignment
representation, but cannot cross that provider-inheritance boundary. The
combination therefore remains fail closed on current versions and must not be
installed or described as live-compatible.

Utopia now uses MixAgents Broker to start an independent Codex App Server
worker. That is a different architecture. It does not satisfy this Phase 1
contract's fixed native AgentPath/wait/callback/cancel/Multi-Agent V2 lifecycle
and cannot serve as P7 evidence.

## Adapting another provider/model

Using different provider/model pairs for the main task and child remains a
desired general composition capability, but it is not a capability provided by
Codex `0.149.0+` custom-agent roles. The current
[Codex config reference](https://learn.chatgpt.com/docs/config-file/config-reference#model_providersidwire_api)
defines `responses` as the only supported `wire_api` value for a custom model
provider. Re-check the project's pinned Codex baseline for every qualification;
do not keep describing Chat Completions as a parallel direct Codex wire. An
external provider that only supports Chat Completions needs a separately
qualified, local `responses-bridge`, never a proxy for the OpenAI parent.

A new worker must pass three orthogonal layers, not one “provider can chat” test:

1. **Agent/runtime compatibility:** real discovery, spawn, requested-name to
   canonical-AgentPath binding, parent relation, tool calls, wait, cancellation,
   callback, resume, and termination.
2. **Assignment transport compatibility:** explicitly select `native` or
   `plaintext-v2`. Do not use the Hook when native V2 collaboration is reliable;
   otherwise reuse the single plaintext protocol that passed G4.
3. **Wire/provider compatibility:** explicitly select `native`,
   `responses-direct`, or `responses-bridge`, then declare only proven request
   normalization.

The standalone Agent must also acquire its own authentication safely without
switching the parent provider; the model must reliably support the tools needed
by the job; and the user must accept that the external provider receives child
assignment, context, and tool results. See the complete future qualification
contracts in [Phase 2 Worker / Provider Profile](phase2-worker-provider-profiles.en.md)
and [Phase 3 ZHIPU Responses bridge](phase3-zhipu-responses-bridge.en.md). Both
stages remain closed.

The ready-made artifacts in this repository remain deliberately bound to
`v4_flash_worker` and DeepSeek. The agent template, authentication, Hook
matcher, script role, skill, `AGENTS.md` index, and smoke oracles must be renamed
and requalified as one coherent set. Replacing only `model` or `base_url` does
not establish that a new combination works.

## Tested baseline

| Component | Tested version or route |
| --- | --- |
| Codex Desktop for Windows | `26.727.6591.0` |
| Codex CLI | `0.146.0` |
| Multi-agent route | V2, `fork_turns="none"`, `SubagentStart` plaintext Hook |
| DeepSeek model alias | `deepseek-v4-flash` |
| DeepSeek documented version | `DeepSeek-V4-Flash-0731` |
| Date | Windows live baseline `2026-08-05`; Windows/POSIX hardening `2026-08-08`; Windows `env_key` control `2026-08-12` |

This table is a historical baseline for the pre-`0.149.0` route, not a current
Codex installation-compatibility promise. Exact-source oracles for
`0.150.0-alpha.8` and `0.153.4` both prove that child roles retain the parent
provider. Utopia likewise marks this package as a legacy route for `0.148.x`
and earlier.

The Windows Desktop route has an OpenAI parent → DeepSeek child → native
callback baseline; the hardened PowerShell implementation passes the local
protocol, concurrency, and recovery tests and still needs a post-hardening
live smoke.
[Issue #6](https://github.com/Utopia-V/codex-deepseek-subagent/issues/6) adds a
controlled comparison: the Windows Desktop child/callback succeeded after
inheriting `env_key`, while the same Agent's User/HKCU command auth was
unavailable under a sandbox identity.
On macOS, the Python/POSIX route has passed the same callback flow on Codex
`0.146.0` and 31 protocol tests; Linux uses the same POSIX implementation.

Codex `0.145.0` marked configurable subagent models and reasoning effort in
Multi-agent V2 stable. Custom agents, Hooks, and cross-provider transport still
evolve, so prefer a current stable release.

## Installed files and configuration

| Path | Purpose |
| --- | --- |
| [`agents/v4-flash-worker.toml`](../agents/v4-flash-worker.toml) | Default Windows/macOS/Linux `env_key` agent template |
| [`agents/macos-keychain/v4-flash-worker.toml`](../agents/macos-keychain/v4-flash-worker.toml) | Optional macOS Keychain authentication template |
| [`agents/windows-live-env/v4-flash-worker.toml`](../agents/windows-live-env/v4-flash-worker.toml) | Optional Windows User/HKCU command-auth compatibility template |
| [`skills/use-v4-flash-worker/SKILL.md`](../skills/use-v4-flash-worker/SKILL.md) | Lazy-loaded selection, delivery, waiting, and failure protocol |
| [`hooks/plaintext-handoff.ps1`](../hooks/plaintext-handoff.ps1) | Windows stage / Hook script |
| [`hooks/plaintext_handoff.py`](../hooks/plaintext_handoff.py) | macOS/Linux Python 3 script |
| [`hooks/hooks.windows.example.json`](../hooks/hooks.windows.example.json) | Windows Hook structure template |
| [`hooks/hooks.posix.example.json`](../hooks/hooks.posix.example.json) | macOS/Linux Hook structure template |
| [`snippets/AGENTS.md`](../snippets/AGENTS.md) | Two-rule parent skill index |
| [`prompts/install-with-codex.md`](../prompts/install-with-codex.md) | Idempotent installation contract for Codex |
| [`prompts/quick-smoke-test.md`](../prompts/quick-smoke-test.md) | Checkout-free quick smoke |
| [`prompts/smoke-test.md`](../prompts/smoke-test.md) | Contributor tool and SHA-256 smoke |
| [`prompts/message-handoff-probe.md`](../prompts/message-handoff-probe.md) | Raw V2 message-only diagnostic |

Agent registration, `model_provider`, and `[model_providers.deepseek]` remain
inside the standalone agent file. Top-level configuration gains neither
`[agents.v4_flash_worker]` nor `[model_providers.deepseek]`, and the main task
provider stays unchanged. When the user trusts the Hook, Codex may write a
`hooks.state` trust hash to top-level `config.toml`; the installer never forges it.

`model_reasoning_effort` is intentionally absent so the parent can choose per
task. `model_context_window = 1000000` describes provider capacity; it neither
forces 1M-token requests nor guarantees unchanged performance near a full
window. `sandbox_mode = "read-only"` is a mutation default, not a disclosure
boundary. Under the current bounded agent-role projection, that role-file field
also does not override the child's permission profile: the child preserves the
parent permissions. It therefore cannot serve as current per-child sandbox
evidence without a separate effective parent/host boundary and receipt.

## Optional macOS Keychain authentication

The portable template authenticates with `env_key = "DEEPSEEK_API_KEY"` and is
also the macOS default. If the Codex Desktop launch path does not inherit the
shell environment, explicitly ask the installer to use the separate Keychain
template. The two templates are mutually exclusive, and the installer never
silently migrates a working installation between authentication mechanisms.

Create a generic password item in Keychain Access with:

- service/name: `io.github.utopia-v.codex-deepseek-subagent.deepseek-api-key`
- account: the current macOS short user name printed by `/usr/bin/id -un`
- password: the DeepSeek API key

Then include “use the repository's macOS Keychain authentication template” in
the installation request. The template retrieves the password with
`/usr/bin/security` and writes it only to Codex's authentication channel through
the shell's built-in `printf`; the key is not placed in an external `printf`
process's argv. This existence probe does not read the password value and
reports only `present` or `missing`:

```sh
SERVICE='io.github.utopia-v.codex-deepseek-subagent.deepseek-api-key'
ACCOUNT=$(/usr/bin/id -un)
if /usr/bin/security find-generic-password -s "$SERVICE" -a "$ACCOUNT" >/dev/null 2>&1; then
  printf '%s\n' present
else
  printf '%s\n' missing
fi
```

The repository currently has structural validation for this template's TOML,
authentication command, and secret-safe probe. macOS Keychain authorization
prompts and a live provider call are not yet claimed as evidence.

## Windows authentication boundary

Windows now defaults to the portable `env_key` template too. After setting the
user variable, fully quit and restart Codex Desktop so the new process actually
inherits `DEEPSEEK_API_KEY`.

The optional `windows-live-env` template reads User/HKCU through command-backed
authentication, but that User scope belongs to the command's actual process
identity. [Issue #6](https://github.com/Utopia-V/codex-deepseek-subagent/issues/6)
observed Codex Desktop using `CodexSandboxOffline`, which could not see the
logged-in user's HKCU. The failure occurred before
`SubagentStart` and was unrelated to the plaintext Hook. This diagnostic emits
only the identity and Boolean presence values, never the key:

```powershell
[pscustomobject]@{
  Identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  ProcessEnvPresent = -not [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)
  UserScopePresent = -not [string]::IsNullOrWhiteSpace(
    [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
  )
}
```

The default `env_key` route depends on `ProcessEnvPresent`.
`UserScopePresent` only explains the optional command-auth behavior and does not
prove that the Codex provider can read the value.

## Autonomous routing and context cost

Installing the custom agent makes it discoverable; it does not force parents to
use it. Personal `AGENTS.md` keeps only a two-rule `$use-v4-flash-worker` index.
The complete protocol loads only when the parent actually considers the worker.

Flash fits bounded, text-first code, log, search, extraction, enumeration, and
reading work that produces much more raw material than useful final evidence.
Keep tightly coupled reasoning, consequential decisions, verification, and
final integration in the parent. Use a multimodal worker for image understanding.

## Why V2 currently needs the Hook

Ideal Multi-agent V2 semantics let the parent place a self-contained assignment
in `spawn_agent.message` without giving the child root-task history. On the
current OpenAI-parent to non-OpenAI custom-child route, however, the parent may
produce provider-internal ciphertext for the collaboration argument. Codex
creates the correct DeepSeek child, but its visible `Payload:` is empty and the
task exists only as `encrypted_content` that DeepSeek cannot interpret.

[openai/codex#35845](https://github.com/openai/codex/pull/35845) added a
plaintext collaboration branch, but it activates only when the call already
carries the explicit plaintext marker. A real OpenAI parent may already have
produced ciphertext, so releases containing that change can still reproduce the
defect:

- This repository's
  [Issue #1](https://github.com/Utopia-V/codex-deepseek-subagent/issues/1):
  `fork_turns="1"` inherits the root task rather than a later parent-derived
  child assignment and can make the child mistake itself for the root.
- [openai/codex#34833](https://github.com/openai/codex/issues/34833): a V2
  cross-provider child cannot consume its encrypted assignment.
- [openai/codex#36376](https://github.com/openai/codex/issues/36376): the defect
  remains on `0.147.0-alpha.4` after #35845 and explains why the plaintext branch
  does not activate.

This is a representation failure for the task contract at the cross-provider
boundary, not a failure of the DeepSeek model, Responses API, agent discovery,
or native callback.

## Preferred route: one-shot plaintext handoff

`$use-v4-flash-worker` executes this protocol:

1. The parent forms one complete, self-contained child assignment.
2. It stages the assignment through stdin into a single-slot local state with a
   TTL.
3. It immediately creates a native child with a unique task name, the exact
   `v4_flash_worker` role, and `fork_turns="none"`.
4. The trusted Hook atomically claims the task on that role's `SubagentStart`
   and injects developer context through `hookSpecificOutput.additionalContext`.
5. The child returns through the native callback; the parent uses an idle wait,
   not polling.

Both implementations use an OS-owned nonblocking dispatch lock: POSIX uses
`flock`, while Windows uses an exclusive file handle. The lock covers staging,
Hook claim, delivery output, and consumption; workers that have already started
can still run concurrently. Malformed claims are quarantined and block the
next stage. TTL recovery applies only to a structurally valid pending item or
an expired claim with no live holder. Never spawn after a failed stage; spawn
only after the occupied state is explicitly clear and a complete new stage
succeeds. Current V2
`send_message` and `followup_task` calls can cross the same encryption boundary,
so each Flash child receives one self-contained job. Start a new child when
essential task information changes.

The assignment briefly exists as plaintext in local user state before being
sent to DeepSeek. The Hook is a transport compatibility layer, not a
confidential channel. Default state locations and the threat boundary are in
[SECURITY.md](../SECURITY.md).

## Optional compatibility routes

### Multi-agent V1

Codex builds that still expose the feature switch can select V1 for an entire
new top-level task:

```text
codex --disable multi_agent_v2
```

Or set this in a trusted configuration layer where V1 is an intentional
persistent choice:

```toml
[features]
multi_agent_v2 = false
```

V1 does not use the affected V2 encrypted collaboration path, so it is a valid
explicit workaround. The reporter on this repository's Issue #1 also confirmed
that V1 restored delivery. It is not a per-spawn parameter: it changes the
top-level session's multi-agent implementation and accepts build-specific V1/V2
differences in tools, roles, concurrency, model overrides, identity restoration,
and navigation. The default installer never switches the whole session silently.

### Inherited turns

A positive `fork_turns` value can inherit only turns that already exist. It
cannot carry a child assignment formed later inside the parent. More inherited
history expands the DeepSeek data boundary and identity ambiguity; it does not
turn a missing V2 message into plaintext and is not an autonomous-delegation
fallback.

## Upstream migration condition

Restoring the native cross-provider route requires two independent conditions:

1. Codex provides bounded per-child provider/profile selection while keeping
   the OpenAI parent provider unchanged.
2. Spawn assignments and essential follow-ups are reliably represented as
   provider-neutral plaintext before invoking the external child provider,
   while identity, permissions, cancellation, and callback semantics remain
   truthful.

Either missing condition is fail closed. A Hook can address only the second
layer; it cannot create the provider authority missing from the first.

## External references

DeepSeek documents `deepseek-v4-flash` as `DeepSeek-V4-Flash-0731`, with a 1M
context window, Tool Calls, and Responses API support. Its Responses
implementation is stateless and only partially implements several fields;
consult live documentation for prices and compatibility.

- [Codex: Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex: Other models and providers](https://learn.chatgpt.com/docs/models#other-models)
- [Codex: Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference#configtoml)
- [Codex 0.145.0 release](https://github.com/openai/codex/releases/tag/rust-v0.145.0)
- [Codex PR #39299: restrict agent-role configuration overrides](https://github.com/openai/codex/pull/39299)
- [Current Utopia package boundary](https://github.com/Utopia-V/mixagents/tree/main/packages/codex-deepseek-subagent)
- [DeepSeek: Responses API](https://api-docs.deepseek.com/zh-cn/guides/responses_api)
- [DeepSeek: Models and pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)
