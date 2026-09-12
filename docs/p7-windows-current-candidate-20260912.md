# Windows 当前候选验证交付

本次交付以 `f5c2fec7f5ed602f217439ce569e47baeb875c9b` 为审计基线，绑定 Codex 0.153.4 的完整源码树 `45f946181672a55b78b04506f0436e170576bdde`。Windows CLI 的 SHA-256 为 `f333abaf171811bfa0a162d08c59ac4c918a1d5a8ba978578ba269d1c48c3cc4`。

## 改动与边界

- Git snapshot 同时禁用 optional locks 和 `diff.autoRefreshIndex`，避免读取快照时刷新共享 index。保留用户仓库本身的行尾解释，失败时保留 Git 返回码和 stderr。
- 单文件写入核验接受精确 basename 或同一 canonical absolute path，仍逐项绑定 root、owned path、操作、内容、actor 和 call。路径穿越、drive-relative、foreign 和多操作请求不被接受。
- 源码绑定覆盖有序 patch chain、完整 Git tree、完整 diff 和两个新增文件的原始字节。普通 tracked-only diff 不再被当作完整源码身份。
- macOS 专属 fixture 明确标为 originating-host skip；旧测试名称通过显式映射对应实际执行的 Windows 等价测试。

临时运行目录和 CLI 路径由运行参数及私有目录生成。原始回执中的本机绝对路径是观测值；可移植交付使用相对仓库路径、run ID 和哈希。

## 证据

- [Windows compact receipt](../probes/p7-windows-current-candidate-writer-live-20260912.json)
- [可移植审计明细与失败历史](../probes/p7-windows-current-candidate-audit-20260912.json)
- [上游对照的锁文件版本差异](../probes/p7-windows-upstream-lock-normalization-20260912.patch)

冻结后的 provider-free 套件执行 908 项：900 passed、8 originating-host skips，85/85 Windows equivalences。六项确定性调度使用真实 StateStore 和实际 holder 子进程；它们不代替 native sibling live，也不追溯解释已丢失 fixture 的历史负例。

新的 native positive 包含父子同路径冲突、子写入、精确 callback、close、退出后磁盘屏障和独立 owner 消费 authority。新的 native negative 验证 foreign 脏文件拒绝、零 PostToolUse、权限撤销与关闭。已消费的正例不能再次运行消费型 adjudicator。

Rust 定点测试 14 项通过。完整 core 的原始失败、辅助程序缺失后的三项复验、ignored 清单和 current/control 差异集均见审计明细，不能将其概括为全套绿色。对照是 **base + exact Cargo.lock workspace-version delta**：原始发布锁文件的 149 个工作区版本仍为 0.0.0，先前 `--locked` 因此在测试前失败；仅这些无 source 包的版本同步为 0.153.4，外部依赖与其他字段不变。

候选原全套为 3598 项（3590 passed、7 failed、1 timeout），对照为 3565 项（3559 passed、5 failed、1 timeout），两边各有 77 ignored。补齐测试辅助程序后三项候选失败通过复验；剩余四项是两边同因的权限/环境失败，一项为共同的沙箱冷初始化边界。候选新增的 33 项全部通过；对照另有一项 user-shell 时序失败，未计作候选回归。

最后一项只做了预先限定的 cold/warm 对照：两边 cold 均在 180 秒超时，显式初始化后分别在 12.249 秒（候选）和 10.632 秒（对照）通过。原全套失败的日志时间都落在该测试窗口内，各有七个文件系统辅助进程的冷启动及缺少初始化标记记录。相关测试、入口分发、初始化与文件系统辅助代码逐字节相同；因此此次比较的 `patch_regressions=0`，不表示通用冷初始化问题已修复。

诊断中还发现共享 Cargo target 在切回较早 mtime 的工作树时复用了对照二进制。该次标为 current 的 180 秒诊断及随后 EOF 记录明确作废。清除工作区包缓存、恢复候选 3675 项清单后，最终 cold/warm 使用独立复制并绑定哈希的二进制及官方 nextest 重用元数据。后续跨工作树对照应隔离 target，或先强制重建并冻结可重用产物。

生产候选使用单任务、关闭 LTO、opt-level 0、debug 0、codegen-units 16 的 release 构建。Rust 集成测试另对 `codex-arg0` 启用上游已有的 debug fixture 路径；这只属于测试构建配置，未替换正式 CLI。

## 阶段职责

本分支提供 Windows 当前候选的有界证据。P7、Phase 1 和通用 direct-write qualification 均保持 false，由整合端结合其他平台回执作最终裁定；Phase 2、Phase 3 保持 closed。此次未增加 App 全局 Hook 或改变其信任状态。

整合端应在取得本分支后核对完整源码身份与审计文件哈希，再调用 `adjudicate_phase1_completion.validate_windows`。不要把本分支的 Windows 局部结论直接当作全局 promotion。
