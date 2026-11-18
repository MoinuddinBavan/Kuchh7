"""One native selection dialog for all engineering DXF drawing types."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ..engineering_dxf import CNC_PROTOTYPE, DRAWING_LABELS, DRAWING_TYPES, CncDxfProfile


class EngineeringExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Engineering Drawing Export — DXF")
        self.setMinimumWidth(510)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.drawing_combo = QComboBox()
        for drawing_type in DRAWING_TYPES:
            self.drawing_combo.addItem(DRAWING_LABELS[drawing_type], drawing_type)
        form.addRow("Drawing type", self.drawing_combo)
        layout.addLayout(form)
        self.profile_panel = QWidget()
        profile_form = QFormLayout(self.profile_panel)
        self.outline_layer_edit = QLineEdit("CNC_PANEL_OUTLINES")
        self.label_layer_edit = QLineEdit("CNC_LABELS")
        self.geometry_combo = QComboBox()
        self.geometry_combo.addItems(["LWPOLYLINE", "POLYLINE"])
        self.origin_x_spin = QDoubleSpinBox()
        self.origin_y_spin = QDoubleSpinBox()
        for widget in (self.origin_x_spin, self.origin_y_spin):
            widget.setRange(-1_000_000, 1_000_000)
            widget.setDecimals(1)
            widget.setSuffix(" mm")
        self.include_labels_check = QCheckBox("Add labels on separate annotation layer")
        profile_form.addRow("Outline layer", self.outline_layer_edit)
        profile_form.addRow("Label layer", self.label_layer_edit)
        profile_form.addRow("Geometry", self.geometry_combo)
        profile_form.addRow("Origin X", self.origin_x_spin)
        profile_form.addRow("Origin Y", self.origin_y_spin)
        profile_form.addRow("Annotations", self.include_labels_check)
        layout.addWidget(self.profile_panel)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #9A5635; font-weight: 600;")
        layout.addWidget(self.warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Choose DXF location…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.drawing_combo.currentIndexChanged.connect(self._refresh_mode)
        self._refresh_mode()

    @property
    def drawing_type(self) -> str:
        return self.drawing_combo.currentData()

    def cnc_profile(self) -> CncDxfProfile | None:
        if self.drawing_type != CNC_PROTOTYPE:
            return None
        return CncDxfProfile(
            outline_layer=self.outline_layer_edit.text().strip(),
            label_layer=self.label_layer_edit.text().strip(),
            origin_x_mm=self.origin_x_spin.value(),
            origin_y_mm=self.origin_y_spin.value(),
            geometry_type=self.geometry_combo.currentText(),
            include_labels=self.include_labels_check.isChecked(),
        )

    def _refresh_mode(self) -> None:
        cnc = self.drawing_type == CNC_PROTOTYPE
        self.profile_panel.setVisible(cnc)
        self.warning.setText(
            "Generic CNC-targeted DXF prototype only. No machine compatibility, drilling, "
            "toolpaths or production approval is claimed. Validate an exported file in the client's CAM software."
            if cnc else
            "Engineering drawings use project millimetres and illustrative cabinet construction data. "
            "Not approved for production."
        )
