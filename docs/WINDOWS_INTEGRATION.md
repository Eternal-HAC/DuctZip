# DuctZip Windows 集成说明

更新时间：2026-09-19（v0.6）

## 范围与原则

DuctZip 的 Windows 集成只做**可逆的当前用户（HKCU）注册表项**：

- 不安装任何原生 Shell Extension（DLL/预览处理器）。
- 不写入 HKLM，不需要管理员权限或 UAC 提权。
- 只写 DuctZip 自己拥有的键：其他程序的注册项一律不碰。
- `unregister` 精确移除 `register` 创建的全部内容；正常卸载后不需要任何手工注册表清理。

## 注册与卸载

```powershell
$env:PYTHONPATH = "src"
python -m ductzip shell register     # 注册（幂等，可重复执行）
python -m ductzip shell status       # 查看注册状态与 launcher 是否有效
python -m ductzip shell unregister   # 卸载（未注册时也是安全的空操作）
```

`register` 记录启动器绝对路径（优先 `pythonw.exe`，无控制台窗口）与版本、时间戳；重复执行结果是幂等的。如果 Python 移动或删除导致记录的 launcher 失效，`status` 会报告 "已失效"，重新执行一次 `register` 即可修复。

## 注册表布局（全部在 HKEY_CURRENT_USER 下）

- `Software\DuctZip`：元数据（RegisteredExe / Version / RegisteredAt）。
- `Software\Classes\DuctZip.Archive`：ProgID，含 `shell\open`（打开 GUI）与两个解压动词。
- `Software\Classes\SystemFileAssociations\<ext>\shell\DuctZip.ExtractHere|DuctZip.ExtractTo`：覆盖 `.zip .7z .rar .tar .gz .bz2 .xz .zst` 的右键菜单动词（MUIVerb：「用 DuctZip 解压到当前目录」「用 DuctZip 解压到同名文件夹」）。
- `Software\Classes\<ext>\OpenWithProgids`：值为 `DuctZip.Archive`，让 DuctZip 出现在「打开方式」列表中。**不会**更改任何扩展名的默认打开程序。

## 调用协议（稳定契约）

右键菜单命令行为：

```
"<launcher>" -m ductzip shell extract-here "%1"
"<launcher>" -m ductzip shell extract-to "%1"
```

- `%1` 由 Explorer 替换为所选压缩包路径，带引号，空格与 Unicode（中文）路径安全。
- `extract-here`：每个压缩包解压到它自己的父目录（Smart output 语义，松散文件不另套目录）。
- `extract-to`：每个压缩包解压到同级同名文件夹（按压缩包逻辑名，支持 `.tar.gz` 等多后缀与 `.7z.001` 分卷命名）。
- 两个动词都接受一条命令里传多个压缩包（`"%1"` 位置可扩展为多个路径），也支持 `--password` / `--password-prompt`、`--overwrite-policy`、`--conflict-strategy`、`--retries`、`--sevenzip`、`--verbose`。
- 退出码与 `batch-extract` 一致：0 全部完成，1 部分失败，130 取消。

Explorer 对经典右键动词的行为是**每个选中文件各启动一次进程**（多选 N 个压缩包 = N 次调用），每次只处理一个文件；协议本身支持多路径单进程。单个压缩包失败不影响其他选中项（队列失败隔离）。

## 已知限制（诚实声明）

- Windows 11 的经典注册表动词默认折叠在右键菜单「显示更多选项」里；不实现现代 IExplorerCommand 稀疏包（属于未获批准的原生 Shell Extension）。
- 多后缀压缩包（如 `.tar.gz`）的右键菜单由 `.gz` 条目覆盖；SystemFileAssociations 不支持真正的多后缀键。
- 「文件关联」当前仅指「打开方式」可见性；不改变默认程序是刻意设计（可逆、不劫持）。
- 便携包发布（Phase 6）时需要在新机器上重新执行 `register`，因为命令里记录的是绝对路径。
