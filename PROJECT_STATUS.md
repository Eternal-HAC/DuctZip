# DuctZip Project Status

更新时间：2026-07-03

## 当前阶段

当前处于 v0.2 解压核心增强完成、准备进入 v0.3 GUI 原型阶段。

v0.1 目标已经完成：DuctZip 可以发现 7-Zip、接收压缩包和输出目录、调用后端解压，并返回清晰结果。

## 当前仓库状态

已有文档：

- `docs/MARKET_RESEARCH.md`：GitHub 竞品调研。
- `docs/ARCHITECTURE.md`：DuctZip 架构建议。
- `docs/ROADMAP.md`：开发路线图。
- `docs/DESIGN_DECISIONS.md`：关键设计决策。
- `docs/PRD.md`：v0.1 + v0.2 产品需求文档。

当前已完成 v0.1 CLI 原型和 v0.2 解压核心增强，代码已具备继续进入 v0.3 GUI 原型的基础。

当前正在进行 GitHub 开源首发整理，目标是让仓库具备基础开源展示、测试复现和求职项目展示所需的 README、License、文档和 Git 历史。

## 已完成

- 完成 Windows 解压工具和文件管理工具竞品调研。
- 确定重点参考 NanaZip、PeaZip、7-Zip-zstd、Files、Explorer++。
- 确定不 fork NanaZip，不自研压缩算法。
- 确定第一阶段聚焦解压，不做完整文件管理器。
- 确定 v0.1 先发现系统 7-Zip，v1.0 发布包再内置 7-Zip 后端。
- 建立架构分层建议。
- 建立路线图。
- 建立设计决策记录。
- 建立 v0.1/v0.2 PRD。
- 初始化 Python 项目结构。
- 实现 `ductzip extract <archive_path> --output <output_dir>` CLI 入口。
- 实现 `--sevenzip` 手动指定后端。
- 实现 7-Zip 后端发现。
- 支持从 Windows 卸载注册表发现自定义安装目录中的 7-Zip。
- 实现 `SevenZipCliEngine` 最小解压能力。
- 用真实 7-Zip 验证 ZIP 解压。
- 验证中文路径和空格路径。
- 增加基础单元测试。
- 增加真实 ZIP 集成测试，有 7-Zip 时执行，无 7-Zip 时跳过。
- 增加真实 7z 集成测试，有 7-Zip 时执行，无 7-Zip 时跳过。
- 增加真实 RAR5 集成测试，使用 `tests/让子弹飞（二）.rar` 样例。
- 实现 `ductzip doctor` 诊断命令。
- 输出 7-Zip 后端路径和版本。
- 扩展基础错误映射：损坏压缩包、密码错误、不支持格式、权限错误。
- 增加 `extract --verbose` 基础调试输出。
- 增加 README 最小使用说明。
- 实现 `list_archive()`，并提供 `ductzip list` 命令。
- 实现 `test_archive()`，并提供 `ductzip test` 命令。
- 支持 `--password` 和 `--password-prompt` 密码参数。
- 增加加密 7z 的正确密码和错误密码测试。
- 解压前阻止路径穿越条目，避免写出到输出目录之外。
- 实现 `ProgressEvent` 和 `extract_with_progress()`，为后续 GUI 进度条提供事件流。
- 实现核心层任务取消：`extract_with_progress()` 支持取消信号，取消时终止 7-Zip 子进程并抛出 `ArchiveCancelled`。
- 实现覆盖策略：`skip`、`overwrite`、`rename`，默认 `skip`。
- 完善 README 开源展示内容：项目定位、功能、技术栈、使用方式、测试方式、路线图和项目亮点。
- 增加 MIT License。
- 更新 `.gitignore`，避免提交本地压缩包样例、输出目录和未来第三方二进制目录。

## 当前关键决策

### 技术方向

- 语言：Python。
- GUI：后续使用 PySide6。
- 解压后端：第一版调用 7-Zip CLI。
- 后端分发：v0.1 不内置 7-Zip，发布版计划内置官方 7-Zip Extra 的 standalone console 后端。
- 架构：Core、ArchiveEngine、UI、ShellIntegration、Security 分层。

### 产品范围

- v0.1：CLI 原型，已完成。
- v0.2：可复用解压核心，已完成。
- v0.3 之后：GUI、Smart Extraction、批量解压、Windows 集成。

### 明确暂缓

- 压缩功能。
- 完整文件管理器。
- 云盘和同步。
- 自研解压算法。
- 直接 fork NanaZip。
- Windows 右键菜单，直到核心稳定后再做。

## 下一步

下一步应进入 v0.3 PySide6 GUI 原型。

建议任务顺序：

1. 进入 v0.3 PySide6 GUI 原型。
2. 设计主窗口、文件拖拽、输出目录选择和任务进度展示。
3. 评估是否需要补充 GitHub Actions 自动测试。
4. 如果未来发布包内置 7-Zip，增加 `THIRD_PARTY_NOTICES.md` 并附带 7-Zip 许可证信息。

## 工作方式

当前对话作为 DuctZip 主线程，负责：

- 项目总控。
- 文档维护。
- 阶段决策。
- 路线图更新。

后续可以为具体任务开子对话，例如：

- 实现 v0.1 CLI 原型。
- 深入分析 NanaZip。
- 设计 PySide6 GUI。
- 设计 Windows 右键菜单。

如果开启新对话，新对话应先读取：

- `PROJECT_STATUS.md`
- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/DESIGN_DECISIONS.md`
- `docs/ROADMAP.md`

## 验收提醒

每完成一个阶段，都应更新：

- `PROJECT_STATUS.md`
- `docs/ROADMAP.md`
- `docs/DESIGN_DECISIONS.md`，如果产生新的关键决策
- `CHANGELOG.md`，当开始发布版本后
