from __future__ import annotations

from pathlib import Path
import sys
import threading

from ductzip.archive import ArchiveCancelled, ArchiveError, SevenZipCliEngine

try:
    from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
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
except ImportError as exc:  # pragma: no cover - exercised only without GUI dependency.
    raise SystemExit("PySide6 is required for the GUI. Install with: pip install -e .[gui]") from exc


class DropLineEdit(QLineEdit):
    fileDropped = Signal(str)

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
        if not urls:
            return
        path = urls[0].toLocalFile()
        self.setText(path)
        self.fileDropped.emit(path)


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
        password: str | None,
        cancel_event: threading.Event,
    ):
        super().__init__()
        self.archive_path = archive_path
        self.output_dir = output_dir
        self.overwrite_policy = overwrite_policy
        self.password = password
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            engine = SevenZipCliEngine()
            for event in engine.extract_with_progress(
                self.archive_path,
                self.output_dir,
                password=self.password,
                cancel_event=self.cancel_event,
                overwrite_policy=self.overwrite_policy,
            ):
                if event.kind == "started":
                    self.status.emit(f"Extracting {self.archive_path.name}")
                elif event.kind == "progress" and event.percent is not None:
                    self.progress.emit(event.percent)
                elif event.kind == "completed" and event.result is not None:
                    self.progress.emit(100)
                    self.completed.emit(str(event.result.output_dir))
                elif event.kind == "cancelled":
                    self.cancelled.emit()
        except ArchiveCancelled:
            self.cancelled.emit()
        except ArchiveError as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DuctZip")
        self.resize(720, 420)

        self.cancel_event: threading.Event | None = None
        self.worker_thread: QThread | None = None
        self.worker: ExtractWorker | None = None
        self.last_output_dir: Path | None = None

        self.archive_input = DropLineEdit("Drop an archive here or choose a file")
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Choose an output directory")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password, if required")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.show_password_checkbox = QCheckBox("Show")

        self.archive_button = QPushButton("Browse")
        self.output_button = QPushButton("Browse")
        self.extract_button = QPushButton("Extract")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.open_output_button = QPushButton("Open Folder")
        self.open_output_button.setEnabled(False)

        self.policy_combo = QComboBox()
        self.policy_combo.addItems(["skip", "overwrite", "rename"])
        self.policy_combo.setToolTip("How to handle existing files in the output directory.")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.preview_table = QTableWidget(0, 3)
        self.preview_table.setHorizontalHeaderLabels(["Name", "Size", "Type"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)

        self._build_layout()
        self._connect_signals()

    def _build_layout(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        archive_row = QHBoxLayout()
        archive_row.addWidget(QLabel("Archive"))
        archive_row.addWidget(self.archive_input, 1)
        archive_row.addWidget(self.archive_button)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output"))
        output_row.addWidget(self.output_input, 1)
        output_row.addWidget(self.output_button)

        password_row = QHBoxLayout()
        password_row.addWidget(QLabel("Password"))
        password_row.addWidget(self.password_input, 1)
        password_row.addWidget(self.show_password_checkbox)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Existing files"))
        action_row.addWidget(self.policy_combo)
        action_row.addStretch(1)
        action_row.addWidget(self.open_output_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.extract_button)

        root.addLayout(archive_row)
        root.addLayout(output_row)
        root.addLayout(password_row)
        root.addLayout(action_row)
        root.addWidget(self.progress_bar)
        root.addWidget(QLabel("Archive contents"))
        root.addWidget(self.preview_table, 1)
        root.addWidget(QLabel("Log"))
        root.addWidget(self.log, 1)

        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.archive_button.clicked.connect(self.choose_archive)
        self.output_button.clicked.connect(self.choose_output_dir)
        self.extract_button.clicked.connect(self.start_extract)
        self.cancel_button.clicked.connect(self.cancel_extract)
        self.open_output_button.clicked.connect(self.open_output_dir)
        self.archive_input.fileDropped.connect(self.on_archive_selected)
        self.show_password_checkbox.toggled.connect(self.toggle_password_visibility)
        self.password_input.editingFinished.connect(self.refresh_preview)

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

    @Slot(str)
    def on_archive_selected(self, path: str) -> None:
        if not self.output_input.text().strip():
            archive = Path(path)
            self.output_input.setText(str(archive.with_suffix("")))
        self.refresh_preview()

    @Slot(bool)
    def toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    @Slot()
    def refresh_preview(self) -> None:
        archive_text = self.archive_input.text().strip()
        if not archive_text:
            return

        archive = Path(archive_text)
        if not archive.is_file():
            self.preview_table.setRowCount(0)
            return

        try:
            listing = SevenZipCliEngine().list(archive, password=self.current_password())
        except ArchiveError as exc:
            self.preview_table.setRowCount(0)
            self.append_log(f"Preview failed: {exc}")
            return

        self.preview_table.setRowCount(len(listing.entries))
        for row, entry in enumerate(listing.entries):
            size = "" if entry.size is None else str(entry.size)
            kind = "Folder" if entry.is_directory else "File"
            self.preview_table.setItem(row, 0, QTableWidgetItem(entry.path))
            self.preview_table.setItem(row, 1, QTableWidgetItem(size))
            self.preview_table.setItem(row, 2, QTableWidgetItem(kind))
        self.append_log(f"Preview loaded: {len(listing.entries)} entries")

    def current_password(self) -> str | None:
        password = self.password_input.text()
        return password or None

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
            self.current_password(),
            self.cancel_event,
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
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
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

    @Slot(str)
    def on_failed(self, message: str) -> None:
        self.append_log(f"Failed: {message}")
        QMessageBox.critical(self, "Extraction failed", message)

    @Slot()
    def on_cancelled(self) -> None:
        self.append_log("Cancelled")

    @Slot()
    def on_worker_finished(self) -> None:
        self.extract_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.worker_thread = None
        self.worker = None
        self.cancel_event = None

    @Slot(str)
    def append_log(self, message: str) -> None:
        self.log.appendPlainText(message)


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
