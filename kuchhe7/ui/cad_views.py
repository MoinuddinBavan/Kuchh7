from __future__ import annotations

from copy import deepcopy
from math import cos, pi, sin

import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget

from ..catalogue import create_catalogue_cabinet, get_catalogue_item, normalized_finish
from ..models import Cabinet, Opening, Room
from ..openings import opening_error, opening_furniture_conflict, wall_length
from ..placement import placement_error, snap_position
from ..presentation import connected_base_runs


FINISH_COLOURS = {
    "Warm White": "#F0EEE8",
    "Cashmere": "#C5B5A2",
    "Natural Oak": "#BA9569",
    "Walnut": "#72503B",
    "Graphite": "#464B4E",
    "White Matte": "#F0EEE8",
    "Cashmere / Greige Matte": "#C5B5A2",
    "Graphite Grey": "#464B4E",
}

FINISH_SURFACES = {
    "Warm White": {"edge": "#C6C1B8", "ambient": 0.48, "diffuse": 0.52, "specular": 0.11},
    "Cashmere": {"edge": "#948777", "ambient": 0.43, "diffuse": 0.57, "specular": 0.09},
    "Natural Oak": {"edge": "#856746", "ambient": 0.39, "diffuse": 0.61, "specular": 0.07},
    "Walnut": {"edge": "#463127", "ambient": 0.39, "diffuse": 0.61, "specular": 0.10},
    "Graphite": {"edge": "#303538", "ambient": 0.46, "diffuse": 0.54, "specular": 0.13},
}

PLAN_FINISH_COLOURS = {
    "Warm White": "#E8E5DE",
    "Cashmere": "#C9BFB3",
    "Natural Oak": "#C9A67B",
    "Walnut": "#80614E",
    "Graphite": "#656A6E",
    "White Matte": "#E8E5DE",
    "Cashmere / Greige Matte": "#C9BFB3",
    "Graphite Grey": "#656A6E",
}


class RoomPlanView(QGraphicsView):
    cabinetSelected = Signal(str)
    cabinetMoveRequested = Signal(str, int, int)
    placementRequested = Signal(str, int, int)
    placementCancelled = Signal()
    wallSelected = Signal(str)
    openingSelected = Signal(str)
    openingMoveRequested = Signal(str, int)
    openingPlacementRequested = Signal(str, str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("roomPlan")
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor("#F7F9FB"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setMouseTracking(True)
        self.setMinimumSize(380, 300)
        self._room = Room()
        self._cabinets = [Cabinet()]
        self._selected_cabinet_id = "C1"
        self._selected_opening_id: str | None = None
        self._selected_wall_id = "WEST"
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._cabinet_items: dict[str, QGraphicsItem] = {}
        self._wall_items: dict[str, QGraphicsItem] = {}
        self._opening_items: dict[str, QGraphicsItem] = {}
        self._pending_type_id: str | None = None
        self._dragging_id: str | None = None
        self._drag_offset = QPointF()
        self._drag_started = False
        self._pending_opening_kind: str | None = None
        self._pending_opening_wall_id: str | None = None
        self._dragging_opening_id: str | None = None
        self._opening_drag_offset = 0.0
        self._wall_select_mode = False
        self._preview_item: QGraphicsItem | None = None
        self._preview_label: QGraphicsItem | None = None
        self._guide_items: list[QGraphicsItem] = []
        self._preview_position: tuple[int, int] | None = None
        self._preview_valid = False
        self._snap_enabled = True
        self._grid_snap_enabled = True
        self.redraw(self._room, self._cabinets, self._selected_cabinet_id)

    @staticmethod
    def _dimension_font() -> QFont:
        return QFont("Segoe UI", 8, QFont.Weight.DemiBold)

    def _draw_horizontal_dimension(self, x1: float, x2: float, wall_y: float, value: int) -> None:
        scene = self.scene()
        dim_y = wall_y - 36
        pen = QPen(QColor("#667785"), 1)
        scene.addLine(x1, wall_y - 3, x1, dim_y - 5, pen)
        scene.addLine(x2, wall_y - 3, x2, dim_y - 5, pen)
        scene.addLine(x1, dim_y, x2, dim_y, pen)
        scene.addLine(x1, dim_y, x1 + 8, dim_y - 4, pen)
        scene.addLine(x1, dim_y, x1 + 8, dim_y + 4, pen)
        scene.addLine(x2, dim_y, x2 - 8, dim_y - 4, pen)
        scene.addLine(x2, dim_y, x2 - 8, dim_y + 4, pen)
        label = scene.addText(f"{value:,} mm", self._dimension_font())
        label.setDefaultTextColor(QColor("#425466"))
        label_rect = label.boundingRect()
        label.setPos((x1 + x2 - label_rect.width()) / 2, dim_y - label_rect.height() - 3)

    def _draw_vertical_dimension(self, y1: float, y2: float, wall_x: float, value: int) -> None:
        scene = self.scene()
        dim_x = wall_x - 40
        pen = QPen(QColor("#667785"), 1)
        scene.addLine(wall_x - 3, y1, dim_x + 5, y1, pen)
        scene.addLine(wall_x - 3, y2, dim_x + 5, y2, pen)
        scene.addLine(dim_x, y1, dim_x, y2, pen)
        scene.addLine(dim_x, y1, dim_x - 4, y1 + 8, pen)
        scene.addLine(dim_x, y1, dim_x + 4, y1 + 8, pen)
        scene.addLine(dim_x, y2, dim_x - 4, y2 - 8, pen)
        scene.addLine(dim_x, y2, dim_x + 4, y2 - 8, pen)
        label = scene.addText(f"{value:,} mm", self._dimension_font())
        label.setDefaultTextColor(QColor("#425466"))
        label.setRotation(-90)
        label.setPos(dim_x - label.boundingRect().height() - 3, (y1 + y2 + label.boundingRect().width()) / 2)

    def redraw(
        self,
        room: Room,
        cabinets: list[Cabinet] | Cabinet,
        selected_cabinet_id: str = "C1",
        selected_opening_id: str | None = None,
        selected_wall_id: str = "WEST",
    ) -> None:
        if isinstance(cabinets, Cabinet):
            cabinets = [cabinets]
            selected_cabinet_id = cabinets[0].cabinet_id
        self._room, self._cabinets = room, cabinets
        self._selected_cabinet_id = selected_cabinet_id
        self._selected_opening_id = selected_opening_id
        self._selected_wall_id = selected_wall_id
        scene = self.scene()
        scene.clear()
        self._cabinet_items.clear()
        self._wall_items.clear()
        self._opening_items.clear()
        self._preview_item = None
        self._preview_label = None
        self._guide_items.clear()
        scale = min(680 / room.width, 510 / room.depth)
        ox, oy = 88.0, 78.0
        self._scale, self._ox, self._oy = scale, ox, oy
        rw, rd = room.width * scale, room.depth * scale

        grid_pen = QPen(QColor("#DDE5EA"), 0.8, Qt.PenStyle.DashLine)
        for distance in range(500, room.width, 500):
            x = ox + distance * scale
            scene.addLine(x, oy, x, oy + rd, grid_pen)
        for distance in range(500, room.depth, 500):
            y = oy + distance * scale
            scene.addLine(ox, y, ox + rw, y, grid_pen)

        wall_points = {
            "NORTH": (QPointF(ox, oy), QPointF(ox + rw, oy)),
            "EAST": (QPointF(ox + rw, oy), QPointF(ox + rw, oy + rd)),
            "SOUTH": (QPointF(ox, oy + rd), QPointF(ox + rw, oy + rd)),
            "WEST": (QPointF(ox, oy), QPointF(ox, oy + rd)),
        }
        for wall in room.walls:
            selected_wall = wall.wall_id == selected_wall_id
            wall_pen = QPen(
                QColor("#147D83" if selected_wall else "#172A3C"),
                9 if selected_wall else 8,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
            )
            start, end = wall_points[wall.wall_id]
            wall_item = scene.addLine(start.x(), start.y(), end.x(), end.y(), wall_pen)
            wall_item.setData(0, f"wall:{wall.wall_id}")
            wall_item.setZValue(4)
            self._wall_items[wall.wall_id] = wall_item

        for opening in room.openings:
            self._draw_opening(opening, opening.opening_id == selected_opening_id)

        for cabinet in cabinets:
            catalogue_item = get_catalogue_item(cabinet.cabinet_type_id)
            selected = cabinet.cabinet_id == selected_cabinet_id
            cw, cd = cabinet.width * scale, cabinet.depth * scale
            cabinet_x = ox + cabinet.position_x * scale
            cabinet_y = oy + cabinet.position_y * scale
            outline = QColor("#147D83") if selected else QColor("#425765")
            footprint_pen = QPen(outline, 3.5 if selected else 1.8)
            if catalogue_item.category == "Wall Cabinets":
                footprint_pen.setStyle(Qt.PenStyle.DashLine)
            fill = QColor(PLAN_FINISH_COLOURS[cabinet.material])
            if catalogue_item.front_style == "corner":
                inset = min(cw, cd) * 0.42
                cabinet_item = scene.addPolygon(QPolygonF([
                    QPointF(cabinet_x, cabinet_y), QPointF(cabinet_x + cw, cabinet_y),
                    QPointF(cabinet_x + cw, cabinet_y + cd), QPointF(cabinet_x + inset, cabinet_y + cd),
                    QPointF(cabinet_x + inset, cabinet_y + inset), QPointF(cabinet_x, cabinet_y + inset),
                ]), footprint_pen, fill)
            else:
                cabinet_item = scene.addRect(cabinet_x, cabinet_y, cw, cd, footprint_pen, fill)
            cabinet_item.setData(0, cabinet.cabinet_id)
            cabinet_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            cabinet_item.setSelected(selected)
            # Wall units occupy the rear portion of a base footprint in plan.
            # Keep their smaller dashed footprint above base units so the click
            # target remains deterministic regardless of project list order.
            cabinet_item.setZValue(20 if catalogue_item.category == "Wall Cabinets" else 10)
            self._cabinet_items[cabinet.cabinet_id] = cabinet_item
            front_line = scene.addLine(cabinet_x, cabinet_y, cabinet_x + cw, cabinet_y, QPen(QColor("#0B5559"), 3))
            front_line.setZValue(cabinet_item.zValue() + 1)
            divisions = cabinet.drawer_count if catalogue_item.front_style == "drawers" else cabinet.door_count
            for index in range(1, divisions):
                x = cabinet_x + cw * index / divisions
                scene.addLine(x, cabinet_y, x, cabinet_y + min(10, cd), QPen(QColor("#FFFFFF"), 1.2))
            compact_names = {
                "base_2_door": "2-DOOR BASE",
                "base_3_drawer": "3-DRAWER BASE",
                "sink_base": "SINK BASE",
                "wall_2_door": "WALL CABINET",
                "wall_open_shelf": "OPEN WALL SHELF",
                "tall_pantry": "TALL PANTRY",
            }
            plan_name = compact_names.get(cabinet.cabinet_type_id, catalogue_item.name.upper())
            label = scene.addText(
                f"{cabinet.cabinet_id} • {plan_name}\n{cabinet.width} × {cabinet.depth} mm",
                QFont("Segoe UI", 7, QFont.Weight.DemiBold),
            )
            label.setData(0, cabinet.cabinet_id)
            label.setDefaultTextColor(QColor("#0B4E52") if selected else QColor("#172A3C"))
            label.setZValue(30)
            if catalogue_item.category == "Wall Cabinets":
                # Keep stacked wall/base footprints legible with a callout just
                # beyond the back-wall footprint instead of overlaying the base.
                label.setPos(cabinet_x + 6, cabinet_y + cd + 4)
            else:
                label.setPos(cabinet_x + 6, cabinet_y + 5)

        self._draw_horizontal_dimension(ox, ox + rw, oy, room.width)
        self._draw_vertical_dimension(oy, oy + rd, ox, room.depth)
        scene.setSceneRect(8, 8, rw + 175, rd + 145)
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _wall_local_to_scene(self, wall_id: str, u: float, v: float = 0.0) -> QPointF:
        if wall_id == "NORTH":
            return QPointF(self._ox + u * self._scale, self._oy + v * self._scale)
        if wall_id == "SOUTH":
            return QPointF(self._ox + u * self._scale, self._oy + (self._room.depth - v) * self._scale)
        if wall_id == "WEST":
            return QPointF(self._ox + v * self._scale, self._oy + u * self._scale)
        return QPointF(self._ox + (self._room.width - v) * self._scale, self._oy + u * self._scale)

    def _wall_offset_from_model(self, wall_id: str, point: QPointF) -> float:
        value = point.x() if wall_id in ("NORTH", "SOUTH") else point.y()
        return max(0.0, min(float(wall_length(self._room, wall_id)), value))

    @staticmethod
    def _tag_item(item: QGraphicsItem, value: str, z: float = 10) -> QGraphicsItem:
        item.setData(0, value)
        item.setZValue(z)
        return item

    def _draw_opening(self, opening: Opening, selected: bool) -> None:
        start = self._wall_local_to_scene(opening.wall_id, opening.offset)
        end = self._wall_local_to_scene(opening.wall_id, opening.offset + opening.width)
        key = f"opening:{opening.opening_id}"
        gap = self.scene().addLine(start.x(), start.y(), end.x(), end.y(), QPen(QColor("#FFFFFF"), 11))
        self._tag_item(gap, key, 11)
        accent = QColor("#E2A93B" if selected else ("#147D83" if opening.kind == "door" else "#2D9CDB"))
        if opening.kind == "window":
            line = self.scene().addLine(start.x(), start.y(), end.x(), end.y(), QPen(accent, 5))
            self._tag_item(line, key, 12)
            self._opening_items[opening.opening_id] = line
        else:
            left_hinge = opening.swing.startswith("Left")
            inward = opening.swing.endswith("In")
            hinge_u = opening.offset if left_hinge else opening.offset + opening.width
            direction = 1.0 if inward else -1.0
            hinge = self._wall_local_to_scene(opening.wall_id, hinge_u)
            leaf_end = self._wall_local_to_scene(opening.wall_id, hinge_u, direction * opening.width)
            leaf = self.scene().addLine(hinge.x(), hinge.y(), leaf_end.x(), leaf_end.y(), QPen(accent, 2.4))
            self._tag_item(leaf, key, 12)
            path = QPainterPath()
            for index in range(13):
                angle = (pi / 2) * index / 12
                u = hinge_u + (opening.width * cos(angle) if left_hinge else -opening.width * cos(angle))
                v = direction * opening.width * sin(angle)
                point = self._wall_local_to_scene(opening.wall_id, u, v)
                if index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            arc = self.scene().addPath(path, QPen(accent.lighter(125), 1.3, Qt.PenStyle.DashLine))
            self._tag_item(arc, key, 11)
            self._opening_items[opening.opening_id] = leaf

        midpoint = (start + end) / 2
        label = self.scene().addText(
            f"{opening.opening_id}  {opening.width} mm\noffset {opening.offset} mm",
            QFont("Segoe UI", 7, QFont.Weight.Bold if selected else QFont.Weight.DemiBold),
        )
        label.setDefaultTextColor(accent.darker(125))
        label.setPos(midpoint.x() + 5, midpoint.y() + 5)
        self._tag_item(label, key, 15)

    def begin_wall_selection(self) -> None:
        self.cancel_interaction(emit_signal=False)
        self._wall_select_mode = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocus()

    def begin_opening_placement(self, kind: str, wall_id: str) -> None:
        self.cancel_interaction(emit_signal=False)
        self._pending_opening_kind = kind
        self._pending_opening_wall_id = wall_id
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()

    def preview_opening_position(self, wall_id: str, offset: int) -> bool:
        if self._pending_opening_kind is None:
            return False
        candidate = self._new_preview_opening(self._pending_opening_kind, wall_id, offset)
        return self._update_opening_preview(candidate)

    def _new_preview_opening(self, kind: str, wall_id: str, offset: int) -> Opening:
        return Opening(
            "PREVIEW",
            kind,
            wall_id,
            offset,
            900 if kind == "door" else 1200,
            2100 if kind == "door" else 1000,
            0 if kind == "door" else 1000,
            "Left In",
        )

    def _opening_for_id(self, opening_id: str) -> Opening:
        return next(item for item in self._room.openings if item.opening_id == opening_id)

    def _update_opening_preview(self, candidate: Opening) -> bool:
        error = opening_error(self._room, self._room.openings, candidate)
        if error is None:
            for cabinet in self._cabinets:
                error = opening_furniture_conflict(self._room, candidate, cabinet)
                if error:
                    break
        self._clear_preview()
        valid = error is None
        start = self._wall_local_to_scene(candidate.wall_id, candidate.offset)
        end = self._wall_local_to_scene(candidate.wall_id, candidate.offset + candidate.width)
        colour = QColor("#39A58A" if valid else "#C95145")
        self._preview_item = self.scene().addLine(
            start.x(), start.y(), end.x(), end.y(), QPen(colour, 10, Qt.PenStyle.DashLine)
        )
        self._preview_item.setZValue(100)
        self._preview_label = self.scene().addText(
            f"PLACE {candidate.kind.upper()}\n{candidate.wall_id} • offset {candidate.offset} mm"
            + ("" if valid else "\nINVALID"),
            QFont("Segoe UI", 8, QFont.Weight.Bold),
        )
        self._preview_label.setDefaultTextColor(colour.darker(130))
        self._preview_label.setPos((start.x() + end.x()) / 2 + 5, (start.y() + end.y()) / 2 + 5)
        self._preview_label.setZValue(101)
        self._preview_position = (candidate.offset, 0)
        self._preview_valid = valid
        return valid

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_snap_options(self, *, snap_enabled: bool, grid_enabled: bool) -> None:
        self._snap_enabled = snap_enabled
        self._grid_snap_enabled = grid_enabled

    def begin_placement(self, type_id: str) -> None:
        self.cancel_interaction(emit_signal=False)
        self._pending_type_id = type_id
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()

    def cancel_interaction(self, *, emit_signal: bool = True) -> None:
        had_interaction = any((
            self._pending_type_id is not None,
            self._dragging_id is not None,
            self._pending_opening_kind is not None,
            self._dragging_opening_id is not None,
            self._wall_select_mode,
        ))
        self._pending_type_id = None
        self._dragging_id = None
        self._pending_opening_kind = None
        self._pending_opening_wall_id = None
        self._dragging_opening_id = None
        self._wall_select_mode = False
        self._drag_started = False
        self._clear_preview()
        self.unsetCursor()
        if emit_signal and had_interaction:
            self.placementCancelled.emit()

    def preview_model_position(self, x: int, y: int) -> bool:
        """Show the current catalogue item at a model-space top-left position."""
        if self._pending_type_id is None:
            return False
        candidate = create_catalogue_cabinet(self._pending_type_id, "PREVIEW", position_x=x, position_y=y)
        return self._update_placement_preview(candidate)

    def _model_point(self, viewport_position) -> QPointF:
        point = self.mapToScene(viewport_position)
        return QPointF((point.x() - self._ox) / self._scale, (point.y() - self._oy) / self._scale)

    def _cabinet_for_id(self, cabinet_id: str) -> Cabinet:
        return next(item for item in self._cabinets if item.cabinet_id == cabinet_id)

    def _clear_preview(self) -> None:
        scene = self.scene()
        for item in [self._preview_item, self._preview_label, *self._guide_items]:
            if item is not None and item.scene() is scene:
                scene.removeItem(item)
        self._preview_item = None
        self._preview_label = None
        self._guide_items.clear()
        self._preview_position = None
        self._preview_valid = False

    def _update_placement_preview(self, candidate: Cabinet) -> bool:
        result = snap_position(
            candidate,
            self._room,
            self._cabinets,
            scale_pixels_per_mm=self._scale * abs(self.transform().m11()),
            snap_enabled=self._snap_enabled,
            grid_enabled=self._grid_snap_enabled,
        )
        candidate.position_x, candidate.position_y = result.x, result.y
        error = placement_error(self._room, self._cabinets, candidate)
        self._clear_preview()
        valid = error is None
        colour = QColor("#39A58A" if valid else "#C95145")
        colour.setAlpha(105)
        x = self._ox + candidate.position_x * self._scale
        y = self._oy + candidate.position_y * self._scale
        width, depth = candidate.width * self._scale, candidate.depth * self._scale
        self._preview_item = self.scene().addRect(
            x, y, width, depth,
            QPen(QColor("#16766D" if valid else "#9A2F29"), 2.4, Qt.PenStyle.DashLine),
            colour,
        )
        self._preview_item.setZValue(100)
        label_text = f"{candidate.cabinet_id if candidate.cabinet_id != 'PREVIEW' else 'PLACE'}\nX {candidate.position_x}  Y {candidate.position_y}"
        if error:
            label_text += "\nINVALID"
        self._preview_label = self.scene().addText(label_text, QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._preview_label.setDefaultTextColor(QColor("#0F5F59" if valid else "#8E2822"))
        self._preview_label.setPos(x + 5, y + 4)
        self._preview_label.setZValue(101)

        guide_pen = QPen(QColor("#25A3A8"), 1.2, Qt.PenStyle.DashLine)
        for guide_x in result.vertical_guides:
            scene_x = self._ox + guide_x * self._scale
            guide = self.scene().addLine(scene_x, self._oy, scene_x, self._oy + self._room.depth * self._scale, guide_pen)
            guide.setZValue(99)
            self._guide_items.append(guide)
        for guide_y in result.horizontal_guides:
            scene_y = self._oy + guide_y * self._scale
            guide = self.scene().addLine(self._ox, scene_y, self._ox + self._room.width * self._scale, scene_y, guide_pen)
            guide.setZValue(99)
            self._guide_items.append(guide)
        self._preview_position = (candidate.position_x, candidate.position_y)
        self._preview_valid = valid
        return valid

    def _preview_from_cursor(self, model_point: QPointF) -> None:
        if self._pending_type_id:
            candidate = create_catalogue_cabinet(self._pending_type_id, "PREVIEW")
            candidate.position_x = round(model_point.x() - candidate.width / 2)
            candidate.position_y = round(model_point.y() - candidate.depth / 2)
        elif self._dragging_id:
            candidate = deepcopy(self._cabinet_for_id(self._dragging_id))
            candidate.position_x = round(model_point.x() - self._drag_offset.x())
            candidate.position_y = round(model_point.y() - self._drag_offset.y())
        else:
            return
        self._update_placement_preview(candidate)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        model_point = self._model_point(event.position().toPoint())
        if self._pending_opening_kind and self._pending_opening_wall_id:
            width = 900 if self._pending_opening_kind == "door" else 1200
            offset = round(self._wall_offset_from_model(self._pending_opening_wall_id, model_point) - width / 2)
            candidate = self._new_preview_opening(
                self._pending_opening_kind,
                self._pending_opening_wall_id,
                offset,
            )
            self._update_opening_preview(candidate)
            if self._preview_valid and self._preview_position:
                self.openingPlacementRequested.emit(
                    self._pending_opening_kind,
                    self._pending_opening_wall_id,
                    self._preview_position[0],
                )
            event.accept()
            return
        if self._pending_type_id:
            self._preview_from_cursor(model_point)
            if self._preview_valid and self._preview_position:
                self.placementRequested.emit(self._pending_type_id, *self._preview_position)
            event.accept()
            return
        item = self.itemAt(event.position().toPoint())
        item_data = item.data(0) if item else None
        if isinstance(item_data, str) and item_data.startswith("opening:"):
            opening_id = item_data.split(":", 1)[1]
            opening = self._opening_for_id(opening_id)
            self.openingSelected.emit(opening_id)
            self._dragging_opening_id = opening_id
            self._opening_drag_offset = self._wall_offset_from_model(opening.wall_id, model_point) - opening.offset
            self._drag_started = False
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
            return
        if isinstance(item_data, str) and item_data.startswith("wall:"):
            wall_id = item_data.split(":", 1)[1]
            self.wallSelected.emit(wall_id)
            if self._wall_select_mode:
                self.cancel_interaction(emit_signal=False)
            event.accept()
            return
        if item and isinstance(item_data, str) and item_data:
            cabinet_id = item_data
            self.cabinetSelected.emit(cabinet_id)
            cabinet = self._cabinet_for_id(cabinet_id)
            self._dragging_id = cabinet_id
            self._drag_offset = QPointF(model_point.x() - cabinet.position_x, model_point.y() - cabinet.position_y)
            self._drag_started = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        model_point = self._model_point(event.position().toPoint())
        if self._pending_opening_kind and self._pending_opening_wall_id:
            width = 900 if self._pending_opening_kind == "door" else 1200
            offset = round(self._wall_offset_from_model(self._pending_opening_wall_id, model_point) - width / 2)
            self._update_opening_preview(self._new_preview_opening(
                self._pending_opening_kind, self._pending_opening_wall_id, offset
            ))
            event.accept()
            return
        if self._dragging_opening_id:
            opening = deepcopy(self._opening_for_id(self._dragging_opening_id))
            opening.offset = round(self._wall_offset_from_model(opening.wall_id, model_point) - self._opening_drag_offset)
            self._update_opening_preview(opening)
            self._drag_started = True
            event.accept()
            return
        if self._pending_type_id or self._dragging_id:
            self._preview_from_cursor(model_point)
            if self._dragging_id:
                self._drag_started = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_opening_id:
            opening_id = self._dragging_opening_id
            if self._drag_started and self._preview_valid and self._preview_position:
                self.openingMoveRequested.emit(opening_id, self._preview_position[0])
            self._dragging_opening_id = None
            self._drag_started = False
            self._clear_preview()
            self.unsetCursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_id:
            cabinet_id = self._dragging_id
            if self._drag_started and self._preview_valid and self._preview_position:
                self.cabinetMoveRequested.emit(cabinet_id, *self._preview_position)
            self._dragging_id = None
            self._drag_started = False
            self._clear_preview()
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and any((
            self._pending_type_id,
            self._dragging_id,
            self._pending_opening_kind,
            self._dragging_opening_id,
            self._wall_select_mode,
        )):
            self.cancel_interaction()
            event.accept()
            return
        super().keyPressEvent(event)


class Cabinet3DView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cabinet3D")
        self._cabinet = Cabinet()
        self._cabinets = [self._cabinet]
        self._room = Room()
        self._selected_cabinet_id = self._cabinet.cabinet_id
        self._doors_visible = True
        self._presentation_mode = False
        self._room_walls_visible = True
        self._door_actors: list[object] = []
        self._handle_actors: list[object] = []
        self._shelf_actors: list[object] = []
        self._selection_actors: list[object] = []
        self._environment_actors: list[object] = []
        self._room_wall_actors: list[object] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        self.plotter.set_background("#F3F6F8", top="#DDE6EC")
        self.plotter.enable_anti_aliasing("ssaa")
        layout.addWidget(self.plotter.interactor)
        self.update_cabinet(self._cabinet, reset_camera=True)

    @property
    def doors_visible(self) -> bool:
        return self._doors_visible

    @property
    def door_actor_count(self) -> int:
        return len(self._door_actors)

    @property
    def handle_actor_count(self) -> int:
        return len(self._handle_actors)

    @property
    def shelf_actor_count(self) -> int:
        return len(self._shelf_actors)

    @property
    def presentation_mode(self) -> bool:
        return self._presentation_mode

    @property
    def environment_actor_count(self) -> int:
        return len(self._environment_actors)

    @staticmethod
    def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
        return pv.Box(bounds=(x0, x1, y0, y1, z0, z1))

    def _add_board(
        self,
        mesh,
        colour: str,
        *,
        name: str,
        edge_colour: str = "#263746",
        selected: bool = False,
        finish: str | None = None,
    ):
        surface = FINISH_SURFACES.get(normalized_finish(finish), {}) if finish else {}
        presentation_edge = surface.get("edge", edge_colour) if not selected else edge_colour
        return self.plotter.add_mesh(
            mesh,
            name=name,
            color=colour,
            edge_color=presentation_edge if self._presentation_mode else edge_colour,
            show_edges=True,
            line_width=1.6 if selected else (0.55 if self._presentation_mode else 0.8),
            ambient=surface.get("ambient", 0.40) if self._presentation_mode else 0.28,
            diffuse=surface.get("diffuse", 0.60) if self._presentation_mode else 0.72,
            specular=surface.get("specular", 0.12) if self._presentation_mode else 0.08,
            specular_power=18 if self._presentation_mode else 14,
            smooth_shading=False,
        )

    def _configure_lighting(self) -> None:
        self.plotter.renderer.RemoveAllLights()
        if not self._cabinets:
            return
        min_x, max_x, min_y, max_y, max_h = self._scene_bounds()
        w, d, h = max_x - min_x, max_y - min_y, max_h
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        if self._presentation_mode:
            lights = [
                pv.Light(position=(max_x + w * 0.8, min_y - d * 1.2, h * 2.0), focal_point=(cx, cy, h * 0.46), color="#FFF9EE", intensity=0.88),
                pv.Light(position=(min_x - w * 0.5, min_y - d * 0.4, h * 1.25), focal_point=(cx, cy, h * 0.5), color="#E8EEF1", intensity=0.48),
                pv.Light(position=(cx, max_y + d * 0.5, h * 1.8), focal_point=(cx, cy, h * 0.55), color="#FFF4E5", intensity=0.38),
            ]
        else:
            lights = [
                pv.Light(position=(max_x + w, min_y - d * 1.8, h * 2.2), focal_point=(cx, cy, h / 2), color="white", intensity=0.85),
                pv.Light(position=(min_x - w, min_y - d, h), focal_point=(cx, cy, h / 2), color="#D8F2F3", intensity=0.45),
                pv.Light(position=(cx, max_y + d * 2, h * 1.5), focal_point=(cx, cy, h / 2), color="#FFF2DE", intensity=0.35),
            ]
        for light in lights:
            self.plotter.add_light(light)

    def update_cabinet(self, cabinet: Cabinet, reset_camera: bool = False) -> None:
        room = Room(
            width=max(1200, cabinet.position_x + cabinet.width),
            depth=max(1200, cabinet.position_y + cabinet.depth),
        )
        self.update_scene(room, [cabinet], cabinet.cabinet_id, reset_camera)

    def update_scene(
        self,
        room: Room,
        cabinets: list[Cabinet],
        selected_cabinet_id: str | None,
        reset_camera: bool = False,
    ) -> None:
        room.validate()
        for cabinet in cabinets:
            cabinet.validate()
        self._room = room
        self._cabinets = cabinets
        self._selected_cabinet_id = selected_cabinet_id
        self._cabinet = next(
            (item for item in cabinets if item.cabinet_id == selected_cabinet_id),
            cabinets[0] if cabinets else None,
        )
        self.plotter.clear()
        self._door_actors.clear()
        self._handle_actors.clear()
        self._shelf_actors.clear()
        self._selection_actors.clear()
        self._environment_actors.clear()
        self._room_wall_actors.clear()
        if self._presentation_mode:
            self.plotter.set_background("#F0EEE8", top="#DDE4E5")
            self._add_presentation_environment()
        else:
            self.plotter.set_background("#F3F6F8", top="#DDE6EC")
        for cabinet in cabinets:
            self._add_cabinet_geometry(cabinet, cabinet.cabinet_id == selected_cabinet_id)

        self._configure_lighting()
        if not self._presentation_mode:
            self.plotter.add_axes(line_width=1, color="#4B5F6D")
        self.set_doors_visible(self._doors_visible, render=False)
        self.set_room_walls_visible(self._room_walls_visible, render=False)
        if reset_camera:
            self.reset_view()
        else:
            # Preserve the chosen viewing direction while fitting changed geometry.
            self.plotter.reset_camera()
            self.plotter.render()

    def _add_environment_mesh(self, mesh, *, name: str, colour: str, wall: bool = False, **kwargs):
        actor = self.plotter.add_mesh(
            mesh,
            name=name,
            color=colour,
            show_edges=False,
            ambient=kwargs.pop("ambient", 0.36),
            diffuse=kwargs.pop("diffuse", 0.64),
            specular=kwargs.pop("specular", 0.04),
            **kwargs,
        )
        actor.SetPickable(False)
        self._environment_actors.append(actor)
        if wall:
            self._room_wall_actors.append(actor)
        return actor

    def _wall_segment_mesh(
        self,
        wall_id: str,
        u0: float,
        u1: float,
        z0: float,
        z1: float,
        room_x0: float,
        room_y0: float,
        thickness: float,
    ):
        room_x1 = room_x0 + self._room.width
        room_y1 = room_y0 + self._room.depth
        if wall_id == "NORTH":
            return self._box(room_x0 + u0, room_x0 + u1, room_y0 - thickness, room_y0, z0, z1)
        if wall_id == "SOUTH":
            return self._box(room_x0 + u0, room_x0 + u1, room_y1, room_y1 + thickness, z0, z1)
        if wall_id == "WEST":
            return self._box(room_x0 - thickness, room_x0, room_y0 + u0, room_y0 + u1, z0, z1)
        return self._box(room_x1, room_x1 + thickness, room_y0 + u0, room_y0 + u1, z0, z1)

    def _add_segmented_wall(
        self,
        wall_id: str,
        room_x0: float,
        room_y0: float,
        wall_height: float,
        thickness: float,
        colour: str,
        opacity: float,
    ) -> None:
        openings = [item for item in self._room.openings if item.wall_id == wall_id]
        length = wall_length(self._room, wall_id)
        u_points = sorted({0.0, float(length), *(
            value for item in openings for value in (float(item.offset), float(item.offset + item.width))
        )})
        z_points = sorted({0.0, wall_height, *(
            value for item in openings
            for value in (float(item.elevation), float(item.elevation + item.height))
        )})
        base_names = {
            "SOUTH": "presentation-back-wall",
            "WEST": "presentation-side-wall",
            "NORTH": "presentation-front-wall",
            "EAST": "presentation-right-wall",
        }
        segment_index = 0
        for u0, u1 in zip(u_points, u_points[1:]):
            for z0, z1 in zip(z_points, z_points[1:]):
                mid_u, mid_z = (u0 + u1) / 2, (z0 + z1) / 2
                if any(
                    item.offset < mid_u < item.offset + item.width
                    and item.elevation < mid_z < item.elevation + item.height
                    for item in openings
                ):
                    continue
                name = base_names[wall_id] if segment_index == 0 else f"{base_names[wall_id]}-{segment_index}"
                mesh = self._wall_segment_mesh(wall_id, u0, u1, z0, z1, room_x0, room_y0, thickness)
                self._add_environment_mesh(
                    mesh,
                    name=name,
                    colour=colour,
                    wall=True,
                    opacity=opacity,
                    ambient=0.60,
                    diffuse=0.40,
                    specular=0.02,
                )
                segment_index += 1

        for opening in openings:
            self._add_opening_detail(opening, room_x0, room_y0, thickness)

    def _add_opening_detail(self, opening: Opening, room_x0: float, room_y0: float, thickness: float) -> None:
        trim = 42.0
        frame_colour = "#6C7478" if opening.kind == "window" else "#725B48"
        pieces = [
            (opening.offset - trim, opening.offset, opening.elevation, opening.elevation + opening.height + trim),
            (opening.offset + opening.width, opening.offset + opening.width + trim,
             opening.elevation, opening.elevation + opening.height + trim),
            (opening.offset, opening.offset + opening.width,
             opening.elevation + opening.height, opening.elevation + opening.height + trim),
        ]
        if opening.kind == "window":
            pieces.append((opening.offset, opening.offset + opening.width,
                           opening.elevation - trim, opening.elevation))
        for index, (u0, u1, z0, z1) in enumerate(pieces):
            u0 = max(0.0, u0)
            u1 = min(float(wall_length(self._room, opening.wall_id)), u1)
            z0 = max(0.0, z0)
            z1 = min(float(self._room.height), z1)
            if u1 <= u0 or z1 <= z0:
                continue
            mesh = self._wall_segment_mesh(
                opening.wall_id,
                u0, u1, z0, z1,
                room_x0,
                room_y0,
                thickness + 8,
            )
            self._add_environment_mesh(
                mesh,
                name=f"presentation-opening-{opening.opening_id}-frame-{index}",
                colour=frame_colour,
                wall=True,
                ambient=0.30,
            )
        if opening.kind == "window":
            glass = self._wall_segment_mesh(
                opening.wall_id,
                opening.offset + trim,
                opening.offset + opening.width - trim,
                opening.elevation + trim,
                opening.elevation + opening.height - trim,
                room_x0,
                room_y0,
                max(5.0, thickness * 0.20),
            )
            self._add_environment_mesh(
                glass,
                name=f"presentation-opening-{opening.opening_id}-glass",
                colour="#9CC7D7",
                wall=True,
                opacity=0.30,
                specular=0.32,
            )

    def _add_presentation_environment(self) -> None:
        """Add non-manufacturing room dressing in the project's millimetre coordinate system."""
        origin_x = min((item.position_x for item in self._cabinets), default=0)
        origin_y = min((item.position_y for item in self._cabinets), default=0)
        x0, x1 = -origin_x, self._room.width - origin_x
        y0, y1 = -origin_y, self._room.depth - origin_y
        wall_height, wall_thickness = float(self._room.height), 32.0

        floor = self._box(x0, x1, y0, y1, -24, 0)
        self._add_environment_mesh(floor, name="presentation-floor", colour="#D8D1C5", ambient=0.42, specular=0.03)
        self._add_segmented_wall("SOUTH", x0, y0, wall_height, wall_thickness, "#EEECE6", 0.96)
        self._add_segmented_wall("WEST", x0, y0, wall_height, wall_thickness, "#E5E3DD", 0.94)
        # Keep camera-facing walls open. Their opening frames remain modeled so
        # a north/east opening is still identifiable without veiling furniture.
        for opening in (item for item in self._room.openings if item.wall_id in ("NORTH", "EAST")):
            self._add_opening_detail(opening, x0, y0, wall_thickness)

        back_baseboard = self._box(x0, x1, y1 - 12, y1 + 3, 0, 72)
        side_baseboard = self._box(x0 - 3, x0 + 12, y0, y1, 0, 72)
        self._add_environment_mesh(back_baseboard, name="presentation-back-junction", colour="#C8C1B6", wall=True)
        self._add_environment_mesh(side_baseboard, name="presentation-side-junction", colour="#C8C1B6", wall=True)

        base_units = [item for item in self._cabinets if get_catalogue_item(item.cabinet_type_id).category in ("Base Cabinets", "Vanity") and item.elevation_z == 0]
        if base_units:
            bx0 = min(item.position_x for item in base_units) - origin_x
            bx1 = max(item.position_x + item.width for item in base_units) - origin_x
            backsplash = self._box(bx0, bx1, y1 - 10, y1 + 2, 760, 1360)
            self._add_environment_mesh(backsplash, name="presentation-backsplash", colour="#D6D0C6", wall=True, opacity=0.82)

        for run in connected_base_runs(self._cabinets):
            run_x0, run_x1 = run.x0 - origin_x, run.x1 - origin_x
            run_y0, run_y1 = run.y0 - origin_y, run.y1 - origin_y
            run_key = run.cabinet_ids[0]
            counter_x0, counter_x1 = run_x0 - 8, run_x1 + 8
            counter_y0, counter_y1 = run_y0 - 22, run_y1 + 10
            counter_z0, counter_z1 = run.top_z, run.top_z + 32
            sink_cabinets = [
                cabinet for cabinet in self._cabinets
                if cabinet.cabinet_id in run.cabinet_ids
                and get_catalogue_item(cabinet.cabinet_type_id).front_style == "sink"
            ]
            sink_cutouts = [
                (
                    cabinet.position_x - origin_x + cabinet.width * 0.22,
                    cabinet.position_x - origin_x + cabinet.width * 0.78,
                    cabinet.position_y - origin_y + cabinet.depth * 0.24,
                    cabinet.position_y - origin_y + cabinet.depth * 0.72,
                    cabinet,
                )
                for cabinet in sink_cabinets
            ]
            x_points = sorted({counter_x0, counter_x1, *(value for cutout in sink_cutouts for value in cutout[:2])})
            y_points = sorted({counter_y0, counter_y1, *(value for cutout in sink_cutouts for value in cutout[2:4])})
            counter_index = 0
            for cell_x0, cell_x1 in zip(x_points, x_points[1:]):
                for cell_y0, cell_y1 in zip(y_points, y_points[1:]):
                    mid_x, mid_y = (cell_x0 + cell_x1) / 2, (cell_y0 + cell_y1) / 2
                    if any(sx0 < mid_x < sx1 and sy0 < mid_y < sy1 for sx0, sx1, sy0, sy1, _ in sink_cutouts):
                        continue
                    countertop = self._box(cell_x0, cell_x1, cell_y0, cell_y1, counter_z0, counter_z1)
                    counter_name = (
                        f"presentation-countertop-{run_key}"
                        if counter_index == 0
                        else f"presentation-countertop-{run_key}-{counter_index}"
                    )
                    self._add_environment_mesh(
                        countertop,
                        name=counter_name,
                        colour="#D9D5CC",
                        ambient=0.46,
                        diffuse=0.48,
                        specular=0.20,
                        pbr=True,
                        roughness=0.58,
                        metallic=0.0,
                    )
                    counter_index += 1

            front_edge = self._box(
                counter_x0, counter_x1, counter_y0 - 5, counter_y0 + 3,
                counter_z0, counter_z1,
            )
            self._add_environment_mesh(
                front_edge,
                name=f"presentation-countertop-edge-{run_key}",
                colour="#C5C0B6",
                ambient=0.42,
                diffuse=0.52,
                specular=0.16,
            )
            plinth = self._box(
                run_x0 + 28, run_x1 - 28, run_y0 + 48, run_y1 - 8,
                0, 88,
            )
            self._add_environment_mesh(
                plinth,
                name=f"presentation-plinth-{run_key}",
                colour="#4B4844",
                ambient=0.25,
            )

            # Presentation-only basin: the countertop cells leave a genuine
            # visual recess, while rim, side walls and floor provide depth.
            for sx0, sx1, sy0, sy1, cabinet in sink_cutouts:
                rim = 24.0
                basin_bottom = counter_z0 - 118
                basin_top = counter_z1 + 10
                sink_material = {
                    "colour": "#AAB4B7", "ambient": 0.32, "diffuse": 0.43,
                    "specular": 0.58, "pbr": True, "metallic": 0.62, "roughness": 0.24,
                }
                rim_parts = [
                    (sx0 - rim, sx1 + rim, sy0 - rim, sy0),
                    (sx0 - rim, sx1 + rim, sy1, sy1 + rim),
                    (sx0 - rim, sx0, sy0, sy1),
                    (sx1, sx1 + rim, sy0, sy1),
                ]
                for index, (rx0, rx1, ry0, ry1) in enumerate(rim_parts):
                    self._add_environment_mesh(
                        self._box(rx0, rx1, ry0, ry1, counter_z1, basin_top),
                        name=f"presentation-sink-{cabinet.cabinet_id}-rim-{index}",
                        **sink_material,
                    )
                basin_parts = [
                    (sx0, sx1, sy0, sy1, basin_bottom, basin_bottom + 12),
                    (sx0, sx0 + 16, sy0, sy1, basin_bottom, counter_z1),
                    (sx1 - 16, sx1, sy0, sy1, basin_bottom, counter_z1),
                    (sx0, sx1, sy0, sy0 + 16, basin_bottom, counter_z1),
                    (sx0, sx1, sy1 - 16, sy1, basin_bottom, counter_z1),
                ]
                for index, bounds in enumerate(basin_parts):
                    self._add_environment_mesh(
                        self._box(*bounds),
                        name=(
                            f"presentation-sink-{cabinet.cabinet_id}"
                            if index == 0
                            else f"presentation-sink-{cabinet.cabinet_id}-bowl-{index}"
                        ),
                        colour="#667479",
                        ambient=0.22,
                        diffuse=0.42,
                        specular=0.50,
                        pbr=True,
                        metallic=0.48,
                        roughness=0.30,
                    )

    def _add_cabinet_geometry(self, cabinet: Cabinet, selected: bool) -> None:
        w, h, d, t = cabinet.width, cabinet.height, cabinet.depth, cabinet.board_thickness
        item = get_catalogue_item(cabinet.cabinet_type_id)
        origin_x = min(item.position_x for item in self._cabinets)
        origin_y = min(item.position_y for item in self._cabinets)
        px, py, pz = cabinet.position_x - origin_x, cabinet.position_y - origin_y, cabinet.elevation_z
        body_colour = FINISH_COLOURS[cabinet.material]
        inside_colour = "#AD8B64" if cabinet.material == "Natural Oak" else body_colour
        edge_colour = "#356E70" if selected else "#34434C"
        if selected:
            selection_box = self._box(px - 6, px + w + 6, py - t - 16, py + d + 6, pz - 6, pz + h + 6)
            selection_actor = self.plotter.add_mesh(
                selection_box,
                name=f"{cabinet.cabinet_id}-selection",
                style="wireframe",
                color="#3E8587",
                line_width=2,
                opacity=0.48,
                pickable=False,
            )
            selection_actor.SetUseBounds(False)
            self._selection_actors.append(selection_actor)
        carcass_parts = [
            ("left-side", self._box(px, px + t, py, py + d, pz, pz + h)),
            ("right-side", self._box(px + w - t, px + w, py, py + d, pz, pz + h)),
            ("top", self._box(px + t, px + w - t, py, py + d, pz + h - t, pz + h)),
            ("bottom", self._box(px + t, px + w - t, py, py + d, pz, pz + t)),
            ("back", self._box(px + t, px + w - t, py + d - 6, py + d, pz + t, pz + h - t)),
        ]
        if self._presentation_mode and item.front_style == "sink":
            carcass_parts = [part for part in carcass_parts if part[0] != "top"]
        for name, part in carcass_parts:
            self._add_board(
                part, body_colour, name=f"{cabinet.cabinet_id}-{name}",
                edge_colour=edge_colour, selected=selected, finish=cabinet.material,
            )
        for shelf_index in range(cabinet.shelf_count):
            z = pz + (h - 2 * t) * (shelf_index + 1) / (cabinet.shelf_count + 1) + t
            shelf = self._box(px + t, px + w - t, py + 18, py + d - 8, z - t / 2, z + t / 2)
            actor = self._add_board(
                shelf,
                inside_colour,
                name=f"{cabinet.cabinet_id}-shelf-{shelf_index}",
                edge_colour=edge_colour,
                selected=selected,
                finish=cabinet.material,
            )
            self._shelf_actors.append(actor)
        if item.front_style == "corner":
            return_panel = self._box(px + w - t, px + w, py - min(120, d * 0.2), py + d, pz, pz + h)
            self._add_board(
                return_panel, body_colour, name=f"{cabinet.cabinet_id}-corner-return",
                edge_colour=edge_colour, selected=selected, finish=cabinet.material,
            )
        if item.front_style == "sink" and not self._presentation_mode:
            basin = self._box(px + w * 0.23, px + w * 0.77, py + d * 0.25, py + d * 0.72, pz + h - 8, pz + h + 12)
            self.plotter.add_mesh(basin, name=f"{cabinet.cabinet_id}-sink", color="#AAB3B8", metallic=0.7, roughness=0.28)
        if item.front_style == "appliance":
            appliance = self._box(px + 12, px + w - 12, py - t - 10, py - 9, pz + h * 0.34, pz + h * 0.66)
            self.plotter.add_mesh(appliance, name=f"{cabinet.cabinet_id}-appliance", color="#20272C", edge_color="#9AA7AF", show_edges=True)

        reveal = 3.0
        door_front = py - 8.0
        door_back = door_front - t
        handle_length = max(90.0, min(180.0, h * 0.24))
        handle_radius = max(4.0, min(7.0, t * 0.3))
        if item.front_style == "drawers" and cabinet.drawer_count:
            drawer_height = (h - ((cabinet.drawer_count + 1) * reveal)) / cabinet.drawer_count
            for drawer_index in range(cabinet.drawer_count):
                z0 = pz + reveal + drawer_index * (drawer_height + reveal)
                drawer = self._box(px + reveal, px + w - reveal, door_back, door_front, z0, z0 + drawer_height)
                actor = self._add_board(
                    drawer, body_colour, name=f"{cabinet.cabinet_id}-drawer-{drawer_index}",
                    edge_colour=edge_colour, selected=selected, finish=cabinet.material,
                )
                self._door_actors.append(actor)
                handle = pv.Cylinder(
                    center=(px + w / 2, door_back - handle_radius * 2.2, z0 + drawer_height * 0.72),
                    direction=(1, 0, 0), radius=handle_radius, height=min(220, w * 0.42), resolution=28, capping=True,
                )
                self._handle_actors.append(self.plotter.add_mesh(handle, name=f"{cabinet.cabinet_id}-handle-{drawer_index}", color="#303A42", metallic=0.75, roughness=0.24, smooth_shading=True))
            return
        if not cabinet.door_count or item.front_style == "open":
            return
        door_width = (w - ((cabinet.door_count + 1) * reveal)) / cabinet.door_count
        for door_index in range(cabinet.door_count):
            x0 = px + reveal + door_index * (door_width + reveal)
            z0, z1 = pz + reveal, pz + h - reveal
            if item.front_style == "appliance":
                if door_index == 0:
                    z1 = pz + h * 0.33
                else:
                    z0 = pz + h * 0.67
                x0, door_width = px + reveal, w - 2 * reveal
            door = self._box(x0, x0 + door_width, door_back, door_front, z0, z1)
            actor = self._add_board(
                door,
                body_colour,
                name=f"{cabinet.cabinet_id}-door-{door_index}",
                edge_colour=edge_colour,
                selected=selected,
                finish=cabinet.material,
            )
            self._door_actors.append(actor)
            if cabinet.door_count == 1:
                handle_x = x0 + door_width - max(28.0, door_width * 0.08)
            elif door_index < cabinet.door_count / 2:
                handle_x = x0 + door_width - max(22.0, door_width * 0.07)
            else:
                handle_x = x0 + max(22.0, door_width * 0.07)
            handle = pv.Cylinder(
                center=(handle_x, door_back - handle_radius * 2.2, pz + h * 0.52),
                direction=(1, 0, 0) if item.front_style == "lift_up" else (0, 0, 1),
                radius=handle_radius,
                height=handle_length,
                resolution=28,
                capping=True,
            )
            handle_actor = self.plotter.add_mesh(
                handle,
                name=f"{cabinet.cabinet_id}-handle-{door_index}",
                color="#147D83" if selected else "#303A42",
                metallic=0.75,
                roughness=0.24,
                smooth_shading=True,
                specular=0.9,
                specular_power=45,
            )
            self._handle_actors.append(handle_actor)

    def _scene_bounds(self) -> tuple[float, float, float, float, float]:
        if not self._cabinets:
            return (0, float(self._room.width), 0, float(self._room.depth), float(self._room.height))
        origin_x = min(item.position_x for item in self._cabinets)
        origin_y = min(item.position_y for item in self._cabinets)
        return (
            0,
            max(item.position_x + item.width for item in self._cabinets) - origin_x,
            0,
            max(item.position_y + item.depth for item in self._cabinets) - origin_y,
            max(item.elevation_z + item.height for item in self._cabinets),
        )

    def set_doors_visible(self, visible: bool, *, render: bool = True) -> None:
        self._doors_visible = visible
        for actor in [*self._door_actors, *self._handle_actors]:
            actor.SetVisibility(visible)
        if render:
            self.plotter.render()

    def set_presentation_mode(self, enabled: bool) -> None:
        if self._presentation_mode == enabled:
            return
        self._presentation_mode = enabled
        self.update_scene(self._room, self._cabinets, self._selected_cabinet_id, reset_camera=True)

    def set_room_walls_visible(self, visible: bool, *, render: bool = True) -> None:
        self._room_walls_visible = visible
        for actor in self._room_wall_actors:
            actor.SetVisibility(visible)
        if render:
            self.plotter.reset_camera_clipping_range()
            self.plotter.render()

    def view_front(self) -> None:
        min_x, max_x, min_y, _max_y, max_h = self._scene_bounds()
        width = max_x - min_x
        distance = max(width, max_h) * 2.25
        self.plotter.camera_position = [
            ((min_x + max_x) / 2, min_y - distance, max_h / 2),
            ((min_x + max_x) / 2, min_y, max_h / 2),
            (0, 0, 1),
        ]
        self.plotter.reset_camera()
        self.plotter.render()

    def view_isometric(self) -> None:
        if self._presentation_mode:
            self.view_presentation()
            return
        min_x, max_x, min_y, max_y, max_h = self._scene_bounds()
        width, depth = max_x - min_x, max_y - min_y
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        self.plotter.camera_position = [
            (cx + width * 0.38, min_y - max(depth * 1.55, width * 0.78), max_h * 1.08),
            (cx, cy + depth * 0.10, max_h * 0.48),
            (0, 0, 1),
        ]
        self.plotter.reset_camera()
        self.plotter.render()

    def view_presentation(self) -> None:
        origin_x = min((item.position_x for item in self._cabinets), default=0)
        origin_y = min((item.position_y for item in self._cabinets), default=0)
        x0, x1 = -origin_x, self._room.width - origin_x
        y0, y1 = -origin_y, self._room.depth - origin_y
        cx = (x0 + x1) / 2
        self.plotter.camera_position = [
            (x1 + self._room.width * 0.44, y0 - self._room.depth * 0.78, 2820),
            (cx - self._room.width * 0.04, y1 - 500, 1030),
            (0, 0, 1),
        ]
        self.plotter.camera.view_angle = 30.0
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()

    def fit_all_cabinets(self) -> None:
        """Fit the complete cabinet assembly without changing the current view direction."""
        self.plotter.camera.view_angle = 27.0 if self._presentation_mode else 30.0
        self.plotter.reset_camera()
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()

    def reset_view(self) -> None:
        if self._presentation_mode:
            self.view_presentation()
        else:
            self.view_isometric()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.plotter.close()
        super().closeEvent(event)
