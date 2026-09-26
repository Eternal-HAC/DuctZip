# DuctZip Claude Code Long Task

## 0. Role and Completion Protocol

你负责本轮的完整工程执行，包括：仓库审计、独立 Code Review、缺陷修复、测试补充、发布候选复验、文档同步和本地 checkpoint commit。

Codex 不参与本轮中途 Review。Codex 只在你完成后执行最终安全验收和结果验收。因此：

- 不要把 `PROGRESS.md`、旧测试日志或旧结论当成完成证据。
- Review 必须由你基于当前源码、Git 历史、工作树差异和 fresh test 独立完成。
- Worker、subagent 或模型自述不算证据，必须检查真实 diff、源码、测试输出和产物。
- 只有全部 MUST 项通过后，才输出 `READY_FOR_CODEX_ACCEPTANCE`。
- 不要输出 `TASK_COMPLETE`。最终完成判定属于 Codex。

允许创建本地 checkpoint commit。禁止 push、修改 remote、创建 tag、创建 GitHub Release、发布 PyPI 包或上传产物。

## 1. Current Audited State

审计日期：2026-09-26。

### 1.1 Git 状态

- 仓库：`F:\01_code\tools\DuctZip`
- 分支：`main`
- 当前 `HEAD`：`6d88b09 feat: bundle 7-Zip 26.03 console backend with enforced digest pinning`
- `origin/main`：`a45e8b8 feat: add PySide6 GUI prototype`
- 本地分支相对 `origin/main`：ahead 7，behind 0。
- 这 7 个本地提交包含 v0.4.1 稳定化、v0.5 批量队列、v0.6 Windows 集成、v0.7 安全/MOTW/便携打包和 7-Zip 后端捆绑。
- `origin/main...HEAD` 约为 53 files changed / 9612 insertions / 221 deletions。
- 当前仍有 18 个 modified tracked files 和 4 个 untracked files，主要是 v1.0.0rc1 收尾、密码/取消/编码/GUI 入口修复、用户手册和发布说明。
- 不得 reset、checkout、stash、clean 或覆盖这些现有改动。

开始时必须重新运行：

```powershell
git status --short
git log -10 --oneline --decorate
git rev-list --left-right --count origin/main...HEAD
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard
```

若结果与上述记录不同，以 fresh output 为准，并在 `PROGRESS.md` 记录差异。

### 1.2 已实现能力

当前代码已经包含：

- 单包 CLI：`extract`、`list`、`test`、`doctor`。
- v0.4.1 Smart Output 和冲突/覆盖策略。
- 引擎层 fresh listing、路径穿越检查、密码错误映射、进度和取消。
- v0.5 顺序批量队列、CLI `batch-extract`、GUI 批量队列、重试、取消、任务状态和日志。
- v0.6 HKCU Windows Explorer 右键菜单、文件关联可见性、注册/卸载/status。
- v0.7 设置、安全测试、MOTW 传播、便携包构建和捆绑 7-Zip 26.03。
- 当前版本号为 `1.0.0rc1`。

这些只是代码存在的事实，不代表发布质量已经通过。

### 1.3 2026-09-26 fresh verification

已经观察到：

1. `python -m pip check`：PASS。
2. `git diff --check`：PASS，仅有 Git 的 LF/CRLF 提示。
3. `python scripts/build_portable.py --output <temp>`：PASS。
   - 产物：`DuctZip-1.0.0rc1-portable.zip`
   - 大小：1,183,597 bytes
   - SHA-256：`90f61d4d8da8e6100e813f674df3c8387fa4acdae935cc75ce2ca89d1f4853fc`
4. 完整测试第一次运行异常退出：进程在 GUI lifecycle 区域附近以 exit 1 终止，没有 unittest failure summary。
5. `tests.test_gui_lifecycle` 单独运行：9 tests PASS。
6. 完整测试第二次运行：247 tests PASS，约 50.5 秒。
7. wheel fresh build 未通过：
   - `--no-build-isolation` 环境无法 import `setuptools.build_meta`。
   - 使用已记录镜像执行隔离构建时，镜像未返回 `setuptools>=68`。
   - 这可能是环境/依赖源问题，但当前不能宣称 wheel 构建 fresh PASS。

上面的首次异常退出必须作为疑似 flaky/crash 处理，不能因为第二次通过就关闭。

## 2. Primary Goal

对 `origin/main` 之后的全部本地实现和当前未提交 v1.0.0rc1 收尾改动做一次独立、发布级 Review；修复确认的问题；建立可重复的测试与构建证据；生成一个可以交给 Codex 做最终安全/结果验收的候选工作树。

本轮不新增产品范围。优先验证已有 PRD、ROADMAP、设计决策和发布说明已经承诺的能力。

## 3. Source of Truth

冲突时按以下顺序判断：

1. 当前工作树的 fresh observable behavior 和测试证据。
2. 当前源码与构建脚本。
3. `docs/PRD.md`。
4. `docs/ROADMAP.md`。
5. `docs/ARCHITECTURE.md`、`docs/DESIGN_DECISIONS.md`、`docs/SECURITY.md`。
6. `README.md`、`PROJECT_STATUS.md`、`CHANGELOG.md`。
7. `PROGRESS.md`、release notes、resume facts，只作为待核验记录。

特别注意：旧 `LONG_TASK.md` 是前一轮实现合同。它可用于理解目标，但其 2026-09-18 基线已经过时。本文件是当前 Review/收尾任务的执行合同。

## 4. Review Scope

Review 必须覆盖 `origin/main...HEAD` 的 7 个提交和当前所有 unstaged/untracked changes。按子系统审查，输出 findings 时按 P0/P1/P2/P3 排序，并给出文件与行号。

### 4.1 Archive engine and security

检查：

- 7-Zip discovery precedence、bundled backend pin、explicit override、settings fallback。
- list/test/extract 的 subprocess 生命周期、stdin、stdout/stderr draining、timeout、cancel、generator abandon、process reaping。
- Ctrl+C / Ctrl+Break 和退出码。
- password required / wrong password / password leakage。
- 路径穿越、绝对路径、UNC/device path、Windows reserved names、分隔符和大小写。
- symlink/Junction/reparse point 的真实行为是否与文档一致。
- planning listing 与 engine fresh listing 的 TOCTOU 边界。
- MOTW 传播是否会越界、跟随链接、覆盖不应触碰的文件，失败语义是否诚实。
- 大 listing、恶意输出、资源消耗和错误信息泄漏。

安全检查不得为了兼容性而下移或绕过。`SevenZipCliEngine` 必须继续在真实解压前自行列举和校验。

### 4.2 Core and batch queue

检查：

- 状态机合法性、terminal state、retry、remove、cancel current、cancel all。
- 顺序保证和 one-task failure isolation。
- password/error/log redaction。
- Smart Output、conflict 和 overwrite 语义是否在单包/批量一致。
- queue 是否保持 `CLI/GUI -> core -> archive` 边界。
- 异常、取消、重复执行和 generator 提前关闭时是否留下错误状态。

### 4.3 CLI and Windows integration

检查：

- 所有命令的 exit code、stderr/stdout、UTF-8 重定向行为。
- 命令行密码暴露提示与实际行为。
- shell register/unregister/status 的 HKCU 范围、幂等性、精确清理、引号、Unicode、空格、多选和 stale launcher。
- 不得写 HKLM，不得改默认程序，不得删除非 DuctZip registry keys。
- 实际 registry 测试必须先记录快照，结束后证明无残留。

### 4.4 GUI and concurrency

检查：

- preview/extract/batch worker 的线程归属、信号、异常、取消和销毁。
- closeEvent 的 bounded shutdown 和 process/thread cleanup。
- stale preview token、切换 archive/password 后的状态清理。
- duplicate terminal notification、modal dialog、deleted QObject/QThread wrapper。
- 单包和批量操作期间 UI responsiveness。
- 无 PySide6 时的入口行为。
- 连续运行完整 suite 时是否出现偶发退出、Qt crash、deadlock 或资源残留。

首次 full-suite 异常退出属于 MUST 调查项。至少检查 Windows Event Log/Python faulthandler 可用证据、测试顺序依赖、QApplication/QThread 生命周期和未回收后台对象。

### 4.5 Packaging, provenance, license and docs

检查：

- wheel、portable zip、launchers、bundled backend、license/notices。
- 产物不得包含测试、缓存、私有 archive、本机绝对路径或敏感信息。
- `scripts/build_portable.py` 当前 manifest 只记录 `git_commit=6d88b09`，但会打包未提交源码。这会让产物来源标识不完整。必须修复为以下两种方案之一：
  - release build 在 dirty tree 明确失败；或
  - manifest 记录 dirty 状态和足以审计的 source diff identity。
- portable zip 当前不包含 `docs/USER_MANUAL.md`，但 release notes 指向该文件。要么把离线用户需要的手册/发布说明纳入包，要么修正文档和使用路径，不能保留断链。
- release notes 中不得保留 `F:\...`、`C:\tmp\...` 等开发机绝对路径。
- wheel hash、portable hash、文件大小和测试计数必须在最终源码确定后重新生成，不能沿用旧数值。
- “repeatable/reproducible” 的措辞必须与实际确定性一致。若产物受时间戳、文件 mtime 或环境影响，只能声称流程可重复，不能声称 bit-for-bit reproducible。
- 核对 7-Zip 来源、版本、三份文件 digest、`THIRD_PARTY_NOTICES.md` 和 build pins 完全一致。不要下载或替换后端，除非发现已记录内容不一致并先报告阻塞。

### 4.6 Test and build reproducibility

检查：

- test discovery、顺序依赖、skip 条件、真实 backend/RAR fixture 依赖。
- 测试是否修改真实 HKCU、用户设置或项目外状态，以及清理是否可靠。
- wheel 的 PEP 517 隔离构建是否可以由项目文档复现。
- 当前项目没有 lint/typecheck 配置。不要临时引入大范围格式化或工具链迁移；可以提出建议，但除非发现能阻止 RC 的具体问题，否则保持 UNKNOWN/known limitation。

## 5. Execution Phases

### Phase 0: Preserve and reproduce

**MUST**

1. 读取 `LONG_TASK.md`、`PROGRESS.md`、README、PRD、ROADMAP、ARCHITECTURE、DESIGN_DECISIONS、SECURITY、RELEASE_CHECKLIST、release notes、user manual。
2. 记录 fresh Git 状态和环境。
3. 不改代码，先复现：完整测试、GUI lifecycle、pip check、wheel、portable build、CLI/GUI smoke。
4. 将本文件 1.3 的首次异常退出视为现有证据，不得删改或忽略。

Gate：得到可复现基线，失败项有原始命令、退出码和最小复现。

### Phase 1: Independent review report

**MUST**

在修复前创建 `docs/FINAL_REVIEW.md`，至少包含：

- review commit range 和 dirty worktree scope；
- P0/P1/P2/P3 findings；
- 每项 evidence、影响、复现/测试、建议修复；
- 文档与代码冲突；
- 未能验证的 UNKNOWN；
- 已审查但未发现问题的关键区域。

不要用“247 tests passed”代替代码 Review。

Gate：所有高风险子系统均被覆盖，findings 有具体文件/行号和证据。

### Phase 2: Fix confirmed defects

**MUST**

- 修复全部 P0/P1。
- 修复会导致错误发布声明、数据越界、进程/线程残留、不可恢复 registry 修改、密码泄漏、产物不可追溯或 acceptance 不可复现的 P2。
- 每个修复先加或同步加入会在旧实现失败的回归测试。
- 其余 P2/P3 若延期，必须写入 `docs/FINAL_REVIEW.md` 和公开文档的 known limitations，并说明为什么不阻塞 RC。
- 保持当前产品范围，不做无关重构。

Gate：对应 targeted tests 通过，diff 与 finding 一一对应。

### Phase 3: Flake and lifecycle hardening

**MUST**

- 找到首次 full-suite 异常退出的原因，或通过充分证据把范围缩小到明确环境因素。
- 对相关 GUI/lifecycle tests 做顺序与重复运行。
- 建议最低证据：相关 test module 连续 20 次通过，完整 suite 连续 3 次通过；若时间/环境不允许，说明替代证据，不能直接标为 PASS。
- 每次运行后检查残留 Python、7-Zip 进程、QThread warning、HKCU 测试键和临时文件。

Gate：无 crash、hang、orphan process、registry residue 或未解释异常退出。

### Phase 4: Build and artifact closure

**MUST**

- 修复 manifest dirty provenance 问题。
- 修复 portable 用户文档断链。
- 在最终源码状态上重新构建 portable artifact，并验证 checksum、manifest、内容和 isolated extraction smoke。
- 在隔离环境完成 wheel build/install/entrypoint/real extraction smoke。
- 如果外部 package index 不可用，保留完整 blocker 证据；不要引用旧 wheel hash 冒充 fresh build。可使用已有可信本地缓存或临时 venv，但不得全局修改 Python/provider 配置。
- 同步版本、文件大小、hash、测试数量、release notes、checklist、README、PROJECT_STATUS、CHANGELOG、ROADMAP 和 resume facts。

Gate：所有 public artifact claims 都能从当前源码 fresh 复现，无机器路径和过时 hash。

### Phase 5: Self-review and handoff

**MUST**

1. Review 最终 diff，而非只看测试。
2. 运行最终验收矩阵。
3. 更新 `PROGRESS.md` 和 `docs/FINAL_REVIEW.md`。
4. 可以创建本地 checkpoint commit；不得 push/tag/release。
5. 输出给 Codex 的验收摘要。

Gate：满足第 8 节全部条件后输出 `READY_FOR_CODEX_ACCEPTANCE`。

## 6. Required Verification Matrix

至少执行并记录：

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests -v
python -m pip check
git diff --check
```

还必须执行：

- GUI lifecycle/batch/entrypoint targeted repetition。
- CLI real-backend matrix：doctor/list/test/extract/batch、中文+空格路径、密码、冲突、覆盖、取消、坏包、穿越。
- Windows HKCU register/status/invoke/unregister round trip，完成后逐键证明无残留。
- portable build、解压后 isolated smoke、bundled backend discovery、GUI launcher、settings portability。
- PEP 517 wheel build、clean venv install、`ductzip`/`ductzip-gui` entrypoint、真实解压。
- bundled 7-Zip 文件 digest 与 pins/notices 比对。
- artifact content audit、secret/path/cache/private fixture scan。
- final `git status --short`、unstaged diff、staged diff、untracked files。

每条必须记录 command、exit code、pass/fail/skip count、产物路径/size/hash，以及环境限制。只记录摘要时，要保留可定位的原始日志路径；公开文档不得写开发机绝对路径。

## 7. Autonomous Decisions

你可以自主决定：

- 小范围内部实现、测试夹具、helper 名称和模块拆分。
- 为确认 finding 所需的最小 instrumentation 或回归测试。
- 在不改变产品语义的前提下修复确定缺陷。
- 是否将一个本地 checkpoint 拆成多个 reviewable commits。
- 如何解决 manifest dirty provenance，只要最终声明真实、可审计。

以下情况必须停止相关分支并报告，不能自行决定：

- 改变 Smart Output、conflict、overwrite、batch、MOTW 或 shell registration 的用户语义。
- 扩大支持格式或新增压缩功能。
- 改成 HKLM、需要管理员权限或原生 shell extension。
- 替换/升级/重新下载 bundled 7-Zip。
- 新增网络、遥测、自动更新或云功能。
- 删除已有公开能力或降低安全检查。
- 需要发布、push、tag、remote 修改或凭据操作。

## 8. Final Gate

只有满足全部条件，才可输出 `READY_FOR_CODEX_ACCEPTANCE`：

- `docs/FINAL_REVIEW.md` 完整，所有 P0/P1 已关闭。
- 阻塞 RC 的 P2 已关闭，其余 findings 有明确延期理由和公开限制。
- 首次 full-suite 异常退出已解释并有 flake/lifecycle 证据。
- 完整 suite 达到约定的重复通过门槛，无未解释 skip。
- wheel 与 portable artifact 都基于最终源码 fresh 构建并通过 isolated smoke。
- manifest 不会把 dirty 内容伪装成纯 `HEAD` 产物。
- portable 包中的文档引用可离线使用，不存在 `docs/USER_MANUAL.md` 断链。
- public docs/产物中没有开发机绝对路径、旧 hash、旧文件大小、旧测试计数或虚假签名/安全声明。
- HKCU 测试无残留，无 orphan 7-Zip/Python/Qt worker。
- 所有源代码、文档和版本信息一致。
- `git diff --check` 通过。
- 最终 status/diff/untracked 已审查并记录。
- 没有 push、remote/tag/release/provider/auth/project-external 修改。

最终回复必须包含：

1. Review findings 和关闭状态。
2. 本轮修改文件与本地 commit hashes。
3. 全部验证命令与结果摘要。
4. 产物名称、大小、SHA-256 和 provenance 说明。
5. 剩余风险、UNKNOWN、人工复验项。
6. 给 Codex 的安全验收重点。
7. 最后一行单独输出：

```text
READY_FOR_CODEX_ACCEPTANCE
```

若任一 MUST 未完成，禁止输出该标记。应给出当前阶段、已验证证据、剩余项和精确 blocker。

## 9. Forbidden Actions

- 禁止 push、force-push、修改 remote、tag、GitHub Release、PyPI 发布。
- 禁止修改 provider/model/auth/API Key/Token/CCSwitch 或用户全局配置。
- 禁止改项目外文件，临时测试/构建目录除外。
- 禁止 `git reset --hard`、`git clean -fd`、覆盖用户改动或删除 UNKNOWN 文件。
- 禁止把测试日志中的密码、私有 archive 或本机路径写入公开产物。
- 禁止为了通过测试降低路径安全、registry 范围或密码保护。
- 禁止把旧日志、单次偶然通过或模型自述作为最终完成证据。
