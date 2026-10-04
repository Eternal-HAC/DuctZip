# PROGRESS.md — DuctZip Long-Task Recovery Ledger

## 2026-10-04 Full-suite hang fix

**Problem**: Running the full suite with `python -m unittest discover -s tests` would hang or time out; individual modules passed.

**Root cause**: The cancellable path in `SevenZipCliEngine._run()` used `process.communicate(timeout=0.05)` in a polling loop. On Windows, when the backend is a `cmd.exe` wrapper script, the reader threads spawned by `communicate()` block cancellation responsiveness while the silent backend holds the pipe write end. This made `tests.test_engine_lifecycle.SilentBackendCancellationTests.test_list_with_cancel_event_raises_and_reaps` take ~15 s (the fake backend ping duration), and several such tests compounded until the suite appeared hung.

**Fix** (`src/ductzip/archive/sevenzip.py`):
1. Replaced the `communicate()` loop with dedicated stdout/stderr reader threads draining into queues; the main loop polls `cancel_event` and `process.poll()` every 10 ms and is no longer blocked by the reader threads.
2. On cancellation the main thread no longer closes the streams itself (which would block if the reader is stuck); it relies on the reader threads to EOF and exit once the process tree is dead.
3. On Windows `_terminate_process()` now runs `taskkill /F /T /PID <pid>` before the graceful `process.terminate()`, killing the whole process tree so grandchildren (e.g. `ping` launched by a `cmd.exe` wrapper) cannot keep the pipes open.
4. `taskkill` is invoked via parameterized `subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], ...)` so the command is explicit, testable, and still outside the mocked backend subprocess paths.

**Regression tests** (`tests/test_engine_lifecycle_regression.py`):
- Added `test_delayed_stdout_after_wrapper_exit_is_captured`
- Added `test_delayed_stderr_after_wrapper_exit_is_captured`
- Added `test_cancel_terminates_grandchild_on_windows`

**Verification**:
- `python -m unittest tests.test_engine_lifecycle -v`: 16 tests, ~9 s, OK.
- `python -m unittest discover -s tests`: **256 tests, OK, exit 0 -- three consecutive runs**.
  Codex independent evidence: 256 tests in 61.414 s, OK.
- `python -m unittest tests.test_password_handling -v`: 9 tests, OK.
- `python -m py_compile src/ductzip/archive/sevenzip.py`: OK.

**Uncommitted changes**: `src/ductzip/archive/sevenzip.py`, `tests/test_engine_lifecycle_regression.py`, `tests/test_password_handling.py`, and the documentation updates. No push/tag/release performed.

**Status**: **CODEX_ACCEPTED**. Codex final safety/result acceptance passed on 2026-10-04.

**Release status**: user authorized publishing on 2026-10-04. The final commit is tagged `v1.0.0rc1`, pushed to `origin/main`, and published as a GitHub pre-release with the portable zip, checksum sidecar, build manifest, and wheel.

**Release rebuild**: the portable package and wheel were rebuilt from a clean committed tree, then exercised from an isolated extraction / clean virtual environment. The final post-documentation rebuild must retain `git_dirty=false` and identify the release commit in `dist/build-manifest.json`.

Recovery ledger per `LONG_TASK.md` §11. Not a marketing status document.

## 2026-09-26 RC closure re-verification (Claude Code) — DONE

Independent pre-release review per `tasks/claude-code/2026-09-26_00-28_ductzip-final-review-and-rc-closure.md`.
Full report with file+line evidence: `docs/FINAL_REVIEW.md` (created before any fix). Raw logs: `.task_logs/`
(`phase3_full_suite_1..3.log`, `phase3_gui_pair_1..20.log`, `phase0_*.log`, `gui_repeat_*.log`,
`single_test_*.log`).

### Findings fixed (all with regression tests that fail on the old implementation)

| ID | Defect | Fix |
| --- | --- | --- |
| P1-1 | GUI teardown race: dropping the worker wrapper while the OS thread is still exiting destroyed the C++ object mid-teardown → intermittent access violation / heap corruption / hard abort (reproduced: 2/30 solo runs, 1/20 module-pair runs, signatures 0xC0000005 & 0xC0000374 & abort; same signature as the unexplained 2026-09-26 first-suite anomalous exit) | `MainWindow.on_worker_finished` / `on_batch_thread_finished` hold references until `QThread.wait()` confirms the OS thread is dead; racy `finished → deleteLater` chains removed; idempotent. Tests: `GuiShutdownTests.test_on_worker_finished_holds_worker_until_os_thread_dead`, `test_on_batch_thread_finished_holds_worker_until_os_thread_dead` |
| P2-4 | MOTW propagation tagged pre-existing files in merge scenarios, mislabeling local content as downloaded | pre-extraction snapshot + `exclude` in `propagate_motw`; only files the extraction produced are tagged. Test: `ServiceMotwIntegrationTests.test_extract_does_not_tag_preexisting_files` |
| P2-1 | portable manifest recorded only `git_commit` — a dirty worktree masqueraded as a pure-HEAD artifact | manifest gains `git_dirty` + `worktree_diff_sha256` (SHA-256 over `git diff HEAD`). Tests: `tests/test_build_portable.py` (3) |
| P2-2 | portable zip lacked `docs/USER_MANUAL.md` (broken reference in the release notes) | package root now ships `USER_MANUAL.md` + version-matched `RELEASE_NOTES.md`; build fails if either is missing; `PORTABLE.txt` updated |
| P2-3 | release notes §6 contained a developer-machine absolute path | rewritten as "仓库根目录" |
| P2-5 | wheel builds are not bit-for-bit reproducible (zip entry timestamps) | wording corrected to "repeatable process"; all recorded hashes regenerated from the final source (below) |
| P3-1 | `BatchQueue.run(external_cancel)` inert during the planning phase | documented as known limitation #9 in the release notes; no caller affected; semantics unchanged |
| P3-2 | three GUI test modules read real user settings on standalone runs | all import `tests.settings_harness` now |

### Re-verification evidence (2026-09-26)

- Full suite (`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1`):
  **253 tests, `OK`, exit 0 — three consecutive runs** (logs `phase3_full_suite_1..3.log`);
  **0 orphan `7z.exe` processes after each run**.
- GUI module pair (`tests.test_gui_lifecycle` + `tests.test_gui_entrypoint`):
  **20 consecutive passes** (logs `phase3_gui_pair_1..20.log`); pre-fix baseline failed at run 11 of 20.
- HKCU: portable smoke `shell register`/`unregister` round trip leaves the `HKCU\Software\DuctZip`
  snapshot **key-identical** (11/11 portable smoke rows PASS).
- Artifacts rebuilt from final source (table below).

| Artifact | Value |
| --- | --- |
| `dist/DuctZip-1.0.0rc1-portable.zip` | 1,200,605 bytes, sha256 `886f3bc74aca2e54d324b58519eaaa065695fda742630973987b56a349dca135` |
| `dist/build-manifest.json` | `git_commit=6d88b09`, **`git_dirty=true`**, `worktree_diff_sha256=d4449a46…65a39`, `python=3.13.7`, `bundled_7zip=true`, 30 files with per-file sha256 (supersedes the Phase 7 manifest caveat) |
| `dist/ductzip-1.0.0rc1-py3-none-any.whl` | 54,393 bytes, sha256 `ced8c72c17a41874327b0c168424275d042728bd3fc730b58ba37e52b680f401` |

- Isolated smokes: portable extraction 11/11 PASS (`C:\tmp\dz_portable_smoke_rc.py`: bundled-backend
  doctor, Chinese+space list/extract round trip, in-package settings, HKCU round trip);
  wheel in a clean venv 8/8 PASS (`C:\tmp\dz_wheel_smoke_rc.py`: both entry points, doctor, list,
  Chinese+space extract round trip, GUI entry without PySide6 → readable message, exit 1).
- `git diff --check` exit 0. No push/tag/release performed; local checkpoint commits recorded below.

Checkpoint: local commit `10cc9e9` on `main` contains the full RC + closure state (33 files);
`.task_logs/` stays untracked as machine-local raw evidence. The artifacts above were built
**before** this commit, hence the manifest's `git_dirty=true`; a release build should be
re-run after committing so the shipped manifest records `git_dirty=false`.

Note: the manifest `worktree_diff_sha256` identifies the tracked diff at build time; the final
commit for release should rebuild so the shipped manifest records `git_dirty=false`.

---

## Phase 7: v1.0 release-candidate closure — DONE (local checkpoint, not pushed)

**Timestamp:** 2026-09-19
**Branch:** `main`, base `HEAD` = `6d88b09` (local checkpoint, not pushed)

### §7.1 Baseline and regression suite — PASS

`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests`

- **247 tests, `OK`, exit 0** (57.3 s on the closing run after the final rebuild and README
  correction; 48.7 s after all Phase 7 code edits; 52.7 s on the first run). Re-run as the
  closing gate after every source and documentation change.
- **0 skips.** There is no skip to justify: the bundled `vendor/7zip` backend makes every
  real-backend test actually run, and the env-provided `tests/让子弹飞（二）.rar` fixture
  (§10.2 #7) is present.
- No network access. The only external process any test starts is the local 7-Zip backend or a
  generated fake one; nothing opens a socket.
- No residue: tests write only into `tempfile.TemporaryDirectory`. `git status --short` is
  identical before and after the run.

Test count trail: 230 (Phase 6) → 243 (Phase 7 first pass) → 245 (engine lifecycle + GUI
entry point regressions) → **247** (console-encoding regressions, §7.3 below).

### §7.2 Packaging and dependency checks — PASS

| Command | Result |
| --- | --- |
| `python -m pip check` | exit 0, `No broken requirements found.` |
| `python -m pip wheel . --no-deps --wheel-dir C:\tmp\dz-wheel` | exit 0 → `ductzip-1.0.0rc1-py3-none-any.whl`, 53,339 bytes, sha256 `1c528ca8…f7af` |
| rebuilt after the README roadmap correction | `dist/ductzip-1.0.0rc1-py3-none-any.whl`, **53,518 bytes**, sha256 `5999558d24beb4bf7f2436a31dcc124f26747708ed48758574a68f826845b4fd`. The wheel embeds `README.md` as its long description, so a README edit changes it; the clean-venv block below was **re-run against this rebuild** (version, `doctor`, `list`, `extract` round trip, GUI entry point, `shell status`) and reproduced its results. **Superseded by the 2026-09-26 rebuild (54,393 bytes, `ced8c72c…f401`) at the top of this file.** |

- Wheel name/version match `pyproject.toml` (`name = "ductzip"`, `version = "1.0.0rc1"`).
- Wheel contents inspected: 25 entries, top level `ductzip/` + `ductzip-1.0.0rc1.dist-info/`
  only. No tests, no `__pycache__`/`.pyc`, no `docs/`, no `dist/`, no fixtures.
- Clean venv (`C:\tmp\dz-venv2`, `python -m venv`) install of that wheel: exit 0, and both
  entry points appear — `Scripts\ductzip.exe`, `Scripts\ductzip-gui.exe`.
  - `ductzip doctor` → exit 0; `ductzip --help` → exit 0.
  - `ductzip-gui` (PySide6 absent) → exit 1 with the actionable message, no traceback.
  - `pip check` inside the venv → exit 0.
  - Real extraction with the installed wheel from a Chinese+spaced archive to a Chinese+spaced
    output directory: exit 0, `list` printed the documented `f<TAB>21<TAB>中文 文件.txt` row,
    content round-tripped.

**Recorded substitutes** (LONG_TASK §7 preamble allows these when the environment requires it):

1. `pip wheel` needs default build isolation, which fetches `setuptools>=68` from PyPI.
   `pypi.org` is unreachable from this machine (TLS `SSLEOFError`), and `--no-build-isolation`
   cannot work because neither the dev interpreter nor a fresh venv has `setuptools`. Substitute:
   `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`. Same wheel, same resolver, mirror host.
2. `rc=$?` after a pipeline reports the *last* command's status, which made `ductzip-gui` look
   like exit 0 on a first attempt. Re-measured with output redirected to files: gui=1, doctor=0,
   `--help`=0, usage error=2.

### §7.3 CLI acceptance — PASS (41/41 rows, transcript in `C:\tmp\s73.log`)

Driver: `python C:\tmp\s73_cli_acceptance.py` (kept outside the repository; it builds its own
fixtures with the bundled backend and drives the real CLI as a subprocess). **41 rows, 0
failures, exit 0.**

| Group | Rows | Result |
| --- | --- | --- |
| A. `doctor` / usage / exit codes (0, 1, 2) | 5 | PASS |
| B. `list` / `test` incl. corrupt, unsupported, missing, RAR | 9 | PASS |
| C. Chinese and spaced paths | 3 | PASS |
| D. Smart Output single vs multi top-level | 2 | PASS |
| E. Conflict strategies merge / rename / cancel | 3 | PASS |
| F. Overwrite policies skip / overwrite / rename | 3 | PASS |
| G. Passwords (required / wrong / correct / test) | 7 | PASS |
| H. Missing backend | 2 | PASS |
| I. Traversal blocked, nothing written outside the boundary | 1 | PASS |
| J. Batch mixed, retry, missing archive | 4 | PASS |
| K. Real Ctrl+Break → 130, backend reaped in 0.77 s | 2 | PASS |

The run was repeated after the engine fix in §7.4 (it touches the cancellable path batch
cancellation uses); the numbers above are the post-fix run.

### Defect fixes from §7.3 (all with regression tests)

1. **Backend could prompt for a password.** With no password argument, 7-Zip prints
   `Enter password (will not be echoed):` and reads the console. DuctZip neither displayed
   nor answered it: interactively the command appeared to hang, non-interactively the
   backend died with `Break signaled` and was reported as "压缩包可能已损坏或格式不受支持".
   Fix: `_password_args` always emits a switch (empty `-p` = "empty password, do not ask"),
   and all three backend process launches pass `stdin=subprocess.DEVNULL`.
2. **"Password required" was unreachable.** Once the empty `-p` suppresses the prompt,
   7-Zip reports the same `Wrong password?` text whether no password was given or the given
   one was wrong. Fix: `_map_sevenzip_error(..., password_supplied=...)`, supplied by the
   caller — `PasswordRequired` ("该压缩包需要密码。") when none was provided, `WrongPassword`
   ("密码错误。") when one was. Raw backend output stays on `.detail`, never in the message.
3. **Ctrl+Break hard-killed DuctZip.** A plain Python process has no `CTRL_BREAK_EVENT`
   handler, so the console default applied: exit `0xC000013A`, no message, backend left
   running. Measured against a control process (`python -c "time.sleep(30)"`) to confirm it
   was a process-wide property, not DuctZip's own handler. Fix: `cli._interruptible()`
   installs `SIGBREAK → default_int_handler` for the duration of a command and restores the
   previous handler; every command now maps an interrupt to "已取消：正在停止..." and exit 130.
   Single-archive `extract` previously had no cancellation handling at all.
4. **Command output depended on the machine's console code page** (found by the §7.3 re-run).
   Python encodes *redirected* streams with the ANSI code page — cp936 here, cp1252 on an
   English install — so `ductzip list` died with an unhandled `UnicodeEncodeError` there
   instead of printing the listing, and Chinese diagnostics reached a redirected file as
   mojibake. Reproduced with `PYTHONIOENCODING=cp1252`: `ductzip test` → traceback, exit 1,
   empty stdout. Fix: `cli._configure_console_output()` fixes stdout/stderr to UTF-8
   (with `replace`/`backslashreplace` handlers) before dispatch; attached to a real console
   nothing changes, because Python already writes through the wide console API there.
   Regression: `tests/test_cli.py::ConsoleEncodingTests` (2 tests) runs the CLI out of process
   under `PYTHONIOENCODING=cp1252` — the only way to see this, since the in-process tests
   capture a `StringIO`, which has no encoding to get wrong. Mutation-checked: with the call
   neutered both tests fail with the original `UnicodeEncodeError`.

New tests across 1–3: `tests/test_password_handling.py` (9), `tests/test_cli.py::CancellationTests` (2).
Both sets were mutation-checked (reverted fix → tests fail) so they are not vacuous.

### Historical limitation found by §7.3 (superseded 2026-10-04)

Cancellation reaps the one backend process DuctZip launched, not the whole descendant tree.
The bundled `7z.exe` spawns no children, so the shipped form leaves nothing behind; but a
user who points `--sevenzip` at a `.cmd` wrapper leaves that wrapper's own child (the real
7-Zip) running after cancel. Measured: the launched wrapper is reaped in 0.77 s, its spawned
grandchild survives. A Job Object (`KILL_ON_JOB_CLOSE`) would close this, but it means
reworking the cancellation/reaping path that §7.4/§7.5 already verify, and no acceptance
criterion requires it. Recorded in `docs/SECURITY.md` under 已知安全边界 and in the release
notes §5.4.

This historical decision was superseded by the 2026-10-04 full-suite hang fix: Windows now
uses parameterized `taskkill /F /T` for best-effort process-tree termination. Non-Windows
platforms still guarantee only the immediate child.

### §7.4 GUI acceptance — PASS (26/26 rows, transcript in `C:\tmp\s74.log`)

Automated offscreen coverage lives in the suite: `tests/test_gui.py`, `test_gui_batch.py`,
`test_gui_lifecycle.py`, `test_gui_settings.py`, `test_gui_entrypoint.py` (constructibility,
state transitions, illegal transitions, bounded close).

Windows UI-automation evidence: `python C:\tmp\s74_gui_acceptance.py` — real Windows, real
bundled 7-Zip backend, offscreen Qt, driving the actual `MainWindow` through the same slots
the widgets are wired to while pumping the event loop. **26 rows, 0 failures.**

| Group | Rows | What the evidence shows |
| --- | --- | --- |
| A. Window state | 1 | title `DuctZip`, Extract enabled / Cancel disabled / Open Folder disabled, password field masked, empty preview |
| B. Preview and stale state | 5 | Chinese+spaced archive → 3 rows; single top-level lands in the requested dir; multi top-level lands in `out_multi\multi`; switching the archive clears rows, entries, open-folder state and conflict summary immediately; clearing the path resets everything |
| C. Real extraction, responsiveness, progress, terminal state | 4 | real extraction to a Chinese+space output dir with a Chinese filename; 9 heartbeats during a 0.30 s extract; 43 heartbeats and 6 distinct progress values on the big archive (1.35 s); log tail `Completed: …` |
| D. Cancel | 2 | cancelled while running, stopped in **63 ms**, 0 leftover backend processes; log says `Cancelled` and Open Folder stays disabled |
| E. Password | 5 | preview after the correct password; wrong password → `密码错误。` with no password in the log; correct password extracts; masked by default and toggled by Show; no password → `该压缩包需要密码。` (not a corruption message) |
| F. Conflicts | 3 | summary `1 existing target(s): photos`; `cancel` fails loudly and leaves the original file untouched; `rename` keeps the original and writes `a_1.txt` |
| G. Batch | 5 | enqueue 2 and enable Start; a running task cannot be removed (illegal transition refused); mixed batch isolates one success and one failure; a completed task opens its output dir; cancel-all stops in **0.02 s** with no leftover backend |
| H. Close while busy | 1 | close during extraction returns in **41 ms** with 0 leftover backend processes |

Two adaptations, recorded as evidence rather than hidden: `QMessageBox` is auto-answered and
its **text captured** (a modal cannot be clicked in a headless harness, and the text is what
the "errors are understandable" criterion is about), and `QDesktopServices.openUrl` is
captured instead of launching Explorer.

Three harness bugs were found and fixed during this run — all in the driver, not the product:
B1 counted 3 preview rows (the zip also lists the `photos` directory entry); B3 expected the
final-output field to be empty right after an archive switch, but the product synchronously
recomputes it from the empty listing and refines it when the preview lands (the row now
asserts immediate *state invalidation* plus a separate row for the derived directory); C1
expected the opened URL to contain `photos` when it is the final output directory. A `pump()`
helper that treated index `0` as falsy and two f-strings that printed a literal `\n` were also
corrected.

### §7.4 GUI acceptance — defect found and fixed

The deadlock below was found by this run, not by any unit test: it is listing-size dependent.

**Listing a large archive could hang forever on the cancellable path** (GUI preview, batch
planning, any `cancel_event` caller). `_run` polled the child for exit and only read its pipes
*after* it exited, so a listing bigger than the OS pipe buffer deadlocked: the backend blocked
in `write()` and never exited, while DuctZip waited for it to exit. Two `7z l -slt -p big.zip`
processes sat for ≥9 minutes; the same archive listed in 0.05 s through the non-cancellable
path, which proves it was the polling loop and not the archive. Reproduced deterministically
with a fake backend emitting a 145 KiB listing. Fix: drain through
`communicate(timeout=0.05)` so both pipes are read concurrently with the wait; cancellation
still terminates the process and closes the pipes directly, without draining (draining can
block on a surviving grandchild holding the pipe's write end). Verified fail-before (32 s
timeout) / pass-after (4.0 s), and
`tests/test_engine_lifecycle.py::CancellableListingDrainTests` (2 tests) pins it — one asserts
a 3000-entry listing completes, one asserts it is still cancellable. Recorded in `CHANGELOG.md`.

Also fixed in this phase: a clean venv running `ductzip-gui` without PySide6 emitted a raw
`ModuleNotFoundError` traceback instead of the required comprehensible error, because the
friendly message in `gui/app.py` was unreachable — an unguarded `from . import workers`
(which imports Qt at module level) ran first. The guard moved to the entry point:
`ductzip.gui.main` (used by both `ductzip-gui` and `python -m ductzip.gui`) converts only a
genuine PySide6 failure into an actionable message — including a native message box when
`pythonw` gives it no console — and re-raises anything else so a real defect keeps its
traceback. New tests: `tests/test_gui_entrypoint.py` (2).

### §7.5 Security acceptance — PASS (mapping to existing evidence)

| Requirement | Evidence |
| --- | --- |
| Engine-level pre-extraction listing and traversal validation stay mandatory even when callers supply a listing | `tests/test_engine_lifecycle.py::ArchiveMutationBoundaryTests` (a forged plan listing changes nothing about what is extracted), `tests/test_extraction_service.py`; the engine takes its own fresh listing before every real extraction |
| Regression tests for relative traversal, absolute/UNC/device-style paths, mixed separators, case behaviour, forged/stale planning data | `tests/test_security.py::PathValidationMatrixTests` (40+-case matrix), `TraversalIntegrationTests` (backslash traversal blocked end-to-end with the real backend), `tests/test_engine_lifecycle.py::WindowsSpecialPathValidationTests` (reserved device names incl. extensions/case/trailing dots), `ArchiveMutationBoundaryTests` |
| Link/Junction/reparse-point behaviour and archive replacement races tested or documented as unsupported with a release decision | reparse points are never followed (MOTW propagation explicitly skips them: `tests/test_motw.py`); links/junctions and TOCTOU are documented as unsupported/not-eliminated in `docs/SECURITY.md` and release notes §5.5–5.6 |
| Extraction never writes outside the approved output boundary in supported scenarios | `tests/test_security.py` traversal cases assert the output directory was not created; §7.3 group I asserts the same end-to-end |
| Logs redact passwords and avoid dumping raw backend output to normal users | `tests/test_password_handling.py` (9, incl. `test_raw_backend_output_never_reaches_the_user_message`), `tests/test_security.py::PasswordNonLeakageTests`; §7.4 rows E1/E3 assert the password never appears in the GUI log |
| No download/update/telemetry/network behaviour added without explicit user approval | the product makes no network call; commitment recorded in `docs/SECURITY.md`; §7.7 audit found no such code |

Suite sizes: `test_security.py` 12, `test_motw.py` 10, `test_password_handling.py` 9,
`test_discovery.py` 6, `test_engine_lifecycle.py` 12.

### §7.6 Windows integration acceptance — PASS

Unit level: `tests/test_shell_integration.py` (16) — only scoped keys written, idempotent
registration, `unregister` removes everything and is safe when already clean, recovery from
partial corruption, `status` reporting a stale launcher and missing verbs, verb/open command
quoting and placeholder protocol for both launcher kinds, and a real-HKCU round trip
(`WinRegistryRoundTripTests::test_register_status_unregister_real_hkcu`).

End-to-end level, on the **extracted portable package** with the real HKCU
(`python C:\tmp\dz_shell_roundtrip.py`, transcript `C:\tmp\dz_shell.log`): **8/8 rows PASS.**

- W1 baseline clean (no DuctZip-owned key anywhere under `Software\Classes`, no app key, no
  `OpenWithProgids` value); W2 `status` says 未注册.
- W3 `register` writes 17 named keys (ProgID + 8 extensions × 2 verbs) and makes DuctZip
  visible in "Open with" for all 8 extensions.
- W4 the recorded extract-here verb is
  `"C:\tmp\dz-psmoke\DuctZip-1.0.0rc1\ductzip.cmd" shell extract-here "%1"` and the ProgID
  open command is `"…\DuctZip GUI.cmd" "%1"` — the portable launchers, with the documented
  protocol, not a module invocation.
- W5 repeated `register` is idempotent: the snapshot is identical except the `RegisteredAt`
  metadata timestamp the code refreshes on purpose (`14:30:02Z` → `14:30:06Z`).
- W6 `status` reports 已注册 and names the launcher.
- **W7 `unregister` is an exact reversal**: the post-unregister snapshot equals the
  pre-registration snapshot key by key, with no `DuctZip*` key left anywhere under
  `Software\Classes` and no residual `OpenWithProgids` value.
- W8 `status` returns to 未注册. The machine is left exactly as it was found.

Three driver assumptions were corrected (all in the harness, not the product): the
`OpenWithProgids` convention is a value *named* for the ProgID with empty data, so presence
is what must be asserted; the `open` verb pointing at the GUI launcher is the documented
design, not a mismatch; and idempotency had to be judged excluding `RegisteredAt`.

### §7.7 Documentation and repository acceptance — PASS

- `git status --short`: **18 modified + 4 untracked**, every one intentional and listed below.
- `git diff --check`: exit 0, no whitespace errors (all output is the CRLF advisory below).
  The 18 `LF will be replaced by CRLF` warnings are a configuration artifact, not hidden by
  conversion: `core.autocrlf=true` with no `.gitattributes`, and every file on disk is
  uniformly LF. Nothing was normalised repo-wide.
- `git diff --stat`: 18 files changed, 858 insertions(+), 125 deletions(-) (the final count, after the README roadmap correction; 853/124 before it).
  `git diff --cached --stat`: empty (nothing staged).
- `git ls-files --others --exclude-standard`: `docs/USER_MANUAL.md`,
  `docs/RELEASE_NOTES_1.0.0rc1.md`, `tests/test_gui_entrypoint.py`,
  `tests/test_password_handling.py`.
- No secrets, credentials, tokens, private fixtures, local absolute paths in tracked
  non-vendor files, or generated build/cache files. The only `password`-shaped strings are
  test fixtures; `C:\tmp\…` paths appear only in driver scripts kept **outside** the repo.
- No unresolved production `TODO`, placeholder behaviour, `NotImplementedError`, or silent
  stub in `src/`.
- Version / test counts / features / limitations / roadmap checkboxes / project status /
  changelog / release notes agree: all read **1.0.0rc1 / 247 tests** at the end of Phase 7
  (2026-09-26 RC closure raised the count to **253**; see the top section).

Files changed or added in Phase 7:

| File | Why |
| --- | --- |
| `src/ductzip/archive/sevenzip.py` | pipe-drain deadlock fix in the cancellable `_run` path |
| `src/ductzip/cli.py` | console encoding fix; Ctrl+Break handler (earlier in phase) |
| `src/ductzip/gui/__init__.py`, `gui/__main__.py` | PySide6 guard moved to the entry point |
| `src/ductzip/gui/app.py` | GUI fixes from earlier in the phase |
| `tests/test_cli.py` | `ConsoleEncodingTests` (2) |
| `tests/test_engine_lifecycle.py` | `CancellableListingDrainTests` (2) |
| `tests/test_gui_entrypoint.py` (new) | missing-PySide6 entry-point behaviour (2) |
| `tests/test_password_handling.py` (new) | password switch never omitted, required vs wrong, no leakage (9) |
| `docs/USER_MANUAL.md` (new) | end-user manual (§7.7 documentation gap) |
| `docs/RELEASE_NOTES_1.0.0rc1.md` (new) | release notes + §7 evidence summary |
| `docs/SECURITY.md`, `docs/ROADMAP.md`, `docs/DuctZip_RESUME_FACTS.md`, `docs/RELEASE_CHECKLIST.md` | same-phase source-of-truth sync |
| `CHANGELOG.md`, `PROJECT_STATUS.md`, `README.md`, `PROGRESS.md` | changelog, status, doc index, this ledger |
| `pyproject.toml` | version `1.0.0rc1` |
| `src/ductzip/__init__.py` | version `1.0.0rc1` |
| `scripts/build_portable.py` | single top-level folder, enforced backend digests |

### §7.8 Static-quality tools — UNKNOWN (not claimed)

The repository configures no formatter, linter, or type checker. Per LONG_TASK §7.8 this
stays **UNKNOWN** and **no lint/typecheck success is claimed anywhere**. Phase 1 introduced
no such tool, so there is nothing to pin or run.

### Release artifacts (this phase, not published)

| Artifact | Value |
| --- | --- |
| `dist/DuctZip-1.0.0rc1-portable.zip` | 1,183,597 bytes, sha256 `90f61d4d8da8e6100e813f674df3c8387fa4acdae935cc75ce2ca89d1f4853fc` (rebuilt after the CLI encoding fix **and** after the README roadmap line was corrected; `.sha256` file agrees with a fresh measurement) — **superseded by the 2026-09-26 rebuild at the top of this file** |
| `dist/build-manifest.json` | regenerated with the same build; records `git_commit=6d88b09`, `python=3.13.7`, `bundled_7zip=true` and the backend's version/upstream URL/installer SHA-256, with no build-host absolute paths. **Caveat recorded:** that commit is the `HEAD` the build ran on, and the Phase 7 changes are still uncommitted, so the manifest does not by itself identify the exact source of this artifact. |
| Portable extraction layout | single top-level `DuctZip-1.0.0rc1\` containing the launchers, `src/`, `vendor/`, and the docs |
| Portable smoke (isolated copy) | **5/5 rows PASS** (transcript `C:\tmp\dz_portable_smoke.py`, **re-run on the final rebuild**): `doctor` resolves the **bundled** backend; Chinese+spaced archive lists and tests via `ductzip.cmd`; extraction into a Chinese+spaced output dir round-trips content; settings are written inside the portable folder |
| Rebuild note | The artifact was rebuilt once more after a **README roadmap line was corrected** (`v0.7 … (packaging in progress)` → v0.7 as shipped plus a `v1.0.0rc1` line), because `README.md` is copied into the portable zip. The registry round trip (§7.6, 8/8) and the GUI-launcher check were **re-run against the re-extracted rebuild** and reproduced their results; a fresh isolated extraction was used, and the fixture the smoke driver expects had to be recreated after that extraction wiped the scratch tree. |

Not done, and deliberately left to the user: **no push, no tag, no GitHub release, no upload.**

### Cleanup

Two stray Python processes were left running by an interrupted acceptance run. Killing them
was denied by the permission classifier twice, so they are reported here rather than
force-killed: **PIDs 2936 and 41524**. They hold no files in the repository and do not affect
any recorded evidence; the user should close them manually.

## Phase 6 (continued): 7-Zip backend bundling — DONE

**Timestamp:** 2026-09-19
**Branch:** `main`, base `HEAD` = `d0a8662` (local checkpoint, not pushed)
**Checkpoint commit:** `6d88b09 feat: bundle 7-Zip 26.03 console backend with enforced digest pinning`
— local only, not pushed. This is the commit Phase 7 was executed on top of.

### Decision revision — §10.2 #3 (user, 2026-09-19)

The approved condition was "verify TLS + Authenticode". **The Authenticode half is
unsatisfiable: upstream 7-Zip does not Authenticode-sign its Windows binaries.** Verified
two independent ways: the PE certificate-table data directory of `7z2603-x64.exe` is all
zeroes (parsed directly from the PE headers), and the locally installed 7-Zip 24.08
`7z.exe` / `7z.dll` also report `NotSigned` with an empty certificate table — so this is an
upstream property, not a local chain/trust-store failure. The official download page
publishes no checksums and no signatures either. No signing evidence was fabricated.

Presented to the user as a §10.2 decision with a substitute verification chain; the user
chose **"接受替代验证并捆绑"** (accept the substitute verification and bundle). DD-008 was
amended to record the revised source (full console backend instead of the 7-Zip Extra
standalone plan) and the revised verification chain.

### Verification chain (all four checks passed)

| Step | Evidence |
| --- | --- |
| 1. TLS | `https://www.7-zip.org/a/7z2603-x64.exe` → `302` → `https://github.com/ip7z/7zip/releases/download/26.03/7z2603-x64.exe` |
| 2. Published digest | `gh api repos/ip7z/7zip/releases/tags/26.03` → `7z2603-x64.exe` `sha256:0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd` |
| 3. Local measurement | `Get-FileHash -Algorithm SHA256` → `0859C524B8A63551848F0C246ABDDCB1D0B7B656B0FBFE879F8D85E61A9E6EDD` (exact match), 1661239 bytes |
| 4. Payload identity | extracted with the machine's independent 7-Zip → `7-Zip 26.03 (x64) : Copyright (c) 1999-2026 Igor Pavlov : 2026-09-03` |

The earlier blocker (302 → unreachable github.com; mirror denied by the permission
classifier) resolved itself when the network recovered on retry; no permission workaround
was used. `7z2603-x64.exe` was fetched through the officially approved entry point.

### What changed

- NEW `vendor/7zip/` — tracked upstream backend: `7z.exe`
  (`6ee3c0ed…c30b2f`), `7z.dll` (`65e4c1f8…71b0d`), `License.txt` (`519ac0a4…7765d`).
- `.gitignore`: `vendor/` → `vendor/*` + `!vendor/7zip/`, so the deliberate bundle is
  tracked while the rest of `vendor/` stays local. (The file's own comment already
  anticipated deliberate, noticed additions.)
- `scripts/build_portable.py`: **pinned digests are now enforced** — `verify_bundled_backend()`
  refuses to package a `vendor/7zip` that is incomplete or whose contents do not match the
  pins, so a swapped/corrupted backend cannot ship silently. Proven by a deliberate
  tamper test (wrong pin → refused; missing file → refused; honest state → passes).
  `local_backend_record()` (which wrote a build-host absolute path into the manifest) was
  replaced by `bundled_backend_record()`, which records only repo-relative facts:
  version, upstream source URL, installer digest. Manifest field
  `discovered_backend_build_input` → `bundled_7zip_backend`.
- Docs: `THIRD_PARTY_NOTICES.md` (full artifact table, verification chain, residual
  limitation, license obligations), `docs/SECURITY.md` (new bundled-backend supply-chain
  section + boundary bullet), `docs/DESIGN_DECISIONS.md` (DD-008 amendment + new review
  conditions), `README.md` (discovery list, "Not Yet Implemented" no longer lists a bundled
  binary, requirements, license section), `packaging/portable/PORTABLE.txt` (requirements +
  backend section), `CHANGELOG.md`, `PROJECT_STATUS.md`, `docs/ROADMAP.md`,
  `docs/RELEASE_CHECKLIST.md` (build-product items now cover the enforced pin).

### Gate results (this machine, 2026-09-19)

1. Full suite (`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`):
   **230 tests, 0 failures — OK** (43.2s). The suite now exercises the bundled 26.03
   backend instead of the system 24.08, since discovery prefers `vendor/7zip`.
2. Bundled backend standalone: `./vendor/7zip/7z.exe` → `7-Zip 26.03 (x64)` (picks up the
   adjacent `7z.dll`).
3. `python scripts/build_portable.py` from scratch → `dist/DuctZip-0.7.0-portable.zip`,
   1176709 bytes, `sha256 a7a2b7f5a572be1ee05e90bf269ff7086855ca7f38f5532bf27cc0f68a57523d`;
   manifest `bundled_7zip: true`, 28 files, `vendor/7zip/*` present with matching digests.
4. Isolated-directory smoke (`C:\tmp\dz-bundled-smoke`, artifact re-extracted, `PYTHONPATH`
   and `DUCTZIP_SETTINGS_PATH` cleared):
   - `doctor` → `C:\tmp\dz-bundled-smoke\vendor\7zip\7z.exe`, 26.03, exit 0.
   - extract of `让子弹飞 (2026).zip` → `解压 输出\让子弹飞 (2026)\…` with `--smart-output`,
     exit 0; tree verified on disk with correct Chinese/spaced names.
   - `doctor --sevenzip "D:\7-Zip\7z.exe"` → reports 24.08, exit 0 — **explicit override
     still wins over the bundled backend**.
   - `shell register` / `status` / `unregister` → exits 0; 26 keys removed.
5. Discovery-order contract pinned by `tests/test_discovery.py` (6 tests): explicit wins and
   raises without fallback; `DUCTZIP_7Z_PATH` beats vendor; vendor beats install dirs;
   install-dir fallback; clean `SevenZipMissing`.

### Still open in Phase 6

- ~~Clean-machine verification~~ — remains a **recorded limitation**, not a gap in this task:
  no second physical machine is available, so under §10.2 #8 the final claim is scoped to the
  evidence actually gathered on this host (release notes §5.3).
- ~~v1.0 version bump~~ — DONE in Phase 7 (`1.0.0rc1`).

---

## Phase 6: v0.7 packaging and distribution — PARTIAL (committed `86f47c3`)

**Timestamp:** 2026-09-19
**Branch:** `main`, `HEAD` = `86f47c3` (local checkpoint, not pushed)
**Gate for §10.2 (all resolved 2026-09-19, see Phase 5 continued):** items #2 portable zip, #6 unsigned RC allowed, #8 recorded-limitation deferrals allowed. **Item #3 7-Zip bundling:
APPROVED 2026-09-19 (user picked "完整控制台后端（推荐）"):** bundle 7z.exe + 7z.dll
extracted from the official installer `7z2603-x64.exe` (7-Zip 26.03, 2026-09-03) downloaded
from https://www.7-zip.org/a/; record measured SHA-256 in the build manifest. RAR support
preserved; DD-008 amended.

> **Superseded 2026-09-19 (same day).** Two statements above were overtaken by execution:
> the installer is *not* Authenticode-signed (upstream 7-Zip does not sign its Windows
> binaries), so "verify TLS + Authenticode" was unsatisfiable and the user approved a
> substitute chain; and this section is no longer merely PARTIAL. See
> "Phase 6 (continued): 7-Zip backend bundling — DONE" at the top of this file for the
> decision record, the four-step verification chain, and the execution evidence.

### Non-prejudicial Phase 6 work completed (2026-09-19)

- NEW `scripts/build_portable.py` (stdlib-only, repeatable, zero downloads):
  `python scripts/build_portable.py` → `dist/DuctZip-0.7.0-portable.zip` (+ `.sha256`,
  `build-manifest.json` with Python/platform/git-commit inputs, bundled_7zip flag,
  per-file SHA-256). Refuses to include `__pycache__`/`.pyc`/`tests`; requires
  LICENSE/README/CHANGELOG/THIRD_PARTY_NOTICES + launchers to exist. Includes
  `vendor/7zip` only if already on disk (never downloads).
- NEW `packaging/portable/`: `ductzip.cmd` (CLI), `DuctZip GUI.cmd` (GUI via pythonw),
  `PORTABLE.txt`. Launchers set `PYTHONPATH`+portable settings path and advertise
  `DUCTZIP_PORTABLE_ROOT`.
- NEW `THIRD_PARTY_NOTICES.md`: 7-Zip bundling honestly marked not-yet-bundled with
  approved policy + license obligations; Python/PySide6 referenced (not distributed).
- Portable-aware Explorer registration (found during clean-copy smoke: registered
  `pythonw.exe -m ductzip ...` could not import the package without a pip install):
  - `shell.build_verb_command` drops the `-m ductzip` selector (launcher carries it);
    new `shell.build_open_command` keeps `-m ductzip.gui` for interpreters, passes the
    archive alone for `.cmd`/`.bat` launchers.
  - `shell.resolve_portable_launchers()` reads `DUCTZIP_PORTABLE_ROOT`; `register()`
    gains `gui_launcher` and auto-picks the portable `.cmd` launchers (explicit
    `launcher=` still wins).
  - CLI: `ductzip shell register --launcher <path>`.
- Tests: +9 (`test_shell_integration` portable env/explicit-launcher/open-command
  forms; `test_cli` `--launcher` passthrough + default None).
- Docs: WINDOWS_INTEGRATION (launcher selection order + new command forms + console
  window note), ROADMAP v0.7 packaging checkbox, CHANGELOG, PROJECT_STATUS, PORTABLE.txt.

### Gate results (this machine, 2026-09-19)

1. Full suite (`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`):
   **224 tests, 0 failures — OK**. Was 215.
2. `pip check` clean; `pip wheel . --no-deps` → `ductzip-0.7.0-py3-none-any.whl`.
3. Portable smoke from isolated dir `C:\tmp\dz-portable-smoke` (env PYTHONPATH unset,
   artifact re-extracted): `doctor` exit 0 (finds `D:\7-Zip\7z.exe`); extract of
   `让子弹飞 (2026).zip` → `解压 输出` with `--smart-output` exit 0; `settings show` exit 0
   (portable settings path beside the app); `shell register`/`status`/`unregister`
   exits 0. `reg query` evidence: verb = `"C:\tmp\dz-portable-smoke\ductzip.cmd" shell
   extract-here "%1"`, open = `"C:\tmp\dz-portable-smoke\DuctZip GUI.cmd" "%1"`.

### ~~Bundling execution — BLOCKED on network/permission~~ — RESOLVED 2026-09-19

**Resolved.** The network recovered on retry and the installer was fetched through the
officially approved entry point; bundling is complete (see the section at the top of this
file). Original blocker text kept for the record:

- Approval recorded above (full console backend from the official installer).
- Download attempt: `https://www.7-zip.org/a/7z2603-x64.exe` returns **302 →
  github.com**, which is unreachable from this machine (connection timeout).
  The official mirror (sparanoid.com/lab/7z) download was **denied by the
  permission classifier** ("Code from External").
- **Next smallest step requires the user:** place `7z2603-x64.exe` at
  `C:\tmp\7z2603-x64.exe` (browser download from https://www.7-zip.org/download.html
  is fine — it ultimately serves the same file), or grant download permission.
  Then: verify Authenticode + SHA-256 → extract 7z.exe/7z.dll/license.txt to
  `vendor/7zip/` → rebuild → smoke → commit.

### Independent work completed while bundling is blocked (2026-09-19)

- NEW `tests/test_discovery.py` (6 tests): explicit `--sevenzip` wins and raises
  without fallback; `DUCTZIP_7Z_PATH` beats vendor; `vendor/7zip/7z.exe` beats
  install dirs; install-dir fallback; clean `SevenZipMissing` — proving bundled
  discovery does not break overrides or system fallback (Phase 6 requirement).
- NEW `docs/RELEASE_CHECKLIST.md` (ROADMAP v0.7 发布检查清单 item closed).
- Full suite: **230 tests, 0 failures — OK** (was 224).

### Still open in Phase 6

- ~~7-Zip bundling execution~~ — **DONE 2026-09-19** (see the top section).
- ~~Clean-machine verification~~ — recorded limitation, see above.
- ~~v1.0 version bump~~ — DONE in Phase 7 (`1.0.0rc1`).

---

## Phase 5 (continued): MOTW propagation — DONE (committed `bd16c6a`)

**Timestamp:** 2026-09-19
**Checkpoint commit:** `bd16c6a feat: v0.7 MOTW propagation (Zone.Identifier ADS), DD-018` — local only, not pushed.
**Blocking decision RESOLVED (user, 2026-09-19, via AskUserQuestion):** LONG_TASK.md §10.2
item 5 — **实现传播，v1.0 阻塞项**: copy the archive's `Zone.Identifier` ADS onto extracted
outputs; silently skip on non-NTFS/no-MOTW; must complete and be tested before v1.0.

**Other §10.2 decisions resolved in the same batch (user, 2026-09-19):**

- #6 Code signing: **unsigned release candidate allowed**, with documented disclosure
  (no fabricated signing evidence).
- #7 RAR fixture: **keep environment-provided test** (`tests/让子弹飞（二）.rar`, gitignored;
  clean clones skip; noted RAR is proprietary and no local rar.exe exists to mint fixtures).
- #8 Release floor: **deferred items allowed if explicitly recorded** — v1.0 may ship as RC
  with recorded limitations.

### MOTW work completed (2026-09-19)

- NEW `src/ductzip/motw.py`: `read_zone_identifier` / `write_zone_identifier` (NTFS ADS via
  `path:Zone.Identifier`), `iter_output_files` (walks final output dir, skips reparse points
  and symlinks), `propagate_motw` → `MotwReport(source_had_motw, propagated, failures)`.
  Best-effort contract: non-Windows/non-NTFS/no-MOTW → silent no-op; per-file write failure
  is collected, never raised.
- Hook: `ExtractionService.extract_with_progress` runs propagation on the engine's
  `completed` event (before yielding it), so CLI, GUI, and batch inherit it automatically.
  Report stashed on `service.last_motw_report` for diagnostics; not user-surfaced (per the
  approved "quiet skip" policy).
- NEW `tests/test_motw.py` (10 tests): ADS write/read round-trip, no-stream → None,
  recursive propagation to files only (directories untagged), no-MOTW no-op, write-failure
  collection, reparse-point skip, missing-output-dir no-op, plus real-backend service
  integration (propagated, untagged source, MOTW failure does not fail extraction).
- Docs: DD-018 appended; SECURITY.md MOTW section rewritten (implemented behavior +
  boundaries, DD-012 alignment); ROADMAP v0.7 checkbox checked; ARCHITECTURE module layout
  updated; CHANGELOG (215 tests); PROJECT_STATUS; README "Not Yet Implemented" cleaned.
- Version stays 0.7.0 (MOTW belongs to the v0.7 milestone).

---

## Phase 5: v0.7 security, settings, privacy — PARTIAL (committed `c2b15f1`)

**Timestamp:** 2026-09-19
**Branch:** `main`, `HEAD` = `c2b15f1` (local checkpoint, not pushed)
**Checkpoint commit:** `c2b15f1 feat: v0.7 settings model, security hardening, adversarial tests`

**~~BLOCKED_BY_USER_DECISION~~ — RESOLVED 2026-09-19 (user chose "实现传播，v1.0 阻塞项";
implemented in "Phase 5 (continued)" above).** Original blocker text kept for the record:
The MOTW work item ("Implement the approved MOTW policy or document a consciously
deferred limitation") cannot proceed without the user's decision on propagation
behavior, supported Windows/filesystem boundary, and whether an incomplete
implementation blocks v1.0. Per §10.2 protocol: the MOTW branch is stopped; only
independent, non-prejudicial work continues below.

**Also pending (do not block current work):** ~~§10.2 #7 (RAR fixture), #8 (release
floor)~~ — all resolved 2026-09-19, see "Phase 5 (continued)" above.

### Unblocked Phase 5 work completed (2026-09-19)

- NEW `src/ductzip/settings.py`: per-user `Settings` model (`%APPDATA%\DuctZip\settings.json`,
  `DUCTZIP_SETTINGS_PATH` override), atomic saves, corrupt-file backup+reset recovery,
  per-field type fallback, write-time backend-path validation, stale-path discovery
  fallback. `smart_output` unset means "surface built-in default" so loading settings
  never changes CLI extract behavior (DD-016).
- CLI: `ductzip settings show/set/unset` (bad key/value → 2); all commands resolve
  preferences via `_runtime_prefs` (explicit flag > setting > built-in default).
- GUI: `SettingsDialog` (new `gui/settings_dialog.py`), Settings… button, window applies
  saved defaults at startup, engines (preview/extract/batch) use the configured backend.
- Security hardening (DD-017): user-facing errors are stable localized messages; raw
  backend output moved to `ArchiveError.detail`; "is not archive" now maps to
  CorruptedArchive.
- NEW tests: `tests/test_settings.py` (17), `tests/test_security.py` (12: 40+-case
  path matrix, malformed archives, cancel races, password non-leakage),
  `tests/test_gui_settings.py` (10), `tests/test_cli.py::SettingsCliTests` (8),
  `tests/settings_harness.py` (forces throwaway settings path for all tests).
- NEW `docs/SECURITY.md`; DD-016/DD-017; ARCHITECTURE/CHANGELOG/PROJECT_STATUS/
  README/ROADMAP reconciled (v0.7 items checked; MOTW explicitly blocked on §10.2 #5).
- Version 0.6.0 → 0.7.0 (pyproject + `__init__`).

### Gate results (this machine, 2026-09-19)

1. `python -m unittest discover -s tests` (`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`,
   `QT_QPA_PLATFORM=offscreen`): **205 tests, 0 failures, 0 skips — OK**. Was 158.
2. Settings CLI smoke with real backend: set/show/unset sevenzip_path + smart_output,
   `doctor` resolves configured backend, corrupt-file recovery verified in suite.
3. One debugging note: offscreen `QMessageBox.critical` in `on_failed` hangs tests;
  root cause during this phase was a stub service rejecting the new `sevenzip_path`
  kwarg (TypeError → failed signal → modal dialog). Fixed the stubs, not the product.

### Gate status

Phase 5 partial gate: settings + adversarial tests + privacy/security docs **PASS**.
MOTW item: was BLOCKED (§10.2 #5), **RESOLVED and implemented — see Phase 5 (continued)**.

## Phase 4: v0.6 Windows integration — DONE (committed `8653ca1`)

**Timestamp:** 2026-09-19
**Checkpoint commit:** `8653ca1 feat: v0.6 Windows Explorer integration (HKCU shell verbs)` — local only, not pushed (per §10.2 #1 authorization).
**Blocking decision RESOLVED (user, 2026-09-19):** LONG_TASK.md §10.2 item 4 — **HKCU current-user registration**, no elevation required.

**Other §10.2 decisions resolved (user, 2026-09-19):**

- #1 Local checkpoint commits: **ALLOWED** (no push/tag/release).
- #2 v1.0 delivery format: **portable zip**.
- #3 7-Zip redistribution: **bundle official standalone backend, but only after presenting exact source/version/checksum/license for explicit approval — no download before approval**.

**Still pending (do not block current work):**

- #5 MOTW policy, #6 code signing, #7 RAR fixture, #8 release floor.

### Blocking decisions RESOLVED (user, 2026-09-19, via AskUserQuestion)

- **#5 MOTW: 实现传播（Zone.Identifier 从压缩包复制到解压产物），v1.0 阻塞项** — 必须完成并测试后才能进入 v1.0 收尾。
- **#6 代码签名: 允许未签名 release candidate**，文档/发布说明中明示未签名风险（不得伪造签名证据）。
- **#7 RAR 样例: 保持环境提供测试** — 真实 RAR 验证维持条件性外部样例，干净克隆跳过，文档化。
- **#8 发布底线: 允许带记录的限制项延期** — v0.5–v0.7 未完成项作为已知限制显式记录后，v1.0 便携包可发布为 RC。

（§10.2 #3 7-Zip 捆绑维持 2026-09-19 决定：先提交来源/版本/校验和/许可证包获批准后才下载。）

### What changed (code)

- NEW `src/ductzip/shell.py`: Registry abstraction (`WinRegistry` lazy-winreg HKCU / `FakeRegistry` for tests), idempotent `register`, exactly-reversible `unregister` (safe on clean/partial/corrupt states), `status` with stale-launcher detection, stable verb command protocol `"<launcher>" -m ductzip shell <verb> "%1"`. Layout: `Software\DuctZip` metadata, ProgID `DuctZip.Archive` (open→GUI + both verbs), per-extension verbs under `SystemFileAssociations`, `OpenWithProgids` visibility only (no default-program hijack). Verbs: extract-here / extract-to; extensions: .zip .7z .rar .tar .gz .bz2 .xz .zst. Version bumped to 0.6.0 (pyproject + `__init__`).
- `src/ductzip/cli.py`: `shell` subcommand group — `extract-here` (per-archive parent dir roots), `extract-to` (per-archive same-named folder roots via `archive_logical_name`), `register`/`unregister`/`status`. Refactored shared queue drain into `_run_queue_to_completion` (retries, Ctrl+C→cancel_all→130, per-task lines, exit codes 0/1/130/2).
- NEW `tests/test_shell_integration.py` (9): scoped-layout, idempotency, full-removal, partial-corruption recovery, stale-launcher status, missing-verb status, command quoting, launcher resolution, real-HKCU round trip.
- `tests/test_cli.py::ShellCliTests` (5): extract-here per-archive parents (Chinese/spaced names), extract-to same-named folders incl. `.tar.gz` multi-suffix, mixed failure isolation + exit 1, negative retries → 2, missing backend → 1.

### Gate results (this machine, 2026-09-19)

1. `python -m unittest discover -s tests` (`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`): **158 tests, 0 failures, 0 skips — OK**. Was 144 before Phase 4.
2. Manual real-HKCU smoke: `shell register` → `reg query` shows scoped verb keys with correct command strings → invoked the registered command form (`pythonw.exe -m ductzip shell extract-to/extract-here "我的 照片.zip"`) with real 7-Zip — correct extraction (same-named folder / parent dir) → `shell unregister` (26 keys removed) → `reg query` confirms clean, `status` = 未注册.

### Documentation reconciliation (same phase)

- `docs/WINDOWS_INTEGRATION.md` (new): scope/principles, registry layout, invocation protocol, known limitations (Win11 classic-verb location, per-file Explorer invocation, multi-suffix coverage).
- `CHANGELOG.md`, `PROJECT_STATUS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` (v0.6 tasks checked), `docs/DESIGN_DECISIONS.md` (DD-015).

### Gate status

Phase 4 gate: **PASS** — repeatable register → invoke → unregister demonstrated on real HKCU with scoped, reversible diff (automated FakeRegistry suite + real-registry round-trip test + manual smoke with Chinese/spaced paths); CLI/core suites still pass.

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
- 2026-09-19 (§10.2, user): #1 local commits allowed, no push; #2 v1.0 = portable zip; #3 7-Zip bundling approved via a substitute verification chain; #4 HKCU-only registration; #5 MOTW propagation is a v1.0 blocker; #6 unsigned RC allowed with documented disclosure; #7 keep the env-provided RAR fixture; #8 deferred items allowed when explicitly recorded.
- 2026-09-19 (Phase 7): release actions — `git push`, tags, GitHub release, any upload — are **out of scope for this task** and left to the user. Only local checkpoint commits are made.

## Last known-good behavior

**253/253 unit tests pass** (`OK`, 0 skips, exit 0 — three consecutive full runs on
2026-09-26) on `1.0.0rc1`. Portable package builds
(`dist/DuctZip-1.0.0rc1-portable.zip`, sha256 `886f3bc7…a135`) and smoke-passes from an
isolated extraction with the bundled backend. Wheel `ductzip-1.0.0rc1-py3-none-any.whl`
(sha256 `ced8c72c…f401`) installs into a clean venv and exposes both entry points. `doctor` finds
`vendor/7zip/7z.exe` (7-Zip 26.03) when nothing else is configured.

## Next smallest step

Phase 7 is complete; every MUST acceptance criterion in LONG_TASK.md §7 has a recorded,
reproduced result (see the §7.x sections above). No further implementation work is pending
inside the task's scope. What remains is user-owned and explicitly out of scope:

1. Manual release actions — review the diff, commit, and (if desired) push / tag / publish.
2. Close the two stray Python processes noted under Cleanup.
3. Optionally verify on a second physical machine; the current conclusions are limited to the
   evidence actually obtained on this host (§10.2 #8).
