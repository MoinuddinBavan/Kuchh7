from __future__ import annotations

import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget

from ..models import Cabinet, Room


FINISH_COLOURS = {
    "Natural Oak": "#C89B63",
    "White Matte": "#ECEFF1",
    "Walnut": "#65432D",
    "Graphite Grey": "#4B5055",
}


class RoomPlanView(QGraphicsView):
    cabinetSelected = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#F7F9FB"))
        self.setMinimumSize(380, 300)
        self._room = Room()
        self._cabinet = Cabinet()
        self.redraw(self._room, self._cabinet)

    def redraw(self, room: Room, cabinet: Cabinet) -> None:
        self._room, self._cabinet = room, cabinet
        scene = self.scene()
        scene.clear()
        scale = min(640 / room.width, 480 / room.depth)
        ox, oy = 70, 70
        rw, rd = room.width * scale, room.depth * scale
        wall_pen = QPen(QColor("#172A3C"), 5)
        scene.addRect(ox, oy, rw, rd, wall_pen, QColor("#FFFFFF"))

        # Window on upper wall.
        window_width = min(1200, room.width * 0.35) * scale
        wx = ox + (rw - window_width) / 2
        scene.addLine(wx, oy, wx + window_width, oy, QPen(QColor("#2D9CDB"), 8))

        # Door opening and swing at lower-left wall.
        door = min(800, room.width * 0.25) * scale
        hinge_x, hinge_y = ox + 20 * scale, oy + rd
        scene.addLine(hinge_x, hinge_y, hinge_x + door, hinge_y - door, QPen(QColor("#147D83"), 3))
        swing = QPainterPath()
        swing.moveTo(hinge_x + door, hinge_y)
        swing.arcTo(hinge_x - door, hinge_y - door, door * 2, door * 2, 0, 90)
        scene.addPath(swing, QPen(QColor("#147D83"), 1))

        cw, cd = cabinet.width * scale, cabinet.depth * scale
        cabinet_item = scene.addRect(ox + (rw - cw) / 2, oy + rd - cd, cw, cd, QPen(QColor("#147D83"), 3), QColor("#B8DEE0"))
        cabinet_item.setData(0, "cabinet")
        label = scene.addText(f"Base cabinet\n{cabinet.width} × {cabinet.depth} mm", QFont("Segoe UI", 8))
        label.setDefaultTextColor(QColor("#172A3C"))
        label.setPos(ox + (rw - cw) / 2 + 4, oy + rd - cd + 4)

        top_dim = scene.addText(f"{room.width} mm", QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        top_dim.setDefaultTextColor(QColor("#172A3C"))
        top_dim.setPos(ox + rw / 2 - 35, oy - 35)
        side_dim = scene.addText(f"{room.depth} mm", QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        side_dim.setDefaultTextColor(QColor("#172A3C"))
        side_dim.setRotation(-90)
        side_dim.setPos(ox - 45, oy + rd / 2 + 35)
        scene.setSceneRect(0, 0, rw + 150, rd + 140)
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        if item and (item.data(0) == "cabinet" or (item.parentItem() and item.parentItem().data(0) == "cabinet")):
            self.cabinetSelected.emit()
        super().mousePressEvent(event)


class Cabinet3DView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        self.plotter.set_background("#F7F9FB")
        layout.addWidget(self.plotter.interactor)
        self.update_cabinet(Cabinet(), reset_camera=True)

    @staticmethod
    def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
        return pv.Box(bounds=(x0, x1, y0, y1, z0, z1))

    def update_cabinet(self, cabinet: Cabinet, reset_camera: bool = False) -> None:
        cabinet.validate()
        self.plotter.clear()
        w, h, d, t = cabinet.width, cabinet.height, cabinet.depth, cabinet.board_thickness
        body_color = FINISH_COLOURS[cabinet.material]
        edge_color = "#263746"

        parts = [
            self._box(0, t, 0, d, 0, h),
            self._box(w - t, w, 0, d, 0, h),
            self._box(t, w - t, 0, d, h - t, h),
            self._box(t, w - t, 0, d, 0, t),
            self._box(t, w - t, d - 6, d, t, h - t),
        ]
        for shelf_index in range(cabinet.shelf_count):
            z = (h - 2 * t) * (shelf_index + 1) / (cabinet.shelf_count + 1) + t
            parts.append(self._box(t, w - t, 20, d - 6, z - t / 2, z + t / 2))
        for part in parts:
            self.plotter.add_mesh(part, color=body_color, edge_color=edge_color, show_edges=True)

        reveal = 2
        door_width = (w - ((cabinet.door_count + 1) * reveal)) / cabinet.door_count
        for door_index in range(cabinet.door_count):
            x0 = reveal + door_index * (door_width + reveal)
            door = self._box(x0, x0 + door_width, -t - 2, -2, reveal, h - reveal)
            self.plotter.add_mesh(door, color=body_color, edge_color=edge_color, show_edges=True)

        self.plotter.add_axes(line_width=1)
        if reset_camera:
            self.plotter.view_isometric()
        self.plotter.reset_camera()
        self.plotter.render()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.plotter.close()
        super().closeEvent(event)

