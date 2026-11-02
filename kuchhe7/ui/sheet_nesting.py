from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..bom import generate_project_bom
from ..models import Project
from ..nesting import NestingGroup, NestingResult, PlacedPanel, SheetSettings, nest_project


DISCLAIMER = "Demonstration nesting layout only. Not approved for CNC cutting or factory use."

MATERIAL_COLOURS = {
    "Warm White": "#E8E5DE",
    "Cashmere": "#BDB2A5",
    "Natural Oak": "#B99568",
    "Walnut": "#82624D",
    "Graphite": "#61676B",
    "Drawer board": "#C6CDD1",
}


def _project_nesting_signature(project: Project) -> tuple:
    return tuple(
        (
            cabinet.cabinet_id,
            cabinet.cabinet_type_id,
            cabinet.width,
            cabinet.height,
            cabinet.depth,
            cabinet.board_thickness,
            cabinet.door_count,
            cabinet.drawer_count,
            cabinet.shelf_count,
            cabinet.material,
        )
        for cabinet in project.cabinets
    )


class SheetLayoutView(QGraphicsView):
    partSelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nestingSheetView")
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QColor("#EEF2F4"))
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.selectionChanged.connect(self._selection_changed)
        self._placements: list[PlacedPanel] = []

    def show_sheet(self, group: NestingGroup | None, sheet_index: int, settings: SheetSettings) -> None:
        self._scene.clear()
        self._placements = []
        sheet_rect = self._scene.addRect(
            0,
            0,
            settings.length_mm,
            settings.width_mm,
            QPen(QColor("#172A3C"), 5),
            QColor("#FCFCFA"),
        )
        sheet_rect.setZValue(-10)
        margin_pen = QPen(QColor("#9CAAB3"), 2, Qt.PenStyle.DashLine)
        self._scene.addRect(
            settings.margin_mm,
            settings.margin_mm,
            settings.length_mm - 2 * settings.margin_mm,
            settings.width_mm - 2 * settings.margin_mm,
            margin_pen,
        ).setZValue(-5)

        if group is not None and 0 <= sheet_index < len(group.sheets):
            sheet = group.sheets[sheet_index]
            self._placements = list(sheet.placements)
            base = QColor(MATERIAL_COLOURS.get(group.material, "#91B9BC"))
            for index, placement in enumerate(sheet.placements):
                colour = base.lighter(103 + (index % 3) * 7)
                rect = QGraphicsRectItem(
                    placement.x_mm,
                    placement.y_mm,
                    placement.placed_length_mm,
                    placement.placed_width_mm,
                )
                rect.setPen(QPen(QColor("#23414D"), 2))
                rect.setBrush(colour)
                rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                rect.setData(0, index)
                self._scene.addItem(rect)

                label_text = (
                    f"{placement.panel.cabinet_id} | {placement.panel.component_name} "
                    f"#{placement.panel.instance_number}\n"
                    f"{placement.panel.length_mm:g} x {placement.panel.width_mm:g} mm"
                    f"{' | ROT 90' if placement.rotated else ''}"
                )
                label = self._scene.addText(label_text, QFont("Segoe UI", 19, QFont.Weight.DemiBold))
                label.setDefaultTextColor(QColor("#172A3C"))
                label.setTextWidth(max(80, placement.placed_length_mm - 18))
                label.setPos(placement.x_mm + 9, placement.y_mm + 6)
                label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                if label.boundingRect().height() > placement.placed_width_mm - 8:
                    label.setVisible(False)

        title = self._scene.addText(
            f"Sheet {sheet_index + 1 if group and group.sheets else 0}  |  "
            f"{settings.length_mm:g} x {settings.width_mm:g} mm  |  margin {settings.margin_mm:g} mm",
            QFont("Segoe UI", 24, QFont.Weight.Bold),
        )
        title.setDefaultTextColor(QColor("#172A3C"))
        title.setPos(20, -58)
        self._scene.setSceneRect(-35, -75, settings.length_mm + 70, settings.width_mm + 110)
        self.fit_sheet()

    def fit_sheet(self) -> None:
        if not self._scene.sceneRect().isEmpty():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.fit_sheet()

    def _selection_changed(self) -> None:
        selected = self._scene.selectedItems()
        if not selected:
            self.partSelected.emit(None)
            return
        index = selected[0].data(0)
        if isinstance(index, int) and 0 <= index < len(self._placements):
            self.partSelected.emit(self._placements[index])


class SheetNestingWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: Project | None = None
        self.result: NestingResult | None = None
        self._generated_signature: tuple | None = None
        self._selected_group_index = 0
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(7)

        header = QFrame()
        header.setObjectName("nestingHeader")
        header_layout = QHBoxLayout(header)
        title_box = QVBoxLayout()
        title = QLabel("DEMONSTRATION SHEET NESTING")
        title.setObjectName("nestingTitle")
        subtitle = QLabel("Authoritative BOM panels grouped by material and thickness")
        subtitle.setObjectName("canvasSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box, 1)
        self.completeness_label = QLabel("Layout complete")
        self.completeness_label.setObjectName("nestingCompletenessBadge")
        header_layout.addWidget(self.completeness_label)
        self.stale_label = QLabel("Layout current")
        self.stale_label.setObjectName("nestingStatusBadge")
        header_layout.addWidget(self.stale_label)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("nestingSplitter")
        splitter.setChildrenCollapsible(False)

        controls_panel = QFrame()
        controls_panel.setObjectName("nestingPanel")
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.addWidget(self._section_label("MATERIAL / THICKNESS GROUPS"))
        self.group_list = QListWidget()
        self.group_list.setAlternatingRowColors(True)
        self.group_list.setWordWrap(True)
        self.group_list.setSpacing(1)
        self.group_list.currentRowChanged.connect(self._group_changed)
        controls_layout.addWidget(self.group_list, 1)

        settings_group = QGroupBox("Example sheet settings")
        settings_form = QFormLayout(settings_group)
        self.sheet_length_spin = self._dimension_spin(2440, 300, 6000)
        self.sheet_width_spin = self._dimension_spin(1220, 300, 3000)
        self.kerf_spin = self._double_spin(3, 0, 20)
        self.margin_spin = self._double_spin(10, 0, 100)
        self.rotation_check = QCheckBox("Allow 90-degree rotation")
        self.rotation_check.setChecked(True)
        self.grain_check = QCheckBox("Restrict rotation for grain direction")
        self.grain_check.setToolTip("User-controlled demonstration rule; finish names do not infer grain direction")
        self.sheet_length_spin.valueChanged.connect(self._settings_changed)
        self.sheet_width_spin.valueChanged.connect(self._settings_changed)
        self.kerf_spin.valueChanged.connect(self._settings_changed)
        self.margin_spin.valueChanged.connect(self._settings_changed)
        self.rotation_check.toggled.connect(self._settings_changed)
        self.grain_check.toggled.connect(self._settings_changed)
        settings_form.addRow("Sheet length", self.sheet_length_spin)
        settings_form.addRow("Sheet width", self.sheet_width_spin)
        settings_form.addRow("Saw kerf", self.kerf_spin)
        settings_form.addRow("Edge margin", self.margin_spin)
        settings_form.addRow(self.rotation_check)
        settings_form.addRow(self.grain_check)
        controls_layout.addWidget(settings_group)
        self.recalculate_button = QPushButton("Recalculate nesting")
        self.recalculate_button.setObjectName("primaryButton")
        self.recalculate_button.clicked.connect(self.recalculate)
        controls_layout.addWidget(self.recalculate_button)
        splitter.addWidget(controls_panel)

        drawing_panel = QFrame()
        drawing_panel.setObjectName("nestingPanel")
        drawing_layout = QVBoxLayout(drawing_panel)
        drawing_layout.setContentsMargins(9, 9, 9, 9)
        sheet_bar = QHBoxLayout()
        sheet_bar.addWidget(self._section_label("SHEET LAYOUT"))
        sheet_bar.addStretch(1)
        self.sheet_combo = QComboBox()
        self.sheet_combo.currentIndexChanged.connect(self._sheet_changed)
        sheet_bar.addWidget(QLabel("Sheet"))
        sheet_bar.addWidget(self.sheet_combo)
        fit_button = QPushButton("Zoom to fit")
        fit_button.clicked.connect(self._fit_sheet)
        sheet_bar.addWidget(fit_button)
        drawing_layout.addLayout(sheet_bar)
        self.sheet_view = SheetLayoutView()
        self.sheet_view.partSelected.connect(self._part_selected)
        drawing_layout.addWidget(self.sheet_view, 1)
        self.sheet_summary = QLabel()
        self.sheet_summary.setObjectName("nestingSheetSummary")
        drawing_layout.addWidget(self.sheet_summary)
        splitter.addWidget(drawing_panel)

        details_panel = QFrame()
        details_panel.setObjectName("nestingPanel")
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(10, 10, 10, 10)
        stats_group = QGroupBox("Layout statistics")
        stats_form = QFormLayout(stats_group)
        self.stat_eligible = QLabel("0")
        self.stat_placed = QLabel("0")
        self.stat_unplaced = QLabel("0")
        self.stat_sheets = QLabel("0")
        self.stat_total_area = QLabel("0.000 m²")
        self.stat_placed_area = QLabel("0.000 m²")
        self.stat_unplaced_area = QLabel("0.000 m²")
        self.stat_area = self.stat_total_area
        self.stat_utilization = QLabel("0.0%")
        self.stat_utilization.setObjectName("utilizationValue")
        stats_form.addRow("Eligible panels", self.stat_eligible)
        stats_form.addRow("Placed panels", self.stat_placed)
        stats_form.addRow("Unplaced panels", self.stat_unplaced)
        stats_form.addRow("Used sheets", self.stat_sheets)
        stats_form.addRow("Eligible panel area", self.stat_total_area)
        stats_form.addRow("Placed panel area", self.stat_placed_area)
        stats_form.addRow("Unplaced panel area", self.stat_unplaced_area)
        stats_form.addRow("Allocated-sheet utilization", self.stat_utilization)
        details_layout.addWidget(stats_group)

        part_group = QGroupBox("Selected part")
        part_form = QFormLayout(part_group)
        self.part_cabinet = QLabel("—")
        self.part_name = QLabel("—")
        self.part_instance = QLabel("—")
        self.part_dimensions = QLabel("—")
        self.part_material = QLabel("—")
        self.part_thickness = QLabel("—")
        self.part_orientation = QLabel("—")
        part_form.addRow("Cabinet ID", self.part_cabinet)
        part_form.addRow("Component", self.part_name)
        part_form.addRow("Instance", self.part_instance)
        part_form.addRow("Original size", self.part_dimensions)
        part_form.addRow("Material", self.part_material)
        part_form.addRow("Thickness", self.part_thickness)
        part_form.addRow("Orientation", self.part_orientation)
        details_layout.addWidget(part_group)

        details_layout.addWidget(self._section_label("UNPLACED PARTS / WARNINGS"))
        self.warning_list = QListWidget()
        self.warning_list.setWordWrap(True)
        details_layout.addWidget(self.warning_list, 1)
        splitter.addWidget(details_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([290, 820, 310])
        root.addWidget(splitter, 1)

        self.disclaimer_label = QLabel(DISCLAIMER)
        self.disclaimer_label.setObjectName("nestingDisclaimer")
        root.addWidget(self.disclaimer_label)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    @staticmethod
    def _dimension_spin(value: int, minimum: int, maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(" mm")
        spin.setSingleStep(10)
        return spin

    @staticmethod
    def _double_spin(value: float, minimum: float, maximum: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setValue(value)
        spin.setSuffix(" mm")
        spin.setSingleStep(0.5)
        return spin

    def current_settings(self) -> SheetSettings:
        return SheetSettings(
            length_mm=self.sheet_length_spin.value(),
            width_mm=self.sheet_width_spin.value(),
            kerf_mm=self.kerf_spin.value(),
            margin_mm=self.margin_spin.value(),
            allow_rotation=self.rotation_check.isChecked(),
            grain_rotation_restricted=self.grain_check.isChecked(),
        )

    def set_project(self, project: Project, force: bool = False) -> None:
        self.project = project
        signature = _project_nesting_signature(project)
        if self.result is None or force or not project.cabinets:
            self.recalculate()
        elif signature != self._generated_signature:
            self._mark_stale("Project changed — recalculate")

    def _settings_changed(self, *_args) -> None:
        if self.result is not None:
            self._mark_stale("Settings changed — recalculate")

    def _mark_stale(self, message: str) -> None:
        self.stale_label.setText(message)
        self.stale_label.setProperty("stale", True)
        self.stale_label.style().unpolish(self.stale_label)
        self.stale_label.style().polish(self.stale_label)

    def recalculate(self) -> None:
        if self.project is None:
            return
        try:
            self.result = nest_project(self.project, self.current_settings())
        except ValueError as error:
            self.warning_list.clear()
            self.warning_list.addItem(str(error))
            return
        self._generated_signature = _project_nesting_signature(self.project)
        self.stale_label.setText("Layout current")
        self.stale_label.setProperty("stale", False)
        self.stale_label.style().unpolish(self.stale_label)
        self.stale_label.style().polish(self.stale_label)
        self._populate_groups()
        self._update_statistics()

    def _populate_groups(self) -> None:
        self.group_list.blockSignals(True)
        self.group_list.clear()
        if self.result is not None:
            for group in self.result.groups:
                count = len(group.placements) + len(group.unplaced)
                item = QListWidgetItem(
                    f"{group.material} · {group.thickness_mm:g} mm\n"
                    f"{count} panels · {len(group.sheets)} sheet(s)"
                )
                item.setSizeHint(QSize(0, 45))
                self.group_list.addItem(item)
        self.group_list.blockSignals(False)
        if self.group_list.count():
            self.group_list.setCurrentRow(min(self._selected_group_index, self.group_list.count() - 1))
        else:
            self._group_changed(-1)

    def _selected_group(self) -> NestingGroup | None:
        if self.result is None:
            return None
        row = self.group_list.currentRow()
        return self.result.groups[row] if 0 <= row < len(self.result.groups) else None

    def _group_changed(self, row: int) -> None:
        self._selected_group_index = max(0, row)
        group = self._selected_group()
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        if group is not None:
            for sheet in group.sheets:
                self.sheet_combo.addItem(f"{sheet.sheet_number} of {len(group.sheets)}")
        self.sheet_combo.blockSignals(False)
        if self.sheet_combo.count():
            self.sheet_combo.setCurrentIndex(0)
        self._show_current_sheet()
        self._populate_warnings(group)

    def _sheet_changed(self, _index: int) -> None:
        self._show_current_sheet()

    def _show_current_sheet(self) -> None:
        settings = self.result.settings if self.result else self.current_settings()
        group = self._selected_group()
        index = max(0, self.sheet_combo.currentIndex())
        self.sheet_view.show_sheet(group, index, settings)
        if group is not None and 0 <= index < len(group.sheets):
            sheet = group.sheets[index]
            area = sheet.placed_area_mm2
            utilization = 100 * area / (settings.length_mm * settings.width_mm)
            self.sheet_summary.setText(
                f"{group.material} · {group.thickness_mm:g} mm  |  "
                f"{len(sheet.placements)} parts  |  {area / 1_000_000:.3f} m²  |  "
                f"sheet utilization {utilization:.1f}%"
            )
            self._part_selected(sheet.placements[0] if sheet.placements else None)
        else:
            self.sheet_summary.setText("No placed parts for this group")
            self._part_selected(None)

    def _fit_sheet(self) -> None:
        self.sheet_view.fit_sheet()

    def _populate_warnings(self, group: NestingGroup | None) -> None:
        self.warning_list.clear()
        if group is None:
            self.warning_list.addItem("No eligible panel groups were found.")
            return
        if not group.unplaced:
            self.warning_list.addItem("No unplaced parts in this material group.")
            return
        for item in group.unplaced:
            self.warning_list.addItem(
                f"{item.panel.cabinet_id} · {item.panel.component_name} "
                f"#{item.panel.instance_number}: {item.reason}"
            )

    def _update_statistics(self) -> None:
        result = self.result
        if result is None:
            return
        self.stat_eligible.setText(str(result.eligible_count))
        self.stat_placed.setText(str(result.placed_count))
        self.stat_unplaced.setText(str(result.unplaced_count))
        self.stat_sheets.setText(str(result.sheet_count))
        self.stat_total_area.setText(f"{result.total_panel_area_mm2 / 1_000_000:.3f} m²")
        self.stat_placed_area.setText(f"{result.placed_area_mm2 / 1_000_000:.3f} m²")
        self.stat_unplaced_area.setText(f"{result.unplaced_area_mm2 / 1_000_000:.3f} m²")
        self.stat_utilization.setText(f"{result.utilization_percent:.1f}%")
        incomplete = result.unplaced_count > 0
        if result.eligible_count == 0:
            self.completeness_label.setText("No eligible panels")
        else:
            self.completeness_label.setText(
                f"Layout incomplete — {result.unplaced_count} unplaced" if incomplete else "Layout complete"
            )
        self.completeness_label.setProperty("incomplete", incomplete)
        self.completeness_label.style().unpolish(self.completeness_label)
        self.completeness_label.style().polish(self.completeness_label)

    def _part_selected(self, placement: PlacedPanel | None) -> None:
        if placement is None:
            for label in (
                self.part_cabinet,
                self.part_name,
                self.part_instance,
                self.part_dimensions,
                self.part_material,
                self.part_thickness,
                self.part_orientation,
            ):
                label.setText("—")
            return
        panel = placement.panel
        self.part_cabinet.setText(panel.cabinet_id)
        self.part_name.setText(panel.component_name)
        self.part_instance.setText(f"{panel.instance_number} · {panel.instance_id}")
        self.part_dimensions.setText(f"{panel.length_mm:g} x {panel.width_mm:g} mm")
        self.part_material.setText(panel.material)
        self.part_thickness.setText(f"{panel.thickness_mm:g} mm")
        self.part_orientation.setText("Rotated 90°" if placement.rotated else "Original")

    def eligible_bom_quantity(self) -> int:
        if self.project is None:
            return 0
        return sum(
            component.quantity
            for component in generate_project_bom(self.project)
            if component.length_mm > 0 and component.width_mm > 0 and component.thickness_mm > 0
        )
