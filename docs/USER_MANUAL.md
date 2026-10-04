# DuctZip 用户手册

面向使用者的操作说明：安装、第一次运行、日常解压、批处理、密码、冲突处理、卸载与故障排查。

- 本手册描述 **DuctZip 1.0.0rc1（未签名候选版）** 的行为。
- 命令行提示为中文；图形界面按钮为英文标签。
- 想了解内部设计与安全边界，见 `README.md`、`docs/SECURITY.md`、`docs/ARCHITECTURE.md`。

---

## 1. DuctZip 是什么

一个轻量的 Windows 解压工具，只做解压，不做压缩。三种用法共用同一套解压逻辑：

| 入口 | 命令 | 说明 |
| --- | --- | --- |
| 命令行 | `ductzip` | 单包解压、批量解压、列出内容、校验完整性、设置、自检 |
| 图形界面 | `ductzip-gui` | 选包、预览内容、解压、批量队列（需另装 PySide6） |
| 资源管理器右键菜单 | `ductzip shell` 注册 | 当前用户的 HKCU 注册，可完全撤销 |

DuctZip 自己不解压：它调用 7-Zip 命令行后端，并在调用前后负责路径安全校验、输出目录规划、文件冲突处理、密码索取与错误翻译。**7-Zip 后端已随程序捆绑**，因此不装 7-Zip 也能用。

### 默认不做的事

不联网、不检查更新、不收集遥测、不写云端。所有操作都在本机完成。

---

## 2. 运行环境

- Windows 10 / 11（x64）。
- Python 3.11 或更新版本，且在 `PATH` 上（`python` / `pythonw`）。
- 图形界面额外需要 PySide6（可选，命令行不需要）。
- 7-Zip：**不需要**单独安装，便携包与源码仓库都带有捆绑后端。

---

## 3. 安装

### 3.1 便携包（推荐，免安装）

1. 解压 `DuctZip-1.0.0rc1-portable.zip`。压缩包内**只有一个顶层目录** `DuctZip-1.0.0rc1\`，把整个目录放到任意位置（例如 `D:\Tools\DuctZip-1.0.0rc1\`）即可。
2. 在该目录内运行：

   ```bat
   ductzip.cmd doctor
   ```

   能打印出 7-Zip 路径与版本，说明可用。

3. 图形界面：双击 `DuctZip GUI.cmd`，或在目录内运行 `ductzip.cmd` 的同级命令 `python -m ductzip.gui`。

便携包的特点：

- 设置文件保存在包内 `settings\settings.json`，整个目录可整体复制、整体删除。
- 右键菜单通过 `ductzip.cmd shell register` 注册（见 §7）。
- 目录移动后需要**重新执行一次** `shell register`（注册表里记录的是绝对路径）。

### 3.2 从源码或 wheel 安装

在源码目录内：

```powershell
python -m pip install .
# 或先构建 wheel 再安装：
python -m pip wheel . --no-deps --wheel-dir dist
python -m pip install dist\ductzip-1.0.0rc1-py3-none-any.whl
```

安装后 `ductzip` 与 `ductzip-gui` 两个命令在 `PATH` 上可用。**注意：DuctZip 目前没有发布到 PyPI**，不要执行 `pip install ductzip`。

从源码目录临时运行（不安装）：

```powershell
$env:PYTHONPATH = "src"
python -m ductzip doctor
```

### 3.3 图形界面依赖

```powershell
python -m pip install PySide6
```

未安装时启动图形界面会打印一段说明并退出（退出码 1），命令行不受影响：

```text
DuctZip GUI requires PySide6, which is not installed in this Python environment.

Install it with:
    python -m pip install PySide6

The command-line interface (ductzip) works without PySide6.
```

---

## 4. 首次运行

### 4.1 自检

```powershell
ductzip doctor
```

输出示例：

```text
DuctZip doctor
7-Zip: D:\Tools\DuctZip-1.0.0rc1\vendor\7zip\7z.exe
Version: 7-Zip 26.03 (x64) : Copyright (c) 1999-2026 Igor Pavlov : 2026-09-03
```

失败时退出码为 1，并说明原因（通常是找不到后端，见 §11）。

### 4.2 设置文件位置

```powershell
ductzip settings show
```

默认位置 `%APPDATA%\DuctZip\settings.json`；便携包使用包内 `settings\settings.json`。可用环境变量 `DUCTZIP_SETTINGS_PATH` 指定其他位置。

设置文件损坏时会被备份为 `settings.json.corrupt` 并重置为默认值，程序不会因此启动失败。

### 4.3 注册右键菜单（可选）

```powershell
ductzip shell register     # 注册到当前用户，无需管理员权限
ductzip shell status       # 查看注册状态与启动器是否失效
ductzip shell unregister   # 精确撤销，只删自己写的键
```

---

## 5. 命令行用法

所有命令都支持 `-h` / `--help`。

### 5.1 解压单个压缩包

```powershell
ductzip extract "archive.zip" --output "D:\out"
ductzip extract "archive.zip" --output "D:\out" --smart-output
ductzip extract "secret.7z" --output "D:\out" --password-prompt
```

常用选项：

| 选项 | 作用 |
| --- | --- |
| `-o`, `--output` | **必填**。普通模式下就是最终解压目录；Smart 模式下是基准目录 |
| `--smart-output` | 按压缩包结构推导最终目录（见 §8） |
| `--conflict-strategy` | `merge`（默认）/ `rename` / `cancel`，见 §9 |
| `--overwrite-policy` | `skip`（默认）/ `overwrite` / `rename`，见 §9 |
| `--password` | 直接给出密码（会留在命令历史里，日常建议改用 `--password-prompt`） |
| `--password-prompt` | 交互式输入密码，不回显 |
| `--sevenzip` | 指定本次使用的 7-Zip 后端路径 |
| `--verbose` | 打印诊断细节（后端路径、进度百分比） |

### 5.2 查看内容与校验完整性

```powershell
ductzip list "archive.zip"
ductzip test "archive.zip"
```

`list` 每行输出 `类型<TAB>大小<TAB>路径`（`f` 文件、`d` 目录，目录的大小为空）。`test` 只校验，不解压，通过时打印 `压缩包测试通过。`

### 5.3 批量解压

```powershell
ductzip batch-extract "a.zip" "b.7z" "c.rar" --output "D:\extracted"
ductzip batch-extract *.zip --output "D:\extracted" --retries 2 --verbose
```

- 严格按命令行给出的顺序、**逐个**执行。
- 每个任务输出一行 `[完成]` / `[失败]` / `[取消]`，末尾在 stderr 给出汇总。
- 一个任务失败不影响后续任务。
- `--retries N` 对失败的任务再重试最多 N 次。
- 每个任务独立套用 Smart Output 与冲突策略，`--output` 是它们共享的基准目录。

### 5.4 设置

```powershell
ductzip settings show
ductzip settings set overwrite_policy overwrite
ductzip settings set sevenzip_path "D:\7-Zip\7z.exe"
ductzip settings unset smart_output
```

可设置的键：`sevenzip_path`、`overwrite_policy`、`conflict_strategy`、`smart_output`。

优先级固定为：**命令行显式选项 > 设置文件 > 内置默认值**。因此保存设置不会在你毫不知情时改变某次命令行的行为。

### 5.5 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 完成 |
| 1 | 解压失败，或批量任务中至少一个失败 |
| 2 | 用法错误（未知命令、缺少必填选项） |
| 130 | 用户取消（Ctrl+C 或 Ctrl+Break） |

取消时会先停止后端并等它退出再返回，不会留下仍在往输出目录写文件的进程。取消是有界的：实测按 Ctrl+Break 后 DuctZip 启动的后端在 0.77 秒内被回收。

### 5.6 输出编码

命令行输出统一使用 **UTF-8**，不随本机控制台代码页变化。这一点在两种常见场景下有意义：

- 直接看：接在真实控制台上时行为与原来一致，中文正常显示。
- 重定向：`ductzip list x.zip > out.txt` 写出的文件是 UTF-8。如果你此前习惯用「ANSI/GBK」
  方式打开这类文件，请在编辑器里选择 UTF-8，否则中文会显示为乱码。

---

## 6. 图形界面

启动：`ductzip-gui`，或 `python -m ductzip.gui`，或便携包里的 `DuctZip GUI.cmd`。

主窗口提供：

- **Archive / Base output**：选择压缩包与输出目录（可拖放压缩包）。
- **Archive contents**：解压前预览压缩包条目。
- **Final output**：Smart Output 推导出的最终目录，解压前即可看到。
- **Conflicts**：目标目录里已存在的同名顶层项，解压前即可看到。
- **Password**：密码输入框。
- **Existing files / Conflicts**：两个下拉框，对应覆盖策略与冲突策略。
- **Extract / Cancel**：开始与取消。取消有界（实测取消单次解压 63ms、解压中关闭窗口 41ms、批量取消全部 0.02s，均无残留后端进程），窗口关闭时会先取消并回收后端。
- **Open Folder**：解压完成后打开最终目录。
- **Batch queue**：多选或拖入多个压缩包形成队列，逐个执行；可开始、重试失败项、移除任务、取消当前、取消全部；双击已完成任务打开其最终目录。
- **Log**：运行日志；密码不会出现在这里。
- **Settings…**：与 `ductzip settings` 同一套设置（写同一个文件）。

切换或清空 Archive 路径时，预览、最终目录、冲突提示与上一次的打开目录状态会立即清空；迟到的旧结果会被丢弃。

---

## 7. 右键菜单

注册后，右键选中的压缩包会出现：

- **用 DuctZip 解压到当前目录**（`shell extract-here`）：每个压缩包解压到自己所在的目录。
- **用 DuctZip 解压到同名文件夹**（`shell extract-to`）：每个压缩包解压到旁边一个与压缩包同名的文件夹。
- **打开方式** 中出现 DuctZip（不改变默认程序）。

覆盖的扩展名：`.zip .7z .rar .tar .gz .bz2 .xz .zst`。

已知行为，不算故障：

- Windows 11 的经典动词默认收在右键菜单的**「显示更多选项」**里。
- 多选 N 个压缩包时，资源管理器会**启动 N 次进程**，每次处理一个（协议本身支持多路径）。
- 多后缀压缩包（如 `.tar.gz`）由 `.gz` 条目覆盖。
- 移动过程序目录后，需要重新执行 `shell register`；`ductzip shell status` 可检测失效的启动器。

---

## 8. 解压到哪：Smart Output

不加 `--smart-output` 时，`--output` 就是最终目录，压缩包内容直接铺在里面。

加 `--smart-output` 时，DuctZip 先看压缩包的顶层结构再决定：

| 压缩包顶层结构 | 最终目录 |
| --- | --- |
| 只有一个顶层目录（如全部在 `photos/` 下） | 直接用基准目录，不会出现 `photos\photos\` |
| 多个顶层项 | 基准目录下新建一个与压缩包同名的子目录 |

批量解压默认开启 Smart Output，可用 `--no-smart-output` 关闭。

---

## 9. 文件已存在怎么办：覆盖策略与冲突策略

这是两个不同层面的选择：

- **`--smart-output`** 决定解压到**哪里**；
- **`--conflict-strategy`** 决定那个地方**已经被占用**时怎么办；
- **`--overwrite-policy`** 决定占用之后，**具体文件**怎么处理。

### 冲突策略（顶层项冲突）

冲突指：压缩包里的顶层项与目标目录里已有的顶层项同名。例如把 `photos.zip` 解压到一个已经有 `photos` 文件夹的位置。

| 取值 | 行为 |
| --- | --- |
| `merge`（默认） | 解压进已有目录，每个同名文件按覆盖策略处理 |
| `rename` | 继续解压，但同名文件改名写入，不覆盖也不跳过 |
| `cancel` | 什么都不写，报出冲突项名称并退出 1 |

### 覆盖策略（文件级）

| 取值 | 目标已存在 `photos\a.txt` 时 |
| --- | --- |
| `skip`（默认） | 保留原文件，不写入压缩包里的版本 |
| `overwrite` | 用压缩包里的版本替换 |
| `rename` | 保留原文件，压缩包里的版本写成 `a_1.txt` |

---

## 10. 密码

```powershell
ductzip extract "secret.7z" --output "D:\out" --password-prompt
```

- 密码一律由 DuctZip 自己索取（`--password-prompt`，或图形界面的密码框），再交给后端。后端进程的输入被接管，**不会**弹出自己的密码提示，因此不会出现卡在提示符上的情况。
- 密码只存在于内存，**不写入**设置文件、日志、进度事件或批量日志；出错输出中也不会包含密码。
- 两种情况会给出不同提示：

| 情况 | 提示 |
| --- | --- |
| 压缩包加密，但没给密码 | `该压缩包需要密码。` |
| 给了密码但不对 | `密码错误。` |

- `--password` 会把密码留在 shell 历史和进程列表里，仅适合脚本等无法交互的场合。

---

## 11. 7-Zip 后端

DuctZip 自己不解压，它调用 7-Zip 命令行后端。查找顺序如下，**先找到的先用**：

1. `--sevenzip` 指定的路径（指定了就必须存在，不会静默回退）；
2. 环境变量 `DUCTZIP_7Z_PATH`；
3. 程序自带的 `vendor\7zip\7z.exe`；
4. 常见的 7-Zip 安装目录；
5. 注册表记录；
6. `PATH`。

因此：想用自己那份 7-Zip，用 `--sevenzip` 或 `DUCTZIP_7Z_PATH` 指过去即可；捆绑后端不会覆盖你的选择。

### 关于捆绑后端的签名

上游 7-Zip **不对 Windows 二进制做 Authenticode 签名**，所以捆绑的 `7z.exe` / `7z.dll` 没有发布者签名。它们通过 TLS 传输、上游发布元数据中的 SHA-256 摘要与本机实测三者比对来验证，完整链条与哈希记录在 `THIRD_PARTY_NOTICES.md`。

这是明确的残余限制：如果你的环境要求后端必须有代码签名，请用 `--sevenzip` 指向自己信任的、已签名的后端。

---

## 12. 安全与隐私

- **不联网**：没有下载、更新、遥测或云功能。
- **路径拦截**：解压前由引擎自己列出条目并校验，任何逃出输出边界的路径（`..`、绝对路径、UNC、设备名等）都会中止解压（`已阻止不安全的压缩包路径。`），不会先写后删。
- **不写设置以外的东西**：除输出目录、设置文件、以及你主动执行的 `shell register` 写入的 HKCU 键之外，DuctZip 不在别处写文件。
- **MOTW 传播**：解压成功后，压缩包的「来源区域」标记（`Zone.Identifier`）会复制到每个解压出的文件上，让 Windows 继续按来源区域对待它们。此步骤是尽力而为：非 NTFS、压缩包本身没有该标记时会安静跳过，个别文件失败也不会让解压失败。

### 已知边界（不支持，明确声明）

- **压缩包内的符号链接 / Junction / 重解析点**：不支持，也不做防护。需要解压不可信来源的压缩包时请注意。
- **压缩包在规划与解压之间被替换**：安全性以实际列出的条目为准，但 Smart Output 的目录规划可能与最终落盘布局不一致。
- **超大压缩包的列表/输出**：没有硬性资源上限。
- **取消行为因平台而异**：Windows 会尽力通过 `taskkill /F /T` 回收 DuctZip 启动的包装脚本及其进程树；非 Windows 平台只保证回收直接子进程。正常完成时最多等待包装脚本后代输出 10 秒，极端慢输出的自定义包装脚本可能丢失尾部输出。捆绑的 `7z.exe` 不派生子进程，不受该边界影响。

---

## 13. 卸载

### 便携包

1. `ductzip.cmd shell unregister`（若注册过右键菜单）。
2. 删除整个 `DuctZip-1.0.0rc1\` 目录。

没有安装程序、没有服务、没有开机自启项，删目录即卸载干净。包内的 `settings\settings.json` 随目录一起删除。

### pip 安装

```powershell
ductzip shell unregister
python -m pip uninstall ductzip
```

如需一并清除设置，删除 `%APPDATA%\DuctZip\`（其中 `settings.json` 是设置，`settings.json.corrupt` 是上一次损坏时的备份）。

### 只撤销右键菜单

```powershell
ductzip shell unregister
ductzip shell status      # 确认已无残留
```

`unregister` 只删除 DuctZip 自己写入的 HKCU 键，不会影响其他程序的关联。

---

## 14. 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `未找到 7-Zip 后端，请安装 7-Zip 或使用 --sevenzip 指定 7z.exe 路径。` | 六处查找都没命中 | `ductzip doctor` 看查找结果；用 `--sevenzip` 指路径，或把 7-Zip 装到默认位置 |
| `找不到压缩包。` | 路径不存在或拼错 | 检查路径；含空格或中文时用引号包起来 |
| `该压缩包需要密码。` | 压缩包加密，未提供密码 | 加 `--password-prompt` |
| `密码错误。` | 密码不对 | 重新输入；注意全角/半角与输入法 |
| `压缩包可能已损坏。` | 文件损坏，或下载不完整 | 重新获取压缩包；用 `ductzip test` 复核 |
| `暂不支持该压缩包格式。` | 后端不支持该格式或压缩方法 | 换用较新的 7-Zip 后端（`--sevenzip`）重试 |
| `已阻止不安全的压缩包路径。` | 压缩包含逃出输出目录的条目 | **不要绕过**。确认来源可信；这是刻意拦截 |
| `目标目录存在冲突：xxx` | 冲突策略为 `cancel` 且目标已存在 | 改用 `--conflict-strategy merge` 或 `rename`，或换输出目录 |
| `没有写入目标目录的权限。` | 输出路径无写权限 | 换有权限的目录，或以有权限的账户运行 |
| `解压失败，请检查压缩包是否损坏或格式是否受支持。` | 后端返回了未分类的错误 | 加 `--verbose` 复现，再用 `ductzip test` 区分是损坏还是格式问题 |
| `已取消：正在停止...`，退出码 130 | 你自己按了 Ctrl+C / Ctrl+Break | 正常行为 |
| 退出码 2，且没有解压 | 命令写错 | `ductzip <命令> --help` |
| 启动图形界面只打印一段英文说明并退出 1 | 没装 PySide6 | `python -m pip install PySide6` |
| 右键菜单里没有 DuctZip | 未注册；或 Windows 11 折叠了经典动词；或程序目录已移动 | `ductzip shell status` 看状态 → `ductzip shell register`；Windows 11 请在「显示更多选项」里找 |
| 右键菜单报错或没反应 | 注册时记录的启动器路径已失效 | `ductzip shell register` 重新注册 |
| 把输出重定向到文件后，中文用某些编辑器打开是乱码 | 输出是 UTF-8，编辑器按 ANSI/GBK 打开了它 | 在编辑器里把文件按 UTF-8 打开（见 §5.6） |

排查时优先看 `--verbose` 输出与图形界面的 Log 面板；两者都只展示稳定的中文短句或诊断信息，不会打印密码。
