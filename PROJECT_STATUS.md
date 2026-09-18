# DuctZip Project Status

更新时间：2026-09-19

## 当前阶段

当前已完成 v0.4.1 Smart Output Semantics 及其稳定化回归（取消响应、子进程回收、GUI 线程安全、Windows 保留设备名防护），完成 v0.5 批量队列核心（`ductzip.core.queue`：任务状态机、顺序执行、失败隔离、重试、取消当前/全部、结构化批量日志、逐任务 Smart Output），并完成 v0.5 批量 CLI 与 GUI 工作流（`ductzip batch-extract` 命令 + 队列列表/逐任务状态进度错误/重试/移除/取消当前/取消全部/最终输出可见）。全部 144 项测试通过。下一步进入 v0.6 Windows 集成（需先确认 LONG_TASK.md §10.2 的人工决策项）。

v0.1 目标已经完成：DuctZip 可以发现 7-Zip、接收压缩包和输出目录、调用后端解压，并返回清晰结果。

## 当前仓库状态

已有文档：

- `docs/MARKET_RESEARCH.md`：GitHub 竞品调研。
- `docs/ARCHITECTURE.md`：DuctZip 架构建议。
- `docs/ROADMAP.md`：开发路线图。
- `docs/DESIGN_DECISIONS.md`：关键设计决策。
- `docs/PRD.md`：v0.1 + v0.2 产品需求文档。

当前已完成 v0.1 CLI 原型、v0.2 解压核心增强、v0.3 PySide6 GUI 原型、v0.4 Smart Extraction 和 v0.4.1 Smart Output Semantics。

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
- 建立 PySide6 GUI 可选模块和 `ductzip-gui` 入口。
- 实现 GUI 主窗口：压缩包选择、文件拖拽、输出目录选择、覆盖策略选择、进度条、日志、取消按钮。
- GUI 支持压缩包内容预览，显示文件名、大小和类型。
- GUI 支持密码输入和显示/隐藏密码。
- GUI 支持解压完成后打开目标目录。
- GUI 通过 `extract_with_progress()` 复用现有解压核心。
- 增加 PySide6 offscreen GUI 初始化测试。
- 实现 Smart Extraction 基础规则：当压缩包已有唯一同名顶层目录时，避免重复套一层目录。
- 增加 `--smart-output` CLI 参数。
- GUI 默认开启 Smart output 复选框。
- GUI 显示 Smart output 计算后的最终实际输出目录。
- 实现输出冲突检测：当最终输出目录下已存在压缩包顶层条目时，GUI 会提前显示冲突摘要。
- 实现冲突处理策略：`merge`、`rename`、`cancel`。
- 增加 `--conflict-strategy` CLI 参数。
- GUI 支持冲突处理策略选择。
- 增加 Smart Extraction 单元测试和真实 ZIP 集成测试。
- 将 Smart output 与冲突策略从 `SevenZipCliEngine` 抽离到 `ductzip.core`：新增无副作用的 `SmartOutputPolicy` 和统一编排服务 `ExtractionService`，CLI 与 GUI 走同一策略与编排。
- 明确 v0.4.1 Smart Output 语义：空列表和单顶层文件直接解压到指定输出；单顶层目录同名时解压到父目录避免 `D/D`；多顶层条目默认解压到按压缩包逻辑名命名的子目录，避免 `name/name`。
- 压缩包逻辑名推导支持常见归档扩展（zip/7z/rar/tar.gz 等）及分卷命名（`.7z.001`、`.partNN.rar`），仅做名称推导，不做首卷/缺卷诊断。
- GUI 选择压缩包后默认输出目录改为压缩包父目录，Final output 实时显示策略结果。
- 引擎仍负责路径穿越校验，且每次实际解压前都基于目标压缩包自行 list 取得真实条目再校验；调用方传入的 listing 仅供策略规划参考，校验不可被绕过。
- 完善 README 开源展示内容：项目定位、功能、技术栈、使用方式、测试方式、路线图和项目亮点。
- 增加 MIT License。
- 更新 `.gitignore`，避免提交本地压缩包样例、输出目录和未来第三方二进制目录。
- 稳定化（v0.4.1 stabilization）：取消无输出后端时从阻塞 ~15s 降至秒级响应；输出流改由专用 reader 线程独占关闭，杜绝关闭管道时阻塞。
- 稳定化：所有子进程路径（正常结束、失败、取消、被遗弃的生成器）都确定性回收，取消后不留孤儿 7-Zip 进程。
- 稳定化：`list` / `test` / `ExtractionService.plan` 支持 `cancel_event`，规划阶段（后端 listing）也可取消。
- 稳定化：取消事件恰好上报一次（事件 + 异常双通道去重）；GUI worker 意外异常经 `failed` 信号呈现，不再静默杀死线程。
- 稳定化：GUI 预览改为长寿命 worker 线程 + 排队请求信号模型，修复 per-preview 线程导致的间歇性堆损坏；预览结果带代际令牌，切换压缩包/密码后迟到结果一律丢弃。
- 稳定化：修改或清空压缩包路径时立即清空预览、最终输出、冲突摘要和上次解压的打开目录状态。
- 稳定化：窗口关闭时预览线程 2s、解压线程 10s 有界回收并泵事件，关闭路径不再死锁或触发已删除 QThread 的 RuntimeError。
- 稳定化：引擎路径校验新增 Windows 保留设备名（CON/PRN/AUX/NUL/CONIN$/CONOUT$/COM1-9/LPT1-9，含 `NUL.txt` 等带扩展形式）。
- 稳定化：明确安全边界——符号链接/Junction/重解析点解压不做防护（当前不支持，诚实声明）；压缩包在规划与解压之间被篡改时，以引擎每次自行 list 的真实条目为准。
- 稳定化：GUI 单元测试改用 stub 引擎保证确定性（真实后端 GUI 覆盖留作人工冒烟证据），真实后端覆盖保留在 CLI 与引擎生命周期测试。
- 测试规模：84 → 107 项（新增引擎生命周期 13 项、GUI 生命周期 7 项，GUI 预览相关测试重写为 stub 引擎 + offscreen）。
- v0.5 批量核心：新增 `ductzip.core.queue`；`BatchQueue` 以并发 1 严格按入队顺序驱动 `ExtractionService`，每个压缩包恰好一次服务操作。
- v0.5 批量核心：任务状态机（queued/planning/running/completed/failed/cancelled）与合法迁移；`completed` 终态，`failed`/`cancelled` 可重试可移除，执行中不可移除。
- v0.5 批量核心：单任务失败不影响后续任务（含规划阶段失败与意外异常隔离）；重试仅针对失败/取消的任务，attempts 计数。
- v0.5 批量核心：`cancel_current()` 只取消在途任务；`cancel_all()` 立即取消在途与排队任务；外部 `cancel_event` 同样生效。
- v0.5 批量核心：结构化批量日志持久化状态迁移与批次起止，进度事件只实时下发不落盘；密码从一切持久化消息与后端原始失败输出中脱敏。
- v0.5 批量核心：队列不接收调用方 listing、不做路径校验；队列级共享输出根 = 每个任务各自的 requested_output_dir，Smart Output 仍在服务内逐任务计算。
- 测试规模：107 → 127 项（新增 `tests/test_batch_queue.py` 20 项，全部确定性、无真实后端）。
- v0.5 批量 CLI：新增 `ductzip batch-extract`，多压缩包共享 `-o` 输出根，逐任务 `[完成]/[失败]/[取消]` 报告；退出码 0 全部完成 / 1 部分失败 / 130 Ctrl+C 取消 / 2 用法错误；`--retries N` 重跑失败任务，Ctrl+C 触发 `cancel_all()` 并确定性回收后端进程。
- v0.5 批量 GUI：拖入/按钮多选添加入队，队列列表逐任务显示状态、进度百分比、错误与最终输出目录；开始、重试（仅失败/取消可重试）、按合法性移除（执行中拒绝并记录日志）、取消当前、取消全部；双击已完成任务打开最终输出目录。
- v0.5 批量 GUI：批量运行在后台线程，窗口全程可响应；关闭窗口时有界取消并回收批量线程（`cancel_all` + 泵事件有界等待），不遗留孤儿线程。
- v0.5 批量测试：新增 CLI 批量 8 项（含真实后端顺序/重试/逐任务 Smart Output 验证）与 GUI 批量 9 项（offscreen + stub 引擎）。
- 测试规模：127 → 144 项。

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
- v0.4：Smart Extraction，已完成。
- v0.4.1：Smart Output Semantics，已完成，并通过稳定化回归（取消、子进程回收、GUI 线程安全、保留设备名）。
- v0.5：批量解压已完成（队列核心 + CLI 批量命令 + GUI 批量工作流，144 项测试通过）。
- v0.6 之后：Windows 集成、发布打包。

### 明确暂缓

- 压缩功能。
- 完整文件管理器。
- 云盘和同步。
- 自研解压算法。
- 直接 fork NanaZip。
- Windows 右键菜单，直到核心稳定后再做。

## 下一步

下一步进入 v0.6 Windows 集成（右键菜单、预览处理器等），但该阶段受 LONG_TASK.md §10.2 人工决策项约束（提交授权、发布范围等），开始前需先与用户确认。稳定化与批量阶段确认的两条安全边界仍然适用：

1. 压缩包内符号链接 / Junction / 重解析点不做防护，属于当前不支持的能力，文档与错误提示需诚实声明，不假装已防护。
2. 引擎在每次实际解压前自行 list 并校验真实条目；调用方（服务规划、批量预检）的 listing 仅供策略参考，安全校验不可被任何预计算数据绕过。

建议任务顺序：

1. ~~设计批量任务模型：每个压缩包独立状态、输出目录和错误信息。~~ 已完成（`ductzip.core.queue`）。
2. ~~CLI 支持传入多个压缩包或新增批量命令。~~ 已完成（`ductzip batch-extract`）。
3. ~~GUI 支持拖入多个压缩包并显示任务列表。~~ 已完成（含重试/移除/取消/最终输出可见）。
4. ~~批量任务支持单个失败不影响后续任务。~~ 已完成并有测试。
5. 真实桌面环境手动试用 Smart output 和冲突策略。
6. 评估是否需要补充 GitHub Actions 自动测试。

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
