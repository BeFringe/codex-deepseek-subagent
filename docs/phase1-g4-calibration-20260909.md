# Phase 1/G4 主线校准（2026-09-09）

[Phase 1 probe plan](phase1-g4-probe-plan.md) ·
[Phase 2](phase2-worker-provider-profiles.md) ·
[Phase 3](phase3-zhipu-responses-bridge.md)

状态：**Phase 1 未完成，`direct_write_qualified=false`**。本附录不降低原始
P1–P7 验收，也不开放 Phase 2/3；它只移除无界样本要求、产品耦合和阶段职责混淆。

## 这条主线实际在证明什么

Phase 1 要证明：在 OpenAI parent 继续使用 Codex native provider、ChatGPT 登录和
Multi-Agent V2 lifecycle 的前提下，
一个异构 child 能收到精确 plaintext assignment，并在 immutable capsule、真实
SessionMeta/canonical AgentPath、mutation mediation、resume、callback、termination 与最终
parent/disk adjudication 的共同约束下安全贡献；未闭合时只能 read-only。

P1–P7 的有限职责如下：

| Gate | 有限职责 |
| --- | --- |
| P1 | 唯一、精确地捕获真实 spawn assignment plaintext；失败时不启动目标 child |
| P2 | requested name 精确绑定真实 SessionMeta、ThreadId、parent edge 与 canonical AgentPath；覆盖 root/nested、serial/concurrent 和 POSIX/Windows 路径合同 |
| P3 | keyed authority 经历 pending→claimed→active→reported→consumed，并对 expiry/crash/orphan fail closed |
| P4 | 枚举并关闭、介入或由可信 sandbox 阻断所有 mutation/control surface；Hook 可见性本身不是信任根 |
| P5/P5a | compaction/resume 后重证 exact capsule；在首次写前处理 Git/base/scope drift 与无事件超时 |
| P5b | interrupt/close 后取得真实 termination、tracked-process exit、post-termination disk barrier 与无重叠 handover |
| P6/P6a/P6b | final attestation、causal provenance 与 feasibility 由 parent/disk/fresh owner 重算，worker narrative/hash 不自授权 |
| P6c | 一个产品无关 live bundle 绑定 invocation/latency authority、dense p95、U1→R→U2、phase conservation、mixed frontier 与十个 race seams |
| P7 | 同一协议的 POSIX/Windows、既有 DeepSeek 路径和安装/回滚回归 |

当前有限矩阵是：P1、P2、P3、P4、P5、P5a、P5b、P6、P6a、P6b、P6c 已
`qualified`；P7 仍为 `partial`。因此不是阻塞在 P1，也不需要“前面一通才全部通”。
P7 的剩余问题只有 native Windows parity。既有 DeepSeek 路径、POSIX native lifecycle、
callback continuity 与隔离的 headless install/reload/rollback 已由产品无关 live receipt
闭合。任何业务仓库、workload 规模或业务侧完成结论都不参与 Phase 1 裁决。

## 三阶段主线

1. **Phase 1 — native lifecycle compatibility and write qualification**：保留 Codex native
   spawn、AgentPath、permissions、wait/callback/cancel 与 Multi-Agent V2，只补 plaintext
   assignment、durable authority、mutation mediation 和 fresh-owner adjudication。其标志性
   节点是 G4：异构 child 能否从 read-only 安全升级为 exact-path direct write。
2. **Phase 2 — Worker / Provider Profiles**：把 worker identity、assignment transport、wire
   transport 与 request normalization 分开配置；不得改写 OpenAI parent provider，也不在
   capsule 中携带 credential。
3. **Phase 3 — external Responses qualification**：优先验证 provider 的 direct Responses；
   只有 direct wire 无法满足 tool/callback/cancel 等语义时才启用局部 bridge。bridge 是
   可删除 fallback，不是默认架构，也不得成为 parent 的全局网关。

## 本轮确认的计划偏移

1. P2/P3 曾被“更广 cohort”保持为 partial，却没有样本数量或新语义阈值。这是无界验收，
   不是原始 gate。当前证据已覆盖真实 root、depth-two nested、serial、concurrent、同一 child
   的后续 message、精确 callback/consumption，以及 expiry/orphan/watchdog 恢复；Windows
   absolute transcript-path 等价 fixture 另由 checker 固定。因此 P2/P3 可独立关闭，剩余
   mutation/quiescence 不再错误挂到这两个 gate。
2. P6c 的有限验收对象是同一个 disposable product-independent live root 内的
   joinable bundle：一组共享 invocation/phase identity 的 dense samples、U1→R→U2、
   mixed frontier 和十个 ordered race seams。不相关应用的数据规模或独立 workload
   运行不属于该 gate。
3. P4 的有限证明域是 exact native qualification actor graph。exact G4 headless candidate 已在
   所有 tool contributor 之后删除非 allowlist runtime，required PreToolUse 对 actor 可达的
   `apply_patch` fail closed，child 不能管理子节点；新增 native spawn admission 又在创建 child
   之前拒绝 default/普通 sibling，阻断通过 sibling 重新取得宽 catalog。独立同 UID 进程或另行
   启动的 App Server 不在该 actor graph 内，也不产生 Phase 1 authority；如果以后有工具重新让
   exact actor 可达这些入口，P4 必须重新打开。
4. Phase 3 不能继续默认等同于“建 ZHIPU bridge”。ZHIPU direct Responses 已有官方候选与
   live wire feasibility；bridge 只在 direct 语义不够时作为可删除 fallback。
5. P6/P6a 曾继续等待未定义的 broader mutation/cross-owner cohort。原始 P6 只要求错误
   final narrative/slice/disk hash 被拒绝并由 fresh owner消费；P6a 要求 forged provenance、
   test-only seam 和 owner-internal derivation 不能自授权。现有 provider-free 与 exact-path
   live mutation evidence 已闭合这些有限门。
6. P6b/P6c 不能靠 SQL-only spike、业务规模或 checker 自报晋级。正式产品无关运行已在同一个
   disposable Git root 中穷举冻结的二十项 dense population，绑定真实 invocation timing、
   四档 multiplicity、五个 equivalence class、U1→R→U2、exact mixed frontier 与十个
   mutation seam；另一个进程从磁盘重算后才晋级。mutation breadth 仍归 P4，platform/
   install regression 仍归 P7。
7. 既有 DeepSeek 路径不再等待业务 workload。最终 live run 在独立临时 Git root 和 handoff
   state 中保留 OpenAI parent，生成真实 DeepSeek child SessionMeta/canonical AgentPath，以一次
   SubagentStart plaintext delivery 驱动一个只读 native tool call，并取得精确 wait/callback、
   consumed state、clean disk 与 fresh-process adjudication。它只晋级 P7 的 DeepSeek、POSIX 和
   callback receipts，不授予 direct write，也不打开 Phase 2/3。
8. 安装/回滚不再要求选择 GUI App Server。最终运行在独立 `CODEX_HOME` 中安装 hash-pinned
   candidate、code-mode host 和 Hook scripts，复用当前 ChatGPT 登录但不读取 auth 内容；安装态
   失败 `apply_patch` 取得同一 tool-use-id 的 Pre/Post callback 并释放 lease。随后所有 managed
   paths 移入可恢复归档，第二个新进程执行同一失败调用且不重建 Hook state，live App 与 v4
   hashes 前后不变。该有限 receipt 已闭合 install/rollback。

## 修正后的执行顺序

1. 保留 P1/P2/P3/P5/P5a/P5b/P6/P6a/P6b/P6c 已 `qualified` 的事实，不再用未定义的
   broader cohort 重新打开它们。
2. P4 已闭合：finalized G4 catalog 完成 trusted-runtime origin binding；required PreToolUse
   fail-closed 由 parent/child 共用的源码谓词与两条 live negative 证明；native spawn admission
   在同一真实 root session 中拒绝普通 sibling、确认拒绝后只有 `/root`，再成功完成唯一精确
   G4 child 的 SessionMeta、SubagentStart/Stop、callback、clean disk 与 fresh-owner consumption。
   现有 macOS Seatbelt negative 另证在刻意开放 Bash 时 read-only sandbox 会阻断实际写入。
3. P5b 以 exact closed-catalog actor 为证明域：现有 source admission freeze、真实
   tracked-exit witness、运行中 write actor close、稳定 disk barrier、唯一 handover 与四个
   原子 writer window 已闭合该门。任意宿主进程的全局 quiescence 不重复挂到 P5b；安装态
   失败回调由 P7 处理。
4. P6b/P6c 已由 disposable product-independent root 的同一次 invocation/phase/race/live
   bundle及 distinct fresh-process disk owner 消费闭合。
5. 当前执行面只剩 P7 的 native Windows parity。
6. 仅当所有 gate 与 exit receipt 均 qualified，才允许一次独立提交把 Phase 1 和 direct
   write 置真并打开 Phase 2；Phase 3 仍需 Phase 2 完成。
