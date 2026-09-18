# Long Task

> Execution contract for continuing DuctZip with a long-running coding agent.
>
> Repository audit date: 2026-09-18
>
> Baseline branch: `main`
>
> Baseline `HEAD`: `a45e8b8 feat: add PySide6 GUI prototype`
>
> Important: the audited v0.4.1 implementation is present as unstaged and untracked work on top of the v0.3 commit. It must not be reset, discarded, or replaced from `HEAD`.

## 1. Project Goal

DuctZip is a lightweight Windows archive extraction tool for users who want clearer defaults and output behavior than invoking 7-Zip directly. It delegates archive algorithms to a 7-Zip CLI backend and owns the user workflow around discovery, inspection, extraction planning, conflict handling, safety checks, progress, cancellation, and Windows integration.

The intended stable product remains an archive extractor, not a complete file manager or a replacement archive implementation.

The current long-task target is to preserve and stabilize the existing v0.4.1 single-archive baseline, then implement the explicit repository roadmap through a verifiable v1.0 release candidate. Every phase is gated. Later phases must not be used to conceal failures in earlier phases.

## 2. Current State

### 2.1 Audited repository state

- Branch: `main`.
- `HEAD` and `origin/main`: `a45e8b8 feat: add PySide6 GUI prototype`.
- The working tree is intentionally dirty and contains the newer v0.4/v0.4.1 implementation and documentation.
- Modified tracked files at audit time include project documentation, `pyproject.toml`, archive code, CLI, GUI, and tests.
- Untracked project files at audit time include `CHANGELOG.md`, benchmarking/resume documents, `src/ductzip/core/`, and Smart Output/service tests.
- No repository-local `AGENTS.md`, `CLAUDE.md`, `PROGRESS.md`, or CI workflow was present at audit time.
- Packaging uses `pyproject.toml` with setuptools. There is no `package.json`, requirements file, lint configuration, or type-check configuration.
- Audited Python requirement: Python 3.11 or newer.
- Audited package version: `0.4.1`.
- GUI dependency is optional: `PySide6>=6.7`.
- The repository does not currently bundle a 7-Zip binary.

Before any edit, run and record:

```powershell
git status --short
git log -5 --oneline --decorate
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard
python --version
```

Do not assume the working tree still matches this audit. Treat fresh command output as authoritative.

### 2.2 Verified baseline

The following commands passed during the 2026-09-18 audit:

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests -v
```

Observed result: 84 tests passed, 0 failed, 0 skipped.

```powershell
python -m pip check
python -m pip wheel . --no-deps --wheel-dir C:\tmp\ductzip-long-task-audit
```

Observed result: dependency check passed and `ductzip-0.4.1-py3-none-any.whl` was built.

```powershell
$env:PYTHONPATH = "src"
python -m ductzip doctor
```

Observed environment-specific result: `D:\7-Zip\7z.exe`, 7-Zip 24.08 x64. This path and version are not portable facts; rediscover them on each machine.

### 2.3 Current architecture

Preserve this dependency direction:

```text
CLI / GUI / future batch queue
            |
            v
     ExtractionService
            |
            +--> SmartOutputPolicy
            |
            v
    SevenZipCliEngine
            |
            v
       7-Zip CLI
```

Primary modules:

| Module | Current responsibility |
|---|---|
| `src/ductzip/cli.py` | `extract`, `list`, `test`, and `doctor` commands; extraction delegates to the service layer. |
| `src/ductzip/gui/app.py` | Current single-window PySide6 GUI, archive preview, extraction worker/thread, progress, cancellation, and output presentation. |
| `src/ductzip/core/extraction.py` | Shared `list -> plan -> conflict -> extract` orchestration and `ExtractionPlan`. |
| `src/ductzip/core/smart_output.py` | Pure Smart Output directory calculation, archive logical-name derivation, top-level grouping, and output conflict calculation. |
| `src/ductzip/archive/sevenzip.py` | Backend discovery, 7-Zip commands, output parsing, progress, cancellation, error mapping, and mandatory pre-extraction path validation. |
| `src/ductzip/archive/errors.py` | DuctZip archive-domain exception types. |

`SevenZipCliEngine` must independently list the actual archive and validate paths immediately before extraction. Caller-provided listings and Smart Output plans are not security evidence.

## 3. Source of Truth

Use this precedence when sources disagree:

1. Fresh tests and observable behavior on the current working tree.
2. Current source code and build configuration.
3. `docs/PRD.md` for product scope and non-goals.
4. `docs/ROADMAP.md` for planned release order and explicit commitments.
5. `docs/ARCHITECTURE.md` and `docs/DESIGN_DECISIONS.md` for boundaries and accepted design choices.
6. `README.md`, `PROJECT_STATUS.md`, and `CHANGELOG.md` for user-facing status.
7. `docs/BANDIZIP_BENCHMARK.md` and `docs/MARKET_RESEARCH.md` as research input only.
8. `docs/DuctZip_RESUME_FACTS.md` as an ancillary career artifact, never as implementation truth.

Conflicts found during the audit:

- `HEAD` represents v0.3, while the working tree and current status documents represent v0.4.1.
- `docs/PRD.md` specifies v0.1 and v0.2 in detail; v0.5 and later are only brief roadmap statements. Do not invent detailed product semantics where the repository is silent.
- `docs/DESIGN_DECISIONS.md` still marks early 7-Zip CLI and PySide6 decisions as awaiting implementation validation, although both are implemented and tested.
- `docs/ROADMAP.md` lists creation of a changelog as incomplete, but `CHANGELOG.md` exists in the working tree.
- `docs/DuctZip_RESUME_FACTS.md` records an older test count and status. It is stale relative to the audited 84-pass baseline.
- A real RAR fixture exists locally but is ignored by `*.rar`; a clean clone cannot rely on it. Therefore the current real-RAR test result is not yet reproducible from Git alone.

When behavior changes, update the relevant source-of-truth documents in the same phase. Do not rewrite historical changelog entries to make the current state appear cleaner.

## 4. Completed Work

The following capabilities exist in the audited working tree and passed the baseline suite unless otherwise noted:

- **MUST baseline:** 7-Zip discovery through explicit paths, environment/registry/common locations, and `ductzip doctor` reporting.
- **MUST baseline:** archive `list`, integrity `test`, and single-archive `extract` CLI workflows.
- **MUST baseline:** ZIP, 7z, and RAR extraction using a real local 7-Zip backend in the audited environment.
- **MUST baseline:** error mapping for missing backend/archive, unsupported/corrupt archive, password errors, permission errors, and cancellation.
- **MUST baseline:** extraction progress event parsing and user-facing progress.
- **MUST baseline:** pre-extraction archive-path validation, including traversal rejection and defense against a forged caller listing.
- **MUST baseline:** Smart Output behavior shared by CLI and GUI through `ExtractionService` and `SmartOutputPolicy`.
- **MUST baseline:** single top-level directory avoids an extra wrapper; multiple top-level entries use an archive-named directory in Smart mode.
- **MUST baseline:** common archive extensions and `.7z.001` / `.partNN.rar` logical-name derivation.
- **MUST baseline:** output conflict choices for merge, rename, and cancel, mapped to existing-file behavior.
- **MUST baseline:** PySide6 single-archive GUI with selection/drop, preview, password field, output selection, Smart mode, conflict choices, progress, cancellation, logs, and open-output action.
- **MUST baseline:** wheel creation from `pyproject.toml`.

The completed list describes the audited local working tree. It does not mean v0.4.1 has been committed, published, installed on a clean machine, or accepted as a stable release.

## 5. Remaining Work

### MUST

MUST work defines the current path to a v1.0 release candidate. All MUST acceptance criteria must pass before `TASK_COMPLETE` may be emitted.

1. Preserve and formalize the dirty v0.4.1 baseline without losing user changes.
2. Make the baseline reproducible from a clean checkout, including a deliberate policy for legal/test-safe RAR coverage.
3. Close or explicitly resolve the known single-task reliability risks: cancellation responsiveness, subprocess cleanup, GUI preview blocking, GUI shutdown/thread lifecycle, duplicate cancellation notification, and stale preview/final-output state.
4. Define and test the security boundary for links/Junctions, Windows-special paths, archive replacement races, and resource exhaustion before claiming release-grade safety.
5. Implement the v0.5 batch queue commitments: multiple archives, per-task state, sequential execution, retry, cancel-current/cancel-all behavior, and batch logs.
6. Expose the same batch semantics through supported CLI and GUI workflows without bypassing `ExtractionService` or archive safety checks.
7. Implement the v0.6 Windows integration commitments after human approval of installation scope and shell-registration behavior: command protocol, context-menu register/unregister, file association, Explorer multi-selection, and documentation.
8. Implement the v0.7 release-readiness commitments: settings, security hardening including MOTW decision/implementation, privacy statement, repeatable packaging, third-party notices, and release checklist.
9. Produce a v1.0 release candidate with install/uninstall instructions, current user documentation, synchronized version/status/changelog, and clean-machine verification evidence.

### SHOULD

SHOULD work is valuable but cannot delay a correct MUST milestone unless it is required to make a MUST acceptance test reliable.

- Add CI for unit tests, packaging, and platform-appropriate smoke checks.
- Add a formatter/linter and type checker only after selecting tools with a small, reviewable configuration; do not mass-reformat unrelated code.
- Diagnose split archives: identify likely first volumes and report missing/incorrect volume selection clearly. Current code only derives names.
- Improve password workflows, including clear retry behavior and no password leakage in logs.
- Add bounded logs and resource limits for unusually large archive listings/output.
- Split the growing GUI module along existing responsibilities when batch work makes the current single file difficult to test.
- Add an explicit engine protocol only when a second backend/test seam or queue design demonstrates a concrete need.

### OPTIONAL

OPTIONAL work is outside the completion gate unless the user promotes it in writing:

- Compression creation.
- In-archive search or rich file preview.
- Extraction history.
- Automatic updater.
- Themes.
- A 7-Zip DLL backend.
- Deep native shell-extension implementation beyond the approved v0.6 command/registration scope.

## 6. Execution Phases

Execute phases in order. A phase may be split into smaller commits or worker tasks, but its acceptance gate must pass before dependent work begins.

### Phase 0: Baseline capture and recovery setup

**Priority:** MUST

**Goal:** Preserve the current dirty v0.4.1 work and make long-running execution resumable.

**Main areas:** Git working tree, `PROGRESS.md`, current documentation, test environment.

**Required work:**

- Read this file and all source-of-truth documents.
- Record current branch, `HEAD`, status, unstaged/staged diff summaries, untracked files, Python/Qt/7-Zip availability, and baseline command results in `PROGRESS.md`.
- Classify every pre-existing modified/untracked file as baseline project work, generated output, or UNKNOWN. Do not delete UNKNOWN files.
- Confirm whether local commits are authorized. Until explicitly authorized, do not commit.
- Do not normalize line endings or reformat the repository during baseline capture.

**Gate:** the full baseline test and wheel commands from section 7 either pass or any failure is recorded with exact output and a bounded repair plan. No pre-existing work is lost.

### Phase 1: v0.4.1 stabilization and reproducibility

**Priority:** MUST

**Goal:** Turn the current single-archive prototype into a reliable baseline suitable for batch expansion.

**Main areas:** `src/ductzip/archive/`, `src/ductzip/core/`, `src/ductzip/gui/`, `tests/`, status/design documents.

**Required work:**

- Add regression tests for silent-backend cancellation, cancellation during listing/planning, subprocess termination/reaping, unexpected worker exceptions, and GUI close while active.
- Move potentially slow GUI archive preview work off the UI thread or otherwise prove the window remains responsive.
- Ensure one logical cancellation produces one terminal UI state.
- Ensure changing/clearing an archive path cannot leave a stale preview or misleading final-output display.
- Define and test path/link/Junction and archive-mutation boundaries. Mark unsupported guarantees honestly.
- Make real-format integration coverage reproducible without committing copyrighted/private user data. If a redistributable RAR fixture cannot be produced, retain a documented conditional external-fixture test and do not claim clean-clone RAR integration coverage.
- Reconcile stale v0.4.1 documentation and test counts.

**Gate:** targeted regressions, full suite, wheel build, CLI smoke tests, and offscreen GUI smoke tests pass. A clean-clone test plan does not depend on the ignored local RAR file.

### Phase 2: v0.5 batch domain model and queue core

**Priority:** MUST

**Goal:** Add a deterministic sequential queue without coupling queue policy to 7-Zip command execution.

**Main areas:** new or existing `ductzip.core` modules, `ExtractionService`, focused queue tests.

**Required work:**

- Define task identity and states such as queued, planning, running, completed, failed, and cancelled.
- Define legal state transitions and terminal-state behavior.
- Reuse one `ExtractionService` operation per archive; do not move Smart Output or conflict logic into the queue.
- Support multiple archives, sequential processing, per-task result/error, retry, current-task cancellation, cancel-all, and structured batch logs.
- Decide and test how queue-level output roots interact with per-archive Smart Output.
- Keep concurrency at one unless a later explicit decision changes it.

**Gate:** deterministic unit tests prove transition legality, ordering, retry, cancellation, one-task failure isolation, Smart Output per task, and path-validation preservation.

### Phase 3: v0.5 CLI and GUI batch workflows

**Priority:** MUST

**Goal:** Make the queue usable and understandable through both supported interfaces.

**Main areas:** `src/ductzip/cli.py`, `src/ductzip/gui/`, batch/core APIs, CLI/GUI tests.

**Required work:**

- Add an explicit batch CLI contract or documented multi-archive extension without breaking current single-archive commands.
- Add GUI multi-selection/drag-drop, queue list, per-task status/progress/error, retry, remove where legal, cancel current, cancel all, and final output visibility.
- Keep the GUI responsive during preview, planning, extraction, cancellation, and shutdown.
- Prevent passwords and raw sensitive backend output from appearing in normal logs.
- Update README/help/status/roadmap/changelog for actual behavior.

**Gate:** CLI tests demonstrate mixed success/failure batches and stable exit behavior; GUI tests cover state transitions and lifecycle; manual smoke evidence covers multiple archives with Chinese and spaced paths.

### Phase 4: v0.6 Windows integration

**Priority:** MUST, blocked by human decisions listed in section 10.

**Goal:** Add reversible Windows Explorer entry points that feed the same CLI/core behavior.

**Main areas:** CLI protocol, Windows registration scripts/module, packaging paths, documentation, integration tests.

**Required work:**

- Define a stable invocation protocol for one or multiple selected archives.
- Implement idempotent register and unregister operations at the approved scope.
- Implement only the approved file associations and context-menu verbs.
- Handle quoted Unicode paths, spaces, multi-selection, and missing/stale executable paths.
- Never require manual registry cleanup after normal uninstall/unregister.
- Do not introduce a native shell extension unless explicitly approved.

**Gate:** repeatable register -> invoke -> unregister tests on a disposable Windows test context; registry diff is scoped and reversible; CLI/core tests still pass.

### Phase 5: v0.7 security, settings, and privacy

**Priority:** MUST

**Goal:** Establish explicit release security defaults and user-configurable backend behavior.

**Main areas:** archive safety layer, settings model/UI, logs, documentation, adversarial tests.

**Required work:**

- Implement the approved MOTW policy or document a consciously deferred limitation before release approval.
- Add settings for supported backend selection/discovery and other approved durable preferences.
- Store settings in an approved per-user location and recover from corrupt settings safely.
- Document what DuctZip reads, writes, executes, and logs; default to local-only behavior.
- Add adversarial tests for traversal, links/reparse points where feasible, special Windows names/paths, malformed archives, resource limits, and cancellation races.

**Gate:** security regression suite passes; settings survive restart and corrupt-file recovery; privacy/security documentation matches observed behavior.

### Phase 6: v0.7 packaging and distribution

**Priority:** MUST, blocked by distribution/signing decisions listed in section 10.

**Goal:** Produce repeatable Windows artifacts without hidden machine dependencies.

**Main areas:** packaging configuration/scripts, bundled resources, licenses/notices, install/uninstall workflow.

**Required work:**

- Use a repeatable build command from a clean environment.
- Implement the approved 7-Zip distribution policy. If bundled, pin the exact official artifact/version and include all required license/notices.
- Ensure bundled-backend discovery does not break explicit user overrides or system-backend fallback.
- Produce checksums and record build inputs/tool versions.
- Verify install, launch, extraction, Windows integration, unregister, and uninstall on a clean Windows environment.
- Signing may remain an explicitly documented release blocker if no certificate is available; never fabricate signing evidence.

**Gate:** reproducible artifact creation and clean-machine smoke evidence; required notices are present in both repository/release package as applicable; no dependency on developer-only paths.

### Phase 7: v1.0 release-candidate closure

**Priority:** MUST

**Goal:** Synchronize product behavior, evidence, and documentation into a truthful release candidate.

**Main areas:** full repository, user documentation, release checklist, version metadata.

**Required work:**

- Run every acceptance command and record exact results in `PROGRESS.md`.
- Verify README, PRD, architecture, decisions, roadmap, project status, changelog, and resume facts do not contradict observable behavior.
- Provide install, uninstall, first-run, backend, batch, password, conflict, security limitation, and troubleshooting instructions.
- Verify no secrets, private archives, local absolute paths, build caches, or machine-specific artifacts are included.
- Prepare release notes and an evidence summary. Do not publish, push, tag, or create a GitHub release.

**Gate:** every MUST criterion in section 7 passes; all UNKNOWN items are resolved or explicitly accepted by the user; final repository status and diff are reviewed. Only then may the agent output `TASK_COMPLETE`.

## 7. Acceptance Criteria

Commands assume PowerShell from the repository root. Adapt only when the environment requires it, and record the exact substitute.

### 7.1 Baseline and regression suite

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -s tests -v
```

Acceptance:

- Exit code is 0.
- No unexpected skips. Every skip is listed in `PROGRESS.md` with its prerequisite and effect on claims.
- Unit tests do not require network access.
- Tests leave no tracked-file changes or unignored archive/output residue.

### 7.2 Packaging and dependency checks

```powershell
python -m pip check
python -m pip wheel . --no-deps --wheel-dir "$env:TEMP\ductzip-wheel"
```

Acceptance:

- Both commands exit 0.
- Wheel name/version matches `pyproject.toml`.
- Installing the wheel in a clean virtual environment exposes `ductzip` and `ductzip-gui` entry points.
- Runtime package does not accidentally include tests, private archives, caches, or developer output directories.

### 7.3 CLI acceptance

At minimum, use fresh temporary directories and generated/redistributable fixtures to verify:

```powershell
ductzip doctor
ductzip list <archive>
ductzip test <archive>
ductzip extract <archive> --output <directory>
```

Acceptance:

- Exit codes distinguish success, user cancellation, invalid input, and extraction failure according to documented behavior.
- Chinese and spaced archive/output paths succeed.
- Single-top-level and multi-top-level Smart Output produce the documented final directory.
- Merge, rename, cancel, skip, and overwrite combinations match documented semantics.
- Password-required, wrong-password, corrupt, unsupported, missing-backend, and traversal cases produce stable user-facing errors without leaking passwords.
- Batch CLI acceptance after Phase 3 covers mixed success/failure, retry, cancellation, ordering, and per-task final directories.

### 7.4 GUI acceptance

Automated offscreen tests must cover constructibility and state transitions. Manual or UI-automation evidence on Windows must additionally show:

- The window remains responsive while listing and extracting a large or slow archive.
- Archive path changes clear or refresh preview and final-output state.
- Password visibility is controlled and passwords do not enter logs.
- Progress and terminal status are understandable.
- Cancel and window-close terminate/reap active backend processes within a documented bounded time.
- Batch queue actions cannot create illegal state transitions.
- Final output directories are visible and openable for completed tasks.
- Unicode, spaces, conflicts, and mixed batch outcomes behave as documented.

### 7.5 Security acceptance

- Engine-level pre-extraction listing and traversal validation remain mandatory even if service/queue callers provide a listing.
- Regression tests cover relative traversal, absolute/UNC/device-style paths as applicable, mixed separators, case behavior, and forged/stale planning data.
- Link/Junction/reparse-point behavior and archive replacement race behavior are tested or explicitly documented as unsupported with a release decision.
- Extraction never writes outside the approved output boundary in supported scenarios.
- Logs redact passwords and avoid dumping raw backend output to normal users.
- No download, update, telemetry, or network behavior is added without explicit user approval.

### 7.6 Windows integration acceptance

- Registration and unregistration are idempotent and restricted to the approved user/machine scope.
- Quoted Unicode paths and Explorer multi-selection reach the documented DuctZip command protocol intact.
- Unregister/uninstall removes only keys/files owned by DuctZip.
- Missing executable/backend states give recoverable errors.
- Tests use a disposable registry/test context where practical and never mutate unrelated associations.

### 7.7 Documentation and repository acceptance

```powershell
git status --short
git diff --check
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard
```

Acceptance:

- Every changed/untracked file is intentional and listed in `PROGRESS.md`.
- `git diff --check` has no whitespace errors. Line-ending warnings alone must be assessed rather than hidden by a repository-wide conversion.
- Version, test counts, implemented features, limitations, roadmap checkboxes, project status, changelog, and release notes agree.
- No secrets, credentials, tokens, private fixtures, local absolute paths, or generated build/cache files are proposed for publication.
- No source file contains unresolved production `TODO`, placeholder behavior, `NotImplementedError`, or silent stub unless explicitly accepted and documented.

### 7.8 Static-quality tools

Current state: UNKNOWN because the repository has no configured formatter, linter, or type checker.

If Phase 1 introduces such tools, pin/configure them in the project, scope the first pass to actionable project code, and add their exact commands here and to `PROGRESS.md`. Do not claim lint/typecheck success before a tool is selected and run.

## 8. Allowed Autonomous Decisions

The coding agent may decide the following without interrupting execution, provided decisions preserve this contract and are recorded in `PROGRESS.md`:

- Internal names and small private helper boundaries.
- Test organization and fixture-generation mechanics using redistributable data.
- Whether focused modules are split when a file becomes difficult to test, as long as public behavior and dependency direction remain stable.
- Data structures for queue state, structured events, and result objects.
- Exact wording of clear user-facing errors and logs, provided documented semantics remain intact.
- Selection of deterministic timeouts/backoff values for tests and process shutdown, with rationale and non-flaky evidence.
- Small accessibility/layout improvements required to fit the approved workflows.
- Backward-compatible CLI additions and deprecation paths.
- Bug fixes whose expected behavior is already unambiguous from tests, PRD, or accepted decisions.

For any nontrivial decision, record alternatives considered, chosen option, and evidence. Prefer the smallest change that preserves existing behavior.

## 9. Forbidden / Out of Scope

The coding agent must not:

- Push, force-push, create or modify remotes, create tags/releases, publish packages, or deploy artifacts.
- Commit unless the user has explicitly authorized local commits for this long task.
- Change Claude Code/Kimi/provider/model/authentication configuration, API keys, tokens, credential stores, or shell profiles.
- Read or modify files outside this repository, except isolated temporary build/test directories and read-only system/tool discovery required by tests.
- Delete, reset, checkout over, stash, or overwrite pre-existing user changes.
- Use destructive Git commands such as `git reset --hard` or broad cleanup commands such as `git clean -fd`.
- Download, bundle, or redistribute 7-Zip or another binary until the distribution source, version, checksum, license obligations, and user approval are recorded.
- Add telemetry, network services, automatic downloads, self-update, cloud integration, ads, or account systems.
- Implement custom compression/decompression algorithms.
- Expand DuctZip into a full file manager.
- Add archive creation, rich preview/search, themes, history, DLL backend, or deep native shell extensions unless promoted from OPTIONAL by the user.
- Weaken pre-extraction path validation to make a test or archive pass.
- Log or persist passwords.
- Claim security guarantees, clean-machine compatibility, release signing, or format support without fresh evidence.

## 10. Known Risks and Blockers

### 10.1 Current technical risks

- **Dirty baseline:** the most advanced implementation is not represented by `HEAD`. An agent starting from the commit alone would regress the project.
- **Cancellation responsiveness:** the current extraction loop performs blocking character reads; a silent backend may delay cancellation. Listing is also synchronous and currently lacks a cancellation path.
- **GUI responsiveness/lifecycle:** preview is performed on the UI thread; active-worker shutdown and unexpected non-domain exceptions need stronger evidence.
- **Duplicate cancellation state:** the engine event and raised cancellation exception may both produce terminal GUI notification.
- **Stale GUI state:** manual path changes/clears may leave old preview or final-output information.
- **Subprocess/resource cleanup:** output buffering and process reaping need bounded behavior on cancel/failure.
- **Safety boundary:** traversal checks exist, but links/Junctions/reparse points, special Windows paths, resource exhaustion, and archive mutation between planning/extraction require explicit treatment.
- **TOCTOU/planning duplication:** the service plans from a listing while the engine re-lists for security. Safety must keep the fresh engine listing; product behavior when the archive changes must be defined.
- **Non-reproducible RAR evidence:** the passing local RAR fixture is ignored and absent from a clean clone.
- **No CI/static analysis:** current success is local and environment-specific.
- **GUI scaling debt:** `src/ductzip/gui/app.py` is a single-window/single-task module and may need a focused split for queue work.
- **Packaging gap:** no installer, bundled backend, third-party notice file, signing process, or clean-machine test evidence exists.

### 10.2 UNKNOWN items requiring human decision

The agent may research and present options, but must not silently choose these product/release decisions:

1. **Local commit permission:** may the long-running agent create local checkpoint commits, or must all work remain uncommitted?
2. **v1.0 delivery format:** portable archive, installer, both, or another explicitly named artifact.
3. **7-Zip redistribution:** confirm that v1.0 should bundle the official standalone backend as currently recorded in DD-008, and approve the exact source/version/license package before download or inclusion.
4. **Windows registration scope:** current-user versus machine-wide registration, whether elevation is acceptable, exact context-menu verbs, and exact file associations.
5. **MOTW policy:** propagation behavior, supported Windows/filesystem boundary, and whether an incomplete implementation blocks v1.0.
6. **Code signing:** certificate availability and whether unsigned artifacts may be called a release candidate or stable release.
7. **RAR integration fixture:** approval to add a newly generated redistributable fixture, or acceptance that real RAR verification remains an environment-provided test.
8. **Release floor:** whether v1.0 must include every roadmap checkbox in v0.5-v0.7, or whether any named item may be deferred with an accepted limitation.

When one of these decisions blocks the next phase, stop that branch, record `BLOCKED_BY_USER_DECISION` in `PROGRESS.md`, and continue only independent work that cannot prejudice the decision.

## 11. Long-Task Recovery Protocol

The agent must create and maintain `PROGRESS.md` in the repository root. It is the recovery ledger, not a marketing status document.

After every coherent work unit and before any planned stop, timeout, context reset, or handoff, update `PROGRESS.md` with:

- Timestamp and current phase.
- Branch and `HEAD`.
- Concise `git status --short` summary.
- Pre-existing files that must be preserved.
- Files changed during the current work unit.
- Completed acceptance criteria with exact commands and results.
- Failed/skipped checks with exact reason.
- Current decisions, UNKNOWN items, and blockers.
- Last known-good behavior.
- Next smallest executable step and command.
- Whether local commits were authorized and, if so, their hashes.

On resume:

1. Read `LONG_TASK.md` and `PROGRESS.md` completely.
2. Run `git status --short`, inspect staged and unstaged diffs, and list untracked files.
3. Verify branch/`HEAD` against the ledger; do not assume divergence is accidental.
4. Re-run the smallest test proving the last known-good checkpoint.
5. Inspect partial files before retrying a failed command or delegated worker task.
6. Continue from the recorded next step. Never restart by resetting the repository.

Worker/subagent reports are advisory. The supervising agent must independently inspect diffs, untracked files, source, and test output before marking a unit complete.

If an operation times out or leaves uncertain state:

- Stop issuing overlapping retries.
- Capture process/tool status and affected files.
- Record the exact uncertain boundary in `PROGRESS.md`.
- Verify whether a child process is still active and whether files are partially written.
- Resume only after the state is understood. Never declare success from a timeout or worker summary.

## 12. Final Completion Gate

The long task is complete only when all statements below are true:

- Every MUST item in sections 5 through 7 is implemented or explicitly removed from scope by a recorded user decision.
- All phases have passed their gates in dependency order.
- The full automated suite passes with every skip explained and accepted.
- CLI, GUI, Windows integration, packaging, and clean-machine checks have fresh recorded evidence appropriate to the final scope.
- Security limitations and unsupported cases are explicit; no unsupported guarantee is presented as complete.
- README, PRD, architecture, decisions, roadmap, project status, changelog, version metadata, and release notes agree with code and tests.
- `PROGRESS.md` contains the final command outputs, artifact names/checksums, remaining OPTIONAL items, and repository status.
- Final `git status`, staged/unstaged diff, and untracked files have been reviewed; no unrelated or sensitive content is included.
- No push, remote modification, tag, release, provider/auth change, or project-external modification occurred.
- All required human decisions in section 10 are resolved or explicitly documented as accepted limitations.

Only after satisfying every applicable condition may the coding agent output exactly:

```text
TASK_COMPLETE
```

Otherwise it must report the current phase, verified evidence, remaining MUST items, and the precise blocker. It must not use `TASK_COMPLETE` as a progress marker.
