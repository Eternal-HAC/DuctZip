# DuctZip 架构建议

更新时间：2026-07-02

## 架构目标

DuctZip 的架构目标是：先做一个可靠的 Windows 解压工具，同时保留后续扩展到 GUI、右键菜单、批量任务和更强文件管理能力的空间。

核心原则：

- UI 不直接调用 `7z.exe`。
- 解压后端可以替换。
- Shell 集成和主程序解耦。
- 后台任务可取消、可汇报进度、可记录错误。
- 安全策略默认开启，而不是交给用户记住。

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
  app/
    main.py
    bootstrap.py
  ui/
    main_window.py
    archive_view.py
    extract_dialog.py
    task_panel.py
    settings_page.py
  core/
    models.py
    task_runner.py
    progress.py
    errors.py
    config.py
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

### Core

负责应用级业务模型和任务编排。

职责：

- 任务队列。
- 进度事件。
- 取消机制。
- 错误归一化。
- 配置读写。
- 最近文件、历史记录。

Core 不关心 UI 框架，也不关心底层压缩库细节。

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
- 覆盖策略统一处理。
- 传播 Mark-of-the-Web。
- 临时目录隔离。
- 密码不落盘。

安全策略应位于 Core 和 ArchiveEngine 之间，不能只在 UI 层做提示。

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

    def extract(self, request: ExtractRequest) -> Iterator[ProgressEvent]:
        ...
```

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

Smart Extraction 用于避免把多个文件直接散落到目标目录。

建议规则：

1. 如果压缩包根目录只有一个顶层文件夹，解压到用户选择目录。
2. 如果压缩包根目录有多个文件或多个文件夹，默认创建同名目录。
3. 如果目标同名目录已存在，提示合并、重命名或取消。
4. 如果压缩包内路径存在风险，先阻止并显示风险原因。

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

