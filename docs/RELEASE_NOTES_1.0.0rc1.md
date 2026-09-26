# DuctZip 1.0.0rc1 发布说明

**版本：** `1.0.0rc1`（release candidate，**未签名**）
**日期：** 2026-09-19（2026-09-26 RC 关闭复核，见 §0）
**状态：** 发布候选。本仓库**未推送、未打 Tag、未创建 GitHub Release**；推送与发布动作按长期任务约束留待用户手动执行。

---

## 0. 2026-09-26 RC 关闭复核（本轮变更）

发布前独立 Review（报告：`docs/FINAL_REVIEW.md`）发现并修复了以下问题，全部带回归测试
（新实现通过、旧实现确定性失败）：

1. **GUI 关闭时偶发原生崩溃**（P1）：`QThread.finished` 在 OS 线程完全退出前发出，旧回收路径
   随即掉落 worker 的最后一个 Python 引用，使 C++ 对象在所属线程退出窗口内被销毁
   （实测签名：access violation / 堆破坏 / 硬 abort，复现率约 1/10–1/20）。修复：回收前
   `QThread.wait()` 确认 OS 线程结束，并移除 `finished → deleteLater` 自删除链。
   修复后 GUI 相关模块连续 20 次通过、完整套件连续 3 次通过。这也是 2026-09-26 fresh audit
   首次记录的「完整套件异常退出（exit 1、无摘要）」的根因。
2. **MOTW 误标已存在文件**（P2）：merge 场景下解压前已存在的本地文件会被打上来源区域标记。
   修复：解压前快照、传播时排除，只标记本次解压产生的文件（与 `docs/SECURITY.md` 语义一致）。
3. **便携包 manifest 来源标识不完整**（P2）：manifest 只记录 `git_commit`，dirty tree 被打包时
   会伪装成纯 HEAD 产物。修复：manifest 增加 `git_dirty` 与 `worktree_diff_sha256`。
4. **便携包不含用户手册**（P2）：发布说明指向的 `docs/USER_MANUAL.md` 不在包内（断链）。
   修复：包内根目录现在包含 `USER_MANUAL.md` 与本版本 `RELEASE_NOTES.md`。
5. **发布说明含开发机绝对路径**（P2）：已改写为「仓库根目录」。
6. **wheel 构建非逐位可复现**（P2，记录在案）：zip 条目时间戳使逐次构建哈希不同；措辞已从
   「可复现」更正为「流程可重复」，最终哈希以 §2 本次重建为准。

§5 新增已知限制第 9 条（`BatchQueue.run(external_cancel=...)` 的外部取消仅在任务运行期生效，
无现存调用方受影响，记录不改语义）。测试规模 247 → **253 项**（新增 6 项回归测试）。
**§2 交付物为 2026-09-26 最终源码重建**；便携包隔离冒烟 11/11、wheel 干净 venv 冒烟 8/8
（中文+空格路径真实解压、设置便携性、HKCU 注册往返零残留）。

---

## 1. 这个版本是什么

DuctZip 是一个 Windows 压缩包解压工具：CLI + 图形界面共用同一套解压内核，提供「聪明输出目录」
（避免 `照片/照片/` 这类重复嵌套）与可预期的冲突/覆盖语义，并捆绑官方 7-Zip 控制台后端，
因此**目标机器无需预装 7-Zip**。

主要能力：

- **CLI**：`extract`、`batch-extract`、`list`、`test`、`doctor`、`settings`、`shell`。
- **GUI**（可选，需 PySide6）：压缩包预览、最终输出目录预览、冲突摘要、批量队列、
  进度与取消、打开输出目录、设置对话框。
- **Windows 右键菜单**（HKCU，无需提权、可完全逆转）：对 `.zip .7z .rar .tar .gz .bz2 .xz .zst`
  提供「用 DuctZip 解压到当前目录」「用 DuctZip 解压到同名文件夹」，以及「打开方式」可见性
  （不篡改任何扩展名的默认打开程序）。
- **每用户设置**：`sevenzip_path` / `overwrite_policy` / `conflict_strategy` / `smart_output`。
- **MOTW 传播**：解压成功后，把压缩包的 `Zone.Identifier` ADS 复制到每个解压出的文件，
  让 Windows 继续把内容视为来自压缩包来源区域。尽力而为，非 NTFS / 无 MOTW 时安静跳过。
- **纯本地**：无网络、无遥测、无自动更新、无云端。

面向使用者的完整说明见 `docs/USER_MANUAL.md`。

## 2. 交付物

| 交付物 | 位置 | 校验 |
| --- | --- | --- |
| 便携包（推荐给最终用户） | `dist/DuctZip-1.0.0rc1-portable.zip`（1,200,605 字节） | SHA-256 `886f3bc74aca2e54d324b58519eaaa065695fda742630973987b56a349dca135`，同目录 `.sha256` 文件记录 |
| 构建清单 | `dist/build-manifest.json` | 记录 Python/平台/提交/`git_dirty`/`worktree_diff_sha256` 与逐文件摘要 |
| Python wheel | `ductzip-1.0.0rc1-py3-none-any.whl`（54,393 字节） | SHA-256 `ced8c72c17a41874327b0c168424275d042728bd3fc730b58ba37e52b680f401`；由 `python -m pip wheel . --no-deps` 生成（2026-09-26 最终源码重建） |
| 源码 | 本仓库 | 版本号见 `pyproject.toml` |

便携包解压后是**单一顶层目录** `DuctZip-1.0.0rc1\`，内含 CLI、GUI 启动器、捆绑的 7-Zip 后端、
`README.md` / `LICENSE` / `CHANGELOG.md` / `THIRD_PARTY_NOTICES.md` / `PORTABLE.txt` /
`USER_MANUAL.md` / `RELEASE_NOTES.md` 与源码。

**本包不在 PyPI 上**，请勿尝试 `pip install ductzip`。

## 3. 环境要求

- Windows 10 / 11（x64）。
- Python 3.11 或更高版本在 `PATH` 上（便携包的 `.cmd` 启动器调用 `python`）。
- **不需要**预装 7-Zip：便携包内含官方 7-Zip 26.03 控制台后端。
- 仅 GUI 需要 PySide6（`python -m pip install PySide6`）；缺失时 `ductzip-gui` 会给出可操作的提示并以 1 退出，CLI 不受影响。

## 4. 安装 / 升级 / 卸载

- **便携安装**：解压 zip，进入 `DuctZip-1.0.0rc1\`，运行 `ductzip.cmd doctor` 自检。
  设置文件保存在包内 `settings\settings.json`（便携语义）。
- **源码 / wheel 安装**：见 `docs/USER_MANUAL.md` §3。
- **升级**：便携包直接替换整个目录（设置随目录一起替换）；wheel 安装用
  `pip install --force-reinstall <新 wheel>`。
- **卸载**：便携包 = 先 `ductzip.cmd shell unregister`，再删除整个目录；
  wheel 安装再加 `pip uninstall ductzip` 并删除 `%APPDATA%\DuctZip\`。

## 5. 已知限制与发布决定

以下限制是**有意记录**的，不是遗漏。逐条对应长期任务的发布决定编号或验收条目。

1. **本 RC 未签名**（决定 #6）。没有代码签名证书，发布包与捆绑的后端都不带发布者签名。
   本说明不主张任何不存在的签名证据。
2. **捆绑后端的供应链限制**（决定 #3，替代验证链）。上游 7-Zip **不**为其 Windows 二进制做
   Authenticode 签名（安装包与已安装的 24.08 构建，PE 证书表均为空）。因此捆绑副本的验证依赖：
   TLS 传输 → 上游 `ip7z/7zip` 26.03 发布元数据中的 `sha256:0859c524…e6edd` → 本地实测摘要一致
   → 载荷自述版本为 26.03。`scripts/build_portable.py` 会**强制校验**固定摘要，摘要不符即拒绝打包。
   需要已签名后端的用户可用 `--sevenzip` / `DUCTZIP_7Z_PATH` 指向自己的副本。
3. **未在第二台物理机器上复验**（决定 #8）。所有验收证据均来自本机（Windows 11 Home China，
   10.0.26200）。因此本说明的结论限定在实际取得的证据范围内，不主张跨机器一致性。
4. **取消只回收 DuctZip 启动的那个后端进程**，不回收任意后代进程。捆绑的 `7z.exe` 不派生子进程，
   因此随包形态下取消后不留残余（实测回收耗时：单任务 63–84 ms，批量取消全部 0.02 s，
   关闭窗口 41 ms，真实 Ctrl+Break 0.77 s）。但若用户把 `--sevenzip` 指向 `.cmd` 包装脚本，
   该脚本自己派生的真正 7-Zip 会在取消后继续运行。彻底解决需要 Job Object
   （`KILL_ON_JOB_CLOSE`），会改动 §7.4/§7.5 已验证的取消/回收路径，且无验收条目要求，故记录不实现。
5. **不支持符号链接 / 目录联接 / 重解析点**：预解压路径校验会拒绝此类条目，而非静默跟随（见 `docs/SECURITY.md`）。
6. **TOCTOU（检查与使用之间的时间窗）**：解压前校验与 7-Zip 实际写入之间，压缩包仍可能被替换。
   引擎在每次真实解压前自行重新列举并校验，因此伪造的调用方列举无法绕过校验，但这个时间窗本身不被消除。
7. **列举结果没有大小上限**：`list` / `test` 会把后端输出整体读入内存，超大压缩包（数十万条目）
   会占用相应内存。
8. **静态质量工具未配置**（§7.8）：仓库没有配置格式化器、linter 或类型检查器，因此
   **不主张**任何 lint / typecheck 通过结论。
9. **`BatchQueue.run(external_cancel=...)` 的外部取消仅在任务运行期生效**：planning 阶段
   （引擎列举）期间生成器尚未产出进度事件，外部取消事件不会被转译进当前任务。CLI/GUI 实际都走
   `cancel_current` / `cancel_all` 内部路径（直接 set 当前任务的取消事件），无现存调用方受影响，
   故记录不改语义（Review 发现 P3-1）。

## 6. §7 验收证据摘要

全部命令在仓库根目录下执行，主体时间为 2026-09-19；交付物与 Windows 集成相关各行
（§7.2 的干净虚拟环境、§7.6、便携冒烟）在 2026-09-20 最后一次重建后**重新执行并复现**。逐条原始输出记入 `PROGRESS.md`。

| 条目 | 内容 | 结果 |
| --- | --- | --- |
| §7.1 | 回归套件 `python -m unittest discover -s tests` | **253 项通过**（2026-09-26 修复后连续 3 次全量运行均 `OK`，0 跳过，退出码 0）；2026-09-19 基线为 247 项；不依赖网络 |
| §7.2 | `python -m pip check` | 退出码 0（`No broken requirements found.`） |
| §7.2 | `python -m pip wheel . --no-deps` | 退出码 0，产物 `ductzip-1.0.0rc1-py3-none-any.whl`，名称/版本与 `pyproject.toml` 一致；wheel 内仅含 `ductzip/` 包与 dist-info（25 项），无测试、缓存或开发产物 |
| §7.2 | 干净虚拟环境安装后的入口点 | `ductzip.exe` / `ductzip-gui.exe` 均生成；`doctor` 退出码 0、`--help` 退出码 0、无 PySide6 时 `ductzip-gui` 给出可读提示并退出 1；从已安装 wheel 对中文+空格路径完成真实解压，内容正确 |
| §7.3 | CLI 验收集（41 行，真实后端） | **41/41 通过**，0 失败；覆盖退出码矩阵、中文/空格路径、Smart Output 单/多顶层、三种冲突策略、三种覆盖策略、密码矩阵、缺后端、穿越防护、批量（混合/重试/顺序/逐任务目录）、真实 Ctrl+Break → 130 |
| §7.4 | GUI 验收集（26 行，offscreen + 真实后端 UI 自动化） | **26/26 通过**；窗口状态、预览与失效、真实解压、大包响应性与进度、取消与关闭的回收时限、密码可见性与不泄漏、冲突、批量队列非法迁移、打开输出目录、混合批量隔离 |
| §7.5 | 安全验收 | 见 §7 映射（下） |
| §7.6 | Windows 集成往返（便携包，真实 HKCU） | **8/8 通过**：未注册 → 注册（ProgID + 每扩展名两动词 + OpenWith，25 键）→ 重复注册幂等（仅 `RegisteredAt` 元数据刷新）→ `unregister` 与注册前快照**逐键相同**、无残留 |
| §7.7 | `git diff --check` / 文件审计 | 退出码 0，无空白错误（仅 `core.autocrlf` 的 CRLF 提示）；18 个修改文件 + 4 个新增文件，全部有意为之并逐条列入 `PROGRESS.md`；无密钥/令牌/私有夹具/本机绝对路径/构建缓存 |
| §7.8 | 静态质量工具 | **UNKNOWN**（未配置任何工具，不主张通过） |

### §7.5 安全验收映射

| 验收要求 | 证据 |
| --- | --- |
| 引擎层预解压列举与穿越校验不在调用方提供列举时失效 | `tests/test_engine_lifecycle.py::ArchiveMutationBoundaryTests`（伪造的 plan listing 不能改变真实解压内容）；每次真实解压前引擎自行重新列举 |
| 覆盖相对穿越、绝对/UNC/设备路径、混合分隔符、大小写、伪造成陈旧计划数据 | `tests/test_security.py::PathValidationMatrixTests`（40+ 用例矩阵）、`TraversalIntegrationTests`（反斜杠穿越压缩包，真实后端端到端阻断）、`tests/test_engine_lifecycle.py::WindowsSpecialPathValidationTests`（保留设备名含扩展名/大小写/尾点）、`ArchiveMutationBoundaryTests` |
| 链接/联接/重解析点与压缩包替换竞态被测试或明确记录为不支持并给出发布决定 | 解压时不跟随重解析点（MOTW 传播跳过重解析点，`tests/test_motw.py`）；链接/联接与 TOCTOU 记录为不支持/不消除（本说明 §5.5、§5.6，`docs/SECURITY.md`） |
| 受支持场景下解压绝不写到批准的输出边界之外 | `tests/test_security.py` 穿越用例断言输出目录未被创建；§7.3 穿越行同样断言边界外无写入 |
| 日志不泄漏密码、不向普通用户倾倒原始后端输出 | `tests/test_password_handling.py`（9 项，含 `test_raw_backend_output_never_reaches_the_user_message`）、`tests/test_security.py::PasswordNonLeakageTests`；§7.4 行 E1/E3 实测日志中不含密码 |
| 未经用户批准不引入下载/更新/遥测/网络行为 | 产品无任何网络调用；`docs/SECURITY.md` 记录该承诺；§7.7 审计未见相关代码 |

### §7.6 Windows 集成映射

- 单元层：`tests/test_shell_integration.py`（16 项）——仅写入受限键、幂等、`unregister` 完全移除且
  在未注册时安全、部分损坏后可恢复、陈旧启动器与缺失动词的 `status` 报告、动词命令的引号与
  占位符协议、便携 `.cmd` 启动器形态、`OpenWith` 行为，以及真实 HKCU 往返
  `WinRegistryRoundTripTests::test_register_status_unregister_real_hkcu`。
- 端到端层：本说明 §6 的 §7.6 一行（便携包 + 真实 HKCU，8/8）。

## 7. 本 RC 中修复的问题

相对 v0.7 检查点（`6d88b09`），发布候选收尾期间发现并修复了 5 个真实缺陷，每个都有回归测试，
且都做了「回退修复 → 测试失败」的变异检查：

1. **后端可能抢走控制台索要密码。** 不带任何密码参数时 7-Zip 会打印
   `Enter password (will not be echoed):` 并读 stdin：交互运行时表现为卡住，非交互运行时后端以
   `Break signaled` 退出并被误报为「压缩包可能已损坏或格式不受支持」。现在每次后端调用都带上密码开关
   （空 `-p` 表示「空密码，不要询问」）并以 `stdin=DEVNULL` 运行。
2. **「需要密码」与「密码错误」不可区分**（且前者不可达）。现在无密码时报
   `该压缩包需要密码。`，给了错密码时报 `密码错误。`。
3. **Ctrl+Break 直接杀死进程而非取消。** 现在 CLI 在命令执行期间安装 `SIGBREAK` 处理器并恢复原处理器，
   报告为「已取消：正在停止...」并退出 130；单压缩包 `extract` 此前完全没有取消处理。
4. **大压缩包列举可能永久挂起**（GUI 预览、批量规划及任何带取消事件的调用路径）。
   轮询子进程退出后才读管道的实现会在输出超过管道缓冲区时死锁：后端阻塞在 `write()` 永不退出，
   DuctZip 则一直等它退出。现在通过 `communicate(timeout=…)` 与等待并发地读取两个管道。
   该问题由 §7.4 GUI 验收针对 300 MB / 1200 条目压缩包时发现。
5. **命令行输出依赖本机控制台代码页。** Python 对**重定向**的流使用 ANSI 代码页
   （中文系统 cp936、英文系统 cp1252），因此在英文 Windows 上 `ductzip list` 会因未捕获的
   `UnicodeEncodeError` 直接崩溃，中文诊断信息写进重定向文件也会变成乱码。现在 CLI 在分发命令前
   把 stdout/stderr 固定为 UTF-8 并使用替换型错误处理；接在真实控制台上时行为不变
   （Python 本就通过宽字符控制台 API 输出）。该问题由 §7.3 CLI 验收发现。

## 8. 反馈与问题定位

排错请先运行：

```text
ductzip.cmd doctor          # 便携包
python -m ductzip doctor    # 源码 / wheel 安装
```

`docs/USER_MANUAL.md` 的排错表按**实际用户可见消息**逐条列出了原因与处理方式。
