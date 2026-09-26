from __future__ import annotations

from pathlib import Path
import sys
import threading

from ductzip.archive import ArchiveEntry, ArchiveError
from ductzip.core import (
    BatchQueue,
    BatchQueueError,
    ExtractionService,
    IllegalTaskTransition,
    SmartOutputPolicy,
    detect_output_conflicts,
)
from ductzip.settings import effective_sevenzip, load_settings, save_settings

# Qt is imported at module level here and in the GUI submodules below. A missing
# optional dependency is reported by ``ductzip.gui.main`` (the entry point for
# both ``ductzip-gui`` and ``python -m ductzip.gui``), which turns the
# ImportError into an actionable message; importing this module directly
# without PySide6 therefore raises ImportError, as any missing import would.
from PySide6.QtCore import QObject, QCoreApplication, QElapsedTimer, QEventLoop, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import workers
from .settings_dialog import SettingsDialog
from .workers import BatchWorker, ExtractWorker, PreviewWorker


# Bounded time the window waits for an active extraction worker to finish
# after the user closes the window or cancels. Chosen well above the engine's
# own terminate grace (2s terminate + 2s kill) plus reader-thread join.
WORKER_SHUTDOWN_TIMEOUT_MS = 10_000


class DropLineEdit(QLineEdit):
    fileDropped = Signal(str)
    filesDropped = Signal(list)

    def __init__(self, placeholder: str):
        super().__init__()
        self.setAcceptDrops(True)
        self.setPlaceholderText(placeholder)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt API
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if not paths:
            return
        self.setText(paths[0])
        self.fileDropped.emit(paths[0])
        self.filesDropped.emit(paths)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DuctZip")
        self.resize(720, 420)

        self._settings_result = load_settings()

        self.cancel_event: threading.Event | None = None
        self.worker_thread: QThread | None = None
        self.worker: ExtractWorker | None = None
        self.preview_thread: QThread | None = None
        self.preview_worker: PreviewWorker | None = None
        self.preview_generation = 0
        self._preview_busy = False
        self.last_output_dir: Path | None = None
        self.preview_entries: tuple[ArchiveEntry, ...] = ()

        self.batch_queue: BatchQueue | None = None
        self.batch_thread: QThread | None = None
        self.batch_worker: BatchWorker | None = None
        self._batch_running = False
        self._task_items: dict[int, QListWidgetItem] = {}
        self._task_percents: dict[int, int] = {}

        self.archive_input = DropLineEdit("Drop an archive here or choose a file")
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Choose a base output directory")
        self.final_output_input = QLineEdit()
        self.final_output_input.setReadOnly(True)
        self.final_output_input.setPlaceholderText("Final extraction directory")
        self.conflict_label = QLabel("No conflicts")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password, if required")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.show_password_checkbox = QCheckBox("Show")
        self.smart_output_checkbox = QCheckBox("Smart output")
        # smart_output settings default to GUI's built-in (on) when unset.
        self.smart_output_checkbox.setChecked(
            self._settings_result.settings.smart_output
            if self._settings_result.settings.smart_output is not None
            else True
        )

        self.archive_button = QPushButton("Browse")
        self.output_button = QPushButton("Browse")
        self.extract_button = QPushButton("Extract")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.open_output_button = QPushButton("Open Folder")
        self.open_output_button.setEnabled(False)
        self.settings_button = QPushButton("Settings…")

        self.policy_combo = QComboBox()
        self.policy_combo.addItems(["skip", "overwrite", "rename"])
        self.policy_combo.setCurrentText(self._settings_result.settings.overwrite_policy)
        self.policy_combo.setToolTip("How to handle existing files in the output directory.")
        self.conflict_strategy_combo = QComboBox()
        self.conflict_strategy_combo.addItems(["merge", "rename", "cancel"])
        self.conflict_strategy_combo.setCurrentText(self._settings_result.settings.conflict_strategy)
        self.conflict_strategy_combo.setToolTip("How to handle existing top-level output conflicts.")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.preview_table = QTableWidget(0, 3)
        self.preview_table.setHorizontalHeaderLabels(["Name", "Size", "Type"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)

        self.add_archives_button = QPushButton("Add Archives...")
        self.start_batch_button = QPushButton("Start Batch")
        self.start_batch_button.setEnabled(False)
        self.retry_task_button = QPushButton("Retry")
        self.retry_task_button.setEnabled(False)
        self.remove_task_button = QPushButton("Remove")
        self.remove_task_button.setEnabled(False)
        self.cancel_current_button = QPushButton("Cancel Current")
        self.cancel_current_button.setEnabled(False)
        self.cancel_all_button = QPushButton("Cancel All")
        self.cancel_all_button.setEnabled(False)
        self.task_list = QListWidget()
        self.task_list.setToolTip("Double-click a completed task to open its output folder.")

        self._build_layout()
        self._connect_signals()
        if self._settings_result.corrupt_recovered:
            self.append_log("设置文件已损坏：已重置为默认值（备份为 settings.json.corrupt）。")

    def _effective_sevenzip(self) -> str | None:
        return effective_sevenzip(self._settings_result.settings)

    def _build_layout(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        archive_row = QHBoxLayout()
        archive_row.addWidget(QLabel("Archive"))
        archive_row.addWidget(self.archive_input, 1)
        archive_row.addWidget(self.archive_button)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Base output"))
        output_row.addWidget(self.output_input, 1)
        output_row.addWidget(self.output_button)

        final_output_row = QHBoxLayout()
        final_output_row.addWidget(QLabel("Final output"))
        final_output_row.addWidget(self.final_output_input, 1)

        conflict_row = QHBoxLayout()
        conflict_row.addWidget(QLabel("Conflicts"))
        conflict_row.addWidget(self.conflict_label, 1)

        password_row = QHBoxLayout()
        password_row.addWidget(QLabel("Password"))
        password_row.addWidget(self.password_input, 1)
        password_row.addWidget(self.show_password_checkbox)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Existing files"))
        action_row.addWidget(self.policy_combo)
        action_row.addWidget(QLabel("Conflicts"))
        action_row.addWidget(self.conflict_strategy_combo)
        action_row.addWidget(self.smart_output_checkbox)
        action_row.addStretch(1)
        action_row.addWidget(self.settings_button)
        action_row.addWidget(self.open_output_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.extract_button)

        root.addLayout(archive_row)
        root.addLayout(output_row)
        root.addLayout(final_output_row)
        root.addLayout(conflict_row)
        root.addLayout(password_row)
        root.addLayout(action_row)
        root.addWidget(self.progress_bar)
        root.addWidget(QLabel("Archive contents"))
        root.addWidget(self.preview_table, 1)
        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("Batch queue"))
        batch_row.addWidget(self.add_archives_button)
        batch_row.addWidget(self.start_batch_button)
        batch_row.addWidget(self.retry_task_button)
        batch_row.addWidget(self.remove_task_button)
        batch_row.addWidget(self.cancel_current_button)
        batch_row.addWidget(self.cancel_all_button)
        root.addLayout(batch_row)
        root.addWidget(self.task_list, 1)
        root.addWidget(QLabel("Log"))
        root.addWidget(self.log, 1)

        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.archive_button.clicked.connect(self.choose_archive)
        self.output_button.clicked.connect(self.choose_output_dir)
        self.extract_button.clicked.connect(self.start_extract)
        self.cancel_button.clicked.connect(self.cancel_extract)
        self.open_output_button.clicked.connect(self.open_output_dir)
        self.settings_button.clicked.connect(self.open_settings)
        self.archive_input.fileDropped.connect(self.on_archive_selected)
        self.archive_input.filesDropped.connect(self.add_batch_archives)
        self.archive_input.textChanged.connect(self.on_archive_text_changed)
        self.show_password_checkbox.toggled.connect(self.toggle_password_visibility)
        self.password_input.editingFinished.connect(self.refresh_preview)
        self.output_input.textChanged.connect(self.update_final_output_dir)
        self.smart_output_checkbox.toggled.connect(self.update_final_output_dir)
        self.add_archives_button.clicked.connect(self.choose_archives)
        self.start_batch_button.clicked.connect(self.start_batch)
        self.retry_task_button.clicked.connect(self.retry_selected_task)
        self.remove_task_button.clicked.connect(self.remove_selected_task)
        self.cancel_current_button.clicked.connect(self.cancel_current_batch)
        self.cancel_all_button.clicked.connect(self.cancel_all_batch)
        self.task_list.itemSelectionChanged.connect(self._update_batch_buttons)
        self.task_list.itemActivated.connect(self.open_task_output)

    @Slot()
    def choose_archive(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose archive",
            "",
            "Archives (*.zip *.7z *.rar);;All files (*.*)",
        )
        if path:
            self.archive_input.setText(path)
            self.on_archive_selected(path)

    @Slot()
    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output directory")
        if path:
            self.output_input.setText(path)
            self.update_final_output_dir()

    @Slot(bool)
    def toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    @Slot()
    def on_archive_selected(self, path: str) -> None:
        if not self.output_input.text().strip():
            self.output_input.setText(str(Path(path).parent))
        self.refresh_preview()

    @Slot(str)
    def on_archive_text_changed(self, text: str) -> None:
        # Any edit (typing, clearing, replacing) invalidates everything the
        # previous archive path produced: preview rows, final-output preview,
        # conflict summary, and the last extraction's open-folder state.
        self.preview_generation += 1
        self.preview_entries = ()
        self.preview_table.setRowCount(0)
        self.last_output_dir = None
        self.open_output_button.setEnabled(False)
        archive = Path(text.strip()) if text.strip() else None
        if archive is None or not archive.is_file():
            self.final_output_input.clear()
            self.conflict_label.setText("No conflicts")
            return
        self.update_final_output_dir()

    @Slot()
    def refresh_preview(self) -> None:
        archive_text = self.archive_input.text().strip()
        if not archive_text:
            self.on_archive_text_changed("")
            return

        archive = Path(archive_text)
        if not archive.is_file():
            self.on_archive_text_changed(archive_text)
            return

        self._start_preview_worker(archive)

    def _ensure_preview_thread(self) -> None:
        if self.preview_thread is not None:
            return
        self.preview_thread = QThread(self)
        self.preview_worker = PreviewWorker(sevenzip_path=self._effective_sevenzip())
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_worker.request.connect(self.preview_worker.on_request)
        self.preview_worker.loaded.connect(self.on_preview_loaded)
        self.preview_worker.failed.connect(self.on_preview_failed)
        self.preview_worker.finished.connect(self.on_preview_finished)
        self.preview_thread.finished.connect(self.preview_worker.deleteLater)
        self.preview_thread.start()

    def _start_preview_worker(self, archive: Path) -> None:
        self._ensure_preview_thread()
        self.preview_generation += 1
        self._preview_busy = True
        assert self.preview_worker is not None
        self.preview_worker.request.emit(str(archive), self.current_password(), self.preview_generation)

    @Slot(object, int)
    def on_preview_loaded(self, listing, generation: int) -> None:
        if generation != self.preview_generation or self._is_stale_preview(listing):
            return
        self.preview_entries = listing.entries
        self.preview_table.setRowCount(len(listing.entries))
        for row, entry in enumerate(listing.entries):
            size = "" if entry.size is None else str(entry.size)
            kind = "Folder" if entry.is_directory else "File"
            self.preview_table.setItem(row, 0, QTableWidgetItem(entry.path))
            self.preview_table.setItem(row, 1, QTableWidgetItem(size))
            self.preview_table.setItem(row, 2, QTableWidgetItem(kind))
        self.update_final_output_dir()
        self.append_log(f"Preview loaded: {len(listing.entries)} entries")

    @Slot(str, int)
    def on_preview_failed(self, message: str, generation: int) -> None:
        if generation != self.preview_generation:
            return
        self.preview_entries = ()
        self.preview_table.setRowCount(0)
        self.update_final_output_dir()
        self.append_log(f"Preview failed: {message}")

    @Slot(int)
    def on_preview_finished(self, generation: int) -> None:
        if generation == self.preview_generation:
            self._preview_busy = False

    def _is_stale_preview(self, listing) -> bool:
        """A preview is stale if the archive path moved on or a newer preview
        started. Stale results are discarded, never shown."""
        worker = self.preview_worker
        if worker is None or self._generation_mismatch():
            return True
        return worker.current_archive_path != listing.archive_path

    def _generation_mismatch(self) -> bool:
        worker = self.preview_worker
        return worker is None or worker.current_generation != self.preview_generation

    def current_password(self) -> str | None:
        password = self.password_input.text()
        return password or None

    def update_final_output_dir(self, *_args) -> None:
        output_text = self.output_input.text().strip()
        if not output_text:
            self.final_output_input.clear()
            self.conflict_label.setText("No conflicts")
            return

        archive_text = self.archive_input.text().strip()
        if self.smart_output_checkbox.isChecked() and archive_text:
            final_output = SmartOutputPolicy().resolve_final_dir(
                Path(archive_text), Path(output_text), self.preview_entries
            )
        else:
            final_output = Path(output_text)
        self.final_output_input.setText(str(final_output))
        self.update_conflict_summary(final_output)

    def update_conflict_summary(self, final_output: Path) -> None:
        if not self.preview_entries:
            self.conflict_label.setText("No conflicts")
            return

        conflicts = detect_output_conflicts(final_output, self.preview_entries)
        if not conflicts:
            self.conflict_label.setText("No conflicts")
            return

        names = ", ".join(conflict.entry_path for conflict in conflicts[:3])
        suffix = "" if len(conflicts) <= 3 else f", +{len(conflicts) - 3} more"
        self.conflict_label.setText(f"{len(conflicts)} existing target(s): {names}{suffix}")

    @Slot()
    def start_extract(self) -> None:
        archive_text = self.archive_input.text().strip()
        output_text = self.output_input.text().strip()
        if not archive_text or not output_text:
            QMessageBox.warning(self, "Missing input", "Choose an archive and output directory.")
            return

        self.cancel_event = threading.Event()
        self.worker_thread = QThread(self)
        self.worker = ExtractWorker(
            Path(archive_text),
            Path(output_text),
            self.policy_combo.currentText(),
            self.conflict_strategy_combo.currentText(),
            self.current_password(),
            self.smart_output_checkbox.isChecked(),
            self.cancel_event,
            sevenzip_path=self._effective_sevenzip(),
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.append_log)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.cancelled.connect(self.on_cancelled)
        self.worker.completed.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.cancelled.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.on_worker_finished)

        self.progress_bar.setValue(0)
        self.extract_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.open_output_button.setEnabled(False)
        self.last_output_dir = None
        self.append_log("Started")
        self.worker_thread.start()

    @Slot()
    def cancel_extract(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.append_log("Cancelling")

    @Slot(str)
    def on_completed(self, output_dir: str) -> None:
        self.last_output_dir = Path(output_dir)
        self.open_output_button.setEnabled(True)
        self.append_log(f"Completed: {output_dir}")

    @Slot()
    def open_output_dir(self) -> None:
        if self.last_output_dir is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output_dir)))

    def open_settings(self) -> None:
        dialog = SettingsDialog(self._settings_result.settings, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        updated = dialog.result_settings()
        path = save_settings(updated)
        self._settings_result = load_settings()
        self.smart_output_checkbox.setChecked(
            updated.smart_output if updated.smart_output is not None else True
        )
        self.policy_combo.setCurrentText(updated.overwrite_policy)
        self.conflict_strategy_combo.setCurrentText(updated.conflict_strategy)
        self.append_log(f"设置已保存：{path}")

    @Slot(str)
    def on_failed(self, message: str) -> None:
        self.append_log(f"Failed: {message}")
        QMessageBox.critical(self, "Extraction failed", message)

    @Slot()
    def on_cancelled(self) -> None:
        self.append_log("Cancelled")

    @Slot()
    def on_worker_finished(self) -> None:
        thread = self.worker_thread
        worker = self.worker
        if thread is not None:
            # QThread.finished fires before the OS thread has fully exited.
            # Dropping the last Python reference to ``worker`` (whose thread
            # affinity is the dying worker thread) inside that window makes
            # shiboken destroy the C++ object concurrently with the thread's
            # teardown, which intermittently crashed the whole process
            # (access violation / heap corruption / hard abort). Wait until
            # the OS thread has ended before the captured references are
            # released, so the C++ worker is deleted from the main thread
            # only after its affinity thread is gone. Idempotent: closeEvent
            # may call this explicitly and the queued signal may deliver it
            # again.
            thread.wait(WORKER_SHUTDOWN_TIMEOUT_MS)
        self.extract_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.worker_thread = None
        self.worker = None
        self.cancel_event = None
        del worker  # released here, after the thread is confirmed dead

    @Slot(str)
    def append_log(self, message: str) -> None:
        self.log.appendPlainText(message)

    # ------------------------------------------------------------------ batch

    @Slot()
    def choose_archives(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose archives",
            "",
            "Archives (*.zip *.7z *.rar);;All files (*.*)",
        )
        if paths:
            self.add_batch_archives(paths)

    def _ensure_batch_queue(self) -> BatchQueue:
        if self.batch_queue is None:
            # workers.SevenZipCliEngine is looked up on the module so tests can
            # patch it once for both preview and batch, like the preview path.
            # The configured settings backend (if any) applies here too.
            self.batch_queue = BatchQueue(ExtractionService(workers.SevenZipCliEngine(self._effective_sevenzip())))
        return self.batch_queue

    @Slot(list)
    def add_batch_archives(self, paths: list) -> int:
        queue = self._ensure_batch_queue()
        added = 0
        for raw in paths:
            archive = Path(raw)
            if not archive.is_file():
                self.append_log(f"Batch: skipping {raw} (not a file)")
                continue
            base = self.output_input.text().strip() or str(archive.parent)
            task = queue.add(
                archive,
                base,
                smart_output=self.smart_output_checkbox.isChecked(),
                conflict_strategy=self.conflict_strategy_combo.currentText(),
                overwrite_policy=self.policy_combo.currentText(),
                password=self.current_password(),
            )
            item = QListWidgetItem()
            item.setData(Qt.UserRole, task.task_id)
            self._task_items[task.task_id] = item
            self._task_percents[task.task_id] = 0
            self._set_task_label(task)
            self.task_list.addItem(item)
            added += 1
        if added:
            self.append_log(f"Batch: added {added} archive(s)")
        self._update_batch_buttons()
        return added

    @Slot()
    def start_batch(self) -> None:
        queue = self.batch_queue
        if queue is None or self._batch_running:
            return
        pending = sum(1 for task in queue.tasks if task.state == "queued")
        if pending == 0:
            self.append_log("Batch: nothing to run.")
            return
        self.batch_thread = QThread(self)
        self.batch_worker = BatchWorker(queue)
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.started.connect(self.batch_worker.run)
        self.batch_worker.event.connect(self.on_batch_event)
        self.batch_worker.finished.connect(self.batch_thread.quit)
        self.batch_thread.finished.connect(self.on_batch_thread_finished)
        self._batch_running = True
        self._update_batch_buttons()
        self.append_log(f"Batch started: {pending} task(s)")
        self.batch_thread.start()

    @Slot(object)
    def on_batch_event(self, event) -> None:
        task = event.task
        if task is None:
            if event.kind == "batch_finished":
                self.append_log(event.message)
            return
        if event.kind == "task_state":
            self._set_task_label(task)
            if event.message:
                self.append_log(f"[{task.archive_path.name}] {event.message}")
            self._update_batch_buttons()
        elif event.kind == "task_progress" and event.progress is not None:
            if event.progress.kind == "progress" and event.progress.percent is not None:
                self._task_percents[task.task_id] = event.progress.percent
                if task.state == "running":
                    self._set_task_label(task)

    def _set_task_label(self, task) -> None:
        item = self._task_items.get(task.task_id)
        if item is None:
            return
        status = {
            "queued": "Waiting",
            "planning": "Planning",
            "running": f"Running {self._task_percents.get(task.task_id, 0)}%",
            "completed": f"Completed → {task.final_output_dir}",
            "failed": f"Failed: {task.error}",
            "cancelled": "Cancelled",
        }.get(task.state, task.state)
        item.setText(f"{task.archive_path.name} — {status}")

    def _selected_task(self):
        if self.batch_queue is None:
            return None
        items = self.task_list.selectedItems()
        if not items:
            return None
        try:
            return self.batch_queue.get(items[0].data(Qt.UserRole))
        except BatchQueueError:
            return None

    def _update_batch_buttons(self) -> None:
        running = self._batch_running
        selected = self._selected_task()
        has_queued = self.batch_queue is not None and any(
            task.state == "queued" for task in self.batch_queue.tasks
        )
        self.start_batch_button.setEnabled(not running and has_queued)
        self.cancel_current_button.setEnabled(running)
        self.cancel_all_button.setEnabled(has_queued or running)
        self.retry_task_button.setEnabled(
            selected is not None
            and self.batch_queue is not None
            and self.batch_queue.can_retry(selected.task_id)
        )
        self.remove_task_button.setEnabled(
            selected is not None and selected.state in ("queued", "failed", "cancelled", "completed")
        )

    @Slot()
    def retry_selected_task(self) -> None:
        task = self._selected_task()
        if task is None or self.batch_queue is None or not self.batch_queue.can_retry(task.task_id):
            return
        self.batch_queue.retry(task.task_id)
        self._task_percents[task.task_id] = 0
        self._set_task_label(task)
        self._update_batch_buttons()

    @Slot()
    def remove_selected_task(self) -> None:
        task = self._selected_task()
        if task is None or self.batch_queue is None:
            return
        try:
            self.batch_queue.remove(task.task_id)
        except IllegalTaskTransition as exc:
            self.append_log(f"Batch: {exc}")
            return
        item = self._task_items.pop(task.task_id, None)
        if item is not None:
            self.task_list.takeItem(self.task_list.row(item))
        self._update_batch_buttons()

    @Slot()
    def cancel_current_batch(self) -> None:
        if self.batch_queue is not None and self.batch_queue.cancel_current():
            self.append_log("Batch: cancelling current task")

    @Slot()
    def cancel_all_batch(self) -> None:
        if self.batch_queue is None:
            return
        self.batch_queue.cancel_all()
        self.append_log("Batch: cancelling all tasks")
        for task in self.batch_queue.tasks:
            self._set_task_label(task)
        self._update_batch_buttons()

    @Slot("QListWidgetItem*")
    def open_task_output(self, item) -> None:
        if self.batch_queue is None:
            return
        try:
            task = self.batch_queue.get(item.data(Qt.UserRole))
        except BatchQueueError:
            return
        if task.final_output_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(task.final_output_dir)))

    @Slot()
    def on_batch_thread_finished(self) -> None:
        thread = self.batch_thread
        worker = self.batch_worker
        if thread is not None:
            # Same teardown race as on_worker_finished: hold the wrapper
            # references until the OS thread has fully exited.
            thread.wait(WORKER_SHUTDOWN_TIMEOUT_MS)
        self._batch_running = False
        self.batch_thread = None
        self.batch_worker = None
        if self.batch_queue is not None:
            for task in self.batch_queue.tasks:
                self._set_task_label(task)
        self._update_batch_buttons()
        del worker  # released here, after the thread is confirmed dead

    def _wait_for_thread(self, thread: QThread, timeout_ms: int) -> bool:
        """Pump events until ``thread`` stops or the bound expires.

        Worker -> thread.quit deliveries are queued to this (main) thread, so
        a plain blocking wait() would deadlock them; pump instead. A deleted
        C++ wrapper (RuntimeError) means shutdown already succeeded.
        """
        timer = QElapsedTimer()
        timer.start()
        while not timer.hasExpired(timeout_ms):
            try:
                running = thread.isRunning()
            except RuntimeError:
                return True
            if not running:
                return True
            QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
        try:
            return not thread.isRunning()
        except RuntimeError:
            return True

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        # Closing the window while background work is running must terminate
        # and reap it within a bounded time, not leave an orphaned process or
        # a thread that outlives the window.
        preview_thread = self.preview_thread

        if preview_thread is not None:
            if self.preview_worker is not None:
                self.preview_worker.cancel()
            preview_thread.quit()
            preview_thread.wait(2_000)
            self.preview_thread = None
            self.preview_worker = None
            self._preview_busy = False

        batch_thread = self.batch_thread
        if batch_thread is not None:
            if self.batch_queue is not None:
                self.batch_queue.cancel_all()
            if not self._wait_for_thread(batch_thread, WORKER_SHUTDOWN_TIMEOUT_MS):
                self.append_log("Warning: batch thread did not stop in time.")
                event.ignore()
                return
            self.on_batch_thread_finished()

        thread = self.worker_thread
        if thread is None:
            event.accept()
            return

        if self.cancel_event is not None:
            self.cancel_event.set()

        if not self._wait_for_thread(thread, WORKER_SHUTDOWN_TIMEOUT_MS):
            self.append_log("Warning: extraction thread did not stop in time.")
            event.ignore()
            return

        self.on_worker_finished()
        event.accept()


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
