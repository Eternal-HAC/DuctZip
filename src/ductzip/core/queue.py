"""Deterministic sequential batch queue for extraction tasks.

``BatchQueue`` drives any number of archives through a single
:class:`~ductzip.core.extraction.ExtractionService`, one task at a time,
without knowing anything about 7-Zip command lines. The queue owns task
identity, state transitions, cancellation routing, retry, and a structured
batch log; Smart Output and conflict policy stay inside the service, applied
per task exactly as they are for a single archive.

Task states and legal transitions::

    queued -> planning -> running -> completed        (success)
    queued -> planning -> running -> failed           (extraction error)
    queued -> planning              -> failed         (listing/planning error)
    queued -> planning -> running -> cancelled        (cancel during extraction)
    queued -> planning              -> cancelled      (cancel during planning)
    queued                          -> cancelled      (cancel-all before start)
    failed    -> queued                               (retry)
    cancelled -> queued                               (retry)
    completed: terminal, no outgoing transitions

Design constraints (LONG_TASK.md Phase 2):

- Concurrency is one; tasks run strictly in enqueue order.
- The queue never accepts a caller-provided listing and never performs path
  validation itself: each task is exactly one ``ExtractionService``
  operation, and the engine's fresh-listing validation remains the sole
  safety authority (DD-009 / DD-012).
- Passwords are held on the task for execution but are redacted from every
  persisted message (state-change log entries and per-task errors); raw
  backend "failed" progress output is redacted before being re-yielded and
  is never persisted in the structured log.
- The queue is deterministic and thread-free: ``run()`` is a plain
  generator. Callers drive it from whatever thread they like; cancellation
  is signaled through events from any thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from collections.abc import Iterator

from ductzip.archive import (
    ArchiveCancelled,
    ArchiveError,
    ExtractResult,
    ProgressEvent,
)

from .extraction import ExtractionService
from .smart_output import ConflictStrategy, OverwritePolicy

# Task states.
QUEUED = "queued"
PLANNING = "planning"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

TaskState = str

_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    QUEUED: frozenset({PLANNING, CANCELLED}),
    PLANNING: frozenset({RUNNING, FAILED, CANCELLED}),
    RUNNING: frozenset({COMPLETED, FAILED, CANCELLED}),
    COMPLETED: frozenset(),
    FAILED: frozenset({QUEUED}),
    CANCELLED: frozenset({QUEUED}),
}

# Tasks may be removed from the queue unless they are actively executing.
_REMOVABLE_STATES: frozenset[TaskState] = frozenset({QUEUED, FAILED, CANCELLED, COMPLETED})

_RETRYABLE_STATES: frozenset[TaskState] = frozenset({FAILED, CANCELLED})


class BatchQueueError(Exception):
    """Base class for batch queue misuse."""


class IllegalTaskTransition(BatchQueueError):
    """Raised when a state transition or operation violates the task state machine."""


def _redact(text: str, password: str | None) -> str:
    if password:
        return text.replace(password, "***")
    return text


@dataclass
class BatchTask:
    """One archive's extraction request and its mutable execution state.

    ``password`` is used only for execution and is never emitted through
    events or persisted messages (see ``_redact``).
    """

    task_id: int
    archive_path: Path
    requested_output_dir: Path
    smart_output: bool = True
    conflict_strategy: ConflictStrategy = "merge"
    overwrite_policy: OverwritePolicy = "skip"
    password: str | None = None
    state: TaskState = QUEUED
    attempts: int = 0
    result: ExtractResult | None = None
    error: str | None = None

    @property
    def final_output_dir(self) -> Path | None:
        """Actual output directory when the task completed, else ``None``."""
        return self.result.output_dir if self.result is not None else None


@dataclass(frozen=True)
class BatchEvent:
    """One structured, UI-agnostic batch record.

    ``kind`` is one of ``batch_started``, ``task_state``, ``task_progress``,
    or ``batch_finished``. State changes (and batch start/finish) are also
    appended to ``BatchQueue.log``; progress events are yielded for live
    display but are not persisted.
    """

    kind: str
    task: BatchTask | None
    state: TaskState | None = None
    progress: ProgressEvent | None = None
    message: str = ""


@dataclass(frozen=True)
class BatchSummary:
    total: int
    completed: int
    failed: int
    cancelled: int

    def __str__(self) -> str:
        return (
            f"批量解压结束：完成 {self.completed}，失败 {self.failed}，"
            f"取消 {self.cancelled}，共 {self.total} 个任务。"
        )


class BatchQueue:
    """Sequential, single-concurrency batch runner over an ExtractionService."""

    def __init__(self, service: ExtractionService | None = None):
        self.service = service if service is not None else ExtractionService()
        self._tasks: list[BatchTask] = []
        self._next_id = 1
        self._log: list[BatchEvent] = []
        self._run_cancel = threading.Event()
        self._current_cancel: threading.Event | None = None
        self._current_task: BatchTask | None = None

    # ------------------------------------------------------------------ tasks

    @property
    def tasks(self) -> tuple[BatchTask, ...]:
        return tuple(self._tasks)

    @property
    def log(self) -> tuple[BatchEvent, ...]:
        """Structured state-change history (progress events are not included)."""
        return tuple(self._log)

    @property
    def summary(self) -> BatchSummary:
        return BatchSummary(
            total=len(self._tasks),
            completed=sum(1 for task in self._tasks if task.state == COMPLETED),
            failed=sum(1 for task in self._tasks if task.state == FAILED),
            cancelled=sum(1 for task in self._tasks if task.state == CANCELLED),
        )

    def get(self, task_id: int) -> BatchTask:
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        raise BatchQueueError(f"找不到任务 {task_id}。")

    def add(
        self,
        archive_path: str | Path,
        requested_output_dir: str | Path,
        *,
        smart_output: bool = True,
        conflict_strategy: ConflictStrategy = "merge",
        overwrite_policy: OverwritePolicy = "skip",
        password: str | None = None,
    ) -> BatchTask:
        task = BatchTask(
            task_id=self._next_id,
            archive_path=Path(archive_path),
            requested_output_dir=Path(requested_output_dir),
            smart_output=smart_output,
            conflict_strategy=conflict_strategy,
            overwrite_policy=overwrite_policy,
            password=password,
        )
        self._next_id += 1
        self._tasks.append(task)
        return task

    def can_retry(self, task_id: int) -> bool:
        return self.get(task_id).state in _RETRYABLE_STATES

    def retry(self, task_id: int) -> BatchTask:
        """Re-queue a failed or cancelled task. Attempts increment on the next run."""
        task = self.get(task_id)
        self._transition(task, QUEUED)
        task.error = None
        return task

    def remove(self, task_id: int) -> None:
        """Drop a task that is not actively executing."""
        task = self.get(task_id)
        if task.state not in _REMOVABLE_STATES:
            raise IllegalTaskTransition(f"任务正在{task.state}，不能移除。")
        self._tasks.remove(task)

    # ------------------------------------------------------------- cancellation

    def cancel_current(self) -> bool:
        """Cancel the in-flight task only; queued tasks keep their state.

        Returns ``True`` when a task was actually in flight.
        """
        if self._current_cancel is None:
            return False
        self._current_cancel.set()
        return True

    def cancel_all(self) -> None:
        """Cancel the in-flight task and every queued task.

        Queued tasks transition to ``cancelled`` immediately so UI observers
        see the change without waiting for the runner to reach them.
        """
        self._run_cancel.set()
        if self._current_cancel is not None:
            self._current_cancel.set()
        for task in self._tasks:
            if task.state == QUEUED:
                task.error = None
                self._transition(task, CANCELLED, "已取消：批量任务已取消。")

    # ----------------------------------------------------------------- running

    def run(self, cancel_event: threading.Event | None = None) -> Iterator[BatchEvent]:
        """Run every queued task sequentially, in enqueue order.

        Yields ``BatchEvent`` records live; state changes are additionally
        persisted in ``self.log``. Tasks that fail or are cancelled do not
        stop later tasks (failure isolation). Not re-entrant: one run at a
        time.
        """
        self._run_cancel.clear()
        pending = [task for task in self._tasks if task.state == QUEUED]
        event = BatchEvent(kind="batch_started", task=None, message=f"批量解压开始：{len(pending)} 个任务。")
        self._log.append(event)
        yield event
        for task in pending:
            if task.state != QUEUED or not any(task is live for live in self._tasks):
                continue  # removed or cancelled after the run started
            if self._run_cancel.is_set() or (cancel_event is not None and cancel_event.is_set()):
                task.error = None
                yield self._transition(task, CANCELLED, "已取消：批量任务已取消。")
                continue
            yield from self._run_task(task, cancel_event)
        event = BatchEvent(kind="batch_finished", task=None, message=str(self.summary))
        self._log.append(event)
        yield event

    def _run_task(
        self,
        task: BatchTask,
        external_cancel: threading.Event | None,
    ) -> Iterator[BatchEvent]:
        task_cancel = threading.Event()
        self._current_cancel = task_cancel
        self._current_task = task
        task.attempts += 1
        try:
            yield self._transition(task, PLANNING)
            saw_started = False
            try:
                progress_events = self.service.extract_with_progress(
                    task.archive_path,
                    task.requested_output_dir,
                    smart_output=task.smart_output,
                    conflict_strategy=task.conflict_strategy,
                    overwrite_policy=task.overwrite_policy,
                    password=task.password,
                    cancel_event=task_cancel,
                )
                for progress in progress_events:
                    if external_cancel is not None and external_cancel.is_set():
                        task_cancel.set()
                    if progress.kind == "started" and not saw_started:
                        saw_started = True
                        yield self._transition(task, RUNNING)
                    if progress.kind == "completed" and progress.result is not None:
                        task.result = progress.result
                    if progress.kind == "failed" and progress.message:
                        # Raw backend output may embed the command line (and
                        # thus the password): redact before it reaches a UI.
                        progress = ProgressEvent(
                            kind=progress.kind,
                            percent=progress.percent,
                            current_file=progress.current_file,
                            message=_redact(progress.message, task.password),
                            result=progress.result,
                        )
                    yield BatchEvent(kind="task_progress", task=task, progress=progress)
                if not saw_started:
                    yield self._transition(task, RUNNING)
                if task.result is not None:
                    yield self._transition(task, COMPLETED)
                else:
                    task.error = "后端未返回解压结果。"
                    yield self._transition(task, FAILED, task.error)
            except ArchiveCancelled:
                yield self._transition(task, CANCELLED, "已取消。")
            except ArchiveError as exc:
                task.error = _redact(str(exc), task.password)
                yield self._transition(task, FAILED, task.error)
            except Exception as exc:  # noqa: BLE001 - one bad task must not kill the batch.
                task.error = _redact(f"Unexpected error: {exc.__class__.__name__}: {exc}", task.password)
                yield self._transition(task, FAILED, task.error)
        finally:
            self._current_cancel = None
            self._current_task = None

    # ----------------------------------------------------------------- internals

    def _transition(self, task: BatchTask, new_state: TaskState, message: str = "") -> BatchEvent:
        legal = _TRANSITIONS.get(task.state, frozenset())
        if new_state not in legal:
            raise IllegalTaskTransition(f"任务 {task.task_id} 不能从 {task.state} 切换到 {new_state}。")
        task.state = new_state
        message = _redact(message, task.password)
        event = BatchEvent(kind="task_state", task=task, state=new_state, message=message)
        self._log.append(event)
        return event
