# DuctZip Final Review — 2026-09-26 (v1.0.0rc1 RC closure)

本文件是本轮独立发布级 Review 的报告与关闭记录。Review 范围：

- 提交区间：`origin/main..HEAD`（`a45e8b8..6d88b09`，7 个本地提交）。
- 工作树脏改动：18 个 modified tracked 文件 + 5 个 untracked 路径
  （含 `tasks/claude-code/` 任务文件，为新增未跟踪目录）。
- 方法：通读当前源码（非 diff 摘要）、fresh 全量测试（faulthandler 开启）、
  重复运行取证、真实后端 CLI 冒烟、构建产物审计、Windows Event Log 检查。
  全部原始日志在 `.task_logs/`。

## Findings

### P1-1 GUI worker 线程回收竞态：Qt 原生崩溃（abort / 0xC0000005 / 0xC0000374）

- **证据**：`tests.test_gui_lifecycle` + `test_gui_entrypoint` 连续运行中
  `GuiShutdownTests.test_close_while_extracting_terminates_worker_bounded`
  间歇性原生崩溃。捕获签名：`Fatal Python error: Aborted`（无 Python traceback）、
  `Windows fatal exception: access violation`、
  `Windows fatal exception: code 0xc0000374`（堆破坏）。
  faulthandler 栈显示主线程位于 `app.py on_worker_finished`（由 `closeEvent`
  调用），崩溃发生在 worker OS 线程、无 Python 帧。
  复现率：20 次模块对运行 1 次失败；30 次单测循环 2 次失败（5/30、8/30）。
- **根因**：`on_worker_finished` / `on_batch_thread_finished` 在 queued
  `finished` 信号送达时立即把 `self.worker` / `self.worker_thread` 置
  `None`。若这是最后一个 Python 引用，shiboken 会**立即**删除底层 C++
  对象；而 `QThread::finished` 在 OS 线程完全终止之前发出，`_wait_for_thread`
  的 `processEvents` 泵会在 OS 线程仍在退出窗口内送达该信号。于是：
  - 删除 `ExtractWorker`（affinity = 正在退出的 worker 线程）→ 跨线程操作
    垂死线程的事件队列 → 0xC0000005 / 0xC0000374；
  - 删除 `QThread` C++ 对象时 OS 线程仍在运行 → Qt
    `qFatal("QThread: Destroyed while thread is still running")` → Aborted。
  这与 2026-09-26 首次全量套件"exit 1、无 unittest 摘要、进程在 GUI
  lifecycle 区域附近死亡"的记录同签名（硬崩溃，unittest 来不及输出摘要）。
- **修复**：`on_worker_finished` / `on_batch_thread_finished` 先取出引用、
  清空属性、然后对线程对象 `wait()`（OS 线程彻底结束后才允许包装器引用
  掉落）。同时移除 `finished → deleteLater` 的自删除连接，统一由
  "线程确认结束后掉落引用"负责析构。幂等，两条路径（closeEvent 显式调用
  与 queued finished 送达）都可安全重入。见
  `src/ductzip/gui/app.py`。
- **关闭证据**：修复后 `test_gui_lifecycle`+`test_gui_entrypoint` 连续 20 次
  通过、完整套件连续 3 次通过（见 PROGRESS.md 本轮记录）。

### P2-1 便携包 manifest 来源标识不完整（dirty tree 伪装为纯 HEAD 产物）

- **证据**：`scripts/build_portable.py` 的 manifest 只记录
  `git_commit=6d88b09`，但打包的是含未提交 Phase 7 改动（版本号、引擎修复、
  CLI 修复、顶层目录包装等）的源码。`dist/build-manifest.json` 实测如此。
- **影响**：产物无法从标识回溯到真实源码状态；与 §4.5 MUST 冲突。
- **修复**：manifest 增加 `git_dirty`（bool）与 `worktree_diff_sha256`
  （对 `git diff HEAD` 全部输出求 SHA-256）；未跟踪但被纳入产物的文件
  本来就逐文件记录 sha256（`files` 数组），可审计。release build 在 dirty
  tree 不再静默伪装。

### P2-2 便携包不含 `docs/USER_MANUAL.md`，发布说明指向断链

- **证据**：release notes §1「面向使用者的完整说明见
  `docs/USER_MANUAL.md`」，但便携包 28 个条目中无该文件
  （`DuctZip-1.0.0rc1/` 下仅 README/LICENSE/CHANGELOG/NOTICES/PORTABLE.txt
  - 启动器 + src + vendor）。
- **修复**：构建把 `docs/USER_MANUAL.md` 与匹配当前版本的
  `docs/RELEASE_NOTES_<version>.md` 纳入包内根目录；`PORTABLE.txt` 与
  release notes §2 同步描述。

### P2-3 release notes 含开发机绝对路径

- **证据**：`docs/RELEASE_NOTES_1.0.0rc1.md` §6 第 89 行
  「全部命令在 `F:\01_code\tools\DuctZip` 下执行」。
- **修复**：改写为不依赖机器路径的表述（"仓库根目录"）。

### P2-4 MOTW 传播会给合并场景下已存在的文件打 Zone.Identifier

- **证据**：`ExtractionService.extract_with_progress` 完成后调用
  `propagate_motw(plan.archive_path, plan.final_output_dir)`，后者遍历
  **最终目录下全部文件**写 ADS（`src/ductzip/motw.py: propagate_motw`）。
  `merge` 冲突策略下目标目录里**解压前就存在**的文件也会被打上来源区域
  标记——把本来本地的文件标记成"来自 Internet"，SmartScreen/受保护视图
  行为会被改变。文档（`docs/SECURITY.md` MOTW 节）写的是
  「写到最终输出目录下的每一个**解压文件**上」，代码与文档冲突。
- **修复**：引擎真正开始写盘前对最终目录做文件快照（best-effort，目录不
  存在则为空集），传播时排除快照内的既有文件。回归测试：预置文件 +
  带 MOTW 的压缩包 merge 解压 → 预置文件无 ADS、新解压文件有 ADS。
  该修复不改变 MOTW 的产品语义（只修正越界写），不需要用户决策。

### P2-5 记录中的 wheel 哈希与 fresh 构建不一致（构建非 bit-for-bit 确定）

- **证据**：`PROGRESS.md`/release notes 记录 wheel sha256
  `5999558d…b4fd`；2026-09-26 fresh 构建同尺寸 53,518 字节但 sha256 为
  `9aeeb8e5…`。wheel zip 条目时间戳导致逐次构建哈希不同。便携包因
  `copy2` 保留 mtime 在源码未变时可复现，但 wheel 不可。
- **影响**：公开文档不得声称 bit-for-bit reproducible；最终源码确定后所有
  记录哈希/大小必须重新生成。
- **修复**：最终构建后在 PROGRESS/release notes/checklist 中刷新全部数值，
  并明确措辞为「流程可重复（repeatable process），wheel 非逐位可复现」。

### P3-1 `BatchQueue.run(external_cancel)` 在 planning 阶段对外部取消无响应

- **证据**：`src/ductzip/core/queue.py _run_task` 只在收到进度事件时检查
  `external_cancel`；planning（引擎 listing）期间生成器尚未 yield，外部
  取消事件不会被转译进 `task_cancel`。GUI/CLI 实际都走
  `cancel_current`/`cancel_all`（内部路径，直接 set 当前任务事件），
  无现存调用方传 `external_cancel`，故不阻塞 RC。
- **处置**：记录为已知限制（`run()` 的 `cancel_event` 参数仅在任务运行期
  生效），不在本轮改语义。

### P3-2 GUI 测试模块独立运行时读取真实用户设置

- **证据**：`settings_harness` 仅被 `test_cli.py` / `test_gui_settings.py` /
  `test_security.py` 导入；`test_gui.py` / `test_gui_batch.py` /
  `test_gui_lifecycle.py` 单独运行（或先于它们运行的顺序）时
  `MainWindow()` 的 `load_settings()` 读取真实 `%APPDATA%` 设置。
  测试不写设置，实际只读，无状态污染。
- **处置**：测试卫生项；为三个 GUI 测试模块补 `import tests.settings_harness`。

## 文档与代码冲突核对

- `docs/SECURITY.md` MOTW「每一个解压文件」 vs 代码打全部文件 → 见 P2-4，
  以修复代码对齐文档。
- README「Not Yet Implemented：Compression / Installer」与实现一致。
- `docs/SECURITY.md` 密码/网络/取消回收/后端验证链与代码一致（本轮实测
  bundled digest 与 pins、THIRD_PARTY_NOTICES 一致）。
- USER_MANUAL §5.5 退出码、§11 后端发现顺序与 `find_sevenzip` 实现一致。

## 已审查但未发现问题的关键区域

- 引擎 `_is_safe_archive_path`：绝对/盘符相对/`..`/空段/UNC/`\\?\`/保留
  设备名（含扩展名、尾点尾空格、大小写）全覆盖；fresh listing 权威边界
  保持（`ArchiveMutationBoundaryTests`）。
- 子进程生命周期：三条启动路径均 `stdin=DEVNULL`；reader 线程独占关闭；
  terminate→wait→kill→wait 回收链；被遗弃生成器 `finally` 回收。
- 密码：`-p` 永不省略、`password_supplied` 分类、批量层 `_redact`、
  日志不泄漏（含 GUI 日志行级断言）。
- Shell 集成：HKCU-only、幂等、精确撤销、引号/Unicode/空格协议；
  `WinRegistryRoundTripTests` 真实 HKCU 往返并断言快照子集无残留。
- 批量状态机：terminal/重试/移除合法性、单任务失败隔离、顺序保证。
- 设置模型：原子写、损坏备份重置、写入时后端路径校验、失效回退。
- bundled 7-Zip 三文件 digest 与 build pins / THIRD_PARTY_NOTICES /
  DD-008 修订完全一致（实测 MATCH），未下载或替换后端。

## UNKNOWN / 未能验证项

- 静态质量工具：仓库无 lint/typecheck 配置，保持 UNKNOWN，不主张通过。
- 第二台物理机干净环境验证：无此环境，维持已记录限制（release notes
  §5.3）。
- 上游 7-Zip Windows 二进制的 Authenticode 签名：上游不签名（已用 PE
  证书表双路验证），维持替代验证链声明。
- 首次全量套件异常退出的**当时**现场（无日志留存、Event Log 无记录）：
  以本轮复现到的同签名崩溃（P1-1）作为解释，并以修复后重复运行证据关闭。

## 关闭记录（2026-09-26，Phase 2–5 完成后补记）

| ID | 状态 | 关闭证据 |
| --- | --- | --- |
| P1-1 | **CLOSED** | 修复：回收前 `QThread.wait()` 确认 OS 线程结束 + 移除 `finished → deleteLater` 自删除链（[app.py](src/ductzip/gui/app.py) `on_worker_finished` / `on_batch_thread_finished`）。回归测试 2 项在旧实现上确定性失败（运行中线程未被等待/包装器提前释放）。修复后 GUI 模块对 **20 连过**（`.task_logs/phase3_gui_pair_1..20.log`），全量套件 **253 项 3 连过**（`.task_logs/phase3_full_suite_1..3.log`），每次运行后 0 孤儿 `7z.exe`。首次异常退出与此同签名，解释成立。 |
| P2-1 | **CLOSED** | manifest 增加 `git_dirty` + `worktree_diff_sha256`；本次构建实测 `git_dirty=true`、`worktree_diff_sha256=d4449a46…65a39`（`dist/build-manifest.json`），并有测试断言 diff 摘要与 `git diff HEAD` 实测一致（`tests/test_build_portable.py`）。 |
| P2-2 | **CLOSED** | 便携包根目录现含 `USER_MANUAL.md` 与 `RELEASE_NOTES.md`（manifest 30 个条目）；构建对缺失文件直接失败；`PORTABLE.txt` 与发布说明同步。 |
| P2-3 | **CLOSED** | 发布说明 §6 改写为「仓库根目录」；全库扫描无 `F:\01_code` 残留（保留的 `D:\…` 均为文档示例，非本机路径）。 |
| P2-4 | **CLOSED** | 解压前快照 + `propagate_motw(exclude=…)`；回归测试 `test_extract_does_not_tag_preexisting_files` 在旧行为上确定性失败（本地文件被误标）；`docs/SECURITY.md` 增加边界条目。 |
| P2-5 | **CLOSED** | 最终源码重建：wheel 54,393 字节 / `ced8c72c…f401`，便携包 1,200,605 字节 / `886f3bc7…a135`；PROGRESS/release notes/checklist/resume facts 全部刷新；措辞统一为「流程可重复」，不再声称逐位可复现。 |
| P3-1 | **DEFERRED（已公开记录）** | 发布说明 §5 新增第 9 条已知限制，注明无现存调用方与不改语义的理由。 |
| P3-2 | **CLOSED** | `test_gui.py` / `test_gui_batch.py` / `test_gui_lifecycle.py` 均导入 `tests.settings_harness`。 |

复验矩阵（2026-09-26，全部实测）：全量套件 253 项 ×3 连过（每次 0 孤儿进程）；GUI 模块对 20 连过；
便携冒烟 11/11；wheel 干净 venv 冒烟 8/8；HKCU 注册往返快照逐键相同；`git diff --check` 退出码 0；
产物哈希与文档记录一致。最终 `git status`/diff 快照见 `PROGRESS.md` 顶部与本地 checkpoint commit。
