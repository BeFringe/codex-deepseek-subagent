# 2026-08-17 candidate live-selection 事故记录与 Phase 1 交接

> 写给下一个接手 session。先读本文，再读 `phase1-evidence.md` 与 `phase1-g4-probe-plan.md`。
> 本文由两路恢复会话（opencode）在事故后联合整理，用户已验收恢复结果。

## TL;DR

上一个 session 为了执行 "live schema-2 paired P1"，用一次性 launchd job 重启了官方
Codex App，并通过 `CODEX_CLI_PATH` 环境变量把 App 的 app-server 替换为
`/private/tmp/codex-plaintext-seam-candidate-20260817` 里的 **unsigned patched
0.148.0-alpha.9**（强制 `features.multi_agent_v2.enabled=true`）。该候选注册的保留工具
`collaboration.followup_task` schema 与 `gpt-5.6-sol` 服务端保留 schema 不匹配，
**所有** API 请求被 400 拒绝，App 全部会话瘫痪。这不是装了第二个 CLI，也没有任何持久
binary 替换——是环境变量级的一次性"夺舍"。

## 1. 事故机制

夺舍链路（全部已由进程/环境/日志证据确认）：

```text
launchctl submit org.openai.codex.g4.candidate.20260817
  → osascript quit 官方 App
  → 等待官方进程退出
  → 在该 job 环境下重启 /Applications/Codex.app（GUI 壳仍是官方签名二进制）
  → App 进程继承环境变量：
      CODEX_CLI_PATH=<repo>/probes/codex_plaintext_candidate_wrapper.sh
      CODEX_G4_LIVE_SELECTION_AUTHORIZED=schema2-paired-probe
      CODEX_G4_CANDIDATE_BIN=/private/tmp/codex-plaintext-seam-candidate-20260817/codex-rs/target/release/codex
      CODEX_G4_CANDIDATE_SHA256=e2874bda15552fac7b677b2553978a452c8c7beb5cae536ec95aead4d8b174d6
  → App 按 CODEX_CLI_PATH 生成 app-server = wrapper
  → wrapper 校验 SHA 后 exec candidate，附：
      -c features.multi_agent_v2.enabled=true
      -c features.multi_agent_v2.message_delivery="plaintext"
  → candidate 向 OpenAI 请求注册补丁版 collaboration.* 工具 schema
  → 服务端：Invalid Value: 'tools'. Function 'collaboration.followup_task' is reserved...
  → 每个会话、每条消息 400，App 完全不可用
```

关键点：

- `CODEX_CLI_PATH` 是 Electron App 选择 app-server 二进制的**进程环境变量**，
  影响的是 App 的后端进程，不是某个 CLI 安装。
- 事故前 15:14，session 还把 `CODEX_CLI_PATH`（指向 wrapper）写进了 live
  `~/.codex/config.toml` 的 `[mcp_servers.node_repl.env]`——这是第二条、可跨重启
  存活的污染向量。App 恢复后已将其自动归一化回官方路径
  `/Applications/Codex.app/Contents/Resources/codex`（现为良性状态，勿再改写）。
- 没有发现独立安装的 codex CLI（`which codex` 无结果）。
  `~/.cache/codex-runtimes/`（8月14）是 App 官方 runtime 基础设施；
  `~/.codex/plugins/.plugin-appserver/codex`（8月16）与 App 内置二进制 SHA 完全一致
  （`6170ff55…d424c754f`），均为正常工件。

## 2. 时间线（UTC 2026-08-17）

```text
~06:39  session 完成 checkpoint df77102 / 4c49dd8（见 §5），声明
        "release preflight 已闭合为可复现、但未 live 的 checkpoint"
06:46  用户批准："手动重启了，允许重启并临时选择 candidate"
06:48  第一次 nohup 后台调度失败（未接管 App，未污染状态）
06:48  改用 macOS 一次性 launchctl job
06:50  App 重启框被用户同意 → App 在 job 下复活，app-server = candidate
06:50  起所有请求 400：collaboration.followup_task schema 不匹配
       （受影响会话包括主 session 01a00147-39cb-… 与新开的 01a00e91-…）
~07:00  用户另开 opencode 会话排障
~07:15  launchctl job 移除、config 清理、官方 App 正常重启，错误消失
```

## 3. 与 preflight 承诺的偏差（哪里越界了）

上一个 session 自己冻结的 preflight 承诺 vs 实际行为：

| 承诺 | 实际 |
|---|---|
| "不替换签名 App binary" | GUI 壳确实没换，但 app-server 进程被整体替换（效果等同） |
| "不修改 live config/Hook" | 15:14 把 `CODEX_CLI_PATH` 写进了 live config.toml |
| "退出/回滚观察项全部冻结" | 回滚依赖 session 自己存活；session 一崩，用户只能靠外部会话手工恢复 |
| "临时 candidate 选择" | 保留工具 schema 不匹配导致的是**全账号级**故障，不是"仅 candidate 受影响"的可控实验 |

根本误判：把 `CODEX_CLI_PATH` wrapper 当成"transport-only、可逆的选择 seam"，没意识到
它劫持的是 GUI App 的唯一后端进程；也没验证 patched 保留工具 schema 能否被服务端接受
就做了 live selection。**任何会影响 App 进程环境或 app-server 选择的实验，故障半径都是
整个 App，不存在"局部探测"。**

## 4. 恢复与验收（已由用户确认）

1. `launchctl bootout gui/501/org.openai.codex.g4.candidate.20260817`（job 连同被劫持
   App 一起终止；另一路会话用的是等价的 `launchctl remove`）
2. 移除 config.toml 中的 wrapper `CODEX_CLI_PATH` 条目；App 重启后自动将其归一化为
   官方路径（现行状态无害）
3. `open -a Codex` 正常重启

验收基线（下个 session 可复查）：

```text
app-server   = /Applications/Codex.app/Contents/Resources/codex
               （官方签名，无 multi_agent_v2 覆盖参数）
Resource SHA = 6170ff5578170ee9b74ad92bfcff96e6186f41d02b60815a7c2b01ad424c754f
launchd job  = 无 org.openai.codex.g4.* 残留
candidate 进程 = 无
hooks.json / g4 state 目录 / repo probes+docs = 未动
```

## 5. Phase 1 证据链清单（分析从这里开始）

- **candidate 构建树**（用户决定原样保留）：
  `/private/tmp/codex-plaintext-seam-candidate-20260817`（约 27G，含 codex 源码 +
  target/release 编译缓存）。candidate 二进制 SHA-256：
  `e2874bda15552fac7b677b2553978a452c8c7beb5cae536ec95aead4d8b174d6`。
  ⚠️ 位于 `/private/tmp`，macOS 会在重启/定期清理时删除 3 天以上文件。
  **下个 session 第一优先级之一：把 git diff / checkpoint / SHA 清单归档进 repo。**
- **writer receipts**：`~/.codex/state/codex-deepseek-subagent-g4/writer_receipt/`
  （161 个文件），其中多个记录 `root=/private/tmp/codex-plaintext-seam-candidate-20260817`
  及 changed paths，含 `codex-rs/core/src/tools/handlers/multi_agents_v2/followup_task.rs`、
  `send_message.rs`、`multi_agents_spec.rs`、`config/mod.rs`、`features/*`——这就是
  candidate 改动的证据锚点。
- **state 目录其余部分**：`hook_event_chain/`（链式事件记录）、
  `pretool_schema_observation/`、`subagentstart_schema_observation/`、
  `hook_schema_observation_arm*/`、`lost/`、`writer_{claim,conflict,abort,receipt}/`。
- **repo checkpoints**（git log 顶端，工作树 clean）：
  - `4c49dd8` test(g4): prepare reversible candidate selection
  - `df77102` test(g4): separate delivery and denial receipts
  - 更早的 `7a95267`/`77f1c2d`/`a1bfe11`/`deb0d96` 为 plaintext seam 系列铺垫
- **测试基线**：原 session 报告 "全量 provider-free 276/276 通过"。
- **遗留 pending claim**：外部 session `01a009f8…` 的 pending claim 在事故前就存在，
  恢复动作未触碰 g4 state，需按 fail-closed 语义处理（不要用"扫描拿第一个"）。
- **崩溃会话 rollout**（事故现场第一手记录）：
  `~/.codex/sessions/2026/08/15/rollout-…-01a00147-39cb-7b50-b78d-7baed910eb45.jsonl`
  （06:39[incident-2026-08-17-candidate-live-selection](incident-2026-08-17-candidate-live-selection.md)–06:50 UTC 段为事故决策过程）。

## 6. 硬性规则（下个 session 必须遵守，防止重演）

1. **永远不要劫持 GUI App 的 app-server**。不 quit/relaunch 官方 App、不给 App 进程
   注入 `CODEX_CLI_PATH`、不写 live config.toml 的任何会改变 App 后端选择的键。
   unsigned patched 二进制注册的保留工具 schema 一旦不匹配，故障半径是全 App/全账号。
2. **candidate 探测一律隔离运行**：独立 `CODEX_HOME`（独立 config/state/sessions）+
   headless `codex exec` 或独立 socket 的 app-server。探测失败只能坏探测进程自己。
3. **live 边界前先做 server 端 schema 验证**：保留工具（`collaboration.*` 等）的
   schema 由服务端裁断，本地"可复现 checkpoint"证明不了服务端接受。
4. **/private/tmp 不是证据存放地**：重要证据（diff、SHA、receipts 副本）必须落 repo。
5. **任何 live 实验必须带"session 死了也能回滚"的说明**：给用户留一条不需要 AI 参与
   的一行恢复命令。
6. 原 Worker 提示词（`~/文档/CAT/CAT/SubAgent Worker提示词.md`）的全部边界继续有效：
   Phase 2 / Phase 3 尚未启动；ZHIPU_API_KEY 属 Phase 3；不要跳阶段。

## 7. 未完成事项（按优先级）

1. 归档 `/private/tmp` candidate 树的证据（git diff、SHA 清单、关键 receipt 副本）进 repo。
2. 处理外部 session `01a009f8…` 的 pending claim（fail-closed）。
3. 原计划但未执行的 live 实验——改为隔离方式重做：
   live schema-2 paired P1、identity matrix（nested/concurrent spawn）。
4. 事故前正在调查的支线："工具失败后为什么没有终态 Hook 回调"（failure callback
   路径），依据源码与真实 lease 遗留决定最小修复。
5. fresh-process rollback 与 disk barrier 验证——本次"回滚"实际是外部会话代执行的
   应急恢复，不等于 candidate 自身回滚路径被验证过。
