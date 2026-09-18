from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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


class _StubEngine:
    """Deterministic stand-in for the real 7-Zip engine in GUI tests.

    Real-backend GUI coverage is manual smoke evidence; spawning the real
    backend in unit tests is slow and environment-sensitive (antivirus
    scanning of child processes makes timings wildly nondeterministic).
    """

    entries: tuple = ()

    def __init__(self, *args, **kwargs):
        pass

    def list(self, archive_path, password=None, cancel_event=None):
        from ductzip.archive import ArchiveEntry, ArchiveListing

        return ArchiveListing(
            archive_path=Path(archive_path).resolve(),
            sevenzip_path=Path("7z.exe"),
            entries=tuple(self.entries),
            stdout="",
            stderr="",
        )


class _FailingEngine(_StubEngine):
    def list(self, archive_path, password=None, cancel_event=None):
        from ductzip.archive import CorruptedArchive

        raise CorruptedArchive()


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_initializes(self) -> None:
        from ductzip.gui.app import MainWindow

        window = MainWindow()

        self.assertEqual(window.windowTitle(), "DuctZip")
        self.assertEqual(window.policy_combo.count(), 3)
        self.assertEqual(window.conflict_strategy_combo.count(), 3)
        self.assertFalse(window.cancel_button.isEnabled())
        self.assertEqual(window.preview_table.columnCount(), 3)
        self.assertEqual(window.password_input.text(), "")
        self.assertFalse(window.open_output_button.isEnabled())
        self.assertTrue(window.smart_output_checkbox.isChecked())
        self.assertEqual(window.final_output_input.text(), "")
        self.assertEqual(window.conflict_label.text(), "No conflicts")

    def test_archive_selection_defaults_output_to_archive_parent(self) -> None:
        from unittest.mock import patch

        from ductzip.archive import ArchiveEntry
        from ductzip.gui import workers
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "sample.zip"
            archive.write_bytes(b"fake")
            window = MainWindow()

            class _Engine(_StubEngine):
                entries = (ArchiveEntry("hello.txt", 5, None, None, False),)

            with patch.object(workers, "SevenZipCliEngine", _Engine):
                window.archive_input.setText(str(archive))
                window.on_archive_selected(str(archive))

                self.assertTrue(
                    pump_events_until(
                        lambda: window.preview_table.rowCount() == 1 and not window._preview_busy
                    ),
                    "preview was not loaded",
                )
            self.assertEqual(window.output_input.text(), str(archive.parent))
            self.assertEqual(window.final_output_input.text(), str(archive.parent))
            window.close()

    def test_preview_failure_clears_preview_and_recovers(self) -> None:
        from unittest.mock import patch

        from ductzip.gui import workers
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "broken.zip"
            archive.write_bytes(b"fake")
            window = MainWindow()

            with patch.object(workers, "SevenZipCliEngine", _FailingEngine):
                window.archive_input.setText(str(archive))
                window.on_archive_selected(str(archive))

                self.assertTrue(
                    pump_events_until(lambda: not window._preview_busy),
                    "preview did not finish",
                )

            self.assertEqual(window.preview_table.rowCount(), 0)
            self.assertIn("Preview failed", window.log.toPlainText())
            window.close()

    def test_final_output_preview_matches_smart_policy_for_multiple_top_level(self) -> None:
        from ductzip.archive import ArchiveEntry
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "out"
            archive.write_bytes(b"fake")
            window = MainWindow()
            window.archive_input.setText(str(archive))
            window.output_input.setText(str(requested))
            window.preview_entries = (
                ArchiveEntry("a.txt", 3, None, None, False),
                ArchiveEntry("b.txt", 3, None, None, False),
            )

            window.update_final_output_dir()

            self.assertEqual(window.final_output_input.text(), str(requested / "photos"))

    def test_final_output_reflects_smart_output(self) -> None:
        from ductzip.archive import ArchiveEntry
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "photos"
            archive.write_bytes(b"fake")
            window = MainWindow()
            window.archive_input.setText(str(archive))
            window.output_input.setText(str(requested))
            window.preview_entries = (
                ArchiveEntry("photos", None, None, "D", True),
                ArchiveEntry("photos/a.jpg", 12, None, None, False),
            )

            window.update_final_output_dir()

            self.assertEqual(window.final_output_input.text(), str(root))

            window.smart_output_checkbox.setChecked(False)

            self.assertEqual(window.final_output_input.text(), str(requested))

    def test_conflict_summary_reflects_existing_targets(self) -> None:
        from ductzip.archive import ArchiveEntry
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "photos").mkdir()
            archive = root / "photos.zip"
            archive.write_bytes(b"fake")
            window = MainWindow()
            window.archive_input.setText(str(archive))
            window.output_input.setText(str(root))
            window.preview_entries = (
                ArchiveEntry("photos", None, None, "D", True),
                ArchiveEntry("photos/a.jpg", 12, None, None, False),
            )

            window.update_final_output_dir()

            self.assertIn("1 existing target", window.conflict_label.text())
            self.assertIn("photos", window.conflict_label.text())

    def test_archive_selection_loads_preview(self) -> None:
        from unittest.mock import patch

        from ductzip.archive import ArchiveEntry
        from ductzip.gui import workers
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "sample.zip"
            archive.write_bytes(b"fake")
            window = MainWindow()

            class _Engine(_StubEngine):
                entries = (ArchiveEntry("hello.txt", 5, None, None, False),)

            with patch.object(workers, "SevenZipCliEngine", _Engine):
                window.archive_input.setText(str(archive))
                window.on_archive_selected(str(archive))

                self.assertTrue(
                    pump_events_until(
                        lambda: window.preview_table.rowCount() == 1 and not window._preview_busy
                    ),
                    "preview was not loaded",
                )
            self.assertEqual(window.preview_table.item(0, 0).text(), "hello.txt")
            window.close()

    def test_password_visibility_toggle(self) -> None:
        from PySide6.QtWidgets import QLineEdit
        from ductzip.gui.app import MainWindow

        window = MainWindow()
        self.assertEqual(window.password_input.echoMode(), QLineEdit.Password)

        window.toggle_password_visibility(True)

        self.assertEqual(window.password_input.echoMode(), QLineEdit.Normal)

    def test_completed_extraction_enables_open_folder(self) -> None:
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            window = MainWindow()

            window.on_completed(temp)

            self.assertTrue(window.open_output_button.isEnabled())
            self.assertEqual(window.last_output_dir, Path(temp))

    def test_open_output_dir_uses_desktop_services(self) -> None:
        from ductzip.gui import app as gui_app

        with tempfile.TemporaryDirectory() as temp:
            window = gui_app.MainWindow()
            window.on_completed(temp)

            with patch.object(gui_app.QDesktopServices, "openUrl") as open_url:
                window.open_output_dir()

            open_url.assert_called_once()
            opened_url = open_url.call_args.args[0]
            self.assertTrue(opened_url.isLocalFile())
            self.assertEqual(Path(opened_url.toLocalFile()), Path(temp))


if __name__ == "__main__":
    unittest.main()
