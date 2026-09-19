# PROGRESS.md — DuctZip Long-Task Recovery Ledger

Recovery ledger per `LONG_TASK.md` §11. Not a marketing status document.

## Phase 6 (continued): 7-Zip backend bundling — DONE (this commit)

**Timestamp:** 2026-09-19
**Branch:** `main`, base `HEAD` = `d0a8662` (local checkpoint, not pushed)

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

- Clean-machine verification beyond isolated-directory smoke on this machine (no second
  physical machine available; under §10.2 #8 the final claim must be scoped to evidence
  actually gathered, and this is recorded as a limitation rather than claimed as done).
- v1.0 version bump — Phase 7.

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
- Clean-machine verification beyond isolated-dir smoke (no second physical machine;
  final claim must be scoped to evidence actually gathered).
- v1.0 version bump — Phase 7.

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

## Last known-good behavior

127/127 unit tests pass (incl. 20 batch-queue + 13 engine-lifecycle + 7 GUI-lifecycle + 19 GUI tests); wheel builds with `ductzip/core/queue.py`; `doctor` discovers `D:\7-Zip\7z.exe`.

## Next smallest step

Phase 3 (v0.5 CLI + GUI batch workflows, LONG_TASK.md Phase 3): batch CLI contract without breaking single-archive commands; GUI multi-selection/drag-drop, queue list with per-task status/progress/error, retry/remove/cancel-current/cancel-all, final output visibility; keep GUI responsive; ensure passwords/raw backend output stay out of normal logs. Read `src/ductzip/cli.py` and `src/ductzip/gui/app.py` first.
