"""GUI lifecycle regression tests: stale-state clearing, single terminal
cancellation notification, unexpected worker exceptions, and bounded window
shutdown while an extraction is active."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_gui import pump_events_until  # noqa: E402


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class GuiStaleStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_clearing_archive_path_clears_preview_and_final_output(self) -> None:
        from ductzip.archive import ArchiveEntry
        from ductzip.gui.app import MainWindow

        window = MainWindow()
        window.archive_input.setText(str(Path(tempfile.gettempdir()) / "x.zip"))
        window.output_input.setText(tempfile.gettempdir())
        window.preview_entries = (ArchiveEntry("a.txt", 1, None, None, False),)
        window.preview_table.setRowCount(1)
        window.update_final_output_dir()
        self.assertNotEqual(window.final_output_input.text(), "")

        window.archive_input.setText("")

        self.assertEqual(window.preview_table.rowCount(), 0)
        self.assertEqual(window.preview_entries, ())
        self.assertEqual(window.final_output_input.text(), "")
        self.assertEqual(window.conflict_label.text(), "No conflicts")

    def test_changing_archive_path_resets_open_folder_state(self) -> None:
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            window = MainWindow()
            window.on_completed(temp)
            self.assertTrue(window.open_output_button.isEnabled())

            window.archive_input.setText("some/other/archive.zip")

            self.assertFalse(window.open_output_button.isEnabled())
            self.assertIsNone(window.last_output_dir)

    def test_nonexistent_archive_path_clears_final_output(self) -> None:
        from ductzip.gui.app import MainWindow

        window = MainWindow()
        window.output_input.setText(tempfile.gettempdir())
        window.archive_input.setText(str(Path(tempfile.gettempdir()) / "missing.zip"))

        self.assertEqual(window.final_output_input.text(), "")
        self.assertEqual(window.preview_table.rowCount(), 0)

    def test_stale_preview_result_is_discarded(self) -> None:
        """A listing that completes after the user switched archives must not
        overwrite the current preview."""
        import time
        from unittest.mock import patch

        from ductzip.archive import ArchiveEntry, ArchiveListing
        from ductzip.gui import workers
        from ductzip.gui.app import MainWindow
        from tests.test_gui import _StubEngine, pump_events_until

        class _SlowPerArchiveEngine(_StubEngine):
            def list(self, archive_path, password=None, cancel_event=None):
                time.sleep(0.3)  # stay in flight across the archive switch
                name = Path(archive_path).stem
                return ArchiveListing(
                    archive_path=Path(archive_path).resolve(),
                    sevenzip_path=Path("7z.exe"),
                    entries=(ArchiveEntry(f"{name}.txt", 1, None, None, False),),
                    stdout="",
                    stderr="",
                )

        with tempfile.TemporaryDirectory() as temp:
            archive_a = Path(temp) / "a.zip"
            archive_b = Path(temp) / "b.zip"
            archive_a.write_bytes(b"fake")
            archive_b.write_bytes(b"fake")
            window = MainWindow()

            with patch.object(workers, "SevenZipCliEngine", _SlowPerArchiveEngine):
                window.archive_input.setText(str(archive_a))
                window.on_archive_selected(str(archive_a))
                # Switch archives while the first listing is still in flight.
                window.archive_input.setText(str(archive_b))
                window.on_archive_selected(str(archive_b))

                self.assertTrue(
                    pump_events_until(lambda: not window._preview_busy),
                    "preview did not finish",
                )

            self.assertEqual(window.preview_table.rowCount(), 1)
            self.assertEqual(window.preview_table.item(0, 0).text(), "b.txt")
            window.close()

    def test_close_during_preview_stops_preview_thread(self) -> None:
        import time
        from unittest.mock import patch

        from ductzip.gui import workers
        from ductzip.gui.app import MainWindow
        from tests.test_gui import _StubEngine, pump_events_until

        class _SlowEngine(_StubEngine):
            def list(self, archive_path, password=None, cancel_event=None):
                time.sleep(0.5)
                return super().list(archive_path, password, cancel_event)

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "a.zip"
            archive.write_bytes(b"fake")
            window = MainWindow()

            with patch.object(workers, "SevenZipCliEngine", _SlowEngine):
                window.archive_input.setText(str(archive))
                window.on_archive_selected(str(archive))
                self.assertTrue(pump_events_until(lambda: window._preview_busy))
                window.close()

            self.assertIsNone(window.preview_thread, "preview thread outlived the window")


class _CancellingService:
    """Stand-in for ExtractionService: blocks like a silent backend until the
    cancel event is set, then reports cancellation through both the event and
    the exception (exactly what the real engine does)."""

    def extract_with_progress(self, *args, **kwargs):
        cancel_event: threading.Event = kwargs["cancel_event"]
        from ductzip.archive import ArchiveCancelled, ProgressEvent

        yield ProgressEvent(kind="started", percent=0, message="test")
        while not cancel_event.wait(0.02):
            pass
        yield ProgressEvent(kind="cancelled", message="cancelled")
        raise ArchiveCancelled()


class _ExplodingService:
    def extract_with_progress(self, *args, **kwargs):
        raise RuntimeError("boom: something unrelated broke")
        yield  # pragma: no cover - makes this a generator


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class GuiWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _make_worker(self, service_class):
        from ductzip.gui.workers import ExtractWorker

        worker = ExtractWorker(
            Path("archive.zip"),
            Path("out"),
            "skip",
            "merge",
            None,
            True,
            threading.Event(),
        )
        return worker

    def test_unexpected_worker_exception_emits_single_failure(self) -> None:
        from PySide6.QtTest import QSignalSpy
        from ductzip.gui import workers

        worker = self._make_worker(_ExplodingService)
        spy_failed = QSignalSpy(worker.failed)
        spy_cancelled = QSignalSpy(worker.cancelled)

        with patch.object(workers, "ExtractionService", _ExplodingService):
            worker.run()

        self.assertEqual(spy_failed.count(), 1)
        self.assertEqual(spy_cancelled.count(), 0)
        self.assertIn("Unexpected error", spy_failed.at(0)[0])

    def test_cancellation_emits_single_terminal_notification(self) -> None:
        from PySide6.QtTest import QSignalSpy
        from ductzip.gui import workers

        worker = self._make_worker(_CancellingService)
        spy_cancelled = QSignalSpy(worker.cancelled)
        spy_failed = QSignalSpy(worker.failed)
        spy_completed = QSignalSpy(worker.completed)

        def cancel_soon() -> None:
            threading.Event().wait(0.1)
            worker.cancel_event.set()

        threading.Thread(target=cancel_soon, daemon=True).start()

        with patch.object(workers, "ExtractionService", _CancellingService):
            worker.run()

        self.assertEqual(spy_cancelled.count(), 1, "cancellation must be reported exactly once")
        self.assertEqual(spy_failed.count(), 0)
        self.assertEqual(spy_completed.count(), 0)


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class GuiShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_close_while_extracting_terminates_worker_bounded(self) -> None:
        from ductzip.gui import workers
        from ductzip.gui.app import MainWindow

        window = MainWindow()
        window.archive_input.setText("archive.zip")
        window.output_input.setText("out")

        with patch.object(workers, "ExtractionService", _CancellingService):
            window.start_extract()
            self.assertIsNotNone(window.worker_thread)
            self.assertTrue(window.worker_thread.isRunning())

            window.close()

        if window.worker_thread is not None:
            self.assertFalse(window.worker_thread.isRunning(), "worker thread outlived the window")
        self.assertIsNone(window.worker_thread)
        self.assertIsNone(window.cancel_event)

    def test_close_without_activity_accepts_immediately(self) -> None:
        from ductzip.gui.app import MainWindow

        window = MainWindow()
        window.close()
        self.assertIsNone(window.worker_thread)


if __name__ == "__main__":
    unittest.main()
