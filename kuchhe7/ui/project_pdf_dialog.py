"""Compact options for the five-section project document."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QLabel, QVBoxLayout)

from ..project_pdf import ProjectPdfOptions, SECTIONS


class ProjectPdfDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Project PDF")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        section_group = QGroupBox("Include sections")
        sections = QVBoxLayout(section_group)
        self.section_checks = {}
        for key, title in SECTIONS:
            check = QCheckBox(title)
            check.setChecked(True)
            sections.addWidget(check)
            self.section_checks[key] = check
            check.toggled.connect(self._update_export_enabled)
        layout.addWidget(section_group)
        settings = QFormLayout()
        self.paper_combo = QComboBox()
        self.paper_combo.addItems(["A3 landscape", "A4 landscape"])
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["High resolution", "Standard resolution"])
        settings.addRow("Paper", self.paper_combo)
        settings.addRow("3D quality", self.quality_combo)
        layout.addLayout(settings)
        self.panel_check = QCheckBox("Include Individual Panel Drawings")
        layout.addWidget(self.panel_check)
        self.note = QLabel("One PDF · project geometry in millimetres · illustrative engineering, not factory approved.")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export PDF…")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _update_export_enabled(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            any(check.isChecked() for check in self.section_checks.values()))

    def options(self) -> ProjectPdfOptions:
        return ProjectPdfOptions(
            sections=tuple(key for key, _ in SECTIONS if self.section_checks[key].isChecked()),
            paper=self.paper_combo.currentText().split()[0],
            quality=self.quality_combo.currentText(),
            include_panels=self.panel_check.isChecked(),
        )
