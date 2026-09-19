# DuctZip 架构建议

更新时间：2026-09-19

## 架构目标

DuctZip 的架构目标是：先做一个可靠的 Windows 解压工具，同时保留后续扩展到 GUI、右键菜单、批量任务和更强文件管理能力的空间。

核心原则：

- UI 不直接调用 `7z.exe`。
- 解压后端可以替换。
- Shell 集成和主程序解耦。
- 后台任务可取消、可汇报进度、可记录错误。
- 安全策略默认开启，而不是交给用户记住。
- 不支持的能力诚实声明，不假装已防护（见 DD-012）。

## 推荐分层

```text
UI
|
+-- ShellIntegration
|
+-- ArchiveEngine
|
+-- Core
|
+-- Utils
```

更具体的模块关系：

```text
ductzip/
  core/
    smart_output.py    # SmartOutputPolicy、archive_logical_name、冲突推导（纯计算，无副作用）
    extraction.py      # ExtractionService：list -> 策略 -> 冲突 -> 引擎解压的编排
  app/
    main.py
    bootstrap.py
  ui/
    main_window.py
    archive_view.py
    extract_dialog.py
    task_panel.py
    settings_page.py
  archive/
    engine.py
    sevenzip_cli.py
    capabilities.py
    parser.py
    password.py
  shell/
    context_menu.py
    file_association.py
    open_with.py
  security/
    path_safety.py
    motw.py
    overwrite_policy.py
  utils/
    paths.py
    logging.py
    platform.py
```

当前实际落地的模块（截至 v0.7，上图中的 app/security/utils 仍是方向性建议，尚未建包）：

```text
ductzip/
  cli.py               # CLI 入口：extract/list/test/doctor/batch-extract/shell/settings
  shell.py             # Windows Explorer 集成：HKCU 注册/卸载/状态、稳定调用协议（DD-015）
  settings.py          # 每用户设置模型：存储/恢复/校验/优先级，详见 DD-016
  motw.py              # Mark-of-the-Web 传播：Zone.Identifier ADS 复制，尽力而为（DD-018）
  core/
    smart_output.py    # SmartOutputPolicy、archive_logical_name、冲突推导
    extraction.py      # ExtractionService 编排（plan / extract_with_progress，支持 cancel_event）
    queue.py           # BatchQueue：任务状态机、顺序执行、重试、取消路由、结构化批量日志（DD-013）
  archive/
    __init__.py        # 错误类型与数据结构（ArchiveError 族、ArchiveEntry、ArchiveListing、ProgressEvent）
    sevenzip.py        # SevenZipCliEngine：7z 进程封装、输出解析、错误映射、路径校验、子进程生命周期
  gui/
    app.py             # MainWindow（单解压 + 批量队列工作流、窗口关闭的有界回收逻辑、设置应用）
    workers.py         # ExtractWorker / PreviewWorker / BatchWorker：QObject worker，与窗口解耦可独立单测
    settings_dialog.py # 设置对话框：与 CLI settings 共用同一 Settings 模型
```

## 各层职责

### UI

负责用户交互，不负责解压细节。

职责：

- 主窗口、拖拽、按钮、菜单、设置页。
- 显示压缩包内容。
- 显示解压进度、取消按钮和错误提示。
- 收集用户选择的输出目录、覆盖策略、密码。

禁止：

- 禁止直接拼接 `7z.exe` 命令。
- 禁止直接解析 7-Zip 输出。
- 禁止直接写安全策略。

### ArchiveEngine

负责所有压缩包相关能力。

职责：

- `list_archive()`：列出压缩包内容。
- `test_archive()`：测试压缩包完整性。
- `extract_archive()`：执行解压。
- `detect_format()`：识别格式。
- `get_capabilities()`：返回后端支持能力。
- 解析 7-Zip 输出并转换为结构化事件。

第一版可以使用 `SevenZipCliEngine`。后续可替换为：

- 7-Zip DLL。
- libarchive。
- 其他 Python 库。

v0.4.1 稳定化后的进程生命周期设计（DD-010）：引擎用专用 reader 线程独占子进程输出流的读取与关闭——Windows 上 cmd/7z 的后代进程可继承管道写端，任何非 reader 的主动关闭都可能阻塞到后代全部退出（实测 ~15s）。取消走 terminate -> wait(2s) -> kill -> wait(2s) 链并在所有路径（正常结束、失败、取消、被遗弃的生成器）确定性回收；`list`/`test` 同样接受 `cancel_event`。

### Core

负责应用级业务模型和任务编排。

职责：

- `SmartOutputPolicy`：无副作用的最终输出目录计算（v0.4.1）。
- `ExtractionService`：编排 list -> 策略 -> 冲突 -> 引擎解压，CLI、GUI 和未来批量队列共用。
- 冲突检测与覆盖策略推导。
- 任务队列。
- 进度事件。
- 取消机制。
- 错误归一化。
- 配置读写。
- 最近文件、历史记录。

Core 不关心 UI 框架，也不关心底层压缩库细节。Core 可以调用 ArchiveEngine 接口，ArchiveEngine 不允许反向依赖 Core。

### ShellIntegration

负责 Windows 资源管理器集成。

职责：

- 右键菜单入口。
- 文件关联。
- “解压到当前目录”。
- “解压到同名文件夹”。
- “用 DuctZip 打开”。

Shell 集成应调用 DuctZip CLI 或主程序入口，不直接链接 UI 内部对象。

### Security

负责安全默认值。

职责：

- 防止路径穿越，例如压缩包内出现 `..\..\Windows`。
- 防止绝对路径写入危险目录。
- 拦截 Windows 保留设备名（CON/PRN/AUX/NUL/CONIN$/CONOUT$/COM1-9/LPT1-9，含 `NUL.txt` 等带扩展形式）。
- 覆盖策略统一处理。
- 传播 Mark-of-the-Web。
- 临时目录隔离。
- 密码不落盘。

安全策略应位于 Core 和 ArchiveEngine 之间，不能只在 UI 层做提示。

诚实边界（DD-012）：压缩包内符号链接 / Junction / 重解析点的解压当前不支持、不做防护；7-Zip CLI 会按链接目标写入，CLI 层无法可靠拦截。压缩包在规划与解压之间被篡改时，以引擎每次实际解压前自行 list 的真实条目为唯一安全依据，调用方 listing 永不参与安全校验。

### Utils

负责平台工具和通用函数。

职责：

- 路径规范化。
- 日志。
- 平台判断。
- 程序资源路径。
- 外部命令查找。

## 依赖方向

允许：

```text
UI -> Core
UI -> ArchiveEngine interface
Core -> ArchiveEngine interface
Core -> Security
ShellIntegration -> CLI/App entry
ArchiveEngine -> Utils
Security -> Utils
```

禁止：

```text
Core -> UI
ArchiveEngine -> UI
Security -> UI
ShellIntegration -> UI internal widgets
Utils -> Core
```

## 关键接口建议

### ArchiveEngine

```python
class ArchiveEngine:
    def list(self, archive_path: Path) -> ArchiveListing:
        ...

    def test(self, archive_path: Path, password: str | None = None) -> TestResult:
        ...

    def extract(
        self,
        archive_path: Path,
        output_dir: Path,
        password: str | None = None,
        overwrite_policy: OverwritePolicy = "skip",
    ) -> Iterator[ProgressEvent]:
        ...
```

v0.4.1 起，ArchiveEngine 不再接收 Smart output 或冲突策略参数；这些决策由 Core 层的 `ExtractionService` + `SmartOutputPolicy` 完成。引擎也不接收任何调用方提供的 listing：每次实际解压前，引擎都基于目标压缩包自行 `list` 取得真实条目并强制执行路径穿越校验，任何调用者传入的数据都不能替代该安全检查（`ExtractionService` 可为策略规划预先 list 一次，属性能取舍，不参与引擎安全校验）。

### ExtractionService

```python
class ExtractionService:
    def plan(self, archive_path, requested_output_dir, *, smart_output=False,
             conflict_strategy="merge", overwrite_policy="skip",
             password=None, listing=None, cancel_event=None) -> ExtractionPlan:
        ...  # list -> SmartOutputPolicy -> 冲突检测/取消 -> 覆盖策略推导

    def extract_with_progress(self, archive_path, requested_output_dir, *, ...) -> Iterator[ProgressEvent]:
        ...
```

CLI、GUI 和批量队列（v0.5，`ductzip.core.queue`）都复用这一编排入口，按任务传入不同的压缩包与输出目录即可。

### BatchQueue

```python
class BatchQueue:
    def add(self, archive_path, requested_output_dir, *, smart_output=True,
            conflict_strategy="merge", overwrite_policy="skip",
            password=None) -> BatchTask: ...
    def run(self, cancel_event=None) -> Iterator[BatchEvent]: ...  # 并发 1，严格入队顺序
    def retry(self, task_id) -> BatchTask: ...        # 仅 failed/cancelled 合法
    def remove(self, task_id) -> None: ...             # 执行中不可移除
    def cancel_current(self) -> bool: ...              # 只取消在途任务
    def cancel_all(self) -> None: ...                  # 在途 + 排队立即取消
```

任务状态机：`queued → planning → running → completed/failed/cancelled`；`failed`/`cancelled → queued`（重试）；`completed` 终态。队列不接收调用方 listing、不做路径校验、不实现 Smart/冲突策略（DD-013）：每个任务恰好一次 `ExtractionService` 操作，引擎 fresh-listing 校验仍是唯一安全权威。`run()` 是确定性纯生成器，由调用方线程驱动；被遗弃前必须先 cancel 再排空。

### 批量前端（v0.5 已落地）

- CLI：`ductzip batch-extract <archives...> -o <root>` 把同一输出根传给每个任务；退出码 0/1/130/2；`--retries N` 重跑失败任务；Ctrl+C 走 `cancel_all()` 后关闭生成器以回收后端进程。
- GUI：`BatchWorker`（`ductzip.gui.workers`）在后台 `QThread` 上消费 `queue.run()` 并把每个 `BatchEvent` 转发给窗口；取消按钮直接调用队列的线程安全取消入口（worker 线程在 `run()` 执行期间没有事件循环，排队信号送达会死锁）。`BatchWorker.run()` 收尾直接 `QThread.currentThread().quit()`，不依赖跨线程排队投递结束线程（DD-014）。
- 窗口关闭：先 `cancel_all()`，再对批量线程做有界泵事件等待（复用 `_wait_for_thread`），最后走既有的预览/解压线程回收路径。

### ExtractRequest

```python
class ExtractRequest:
    archive_path: Path
    output_dir: Path
    password: str | None
    overwrite_policy: OverwritePolicy
    smart_extract: bool
    open_after_done: bool
```

### ProgressEvent

```python
class ProgressEvent:
    kind: str
    percent: int | None
    current_file: str | None
    message: str | None
```

## Smart Extraction 规则

Smart Extraction 用于避免把多个文件直接散落到目标目录。v0.4.1 起规则由 `ductzip.core.smart_output.SmartOutputPolicy` 统一计算，CLI 与 GUI 共用：

1. 空列表：最终输出目录等于用户指定输出目录。
2. 单个顶层普通文件：最终输出目录等于用户指定输出目录。
3. 单个顶层目录 `D`：通常等于用户指定输出目录；若输出目录名与 `D` 忽略大小写相同，则取其父目录，避免 `D/D`。
4. 多个顶层条目：通常等于 `输出目录/压缩包逻辑名`；若输出目录名与逻辑名忽略大小写相同，则直接用输出目录，避免 `name/name`。
5. 压缩包逻辑名去除常见归档扩展（zip/7z/rar/tar/tar.gz 等），并显式处理 `.7z.001`、`.partNN.rar` 等分卷命名。仅做名称推导，不做首卷/缺卷诊断。
6. 最终目录已存在顶层冲突时，沿用 `merge`、`rename`、`cancel` 策略；`rename` 仍是文件级自动重命名，不重命名整个输出目录。
7. 如果压缩包内路径存在风险，先阻止并显示风险原因；路径穿越校验由 ArchiveEngine 强制执行，校验始终基于引擎自己对目标压缩包的真实 listing，任何调用方数据都不能绕过。

## 错误处理

7-Zip 的错误输出不应直接展示给普通用户。建议统一映射：

| 内部错误 | 用户提示 |
| --- | --- |
| ArchiveNotFound | 找不到压缩包 |
| UnsupportedFormat | 暂不支持该格式 |
| PasswordRequired | 需要密码 |
| WrongPassword | 密码错误 |
| CorruptedArchive | 压缩包可能已损坏 |
| PathTraversalBlocked | 已阻止不安全路径 |
| OutputPermissionDenied | 没有写入目标目录的权限 |
| SevenZipMissing | 未找到 7-Zip 后端 |

## 日志策略

日志应服务于调试，而不是替代用户提示。

建议记录：

- 任务开始和结束时间。
- 7z 路径和版本。
- 压缩包路径 hash 或脱敏路径。
- 错误码。
- 失败阶段。

避免记录：

- 密码。
- 用户敏感文件名的完整列表，除非用户开启调试模式。

## 可替换点

第一版先使用 7-Zip CLI，但应预留以下替换点：

- `ArchiveEngine` 可替换为 DLL 或 libarchive。
- `UI` 可从 PySide6 替换为其他桌面框架。
- `ShellIntegration` 可从脚本注册升级为正式 Shell Extension。
- `ConfigStore` 可从 JSON 替换为 SQLite。
- `TaskRunner` 可从线程池升级为进程池或任务服务。

## 不做的事情

第一阶段不做：

- 自研 ZIP/7z/RAR 解压算法。
- 完整文件管理器。
- 云盘和同步。
- 自解压包生成。
- 压缩功能全量配置。
- 插件市场。
