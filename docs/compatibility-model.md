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

authority continuity 与 artifact causal provenance 也是正交维度。SessionMeta、Git
状态、路径和内容 hash 能证明 bytes 在哪里、何时发生变化，不能证明一个 PASS 是从
authoritative input owner 派生，还是从 caller 注入但内部自洽的 derived facts 生成。

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

Phase 2 profile 只能声明某 worker/provider 是否支持该 provenance contract 以及所需的
runtime posture；authoritative input owner、derived facts 和 real/test boundary 仍属于每个
assignment 的 capsule，不能被 provider profile 默认、推断或归一化。wire conversion 也
不得把 provider 返回的 digest/PASS 提升为 provenance proof。

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
    "allow_descendant_head": false,
    "base_index_changed": false,
    "base_git_status_short": "exact initial status"
  },
  "capture_preflight": {
    "expected_root": "/absolute/resolved/git/root",
    "expected_branch": "branch name or null",
    "expected_base_head": "full exact object id"
  },
  "capture_snapshot_sha256": "hex",
  "owned_paths": ["repo-relative/path"],
  "excluded_paths": ["repo-relative/path"],
  "git_authority": {
    "stage": false,
    "commit": false,
    "branch": false,
    "push": false
  },
  "ownership_handover": [
    {
      "prior_assignment_id": "uuid",
      "barrier_sha256": "hex",
      "snapshot_sha256": "hex"
    }
  ],
  "stop_condition": "assigned slice completion only",
  "verification": ["exact command or evidence contract"],
  "authority_provenance": {
    "authoritative_input_owners": ["owner boundary identifier"],
    "authoritative_input_roots": ["repo-relative/input-root"],
    "forbidden_caller_supplied_derived_facts": ["derived authority fact"],
    "test_only_injection_seams": ["explicit non-final seam"],
    "required_derivation_boundary": "owner-internal operation"
  },
  "execution_contract": {
    "posture": "strict_read_only|direct_write_unqualified",
    "review_range": {"base_oid": "full oid", "head_oid": "full oid"},
    "required_invariants": ["state-machine invariant"],
    "diagnostics": {
      "stable_failure_codes": ["OWNER.FAILURE_CODE"],
      "known_true_failure_codes": ["OWNER.FAILURE_CODE"],
      "generic_unclassified_failure_code": "TASK.FAILURE_UNCLASSIFIED",
      "allow_literal_expensive_rerun": false,
      "allowed_failure_code_localities": {
        "OWNER.FAILURE_CODE": ["overall", "per_item"]
      }
    },
    "proven_input_baselines": [
      {
        "baseline_id": "stable id",
        "owner": "authoritative owner",
        "manifest_path": "repo-relative/input-manifest",
        "sha256": "hex",
        "proven_failure_code": "OWNER.FAILURE_CODE",
        "non_authorizing": true,
        "replay_policy": "reuse_without_authority_expansion"
      }
    ],
    "termination_contract": {
      "catalog_closed": true,
      "boundary_catalog": [
        {
          "boundary_id": "stable id",
          "seam": "owner boundary",
          "ordinal": 0,
          "termination_primitive": "os._exit",
          "expected_durable_resolution": "UNJOURNALED|BLOCKED|CANCELLED|COMPLETED|TERMINAL_NOOP"
        }
      ]
    },
    "evidence_binding": {
      "executed_root": "/absolute/resolved/git/root",
      "hashed_root": "/absolute/resolved/git/root",
      "source_identity": {"kind": "git_commit", "value": "full oid"},
      "canonical_output": "repo-relative/evidence.json",
      "no_follow_dirfd_walk": true,
      "terminal_regular_file_reproof": true,
      "preflight_before_expensive_execution": true
    },
    "review_continuation": {
      "prior_assignment_id": "uuid",
      "frozen_cumulative_base_oid": "full oid",
      "prior_review_base_oid": "full oid",
      "prior_review_tip_oid": "full oid",
      "corrected_tip_oid": "full oid",
      "prior_findings_sha256": "hex",
      "unresolved_finding_ids": ["stable finding id"],
      "exact_narrowed_objective": "review only these findings at this tip",
      "require_clean_worktree": true
    },
    "closed_registries": [
      {
        "registry_id": "stable registry id",
        "closed_item_ids": ["exact item id"],
        "count_authority": "mechanical_cardinality_only"
      }
    ],
    "relation_contracts": [
      {
        "relation_id": "stable relation id",
        "owner_schema_fields": ["owner_id", "terminal_state"],
        "handoff_schema_fields": ["handoff_id", "owner_id", "terminal_state"],
        "owner_id_field": "owner_id",
        "handoff_id_field": "handoff_id",
        "handoff_owner_id_field": "owner_id",
        "terminal_state_field": "terminal_state",
        "referential_cardinality": "exactly_one_to_one_nonterminal",
        "absence_semantics": "missing_or_orphan_relation_is_error",
        "allowed_terminal_absence": "tombstone_or_clear_only"
      }
    ]
  },
  "preexisting_dirty": [
    {"path": "repo-relative/path", "status": " M", "kind": "file", "sha256": "hex-or-null"}
  ],
  "assignment_sha256": "hex",
  "created_at": "UTC timestamp",
  "pre_write_attestation_deadline": "UTC timestamp",
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
- authority provenance 冻结 authoritative input owner/root、禁止 caller 注入的派生事实、
  仅测试 seam 与必须重算的 owner boundary。artifact digest 覆盖这些字段仍只是必要条件，
  不能把攻击者选择的 derived inputs 提升为可信来源。
- `strict_read_only` posture 只允许 clean worktree 上的 exact full-OID review range，owned/
  excluded paths 必须为空且所有 Git authority 为 false；它不需要 mutation handover。
- `proven_input_baselines` 是 owner、manifest path、实际文件 hash 与 known-true failure code
  的可复核 replay 证据，必须 `non_authorizing=true`。它不能产生路径/Git/完成权限，也不能
  绕过 owner-internal derivation boundary。
- stable owner failure code 必须原样透传；只有缺失或未分类 code 才能映射到 generic。
  禁止 literal expensive rerun 是 capsule authority，不得因 worker 运行时间长而自行放宽。
- 每个 stable failure code 必须明示允许出现在 `overall`、`per_item` 或两者。合法 locality
  变化不是行为缺失；未声明 locality 也不能被 adapter 静默改写为 generic。最终行为是否满足
  要求仍由 parent fresh adjudicate，不能从 diagnostic 层级自行推断。
- crash claim 必须覆盖闭合的 boundary id/seam/ordinal catalog；`KeyboardInterrupt`、exception
  或 finally unwind 不是 process-death evidence。每个 boundary 必须真实使用 `os._exit`，再由
  owner-internal fresh-process observer 核对一个明示的 durable resolution；公开 API 不接受
  caller 预制的 crash reports，避免再次产生浅层自证。
- evidence runner 在昂贵执行前必须证明 executed root、hashed root、Git source identity 与
  canonical output 属于同一 authority。output 从 root 开始用 no-follow dirfd walk 打开，并在
  结束时重新证明 terminal 仍是同一 regular file identity。
- review follow-up 是新 assignment，不是旧线程 authority 的自然延长。它冻结 prior assignment、
  原 cumulative base、旧 review base/tip、fresh corrected tip、prior-findings hash、未解决
  finding 集合、exact narrowed objective 与 clean worktree requirement；任何一项缺失都不能
  凭 thread continuity 补足。
- worker 列举的 item/test IDs 可以是高容量 contribution，但 narrative aggregate count 没有
  authority。closed registry 冻结 exact IDs；SubagentStop 从 item cardinality 机械重算 count，
  并同时核对顺序、重复与 registry digest。
- strict object codec 只证明单行可解析，不证明 closed-world relation 完整。relation contract
  同时冻结两侧 object schema、非终态 1:1 cardinality、missing/orphan 是 error 的 absence
  semantics，以及唯一 `tombstone|clear` terminal absence 例外；parent/owner 必须 fresh recompute。
- pre-existing dirty hashes 防止 child 把用户修改误报为自己的贡献。
- `capture_preflight` 是 parent 可选的只收窄断言：Hook 只比较 expected root/branch/full
  HEAD 与当前实际 Git snapshot，任何不相等都在 spawn 前 block。它不能授权 branch/commit、
  改写 owned paths 或自行推断新任务。
- `ownership_handover` 只引用 trusted host 在旧 assignment 冻结后创建的 termination+
  quiescence barrier；它不是 child/assignment 可自报的权限字段，也不能清除混合 provenance。

恢复上下文优先重注入一个从完整 capsule 确定性派生的 compact invariant：精确 runtime/
child/parent identity、owned/excluded paths、root/base、Git authority、authoritative input
roots、stop condition 和 completion predicate。完整 capsule/assignment 仍保留在 durable
state；compact copy 不能扩大或替代它。

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
       ↓ worker final attestation 与 disk evidence 一致
reported/<assignment_id>.json
  └─ 仅表示 callback/contribution 已被记录，不表示 parent integration 通过
       ↓ parent fresh verification + causal source review 四维全 PASS
consumed/<assignment_id>.json
```

- pending/claimed/active/consumed/quarantine 的所有转换都在 OS-owned lock 下完成。
- identity mismatch 只拒绝该 claim，不消费、不覆盖、不 quarantine 有效 assignment。
- 只有 JSON/schema/UUID/hash/timestamp/required identity 等 state corruption 才 quarantine。
- initial delivery 后不得删除唯一 authority copy。active 至少保留到 accepted final
  attestation 或安全过期；过期的有写入 capsule 进入 unresolved evidence，不静默删除。
- 旧 child 只能使用已绑定的 child session/agent id；错误 child 或旧 session 不得重领。

### interrupt/cancel 与 ownership handover

`interrupt_agent`/cancel 的返回只表示 control request 已被确认，不等于 child process、已有
PTY、outer executor、MCP 或其他 mutation source 已静默。interrupt ack 不能单独作为
mutation quiescence，也不能授权立即把相同 owned paths 交给新 child。

重派相同/父子重叠 ownership 的顺序必须是：先把旧 active authority 冻结为 unresolved，
再取得 host-owned `child_terminated_and_mutations_quiesced` receipt，最后在 termination 之后
采集 exact root/branch/HEAD/index/status/path hashes。barrier 与 prior assignment/child ThreadId
hash 绑定；新 pending stage 在同一 state lock 内重新检查 state conflict，并在发布前用一次
fresh snapshot 核对 `capture_snapshot_sha256` 与 barrier snapshot，再把 barrier 摘要写入新
capsule。任何 active/pending/claimed/reported conflict、缺失
barrier 或 snapshot drift 都 block。

旧 child 冻结后的任何 PreToolUse 因找不到 active binding 而拒绝。若迟到 mutation 发生在
barrier 后、重派前，capture 记录 `late_mutation_after_interrupt` 与
`overlapping_assignment_provenance` 并拒绝 spawn；若发生在新 capture 后，新 child 首次
attestation 的 exact baseline check 冻结新 authority，并记录相同混合 provenance。若 host
不能证明 termination+quiescence，新 assignment 不得认领相同 owned paths，等待时间或普通
interrupt ack 都不能替代证明。

严格只读的 committed-range review 不认领 mutation ownership，因此不走上述 handover。
它仍须在每次工具调用和 final return 重新核对 compact invariant、clean snapshot 与 exact
review range；若磁盘漂移则停止，而不是把 read-only capsule 升格为 mutation authority。

当前 isolated adapter 只从可信 `PreToolUse(spawn_agent)` 捕获新 assignment；尚未证明 native
follow-up/send-input 的等价可信事件与 immutable receipt。因此 `review_continuation` 目前只是
schema 与 capture fixture，不能声称同一 live child 的 follow-up authority 已 durable 绑定。
在该 Hook surface 被证明前，应使用新的可信 spawn，或把 native follow-up 保持在 parent 自行
fresh review 的 read-only contribution 范围。

混合贡献必须整体冻结，由 parent 以 barrier 前后 hashes、source review 和 fresh tests 裁决；
不能依据后一 child 的 attestation 把所有 bytes 单独归因给后一 assignment。
state lock 不是 filesystem transaction；fresh pre-stage snapshot 之后的剩余窗口仍由新 child
首次 exact attestation 捕获。没有 host quiescence guarantee 时这两个检查都不能升级为强证明。

### 为什么 assignment 不能补足外层不可见性

assignment/capsule 是 child 的模型输入，不是外层 runtime mediation。它不能让
`write_stdin` 产生缺失的第二次 PreToolUse，不能把 opaque Bash 完整分解为路径/Git
副作用，不能为任意 MCP/dynamic/custom/freeform tool 补出可信 side-effect schema，
也不能包住 code-mode outer executor 或保护同 UID 可写的 rollout/state。用户在
assignment 中重复“禁止写入/提交”只能描述意图；它既不能证明 child 遵守，也不能阻断
runtime 看不见的 mutation，且 narrative 还可能在 compaction 后丢失。因此任一负空间
未被外层 runtime/sandbox 实证阻断时，direct-write 必须维持 unqualified/read-only。

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

### pre-write attestation deadline 与 fast-stop

capsule 必须包含短且有界的 `pre_write_attestation_deadline`。首次工具执行前，guard 读取
实际 root/branch/full HEAD/index/status/path hashes，并与 immutable capsule 做完整相等
比较；full HEAD 不能使用前缀比较。首次 mismatch 立即把 active authority 冻结为 unresolved，
禁止任何后续 mutation。首次 attestation 超时也执行相同 fail-closed transition。

Hook event 本身不是 wall-clock timer：如果 child 长时间计算且没有产生任何 Hook event，
PreToolUse 无法自行醒来或 cancel child。因此 bounded fast-stop 还依赖 parent/host 定时调用
isolated watchdog，并在 watchdog 返回 `parent_cancel_required=true` 时 interrupt/cancel child。
没有该外层调度证据就只能证明“下一事件会被拒绝”，不能宣称“deadline 时刻已停止 provider
turn”。这项限制不能用 assignment prompt 补足。
当前 isolated API 只建模 trusted host receipt 的格式与状态转换；Codex 0.147.0 是否公开提供
满足该强语义的 termination receipt 仍未证明。因此 live direct-write handover 继续不合格。

## final-return attestation

child final return 必须包含一个可机读对象：

```json
{
  "assignment_id": "uuid",
  "handoff_id": "uuid",
  "capsule_sha256": "hex",
  "compact_invariant_sha256": "hex",
  "authority_provenance": {
    "policy_sha256": "hex",
    "worker_claimed_origin": "owner_internal|caller|unknown",
    "test_only_injection_used": false,
    "derivation_receipt_sha256": "hex-or-null"
  },
  "canonical_agent_path": "/root/task",
  "recovery_count": 0,
  "context_lost": false,
  "root": "/absolute/resolved/git/root",
  "branch": "branch or null",
  "head": "full commit or null",
  "index_changed": false,
  "git_status_short": "exact text",
  "changed_paths": [{"path": "relative/path", "sha256": "hex"}],
  "verification": [{"command": "exact command", "exit_code": 0}],
  "inventory_summaries": [
    {
      "registry_id": "stable registry id",
      "declared_count": 18,
      "item_ids": ["exact item id"],
      "items_sha256": "hex"
    }
  ],
  "authority_violation": false,
  "assigned_slice_complete": true
}
```

child 无权把 `assigned_slice_complete` 提升为 parent task/feature complete。若 narrative
称无 assignment/无写入，但 consumed handoff 与 owned-path hashes 证明发生写入，事件
分类为 return-context loss；冻结贡献并由 parent fresh verify，不能信 narrative，也不能
仅因 narrative 丢失而丢弃磁盘证据。
同样，`declared_count` 不能由 child narrative 自证。SubagentStop 必须要求 summary 精确覆盖
capsule 的 closed registries，并验证 `declared_count == len(item_ids)`、exact item IDs 与 canonical
digest；任何聚合漂移都 block final return，即使每个 item ID 单独有效。

无 final return 的 watchdog evidence 必须另外分类：baseline root/branch/HEAD/index/status/
path hashes 全部未变为 `unresponsive_no_disk_change`；有磁盘 delta 但未完成首次 attestation
为 `unresponsive_with_disk_change_before_attestation`；已 attested 后有贡献但无返回为
`unresponsive_with_contribution`。只有 child 已返回错误/遗失 narrative 且磁盘存在贡献时才是
`return_context_loss_with_contribution`。这些状态都不是 completion proof，也不能相互替换。
若 capsule 的 location/base 本身不可信，disk delta 不得根据该 baseline 强行计算；结果必须
标记为 `initial_authority_mismatch`、`baseline_comparable=false`、`disk_changed=null`，再由
parent 使用独立可信 baseline 裁决，不能把 HEAD mismatch 误报成贡献。

SubagentStop 的成功只把状态推进到 `reported`。parent 以四个独立维度裁决：location
integrity、mutation-scope integrity、verification freshness、derivation/provenance
integrity。前三者全绿也不能替代第四项：对 attacker-selected derived inputs 计算出的
self-consistent digest 仍可伪造 PASS。只有 owner-internal real-mode derivation（必要时一次
昂贵 derivation 在同一 owner boundary 内复用于多个输出）、fresh verification 与源码级
causal review 都通过，parent 才能推进到 `consumed`。worker tests/hashes 只是 contribution
evidence，不是 integration authority；test-only injection seam 必须显式 non-final。
该 provenance output 只是 worker claim：Hook 可以核对 policy hash 并拒绝显式 caller/
test-only completion，但不能据此证明 child 没有撒谎；receipt digest 同样必须由 parent
回到 owner boundary 复核。

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
| P3 | keyed lifecycle | pending→claimed→active→reported→consumed、expiry、crash recovery | initial delivery 后无 active copy 即失败 |
| P4 | mutation guard coverage | shell、apply-patch、code-mode nested tools、MCP/write apps、Git | 任一写路径绕过即只读降级 |
| P5 | compact/resume continuity | 正确初始写入后 compaction、scope/Git expansion attempt | 扩权产生写入即失败 |
| P5a | pre-write deadline | same-prefix wrong full HEAD、spawn preflight、no-event watchdog/cancel signal | mismatch/timeout 仍进入昂贵 mutation 即失败 |
| P5b | ownership handover | interrupt ack、strong termination receipt、post-termination barrier、late write before/after re-spawn | 无 quiescence 仍重叠认领即失败 |
| P6 | final attestation | no-assignment narrative、slice→parent claim、disk hash mismatch | 不 block 错误 final 即失败 |
| P6a | causal provenance | hash-valid forged derived facts、test-only seam in real mode、owner-internal shared derivation | caller 可自授权 PASS 即失败 |
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
