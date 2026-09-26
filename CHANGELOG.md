# Changelog

All notable changes to DuctZip are documented here. Versions follow the roadmap milestones; this release candidate is unsigned (no code-signing certificate) — see the release notes.

## [1.0.0rc1] - 2026-09-26 (RC closure)

Independent pre-release review fixes on top of the 2026-09-19 candidate; 253 tests pass (three consecutive full-suite runs).

### Fixed

- **Intermittent native crash when a GUI extraction/batch window closes while the worker thread is finishing** (access violation / heap corruption / hard abort). `QThread.finished` fires before the OS thread has fully exited; the old teardown dropped the last Python reference to the worker — destroying its C++ object from the main thread while the worker thread was still in its exit window. `MainWindow.on_worker_finished` / `on_batch_thread_finished` now hold the wrapper references until the OS thread is confirmed dead (`QThread.wait`), and the racy `finished → deleteLater` self-deletion chains were removed. Two new deterministic regression tests assert the teardown invariant.
- **MOTW propagation no longer tags pre-existing files.** Extracting into a directory that already contains files (merge-conflict scenarios) previously copied the archive's `Zone.Identifier` onto those local files, mislabeling them as downloaded. The service now snapshots files present before the engine runs and the propagation pass skips them; only files the extraction produced are tagged, matching `docs/SECURITY.md`.

### Changed

- Portable packaging: the zip now ships `USER_MANUAL.md` and the release notes for the packaged version at the package root (previously the release notes pointed at a `docs/USER_MANUAL.md` path that did not exist inside the package), and `build-manifest.json` records honest provenance — `git_dirty` plus a `worktree_diff_sha256` digest over `git diff HEAD` — so a build from a modified worktree is identifiable instead of masquerading as a pure-HEAD artifact. The build fails when the user manual or the version-matched release notes are missing.
- Release notes: removed a developer-machine absolute path from the acceptance-evidence section.
- GUI tests: all GUI test modules now import the throwaway-settings harness so standalone runs never touch the real user settings.

## [1.0.0rc1] - 2026-09-19

v0.7 settings/security/privacy pass, v0.6 Windows integration, v0.5 batch workflows, and v0.4.1 stabilization: cancellation responsiveness, subprocess lifecycle, GUI thread-safety, and safety-boundary hardening. 247 tests pass at the 2026-09-19 baseline (253 after the 2026-09-26 RC-closure regressions below).

### Added

- **Bundled 7-Zip backend.** The repository and the portable build now ship the official 7-Zip console backend (`vendor/7zip/7z.exe` + `7z.dll` + `License.txt`, 7-Zip 26.03 x64, build date 2026-09-03), so extraction works on a machine with no 7-Zip installed and the whole test suite runs against a pinned backend version (26.03 fixes CVE-2026-14266). Discovery order is unchanged and the bundled copy never overrides the user: explicit `--sevenzip` > `DUCTZIP_7Z_PATH` > `vendor/7zip/7z.exe` > install directories > registry > `PATH`; a system installation is still used when no bundled copy exists. `tests/test_discovery.py` (6 tests) pins that contract.
  - Supply-chain note recorded honestly: upstream 7-Zip does **not** Authenticode-sign its Windows binaries (the PE certificate table of the installer and of an installed 24.08 build are both empty), so the bundled files carry no publisher signature. Approval condition §10.2 #3 was amended by the user on 2026-09-19 to a substitute chain — TLS transport, the `sha256:0859c524…e6edd` digest published in the upstream `ip7z/7zip` 26.03 release metadata, a matching local measurement, and payload self-identification as 26.03. The residual limitation is stated in `THIRD_PARTY_NOTICES.md`, `docs/SECURITY.md`, `PORTABLE.txt`, and DD-008's amendment; users who require a signed backend can point `--sevenzip`/`DUCTZIP_7Z_PATH` at their own copy.
  - `scripts/build_portable.py` now **enforces** the recorded digests: it refuses to package a `vendor/7zip` whose contents are missing or do not match the pinned SHA-256 values, so a swapped or corrupted backend cannot ship silently. `build-manifest.json` gained a `bundled_7zip_backend` record (version, upstream source URL, installer digest) and no longer records build-host absolute paths.
- Repeatable portable packaging: `python scripts/build_portable.py` produces `dist/DuctZip-<version>-portable.zip` (runtime sources, launchers, bundled backend, README/LICENSE/CHANGELOG/notices) plus a `.sha256` checksum and `build-manifest.json` recording Python/platform/git-commit inputs and per-file digests. The build never downloads anything: the bundled backend is taken from the tracked `vendor/7zip` folder, never fetched.
- Portable launchers (`ductzip.cmd`, `DuctZip GUI.cmd`) that set `PYTHONPATH`/`DUCTZIP_SETTINGS_PATH` beside the package and advertise `DUCTZIP_PORTABLE_ROOT`.
- Portable-aware Explorer registration: `ductzip shell register` launched from a portable copy records the portable `.cmd` launchers (verbs get `"<ductzip.cmd>" shell <verb> "%1"`; the GUI open command passes the archive only), so context-menu invocations work without a pip install. New `--launcher` option records an explicit launcher; verb/open command builders now derive the module selector from the launcher kind. New tests cover both launcher forms, portable env detection, and CLI passthrough.
- Mark-of-the-Web propagation (DD-018): after a successful extraction, the archive's `Zone.Identifier` NTFS ADS is copied verbatim onto every extracted file (directories and reparse points excluded), so Windows keeps treating extracted content as coming from the archive's source zone. Best-effort by design: non-Windows/non-NTFS/no-MOTW archives are silent no-ops, and per-file ADS write failures never fail the extraction (collected on `MotwReport.failures` / `ExtractionService.last_motw_report`). Applies to CLI, GUI, and batch through the shared `ExtractionService`. 10 new tests cover ADS round-trips, recursive propagation, failure isolation, reparse skipping, and real-backend end-to-end propagation.

- Per-user settings (`ductzip settings` and a GUI Settings dialog, same model):
  - `ductzip settings show/set/unset` for `sevenzip_path`, `overwrite_policy`, `conflict_strategy`, `smart_output`. Precedence: explicit CLI flag > setting > built-in default, so loading settings never silently changes CLI behavior.
  - Storage at `%APPDATA%\DuctZip\settings.json` (override with `DUCTZIP_SETTINGS_PATH`); atomic saves; corrupt files are backed up as `settings.json.corrupt` and reset to defaults so startup never hangs on bad input.
  - A configured backend path is validated when written and falls back to normal discovery if it later goes stale.
- Adversarial security regression suite (12 tests): a 40+-case path-validation matrix (traversal with either separator, dot/empty segments, absolute/drive-relative/UNC/`\\?\` paths, reserved device names with extensions/case/trailing dots), batch validation with one bad entry, backslash-traversal archives blocked end-to-end, malformed archives (garbage bytes, truncated zip, empty file) mapped to stable errors, preset/mid-run cancellation races, and CLI wrong-password output proven free of the password.
- `docs/SECURITY.md`: what DuctZip reads, writes, executes, and logs; password handling; the local-only (no network/telemetry) commitment; the implemented MOTW propagation behaviour and its boundaries (DD-018); the bundled-backend supply-chain limitation; and known unsupported boundaries (links/reparse points, TOCTOU, listing-size limits).

### Added

- Reversible current-user Windows Explorer integration (`ductzip shell`):
  - `ductzip shell register` / `unregister` / `status`: idempotent HKCU registration, scoped and exactly reversible; no elevation, no HKLM, no native shell extension.
  - Context-menu verbs for `.zip .7z .rar .tar .gz .bz2 .xz .zst`: 「用 DuctZip 解压到当前目录」(extract-here) and 「用 DuctZip 解压到同名文件夹」(extract-to), plus an Open-with (OpenWithProgids) entry that never hijacks the default program.
  - Stable invocation protocol `"<launcher>" -m ductzip shell <verb> "%1"` with quoted Unicode path handling; verbs also accept multiple archives per invocation and the standard batch options (`--password`, `--overwrite-policy`, `--conflict-strategy`, `--retries`, `--sevenzip`, `--verbose`).
  - Stale-launcher detection via `shell status`; re-running `register` repairs the recorded path.
  - `docs/WINDOWS_INTEGRATION.md` documents scope, registry layout, protocol, and known limitations (Windows 11 classic-verb location, per-file Explorer invocation, multi-suffix coverage).
- New `ductzip batch-extract` CLI command: extract multiple archives into one shared output root with a single invocation. Per-task `[完成]/[失败]/[取消]` reporting and a Chinese summary on stderr; exit codes 0 (all completed), 1 (some failed), 130 (cancelled via Ctrl+C or Ctrl+Break, which cancels the whole queue), 2 (usage error). `--retries N` re-runs failed tasks up to N times; `--verbose` streams per-task progress.
- GUI batch queue: drop multiple archives (or add via file dialog) to populate a queue list with per-task status, progress percentage, error, and final output directory; start, retry failed/cancelled tasks, remove tasks where legal (running/planning tasks are refused and the refusal is logged), cancel current task, cancel all; double-click a completed task to open its final output folder. Batch runs on a background thread with the window staying responsive; window close during a batch cancels and reaps it within a bounded time.
- New `ductzip.gui.workers.BatchWorker`: re-emits every `BatchEvent` from the queue runner to the window; cancellation calls straight into the queue (thread-safe) because the worker thread has no event loop while `run()` executes.
- 17 new tests: 8 CLI batch tests (mixed success/failure exit code, CLI order with real backend, retry recovers a flaky backend, per-task Smart Output final dirs with real backend, missing backend, usage error, Ctrl+C → 130) and 9 GUI batch tests (queue population via drag-drop signal, non-file skip, completion with final dirs visible, mixed failure isolation, retry via GUI, bounded cancel-all with thread reaping, remove legality, open-output double-click, bounded close-during-batch).
- New `ductzip.core.queue` module (v0.5 batch core):
  - `BatchQueue`: deterministic sequential runner over `ExtractionService` (concurrency = 1, strict enqueue order, one service operation per archive).
  - `BatchTask`: per-archive request + state (`queued`/`planning`/`running`/`completed`/`failed`/`cancelled`), attempts, per-task result (`final_output_dir`) and normalized error.
  - Legal-transition enforcement with `IllegalTaskTransition`; `completed` is terminal, `failed`/`cancelled` can be retried or removed, active tasks cannot be removed.
  - `cancel_current()` cancels the in-flight task only; `cancel_all()` cancels in-flight and queued tasks immediately.
  - Structured batch log: state changes and batch start/finish persist in `BatchQueue.log`; progress events are yielded live but never persisted.
  - Password redaction: task passwords are stripped from persisted errors/messages and from raw backend `failed` output before re-yield.
- 20 new queue tests: transition legality, sequential ordering without overlap, one-task failure isolation, retry (failed and cancelled), cancel-current/cancel-all semantics, removal mid-run, external cancel events, per-task Smart Output against a shared queue root, no-caller-listing guarantee, redaction, and structured logs.
- Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `CONIN$`, `CONOUT$`, `COM1-9`, `LPT1-9`, including forms with extensions such as `NUL.txt`) are rejected by the engine's pre-extraction path validation, in addition to absolute paths, drive-relative paths, `..` traversal, and UNC/`\\?\` prefixes.
- `cancel_event` parameter for `SevenZipCliEngine.list` / `test` and for `ExtractionService.plan`: the planning phase (backend listing) can now be cancelled without waiting for the backend to finish.
- New `ductzip.gui.workers` module: `ExtractWorker` and `PreviewWorker` QObjects, split from the window code so their lifecycle (thread affinity, signals, cancellation) is unit-testable without constructing widgets.
- Generation-token stale-result discarding for asynchronous GUI previews: a listing that completes after the user switched archives (or edited the password) is never applied to the current state.

### Changed

- Cancelling a running extraction is now responsive even when the backend produces no output: output streams are drained by a dedicated reader thread, and on cancel the process is terminated (terminate -> wait -> kill -> wait) and reaped within seconds instead of blocking until the backend exits on its own.
- All engine subprocess paths (normal completion, failure, cancellation, abandoned generators) deterministically reap the child process; no orphaned 7-Zip processes remain after cancel.
- Cancellation is reported exactly once: the worker emits a single `cancelled` signal whether the engine signals it via the `cancelled` event, the `ArchiveCancelled` exception, or both.
- Unexpected (non-archive-domain) exceptions in GUI workers are surfaced through the `failed` signal instead of silently killing the background thread.
- GUI archive preview now runs on a single long-lived worker thread (queued-request signal pattern) instead of per-preview threads, fixing intermittent heap corruption from thread churn. Window shutdown bounds preview-thread stop at 2s and extraction-thread stop at 10s with event pumping, so queued cross-thread signal delivery cannot deadlock the close path.
- Changing or clearing the archive path in the GUI immediately clears preview rows, the final-output preview, the conflict summary, and the previous extraction's open-folder state; results that arrive late are discarded as stale.
- GUI unit tests use stub engines for determinism (real-backend GUI coverage is manual smoke evidence): antivirus scanning of real 7-Zip child processes makes backend timings wildly nondeterministic (0.27s-15s+ for one listing). Real-backend coverage stays in the CLI and engine-lifecycle suites.

### Fixed

- Cancelling a silent extraction (backend producing no output) could block for ~15s while closing pipes still held open by a surviving grandchild process; stream closing is now owned exclusively by the reader thread, which never blocks the caller.
- `communicate()`-style draining after terminate could block the same way; the cancellable `_run` path now closes the pipes directly on cancel.
- Window close during an extraction could deadlock (queued `quit` delivery never processed while the main thread blocked in `wait()`) or crash with `RuntimeError` on a deleted QThread wrapper; both are handled with an event-pumping bounded wait.
- The backend could take over the console to ask for a password. With no password argument 7-Zip prints `Enter password (will not be echoed):` and reads stdin, so an interactive run appeared to hang and a non-interactive one died with `Break signaled` — reported to the user as "压缩包可能已损坏或格式不受支持". Every backend invocation now passes a password switch (empty `-p` means "empty password, do not ask") and runs with `stdin=DEVNULL`, so the prompt is both unnecessary and unreachable.
- "Password required" and "wrong password" were indistinguishable (and the first was unreachable): an encrypted archive with no password given is now reported as `该压缩包需要密码。` rather than a corruption message, while a supplied-but-wrong password still reports `密码错误。`. `_map_sevenzip_error` takes `password_supplied` from the caller, which is the only party that knows.
- Ctrl+Break killed the process outright instead of cancelling. A plain Python process installs no `CTRL_BREAK_EVENT` handler, so the console default applied: exit `0xC000013A` instead of the documented 130, no message, and the backend left running. `ductzip.cli` now installs a `SIGBREAK` handler for the duration of a command (restored afterwards) and every command reports an interrupt as `已取消：正在停止...` with exit code 130.
- A single-archive `extract` interrupted by the user had no cancellation handling at all; it now returns 130 like the batch path.
- Listing a large archive could hang forever on the cancellable path (GUI preview, batch planning, and any `cancel_event` caller). `_run` polled the child for exit and only read its pipes after it exited, so a listing bigger than the OS pipe buffer deadlocked: the backend blocked in `write()` and never exited, while DuctZip waited for it to exit. The loop now drains through `communicate(timeout=…)`, which reads both pipes concurrently with the wait; cancellation still terminates and closes the pipes directly, without draining. Found by the §7.4 GUI acceptance run against a 300 MB / 1200-entry archive; `tests/test_engine_lifecycle.py::CancellableListingDrainTests` reproduces it with a backend that emits a 145 KiB listing (fails by deadlocking before the fix, 2 tests).

- Command output depended on the machine's console code page. Python encodes *redirected* streams with the ANSI code page (cp936 on a Chinese install, cp1252 on an English one), so on an English Windows `ductzip list` died with an unhandled `UnicodeEncodeError` instead of printing the listing, and Chinese diagnostics reached a redirected file as mojibake. `ductzip.cli.main` now fixes stdout/stderr to UTF-8 with replacement error handlers before dispatch; attached to a real console nothing changes, because Python already writes through the wide console API there. Found by the §7.3 CLI acceptance run; `tests/test_cli.py::ConsoleEncodingTests` reproduces it by running the CLI out of process under `PYTHONIOENCODING=cp1252` (2 tests).

## [v0.4.1] - 2026-09-14

Smart Output Semantics.

### Added

- New `ductzip.core.smart_output` module:
  - `SmartOutputPolicy`: side-effect-free computation of the final extraction directory.
  - `archive_logical_name`: strips common archive extensions, including multi-suffix formats (`tar.gz`, `tgz`, `tar.bz2`, ...) and volume naming (`.7z.001`, `.partNN.rar`). Name derivation only; no first-volume/missing-volume diagnostics.
  - Top-level conflict detection and overwrite-policy derivation shared by all frontends.
- New `ductzip.core.extraction` module:
  - `ExtractionService`: single orchestration entry (list -> policy -> conflict handling -> engine extract) used by both the CLI and the GUI, designed for per-task reuse by a future batch queue.
  - `ExtractionPlan`: the resolved final output directory, conflicts, and effective overwrite policy.
- New tests: policy semantics, logical-name derivation (including Chinese and space-containing names), orchestration (smart toggle, merge/rename/cancel, controlled listing reuse), CLI smart output, GUI final-output preview, and path-traversal safety under Smart mode.

### Changed

- Formalized Smart Output semantics:
  - Empty listing or a single top-level regular file extracts to the requested output directory.
  - A single top-level directory extracts to the requested output directory, or to its parent when the requested folder has the same name (case-insensitive), avoiding `D/D`.
  - Multiple top-level entries extract to `requested_output/archive_logical_name`, unless the requested output already has that name (case-insensitive), avoiding `name/name`.
- `SevenZipCliEngine.extract` / `extract_with_progress` no longer accept `smart_output` or `conflict_strategy`. The engine keeps ownership of 7-Zip list/test/extract, progress events, error mapping, and path traversal validation.
- `SevenZipCliEngine.extract` / `extract_with_progress` also no longer accept a caller-provided `listing`: before every real extraction the engine takes its own fresh listing of the target archive and validates those entries, so a forged safe listing cannot bypass path traversal protection. `ExtractionService` may still list once up front for Smart output / conflict planning, at the cost of one duplicate `list` call.
- Top-level name grouping is case-insensitive (Windows path semantics): `Folder/a.txt` and `folder/b.txt` count as one top-level directory, and conflict prompts keep a stable original display name.
- CLI and GUI both call the shared `ExtractionService` and `SmartOutputPolicy`.
- All Smart output and conflict-policy helpers are imported from `ductzip.core` only; the `archive` package no longer re-exports them, removing the `archive -> core -> archive` cycle (no compat shim, since the v0.4 Smart API was never released).
- GUI: selecting an archive defaults the output directory to the archive's parent folder; the Final output field shows the policy result; Smart output remains enabled by default.

## [v0.4.0] - 2026-07

Smart Extraction and conflict strategies.

### Added

- `--smart-output` CLI flag and GUI Smart output toggle to avoid duplicate top-level folders.
- Top-level output conflict detection with `merge` / `rename` / `cancel` strategies (`--conflict-strategy`, default `merge`).
- GUI final-output preview and conflict summary.

## [v0.3.0] - 2026-07

PySide6 GUI prototype.

### Added

- Archive selection, drag-and-drop, output directory selection, archive preview, password input, progress bar, cancellation, and open-output-folder action.

## [v0.2.0] - 2026-07

Reusable extraction core.

### Added

- `ductzip list` / `ductzip test` commands.
- Progress events, cancellation, password handling, error normalization, and path traversal protection.
- Overwrite policies: `skip` (default), `overwrite`, `rename`.

## [v0.1.0] - 2026-07

Initial CLI prototype.

### Added

- `ductzip extract <archive> --output <dir>` with 7-Zip backend discovery (explicit path, `DUCTZIP_7Z_PATH`, standard install locations, Windows uninstall registry, `PATH`) and `ductzip doctor`.
