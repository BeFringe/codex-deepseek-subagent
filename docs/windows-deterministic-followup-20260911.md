# Windows Phase 1/P7 确定性续验草案

基线为已推送的 `c9bc913468c5b3e5156ae764710b618298c37e89`。
本轮仅在独立本地分支 `codex/p7-windows-deterministic-20260911` 工作；不更新原临时分支，等待 Mac 审计。
生产 Hook、StateStore、Rust 与全局 App 配置均不修改。Phase 1、P7、通用 direct-write 仍为 false。

## 机制调度证据

[六组确定性调度](../probes/p7-windows-deterministic-schedules-20260911.json)调用原实现的 Windows 锁、
原子发布和状态校验。包装器只在真实发布完成后等待 controller release，不注入 allow/deny 或状态结果。
所有合成身份与临时夹具保留；证据包含实际状态、哈希、线程/进程与时间事件。

- 在 pending 发布、claimed 发布、active 发布三个边界持有真实锁，令第二个 distinct assignment 的执行者
  明确到达锁竞争处，再由 controller 释放。两 assignment/spawn、AgentPath、child ID、root/branch/full HEAD
  均精确绑定，pending/claimed 消费后无残留。这是受控交错，不是概率性重复。
- 明确持有 overlapping exact-path parent claim，竞争者被拒绝；在 guard 返回处读取已持久化 conflict，
  证明 publish 先于 deny return。错误 call ID 的 PostToolUse 不释放 claim，精确 callback 后 successor 可准入。
- 独立 Python holder 在持久 claim 后直接 `os._exit(23)`；其父/兄弟竞争请求仍 fail closed，
  进程死亡不隐式解除 authority。确认 claimed paths 与 Git frontier 未变后，通过现有精确 abort API 恢复；
  successor 可准入，随后精确 release。
- watchdog 的显式 `now` 输入在 pre-write deadline 与其后 1 微秒两侧运行。前者仍 active，后者撤权，
  后续工具请求被拒绝。没有改写持久时间戳，也不把控制时钟的机制测试称为真实 native 超时实验。

这些结果不解释历史缺 capsule 和缺 durable conflict 两次失败。原现场已缺失，仍保留原负回执。
合成 sibling 请求不能冒充 native sibling live；此次 native 封闭图只有 parent 与一个 writer child。

## Native parent/child 的显式写屏障

可选 `--parent-claim-barrier` 仅用于隔离 positive 探针：child PreToolUse 获得真实 claim 后发布 ready，
等待 parent 的真实 apply_patch 请求。parent Hook 等待 ready，调用原 guard，要求已有 durable conflict
精确引用该 child claim，再发布 release。child 重证同一 claim 后才返回 allow 并执行写入。
等待有界，失败不发出不完整 allow；不依赖模型在某个 sleep 窗口恰好竞争。

独立裁决核对 ready/release 的字节值、实际 native call ID、actor、conflict 文件哈希、拒绝输出和无 parent
PostToolUse，并验证 child 的真实写入、writer receipt、attestation、callback、close、ACL 与退出后磁盘屏障。
跨进程事件须严格有序；同一 Hook 中最后一次观测和 finished 允许同一 Windows 时钟刻度，不能倒序。

## 可重算 feasibility 与消费边界

`p7_write_feasibility.py` 从本次实际 baseline、authoritative 文件原始 UTF-8 字节和精确 patch 收集输入。
通过原 patch parser 推导路径集合，检查 clean baseline、目标不存在、确切新增内容与输入字节哈希；
按唯一 Add 操作推导一个工具调用的表示，并保存输入、反例检查结果、规模 witness 和推导证据。
不存在 1/2/3/4 占位哈希；CRLF 原始字节被保留，不做换行归一化后再冒充文件哈希。

该 invariant 仅针对这一个具体 addition 的表示与前置条件，不宣称服务端必定完成、一般 writer safety
或其他任务的可行性。新进程重算 packet，核对与 native assignment/capsule 中的 attestation 完全一致。

`adjudicate_p7_windows_writer.py` 在 outcome 检查之上独立重算完整 final schema、Git snapshot、capsule
身份、provenance、verification 和 trusted writer observation，要求无 in-flight authority，再消费 exact
closed writer run 的 reported authority。即使消费成功，也不开放通用 direct-write，不把 native sibling
缺证据或两条历史并发负例标为已解决。

## 保留的本轮失败

[原始未晋级回执](../probes/p7-windows-deterministic-unpromoted-20260911.json)保留 manifest 与 terminal envelope。

- `p7-mutation-positive-9adafdccfa8044828ce40720d4f168d1`：native parent 拒绝和 child 写入均完成，
  但 DS 两次 final schema 错误，guard 以 `final_return_correction_exhausted` 撤权。未晋级。
- `p7-mutation-positive-e774ecb7fb624879b24cfaaf0c92fa75`：已报告写入结果，初版独立 checker 在同一
  Hook 的 release-observed 与 finished 时间相等时拒绝。保留原失败，不重新消费；最终证据使用新运行。

[最终 native 回执](../probes/p7-windows-deterministic-writer-live-20260911.json)对应
`p7-mutation-positive-8b29eed8cc254243a9247e9dadd3a729`。
[新进程 owner 回执](../probes/p7-windows-deterministic-writer-owner-20260911.json)已通过完整上述检查，
实际消费 assignment `7b0272b3-4ebe-4118-8374-509fd74e9206` 的 authority。
这不是 outcome-only；`exact_closed_writer_run_qualified=true`，`authority_consumed=true`。
native sibling、通用 direct-write、Phase 1 和 P7 仍为 false。

[最终完整回归](../probes/p7-windows-deterministic-provider-free-20260911.json)：856 tests，852 passed、
4 originating-host skips，85/85 原 Windows 等价用例实际执行。受测源码/backend 哈希再次核对无漂移。
新增四个 feasibility 测试覆盖原始 CRLF、输入哈希漂移、dirty/已有目标及错误路径/内容。

上述证据形成一条本地 semantic commit 草案供 Mac 审计，不推送，也不改变已发布的 c9bc913 分支。
