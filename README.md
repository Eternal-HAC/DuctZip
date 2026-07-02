# DuctZip

DuctZip is a lightweight Windows archive extraction tool. The current version is a v0.2 CLI and archive-core prototype focused on reliably finding a local 7-Zip backend, inspecting archives, extracting files, and returning clear user-facing results.

The project is intentionally scoped as an engineering prototype for a future desktop extractor. It documents product research, architecture, roadmap decisions, and test coverage so the repository can be reviewed as a maintainable open-source project rather than a one-off script.

## Features

- `ductzip extract` command for extracting an archive into a target directory.
- `ductzip list` command for listing archive entries.
- `ductzip test` command for archive integrity checks.
- `ductzip doctor` command for checking whether a usable 7-Zip backend is available.
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
- Path traversal entries are blocked before extraction.
- Extraction can emit structured lifecycle and progress events for future GUI use.
- Extraction can be cancelled through a core-layer cancellation signal for future GUI use.
- Existing files are handled through explicit overwrite policies: `skip`, `overwrite`, or `rename`.
- Basic error mapping for missing archives, missing 7-Zip, corrupted archives, unsupported formats, password errors, and permission errors.

## Not Yet Implemented

- GUI.
- Compression.
- Batch extraction.
- Smart Extraction.
- Windows context menu.
- Bundled 7-Zip binary.

## Tech Stack

- Python 3.11+
- Standard-library CLI and test tooling
- 7-Zip CLI backend (`7z.exe` or `7zz.exe`)
- Planned GUI stack: PySide6

## Requirements

- Windows.
- Python 3.11 or newer.
- 7-Zip installed, or a standalone `7z.exe` / `7zz.exe`.

The prototype can find 7-Zip from common install locations and Windows registry entries. If discovery fails, pass the backend path manually.

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

## Project Highlights

- Clear separation between the CLI layer and the archive backend.
- Replaceable backend design centered on `SevenZipCliEngine`.
- Windows-first backend discovery, including registry-based 7-Zip lookup.
- Testable command-line workflow before adding GUI complexity.
- Product and architecture documentation maintained in `docs/`.
- Explicit roadmap for Smart Extraction, progress reporting, path safety, GUI, and Windows integration.

## Roadmap

- v0.1: CLI prototype with backend discovery and basic extraction.
- v0.2: reusable extraction core with listing, testing, progress, cancellation, password handling, and path traversal protection.
- v0.3: PySide6 GUI prototype.
- v0.4: Smart Extraction.
- v0.5: batch extraction.
- v0.6: Windows Explorer integration.
- v0.7+: packaging, security hardening, and release readiness.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the detailed plan.

## Project Docs

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
- [`docs/PRD.md`](docs/PRD.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md)
- [`docs/MARKET_RESEARCH.md`](docs/MARKET_RESEARCH.md)

## License

DuctZip is released under the MIT License. See [`LICENSE`](LICENSE).

The current repository does not bundle 7-Zip binaries. If a future release includes 7-Zip, the repository should add `THIRD_PARTY_NOTICES.md` and include the required 7-Zip license notices.
