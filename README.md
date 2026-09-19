# DuctZip

DuctZip is a lightweight Windows archive extraction tool. The current version is a v0.7 CLI, archive-core, batch queue, Windows Explorer integration, and PySide6 GUI prototype focused on reliably finding a local 7-Zip backend, inspecting archives, extracting files, and returning clear user-facing results.

The project is intentionally scoped as an engineering prototype for a future desktop extractor. It documents product research, architecture, roadmap decisions, and test coverage so the repository can be reviewed as a maintainable open-source project rather than a one-off script.

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
  - planned bundled `vendor/7zip/7z.exe` path
  - standard Windows 7-Zip install directories
  - Windows uninstall registry entries
  - `PATH`
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
- Mark-of-the-Web propagation (see [`docs/SECURITY.md`](docs/SECURITY.md)).
- Bundled 7-Zip binary.
- Installer / signed release artifacts.

## Tech Stack

- Python 3.11+
- Standard-library CLI and test tooling
- 7-Zip CLI backend (`7z.exe` or `7zz.exe`)
- Optional GUI stack: PySide6

## Requirements

- Windows.
- Python 3.11 or newer.
- 7-Zip installed, or a standalone `7z.exe` / `7zz.exe`.

The prototype can find 7-Zip from common install locations and Windows registry entries. If discovery fails, pass the backend path manually.

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

Choose how existing files are handled:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip extract "archive.zip" --output "output-dir" --overwrite-policy skip
python -m ductzip extract "archive.zip" --output "output-dir" --overwrite-policy overwrite
python -m ductzip extract "archive.zip" --output "output-dir" --overwrite-policy rename
```

The default policy is `skip`.

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

The default conflict strategy is `merge`.

Extract several archives into one shared output root:

```powershell
$env:PYTHONPATH = "src"
python -m ductzip batch-extract "photos.zip" "docs.7z" "old.rar" --output "extracted"
python -m ductzip batch-extract *.zip --output "extracted" --retries 2 --verbose
```

`batch-extract` runs the archives strictly in the order given, one at a time. Each task reports `[完成]` (completed), `[失败]` (failed), or `[取消]` (cancelled), and the command exits with 0 when everything completed, 1 when at least one task failed, 130 when cancelled with Ctrl+C, and 2 on a usage error. `--retries N` re-runs failed tasks up to N times; Smart output and conflict strategies work per task.

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
- v0.7: settings, security hardening, and privacy documentation (packaging in progress).

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the detailed plan.

## Project Docs

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`docs/PRD.md`](docs/PRD.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md)
- [`docs/MARKET_RESEARCH.md`](docs/MARKET_RESEARCH.md)

## License

DuctZip is released under the MIT License. See [`LICENSE`](LICENSE).

The current repository does not bundle 7-Zip binaries. If a future release includes 7-Zip, the repository should add `THIRD_PARTY_NOTICES.md` and include the required 7-Zip license notices.
