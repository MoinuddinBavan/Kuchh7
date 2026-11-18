"""Review-only design proposal workspace; editing stays in the main 2D studio."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..ai_design import DesignProposal
from ..catalogue import get_catalogue_item
from ..product_libraries import get_product
from .cad_views import RoomPlanView


class AIDesignWorkspace(QWidget):
    def __init__(self, generate_callback, apply_callback, reject_callback, parent=None) -> None:
        super().__init__(parent)
        self._generate_callback = generate_callback
        self._apply_callback = apply_callback
        self._reject_callback = reject_callback
        self.proposal: DesignProposal | None = None
        outer = QVBoxLayout(self)
        heading = QLabel("DESIGN ASSISTANT")
        heading.setObjectName("canvasTitle")
        outer.addWidget(heading)
        self.mode_label = QLabel("Local rule-based demonstration — not AI generation unless a service is configured.")
        self.mode_label.setStyleSheet("color: #147D83; font-weight: 600;")
        outer.addWidget(self.mode_label)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        outer.addWidget(split, 1)

        left = QWidget()
        controls = QVBoxLayout(left)
        controls.addWidget(QLabel("Describe the kitchen using catalogue products, finishes and layout style:"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("Example: Modern L-shaped kitchen in Cashmere with a sink cabinet, wall cabinet and plant")
        self.prompt_edit.setMaximumHeight(120)
        controls.addWidget(self.prompt_edit)
        choice = QHBoxLayout()
        choice.addWidget(QLabel("Apply mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Replace current furniture layout", "replace")
        self.mode_combo.addItem("Add to current layout", "add")
        choice.addWidget(self.mode_combo, 1)
        controls.addLayout(choice)
        self.generate_button = QPushButton("Generate proposal")
        self.generate_button.clicked.connect(
            lambda: self._generate_callback(self.prompt_edit.toPlainText(), self.mode_combo.currentData())
        )
        controls.addWidget(self.generate_button)
        self.summary_label = QLabel("No proposal yet. Generating does not alter the project.")
        self.summary_label.setWordWrap(True)
        controls.addWidget(self.summary_label)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Catalogue model", "X", "Y", "Z", "W × D × H (mm)", "Finish"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        controls.addWidget(self.table, 1)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #A03E35; font-weight: 600;")
        controls.addWidget(self.warning_label)
        actions = QHBoxLayout()
        self.apply_button = QPushButton("Apply validated proposal")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_callback)
        self.reject_button = QPushButton("Reject proposal")
        self.reject_button.setEnabled(False)
        self.reject_button.clicked.connect(self._reject_callback)
        actions.addWidget(self.apply_button)
        actions.addWidget(self.reject_button)
        controls.addLayout(actions)
        split.addWidget(left)

        right = QWidget()
        preview_layout = QVBoxLayout(right)
        preview_layout.addWidget(QLabel("PROPOSED 2D PLAN — review before applying"))
        self.preview = RoomPlanView()
        self.preview.setEnabled(False)
        self._clear_preview()
        preview_layout.addWidget(self.preview, 1)
        split.addWidget(right)
        split.setSizes([590, 700])

    def show_proposal(self, proposal: DesignProposal) -> None:
        self.proposal = proposal
        self.mode_label.setText(proposal.source)
        self.summary_label.setText(
            f"{proposal.intent.layout} · {len(proposal.items)} validated item(s) · "
            f"{proposal.mode.title()} mode. {proposal.intent.explanation}"
        )
        self.table.setRowCount(len(proposal.items))
        for row, item in enumerate(proposal.items):
            try:
                name = get_catalogue_item(item.type_id).name
            except ValueError:
                name = get_product(item.type_id).name
            values = (item.item_id, name, item.x, item.y, item.z,
                      f"{item.width} × {item.depth} × {item.height}", item.finish)
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.warning_label.setText("\n".join(f"• {warning}" for warning in proposal.warnings)
                                   if proposal.warnings else "All proposed items passed local geometry checks.")
        self.apply_button.setEnabled(proposal.can_apply)
        self.reject_button.setEnabled(True)
        project = proposal.after_project
        self.preview.redraw(project.room, project.cabinets, project.selected_cabinet_id,
                            None, "WEST", project.placed_products, None)

    def clear_proposal(self, message: str = "Proposal rejected; project unchanged.") -> None:
        self.proposal = None
        self.table.setRowCount(0)
        self.summary_label.setText(message)
        self.warning_label.clear()
        self.apply_button.setEnabled(False)
        self.reject_button.setEnabled(False)
        self._clear_preview()

    def _clear_preview(self) -> None:
        scene = self.preview.scene()
        scene.clear()
        note = scene.addText("Generate a proposal to preview its 2D layout.")
        note.setDefaultTextColor(Qt.GlobalColor.darkGray)
        note.setPos(30, 40)
        scene.setSceneRect(0, 0, 650, 500)
