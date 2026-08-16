# Phase 2：Worker / Provider Profile 阶段契约

[English](phase2-worker-provider-profiles.en.md) ·
[Phase 1 / G4 probe plan](phase1-g4-probe-plan.md) ·
[Phase 3](phase3-zhipu-responses-bridge.md)

状态：**关闭，未获准实施**。本文件保存未来阶段的设计合同，不是已实现能力、安装说明或
打开 Phase 2 的批准。只有 Phase 1 的 P1–P7（含 P5a/P5b/P6a/P6b/P6c）、live G4 证据、
平台回归与安装回滚全部闭合后，才能由一次独立裁决打开本阶段。

## 阶段目标

把当前绑定 `v4_flash_worker`、DeepSeek 和 `deepseek-v4-flash` 的配置抽成最小、声明式
profile，使 plaintext assignment transport 本身不知道具体产品或 provider：

```text
Worker Profile
├── worker identity
├── assignment transport
├── wire transport
└── request normalization
```

三个 transport 维度必须正交：

| 维度 | 候选值 | 含义 |
| --- | --- | --- |
| `assignment_transport` | `native`、`plaintext-v2` | assignment 如何到达真实 Codex child |
| `wire_transport` | `native`、`responses-direct`、`responses-bridge` | child 如何访问自己的 provider |
| `request_profile` | `none`、`deepseek`、`glm-thinking`、… | 已证明必要的 provider/model-family request normalization |

ZHIPU 是 provider，GLM 是 model family，因此候选名称使用 `glm-thinking`，不得把两者
混成一个含混的 profile 名称。

## 不可变边界

- OpenAI parent 始终使用当前 Codex native OpenAI provider、模型与 ChatGPT 登录；profile
  不得改变或代理 parent 流量。
- Codex 原生拥有 discover、spawn、canonical AgentPath、permissions、lifecycle、wait/
  callback、cancel 与 Multi-Agent V2 graph。profile 不能复制或接管这些职责。
- profile 只声明能力和所需 runtime posture，不能授予 mutation、Git、path、completion、
  cost 或 provenance authority。
- assignment 的 authoritative input roots、derived-fact 禁区、real/test boundary、owned/
  excluded paths、verification、stop condition、feasibility/cost contract 仍逐 assignment
  冻结在 immutable capsule 中；profile 不得默认、推断或归一化这些字段。
- credentials 不进入 profile 的可提交值、handoff、capsule、Hook output、日志或 Git。
- Phase 2 最多定义 opaque credential source/reference 的声明位置；不得读取或消费真实
  `ZHIPU_API_KEY`。用户提前准备的 host environment 不是 Phase 2 交付，也不开放任何
  阶段；只有 Phase 3 获准并启动 `zhipu_plan_worker` qualification 后，才可检查其
  present/missing 并使用 host-owned 转发路径，不能读取或记录值。
- Windows 与 POSIX 必须使用同一 protocol/schema，不得形成 provider-specific handoff
  副本。

## 候选声明模型

以下仅表达设计形状，不是可安装配置：

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

实现时应沿用仓库现有的小型文件/数据结构，不为 profile 引入大型 framework。核心
handoff 中不能继续硬编码 `AGENT_TYPE = "v4_flash_worker"`，但也不能复制出
`plaintext_handoff_deepseek`、`plaintext_handoff_zhipu` 等平行协议。

## 获准后的实施顺序

1. 先冻结 Phase 1 G4 的完整 evidence commit 与 live install/rollback 基线。
2. 定义最小 profile schema、validation、unknown-value fail-closed 和稳定 canonical hash。
3. 让 installer、Hook matcher、Skill、Agent template 与 smoke oracle 从同一 profile
   合同派生或受其一致性测试约束。
4. 保持 `$use-v4-flash-worker` 为向后兼容 wrapper/alias，不能让现有 DeepSeek 用户突然
   改用新命令或新数据边界。
5. 先把现有 DeepSeek 路径无行为变化地迁入 profile，再验证 `native` control；不得在同一
   步引入 ZHIPU bridge 或真实 ZHIPU credential。
6. 完成 POSIX/Windows provider-free tests、DeepSeek live regression 与完整回滚后，才可
   独立裁决 Phase 2 complete。

## 资格矩阵

一个新 worker 必须分别通过：

### A. Agent/runtime compatibility

真实 discover、spawn、requested name → canonical AgentPath、parent relation、tool call、
wait、cancel、callback、termination/quiescence 与 resume identity 必须精确。

### B. Assignment transport compatibility

明确选择 `native` 或 `plaintext-v2`。若原生 cross-provider V2 collaboration 已可靠，
不得强行使用 Hook；若选择 plaintext，必须复用 Phase 1 已通过 G4 的唯一协议。

### C. Wire/provider compatibility

明确选择 `native`、`responses-direct` 或 `responses-bridge`，再声明最小 request profile。
仅替换 `model` 或 `base_url` 不能取得资格。

### D. Authority/provenance compatibility

profile 必须声明它能否满足 Phase 1 capsule 与 runtime posture，但 worker narrative、hash、
provider-returned digest 或 PASS 仍只是 contribution evidence。parent/disk/fresh owner 才有
integration authority。

## Phase 2 退出条件

- profile schema、installer、matcher、Skill、Agent template 与 smoke 工件一致；
- 核心 assignment transport 无 DeepSeek/ZHIPU 产品硬编码；
- v4 wrapper 向后兼容，现有 DeepSeek direct Responses route 全绿；
- native worker control 不经过 plaintext Hook 或 bridge；
- credentials 与 parent provider isolation 经静态和 live 证据证明；
- POSIX/Windows parity、callback/cancel/termination、concurrency 与 rollback 全绿；
- 未打开或预装 Phase 3 bridge。

任一条件缺失时，Phase 2 保持关闭；Phase 3 也保持关闭。
