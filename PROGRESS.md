# PROGRESS.md — DuctZip Long-Task Recovery Ledger

Recovery ledger per `LONG_TASK.md` §11. Not a marketing status document.

## Phase 4: v0.6 Windows integration — IN PROGRESS

**Timestamp:** 2026-09-19
**Blocking decision RESOLVED (user, 2026-09-19):** LONG_TASK.md §10.2 item 4 — **HKCU current-user registration**, no elevation required.

**Other §10.2 decisions resolved (user, 2026-09-19):**

- #1 Local checkpoint commits: **ALLOWED** (no push/tag/release).
- #2 v1.0 delivery format: **portable zip**.
- #3 7-Zip redistribution: **bundle official standalone backend, but only after presenting exact source/version/checksum/license for explicit approval — no download before approval**.

**Still pending (will block Phases 5-7):** #5 MOTW policy, #6 code signing, #7 RAR fixture, #8 release floor.

**Phase 4 plan:** CLI invocation protocol for one/multiple selected archives → HKCU register/unregister module (idempotent, scoped, reversible; approved verbs: context-menu 解压到当前目录 / 解压到同名文件夹; approved associations per user confirmation at implementation time if ambiguous) → integration tests on disposable registry keys → docs.

## Phase 3: v0.5 batch CLI + GUI workflows — DONE

**Timestamp:** 2026-09-19
**Scope:** `batch-extract` CLI command, GUI batch queue workflow (LONG_TASK.md Phase 3).

### What changed (code)

- `src/ductzip/cli.py`: `batch-extract` subcommand (multiple archives, one shared `-o` root, `--password/--password-prompt`, `--overwrite-policy`, `--conflict-strategy`, `--no-smart-output`, `--retries N`, `--verbose`). Exit codes: 0 all completed, 1 some failed, 130 cancelled (Ctrl+C → `cancel_all()` then generator `close()` reaps the engine), 2 usage error (e.g. negative `--retries`). Per-task `[完成]/[失败]/[取消]` lines + summary on stderr.
- `src/ductzip/gui/workers.py`: `BatchWorker` (re-emits every `BatchEvent`; direct-call `cancel_current()`/`cancel_all()` — queued cancels would deadlock since the worker thread has no event loop while `run()` executes). `run()`'s `finally` calls `QThread.currentThread().quit()` directly: a queued `finished → quit` delivery can deadlock when the pump is `QTest.qWait` (batch thread stuck in C++ `exec()` with empty Python stack; main thread blocked inside qWait's event processing).
- `src/ductzip/gui/app.py`: drop-many / add-button queue population (shared output root = output field or archive parent), queue list with per-task status/progress/error labels, start/retry/remove/cancel-current/cancel-all buttons with legality-sensitive enablement, double-click opens a completed task's final dir via `QDesktopServices`, batch thread lifecycle (start on demand, `on_batch_thread_finished` cleanup), closeEvent extended: batch shutdown (cancel_all → bounded `_wait_for_thread` pump) before the extraction-worker path.
- NEW `tests/test_cli.py::BatchCliTests` (8 tests): mixed exit 1, CLI order with real backend, retry recovers flaky backend, no-retry failure, per-task smart-output final dirs with real backend, missing backend → 1, negative retries → 2, Ctrl+C → 130.
- NEW `tests/test_gui_batch.py` (9 tests, offscreen + stub engines): filesDropped/add wiring, non-file skip, run to completion with final dirs visible, mixed success/failure isolation, flaky retry via GUI button, cancel-all bounded + thread reaped, remove legality (queued ok / running refused + logged), double-click opens folder, close-during-batch bounded shutdown.

### Gate results (this machine, 2026-09-19)

1. `python -m unittest discover -s tests` (`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`): **144 tests, 0 failures, 0 skips — OK** (26.8s). Was 127 before Phase 3.
2. Manual batch CLI smoke with real 7-Zip, Chinese + spaced archive names and output root (`照片 档案.zip`, `文档 archive.zip`, `-o '输出 out'`): both completed, exit 0, correct final dirs, content verified.

### Documentation reconciliation (same phase)

- `CHANGELOG.md`, `PROJECT_STATUS.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `README.md`: Phase 3 entries (see git diff; no commits per §10.2).
- `docs/DESIGN_DECISIONS.md`: DD-014 (batch worker thread teardown: direct `quit()` from `run()` finally; avoid queued finished→quit under qWait pumps).

### Gate status

Phase 3 gate: **PASS** — batch CLI acceptance covers mixed success/failure, retry, cancellation, ordering, per-task final directories (automated + real-backend smoke with Chinese/spaced paths); GUI covers multi-add/drag-drop, queue list, per-task status/progress/error, retry, remove-where-legal, cancel current/all, final output visibility, responsive shutdown.

## Phase 2: v0.5 batch domain model and queue core — DONE

**Timestamp:** 2026-09-19
**Scope:** `ductzip.core.queue` — deterministic sequential batch queue (LONG_TASK.md Phase 2).

### What changed (code)

- NEW `src/ductzip/core/queue.py`:
  - `BatchQueue` over one `ExtractionService`; concurrency 1; strict enqueue order; one service operation per archive; `run()` is a deterministic plain generator (no threads in core).
  - `BatchTask` states queued/planning/running/completed/failed/cancelled with legal-transition table; `completed` terminal; `failed`/`cancelled` retryable/removable; active tasks not removable (`IllegalTaskTransition`).
  - `cancel_current()` (in-flight only), `cancel_all()` (in-flight + immediate queued cancellation), external `cancel_event` support; mid-run removal of queued tasks is skipped safely.
  - Structured batch log: state changes + batch start/finish persisted in `BatchQueue.log`; progress yielded but not persisted. Password redaction on persisted messages, task errors, and raw backend `failed` output.
  - Queue-level output root decision: each task carries its own `requested_output_dir`; a shared root is just the same Path given to multiple tasks; Smart Output/conflict policy stay in the service, computed per task. Queue never accepts caller listings and never validates paths (engine remains sole authority).
- `src/ductzip/core/__init__.py`: exports queue API.
- NEW `tests/test_batch_queue.py` (20 tests, all deterministic with scripted service/engine stubs): transition legality, sequential non-overlapping ordering, failure isolation (incl. planning-phase and unexpected exceptions), retry semantics, cancel-current/cancel-all/external-cancel, mid-run removal, per-task Smart Output against a shared root, no-listing API guarantee, redaction, structured logs, final-output visibility.

### Gate results (this machine, 2026-09-19)

1. `python -m unittest discover -s tests` (`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`): **127 tests, 0 failures, 0 skips — OK** (18.1s). Was 107 before Phase 2.
2. `python -m pip wheel . --no-deps`: builds `ductzip-0.4.1-py3-none-any.whl`; wheel contains `ductzip/core/queue.py`.

### Documentation reconciliation (same phase)

- `CHANGELOG.md`: queue core entries under `[Unreleased]` (127 tests).
- `PROJECT_STATUS.md`: phase, completed items, test count 107→127, next-step list updated.
- `docs/DESIGN_DECISIONS.md`: new DD-013 (deterministic sequential runner, policy stays out of the queue).
- `docs/ARCHITECTURE.md`: `queue.py` in landed module layout; `BatchQueue` interface + state machine section.
- `docs/ROADMAP.md`: v0.5 core tasks checked; status line added.

### Gate status

Phase 2 gate: **PASS** — deterministic unit tests prove transition legality, ordering, retry, cancellation, one-task failure isolation, Smart Output per task, and path-validation preservation (engine invoked for every real extraction; queue has no listing parameter).

## Phase 1: v0.4.1 stabilization and reproducibility — DONE

**Timestamp:** 2026-09-19
**Scope:** cancellation responsiveness, subprocess lifecycle, GUI thread-safety, safety boundaries, doc reconciliation (LONG_TASK.md Phase 1).

### What changed (code)

- `src/ductzip/archive/sevenzip.py`:
  - Reader-thread subprocess output drain (`queue.Queue` + None sentinel); reader thread owns stream close (consumer close blocked ~15s on surviving grandchild pipe write ends).
  - `list()`/`test()` accept `cancel_event`; `extract_with_progress` passes it through.
  - `_terminate_process` (terminate→wait(2)→kill→wait(2)) and `_reap_process` on every exit path incl. abandoned generators; `_run` cancel path closes pipes directly instead of `communicate()`.
  - Windows reserved device names (`CON/PRN/AUX/NUL/CONIN$/CONOUT$/COM1-9/LPT1-9`, with extensions) rejected by `_is_safe_archive_path`.
- `src/ductzip/core/extraction.py`: `plan()` accepts `cancel_event` and passes it to the engine listing.
- `src/ductzip/gui/workers.py` (NEW): `ExtractWorker` (exactly-once cancellation; unexpected exceptions → `failed`), `PreviewWorker` (long-lived, generation tokens, silent shutdown cancel).
- `src/ductzip/gui/app.py`: long-lived preview thread via queued `request` signal; generation-guarded result slots; full stale-state clearing on path change; bounded closeEvent (preview 2s / extraction 10s with event pumping; RuntimeError-on-deleted-QThread treated as success; `event.ignore()` if still running).
- New tests: `tests/test_engine_lifecycle.py` (13: silent-backend cancel <6s, reaping, planning cancel, reserved device names with real 7z, archive-mutation boundary), `tests/test_gui_lifecycle.py` (7: stale-state clearing, stale preview discard, single cancellation notification, unexpected-exception surfacing, bounded shutdown); `tests/test_gui.py` preview tests rewritten to stub engines (real-backend GUI = manual smoke evidence; antivirus makes real-backend timings nondeterministic).

### Gate results (this machine, 2026-09-19)

1. `python -m unittest discover -s tests -v` (`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`): **107 tests, 0 failures, 0 skips — OK** (~20s).
2. `python -m pip check`: clean.
3. `python -m pip wheel . --no-deps`: builds `ductzip-0.4.1-py3-none-any.whl`.
4. CLI smoke (real backend, Chinese + spaced paths): doctor/list/test/extract OK; smart output avoids double wrap; `--conflict-strategy cancel` exits 1; missing archive exits 1. (Console mojibake is a GBK capture artifact; extracted filenames verified correct.)
5. Offscreen GUI smoke: 19 GUI tests pass.

### Documentation reconciliation (same phase, per LONG_TASK.md §3)

- `CHANGELOG.md`: new `[Unreleased]` stabilization entry (107 tests).
- `PROJECT_STATUS.md`: date, phase, completed items, safety-boundary notes, test count 84→107.
- `docs/DESIGN_DECISIONS.md`: DD-001/DD-002 marked validated; new DD-010 (reader-thread stream ownership + reap chains + exactly-once cancel), DD-011 (GUI thread model: long-lived preview thread + generation tokens, bounded shutdown, stub engines in GUI unit tests), DD-012 (honest safety boundaries: links/junctions/reparse points unsupported; engine fresh listing authoritative).
- `docs/ARCHITECTURE.md`: actual landed module layout vs aspirational layers; DD-010 process lifecycle; Security section reserved device names + DD-012 boundaries; `plan()` signature with `cancel_event`.
- `docs/ROADMAP.md`: CHANGELOG checkbox checked; v0.4.1 stabilization task recorded.
- `docs/DuctZip_RESUME_FACTS.md`: stale facts fixed (52/44+8-skip → 107 passing; PySide6 now installed and GUI tests run offscreen; v0.4.1 stabilization).
- `README.md`: reserved device names, responsive cancel + deterministic reaping, GUI background preview + stale protection bullets.

### Gate status

Phase 1 gate: **PASS** — all Phase 1 acceptance commands green; docs reconciled.

## Phase 0: Baseline capture and recovery setup — DONE

**Timestamp:** 2026-09-18
**Branch:** `main`, `HEAD` = `a45e8b8 feat: add PySide6 GUI prototype` (= `origin/main`)
**Local commits authorized:** NO — no commits will be created until the user explicitly authorizes them (LONG_TASK.md §10.2 item 1).

### Environment (fresh command output, authoritative)

- Python 3.13.7 (`D:\python\python.exe`)
- PySide6 6.11.2 installed
- 7-Zip backend: `D:\7-Zip\7z.exe`, 7-Zip 24.08 (x64) — machine-specific, rediscover each session
- Windows 11, PowerShell + Git Bash both available

### Git state

- Working tree intentionally dirty (v0.4.1 implementation on top of v0.3 HEAD). **Must not be reset/discarded.**
- Modified tracked (14 files): `PROJECT_STATUS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/DESIGN_DECISIONS.md`, `docs/ROADMAP.md`, `pyproject.toml`, `src/ductzip/__init__.py`, `src/ductzip/archive/__init__.py`, `src/ductzip/archive/errors.py`, `src/ductzip/archive/sevenzip.py`, `src/ductzip/cli.py`, `src/ductzip/gui/app.py`, `tests/test_cli.py`, `tests/test_gui.py`
- Untracked (9 paths): `CHANGELOG.md`, `LONG_TASK.md`, `docs/BANDIZIP_BENCHMARK.md`, `docs/DuctZip_RESUME_FACTS.md`, `src/ductzip/core/` (`__init__.py`, `extraction.py`, `smart_output.py`), `tests/test_extraction_service.py`, `tests/test_smart_extraction.py`
- Staged diff: empty
- Line-ending warnings (LF→CRLF) present on modified files; not normalized, per Phase 0 instruction.

### File classification

All modified/untracked files classified as **baseline project work**. No UNKNOWN files. No generated output or residue detected.

### Ignored local fixture (non-reproducible)

- `tests/让子弹飞（二）.rar` — real RAR fixture, ignored via `.gitignore:14 (*.rar)`. Present locally; a clean clone cannot rely on it. Real-RAR integration coverage must stay a documented conditional external-fixture test unless the user approves a redistributable fixture (§10.2 item 7).

### Baseline command results (this machine, 2026-09-18)

1. `python -m unittest discover -s tests -v` (with `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`): **84 tests, 0 failed, 0 skipped — OK** (15.9s).
2. `python -m pip check`: **No broken requirements found.**
3. `python -m pip wheel . --no-deps --wheel-dir $TEMP/ductzip-wheel`: **Successfully built ductzip** (wheel `ductzip-0.4.1-py3-none-any.whl`).
4. `python -m ductzip doctor`: found `D:\7-Zip\7z.exe`, 7-Zip 24.08 (x64).

### Gate status

Phase 0 gate: **PASS** — baseline suite and wheel commands pass; no pre-existing work lost.

## Decisions / blockers log

- 2026-09-18: Commit permission not yet granted; all work stays uncommitted in the working tree.
- 2026-09-18: RAR fixture policy — keep as documented conditional external-fixture test for now; §10.2 item 7 remains open for user decision.
- 2026-09-19: GUI unit tests use stub engines; real-backend GUI coverage is manual smoke evidence (antivirus scanning of 7z.exe child processes makes real-backend timings nondeterministic, 0.27s–15s+). Recorded in DD-011.
- 2026-09-19: Safety boundary declared (DD-012): links/Junctions/reparse points = unsupported, not guarded; engine fresh listing is the sole safety authority. Never weaken to pass tests.

## Last known-good behavior

127/127 unit tests pass (incl. 20 batch-queue + 13 engine-lifecycle + 7 GUI-lifecycle + 19 GUI tests); wheel builds with `ductzip/core/queue.py`; `doctor` discovers `D:\7-Zip\7z.exe`.

## Next smallest step

Phase 3 (v0.5 CLI + GUI batch workflows, LONG_TASK.md Phase 3): batch CLI contract without breaking single-archive commands; GUI multi-selection/drag-drop, queue list with per-task status/progress/error, retry/remove/cancel-current/cancel-all, final output visibility; keep GUI responsive; ensure passwords/raw backend output stay out of normal logs. Read `src/ductzip/cli.py` and `src/ductzip/gui/app.py` first.
