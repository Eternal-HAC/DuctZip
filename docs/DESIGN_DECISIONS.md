# DuctZip Design Decisions

更新时间：2026-09-19

本文档记录 DuctZip 的关键设计决策。每条决策都应说明采用方案、原因、放弃方案和后续复审条件。

## DD-001 采用 7-Zip CLI 作为第一版解压后端

状态：已验证（v0.4.1 稳定化后）。

采用方案：

- 第一版通过进程调用 `7z.exe`。
- 在 `ArchiveEngine` 中封装命令构造、输出解析、错误映射和进度事件。

原因：

- 7-Zip 成熟稳定，格式支持广。
- 避免自研压缩/解压算法。
- CLI 接入成本低，适合快速原型。
- 后续可以替换为 DLL 或其他后端。

放弃方案：

- 自己实现 ZIP。
- 直接 fork 7-Zip。
- 直接 fork NanaZip。
- 第一版直接调用 7-Zip DLL。

风险：

- CLI 输出解析可能受版本和语言影响。
- 进程调用的进度控制不如库调用精细。
- 需要处理 7z 缺失、路径查找和版本兼容。

复审条件：

- 如果 CLI 解析导致明显不稳定，再评估 DLL 后端。
- 如果需要更细粒度进度或性能优化，再评估后端替换。

验证记录（2026-09-19）：真实后端集成测试覆盖 ZIP/7z/RAR/加密包/中文与空格路径；CLI 输出解析在 24.08 上稳定；稳定化阶段补齐了取消响应与子进程回收（见 DD-010）。已知的 CLI 固有风险——杀毒软件扫描子进程导致首次调用耗时 0.27s-15s+ 不等——被 GUI 单元测试用 stub 引擎规避，真实后端 GUI 覆盖转为人工冒烟证据。

## DD-002 GUI 使用 PySide6

状态：已验证（v0.4.1 稳定化后）。

采用方案：

- 使用 PySide6 构建 Windows 桌面界面。
- UI 层只依赖 Core 和 ArchiveEngine 接口，不直接调用 `7z.exe`。

原因：

- Python 开发速度快，适合个人项目快速迭代。
- PySide6 能提供成熟桌面控件、拖拽、线程和系统对话框。
- 与 CLI/core 共享 Python 代码，降低早期维护成本。

放弃方案：

- Tkinter：开发简单但现代体验不足。
- Electron：包体大，本地集成成本不低。
- C# / WinUI：Windows 体验强，但早期工程复杂度较高。
- C++ / Win32：性能好但迭代慢。

风险：

- PySide6 包体较大。
- Windows 原生观感不如 WinUI。
- 打包和签名需要后续专门处理。

复审条件：

- 如果后续目标转为完整 Windows 文件管理器，再评估 C# / WinUI。
- 如果 GUI 包体和启动速度成为主要问题，再评估替代方案。

验证记录（2026-09-19）：offscreen 下 19 项 GUI 测试通过；稳定化阶段确立了后台线程模型（见 DD-011），解决了线程churn导致的堆损坏与关闭死锁。包体与启动速度未量化，仍列为打包阶段（v0.7）复审项。

## DD-003 第一版只做解压，不做完整压缩功能

状态：已建议。

采用方案：

- v1.0 之前以解压为核心。
- 可以保留压缩功能接口，但不进入第一阶段交付范围。

原因：

- 解压是更高频、更容易形成稳定体验的场景。
- 压缩功能会引入格式、等级、加密、分卷、排除规则等复杂配置。
- 第一阶段应优先验证 7z 调用、路径安全、进度、GUI 和右键菜单。

放弃方案：

- 第一版同时做压缩和解压。
- 第一版提供完整 7-Zip 参数面板。

复审条件：

- 当解压流程稳定、用户明确需要压缩时，再进入 v1.x。

## DD-004 不做完整文件管理器

状态：已建议。

采用方案：

- DuctZip 只做与压缩包相关的最小文件浏览能力。
- 不替代 Windows Explorer。

原因：

- Files、Double Commander、muCommander 说明文件管理器是大型长期项目。
- 完整文件管理器会引入标签页、搜索索引、缩略图、云盘、权限、网络位置等复杂问题。
- DuctZip 的核心价值应先聚焦在“可靠解压”。

允许范围：

- 压缩包内容浏览。
- 输出目录选择。
- 解压后打开目录。
- 批量解压列表。

暂不做：

- 双栏文件管理。
- 文件标签。
- 全盘搜索。
- 云盘聚合。
- 缩略图缓存。

## DD-005 Smart Extraction 作为核心体验

状态：已采用，v0.4 已实现，v0.4.1 形式化。

采用方案：

- 根据压缩包顶层结构自动选择最终输出目录，规则由无副作用的 `SmartOutputPolicy` 统一计算（v0.4.1）。
- 空列表或单个顶层普通文件：最终输出目录等于用户指定输出目录。
- 单个顶层目录 `D`：通常等于用户指定输出目录；若输出目录名与 `D` 忽略大小写相同，则取父目录，避免出现 `name/name`。
- 多个顶层条目：通常等于 `输出目录/压缩包逻辑名`；若输出目录名与逻辑名忽略大小写相同，则直接用输出目录。
- 压缩包逻辑名去除常见归档扩展，并显式处理 `.7z.001`、`.partNN.rar` 等分卷命名；仅做名称推导，不做首卷/缺卷诊断。
- CLI 使用显式 `--smart-output` 开启，保持向后兼容；GUI 默认开启 Smart output。
- GUI 显示最终实际输出目录，并提前提示顶层输出冲突；选择压缩包后默认输出目录为压缩包父目录。
- 顶层输出冲突支持三种策略：`merge` 继续解压并按覆盖策略处理文件，`rename` 强制使用 7-Zip 自动重命名避免覆盖已有文件，`cancel` 在启动解压前停止。
- 不移动或重命名用户已有文件；`rename` 仍是文件级自动重命名，不重命名整个输出目录。

原因：

- NanaZip 的 Smart Extraction 是非常适合 DuctZip 的差异化体验。
- 用户最常见的不满之一是解压后文件散落。
- 该能力可以在不增加复杂 UI 的情况下显著提升体验。

风险：

- 用户可能不理解最终输出目录。
- 需要清楚展示“将解压到哪里”。
- `rename` 策略依赖 7-Zip 的自动重命名行为，目录本身仍可能被合并，但同名文件不会被覆盖。

复审条件：

- 如果用户反馈自动判断不符合预期，应增加明确开关和预览说明。
- 如果用户需要“重命名整个输出目录并去掉压缩包内顶层目录”的行为，需要评估是否引入后处理移动逻辑。

## DD-009 Smart 策略与编排下沉到 Core 层

状态：已采用，v0.4.1 已实现。

采用方案：

- 新增 `ductzip.core.smart_output`：`SmartOutputPolicy` 为无副作用的纯目录计算，`archive_logical_name` 负责扩展名与分卷命名推导，冲突检测与覆盖策略推导同层提供。
- 新增 `ductzip.core.extraction`：`ExtractionService` 编排 list -> 策略 -> 冲突 -> 引擎解压，产出 `ExtractionPlan`。
- CLI 与 GUI 都调用同一个 `ExtractionService` 和同一个 `SmartOutputPolicy`。
- `SevenZipCliEngine` 不再接收 `smart_output` / `conflict_strategy` 参数，只负责 7-Zip list/test/extract、进度、错误映射和路径穿越校验。
- 引擎不接收调用方提供的 listing：每次实际解压前都基于目标压缩包自行 list 并对待解压条目执行路径穿越校验，校验不可被编排层或任何预计算/伪造数据绕过；编排层可为策略规划预先 list 一次（性能取舍，不参与安全校验）。
- 设计为 v0.5 批量队列预留：队列可按任务复用同一服务与策略，本次不实现队列代码。

原因：

- v0.4 把 Smart/冲突逻辑写在引擎里，CLI 与 GUI 无法保证一致，也难以单测纯规则。
- 纯策略对象无副作用，可直接为 GUI 预览和批量预检复用。
- 引擎职责更单一，未来替换后端（DLL/libarchive）时不需要搬迁策略代码。

放弃方案：

- 在 CLI 和 GUI 各写一份 Smart 规则。
- 把策略保留在引擎内部并通过参数开关控制。

风险：

- 需要一次性调整引擎公开接口签名；已通过测试覆盖迁移。

复审条件：

- v0.5 批量队列落地时，若出现跨任务的全局冲突汇总需求，再评估 `ExtractionPlan` 的聚合形态。

## DD-006 安全策略默认开启

状态：已建议。

采用方案：

- 默认阻止路径穿越。
- 默认处理覆盖冲突。
- 默认不记录密码。
- 评估并实现 Mark-of-the-Web 传播。

原因：

- 压缩包天然存在路径穿越、覆盖敏感文件、恶意脚本释放等风险。
- 用户不应该为了安全而手动开启一堆选项。
- NanaZip 的 MOTW 传播值得参考。

放弃方案：

- 只依赖 7-Zip 默认行为。
- 只在 UI 提示风险，不在核心层阻止。

复审条件：

- 当引入右键菜单和批量解压后，必须重新审查安全默认值。

## DD-007 文档作为项目记忆

状态：已采用。

采用方案：

- 把调研、架构、路线图和设计决策写入 `docs/`。
- 后续每完成阶段更新对应文档。

原因：

- 白皮书强调长期线程需要可审查的记忆。
- 聊天记录不适合作为唯一项目上下文。
- Markdown 文档可以被打开、修改、diff 和复用。

当前文档：

- `docs/MARKET_RESEARCH.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/DESIGN_DECISIONS.md`

后续建议：

- 增加 `PROJECT_STATUS.md` 记录当前阶段。
- 增加 `CHANGELOG.md` 记录发布变化。
- 在 README 中链接核心文档。

## DD-008 发布版内置 7-Zip 后端

状态：已建议，v0.1 先实现后端发现，发布版再内置。

采用方案：

- v0.1 先查找用户指定路径、环境变量、本机安装路径和 `PATH`。
- v1.0 发布包内置官方 7-Zip Extra 中的 standalone console 后端。
- 随发布包附带 7-Zip license 和相关再分发说明。
- 高级设置允许用户切换为系统安装的 7-Zip。

原因：

- 普通用户不应为了使用 DuctZip 先手动安装 7-Zip。
- 自带后端可以让错误输出、功能能力和测试结果更可控。
- 7-Zip 官方提供 standalone console version、7z DLL 等 Extra 包，适合作为后端来源。
- 7-Zip 许可证允许使用和二进制分发，但必须随二进制再分发相关许可证信息。

后端选择优先级：

1. 用户显式配置的 `7z.exe`。
2. DuctZip 自带的 `7z.exe`。
3. 系统安装目录中的 7-Zip。
4. `PATH` 中的 `7z.exe` 或 `7zz.exe`。

放弃方案：

- 要求用户必须提前安装 7-Zip。
- 首版直接下载并安装 7-Zip。
- 把 7-Zip 源码合并进 DuctZip。

风险：

- 内置二进制需要跟进 7-Zip 安全更新。
- 发布包需要处理 x64、x86、arm64 等架构。
- 需要清晰展示第三方许可证。

复审条件：

- v0.1 验证 CLI 调用稳定后，进入打包阶段前复审内置后端方案。
- 如果官方 7-Zip 后端出现安全更新，发布流程必须包含后端版本检查。

## DD-010 子进程生命周期：reader 线程独占关闭流

状态：已采用，v0.4.1 稳定化已实现。

采用方案：

- 引擎用专用 reader 线程把子进程 stdout/stderr 逐字符读入队列，消费者按 50ms 超时轮询；EOF 时 reader 在自己线程内关闭流。
- 取消路径执行 terminate -> wait(2s) -> kill -> wait(2s) 链，`_reap_process` 兜底回收；被遗弃的生成器（`gen.close()`）同样触发回收。
- 取消上报恰好一次：引擎可同时发出 `cancelled` 事件并抛出 `ArchiveCancelled`，worker 层去重。

原因：

- Windows 上 cmd/7z 的后代进程可能继承管道写端；只要还有一个后代存活，消费方主动 `close()`/`communicate()` 就会一直阻塞（实测取消无输出后端阻塞 ~15s）。只有 reader 线程自己关闭才安全，因为它本来就阻塞在 `read()` 上，关闭与否都不影响调用方。
- 取消必须秒级响应，否则 GUI 的取消按钮形同虚设。

放弃方案：

- 消费方在 finally 里 `stream.close()`（会阻塞）。
- 取消后 `communicate()` 排空（等到 EOF 要等后代进程全部退出，同样阻塞）。
- 依赖 `__del__`/GC 回收子进程（不确定、产生孤儿进程）。

风险：

- reader 线程模型比普通 `communicate()` 复杂，需要 None 哨兵与 join 超时配合。

复审条件：

- 如果后端换成 7-Zip DLL 或库调用，整个子进程生命周期设计随之退役。

## DD-011 GUI 后台线程模型：长寿命 worker 线程 + 代际令牌

状态：已采用，v0.4.1 稳定化已实现。

采用方案：

- 预览使用窗口级长寿命 `PreviewWorker` + 单 `QThread`，通过 `request` 排队信号投递任务；`generation` 代际令牌随请求与结果往返，窗口丢弃一切迟到/过期结果。
- 解压仍为 per-task `QThread`（单次解压生命周期与窗口一致，无需长驻），worker 对象与信号接线集中在 `ductzip.gui.workers`，可无窗口单测。
- 窗口关闭：预览 `cancel + quit + wait(2s)`；解压取消 + 带 `processEvents` 泵的 `QElapsedTimer` 有界等待（10s），期间容忍 QThread C++ 包装已删除的 `RuntimeError`（视为关闭成功）；仍停不下来则 `event.ignore()` 保住窗口并告警。
- GUI 单元测试一律 stub 引擎；真实后端 GUI 行为是人工冒烟证据（杀毒软件扫描使真实后端时序不可复现）。

原因：

- per-preview 线程（`QThread(self)` + `started.connect(run)` + `finished→deleteLater`）实测间歇性把 worker 跑在主线程、线程凭空消失并触发 0xc0000374 堆损坏；线程churn不可接受。
- 取消→`thread.quit` 是排队到主线程的信号，主线程若在 `wait()` 里死等，quit 永远送不到；必须泵事件。
- 文本框每次变更都令上一压缩包的预览、最终输出、冲突摘要、打开目录状态全部作废，否则用户看到的是旧压缩包的结论。

放弃方案：

- 每预览一个压缩包新建/销毁线程。
- 主线程 `thread.wait()` 无超时死等。
- 用真实 7-Zip 跑 GUI 单元测试。

复审条件：

- v0.5 批量队列到来时，per-task 解压线程模型将被队列 runner 取代（DD-009 预留），届时复审本决策。

## DD-012 安全边界：诚实声明不支持的能力

状态：已采用，v0.4.1 稳定化已实现并文档化。

采用方案：

- 明确声明：压缩包内符号链接 / Junction / 重解析点的解压不做防护，属于当前不支持的能力；不在 UI 里假装已防护。路径校验仍覆盖绝对路径、盘符相对路径、`..` 穿越、UNC/\\?\ 前缀和 Windows 保留设备名（CON/PRN/AUX/NUL/CONIN$/CONOUT$/COM1-9/LPT1-9，含 `NUL.txt` 等带扩展形式）。
- 压缩包在规划与解压之间被替换/篡改时，以引擎每次实际解压前自行 list 的真实条目作为唯一安全依据；调用方 listing（服务规划、未来批量预检）仅供策略参考，永远不能参与安全校验。

原因：

- 7-Zip CLI 会按压缩包内链接目标写入，DuctZip 无法在 CLI 层拦截重解析点展开；与其留下虚假安全感，不如列为不支持并留待 DLL 后端或专用校验层。
- 引擎独占安全校验是 v0.4.1 已确立的红线（DD-009）；稳定化测试补上了“伪造安全 listing 与规划后换包”两个对抗场景，红线有回归测试守护。

放弃方案：

- 在 7-Zip CLI 之上叠加重解析点/链接拦截（CLI 层做不到可靠拦截）。
- 信任调用方提供的 listing 做校验（会引入伪造面）。

复审条件：

- 如果后端更换或增加解压前静态扫描层，重新评估链接/重解析点支持范围。
- 批量队列（v0.5）落地时必须复用同一红线，批量预检不得绕过引擎校验。

## DD-013 批量队列核心：确定性顺序 runner，策略不进队列

状态：已采用，v0.5 队列核心已实现。

采用方案：

- 新增 `ductzip.core.queue`：`BatchQueue` 驱动任意数量压缩包逐一通过同一个 `ExtractionService`，并发固定为 1，严格入队顺序。
- 队列只拥有：任务身份与状态机（queued/planning/running/completed/failed/cancelled）、合法迁移校验、取消路由（cancel_current / cancel_all / 外部 cancel_event）、重试、结构化批量日志（持久化状态迁移，进度只实时下发不落盘）。
- 每个任务是恰好一次服务操作；队列不接收调用方 listing、不做路径校验、不碰 Smart Output 与冲突策略——这些仍在 `ExtractionService` 内逐任务计算。队列级共享输出根 = 每个任务各自的 `requested_output_dir`，共享根只是同一个 Path 传给多个任务。
- 队列是线程无关的确定性生成器：`run()` 是纯生成器，调用方在任何线程驱动，取消经 `threading.Event` 从任意线程信号化。
- 密码脱敏内建：任务持有密码仅供执行；持久化消息、逐任务错误、后端原始 `failed` 输出在到达 UI 前一律替换为 `***`。

原因：

- 队列策略与 7-Zip 命令执行解耦（LONG_TASK Phase 2 目标）：队列测试全部用脚本化服务替身，20 项测试零真实后端、零 sleep（除取消等待事件外）。
- `completed` 终态、`failed`/`cancelled` 可重试可移除的语义与 GUI「重试 / 移除（合法时）」按钮一一对应。
- GUI 杀软时序问题（DD-011）同样适用于批量：核心必须可在 stub 下完全确定性测试。

放弃方案：

- 在队列内做 Smart Output / 冲突汇总（会把策略逻辑复制出 Core 编排层）。
- 队列自己持有 7-Zip 进程句柄或线程池（破坏引擎独占子进程生命周期，DD-010）。
- 并发 >1（当前无需求，失败隔离与取消语义都会复杂化）。

风险：

- 中途被遗弃的 `run()` 生成器会把任务留在 planning/running 非终态；调用方必须先 cancel 再排空生成器（GUI 关闭路径已按此模式实现，Phase 3 批量 worker 沿用）。

复审条件：

- 若出现跨任务全局冲突汇总需求，评估 `ExtractionPlan` 聚合形态（继承 DD-009 复审条件）。
- 若用户明确要求并发解压，重新评估并发数与后端进程配额设计。

## DD-015 Windows 集成：仅 HKCU 注册表动词，不碰原生 Shell Extension

状态：已采用，v0.6 已实现。

采用方案：

- 集成面 = 当前用户（HKCU）注册表项：`SystemFileAssociations\<ext>\shell` 下的两个 DuctZip 动词（解压到当前目录 / 解压到同名文件夹）、自有 ProgID `DuctZip.Archive`（open 指向 GUI + 同带动词）、各扩展名 `OpenWithProgids` 可见性项、`Software\DuctZip` 元数据键。
- `register` 幂等；`unregister` 精确移除自己创建的键与值，部分损坏状态下也能恢复干净；全程无 HKLM、无提权。
- 文件关联只做 Open-with 可见性，不更改默认打开程序（可逆、不劫持）。
- 稳定调用协议 `"<launcher>" -m ductzip shell <verb> "%1"`；launcher 记录绝对路径，`status` 检测失效路径，重新 `register` 修复。

原因：

- 用户决策（§10.2 #4）批准的范围就是当前用户注册；原生 Shell Extension（DLL、IExplorerCommand 稀疏包）未获批准且引入签名/部署复杂度。
- 注册表动词是 Explorer 的公开稳定扩展点，注册到调用到卸载可用 `reg query` 与脚本完全验证，符合可逆底线。

放弃方案：

- HKLM 整机器注册（需要提权，超出批准范围）。
- 修改默认文件关联（劫持用户选择，不可逆风险）。
- 现代 Win11 上下文菜单包（属于未批准的原生扩展）。

风险：

- Windows 11 上经典动词折叠在「显示更多选项」内，入口深度不如原生菜单（已在 docs/WINDOWS_INTEGRATION.md 诚实声明）。
- 便携包迁移后记录的 launcher 绝对路径会失效，需重新 register（status 可检测）。

复审条件：

- 若未来批准原生 Shell Extension，重新评估 Win11 一级菜单入口。
- 若新增格式支持，扩展 ARCHIVE_EXTENSIONS 并复审动词覆盖。

## DD-014 批量 worker 线程回收：run() 收尾直接退出本线程事件循环

状态：已采用，v0.5 GUI 批量工作流已实现。

采用方案：

- `BatchWorker.run()` 的 `finally` 在 `finished.emit()` 之后直接调用 `QThread.currentThread().quit()`，不依赖跨线程排队的 `finished -> thread.quit` 投递来结束线程。
- 同时不在 `batch_thread.finished` 上连接 `batch_thread.deleteLater()`（worker 的 deleteLater 保留；QThread 对象由窗口生命周期持有）。

原因：

- 实测发现（Windows + offscreen + `QTest.qWait` 泵事件）：队列跑完后 worker 的 Python 槽已返回、批量线程停在 C++ `exec()`（Python 栈为空），排队的 quit 事件未被处理，主线程阻塞在 `qWait` 的事件处理里，形成不死不活的死锁；`processEvents` 泵则不会触发。
- run() 收尾自己 quit 是确定性的：退出只依赖本线程，与调用方如何泵事件无关。GUI 关闭路径（`_wait_for_thread` 泵事件）与自然完成路径（测试里的 `qWait` 泵）都验证通过。

放弃方案：

- 保留排队 `finished -> quit` 并在文档中要求"GUI 测试只能用 processEvents 泵"（把 Qt 内部时序脆弱点转嫁给所有调用方）。

复审条件：

- 若未来把 `BatchWorker` 复用到非 `QThread` 宿主（如 `QThreadPool`），移除 quit 调用并改用宿主自己的完成通知。
