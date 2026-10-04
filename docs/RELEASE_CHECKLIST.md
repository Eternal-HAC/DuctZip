# DuctZip Release Checklist

> 2026-10-04 update: full-suite hang fix completed; suite count is now 256 tests (CODEX_ACCEPTED). Portable and wheel artifacts were rebuilt from a clean commit and passed isolated smoke checks.

一步一步的发布前检查清单。当前状态：**v1.0.0rc1 发布候选，本清单已在 2026-09-19 完整执行，并在 2026-09-26 RC 关闭复核中重新执行并更新**（见 §8）。
每一步的实际结果见 `PROGRESS.md` 的 Phase 7 各节与 2026-09-26 节；本节括号内是结论摘要。

## 1. 代码与测试门

- [x] `git status --short` —— 只有本清单预期的文件；无 UNKNOWN 文件被改动或删除。
      （18 个修改 + 4 个新增，逐条列入 `PROGRESS.md` §7.7 的表格。）
- [x] `python -m unittest discover -s tests`（`PYTHONPATH=src`、`PYTHONDONTWRITEBYTECODE=1`、`QT_QPA_PLATFORM=offscreen`）—— 全部通过；每个 skip 都在 `PROGRESS.md` 记录前提与影响。
      （2026-10-04 修复后 **256 项通过，`OK`，0 跳过，连续 3 次全量运行退出码均为 0**，每次运行后无孤儿 `7z.exe`；09-19 基线为 247 项，09-26 中间状态为 253 项。）
- [x] `python -m pip check` —— 无 broken requirements。
- [x] `python -m pip wheel . --no-deps` —— 成功，wheel 版本与 `pyproject.toml` 一致。
      （`ductzip-1.0.0rc1-py3-none-any.whl`；2026-09-26 最终源码重建后 54,393 字节 / SHA-256 `ced8c72c…f401`。注意 wheel 构建非逐位可复现——zip 条目时间戳使逐次构建哈希不同，本记录为最终源码的单次构建实测值。）
- [x] `git diff --check` —— 无空白错误。
      （退出码 0；仅有 `core.autocrlf=true` 且无 `.gitattributes` 造成的 CRLF 提示，未被全仓转换掩盖。）

## 2. 版本与文档一致性

- [x] `pyproject.toml` / `src/ductzip/__init__.py` / README / PROJECT_STATUS / ROADMAP / CHANGELOG 的版本号、测试数、功能清单相互一致。
      （全部为 `1.0.0rc1` / 256 项，2026-10-04 更新；09-26 中间状态为 253 项。）
- [x] CHANGELOG 的 [Unreleased] 已整理为目标版本段落，未重写历史条目。
- [x] README「Not Yet Implemented」与真实行为一致（不宣称未实现的能力）。
- [x] `docs/SECURITY.md` 的 MOTW/密码/网络承诺与代码行为一致。

## 3. 构建产物

- [x] `python scripts/build_portable.py` 从零构建成功（可先删除 `dist/`）。
- [x] 记录 `dist/build-manifest.json` 的 git 提交号、Python 版本、`bundled_7zip` 标志与 `bundled_7zip_backend`（版本/上游来源/安装包 SHA-256）；该文件不得出现构建机绝对路径。
      （2026-09-26：`git_commit=6d88b09`、`git_dirty=true`、`worktree_diff_sha256` 已记录（对 `git diff HEAD` 的 SHA-256，可审计）、`python=3.13.7`、`bundled_7zip=true`、后端 26.03 与上游安装包 SHA-256；绝对路径扫描为空。
      2026-09-19 的遗留问题——提交号把 dirty tree 伪装成纯 HEAD 产物——已由 manifest 诚实记录修复；当前发布构建要求 `git_dirty=false` 且 `git_commit` 与最终发布提交一致。）
- [x] 记录产物 SHA-256（`.sha256` 文件内容）。
      （2026-09-26 最终源码重建后 `886f3bc74aca2e54d324b58519eaaa065695fda742630973987b56a349dca135`，与 `.sha256` 文件和重新测量一致；1,200,605 字节。）
- [x] 解包检查：无 `tests/`、`__pycache__`、本地路径、私有样例；`LICENSE`/`THIRD_PARTY_NOTICES.md`/`README.md` 与 `vendor/7zip/` 在位。
- [x] 捆绑校验门生效：`vendor/7zip/` 三个文件与 `scripts/build_portable.py` 中的 pin 一致（构建会自行拒绝不一致的情况）；`THIRD_PARTY_NOTICES.md` 的版本/来源/校验和与之一致。
- [x] 供应链限制已在 `THIRD_PARTY_NOTICES.md`、`docs/SECURITY.md`、`PORTABLE.txt` 与发布说明中明示：上游 7-Zip Windows 二进制不含 Authenticode 签名，验证依赖 TLS + 上游发布摘要。

## 4. 产物冒烟（隔离目录，不依赖开发环境）

- [x] 解包到临时目录（zip 内含单一顶层目录 `DuctZip-<version>\`），`PYTHONPATH` 置空后在该目录内运行 `ductzip.cmd doctor` 找到后端（捆绑或系统），并用它做一次真实解压。
      （解包得到单一顶层目录 `DuctZip-1.0.0rc1\`；`doctor` 解析到**包内捆绑**后端 26.03；
      用 `ductzip.cmd extract` 完成真实解压，内容往返一致。）
- [x] 中文 + 空格路径的压缩包 `extract` 成功。
- [x] `settings show` 使用包内/预期的设置路径。
      （`DuctZip-1.0.0rc1\settings\settings.json`；`set`/`unset` 往返正常。）
- [x] `shell register` → `reg query` 确认命令形态 → `shell unregister` 全部退出码 0，注册表无残留。
      （改用 `winreg` 直接读取替代 `reg query`，因为 bash 传递反斜杠路径会破坏 `reg` 参数；
      结论更强：`unregister` 后的快照与注册前**逐键相同**，`Software\Classes` 下无任何 `DuctZip*` 键。）
- [x] GUI launcher 能启动（有 PySide6 的环境）；无 PySide6 时给出可理解的错误。
      （两者都验证：offscreen 下 GUI 进程启动后持续存活；无 PySide6 时 `ductzip-gui` 打印可读说明并退出 1。）

## 5. 安全与隐私复核

- [x] 错误输出不含密码与后端原始输出（`tests/test_security.py` 覆盖）。
- [x] 未引入任何网络/遥测/自动更新行为。
- [x] `docs/SECURITY.md` 的「已知安全边界」段落与当前代码一致（链接/Junction、TOCTOU、列表上限）。
- [x] 仓库内无密钥、token、私有压缩包、本机绝对路径。

## 6. 发布决定记录

- [x] §10.2 全部决定已记录或明确接受为限制项。
- [x] 未签名状态在发布说明中明示（决定 #6），不伪造签名证据。
- [x] 延期项逐条列出并注明决定 #8 的授权。
- [x] 不执行 push/tag/release/发布（长期任务约束）；发布动作由用户手动完成。

## 7. 收尾

- [x] `PROGRESS.md` 记录以上每一步的实际结果。
- [x] 最终 `git status` / 暂存差异 / 未跟踪文件已复核并记录。

## 8. 2026-09-26 RC 关闭复核（2026-10-04 全量挂起修复已关闭，CODEX_ACCEPTED）

- [x] 独立 Review 报告 `docs/FINAL_REVIEW.md` 先于修复完成；P0/P1 清零，RC 阻塞级 P2 全部修复（逐项见报告）。
- [x] 首次全量套件异常退出（exit 1、无摘要）已用同签名复现崩溃根因解释，并以修复后 GUI 模块 20 连过 + 全量 3 连过关闭。
- [x] 每个修复带回归测试，且在旧实现上确定性失败（GUI 回收 2 项、MOTW 1 项、构建 manifest/内容 3 项）。
- [x] 便携包与 wheel 从最终源码重建；便携冒烟 11/11、wheel 干净 venv 冒烟 8/8（含 HKCU 注册往返零残留）。
- [x] 发布说明/清单/CHANGELOG/SECURITY 已同步到当前源码事实：256 项、Windows 进程树取消行为、MOTW 边界措辞和已知限制。
- [x] 最终提交后重新构建 wheel 与便携包，刷新 manifest 与 SHA-256，并重新执行隔离冒烟。
- [x] 仍不做 push/tag/release；本地 checkpoint commit 已创建，最终发布动作留给用户。
