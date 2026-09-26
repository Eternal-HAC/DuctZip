# Claude Code Long Tasks

本目录专门保存人工交给 Claude Code 执行的长任务合同，便于交接、审计和追溯。

## 命名规则

```text
YYYY-MM-DD_HH-mm_<task-slug>.md
```

- 时间使用任务生成时的本地时间，精确到分钟。
- 文件名使用 Windows 安全字符，不使用冒号。
- `<task-slug>` 简要描述任务目标，使用小写英文和连字符。
- 已经交付执行的任务不覆盖；需求变化时新增一个时间戳文件。

## 内容要求

每个任务至少写明：

- 当前 Git 与工作树基线。
- 目标、范围和 source of truth。
- 分阶段执行计划。
- 可验证验收标准。
- 允许自主决定的事项。
- 禁止操作和人工决策边界。
- 恢复协议和最终交付标记。

Claude Code 执行期间持续更新仓库根目录的 `PROGRESS.md`。功能状态、下一步和阻塞项发生变化时，同步更新 `PROJECT_STATUS.md`。

## 当前任务

- `2026-09-26_00-28_ductzip-final-review-and-rc-closure.md`：独立 Review、缺陷修复、构建复验和 v1.0.0rc1 收尾。
