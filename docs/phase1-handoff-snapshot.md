# Phase 1 临时换机交接任务快照

> 临时性：本文件只用于跨电脑恢复任务上下文。它在原始 handoff 提交后仍可能追加新反馈；
> 新环境完成接管后，应以单独提交删除本文件，不要逐个 revert handoff 更新，也不得回退其
> 前面的 Phase 1 实现提交。

## 结论

**Phase 1 尚未完成。** Repo-side 的 schema v2、isolated runtime/control fixtures、
provider-free tests 与 compatibility model 已形成连续 checkpoint，但 G4 所要求的 live
mutation-surface、真实 child identity/event binding、sandbox trust、termination/quiescence、
Windows/POSIX parity 和 DeepSeek live regression evidence 尚未闭合。

因此当前硬状态保持：

- `direct_write_qualified=false`；
- external heterogeneous worker 只能按已证明边界保持 read-only/unqualified；
- Phase 2 worker/provider profile 与 Phase 3 ZHIPU/GLM bridge 不得开始；
- OpenAI parent 继续使用 Codex native OpenAI provider、当前主模型和 ChatGPT 登录，不经过本项目 router/bridge。

## 快照身份

- 日期：2026-08-14（Asia/Shanghai）
- 仓库：`git@github.com:BeFringe/codex-deepseek-subagent.git`
- 分支：`main`
- 本临时交接文档之前的实现 checkpoint：
  `9bc00342857e430e4d5533ef3e3fa1d60d637ad1`
- 原始 Phase 0 起点：`main@1377b76`
- Source task：`019fe3c5-e3cc-7050-92f6-49136b0a57b3`
- Compatibility model：`docs/compatibility-model.md`
- Provider-free evidence：`docs/phase1-evidence.md`
- Mutation matrix：`probes/codex-0.147.0-mutation-surfaces.json`

新环境不得假定本机绝对路径仍存在。应先 clone/fetch，然后用 Git root 解析所有路径。

## 原始任务目标与边界

### 设计要求

1. 把 DeepSeek one-shot 教程演化为可验证、可替换的 heterogeneous-worker compatibility layer。
2. Codex native 继续拥有 spawn/AgentPath/permissions/lifecycle/wait/callback/cancel/Multi-Agent V2；
   本项目只处理 assignment transport compatibility、authority continuity 与 external provider wire compatibility。
3. Assignment transport、wire transport、request normalization 三维正交，可独立替换或移除。
4. Immutable capsule 必须绑定 runtime/parent/child identity、root/branch/full base OID、owned/excluded
   paths、Git authority、stop condition、verification、pre-existing dirty hashes 与 causal provenance。
5. Compaction/resume 后，每次 mutation-capable tool 与 final return 都必须重新取得并证明同一 durable authority。
6. Parent/disk/fresh owner evidence 优先于 worker narrative；worker contribution 不能自行消费 completion。
7. 任何 mutation negative space、identity ambiguity、state trust 缺口或 termination/quiescence 缺口都必须 fail closed。
8. Credentials 不进入 capsule、handoff、log 或提交；不得读取、显示或转发 API key。

### 明确不做

- 不修改任何产品项目或把产品 Spec/workflow 语义写入 adapter。
- 不覆盖或重装仍在使用的 live Hook/skill/state，直到独立 G4 gate 明确授权。
- 不用正在被改造的 external worker 证明自身正确性。
- 不因测试全绿、磁盘 hash 自洽或 child completion narrative 提前宣布 Phase 1 完成。
- G4 前不进入 Phase 2；Phase 2 前不进入 ZHIPU/GLM provider bridge。

## 已实现的 repo-side checkpoint

以下是“已实现”，不是 live qualification：

- 四层兼容模型：runtime identity、assignment transport、authority continuity、wire/provider。
- Schema v2 keyed `pending → claimed → active → reported → consumed|unresolved` 状态机。
- Parent `PreToolUse(spawn_agent)` 捕获真实 message/task/role/fork/root/full OID；native message 仍是唯一 assignment source。
- Requested task name、canonical AgentPath、handoff id、runtime session、parent/child ThreadId 分离建模。
- Active capsule 与 compact invariant 在 initial delivery 后保留；PreCompact 只增加 recovery epoch。
- 每次 synthetic PreToolUse 重新读取 SessionMeta、active capsule 与真实 Git/path snapshot。
- Pre-write deadline、wrong full-OID fast-stop、watchdog termination classification。
- Interrupt/cancel 与 mutation quiescence 分离；overlapping ownership 需要 host termination receipt + post-termination barrier。
- SubagentStop exact attestation、closed registry count、relation closure、slice overclaim 和 disk/hash/status 裁决。
- Parent `reported → consumed` 五维裁决：location、mutation scope、verification freshness、
  derivation provenance、feasibility contract。
- Causal provenance guard：real mode 不接受 caller-supplied derived authority；test-only seam 必须 non-final。
- Feasibility contract：budget unit/cardinality domain、lower bound、scale witness/monotonicity、
  owner-derived equivalence grouping 与 fan-out conservation。
- Recovery artifact identity 只作为 baseline，不扩大 `owned_paths`。
- Mutation surface matrix 与 same-UID state/rollout trust negative probe 都保持 direct write unqualified。

关键提交从旧到新可通过以下命令重建：

```bash
git log --oneline --reverse 1377b76..9bc0034
```

## 已验证结果

最近一次 fresh provider-free 全量验证：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

结果：

```text
Ran 143 tests in 10.480s
OK
agent template checks passed
```

最近一次核心 control-plane 验证：84 tests，全部通过。

这些结果证明 isolated fixtures 内的 schema、hash、binding、recovery、provenance、feasibility
与 final adjudication 语义；不证明 live Codex host 已提供完整 mutation mediation 或 strong termination receipt。

## 尚未完成的 G4 条件

### P1/P2：真实 Hook event 与 identity binding

- 在新环境当前 Codex baseline 上重新锁定 CLI/version/source contract。
- 用 isolated/disposable config 获取真实 `PreToolUse(spawn_agent)`、`SubagentStart`、`PreCompact`、
  `SubagentStop` inputs；覆盖 root/nested、serial/concurrent、POSIX，Windows 做等价 fixture/live evidence。
- 证明 SessionMeta flush 时序、direct parent、role、requested task name 与 canonical AgentPath 唯一绑定。
- 任一 ambiguity/mismatch 必须 preserve valid pending 并 block；不得退化为“下一个同 role child”。

### P4：mutation-surface 与 sandbox trust

当前已知阻断项：

- `write_stdin` 二次输入没有第二次 PreToolUse；
- opaque Bash 无法证明实际 path/Git effects；
- MCP/dynamic/agent-control schemas 没有 provider-independent side-effect contract；
- extension custom/freeform 不继承 function-only PreToolUse payload；
- code-mode outer executor 缺少等价可审计 payload；
- child 与 Hook/state/rollout 若同 UID，POSIX mode bits 不是 trust boundary。

除非 host sandbox 或 runtime adapter 对所有类别提供可审计阻断证据，否则 direct write 继续不合格。
用户 assignment 中的“不要写/不要 Git”无法补足外层不可见性。

### P5/P5b：resume 与 termination/quiescence

- 证明 live compaction/resume 后 mutation 前能重新取得 durable capsule，而不是只依赖 one-shot context。
- 证明 parent cancel/interrupt 后旧 child 真正 terminated 且 mutation quiesced。
- 在缺少 strong receipt 时，不得把同一 owned paths 立即重派给新 child。
- 验证旧 child 后续 PreToolUse 被 frozen/unresolved state 阻断，并覆盖 late mutation/mixed provenance。

### P6/P7：final callback、parity 与 regression

- 用真实 external child callback 证明 SubagentStop block/continuation/final attestation 语义。
- Parent 必须 fresh source review、owner-derived executable inventory、宽回归与 exact disk/Git identity。
- POSIX/Windows 协议、安装器、agent/skill/template/smoke 必须与同一 profile contract 同步。
- 在 isolated path 全绿且 live evidence 闭合后，才讨论 live install 切换；切换前需独立 rollback 记录。

### P6b/P6c：端到端成本与 staged authority continuity

现有 feasibility fixtures 只证明 invocation budget/domain、scale witness 与 equivalence fan-out，
不证明真实规模的端到端 latency 或分阶段 derivation。新的 G4 prerequisite 必须冻结并验证：

- invocation budget 与 latency gate 的独立 cost unit/statistic；
- multiplicity/等价类分布、representative worst dense witness、sample count、p95 定义与 phase timing；
- owner-derived `U1 → refinement set R → U2`，且 `true <= U2 <= U1`；
- 每个 phase 的 identity/source/root/authority-epoch reproof 与 closed-set conservation equations；
- final mixed-frontier exact cardinality、canonical order 与 item identity；
- phase before/mid/after mutation race fail-closed。

小 cohort、存储查询 spike、局部 phase benchmark 或 SQL-only result 都不能授权端到端 scale claim。
如果 phase-internal seam 位于 opaque tool 内且 Hook 不可见，维持 read-only/unqualified，不能让 child
用运行中便利假设改写 completion condition。

## 下一步执行顺序

1. **重建环境身份**：clone/fetch，核对 `origin/main`、branch、full HEAD、Codex CLI/version；确认无意外 dirty files。
2. **重跑 provider-free 基线**：全量 143 tests、mutation matrix、same-UID trust probe；任何漂移先修复或记录。
3. **刷新 source contract**：若 Codex 版本不是 0.147.0，重新审计 Hook schema/dispatch/SessionMeta/AgentPath，并更新 pinned anchors。
4. **只读 live probe 设计**：使用 disposable config/state/fixtures，不覆盖用户 live install，不输出 credential。
5. **先闭合 P1/P2**：真实 capture、flush、root/nested/concurrent identity；不精确则停在 read-only。
6. **再闭合 P4**：逐 mutation surface 证明 visibility + mediation + sandbox trust；任一负空间保留即不合格。
7. **闭合 P5/P5b**：durable resume、strong termination receipt、post-termination disk barrier 与 late-write tests。
8. **闭合 P6b/P6c**：补齐独立 latency/dense witness、U1→R→U2、phase conservation、
   mixed-frontier exactness 与 before/mid/after race fixtures。
9. **闭合 P6/P7**：真实 callback/final adjudication、DeepSeek regression、POSIX/Windows parity。
10. **G4 fresh adjudication**：对照 `docs/compatibility-model.md` 逐 gate 记录 evidence；只有全部 PASS 才允许把
   `direct_write_qualified` 改为 `true`。
11. **Phase 2 仍后置**：G4 完成后再建立 declarative worker/provider profile；profile 名倾向 `glm-thinking`，
    但 ZHIPU/GLM bridge 必须继续等待 Phase 2 独立授权。

## Phase 1 完成验收标准

Phase 1 只有同时满足以下条件才算完成：

- P1–P7（含 P5a/P5b/P6a/P6b/P6c）全部 provider-free 与所需 live evidence PASS；
- mutation matrix 没有不可见/不可阻断的 mutation-capable surface；
- real Hook events 上可复现 exact SessionMeta/child identity binding；
- compaction/resume 后 durable capsule 可重新证明，缺失/歧义时新增 mutation 被阻断；
- interrupt/cancel 有 strong child-terminated + mutation-quiesced receipt 和 post-termination disk barrier；
- SubagentStop/final adjudication 能机械核对 actual root/branch/HEAD/status/path hashes、inventory、
  provenance、feasibility 与 completion boundary；
- invocation 与 latency authority 分离，representative dense p95、phase timing、U1→R→U2、
  cross-phase conservation 与 mixed-frontier exactness 都有 fresh owner evidence；
- POSIX/Windows parity 和 DeepSeek regression 全绿；
- live install 切换与 rollback evidence 已单独审计；
- `direct_write_qualified=true` 的变化有上述证据，而不是 prompt/narrative 推断。

若任一项不成立，正确结论仍是：Phase 1 in progress，direct write read-only/unqualified，Phase 2 closed。

## 新环境续接提示词

将下面整段作为新 Codex 任务的首条指令；不要只复制“下一步执行顺序”而丢失设计约束。

```text
你正在续接 Native Codex Heterogeneous-Worker Compatibility Layer 的 Phase 1/G4。

仓库与身份：
- Clone/fetch git@github.com:BeFringe/codex-deepseek-subagent.git。
- 使用 main 分支；先完整读取 docs/phase1-handoff-snapshot.md、
  docs/compatibility-model.md、docs/compatibility-model.en.md、docs/phase1-evidence.md。
- 本临时 handoff doc 之前的实现 checkpoint 是
  9bc00342857e430e4d5533ef3e3fa1d60d637ad1；不要 reset/checkout/覆盖之后的用户修改。
- 先执行 git status/log/diff、确认 full HEAD 和 remote，再重跑 provider-free tests。

当前裁决：
- Phase 1 未完成；direct_write_qualified=false。
- Isolated schema v2/runtime/control/provenance/feasibility fixtures 已实现并曾有 143 tests 全绿。
- G4 仍缺 live mutation-surface、真实 SessionMeta identity、sandbox trust、
  termination/quiescence、end-to-end cost/staged-authority continuity、callback 和
  POSIX/Windows/DeepSeek regression evidence。
- Phase 2 worker/provider profile 与 ZHIPU/GLM bridge关闭，不得启动。

不可改变的目标与边界：
- OpenAI parent 完全走 Codex native OpenAI、当前主模型/provider/ChatGPT 登录；
  不经过本项目 router/bridge，不读取、输出、记录或提交 API key。
- Codex native 保有 spawn/AgentPath/permissions/lifecycle/wait/callback/cancel/Multi-Agent V2；
  本项目只处理 assignment transport compatibility、durable authority continuity 与 external wire compatibility。
- Assignment transport、wire transport、request normalization 正交；adapter 产品无关。
- Immutable capsule 必须在 compaction/resume 后重新证明 exact identity、root/branch/full base、
  owned/excluded paths、Git authority、authoritative input roots、stop condition、verification、
  provenance、feasibility、cost unit/distribution、phase derivation 与 final mixed-frontier
  equivalence；缺失或歧义必须 fail closed。
- Worker tests/hashes/narrative 只是 contribution evidence；parent/disk/fresh owner adjudication 才有 integration authority。
- 不用 external worker 证明它自己的正确性；只允许 native subagent 做边界明确的只读 scout。
- 不修改无关产品仓库；不覆盖 live Hook/skill/state，直到 G4 明确授权。

第一轮任务：
1. 重建新电脑的 exact Git/Codex/environment baseline，并报告与 handoff snapshot 的任何漂移。
2. Fresh 运行全量 provider-free tests、mutation-surface matrix、same-UID trust probe；保留原始结果摘要。
3. 对当前 Codex version 重新核对 Hook schema、PreToolUse/SubagentStart/PreCompact/SubagentStop、
   SessionMeta flush、requested task name→canonical AgentPath contract；若版本变化，更新 pinned source anchors。
4. 产出下一批可执行 live/isolated probe 计划，优先真实 root/nested/serial/concurrent identity binding
   与完整 mutation negative space；任何 identity 不精确或 mutation surface 不可见，维持 read-only。
5. 同时设计 P6c provider-free fixtures：独立 invocation/latency authority、representative dense p95、
   sample/stat definition、U1→R→U2、phase binding/conservation、mixed-frontier exactness 与
   before/mid/after mutation races；小 cohort 或 SQL-only spike 不得授权端到端完成。
6. 能安全推进时做一个小步实现+tests+evidence commit；不能证明时提交可复用 probe/docs，
   不伪造 runtime guarantee，不开启 Phase 2。

Phase 1 验收：
- P1–P7（含 P5a/P5b/P6a/P6b/P6c）证据闭合；
- 所有 mutation surface 有可审计 visibility/mediation/sandbox block；
- real SessionMeta/child identity 精确绑定；
- durable resume re-attestation 与 final SubagentStop/adjudication 可复现；
- strong termination/quiescence receipt + post-termination disk barrier；
- POSIX/Windows parity、DeepSeek regression、live install rollback evidence 全绿。
未全部满足前，禁止把 direct_write_qualified 改为 true。

换机接管成功后，单独 revert 临时 docs(handoff) 提交或删除
docs/phase1-handoff-snapshot.md；由于 snapshot 有追加提交，优先用新的 `git rm` 提交，
不要逐个 revert handoff 历史，也不要回退 Phase 1 实现提交。
```

## 临时文档撤回方式

本文件包含多个共享历史提交。换机恢复完成时优先使用一个新的非破坏性清理提交：

```bash
git rm docs/phase1-handoff-snapshot.md
git commit -m "docs(handoff): remove temporary phase 1 snapshot"
git push origin main
```

不要用 `git reset --hard`、force push 或回退 `9bc0034` 及其之前的实现历史。
