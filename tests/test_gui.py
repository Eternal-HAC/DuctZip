from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
        self.assertFalse(window.cancel_button.isEnabled())
        self.assertEqual(window.preview_table.columnCount(), 3)
        self.assertEqual(window.password_input.text(), "")
        self.assertFalse(window.open_output_button.isEnabled())

    def test_archive_selection_suggests_output_directory(self) -> None:
        from ductzip.gui.app import MainWindow

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "sample.zip"
            archive.write_bytes(b"fake")
            window = MainWindow()

            window.on_archive_selected(str(archive))

            self.assertEqual(window.output_input.text(), str(archive.with_suffix("")))

    def test_archive_selection_loads_preview(self) -> None:
        from ductzip.archive import SevenZipMissing, find_sevenzip
        from ductzip.gui.app import MainWindow

        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "sample.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("hello.txt", "hello")
            window = MainWindow()

            window.archive_input.setText(str(archive))
            window.on_archive_selected(str(archive))

            self.assertEqual(window.preview_table.rowCount(), 1)
            self.assertEqual(window.preview_table.item(0, 0).text(), "hello.txt")

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
