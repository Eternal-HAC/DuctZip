# DuctZip Release Checklist

一步一步的发布前检查清单。当前状态：适用于 v0.7.x → v1.0 RC。
每一步都要把实际结果（命令输出摘要、校验和、退出码）记录进 `PROGRESS.md`。

## 1. 代码与测试门

- [ ] `git status --short` —— 只有本清单预期的文件；无 UNKNOWN 文件被改动或删除。
- [ ] `python -m unittest discover -s tests`（`PYTHONPATH=src`、`PYTHONDONTWRITEBYTECODE=1`、`QT_QPA_PLATFORM=offscreen`）—— 全部通过；每个 skip 都在 `PROGRESS.md` 记录前提与影响。
- [ ] `python -m pip check` —— 无 broken requirements。
- [ ] `python -m pip wheel . --no-deps` —— 成功，wheel 版本与 `pyproject.toml` 一致。
- [ ] `git diff --check` —— 无空白错误。

## 2. 版本与文档一致性

- [ ] `pyproject.toml` / `src/ductzip/__init__.py` / README / PROJECT_STATUS / ROADMAP / CHANGELOG 的版本号、测试数、功能清单相互一致。
- [ ] CHANGELOG 的 [Unreleased] 已整理为目标版本段落，未重写历史条目。
- [ ] README「Not Yet Implemented」与真实行为一致（不宣称未实现的能力）。
- [ ] `docs/SECURITY.md` 的 MOTW/密码/网络承诺与代码行为一致。

## 3. 构建产物

- [ ] `python scripts/build_portable.py` 从零构建成功（可先删除 `dist/`）。
- [ ] 记录 `dist/build-manifest.json` 的 git 提交号、Python 版本、`bundled_7zip` 标志。
- [ ] 记录产物 SHA-256（`.sha256` 文件内容）。
- [ ] 解包检查：无 `tests/`、`__pycache__`、本地路径、私有样例；`LICENSE`/`THIRD_PARTY_NOTICES.md`/`README.md` 在位。
- [ ] 若捆绑 7-Zip：`vendor/7zip/` 内二进制与构建清单中的版本/校验和一致；`THIRD_PARTY_NOTICES.md` 已填具体版本、来源与校验和。

## 4. 产物冒烟（隔离目录，不依赖开发环境）

- [ ] 解包到临时目录，`PYTHONPATH` 置空后运行 `ductzip.cmd doctor` 找到后端（捆绑或系统）。
- [ ] 中文 + 空格路径的压缩包 `extract` 成功。
- [ ] `settings show` 使用包内/预期的设置路径。
- [ ] `shell register` → `reg query` 确认命令形态 → `shell unregister` 全部退出码 0，注册表无残留。
- [ ] GUI launcher 能启动（有 PySide6 的环境）；无 PySide6 时给出可理解的错误。

## 5. 安全与隐私复核

- [ ] 错误输出不含密码与后端原始输出（`tests/test_security.py` 覆盖）。
- [ ] 未引入任何网络/遥测/自动更新行为。
- [ ] `docs/SECURITY.md` 的「已知安全边界」段落与当前代码一致（链接/Junction、TOCTOU、列表上限）。
- [ ] 仓库内无密钥、token、私有压缩包、本机绝对路径。

## 6. 发布决定记录

- [ ] §10.2 全部决定已记录或明确接受为限制项。
- [ ] 未签名状态在发布说明中明示（决定 #6），不伪造签名证据。
- [ ] 延期项逐条列出并注明决定 #8 的授权。
- [ ] 不执行 push/tag/release/发布（长期任务约束）；发布动作由用户手动完成。

## 7. 收尾

- [ ] `PROGRESS.md` 记录以上每一步的实际结果。
- [ ] 最终 `git status` / 暂存差异 / 未跟踪文件已复核并记录。
