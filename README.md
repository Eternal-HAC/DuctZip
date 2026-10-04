# DuctZip

DuctZip is a lightweight Windows archive extraction tool. This is **v1.0.0rc1**, a release candidate covering the CLI, archive core, batch queue, Windows Explorer integration, and an optional PySide6 GUI. It ships a bundled 7-Zip console backend, so extraction works on a machine with no 7-Zip installed.

The project is scoped as a focused extractor rather than a general archive manager: it does not compress, and it never phones home. Scope, architecture, decisions, and test coverage are documented in this repository so it can be reviewed as a maintainable project rather than a one-off script.

## Features

- `ductzip extract` command for extracting an archive into a target directory.
- `ductzip list` command for listing archive entries.
- `ductzip test` command for archive integrity checks.
- `ductzip doctor` command for checking whether a usable 7-Zip backend is available.
- `ductzip batch-extract` command for extracting multiple archives into one shared output root, with per-task reporting, retries, and documented exit codes (0 all completed, 1 some failed, 130 cancelled, 2 usage error).
- GUI batch queue: drop or multi-select archives, watch per-task status/progress/error, retry or remove failed/cancelled tasks, cancel the current task or the whole batch, and double-click a finished task to open its output folder. One failed archive never blocks the rest.
- Optional PySide6 GUI prototype with archive selection, drag-and-drop, output directory selection, archive preview, password input, progress display, cancellation, overwrite policy selection, and an open-output-folder action after extraction.
- GUI previews load on a background worker thread with stale-result protection (switching archives never shows the previous archive's listing), and window shutdown terminates background work within a bounded time.
- 7-Zip discovery through:
  - explicit `--sevenzip` path
  - `DUCTZIP_7Z_PATH`
  - bundled `vendor/7zip/7z.exe` backend (7-Zip 26.03, tracked in the repository and shipped in the portable build)
  - standard Windows 7-Zip install directories
  - Windows uninstall registry entries
  - `PATH`
- Bundled console backend, so a machine with no 7-Zip installation can still extract. The bundled binary carries no publisher signature; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for the verification chain and the residual supply-chain limitation.
- ZIP, 7z, and RAR extraction verified with real 7-Zip integration tests.
- Chinese and space-containing paths covered by tests.
- Password-protected 7z extraction covered by tests.
- Path traversal entries are blocked before extraction, along with absolute paths, drive-relative paths, UNC/`\\?\` prefixes, and Windows reserved device names (`CON`, `NUL`, `COM1-9`, `LPT1-9`, ...).
- Cancellation is responsive even when the backend produces no output, and the engine deterministically reaps the 7-Zip child process on every path (completion, failure, cancel, abandoned generators).
- Extraction can emit structured lifecycle and progress events for future GUI use.
- Extraction can be cancelled through a core-layer cancellation signal for future GUI use.
- Existing files are handled through explicit overwrite policies: `skip`, `overwrite`, or `rename`.
- Smart output avoids scattered files and duplicate top-level folders, driven by one pure `SmartOutputPolicy` shared by the CLI and GUI (v0.4.1 semantics): an empty archive or a single top-level file extracts directly to the requested output; a single top-level directory extracts to the requested output, or to its parent when the requested folder already has the same name; multiple top-level entries extract to a same-named subfolder derived from the archive name, unless the requested output already has that name.
- The logical archive name strips common archive extensions, including multi-suffix formats such as `tar.gz` and volume naming such as `.7z.001` and `part01.rar`.
- The GUI previews the final extraction directory and warns about existing top-level output conflicts.
- Top-level output conflicts can be handled with `merge`, `rename`, or `cancel`.
- Basic error mapping for missing archives, missing 7-Zip, corrupted archives, unsupported formats, password errors, and permission errors.

## Not Yet Implemented

- Compression.
- Installer / signed release artifacts.

## Tech Stack

- Python 3.11+
- Standard-library CLI and test tooling
- 7-Zip CLI backend (`7z.exe` or `7zz.exe`)
- Optional GUI stack: PySide6

## Requirements

- Windows.
- Python 3.11 or newer.
- No 7-Zip installation required: the repository and the portable build ship a bundled backend. A system-installed or explicitly configured `7z.exe` / `7zz.exe` takes priority when you want a different one.

The bundled backend is used automatically. `ductzip doctor` reports which backend was selected; an explicit `--sevenzip` path always wins, and a system installation is used when no bundled copy is present.

Install GUI dependencies:

```powershell
python -m pip install -e .[gui]
```

## Usage

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip doctor
```

Extract an archive:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "archive.zip" --output "output-dir"
```

List archive entries:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip list "archive.zip"
```

Test archive integrity:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip test "archive.zip"
```

Extract a password-protected archive:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "secret.7z" --output "output-dir" --password-prompt
```

DuctZip always prompts for the password itself (`--password-prompt`, or the GUI dialog) and hands the answer to the backend. The backend is never allowed to ask: it runs with its console input closed, so extraction cannot stall on a prompt DuctZip does not own. An encrypted archive with no password given reports `该压缩包需要密码。`; a wrong password reports `密码错误。`. Passwords are never printed, logged, or written to settings.

Choose how existing files are handled:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "archive.zip" --output "output-dir" --overwrite-policy skip
python -m ductzip extract "archive.zip" --output "output-dir" --overwrite-policy overwrite
python -m ductzip extract "archive.zip" --output "output-dir" --overwrite-policy rename
```

The default policy is `skip`. It applies per file, inside the final directory:

| Policy | An existing `photos/a.txt` |
| --- | --- |
| `skip` (default) | kept as it is; the archived copy is not written |
| `overwrite` | replaced by the archived copy |
| `rename` | kept; the archived copy is written alongside as `a_1.txt` |

Avoid scattered files and duplicate top-level folders when extracting:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "photos.zip" --output "photos" --smart-output
python -m ductzip extract "loose-files.zip" --output "." --smart-output
```

With Smart output, the CLI and GUI both go through the shared `ExtractionService` and `SmartOutputPolicy`: single top-level directories never end up nested as `name/name`, and multi-entry archives land in a folder named after the archive.

Choose how top-level output conflicts are handled:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "archive.zip" --output "output-dir" --conflict-strategy merge
python -m ductzip extract "archive.zip" --output "output-dir" --conflict-strategy rename
python -m ductzip extract "archive.zip" --output "output-dir" --conflict-strategy cancel
```

The default conflict strategy is `merge`. A conflict is a **top-level entry the archive shares with the target directory** — for example extracting `photos.zip` into a directory that already has a `photos` folder:

| Strategy | What happens |
| --- | --- |
| `merge` (default) | extraction proceeds into the existing entry; the overwrite policy decides each colliding file |
| `rename` | extraction proceeds, but a colliding file is written under a new name instead of being skipped or replaced |
| `cancel` | nothing is written; the conflicting entry is named and the command exits 1 |

`--smart-output` decides *where* the archive lands, `--conflict-strategy` decides what happens when that place is already occupied, and `--overwrite-policy` decides what happens to individual files inside it.

Extract several archives into one shared output root:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip batch-extract "photos.zip" "docs.7z" "old.rar" --output "extracted"
python -m ductzip batch-extract *.zip --output "extracted" --retries 2 --verbose
```

`batch-extract` runs the archives strictly in the order given, one at a time. Each task reports `[完成]` (completed), `[失败]` (failed), or `[取消]` (cancelled), and the command exits with 0 when everything completed, 1 when at least one task failed, 130 when cancelled, and 2 on a usage error. `--retries N` re-runs failed tasks up to N times; Smart output and conflict strategies work per task.

Every command uses the same exit codes:

| Code | Meaning |
| --- | --- |
| 0 | the work completed |
| 1 | the archive failed, or one or more batch tasks failed |
| 2 | usage error (unknown command, missing required option) |
| 130 | cancelled by the user (Ctrl+C, or Ctrl+Break) |

Cancellation stops the backend and waits for it to exit before returning, so nothing is left writing into the output directory.

Launch the GUI prototype:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip.gui
```

Register Windows Explorer integration (current user, no elevation — adds "用 DuctZip 解压到当前目录 / 解压到同名文件夹" to the archive context menu):

```powershell
$env:PYTHONPATH = "src"
python -m ductzip shell register
python -m ductzip shell status
python -m ductzip shell unregister
```

Registration is idempotent and exactly reversible; see [`docs/WINDOWS_INTEGRATION.md`](docs/WINDOWS_INTEGRATION.md) for the registry layout, the stable invocation protocol, and known limitations.

Manage durable preferences (backend path, default policies):

```powershell
$env:PYTHONPATH = "src"
python -m ductzip settings                 # show current values and file location
python -m ductzip settings set smart_output false
python -m ductzip settings set sevenzip_path "D:\7-Zip\7z.exe"
python -m ductzip settings unset sevenzip_path
```

Settings live in `%APPDATA%\DuctZip\settings.json` (override with `DUCTZIP_SETTINGS_PATH`). Explicit command-line flags always win over settings, and settings never change the CLI's built-in defaults on their own. The GUI has the same options under **Settings…**. Corrupt settings files are backed up as `settings.json.corrupt` and reset to defaults. See [`docs/SECURITY.md`](docs/SECURITY.md) for the full security and privacy statement (password handling, network behavior, and known limitations).

The GUI supports archive preview, password input, Smart output (on by default, with the output directory defaulting to the archive's parent folder), final-output preview, and conflict strategy selection. If a preview fails because the archive requires a password, enter the password and reload by leaving the password field.

Use a specific 7-Zip backend:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "archive.zip" --output "output-dir" --sevenzip "D:\7-Zip\7z.exe"
```

Print diagnostic details during extraction:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "archive.zip" --output "output-dir" --verbose
```

`--verbose` prints backend details and progress percentages when 7-Zip emits them.

## Tests

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
```

The test suite includes fake-backend unit tests and real 7-Zip integration tests. Real-backend tests are skipped when 7-Zip is unavailable.

For GUI tests in headless environments:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
```

## Project Highlights

- Clear separation between the CLI layer, the application orchestration layer, and the archive backend.
- Replaceable backend design centered on `SevenZipCliEngine`; Smart output and conflict policies live in the pure `ductzip.core` layer and are shared by the CLI and GUI.
- Windows-first backend discovery, including registry-based 7-Zip lookup.
- Testable command-line workflow before adding GUI complexity.
- Product and architecture documentation maintained in `docs/`.
- Explicit roadmap for Smart Extraction, progress reporting, path safety, GUI, and Windows integration.

## Roadmap

- v0.1: CLI prototype with backend discovery and basic extraction.
- v0.2: reusable extraction core with listing, testing, progress, cancellation, password handling, and path traversal protection.
- v0.3: PySide6 GUI prototype.
- v0.4: Smart Extraction.
- v0.4.1: Smart Output Semantics formalized in `ductzip.core` with a shared CLI/GUI orchestration service.
- v0.5: batch extraction.
- v0.6: Windows Explorer integration.
- v0.7: settings, security hardening, and privacy documentation; portable packaging and the bundled 7-Zip backend.
- v1.0.0rc1: release-candidate closure — every LONG_TASK §7 acceptance item executed and recorded, plus the end-user manual, release notes, and security statement. The current source passed 256 tests and Codex final acceptance; release artifacts are built from a clean committed tree and carry their own manifest/checksum evidence. Not yet pushed, tagged, or published.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the detailed plan.

## Project Docs

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) — end-user manual: install, first run, CLI/GUI, context menu, passwords, conflicts, uninstall, troubleshooting
- [`docs/RELEASE_NOTES_1.0.0rc1.md`](docs/RELEASE_NOTES_1.0.0rc1.md) — 1.0.0rc1 release notes: artifacts, environments, the recorded limitations, and the §7 acceptance evidence summary
- [`docs/SECURITY.md`](docs/SECURITY.md) — security and privacy statement, password handling, known boundaries
- [`docs/PRD.md`](docs/PRD.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md)
- [`docs/MARKET_RESEARCH.md`](docs/MARKET_RESEARCH.md)

## License

DuctZip is released under the MIT License. See [`LICENSE`](LICENSE).

DuctZip bundles the 7-Zip console backend under [`vendor/7zip/`](vendor/7zip/) (7-Zip 26.03, LGPL v2.1+ with the unRAR restriction). Third-party components, their licenses, the exact source URL, and the recorded SHA-256 checksums are documented in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
