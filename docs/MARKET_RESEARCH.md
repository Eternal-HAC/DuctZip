# DuctZip 竞品调研

更新时间：2026-07-02

## 调研目标

DuctZip 的目标不是重新实现压缩算法，而是做一个轻量、可靠、适合 Windows 日常使用的解压工具。竞品调研重点关注：

- 成熟解压软件如何组织压缩核心、UI、Shell 集成和插件能力。
- Windows 文件管理工具如何处理标签页、拖拽、预览、右键菜单和批量任务。
- 哪些设计适合 DuctZip 第一阶段借鉴，哪些会导致范围过大或维护成本过高。

## 调研对象总览

| 项目 | 类型 | 技术栈 | Star 量级 | 维护状态 | 参考优先级 |
| --- | --- | --- | --- | --- | --- |
| NanaZip | Windows 解压工具 | C/C++、MSIX、WinUI/现代 Windows 集成 | 14k+ | 活跃 | 最高 |
| PeaZip | 跨平台解压/文件管理 | Lazarus、FreePascal | 7k+ | 活跃 | 高 |
| 7-Zip-zstd | 7-Zip 增强版 | C、C++、Assembly | 7k+ | 活跃 | 高 |
| Files | 现代 Windows 文件管理器 | C#、WinUI、Windows App SDK | 44k+ | 活跃 | 高 |
| Explorer++ | 轻量 Windows 文件管理器 | C++、WinAPI | 3k+ | 活跃 | 中高 |
| Double Commander | 双栏文件管理器 | Pascal | 4k+ | 活跃 | 中 |
| Spacedrive | 跨设备文件管理器 | Rust、TypeScript、Tauri 类架构 | 38k+ | 活跃 | 中 |
| Czkawka / Krokiet | 文件清理工具 | Rust、Slint、CLI | 31k+ | 活跃 | 中 |
| muCommander | 跨平台双栏文件管理器 | Java、Gradle | 1k+ | 活跃 | 中 |
| p7zip-project | 7-Zip 跨平台 fork | C、C++、Assembly | 900+ | 活跃 | 中 |
| Windows File Manager | 经典文件管理器 | C、Win32 | 7k+ | 已归档 | 低 |

## 重点项目分析

### NanaZip

NanaZip 是 7-Zip 的现代 Windows 派生版本，目标是把 7-Zip 的压缩核心带入 Windows 10/11 的现代体验。仓库结构按职责拆分明显，包括 `NanaZip.Core`、`NanaZip.Codecs`、`NanaZip.UI.Classic`、`NanaZip.UI.Modern`、`NanaZip.ExtensionPackage`、`NanaZipPackage` 等。

功能特点：

- 继承 7-Zip、7-Zip ZS、7-Zip NSIS 的核心能力。
- 支持 Windows 10/11 文件资源管理器右键菜单。
- 支持 MSIX 打包、暗色模式、Mica、Per-Monitor DPI。
- 提供 Smart Extraction、解压后打开文件夹、策略机制。
- 默认传播 Mark-of-the-Web，降低从互联网下载压缩包后的安全风险。

值得借鉴：

- 核心、编解码、经典 UI、现代 UI、扩展包分层清晰。
- Windows Shell 集成单独封装，不把 UI 和右键菜单混在一起。
- Smart Extraction 是 DuctZip 应重点参考的用户体验。
- Mark-of-the-Web 传播值得作为安全解压的默认策略。

不建议照搬：

- 不建议直接 fork NanaZip。它继承大量 7-Zip 历史代码，理解和维护成本高。
- 不建议第一版实现完整 MSIX、策略系统、双 UI。
- 不建议一开始追求和 7-Zip 完整功能对齐。

### PeaZip

PeaZip 是跨平台压缩/解压工具，也带有文件管理能力。它使用 Lazarus/FreePascal，Windows 安装包使用 InnoSetup。项目覆盖 7Z、ZIP、RAR 提取、TAR、GZ、BZ2、ISO、Zstandard 等大量格式。

功能特点：

- 同时提供压缩、解压、加密、分卷、自解压、文件管理。
- 支持便携版。
- 支持广泛格式和多平台。
- 将压缩包浏览体验做得接近文件管理器。

值得借鉴：

- “压缩包即目录”的浏览模型。
- 格式支持清单和能力识别。
- 便携版思路适合个人工具传播。
- 解压、测试、校验、加密等能力可以按阶段逐步开放。

不建议照搬：

- Lazarus/FreePascal 对 DuctZip 的 Python/PySide6 路线没有直接复用价值。
- 功能范围过宽，第一版不应同时做压缩、加密、分卷、自解压和完整文件管理。

### 7-Zip-zstd

7-Zip-zstd 是 7-Zip 的增强版本，重点在 codec 扩展，支持 Brotli、Fast-LZMA2、Lizard、LZ4、LZ5、Zstandard 等。

功能特点：

- 保持 7-Zip 命令行和 DLL 生态兼容。
- 扩展格式、codec 和 hash 算法。
- 可作为完整安装包，也可作为 codec 插件。

值得借鉴：

- DuctZip 应把格式能力建模成可查询的 `ArchiveCapabilities`，不要在 UI 里硬编码。
- 解压核心应该是可替换的，第一版可调用 `7z.exe`，后续再替换为 DLL 或其他后端。
- hash、test、list、extract 应作为后端能力，而不是 UI 功能。

不建议照搬：

- 不建议直接改 7-Zip-zstd 源码。
- 不建议第一版实现 codec 插件系统，只需要先预留扩展点。

### Files

Files 是现代 Windows 文件管理器，使用 C#、WinUI 和 Windows App SDK。项目结构主要包括 `src`、`tests`、`docs`，并有清晰的社区贡献和发布流程。

功能特点：

- 现代 Windows 11 风格。
- 标签页、多任务、文件标签、深度系统集成。
- 适合替代或补充 Windows 文件资源管理器。

值得借鉴：

- Windows 现代视觉和交互：面包屑、标签页、快捷操作、设置页。
- 用户任务以“当前位置 + 选择对象 + 操作按钮”为中心。
- 文档、测试、发布节奏比较规范。

不建议照搬：

- DuctZip 第一版不应做完整文件管理器。
- C# / WinUI 路线和 PySide6 路线不同，不应混用技术栈。
- Files 的体量和社区流程对个人早期项目偏重。

### Explorer++

Explorer++ 是轻量 Windows 文件管理器，使用 C++ 和 WinAPI。它支持便携配置、标签页、预览、拖拽、书签、搜索、过滤和多视图。

值得借鉴：

- 轻量、快速、低依赖。
- 便携模式和配置文件模式。
- 和 Windows Explorer 的拖放互操作。
- 文件预览和筛选能力。

不建议照搬：

- 传统 Win32 UI 对现代外观升级成本较高。
- C++/WinAPI 不适合 DuctZip 第一阶段快速迭代。

## 其他项目分析

### Double Commander

Double Commander 是 Total Commander 风格的双栏文件管理器，使用 Pascal。它的 `plugins`、`sdk`、`components`、`src` 结构体现了成熟的插件化设计。

可借鉴双栏操作、键盘优先、批量重命名、插件 SDK。不建议照搬高密度 UI，普通用户学习成本较高。

### Spacedrive

Spacedrive 使用 Rust 构建虚拟分布式文件系统，覆盖多设备和云文件。它适合参考“核心服务 + 多端 UI + 扩展适配器”的长期架构。

不建议 DuctZip 第一版引入分布式文件系统、跨设备同步或复杂索引服务。

### Czkawka / Krokiet

Czkawka 是 Rust 写的文件清理工具，包含 core library、CLI 和 GUI。它强调多线程、缓存、无网络追踪、可复用核心库。

DuctZip 可借鉴 `core + cli + gui` 分离、后台任务、缓存和安全默认值。不应照搬清理工具功能域。

### muCommander

muCommander 是 Java/Gradle 项目，模块化程度高，包含 `format-*`、`protocol-*`、`viewer-*`、`os-*` 等模块。

可借鉴协议层、格式层、预览层的插件化拆分。不建议采用 Java 桌面路线。

### p7zip-project

p7zip-project 是 7-Zip/p7zip 的新 fork，适合参考命令行接口、跨平台构建和格式识别能力。

不建议作为 Windows GUI 的主要参考，因为它不是 Windows-first 桌面体验项目。

### Windows File Manager

Windows File Manager 是微软开源的经典 WinFile，已经归档。它有历史价值，适合学习原生文件管理器的最小模型。

不建议照搬，因为 UI、交互和代码组织都不适合现代项目。

## 我的结论

### 为什么选择 Python + PySide6

DuctZip 当前更适合作为个人可持续迭代项目，而不是一次性追求大型原生应用。Python + PySide6 的优势是：

- 开发速度快，适合快速验证解压流程、拖拽、进度条和错误处理。
- PySide6 能提供足够好的 Windows 桌面体验。
- 后台解压、路径处理、配置、日志、测试都可以用 Python 快速搭建。
- 后续如果核心稳定，可以再将性能敏感部分迁移到 Rust/C++ 或 DLL 调用。

放弃 C# / WinUI 的原因：

- Windows 现代体验更强，但早期工程复杂度更高。
- 当前目标是先做出可靠解压工具，不是完整文件资源管理器。

放弃 Electron 的原因：

- 包体和运行成本偏高。
- 对本地文件、Shell 集成和原生对话框并不天然更简单。

### 为什么调用 7-Zip

压缩算法不是 DuctZip 的核心创新点。调用 7-Zip 可以直接获得成熟格式支持和稳定性：

- 支持 ZIP、7z、RAR 提取、TAR、GZ、BZ2、ISO 等常见格式。
- 命令行能力成熟，便于第一版快速集成。
- 可以先通过进程调用实现，后续再考虑 DLL 或其他库。
- 规避自研压缩/解压算法的安全和正确性风险。

### 为什么不 fork NanaZip

NanaZip 是最值得参考的 Windows 解压项目，但不适合作为 DuctZip 的起点：

- 代码体量大，历史包袱重。
- 需要理解 7-Zip、Windows Shell Extension、MSIX、现代 UI、多语言等复杂体系。
- DuctZip 的定位是轻量工具，不是 7-Zip 的完整现代化替代品。

正确做法是参考 NanaZip 的产品设计和分层方式，而不是复制代码。

### 为什么第一版不做压缩功能

第一版应把“解压”做到可靠：

- 压缩包识别。
- 列出内容。
- 选择输出目录。
- 智能解压。
- 中文路径。
- 密码提示。
- 进度和取消。
- 错误提示。
- 路径穿越防护。

压缩功能涉及格式选择、压缩等级、加密、分卷、排除规则、覆盖策略和性能参数，会显著拉大范围。建议 v1.0 之前以解压为主，压缩能力放到后续阶段。

### 为什么第一版不做完整文件管理器

Files、Double Commander、muCommander 证明文件管理器是大项目。DuctZip 可以有文件浏览和压缩包浏览，但不应替代 Explorer。

第一阶段只需要围绕解压流程提供最小文件操作：

- 拖入压缩包。
- 浏览压缩包目录。
- 选择输出目录。
- 解压完成后打开目录。
- 批量解压。

完整文件管理器能力，例如标签页、云盘、双栏、文件标签、搜索索引、缩略图缓存，应放在长期路线中谨慎评估。

