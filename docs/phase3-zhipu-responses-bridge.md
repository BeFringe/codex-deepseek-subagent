# Phase 3：ZHIPU child optional Responses bridge 阶段契约

[English](phase3-zhipu-responses-bridge.en.md) ·
[Phase 2](phase2-worker-provider-profiles.md) ·
[Phase 1 / G4 probe plan](phase1-g4-probe-plan.md)

状态：**关闭，未获准设计实现或安装**。用户只批准了一个隔离的 direct-Responses
feasibility probe；这不等于打开 Phase 3。Phase 1 G4 通过还不够；只有 Phase 2 profile
稳定、回归与回滚证据闭合并被独立裁决完成后，才能开始本阶段。本文不包含 credential
或可运行 bridge 配置。

## 目标拓扑

为候选 `zhipu_plan_worker` 资格认证 ZHIPU Responses compatibility。实施开始时先核对
ZHIPU 当前 endpoint 是否已直接满足 Codex 所需 Responses 语义；若满足，选择
`responses-direct` 并不部署 bridge。只有 direct 不满足且转换语义可证明时，才提供只服务
该 child 的 optional local Responses bridge：

当前 ZHIPU Coding Plan 官方 Codex 文档已给出 Responses direct 配置：
`base_url = "https://open.bigmodel.cn/api/v1"` 与 `wire_api = "responses"`。这使
“必须建 protocol bridge”不再是默认假设，但只证明 wire 候选。官方手动配置是
全局切换 `model_provider`，不满足本项目 OpenAI parent 保持不变的边界；同时
Codex `0.149.0+` 的 child role 无法覆盖继承的 parent provider。因此 native
`zhipu_plan_worker` 的 provider 入口仍然不可用，Phase 3 继续关闭。

```text
OpenAI parent ─────────────────────────────→ native OpenAI
                                             完全不变

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

bridge 只能是 `zhipu_plan_worker.model_provider.base_url` 的局部 upstream。不得修改
OpenAI parent base URL、截获 parent、合并 Codex native model catalog、代理 Voice/
Realtime/images/background turns，或把本项目变成全局 router。DeepSeek 的
`responses-direct` 路径继续直连；native OpenAI worker 也不经过 bridge。

`responses-direct` 的成功资格会使 bridge 成为不需要安装的 adapter，而不是 Phase 3
失败；两条路径都必须保持 assignment transport 与 parent lifecycle 不变。

## Endpoint 与配置边界

当前官方 Codex 候选 endpoint 是：

```text
https://open.bigmodel.cn/api/v1
```

该值来自 [ZHIPU Coding Plan 的 Codex 文档](https://docs.bigmodel.cn/cn/coding-plan/tool/codex)。
实施前仍必须重新核对官方文档、账户/地区差异与 live behavior。
`open.bigmodel.cn`、`api.z.ai` 或未来 endpoint 的差异应通过 Phase 2 provider profile/
config/env 选择，不得硬编码到 assignment transport core。本文记录候选，不宣称当前
endpoint、模型名或账户权限已经资格认证。

### 2026-09-07 隔离 wire feasibility

当前官方 Codex 页面可直接取得，但没有出现在同日 `llms.txt` 索引中；页面内容 SHA-256、
三次独立 invocation、latency、request/response hash 与只保留结构化摘要的结果固定在
[`../probes/zhipu-responses-direct-feasibility-20260907.json`](../probes/zhipu-responses-direct-feasibility-20260907.json)。
官方示例已使用 `glm-5.3`。第一次 32 output-token 请求取得标准 `response` JSON 并以
`status=incomplete` 结束；最终 384 output-token control 取得 HTTP 200、
`status=completed`、独立 `reasoning`/`message` items 和精确 21 字节 marker。

这把“endpoint 是否真实支持 Responses”从纯文档候选推进为 live wire feasibility，仍然
没有证明 Codex client、streaming、tool call/result、continuation、normalization、callback、
cancel 或 native child。尤其 Codex 的 bounded role projection 仍不允许 child role 选择
不同于 parent 的 provider；所以不能把这次 direct HTTP 正证据写成
`OpenAI parent → native ZHIPU child`。credential 只以 host 环境变量的存在性参与调用，
值未进入 argv、输出、hash、响应留存或 Git。三次 exploratory 调用不是 representative
latency cohort，也没有定义 p95。

## Bridge 与 normalization 职责

优先由 LiteLLM 承担通用 Responses → OpenAI-compatible Chat Completions 转换；只有 live
证据证明 LiteLLM 不满足所需语义时，才评估更窄的补丁，不能自行重写完整 Responses
协议。bridge 必须验证：

- streaming 与中断恢复；
- tool call、tool result、function arguments，尤其 streaming argument assembly；
- usage、reasoning/thinking 与 continued conversation；
- Codex native callback、cancel、timeout 与 error propagation。

外层 `glm-thinking` profile 只做官方文档/live probe 已证明必要的 normalization。逐项
调查 thinking enable 参数、`reasoning_effort` 层级与 high/max 映射、thinking 时是否需
删除 `temperature`/`top_p`、forced/auto `tool_choice`、tool calling 稳定性、maximum
context 和 Responses replay。不得因 DeepSeek/Qwen 的限制而推断 GLM 也要同样降级。

## 安全与隔离

- bridge 默认只监听 loopback，并拒绝非本机 listener 配置的静默升级；
- provider credentials 不写日志、handoff、capsule、transcript 或 Git；
- 实施时 `ZHIPU_API_KEY` 只作为 child provider/bridge 的 host-owned credential source；
  probe 只记录 present/missing，绝不读取、输出、hash 或提交其值；
- parent ChatGPT auth 绝不转发到 external provider；
- 启用 GLM 不修改 OpenAI native provider；
- plaintext assignment 的既有 external-provider 数据边界继续适用；
- bridge 停止或 normalization 失败时，只允许 ZHIPU worker 失败，parent、native worker
  和 DeepSeek direct worker 必须继续可用。

## 资格要求

`curl` 能聊天、SQL-only spike、小 cohort 或 provider 自报 PASS 均不足。至少要取得真实
端到端证据：

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

矩阵至少覆盖：

- read-only text/code task 与本地 search/read tool；
- forced/auto tool behavior、streaming arguments 与 continued conversation；
- failure propagation、bridge unavailable、timeout 与 cancellation；
- concurrent DeepSeek + ZHIPU workers，身份和 callback 不串线；
- parent provider/auth/base URL 始终不变；
- Phase 1 authority/provenance/cost/phase capsule 在 bridge 前后 exact continuity；
- POSIX/Windows parity、安装/卸载与完整 rollback。

## Phase 3 退出条件

- Phase 2 已独立通过，profile 抽象没有为 ZHIPU 特判 assignment transport；
- native per-child provider 入口已可用，且 parent provider/auth/base URL 保持不变；
- endpoint/model/request normalization 均有当前官方资料与 live evidence；
- bridge 的 protocol、tool/callback/cancel/error semantics 通过真实端到端矩阵；
- credentials、loopback 与 parent isolation 有独立 host 证据；
- DeepSeek direct、native OpenAI 与 bridge-down failure isolation 回归全绿；
- 所有安装物可完整回滚，且 rollback 不删除诊断证据。

最终标准不是“ZHIPU 能回答”，而是 bridge 仍是可独立替换/删除的 child wire adapter，
且 OpenAI parent 与 Codex native Multi-Agent V2 lifecycle 从未被代理化。
