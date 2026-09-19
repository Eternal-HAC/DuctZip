"""Settings dialog for the DuctZip GUI (v0.7).

Edits the same per-user ``Settings`` the CLI uses (``ductzip settings``);
both surfaces stay consistent. No passwords are ever part of settings.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from ..settings import CONFLICT_STRATEGIES, OVERWRITE_POLICIES, Settings

_SMART_LABELS = ("默认（开）", "开", "关")
_SMART_VALUES: tuple[bool | None, ...] = (None, True, False)


class SettingsDialog(QDialog):
    """Modal editor for durable preferences.

    ``result_settings()`` returns the edited values; the caller persists
    them with ``ductzip.settings.save_settings``.
    """

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("DuctZip 设置")
        self.setMinimumWidth(480)

        self.backend_input = QLineEdit(settings.sevenzip_path or "")
        self.backend_input.setPlaceholderText("留空则自动发现 7-Zip")
        browse_button = QPushButton("浏览…")
        browse_button.clicked.connect(self._browse_backend)

        backend_row = QHBoxLayout()
        backend_row.addWidget(self.backend_input, 1)
        backend_row.addWidget(browse_button)

        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItems(OVERWRITE_POLICIES)
        self.overwrite_combo.setCurrentText(settings.overwrite_policy)

        self.conflict_combo = QComboBox()
        self.conflict_combo.addItems(CONFLICT_STRATEGIES)
        self.conflict_combo.setCurrentText(settings.conflict_strategy)

        self.smart_combo = QComboBox()
        self.smart_combo.addItems(_SMART_LABELS)
        index = _SMART_VALUES.index(settings.smart_output)
        self.smart_combo.setCurrentIndex(index)

        form = QFormLayout()
        form.addRow("7-Zip 后端路径", backend_row)
        form.addRow("已存在文件默认处理", self.overwrite_combo)
        form.addRow("顶层冲突默认策略", self.conflict_combo)
        form.addRow("Smart output 默认", self.smart_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow(form)
        layout.addRow(buttons)

    def _browse_backend(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "选择 7-Zip 后端",
            self.backend_input.text() or str(Path.home()),
            "7-Zip (7z.exe 7zz.exe)",
        )
        if chosen:
            self.backend_input.setText(chosen)

    def _on_accept(self) -> None:
        backend = self.backend_input.text().strip()
        if backend and not Path(backend).is_file():
            QMessageBox.warning(self, "无效路径", f"7-Zip 后端不存在：\n{backend}")
            return
        self.accept()

    def result_settings(self) -> Settings:
        backend = self.backend_input.text().strip()
        return Settings(
            sevenzip_path=backend or None,
            overwrite_policy=self.overwrite_combo.currentText(),
            conflict_strategy=self.conflict_combo.currentText(),
            smart_output=_SMART_VALUES[self.smart_combo.currentIndex()],
        )
