"""Qt worker objects for background archive work.

These QObject workers are moved onto QThread instances by the GUI. Keeping
them separate from the window code lets the lifecycle (thread affinity,
signal emission, cancellation) be tested without constructing widgets.

Design rules:
- Exactly one terminal signal per logical outcome. Cancellation is reported
  once even when both the engine's ``cancelled`` event and the raised
  ``ArchiveCancelled`` exception are observed.
- Unexpected (non-archive-domain) exceptions are reported through ``failed``
  instead of silently killing the thread.
- No password or raw backend output is ever emitted through a signal.
"""

from __future__ import annotations

from pathlib import Path
import threading

from ductzip.archive import (
    ArchiveCancelled,
    ArchiveError,
    ArchiveListing,
    SevenZipCliEngine,
)
from ductzip.core import BatchQueue, ExtractionService

from PySide6.QtCore import QObject, QThread, Signal, Slot


class ExtractWorker(QObject):
    progress = Signal(int)
    status = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        archive_path: Path,
        output_dir: Path,
        overwrite_policy: str,
        conflict_strategy: str,
        password: str | None,
        smart_output: bool,
        cancel_event: threading.Event,
        sevenzip_path: str | None = None,
    ):
        super().__init__()
        self.archive_path = archive_path
        self.output_dir = output_dir
        self.overwrite_policy = overwrite_policy
        self.conflict_strategy = conflict_strategy
        self.password = password
        self.smart_output = smart_output
        self.cancel_event = cancel_event
        self.sevenzip_path = sevenzip_path
        self._cancel_reported = False

    def _report_cancelled_once(self) -> None:
        if not self._cancel_reported:
            self._cancel_reported = True
            self.cancelled.emit()

    @Slot()
    def run(self) -> None:
        try:
            service = ExtractionService(sevenzip_path=self.sevenzip_path)
            for event in service.extract_with_progress(
                self.archive_path,
                self.output_dir,
                password=self.password,
                cancel_event=self.cancel_event,
                overwrite_policy=self.overwrite_policy,
                smart_output=self.smart_output,
                conflict_strategy=self.conflict_strategy,
            ):
                if event.kind == "started":
                    self.status.emit(f"Extracting {self.archive_path.name}")
                elif event.kind == "progress" and event.percent is not None:
                    self.progress.emit(event.percent)
                elif event.kind == "completed" and event.result is not None:
                    self.progress.emit(100)
                    self.completed.emit(str(event.result.output_dir))
                elif event.kind == "cancelled":
                    self._report_cancelled_once()
        except ArchiveCancelled:
            self._report_cancelled_once()
        except ArchiveError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - unexpected bugs must surface, not vanish.
            self.failed.emit(f"Unexpected error: {exc.__class__.__name__}: {exc}")


class BatchWorker(QObject):
    """Runs a BatchQueue on a background thread.

    Every ``BatchEvent`` is re-emitted through ``event`` so the window can
    update per-task rows. Cancellation (``cancel_current``/``cancel_all``)
    deliberately calls straight into the queue instead of using queued
    signals: while ``run()`` is executing, the worker thread has no event
    loop, so a queued cancel would never be delivered until the run ended.
    The queue's cancellation entry points are safe from any thread (events
    are thread-safe; queued-task transitions never race the runner's
    current-task transitions).
    """

    event = Signal(object)  # BatchEvent
    finished = Signal()

    def __init__(self, queue: BatchQueue):
        super().__init__()
        self._queue = queue

    @Slot()
    def run(self) -> None:
        try:
            for event in self._queue.run():
                self.event.emit(event)
        finally:
            self.finished.emit()
            # Quit this thread's event loop directly. Relying on a queued
            # ``finished -> thread.quit`` delivery can deadlock under a
            # QTest.qWait pump: the quit event may never reach a thread whose
            # Python slot has already returned, leaving exec() spinning while
            # the main thread blocks inside qWait's event processing.
            QThread.currentThread().quit()

    def cancel_current(self) -> None:
        self._queue.cancel_current()

    def cancel_all(self) -> None:
        self._queue.cancel_all()


class PreviewWorker(QObject):
    """Loads archive listings off the UI thread.

    Long-lived: the window owns one preview thread for its whole lifetime and
    delivers requests through the ``request`` signal, avoiding per-preview
    thread churn. ``generation`` is an opaque token supplied by the window so
    results that arrive after the archive path or password changed can be
    discarded as stale.
    """

    request = Signal(str, object, int)  # archive path, password, generation
    loaded = Signal(object, int)  # ArchiveListing, generation
    failed = Signal(str, int)  # message, generation
    finished = Signal(int)  # generation

    def __init__(self, sevenzip_path: str | None = None):
        super().__init__()
        self._archive_path = Path(".")
        self._password: str | None = None
        self._generation = -1
        self._cancel_event = threading.Event()
        self._sevenzip_path = sevenzip_path
        self._engine: SevenZipCliEngine | None = None

    def _get_engine(self) -> SevenZipCliEngine:
        # Backend discovery (registry scan, PATH search) is not cheap; do it
        # once per window instead of once per preview request.
        if self._engine is None:
            self._engine = SevenZipCliEngine(self._sevenzip_path)
        return self._engine

    @Slot(str, object, int)
    def on_request(self, archive_path: str, password, generation: int) -> None:
        self._archive_path = Path(archive_path)
        self._password = password
        self._generation = generation
        self._cancel_event.clear()
        self._run()

    def cancel(self) -> None:
        """Ask the in-flight listing to abort (used at window shutdown)."""
        self._cancel_event.set()

    @property
    def current_archive_path(self) -> Path:
        return self._archive_path

    @property
    def current_generation(self) -> int:
        return self._generation

    def _run(self) -> None:
        try:
            listing = self._get_engine().list(
                self._archive_path,
                password=self._password,
                cancel_event=self._cancel_event,
            )
        except ArchiveCancelled:
            # Shutdown-time cancellation: report nothing, just finish.
            pass
        except ArchiveError as exc:
            self.failed.emit(str(exc), self._generation)
        except Exception as exc:  # noqa: BLE001 - unexpected bugs must surface, not vanish.
            self.failed.emit(f"Unexpected error: {exc.__class__.__name__}: {exc}", self._generation)
        else:
            self.loaded.emit(listing, self._generation)
        finally:
            self.finished.emit(self._generation)
