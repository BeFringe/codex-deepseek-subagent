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

当前有限矩阵是：P1、P2、P3、P5、P5a、P5b、P6、P6a、P6b、P6c 已
`qualified`；P4、P7 仍为 `partial`。因此不是阻塞在 P1，也不需要“前面一通才全部通”。
P4 的剩余问题是 Hook/ToolRouter 之外的 host-control 与 OS/权限信任根；P7 的剩余问题是
Windows、既有 DeepSeek 路径以及安装态失败回调/回滚。外部业务会话没有 Phase 1
裁决职责，只能在自然发生异常时贡献带原始 identity/hash/timeline 的事故样本。

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
3. P4 的主要阻点不是继续微调 Hook matcher。exact G4 headless candidate 已能在所有 tool
   contributor 之后删除非 allowlist runtime；但 Hook 错误仍可能 fail open，普通 GUI parent、
   App Server/daemon/control client、同 UID state/rollout 改写和独立进程仍在 ToolRouter 之外。
   这要求 mandatory runtime gate 加 OS/不同权限信任根，不能靠 prompt、claim refresh 或
   更多 after-the-fact hash 代替。
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

## 修正后的执行顺序

1. 保留 P1/P2/P3/P5/P5a/P5b/P6/P6a/P6b/P6c 已 `qualified` 的事实，不再用未定义的
   broader cohort 重新打开它们。
2. P4 的 finalized G4 catalog 已完成 trusted-runtime origin binding；required PreToolUse
   fail-closed 由 parent/child 共用的源码谓词、exact parent missing-handler live denial 与
   exact child partial multi-handler failure live denial 共同闭合。无需再跑 actor×failure
   笛卡尔积。P4 下一步只处理 ToolRouter 外的同 UID hostile host、独立 App Server/daemon/
   control client、已打开进程输入和 external worker bootstrap 的 OS/privilege boundary。
3. P5b 以 exact closed-catalog actor 为证明域：现有 source admission freeze、真实
   tracked-exit witness、运行中 write actor close、稳定 disk barrier、唯一 handover 与四个
   原子 writer window 已闭合该门。任意宿主进程的全局 quiescence 不重复挂到 P5b；独立
   host-control 与同 UID 攻击仍由 P4 处理，安装态失败回调由 P7 处理。
4. P6b/P6c 已由 disposable product-independent root 的同一次 invocation/phase/race/live
   bundle及 distinct fresh-process disk owner 消费闭合。
5. 当前执行面收束为 P4 的 host/OS trust boundary 与 P7 的 native Windows、DeepSeek
   regression、安装态失败 callback 和完整 live install/rollback。
6. 仅当所有 gate 与 exit receipt 均 qualified，才允许一次独立提交把 Phase 1 和 direct
   write 置真并打开 Phase 2；Phase 3 仍需 Phase 2 完成。
