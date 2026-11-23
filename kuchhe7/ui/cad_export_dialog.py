"""One CAD drawing selector; DWG remains unavailable without a genuine writer."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel

from ..engineering_dxf import (CNC_PROTOTYPE, FRONT_ELEVATIONS,
                               KITCHEN_LAYOUT, PANEL_OUTLINES, ROOM_PLAN)
from .engineering_export_dialog import EngineeringExportDialog


COMPLETE = "complete_kitchen"
WALL_ELEVATIONS = "wall_elevations"
SHEET_LAYOUT = "sheet_layout"
LEGACY_ELEVATION = "legacy_elevation"


class CadExportDialog(EngineeringExportDialog):
    def __init__(self, parent=None, *, sheet_available: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export CAD Drawing")
        self.drawing_combo.insertItem(0, "Complete Kitchen Drawing", COMPLETE)
        self.drawing_combo.addItem("Wall Elevations", WALL_ELEVATIONS)
        self.drawing_combo.addItem("Sheet Cutting Layout", SHEET_LAYOUT)
        self.drawing_combo.addItem("Legacy Cabinet Elevation", LEGACY_ELEVATION)
        if not sheet_available:
            index = self.drawing_combo.findData(SHEET_LAYOUT)
            self.drawing_combo.model().item(index).setEnabled(False)
            self.drawing_combo.setItemData(index,
                "Recalculate a current valid layout in Sheet Nesting first.",
                Qt.ItemDataRole.ToolTipRole)
        self.format_combo = QComboBox()
        self.format_combo.addItem("DXF · editable drawing", "dxf")
        self.format_combo.addItem("DWG · unavailable pending validated writer", "dwg")
        self.format_combo.model().item(1).setEnabled(False)
        format_form = QFormLayout()
        format_form.addRow("File format", self.format_combo)
        self.layout().insertLayout(1, format_form)
        self.dwg_note = QLabel("Genuine DWG is pending. A DXF will never be renamed as DWG.")
        self.dwg_note.setWordWrap(True)
        self.layout().insertWidget(2, self.dwg_note)
        self.drawing_combo.setCurrentIndex(0)
        self._refresh_mode()

    def _refresh_mode(self) -> None:
        super()._refresh_mode()
        if self.drawing_type in (COMPLETE, WALL_ELEVATIONS, SHEET_LAYOUT, LEGACY_ELEVATION):
            self.profile_panel.hide()
            self.warning.setText(
                "One millimetre DXF from the current project. Demonstration engineering only; "
                "CAM import and factory rules require client validation."
            )

    @property
    def drawing_format(self) -> str:
        return self.format_combo.currentData()
