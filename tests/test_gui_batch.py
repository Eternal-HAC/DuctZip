from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pump_events_until(condition, timeout_ms: int = 5_000) -> bool:
    """Process the Qt event loop until ``condition()`` is true or timeout."""
    from PySide6.QtCore import QElapsedTimer
    from PySide6.QtTest import QTest

    timer = QElapsedTimer()
    timer.start()
    while not condition():
        if timer.hasExpired(timeout_ms):
            return False
        QTest.qWait(20)
    return True


class _BatchStubEngine:
    """Deterministic engine stand-in: every archive extracts instantly."""

    def __init__(self, *args, **kwargs):
        pass

    def list(self, archive_path, password=None, cancel_event=None):
        from ductzip.archive import ArchiveEntry, ArchiveListing

        return ArchiveListing(
            archive_path=Path(archive_path).resolve(),
            sevenzip_path=Path("7z.exe"),
            entries=(ArchiveEntry("hello.txt", 5, None, None, False),),
            stdout="",
            stderr="",
        )

    def extract_with_progress(
        self,
        archive_path,
        output_dir,
        password=None,
        cancel_event=None,
        overwrite_policy="skip",
    ):
        from ductzip.archive import ExtractResult, ProgressEvent

        yield ProgressEvent(kind="started", percent=0, message=str(archive_path))
        yield ProgressEvent(kind="progress", percent=50)
        yield ProgressEvent(
            kind="completed",
            percent=100,
            result=ExtractResult(
                archive_path=Path(archive_path),
                output_dir=Path(output_dir),
                sevenzip_path=Path("7z.exe"),
                stdout="",
                stderr="",
            ),
        )


class _MixedEngine(_BatchStubEngine):
    """Archives whose name contains ``bad`` fail; the rest succeed."""

    def extract_with_progress(self, archive_path, output_dir, **kwargs):
        from ductzip.archive import ArchiveError

        if "bad" in Path(archive_path).name:
            raise ArchiveError("boom")
        yield from super().extract_with_progress(archive_path, output_dir, **kwargs)


class _FlakyEngine(_BatchStubEngine):
    """Fails the first extraction attempt of each archive, then succeeds."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts: dict[str, int] = {}

    def extract_with_progress(self, archive_path, output_dir, **kwargs):
        from ductzip.archive import ArchiveError

        key = str(archive_path)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if self.attempts[key] < 2:
            raise ArchiveError("flaky backend")
        yield from super().extract_with_progress(archive_path, output_dir, **kwargs)


class _BlockingEngine(_BatchStubEngine):
    """Holds the current task open until the queue cancels it."""

    def extract_with_progress(self, archive_path, output_dir, cancel_event=None, **kwargs):
        from ductzip.archive import ArchiveCancelled, ProgressEvent

        yield ProgressEvent(kind="started", percent=0)
        while cancel_event is not None and not cancel_event.is_set():
            time.sleep(0.01)
        raise ArchiveCancelled()


def _make_archive(directory: Path, name: str) -> Path:
    archive = directory / name
    archive.write_bytes(b"fake")
    return archive


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class GuiBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        from ductzip.gui.app import MainWindow

        return MainWindow()

    def _run_batch(self, window) -> bool:
        window.start_batch()
        return pump_events_until(
            lambda: not window._batch_running and window.batch_thread is None,
            timeout_ms=8_000,
        )

    # ------------------------------------------------------------------ adding

    def test_files_dropped_signal_adds_archives_to_queue(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = _make_archive(root, "a.zip")
            second = _make_archive(root, "b.zip")
            window = self._window()

            with patch.object(workers, "SevenZipCliEngine", _BatchStubEngine):
                window.archive_input.filesDropped.emit([str(first), str(second)])

            self.assertEqual(window.task_list.count(), 2)
            self.assertIsNotNone(window.batch_queue)
            self.assertEqual(len(window.batch_queue.tasks), 2)
            window.close()

    def test_add_batch_skips_non_files(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            real = _make_archive(root, "a.zip")
            window = self._window()

            with patch.object(workers, "SevenZipCliEngine", _BatchStubEngine):
                added = window.add_batch_archives([str(real), str(root / "missing.zip")])

            self.assertEqual(added, 1)
            self.assertEqual(window.task_list.count(), 1)
            self.assertIn("skipping", window.log.toPlainText())
            window.close()

    # ------------------------------------------------------------------ running

    def test_batch_run_completes_and_shows_final_dirs(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "out"
            first = _make_archive(root, "a.zip")
            second = _make_archive(root, "b.zip")
            window = self._window()
            window.output_input.setText(str(out))

            with patch.object(workers, "SevenZipCliEngine", _BatchStubEngine):
                window.add_batch_archives([str(first), str(second)])
                self.assertTrue(self._run_batch(window), "batch did not finish")

            states = {task.archive_path.name: task.state for task in window.batch_queue.tasks}
            self.assertEqual(states, {"a.zip": "completed", "b.zip": "completed"})
            labels = [window.task_list.item(i).text() for i in range(window.task_list.count())]
            for label in labels:
                self.assertIn("Completed", label)
                self.assertIn(str(out), label)
            # Nothing queued or running left: the batch action buttons reset.
            self.assertFalse(window.start_batch_button.isEnabled())
            self.assertFalse(window.cancel_current_button.isEnabled())
            self.assertFalse(window.cancel_all_button.isEnabled())
            window.close()

    def test_batch_mixed_success_and_failure_isolated(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = _make_archive(root, "good.zip")
            bad = _make_archive(root, "bad.zip")
            window = self._window()

            with patch.object(workers, "SevenZipCliEngine", _MixedEngine):
                window.add_batch_archives([str(good), str(bad)])
                self.assertTrue(self._run_batch(window), "batch did not finish")

            states = {task.archive_path.name: task.state for task in window.batch_queue.tasks}
            self.assertEqual(states, {"good.zip": "completed", "bad.zip": "failed"})
            labels = {window.task_list.item(i).text() for i in range(window.task_list.count())}
            self.assertTrue(any("Failed" in label and "boom" in label for label in labels))
            self.assertTrue(any("Completed" in label for label in labels))
            # A failed batch leaves the start button disabled (nothing queued)
            # but the failed task retryable.
            selected = window.task_list.item(1)
            window.task_list.setCurrentItem(selected)
            self.assertTrue(window.retry_task_button.isEnabled())
            window.close()

    def test_retry_recovers_flaky_task(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = _make_archive(root, "flaky.zip")
            window = self._window()

            with patch.object(workers, "SevenZipCliEngine", _FlakyEngine):
                window.add_batch_archives([str(archive)])
                self.assertTrue(self._run_batch(window), "first run did not finish")
                self.assertEqual(window.batch_queue.tasks[0].state, "failed")

                window.task_list.setCurrentItem(window.task_list.item(0))
                self.assertTrue(window.retry_task_button.isEnabled())
                window.retry_selected_task()
                self.assertEqual(window.batch_queue.tasks[0].state, "queued")

                self.assertTrue(self._run_batch(window), "second run did not finish")

            self.assertEqual(window.batch_queue.tasks[0].state, "completed")
            self.assertIn("Completed", window.task_list.item(0).text())
            window.close()

    # ------------------------------------------------------- cancel and remove

    def test_cancel_all_stops_batch_and_reaps_thread(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = _make_archive(root, "a.zip")
            second = _make_archive(root, "b.zip")
            window = self._window()

            with patch.object(workers, "SevenZipCliEngine", _BlockingEngine):
                window.add_batch_archives([str(first), str(second)])
                window.start_batch()
                self.assertTrue(pump_events_until(lambda: window._batch_running))
                # Let the first task reach its blocking extraction.
                self.assertTrue(
                    pump_events_until(
                        lambda: window.batch_queue.tasks[0].state == "running", timeout_ms=2_000
                    ),
                    "first task did not start running",
                )

                window.cancel_all_batch()

                self.assertTrue(
                    pump_events_until(
                        lambda: not window._batch_running and window.batch_thread is None,
                        timeout_ms=8_000,
                    ),
                    "batch thread was not reaped after cancel-all",
                )

            states = {task.archive_path.name: task.state for task in window.batch_queue.tasks}
            self.assertEqual(states, {"a.zip": "cancelled", "b.zip": "cancelled"})
            self.assertFalse(window._batch_running)
            window.close()

    def test_remove_queued_task_and_illegal_remove_of_running(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = _make_archive(root, "a.zip")
            second = _make_archive(root, "b.zip")
            window = self._window()

            with patch.object(workers, "SevenZipCliEngine", _BlockingEngine):
                window.add_batch_archives([str(first), str(second)])
                # Remove the queued second task before running.
                window.task_list.setCurrentItem(window.task_list.item(1))
                self.assertTrue(window.remove_task_button.isEnabled())
                window.remove_selected_task()
                self.assertEqual(window.task_list.count(), 1)
                self.assertEqual(len(window.batch_queue.tasks), 1)

                window.start_batch()
                self.assertTrue(
                    pump_events_until(lambda: window.batch_queue.tasks[0].state == "running"),
                    "task did not start running",
                )
                # The running task cannot be removed: the queue refuses, the
                # item survives, and the refusal reaches the log.
                window.task_list.setCurrentItem(window.task_list.item(0))
                window.remove_selected_task()
                self.assertEqual(window.task_list.count(), 1)
                self.assertEqual(window.batch_queue.tasks[0].state, "running")
                self.assertIn("不能移除", window.log.toPlainText())
                window.cancel_all_batch()
                pump_events_until(lambda: not window._batch_running, timeout_ms=8_000)

            self.assertEqual(window.batch_queue.tasks[0].state, "cancelled")
            window.close()

    # -------------------------------------------------------------- visibility

    def test_open_task_output_uses_desktop_services(self) -> None:
        from ductzip.gui import app as gui_app
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "out"
            archive = _make_archive(root, "a.zip")
            window = self._window()
            window.output_input.setText(str(out))

            with patch.object(workers, "SevenZipCliEngine", _BatchStubEngine):
                window.add_batch_archives([str(archive)])
                self.assertTrue(self._run_batch(window), "batch did not finish")

            with patch.object(gui_app.QDesktopServices, "openUrl") as open_url:
                window.open_task_output(window.task_list.item(0))

            open_url.assert_called_once()
            opened_url = open_url.call_args.args[0]
            self.assertTrue(opened_url.isLocalFile())
            self.assertEqual(Path(opened_url.toLocalFile()), window.batch_queue.tasks[0].final_output_dir)
            window.close()

    def test_close_during_batch_shuts_down_bounded(self) -> None:
        from ductzip.gui import workers

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = _make_archive(root, "a.zip")
            window = self._window()

            with patch.object(workers, "SevenZipCliEngine", _BlockingEngine):
                window.add_batch_archives([str(first)])
                window.start_batch()
                self.assertTrue(
                    pump_events_until(lambda: window.batch_queue.tasks[0].state == "running"),
                    "task did not start running",
                )

                window.close()  # closeEvent cancels all and pumps until reaped

                self.assertTrue(
                    pump_events_until(lambda: not window._batch_running, timeout_ms=8_000),
                    "batch did not shut down after close",
                )

            self.assertEqual(window.batch_queue.tasks[0].state, "cancelled")
            thread = window.batch_thread
            self.assertTrue(thread is None or not thread.isRunning())


if __name__ == "__main__":
    unittest.main()
