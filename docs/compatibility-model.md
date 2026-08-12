# Native Codex 异构 Worker 兼容模型

[English](compatibility-model.en.md)

状态：v1 控制面设计，2026-08-12。当前批准 Phase 0 证据与 probe 驱动的 Phase 1
实现，但 Phase 1 尚未通过 G4；Phase 2/3 尚未获准实施。

## 目标与非目标

本仓库是可删除的异构 worker compatibility layer，不是全局 model router：

```text
OpenAI parent ─────────────────────────────→ native OpenAI

custom external child
  ├─ assignment transport compatibility
  └─ child-specific provider wire compatibility
```

Codex 原生拥有 agent discovery、spawn、canonical AgentPath、parent relation、
permissions、lifecycle、wait/callback、cancel 和 Multi-Agent V2 graph。本仓库只拥有：

- assignment transport 的兼容表示；
- worker authority 在 compact/resume 后的连续性约束；
- external provider wire 与必要 request normalization。

assignment transport、wire transport、request profile 是三个正交维度。任一维度的
上游修复都必须能单独替换或删除，不得迫使 OpenAI parent 或其他 worker 经过 bridge。

## 四层兼容模型

### A. Agent/runtime identity

必须分别证明 discover、spawn、requested task name、canonical AgentPath、parent
relation、agent role、lifecycle、wait/callback 和 cancel。`requested_task_name` 是 parent
传入的 path segment；`canonical_agent_path` 是 Codex 从 parent path 派生的运行时
身份。二者不得共用含混的 `task_name` 字段。

### B. Assignment transport

每个 worker 只能选择 `native` 或 `plaintext-v2`。`plaintext-v2` 从可信
`PreToolUse(spawn_agent)` 捕获真实 `spawn_agent.message`；真实 message 仍保持自洽，
Hook 不改写 spawn arguments。transport instance 使用独立 `handoff_id`，不能用
logical task name 充当 handoff identity。

### C. Authority continuity

初始 transport 成功不等于 child 在整个 turn 中持续拥有同一 authority。active
capsule 必须在 child compact/resume 后仍可由 runtime guard 读取。任何不可唯一恢复、
identity mismatch、owned-path 扩张、Git authority 扩张或 stop-condition 扩张都必须
fail closed。

当前 Codex 0.147.0 的源码合同表明：

- `SubagentStart` 只在 thread-spawn child 的 startup 运行；child compact/resume 不会
  再次运行该 Hook；
- `PreCompact`/`PostCompact` 有 child identity 输入，但输出不能注入 additional
  context；
- `PreToolUse` 在 child 中包含 session/turn/agent identity、tool input 与 tool-use id，
  可注入 context、拒绝工具或改写输入；本设计禁止改写真实 spawn input；
- `SubagentStop` 可读取 child final message 与 parent/child transcript paths，并可 block
  final return、向 child 发送 continuation prompt。

因此 Phase 1 的候选闭环是：active capsule 保留在磁盘，所有 mutation-capable tools
先经 `PreToolUse` re-attestation/authority guard，final return 再经 `SubagentStop`
attestation gate。若 live probe 不能证明所有写路径都受 guard 覆盖，则 direct-write
continuity 不成立，只能保留 read-only posture 并记录 upstream limitation。

### D. Wire/provider

worker 独立选择 `native`、`responses-direct` 或 `responses-bridge`，再选择
`request_profile`。provider 与 model family 不混名；ZHIPU worker 的候选 profile 名称
为 `glm-thinking`。credentials 不进入 handoff、capsule、日志或 Git，profile 也不能
扩大 Codex 实际 permission boundary。

## 不可变 boundary capsule

下列逻辑对象在 `PreToolUse(spawn_agent)` 时创建。序列化字段顺序固定，
`capsule_sha256` 对去掉自身后的 canonical JSON 计算：

```json
{
  "schema": 2,
  "assignment_id": "uuid",
  "handoff_id": "uuid",
  "runtime_session_id": "root and descendants shared session id",
  "parent_thread_id": "direct parent thread id",
  "parent_turn_id": "turn id",
  "spawn_tool_use_id": "tool-use id",
  "worker_profile": "v4_flash_worker",
  "agent_type": "v4_flash_worker",
  "requested_task_name": "logical path segment",
  "canonical_agent_path": null,
  "root": {
    "path": "/absolute/resolved/git/root",
    "branch": "branch name or null",
    "base_commit": "full commit or null",
    "allow_descendant_head": false
  },
  "owned_paths": ["repo-relative/path"],
  "excluded_paths": ["repo-relative/path"],
  "git_authority": {
    "stage": false,
    "commit": false,
    "branch": false,
    "push": false
  },
  "stop_condition": "assigned slice completion only",
  "verification": ["exact command or evidence contract"],
  "preexisting_dirty": [
    {"path": "repo-relative/path", "status": " M", "sha256": "hex"}
  ],
  "assignment_sha256": "hex",
  "created_at": "UTC timestamp",
  "expires_at": "UTC timestamp",
  "capsule_sha256": "hex"
}
```

规则：

- `assignment_id` 标识 immutable authority；`handoff_id` 标识一次 transport instance。
- `canonical_agent_path` 只在 runtime metadata 证明后写入绑定记录，不能猜字符串格式。
- capsule 本身不可原地扩大权限。恢复 assignment 必须新建 identity，并显式引用冻结的
  dirty baseline；不得 replay 已消费的 handoff。
- owned/excluded paths、Git authority、stop condition 和 verification 都是 authority，
  不是提示性文字。
- pre-existing dirty hashes 防止 child 把用户修改误报为自己的贡献。

## handoff 与 authority 生命周期

```text
pending/<handoff_id>.json
  └─ PreToolUse 捕获真实 spawn input，尚未绑定 child
       ↓ exact runtime identity match
claimed/<handoff_id>.json
  └─ 绑定 child session/agent id，正在输出初始 context
       ↓ stdout 成功且状态原子更新
active/<assignment_id>.json
  └─ compact/resume 后仍可读；PreToolUse/SubagentStop 共同引用
       ↓ final attestation 与 disk evidence 一致
consumed/<assignment_id>.json
```

- pending/claimed/active/consumed/quarantine 的所有转换都在 OS-owned lock 下完成。
- identity mismatch 只拒绝该 claim，不消费、不覆盖、不 quarantine 有效 assignment。
- 只有 JSON/schema/UUID/hash/timestamp/required identity 等 state corruption 才 quarantine。
- initial delivery 后不得删除唯一 authority copy。active 至少保留到 accepted final
  attestation 或安全过期；过期的有写入 capsule 进入 unresolved evidence，不静默删除。
- 旧 child 只能使用已绑定的 child session/agent id；错误 child 或旧 session 不得重领。

## runtime binding

### Parent capture

`PreToolUse(spawn_agent)` 输入必须精确保存：

- `session_id`, `turn_id`, `tool_use_id`；
- `tool_input.message`, `task_name`, `agent_type`, `fork_turns`；
- parent `transcript_path` 与当前 cwd。

stage 失败必须 block spawn。非 plaintext worker 原样 pass。Hook 不返回
`updatedInput`，以免 transport 层成为第二个 assignment source。

### Child claim

`SubagentStart` 自身不暴露 parent id、task name 或 AgentPath，因此 claim 必须读取它
提供的 child `transcript_path` 中的首条 `SessionMeta`，并联合验证：

- Hook `session_id == SessionMeta.session_id`（root 与 descendants 共享）；
- Hook `agent_id == SessionMeta.id`（child ThreadId）；
- `SessionMeta.parent_thread_id == capsule.parent_thread_id`；
- `SessionMeta.agent_role == capsule.agent_type`；
- `SessionMeta.agent_path` 与 requested task name/parent AgentPath 的关系唯一；
- 预先算出的 expected path（如有）与实际 path 完全一致。

任何零匹配或多匹配都 fail closed。bounded retry 只有在 live probe 证明存在短暂 flush
race 且最终 identity 唯一时才允许。

## compact/resume authority guard

Phase 1 不以 prompt 里的 `TASK.CONTEXT_LOST` 代替 runtime gate：

1. `PreCompact` 记录 recovery epoch，但不能删除 active capsule。
2. child 的每次工具调用由 `PreToolUse` 使用 session/agent id 解析唯一 active capsule。
3. mutation-capable tool 必须先重新注入 capsule 摘要并验证 root、branch/base、owned
   paths、Git authority 与 recovery epoch；不一致直接 block。
4. 无 active capsule、重复绑定或 state corruption 时禁止新增写入/Git/scope expansion。
5. `SubagentStop` 要求 final attestation；缺失或与 disk 不符时 block，并提供只允许
   attestation/`TASK.CONTEXT_LOST` 的 continuation prompt。
6. parent 以 actual disk、Git 和 capsule evidence 裁决；child narrative 只是一项输入。

只缩小任务可以降低 compaction 风险，但不是协议修复。

## final-return attestation

child final return 必须包含一个可机读对象：

```json
{
  "assignment_id": "uuid",
  "handoff_id": "uuid",
  "capsule_sha256": "hex",
  "canonical_agent_path": "/root/task",
  "recovery_count": 0,
  "context_lost": false,
  "root": "/absolute/resolved/git/root",
  "branch": "branch or null",
  "head": "full commit or null",
  "git_status_short": "exact text",
  "changed_paths": [{"path": "relative/path", "sha256": "hex"}],
  "verification": [{"command": "exact command", "exit_code": 0}],
  "authority_violation": false,
  "assigned_slice_complete": true
}
```

child 无权把 `assigned_slice_complete` 提升为 parent task/feature complete。若 narrative
称无 assignment/无写入，但 consumed handoff 与 owned-path hashes 证明发生写入，事件
分类为 return-context loss；冻结贡献并由 parent fresh verify，不能信 narrative，也不能
仅因 narrative 丢失而丢弃磁盘证据。

## 已重建事实、假设与 probes

### 已重建事实

- workflow checkout 为 `main@1377b76`，live install 未修改。
- 现有 repo/live Hook 是 schema 1、按 role 单槽、manual stage、initial delivery 后立即
  删除 claimed state。
- 多次真实事件显示 initial assignment transport 正确且 owned-path changes 落盘；长
  turn compact/recovery 后 final narrative 丢失 assignment，或扩大 Git/scope/completion
  authority。它们是 continuity/final-attestation failure，不是 initial transport miss。
- 本机 `codex-cli 0.147.0`；官方 `rust-v0.147.0` tag 的 peeled commit 为
  `be6e8eac029b183056b7e4402879f15d2c85f61b`。
- 该源码从 parent AgentPath `join(requested task name)` 构造 child path，spawn 返回值的
  `task_name` 实际序列化 canonical path。
- child rollout materialization 会在 Hook 取得 `transcript_path` 时落下 SessionMeta；
  是否在所有支持平台/host 上无 race 仍需 live probe。

### 当前假设

- trusted PreToolUse Hook 能稳定匹配 Codex 对 `spawn_agent` 的 canonical tool name。
- child `SessionMeta` 在 SubagentStart 时已包含完整 parent/path/role；源码支持这一点，
  但 root/nested/concurrent live behavior 尚未资格认证。
- 所有 direct-write 路径都能被一组可枚举的 PreToolUse matcher 覆盖。
- SubagentStop block 在真实 external child callback 中可可靠生成 continuation turn。

### Phase 1 probe matrix

| Probe | 目标 | 必须覆盖 | Gate |
|---|---|---|---|
| P1 | 捕获真实 spawn input | pass/block、非目标 worker、无 input rewrite | stage 失败仍 spawn 即失败 |
| P2 | SessionMeta flush | root/nested、serial/concurrent、POSIX；Windows 等价 fixture/live | identity 不唯一即停止 |
| P3 | keyed lifecycle | pending→claimed→active→consumed、expiry、crash recovery | initial delivery 后无 active copy 即失败 |
| P4 | mutation guard coverage | shell、apply-patch、code-mode nested tools、MCP/write apps、Git | 任一写路径绕过即只读降级 |
| P5 | compact/resume continuity | 正确初始写入后 compaction、scope/Git expansion attempt | 扩权产生写入即失败 |
| P6 | final attestation | no-assignment narrative、slice→parent claim、disk hash mismatch | 不 block 错误 final 即失败 |
| P7 | parity/regression | POSIX/Windows protocol、DeepSeek existing path | 全绿后才能进入 Phase 2 |

## Decision gates

- **G0 — model accepted**：本文件经审查，事实与假设分离。
- **G1 — spawn capture**：P1 证明真实 message 是唯一 assignment source。
- **G2 — exact child binding**：P2 证明无需弱化为“下一个同 role child”；否则记录
  upstream limitation 并停止 direct-write Phase 1。
- **G3 — durable enforcement**：P3–P6 证明 compact/resume 后写入与 final return 都受
  capsule gate。prompt-only re-attestation 不通过此 gate。
- **G4 — Phase 1 complete**：schema/hash、mismatch preserve、corrupt quarantine、
  nested/concurrent、expiry/recovery、Windows/POSIX 与 DeepSeek regression 全绿，并记录
  live evidence。G4 前禁止 Phase 2；Phase 2 前禁止 Phase 3。

## Rollback

- Phase 0/1 开发只改仓库，不覆盖 live Hook/skill/state。
- schema 2 与 hook matchers 在未资格认证前使用隔离 state directory/config。
- 保留 v4 wrapper/alias；失败时恢复到已记录的 schema 1 repo baseline，不伪造 continuity
  guarantee。
- 不修改 OpenAI parent provider/base URL，不把 bridge 放进全局配置。
- 不自动删除 quarantine/unresolved evidence；回滚只切换 adapter 选择，不抹除证据。

## 当前 dirty diff 所有权基线

下列文件在本支线开始前已修改，属于用户/前序工作。本支线不得 reset、checkout 或
覆盖；后续若必须编辑，先以这些 SHA-256 作为三方合并基线：

| Path | Existing diff | SHA-256 at audit |
|---|---:|---|
| `README.md` | 1+/1- | `ae0395d95310cf043348fa5afa2dfaa6ed12e8e42d8ae4e2c09d0638a30dff5a` |
| `README.en.md` | 1+/1- | `ab8dd3a59bcb615fd7e58f12bc973bd616585493347a817e6ddbe542ea4d6fe3` |
| `docs/advanced.md` | 1+/1- | `99fab3fd999f45a1a54412f318c99089748a6493d853f6f90f75bf030f31e8a1` |
| `docs/advanced.en.md` | 1+/1- | `6bdfbee6a3fe056004bb16eda09271c4117ad29ced40cf873964a790648bfce4` |
| `tests/test_plaintext_handoff.py` | 144+ | `a1061c3276c604b9bb608061b17198a52f50432b203da8a39a3f19e6b00e2689` |

## Codex 0.147.0 源码证据

以下是版本锁定的源码观察，不冒充跨版本公开保证：

- [`PreToolUse` input/output schema](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/hooks/src/schema.rs)
- [SubagentStart 仅在 child startup 分发](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/hook_runtime.rs)
- [compact Hook 是无 context 输出的 gate](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/hooks/src/events/compact.rs)
- [SubagentStop 可 block 并生成 continuation](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/hooks/src/events/stop.rs)
- [requested task name → canonical AgentPath](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/tools/handlers/multi_agents_common.rs)
- [V2 spawn 返回 canonical path](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs)
- [SessionMeta identity fields](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/protocol/src/protocol.rs)
- [Hook session id 是 root/descendants 共享 identity](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/session/session.rs)
- [Hook transcript materialization test](https://github.com/openai/codex/blob/be6e8eac029b183056b7e4402879f15d2c85f61b/codex-rs/core/src/session/tests.rs)

未找到能够把上述源码行为提升为长期稳定 API guarantee 的官方文档。因此每个最低支持
Codex baseline 都必须重新运行 probes；若 contract 改变，adapter fail closed，而不是
靠 prompt 猜测兼容。
