from __future__ import annotations

from dataclasses import dataclass

import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..bom import Component, generate_bom
from ..models import Cabinet
from .cad_views import FINISH_COLOURS


DISCLAIMER = "Engineering feasibility demo — drilling and construction rules not approved for production."


@dataclass(frozen=True)
class DrillingParameters:
    hole_diameter_mm: int = 5
    edge_offset_mm: int = 37
    pitch_mm: int = 96
    hole_count: int = 4


def engineering_components(cabinet: Cabinet) -> list[Component]:
    """Expose the authoritative demo BOM rows to the engineering workspace."""
    return generate_bom(cabinet)


class ComponentDrawingView(QGraphicsView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("technicalDrawing")
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#FFFFFF"))
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._component: Component | None = None

    def set_component(self, component: Component | None) -> None:
        self._component = component
        self._redraw()

    @staticmethod
    def _dimension_line(scene: QGraphicsScene, x1: float, y1: float, x2: float, y2: float, text: str) -> None:
        pen = QPen(QColor("#147D83"), 1.4)
        scene.addLine(x1, y1, x2, y2, pen)
        if abs(x2 - x1) >= abs(y2 - y1):
            scene.addLine(x1, y1 - 7, x1, y1 + 7, pen)
            scene.addLine(x2, y2 - 7, x2, y2 + 7, pen)
            label = scene.addText(text, QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            label.setPos((x1 + x2 - label.boundingRect().width()) / 2, y1 - 28)
        else:
            scene.addLine(x1 - 7, y1, x1 + 7, y1, pen)
            scene.addLine(x2 - 7, y2, x2 + 7, y2, pen)
            label = scene.addText(text, QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            label.setRotation(-90)
            label.setPos(x1 - 34, (y1 + y2 + label.boundingRect().width()) / 2)
        label.setDefaultTextColor(QColor("#0E6267"))

    def _redraw(self) -> None:
        scene = self._scene
        scene.clear()
        scene.setSceneRect(0, 0, 760, 500)
        component = self._component
        if component is None:
            message = scene.addText("Select a component to view its technical drawing.")
            message.setDefaultTextColor(QColor("#61727D"))
            message.setPos(170, 225)
            return

        title = scene.addText(
            f"{component.cabinet_id}  •  {component.name}",
            QFont("Segoe UI", 14, QFont.Weight.Bold),
        )
        title.setDefaultTextColor(QColor("#172A3C"))
        title.setPos(34, 22)
        if component.length_mm <= 0 or component.width_mm <= 0:
            circle = scene.addEllipse(270, 120, 220, 220, QPen(QColor("#172A3C"), 3))
            circle.setBrush(QColor("#D8E0E4"))
            note = scene.addText(
                f"Hardware item\nQuantity: {component.quantity}\nNo board dimensions in the BOM",
                QFont("Segoe UI", 11, QFont.Weight.DemiBold),
            )
            note.setDefaultTextColor(QColor("#425466"))
            note.setPos(255, 365)
            return

        ratio = component.length_mm / max(1.0, component.width_mm)
        drawing_width = min(470.0, 300.0 * max(0.7, ratio))
        drawing_height = min(300.0, drawing_width / max(0.3, ratio))
        x = (760 - drawing_width) / 2
        y = 120 + (260 - drawing_height) / 2
        panel = scene.addRect(x, y, drawing_width, drawing_height, QPen(QColor("#172A3C"), 2.5))
        panel.setBrush(QColor("#E8E5DE"))
        self._dimension_line(scene, x, y - 30, x + drawing_width, y - 30, f"L {component.length_mm:g} mm")
        self._dimension_line(scene, x - 30, y, x - 30, y + drawing_height, f"W {component.width_mm:g} mm")
        detail = scene.addText(
            f"Thickness {component.thickness_mm:g} mm   •   {component.material}   •   Qty {component.quantity}",
            QFont("Segoe UI", 10, QFont.Weight.DemiBold),
        )
        detail.setDefaultTextColor(QColor("#425466"))
        detail.setPos((760 - detail.boundingRect().width()) / 2, 435)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class DrillingPreviewView(QGraphicsView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("drillingPreview")
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#FFFFFF"))
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._component: Component | None = None
        self._parameters = DrillingParameters()

    def set_preview(self, component: Component | None, parameters: DrillingParameters) -> None:
        self._component = component
        self._parameters = parameters
        self._redraw()

    def _redraw(self) -> None:
        scene = self._scene
        scene.clear()
        scene.setSceneRect(0, 0, 760, 500)
        component = self._component
        title = scene.addText("ILLUSTRATIVE DRILLING PREVIEW", QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setDefaultTextColor(QColor("#172A3C"))
        title.setPos(30, 18)
        if component is None or component.length_mm <= 0 or component.width_mm <= 0:
            note = scene.addText("Select a door or side panel for drilling illustration.")
            note.setDefaultTextColor(QColor("#61727D"))
            note.setPos(180, 230)
            return

        panel_x, panel_y, panel_w, panel_h = 180.0, 82.0, 390.0, 330.0
        panel = scene.addRect(panel_x, panel_y, panel_w, panel_h, QPen(QColor("#172A3C"), 2.4))
        panel.setBrush(QColor("#F2EFE9"))
        scene.addText("REFERENCE EDGE", QFont("Segoe UI", 8, QFont.Weight.Bold)).setPos(panel_x - 105, panel_y + 120)
        reference = scene.addLine(panel_x, panel_y, panel_x, panel_y + panel_h, QPen(QColor("#147D83"), 5))
        reference.setZValue(2)

        params = self._parameters
        usable_height = max(1.0, component.length_mm)
        scale_y = panel_h / usable_height
        offset_x = min(panel_w * 0.42, max(18.0, params.edge_offset_mm * panel_w / max(1.0, component.width_mm)))
        first_y = panel_y + 45
        pitch_px = max(18.0, params.pitch_mm * scale_y)
        hole_pen = QPen(QColor("#8A281F"), 2)
        for index in range(params.hole_count):
            cy = first_y + index * pitch_px
            if cy > panel_y + panel_h - 22:
                break
            radius = max(4.0, params.hole_diameter_mm * 0.9)
            hole = scene.addEllipse(panel_x + offset_x - radius, cy - radius, radius * 2, radius * 2, hole_pen)
            hole.setBrush(QColor("#E9B8B2"))
            hole_label = scene.addText(f"H{index + 1}  Ø{params.hole_diameter_mm}", QFont("Segoe UI", 8))
            hole_label.setDefaultTextColor(QColor("#8A281F"))
            hole_label.setPos(panel_x + offset_x + 13, cy - 10)

        dimension_pen = QPen(QColor("#147D83"), 1.4)
        dimension_y = panel_y + panel_h + 25
        scene.addLine(panel_x, dimension_y, panel_x + offset_x, dimension_y, dimension_pen)
        scene.addLine(panel_x, dimension_y - 7, panel_x, dimension_y + 7, dimension_pen)
        scene.addLine(panel_x + offset_x, dimension_y - 7, panel_x + offset_x, dimension_y + 7, dimension_pen)
        offset_label = scene.addText(f"Edge offset {params.edge_offset_mm} mm", QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        offset_label.setDefaultTextColor(QColor("#0E6267"))
        offset_label.setPos(panel_x + 8, dimension_y + 4)
        panel_label = scene.addText(
            f"Example on {component.name}  •  {component.length_mm:g} × {component.width_mm:g} × {component.thickness_mm:g} mm",
            QFont("Segoe UI", 9, QFont.Weight.DemiBold),
        )
        panel_label.setDefaultTextColor(QColor("#425466"))
        panel_label.setPos(180, 54)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class ExplodedCabinetView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        self.plotter.set_background("#F5F7F8", top="#DCE5EA")
        self.plotter.enable_anti_aliasing("ssaa")
        layout.addWidget(self.plotter.interactor)
        self._component_actors: dict[str, list[object]] = {}
        self._actor_colours: dict[object, str] = {}

    @staticmethod
    def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
        return pv.Box(bounds=(x0, x1, y0, y1, z0, z1))

    def _add_part(self, mesh, component_name: str, colour: str, actor_name: str):
        actor = self.plotter.add_mesh(
            mesh,
            name=actor_name,
            color=colour,
            edge_color="#334653",
            show_edges=True,
            line_width=1.0,
            ambient=0.34,
            diffuse=0.62,
            specular=0.10,
        )
        self._component_actors.setdefault(component_name, []).append(actor)
        self._actor_colours[actor] = colour
        return actor

    def update_cabinet(self, cabinet: Cabinet, components: list[Component]) -> None:
        self.plotter.clear()
        self._component_actors.clear()
        self._actor_colours.clear()
        w, h, d, t = cabinet.width, cabinet.height, cabinet.depth, cabinet.board_thickness
        inside_w, inside_h = w - 2 * t, h - 2 * t
        spread = max(95.0, min(w, h) * 0.17)
        colour = FINISH_COLOURS[cabinet.material]
        labels: list[str] = []
        points: list[tuple[float, float, float]] = []

        parts = [
            ("Left side panel", self._box(-w / 2 - spread - t, -w / 2 - spread, -d / 2, d / 2, -h / 2, h / 2), (-w / 2 - spread, 0, 0)),
            ("Right side panel", self._box(w / 2 + spread, w / 2 + spread + t, -d / 2, d / 2, -h / 2, h / 2), (w / 2 + spread, 0, 0)),
            ("Top panel", self._box(-inside_w / 2, inside_w / 2, -d / 2, d / 2, h / 2 + spread, h / 2 + spread + t), (0, 0, h / 2 + spread)),
            ("Bottom panel", self._box(-inside_w / 2, inside_w / 2, -d / 2, d / 2, -h / 2 - spread - t, -h / 2 - spread), (0, 0, -h / 2 - spread)),
            ("Back panel", self._box(-inside_w / 2, inside_w / 2, d / 2 + spread, d / 2 + spread + 6, -inside_h / 2, inside_h / 2), (0, d / 2 + spread, 0)),
        ]
        component_names = {component.name for component in components}
        for index, (name, mesh, label_point) in enumerate(parts):
            if name not in component_names:
                continue
            self._add_part(mesh, name, colour, f"engineering-{index}-{name}")
            labels.append(name.replace(" panel", ""))
            points.append(label_point)

        shelf_component = next((item for item in components if item.name == "Shelf"), None)
        if shelf_component:
            for index in range(shelf_component.quantity):
                z = -inside_h / 2 + inside_h * (index + 1) / (shelf_component.quantity + 1)
                mesh = self._box(-inside_w / 2, inside_w / 2, -d / 2 + 20, d / 2 - 10, z - t / 2, z + t / 2)
                self._add_part(mesh, "Shelf", colour, f"engineering-shelf-{index}")
                labels.append(f"Shelf {index + 1}")
                points.append((0, -d / 2 + 20, z))

        door_component = next((item for item in components if item.name in ("Door", "Drawer front")), None)
        if door_component:
            if door_component.name == "Door":
                count = door_component.quantity
                for index in range(count):
                    door_width = door_component.width_mm
                    x = -w / 2 + (index + 0.5) * w / count
                    offset = (index - (count - 1) / 2) * 32
                    mesh = self._box(
                        x - door_width / 2 + offset, x + door_width / 2 + offset,
                        -d / 2 - spread - t, -d / 2 - spread,
                        -door_component.length_mm / 2, door_component.length_mm / 2,
                    )
                    self._add_part(mesh, "Door", colour, f"engineering-door-{index}")
                    labels.append(f"Door {index + 1}")
                    points.append((x + offset, -d / 2 - spread, 0))
            else:
                count = door_component.quantity
                for index in range(count):
                    z = -h / 2 + (index + 0.5) * h / count
                    mesh = self._box(
                        -door_component.width_mm / 2, door_component.width_mm / 2,
                        -d / 2 - spread - t, -d / 2 - spread,
                        z - door_component.length_mm / 2, z + door_component.length_mm / 2,
                    )
                    self._add_part(mesh, "Drawer front", colour, f"engineering-drawer-{index}")
                    labels.append(f"Drawer {index + 1}")
                    points.append((0, -d / 2 - spread, z))

        hardware = [item for item in components if item.length_mm == 0 and item.width_mm == 0]
        for component_index, component in enumerate(hardware):
            for index in range(component.quantity):
                z = -h * 0.32 + (index % max(1, component.quantity)) * min(80.0, h * 0.64 / max(1, component.quantity - 1))
                x = w / 2 + spread * 0.35 + component_index * 45
                hardware_mesh = pv.Cylinder(
                    center=(x, -d / 2 - spread * 0.35, z),
                    direction=(0, 1, 0), radius=10, height=32, resolution=24,
                )
                self._add_part(hardware_mesh, component.name, "#3C454B", f"engineering-hardware-{component_index}-{index}")
            labels.append(f"{component.name} ×{component.quantity}")
            points.append((w / 2 + spread * 0.35 + component_index * 45, -d / 2 - spread * 0.35, h * 0.42))

        if points:
            self.plotter.add_point_labels(
                points, labels, name="engineering-labels", point_size=0,
                font_size=13, text_color="#FFFFFF", shape_color="#172A3C",
                shape_opacity=0.86, margin=4, always_visible=True,
            )
        self.plotter.add_axes(line_width=1, color="#526571")
        self.plotter.camera_position = [
            (w * 1.75, -d * 2.65, h * 1.45),
            (0, 0, 0),
            (0, 0, 1),
        ]
        self.plotter.reset_camera()
        self.plotter.render()

    def clear_cabinet(self) -> None:
        self.plotter.clear()
        self._component_actors.clear()
        self._actor_colours.clear()
        self.plotter.set_background("#F5F7F8", top="#DCE5EA")
        self.plotter.add_text(
            "No cabinet selected\nAdd furniture in Design Studio to begin.",
            position="upper_left",
            font_size=12,
            color="#61727D",
            name="engineering-empty-state",
        )
        self.plotter.render()

    def select_component(self, component_name: str) -> None:
        for actor, colour in self._actor_colours.items():
            actor.GetProperty().SetColor(*pv.Color(colour).float_rgb)
            actor.GetProperty().SetLineWidth(1.0)
        for actor in self._component_actors.get(component_name, []):
            actor.GetProperty().SetColor(*pv.Color("#147D83").float_rgb)
            actor.GetProperty().SetLineWidth(2.6)
        self.plotter.render()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.plotter.close()
        super().closeEvent(event)


class ManufacturingPreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("manufacturingPreview")
        self.cabinet: Cabinet | None = None
        self.components: list[Component] = []
        self.selected_component: Component | None = None
        self._signature: tuple | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QFrame()
        header.setObjectName("engineeringHeader")
        header_layout = QHBoxLayout(header)
        title_layout = QVBoxLayout()
        title = QLabel("CABINET ENGINEERING PREVIEW")
        title.setObjectName("engineeringTitle")
        subtitle = QLabel("Selected-cabinet exploded assembly and authoritative BOM component review")
        subtitle.setObjectName("canvasSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        self.cabinet_badge = QLabel("C1")
        self.cabinet_badge.setObjectName("cabinetIdBadge")
        header_layout.addLayout(title_layout, 1)
        header_layout.addWidget(self.cabinet_badge)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

        component_panel = QFrame()
        component_panel.setObjectName("engineeringPanel")
        component_layout = QVBoxLayout(component_panel)
        component_title = QLabel("COMPONENTS FROM CURRENT BOM")
        component_title.setObjectName("sectionTitle")
        self.component_list = QListWidget()
        self.component_list.setAlternatingRowColors(True)
        self.component_list.setWordWrap(True)
        self.component_list.setSpacing(1)
        self.component_list.currentRowChanged.connect(self._component_selected)
        component_layout.addWidget(component_title)
        component_layout.addWidget(self.component_list, 1)
        splitter.addWidget(component_panel)

        exploded_panel = QFrame()
        exploded_panel.setObjectName("engineeringPanel")
        exploded_layout = QVBoxLayout(exploded_panel)
        exploded_title = QLabel("EXPLODED CABINET ASSEMBLY")
        exploded_title.setObjectName("sectionTitle")
        self.exploded_view = ExplodedCabinetView()
        reset_button = QPushButton("Reset Exploded View")
        reset_button.clicked.connect(lambda: self._reset_exploded_camera())
        exploded_layout.addWidget(exploded_title)
        exploded_layout.addWidget(self.exploded_view, 1)
        exploded_layout.addWidget(reset_button)
        splitter.addWidget(exploded_panel)

        detail_panel = QFrame()
        detail_panel.setObjectName("engineeringPanel")
        detail_layout = QVBoxLayout(detail_panel)
        detail_group = QGroupBox("Selected component detail")
        detail_form = QFormLayout(detail_group)
        self.detail_name = QLabel("—")
        self.detail_length = QLabel("—")
        self.detail_width = QLabel("—")
        self.detail_thickness = QLabel("—")
        self.detail_material = QLabel("—")
        self.detail_quantity = QLabel("—")
        self.detail_cabinet = QLabel("—")
        for label, widget in (
            ("Component", self.detail_name), ("Length", self.detail_length),
            ("Width", self.detail_width), ("Thickness", self.detail_thickness),
            ("Material", self.detail_material), ("Quantity", self.detail_quantity),
            ("Cabinet ID", self.detail_cabinet),
        ):
            detail_form.addRow(label, widget)

        self.drawing_tabs = QTabWidget()
        self.component_drawing = ComponentDrawingView()
        self.drawing_tabs.addTab(self.component_drawing, "Component Drawing")
        drilling_page = QWidget()
        drilling_layout = QVBoxLayout(drilling_page)
        drilling_controls = QGroupBox("Configurable example parameters")
        drilling_form = QFormLayout(drilling_controls)
        self.hole_diameter_spin = self._parameter_spin(2, 35, 5, " mm")
        self.edge_offset_spin = self._parameter_spin(10, 200, 37, " mm")
        self.hole_pitch_spin = self._parameter_spin(32, 500, 96, " mm")
        self.hole_count_spin = self._parameter_spin(1, 12, 4, "")
        drilling_form.addRow("Hole diameter", self.hole_diameter_spin)
        drilling_form.addRow("Reference edge offset", self.edge_offset_spin)
        drilling_form.addRow("Hole pitch", self.hole_pitch_spin)
        drilling_form.addRow("Hole count", self.hole_count_spin)
        self.drilling_view = DrillingPreviewView()
        drilling_layout.addWidget(drilling_controls)
        drilling_layout.addWidget(self.drilling_view, 1)
        self.drawing_tabs.addTab(drilling_page, "Drilling Preview")
        for spin in (
            self.hole_diameter_spin, self.edge_offset_spin,
            self.hole_pitch_spin, self.hole_count_spin,
        ):
            spin.valueChanged.connect(self._refresh_drilling)

        detail_layout.addWidget(detail_group)
        detail_layout.addWidget(self.drawing_tabs, 1)
        splitter.addWidget(detail_panel)
        splitter.setSizes([285, 720, 485])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        root.addWidget(splitter, 1)

        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setObjectName("engineeringDisclaimer")
        disclaimer.setWordWrap(True)
        root.addWidget(disclaimer)

    @staticmethod
    def _parameter_spin(minimum: int, maximum: int, value: int, suffix: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    @property
    def drilling_parameters(self) -> DrillingParameters:
        return DrillingParameters(
            self.hole_diameter_spin.value(),
            self.edge_offset_spin.value(),
            self.hole_pitch_spin.value(),
            self.hole_count_spin.value(),
        )

    def set_cabinet(self, cabinet: Cabinet | None, *, force: bool = False) -> None:
        if cabinet is None:
            if not force and self.cabinet is None and self._signature == ("empty",):
                return
            self.cabinet = None
            self.components = []
            self.selected_component = None
            self._signature = ("empty",)
            self.cabinet_badge.setText("No cabinet selected")
            self.component_list.blockSignals(True)
            self.component_list.clear()
            self.component_list.addItem("Add and select a cabinet in Design Studio to review its components.")
            self.component_list.setCurrentRow(-1)
            self.component_list.blockSignals(False)
            for label in (
                self.detail_name, self.detail_length, self.detail_width,
                self.detail_thickness, self.detail_material,
                self.detail_quantity, self.detail_cabinet,
            ):
                label.setText("—")
            self.component_drawing.set_component(None)
            self.drilling_view.set_preview(None, self.drilling_parameters)
            self.exploded_view.clear_cabinet()
            return
        signature = tuple(cabinet.__dict__.values())
        if not force and signature == self._signature:
            return
        previous_name = self.selected_component.name if self.selected_component else None
        self.cabinet = cabinet
        self._signature = signature
        self.components = engineering_components(cabinet)
        self.cabinet_badge.setText(
            f"{cabinet.cabinet_id}  •  {cabinet.width} × {cabinet.height} × {cabinet.depth} mm"
        )
        self.component_list.blockSignals(True)
        self.component_list.clear()
        selected_row = 0
        for row, component in enumerate(self.components):
            dimensions = (
                f"{component.length_mm:g} × {component.width_mm:g} × {component.thickness_mm:g} mm"
                if component.length_mm or component.width_mm else "Hardware"
            )
            item = QListWidgetItem(f"{component.name}\n{dimensions}  •  Qty {component.quantity}")
            item.setSizeHint(QSize(0, 46))
            item.setData(Qt.ItemDataRole.UserRole, row)
            item.setToolTip(f"{component.cabinet_id} — {component.material}")
            self.component_list.addItem(item)
            if component.name == previous_name:
                selected_row = row
        self.component_list.blockSignals(False)
        self.exploded_view.update_cabinet(cabinet, self.components)
        self.component_list.setCurrentRow(selected_row)
        self._component_selected(selected_row)

    def select_component(self, component_name: str) -> None:
        for row, component in enumerate(self.components):
            if component.name == component_name:
                self.component_list.setCurrentRow(row)
                return
        raise ValueError(f"Component {component_name!r} is not available for the selected cabinet.")

    def _component_selected(self, row: int) -> None:
        if not 0 <= row < len(self.components):
            self.selected_component = None
            return
        component = self.components[row]
        self.selected_component = component
        self.detail_name.setText(component.name)
        self.detail_length.setText(f"{component.length_mm:g} mm" if component.length_mm else "—")
        self.detail_width.setText(f"{component.width_mm:g} mm" if component.width_mm else "—")
        self.detail_thickness.setText(f"{component.thickness_mm:g} mm" if component.thickness_mm else "—")
        self.detail_material.setText(component.material)
        self.detail_quantity.setText(str(component.quantity))
        self.detail_cabinet.setText(component.cabinet_id)
        self.component_drawing.set_component(component)
        self.exploded_view.select_component(component.name)
        self._refresh_drilling()

    def _drilling_component(self) -> Component | None:
        if self.selected_component and self.selected_component.name in ("Door", "Left side panel", "Right side panel"):
            return self.selected_component
        return next(
            (component for component in self.components if component.name in ("Door", "Left side panel", "Right side panel")),
            None,
        )

    def _refresh_drilling(self, *_args) -> None:
        self.drilling_view.set_preview(self._drilling_component(), self.drilling_parameters)

    def _reset_exploded_camera(self) -> None:
        if self.cabinet is not None:
            self.exploded_view.update_cabinet(self.cabinet, self.components)
            if self.selected_component is not None:
                self.exploded_view.select_component(self.selected_component.name)
