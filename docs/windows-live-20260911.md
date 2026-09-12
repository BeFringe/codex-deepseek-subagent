# Windows native parity：2026-09-11 续验

Windows 等价修复已实际闭合原 85 个 category-b 用例；新 CLI 的 DS、ZHIPU
原生只读回归均通过独立进程裁决并消费 authority。DeepSeek custom-tool 回传缺口已在 Windows
本地修复；原生写入正例与撤权拒写负例均通过独立 outcome 校验，但尚未授予完整写资格。
P7 整体、Phase 1 和 direct write 保持未完成，Phase 2/3 保持关闭。

## 后续 Windows 等价闭合

[新审计](../probes/p7-windows-provider-free-closure-20260911.json)保留每个原始 b case 的 ID、
同名实际执行结果、backend、源码哈希和 `windows_equivalence_proven`。
原 [分类审计](../probes/p7-windows-provider-free-20260911.json)原样保留作为基线，不能把旧失败改成通过。
最后一次固定源码的完整审计为 852 tests：848 passed、4 originating-host skips；
Python/PowerShell/shell 受测源码逐文件复核无漂移。
85/85 已由 Windows 执行证明，当前无 category-b 或 category-d；4 个 category-c
只涉及 originating-host raw manifest/writer root，在 Windows 无法重放，不参与 Windows 本机通过声明。

- 平台无关契约在 Windows 使用本机临时根；POSIX 原有 `/private/tmp` ceiling 保留。
- 原 wrapper 契约直接执行 Windows Python launcher，真实子进程记录 argv；没有借助 shell 模拟器。
- 原 plaintext handoff 契约在 Windows 直接执行 PowerShell backend，包括真实并发、排他锁、
  过期恢复和原子发布；Windows 发布文件现在在创建时设置私有 DACL。
- 历史 live 回执绑定资格基线的原始 Git blob；当前实现由新的 provider-free / live 回执另行验证。

## Mutation 实验与尚未开放的资格

`run_p7_windows_mutation.py`、`p7_windows_mutation_hook.py` 和 `p7_windows_model_catalog.py`
仅用于隔离 qualification。完整 bundled catalog 保留 parent 条目，只为 exact `deepseek-v4-flash`
生成保守 descriptor，声明 `apply_patch_tool_type=freeform`，不虚构 multi-agent capability。
正例只生成临时 role overlay，唯一允许 `qualified.txt` 的一次受 lease 管理的 apply_patch；
负例使用相同的临时 write role 和 exact `qualified.txt` authority；在 child 绑定完成后、模型开始前，
测试夹具修改 `foreign.txt`，要求真实 PreToolUse 撤销过期 authority 并保护该文件的 dirty bytes。
这验证的是 capture 后磁盘变化触发的撤权，不能冒充单独的 wrong-path lease 排他证明。
两个角色、catalog、assignment、root/branch/full HEAD 和 before/after bytes 必须进入原始回执。
仓库角色、GUI/global Hooks 和 LocalCAT 未修改。

[DeepSeek 官方转换库](https://github.com/deepseek-ai/deepseek-recipe/blob/8cadfede7063c896b944e7bae05daa3549ae97ea/README.md)列出 Responses 的 apply_patch custom-tool
格式支持；这只是 wire 格式参考，不证明当前托管服务、Codex 注册或 mutation 生命周期已经通过。
没有安装该库。实际 finalized catalog、tool call/result、同一 tool-use identity 的 Pre/PostToolUse、
writer 排他、callback、fresh-owner 与 termination/disk barrier 仍必须由新 live 正/负例证明。
参考版本按 mac.local 只读核对的官方 HEAD 固定为 `8cadfede7063c896b944e7bae05daa3549ae97ea`。

一次完整复测出现并发 child binding 断言失败，记录在
[独立负回执](../probes/p7-windows-concurrent-binding-negative-20260911.json)。原失败时的临时目录
已由 unittest teardown 删除，旧断言没有打印实际 binding；无法恢复的身份、状态哈希和调度字段
明确记为未知。后续有限复现 cohort 和完整审计通过不等于找到根因，也不能抹除这条负证据。
该用例现加入线程/锁事件、阶段前后原始状态及哈希，并逐项核对 child/assignment/handoff 映射，
确保再次失败时保留可分析的实际数据。尚未据此宣称协议缺口已修复。

用户明确授权出站测试资料后，已实际执行并保留六个运行的
[验证诊断](../probes/p7-windows-authorized-validation-20260911.json)。原始 artifact 哈希、
两次退出后磁盘快照和已生成的 bounded close receipt 均再次核对。资格层源码未因以下失败放宽权限。

- 首次 capability 在 spawn 前因 descriptor 未声明角色要求的 `low` effort 失败；修正后再运行，
  native child 的实际目录为 `apply_patch`、`list_agents`、`view_image`，只读工具调用及关闭完成。
- positive 发出了真实 `custom_tool_call apply_patch`，同一 call ID 的 `custom_tool_call_output`
  也真实存在；输出是只读 sandbox 拒绝。父子 TurnContext 实际均为 read-only，尽管探针请求 workspace-write。
  `qualified.txt` 没有生成，退出后两次快照与 baseline 完全一致；不能把此次运行视为成功写入。
- 正例在该输出后收到 DeepSeek `No tool output found for tool call call_00_39NKXRfLL6ScHqGwefXt7721`。
  原始序列为 custom call → Hook developer context → Hook post-mutation observation → custom output。
  受测 `core/src/client.rs` 的 `normalize_function_call_output_adjacency` 只匹配 FunctionCall/FunctionCallOutput，
  未处理 CustomToolCall/CustomToolCallOutput。后续本地 Rust 对照已证明这个实现缺口，见下文；
  新 CLI 的服务端实际效果已由下文独立 live 正例验证。
- negative 的 dirty fixture 在 spawn PreToolUse 被 `strict read-only review requires a clean captured worktree`
  拒绝。没有 child、目标 apply_patch 或 child close，因此不能冒充目标越权写入拒绝通过。
- 当前 DS、ZHIPU 原只读 catalog 回归均有 fresh-owner 成功回执；对应完整回执及哈希包含在验证诊断中。

Windows sandbox 未启用时，原生配置会把 workspace-write 降为 read-only。隔离 mutation 探针现显式选择
`windows.sandbox=unelevated`；不更改用户全局 sandbox 配置。负例夹具已改为先合法 capture/bind，再注入
一次外部 dirty-byte 变化，保留生产 guard 的严格准入条件。
这次实验复用既有写探针的 fixture feasibility hashes，不能将其当成真实产品可行性测量证据。

## Windows 本地 custom-tool 修复与对照

新累计源码补丁为 `current-signed-runtime-g4-custom-tool-pairing-source-candidate.patch`，
SHA-256 `4f61f37ae46f6160055fde7b7ce95d095b2456ce1b9f1a96f5947669baab63b8`。
相对既有候选只修改三个 Rust 文件：`client.rs`、`client_tests.rs` 和 `unified_exec/mod.rs`。
发送请求时的邻接整理现同时处理 FunctionCall 和 CustomToolCall，按工具种类与 call ID 配对，
避免同 ID 的不同种类互相消费；Hook 内容完整保留，持久化 rollout 不重写。
该整理仍只在 provider 显式启用 adjacency flag 时执行。
新[构建回执](../probes/p7-windows-custom-pairing-build-20260911.json)已固定：Cargo exit 0，
`codex-cli 0.153.4`，二进制 SHA-256 为
`be617eb1ebe44d9df02b64b689a140804600e91b0d7b352e8a23223e5d664e80`。
旧 e97c1190 二进制保留并核对恢复，不以新候选改写旧证据。

[Rust 红绿对照](../probes/p7-windows-custom-pairing-red-green-20260911.json)使用实际 codex_protocol
类型及提取自旧、新源码的同一函数：旧代码 1 passed / 2 failed，新代码 3 passed / 0 failed。
这证明 custom output 与 Hook message 的排序缺口及修复，不替代完整 core 测试或真实 API 验证。
Windows core 测试编译另外发现可移植的 remote-executor mock 测试被 Unix cfg 隔离，
而 process-manager 测试引用其 helper；现开放该可移植模块的五个测试，真实 Unix 后端测试的 cfg 保留。
完整 `codex-core` lib 测试产物已构建成功，三个配对测试、五个 remote-process 测试和一个 exact-exit
测试均通过；再用仓库的 `just test` / nextest 入口运行同一范围，9 passed，2362 个不在本次范围。
没有声称跑完 Codex 全 workspace Rust 套件。`just fmt` 已执行；其带出的三处既有 Bazel 格式改动
恢复为上游原文，Rust 补丁仍逐字节等于上述固定 SHA-256。工具安装仅在本任务缓存内。

[旧 CLI live 对照](../probes/p7-windows-custom-pairing-old-live-control-20260911.json)复用原始 e97c1190
二进制的逐项哈希相同副本，采用修正后的 Windows sandbox。父子实际均为 workspace-write，
`qualified.txt` 写入成功，真实 writer receipt 与 PostToolUse 齐全，但 DeepSeek 仍拒绝同一 custom call ID，
报 `No tool output found`。真实 bounded close 与两次退出后磁盘观察已独立复核。
这把权限配置问题与 provider 输出排序问题分离开来；本次写入没有成功 attestation，也未消费 authority。

[最终同探针对照](../probes/p7-windows-custom-pairing-final-old-live-control-20260911.json)又以旧二进制
运行了与新版成功正例逐项哈希相同的 harness、catalog 和 role：实际写入及 writer receipt 成功，
同一 custom output 仍被 DeepSeek 拒绝。原生 capability ACL、bounded close 和当前磁盘均重新核验。
更早旧对照的临时写根在最终冻结时已不存在，原因未知；总回执明确记录其未再次核验当前磁盘，
保留原始屏障证据，不将历史失败提升为资格。最终同探针对照提供了新的完整本机证据。

新候选的[验证总回执](../probes/p7-windows-custom-pairing-validation-20260911.json)包含以下结果：

| 场景 | 独立裁决 | 权限含义 |
| --- | --- | --- |
| DS / ZHIPU 只读 native child | 两者均通过，authority consumed | 仅 exact closed read-only actor graph |
| DS 一次 owned `qualified.txt` 写入 | 写入、custom output、writer receipt、attestation、callback、close、磁盘屏障通过 | outcome verified；不消费完整写资格 |
| DS capture 后外部 dirty-byte 变化 | PreToolUse 撤权拒写、`TASK.CONTEXT_LOST` callback、close、原字节保护通过 | 过期 authority 撤销边界；不冒充独立 wrong-path lease 排他证明 |

首次新版正例已经完成真实写入和 attestation，初版校验器却在 ACL 检查中拒绝了原生 sandbox
添加的 workspace capability ACE。经核对 `windows-sandbox-rs` 的 `cap.rs`、`spawn_prep.rs` 和
`acl.rs`，它属于按 canonical CWD 分配的 SID，权限恰为 `0x1301bf`，不包含 WRITE_DAC、
WRITE_OWNER 或 FILE_DELETE_CHILD。它不是任意新增的账户授权。
新的独立校验只接受私有基线加这一条精确 ACE，并核对本次私有 CODEX_HOME 的非凭据 `cap_sid`
注册表、root/SID 绑定、两次退出后 ACL 与当前实际 ACL。artifact root 和 CODEX_HOME 仍须满足
原来的三主体私有 DACL。通用 `p7_windows_acl.py` 没有放宽。
新增四个测试覆盖实际 Windows ACL 往返、额外主体、权限扩大、SID 复用和错误根绑定拒绝。
首次新版正例的旧校验失败保留；以上成功结论来自带完整 ACL 采集的新运行。

另一次完整审计出现 parent writer 竞争负例，记录在
[原始负证据](../probes/p7-windows-parent-claim-negative-20260911.json)：观察到一 allow、一 deny 和一条
writer claim，但缺少期望的 durable conflict。原失败的拒绝原因与临时状态未保留，不能推断为锁缺陷或
Git 错误。测试已补充实际拒绝原因、异常栈和失败夹具保留；后续绿色回归不能将这两条并发负证据作废。
带该诊断的三轮有限完整复现均为 844 passed / 4 originating-host skips，最后一轮受测源码无漂移，
已更新最新 Windows closure 回执；原始失败回执及每轮原始审计均保留。
补齐 native ACL 校验后的最终完整审计为 848 passed / 4 originating-host skips，85 个 Windows
等价用例仍全部执行通过。上述历史并发负例仍未解释；父/兄弟 writer 排他、完整 fresh-owner 写资格
以及真实产品 feasibility 证据仍待补齐，Phase 2/3 不因本次修复而开放。

## 首轮只读 live 历史结果（31922bf）

[总回执](../probes/p7-windows-readonly-pair-20260911.json)绑定相同 CLI、最终 harness、逐项测试
审计、两个成功运行和两个未晋级尝试。成功运行均由另一个 Python 进程重算并消费 authority。

| Provider | Child 导出名称 | 调用参数 | Callback / close / disk | Authority |
| --- | --- | --- | --- | --- |
| [DeepSeek](../probes/p7-windows-deepseek-readonly-20260911.json) | `list_agents`，无 namespace | `{}`，一次 | 全部通过 | consumed |
| [ZHIPU](../probes/p7-windows-zhipu-readonly-20260911.json) | `g4_assignment.list_agents` | `{}`，一次 | 全部通过 | consumed |

两者都是实际 OpenAI/ChatGPT parent 和 native child，保留真实 SessionMeta、AgentPath、
call_id/output、SubagentStop、字节一致 callback、关闭后的 catalog 与退出后的两次磁盘观察。
只证明 exact closed actor graph 的只读生命周期，不证明全局进程树静默或 direct write。

DeepSeek 在首轮只读工具调用和双 flags 组合中未重现旧的 `No tool output found`；上述新增 custom-tool 实验已复现。前两次新 CLI
尝试仍完整保留且没有晋级：第一次是旧 Windows verifier 要求 namespaced 名称，与明确关闭
namespace 的 provider profile 不符；第二次是模型给最终 envelope 加 Markdown 围栏，Stop
正确阻止，随后纠正的第二份 envelope 仍不满足本 probe 的单次证明合同。最终运行明确要求
纯文本 envelope，名称按 provider 精确匹配，没有放宽工具集合或最终证明条件。

## 固定版本

- 资格层基线：`785b945d46a9a8879f659a428ff0a03d940cf7a1`。
- Codex 上游：`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`，0.153.4。
- 累积源码补丁：`probes/current-signed-runtime-g4-cumulative-source-candidate.patch`。
- 完整索引补丁 SHA-256：`94ec3d6140868055662ca43b0d0d464f5bda8d41cd40433a20facb4fb600f72d`，228346 bytes、57 paths。
- Windows 修改分支：`p7-windows-parity-20260911`；原工作目录的既有修改保留。

早期 `55af3a3` 的补丁使用了缩短的 blob ID，不能作为最终 full-index 回执。
当前构建目录虽保留旧目录名，实际 `git diff --binary --full-index HEAD` 与上述补丁逐字节一致。
复用的旧 target 只是构建缓存；其中原有 `codex.exe` 的存在不代表本次构建成功。
必须等待本次 Cargo 成功退出，再重新计算最终二进制哈希。

本次[构建回执](../probes/p7-windows-build-20260911.json)已生成：Cargo exit 0，release 构建耗时
112m 47s，版本 `codex-cli 0.153.4`。新 `codex.exe` SHA-256 为
`e97c11909c080ff4556c0746b80b7c47f9508f5792ccac8bb83d91db187a9101`；四个请求构建的二进制均已重新核验。

本轮使用 Rust 1.95.0、x64 MSVC Build Tools 环境和 `LIBSQLITE3_FLAGS=SQLITE_DISABLE_INTRINSIC`，
在上游 `codex-rs` 目录执行：

```text
cargo build --locked --release --jobs 1 --target x86_64-pc-windows-msvc --bin codex --bin codex-code-mode-host --bin codex-windows-sandbox-setup --bin codex-command-runner
```

Cargo/Rustup 缓存与匹配目标的 V8 archive/bindings 通过本机环境指定，不把某个用户的绝对路径
写成安装默认值。运行期 Hook 和审计使用 Python 3.12、Git，以及 Windows 自带的锁、句柄和 ACL
API；新增的 Windows 支持使用 Python 标准库 `msvcrt`/`ctypes`，没有新增 pip 包或常驻 broker。

## 已验证的修改

Windows authority store 使用 `msvcrt` 非阻塞字节锁，带有限等待期限。异常或超时发生在 mutation
之前；正常退出和进程异常退出都释放系统锁。POSIX 的 `fcntl` 路径保持原义。

writer guard 接受 Windows 原生反斜杠路径，再执行原有根目录和 ownership 验证。
drive-relative、设备命名空间、alternate data stream、路径组件中的保留名、尾点/空格、越界和
同一补丁中的大小写别名被拒绝。非 Git writer 也明确拒绝 Windows reparse point，避免把
junction 当作普通目录。该修正本身不授予 direct-write 资格。

Windows evidence binding 使用目录句柄相对的 `NtCreateFile`，逐级拒绝 reparse point，独占
创建最终文件，执行后重证目录链与终端身份。测试使用不需要 symlink 特权的 junction，并用
Windows `FileDispositionInfoEx` 的 POSIX 删除语义制造真实终端替换，确认旧句柄不能掩盖替换。
目录替换测试分别识别原生拒绝与替换后的验证拒绝，不把前者冒充成功完成了替换。

三个通用 Hook overlay 在文件创建时设置受保护 Windows DACL，权限限于当前用户、SYSTEM 和
Administrators；不会先创建宽权限文件再收紧。独立 ACL 检查验证 owner、规则集合和禁止继承，
并有父目录含额外写者、已有文件、ADS/设备别名等反例。

测试夹具使用本机临时目录作为本机绝对路径；序列化的仓库相对路径明确使用 POSIX 分隔符。
历史 macOS 回执按其原路径语法检查，不能把它们解释为当前 Windows 上存在的文件。

原生 PowerShell plaintext handoff 的 12 组验证通过，覆盖单次投递、锁争用、UTF-8、claim
恢复、隔离、原子发布和并发；它独立于明确要求 POSIX 锁的 Python handoff 实现。
后续同名 Python unittest 在 Windows 选择 PowerShell backend，31 项实际执行；
包括替换过期 pending 后的私有 DACL 检查，不以 POSIX skip 代替等价证明。

## 全量回归的裁决方式

`probes/run_p7_windows_provider_free.py` 保存每个测试、失败子测试、诊断和所测源码哈希。
测试级计数与 unittest 错误事件计数分别记录，避免把同一个测试的多个子测试错误误算成多个测试。

`31922bf` 初次[逐项分类审计](../probes/p7-windows-provider-free-20260911.json)：842 项测试，753 passed、
67 error、14 failed、8 skipped；unittest 的 error 事件为 72（含同一测试的多个失败子测试）。
非通过项全部逐项分类：b 类 85 项（含既有的 4 项 POSIX 锁 skip），c 类 4 项（原主机锚点 skip）。
该历史审计当时没有 d 类遗留；此前识别的 Windows 实现缺口已通过回归。
该结果没有把 b 类测试自动跳过，也没有宣称整个套件通过。

分类不改变测试结果，也不等于 skip 或豁免：

- b：POSIX 临时目录/authority ceiling、shell launcher 或显式 POSIX handoff。需核对 Windows 对应合同。
- c：原主机原始锚点缺失，或必须在原主机进行的 canonical filesystem validation。
- d：尚未定位或未补齐的 Windows 能力，一律保留阻塞。早期归入此类的 no-follow、junction
  和三个通用 builder 的 private DACL 已有上述实现与定向测试，需由最终完整审计确认。
  不能用 `chmod(0600)` 或一次 `Path.resolve()` 冒充 Windows 等价保证。

以上数字是保留的历史基线。后续 85 项闭合和当前完整审计以本页顶部的新回执为准；
并发绑定负证据独立保留，不能用后续成功抹除。只读 native lifecycle 不覆盖 mutation 资格。

## Live 运行边界

`run_p7_windows_live.py` 从自身位置解析项目根和工具路径，机器绝对路径只出现在运行期配置与原始回执。
每次运行使用独立 Git fixture、私有 DACL 的证据目录和隔离 `CODEX_HOME`，保留真实
OpenAI/ChatGPT parent。子模型分别为 DeepSeek 和 ZHIPU。DeepSeek 同时设置：

```toml
supports_namespace_tools = false
requires_function_call_output_adjacency = true
```

child 只调用一次 `g4_assignment.list_agents {}`；独立进程重算 SessionMeta、AgentPath、Hook
事件、call_id/output、Stop、字节一致的 callback、close、关闭后 catalog 和退出后的两次磁盘观察。
collector 永不自我晋级；只有 fresh owner 可以在全部检查通过后消费 reported authority。

Hook 仍是外部 Python 脚本，由隔离 `CODEX_HOME` 的 Hook 配置加载。Rust 补丁负责原生 provider
路由和生命周期/权限约束，并没有把 Hook 安装进 App 或替代 Hook 脚本。本轮不改 GUI、现用
App Server、全局 Hook 或 LocalCAT。
