"""Review company price differences before changing an existing project."""

from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)


class PricingRefreshDialog(QDialog):
    def __init__(self, preview, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review Company Price Refresh")
        self.resize(1060, 620)
        layout = QVBoxLayout(self)
        heading = QLabel("COMPANY PRICE REFRESH — REVIEW BEFORE APPLYING")
        heading.setObjectName("canvasTitle")
        layout.addWidget(heading)
        layout.addWidget(QLabel(
            f"Project currency: {preview.old_currency or 'unset'}    Proposed: {preview.proposed_currency or 'unset'}"
            f"    Company revision: {preview.source_revision}    Latest effective date: {preview.latest_effective_date or 'none'}"))
        self.table = QTableWidget(len(preview.changes), 7)
        self.table.setHorizontalHeaderLabels(
            ["Type", "ID", "Change", "Current rate / rule", "Proposed rate / rule", "Current effective", "Proposed effective"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for row, change in enumerate(preview.changes):
            for column, value in enumerate((change.kind, change.record_id, change.change,
                                            change.old_value, change.new_value,
                                            change.old_effective, change.new_effective)):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        layout.addWidget(self.table, 1)
        old_status = "INCOMPLETE" if preview.old_incomplete else "complete"
        new_status = "INCOMPLETE" if preview.proposed_incomplete else "complete"
        self.draft_label = QLabel(
            f"LIVE DRAFT: {preview.old_draft_total} ({old_status}) → {preview.proposed_draft_total} ({new_status})")
        self.draft_label.setObjectName("canvasTitle")
        layout.addWidget(self.draft_label)
        self.exceptions_label = QLabel(
            "Cabinet pricing exceptions preserved: " + (", ".join(preview.manual_exception_ids)
                                                       if preview.manual_exception_ids else "none"))
        layout.addWidget(self.exceptions_label)
        note = QLabel("Applying replaces this project's price-master snapshot with approved company records, "
                      "including removals shown above. Issued quotations remain frozen. "
                      "No cabinet dimensions, BOM formulas or manufacturing output are changed.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply reviewed prices")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
