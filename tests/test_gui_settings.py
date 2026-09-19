"""GUI settings tests (v0.7): the settings dialog, window-level default
application, corrupt-recovery surfacing, and the save path."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tests.settings_harness  # noqa: F401  # forces a throwaway settings path
from ductzip.settings import Settings, load_settings, save_settings, settings_path


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _make_dialog(self, settings: Settings):
        from ductzip.gui.settings_dialog import SettingsDialog

        return SettingsDialog(settings)

    def test_dialog_reflects_given_settings(self) -> None:
        dialog = self._make_dialog(
            Settings(overwrite_policy="rename", conflict_strategy="cancel", smart_output=False)
        )
        self.assertEqual(dialog.overwrite_combo.currentText(), "rename")
        self.assertEqual(dialog.conflict_combo.currentText(), "cancel")
        self.assertEqual(dialog.smart_combo.currentText(), "关")
        self.assertEqual(dialog.backend_input.text(), "")

    def test_dialog_smart_output_three_states(self) -> None:
        from ductzip.gui.settings_dialog import _SMART_LABELS, _SMART_VALUES

        self.assertEqual(len(_SMART_LABELS), 3)
        self.assertEqual(_SMART_VALUES, (None, True, False))
        for label, value in zip(_SMART_LABELS, _SMART_VALUES):
            dialog = self._make_dialog(Settings(smart_output=value))
            self.assertEqual(dialog.smart_combo.currentText(), label)
            self.assertEqual(dialog.result_settings().smart_output, value)

    def test_result_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = Path(temp) / "7z.exe"
            backend.write_bytes(b"fake")
            dialog = self._make_dialog(Settings())
            dialog.backend_input.setText(str(backend))
            dialog.overwrite_combo.setCurrentText("overwrite")
            dialog.conflict_combo.setCurrentText("rename")
            dialog.smart_combo.setCurrentText("开")
            self.assertEqual(
                dialog.result_settings(),
                Settings(
                    sevenzip_path=str(backend),
                    overwrite_policy="overwrite",
                    conflict_strategy="rename",
                    smart_output=True,
                ),
            )

    def test_accept_rejects_missing_backend_path(self) -> None:
        from PySide6.QtWidgets import QDialog

        dialog = self._make_dialog(Settings())
        dialog.backend_input.setText(r"C:\no\such\7z.exe")
        with patch("ductzip.gui.settings_dialog.QMessageBox.warning") as warning:
            dialog._on_accept()
        warning.assert_called_once()
        self.assertEqual(dialog.result(), QDialog.Rejected)

    def test_empty_backend_path_means_unset(self) -> None:
        dialog = self._make_dialog(Settings(smart_output=True))
        dialog.smart_combo.setCurrentText("默认（开）")
        self.assertIsNone(dialog.result_settings().sevenzip_path)
        self.assertIsNone(dialog.result_settings().smart_output)


class WindowSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        path = settings_path()
        if path.is_file():
            path.unlink()
        backup = path.with_name(path.name + ".corrupt")
        if backup.is_file():
            backup.unlink()

    def _make_window(self):
        from ductzip.gui.app import MainWindow

        return MainWindow()

    def test_window_applies_saved_defaults(self) -> None:
        save_settings(Settings(overwrite_policy="rename", conflict_strategy="cancel", smart_output=False))
        window = self._make_window()
        try:
            self.assertFalse(window.smart_output_checkbox.isChecked())
            self.assertEqual(window.policy_combo.currentText(), "rename")
            self.assertEqual(window.conflict_strategy_combo.currentText(), "cancel")
        finally:
            window.deleteLater()

    def test_window_unset_smart_output_uses_gui_builtin(self) -> None:
        save_settings(Settings(smart_output=None))
        window = self._make_window()
        try:
            self.assertTrue(window.smart_output_checkbox.isChecked())
        finally:
            window.deleteLater()

    def test_window_survives_corrupt_settings(self) -> None:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json at all", encoding="utf-8")
        window = self._make_window()
        try:
            self.assertTrue(window.smart_output_checkbox.isChecked())
            self.assertEqual(window.policy_combo.currentText(), "skip")
            self.assertIn("损坏", window.log.toPlainText())
        finally:
            window.deleteLater()

    def test_open_settings_persists_and_applies(self) -> None:
        window = self._make_window()
        try:
            updated = Settings(overwrite_policy="overwrite", conflict_strategy="rename", smart_output=False)
            fake_dialog = unittest.mock.Mock()
            fake_dialog.exec.return_value = 1  # QDialog.Accepted
            fake_dialog.result_settings.return_value = updated
            with patch("ductzip.gui.app.SettingsDialog", return_value=fake_dialog):
                window.open_settings()
            loaded = load_settings()
            self.assertEqual(loaded.settings.overwrite_policy, "overwrite")
            self.assertEqual(window.policy_combo.currentText(), "overwrite")
            self.assertFalse(window.smart_output_checkbox.isChecked())
            self.assertIn("设置已保存", window.log.toPlainText())
        finally:
            window.deleteLater()

    def test_effective_sevenzip_uses_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = Path(temp) / "7z.exe"
            backend.write_bytes(b"fake")
            save_settings(Settings(sevenzip_path=str(backend)))
            window = self._make_window()
            try:
                self.assertEqual(window._effective_sevenzip(), str(backend))
            finally:
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
