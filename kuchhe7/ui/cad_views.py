from __future__ import annotations

from copy import deepcopy
from math import cos, pi, sin

import pyvista as pv
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkRenderingCore import vtkCellPicker
from pyvistaqt import QtInteractor
from PySide6.QtCore import QEvent, QLineF, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget

from ..catalogue import create_catalogue_cabinet, get_catalogue_item, normalized_finish
from ..models import Cabinet, Opening, PlacedProduct, Room
from ..product_libraries import CURATED_PROP_IDS, get_product, product_colour
from .prop_geometry import add_curated_prop_geometry
from .presentation_textures import (
    backsplash_texture, door_wood_texture, floor_texture, garden_texture, map_surface,
    plaster_texture, stone_texture, wood_texture,
)
from ..openings import opening_error, opening_furniture_conflict, wall_length
from ..placement import placement_error, product_placement_error, snap_position
from ..presentation import connected_base_runs


FINISH_COLOURS = {
    "Warm White": "#E8E5DE",
    "Cashmere": "#BDB2A5",
    "Natural Oak": "#B99568",
    "Walnut": "#694B39",
    "Graphite": "#43474A",
    "White Matte": "#E8E5DE",
    "Cashmere / Greige Matte": "#BDB2A5",
    "Graphite Grey": "#43474A",
}

FINISH_SURFACES = {
    "Warm White": {"edge": "#C8C3B9", "ambient": 0.39, "diffuse": 0.61, "specular": 0.13},
    "Cashmere": {"edge": "#968D81", "ambient": 0.37, "diffuse": 0.63, "specular": 0.11},
    "Natural Oak": {"edge": "#856B4F", "ambient": 0.35, "diffuse": 0.65, "specular": 0.08},
    "Walnut": {"edge": "#46352B", "ambient": 0.38, "diffuse": 0.62, "specular": 0.09},
    "Graphite": {"edge": "#33383A", "ambient": 0.40, "diffuse": 0.60, "specular": 0.12},
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
    productSelected = Signal(str)
    productPlacementRequested = Signal(str, int, int)
    productMoveRequested = Signal(str, int, int)
    placementRejected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("roomPlan")
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor("#FAF9F6"))
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
        self._product_items: dict[str, QGraphicsItem] = {}
        self._products: list[PlacedProduct] = []
        self._selected_product_id: str | None = None
        self._pending_product_type_id: str | None = None
        self._dragging_product_id: str | None = None
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
        self._product_preview_error: str | None = None
        self._snap_enabled = True
        self._grid_snap_enabled = True
        self.redraw(self._room, self._cabinets, self._selected_cabinet_id)

    @staticmethod
    def _dimension_font() -> QFont:
        return QFont("Segoe UI", 9, QFont.Weight.DemiBold)

    def _draw_horizontal_dimension(self, x1: float, x2: float, wall_y: float, value: int) -> None:
        scene = self.scene()
        dim_y = wall_y - 36
        pen = QPen(QColor("#817D73"), 1)
        pen.setCosmetic(True)
        scene.addLine(x1, wall_y - 3, x1, dim_y - 5, pen)
        scene.addLine(x2, wall_y - 3, x2, dim_y - 5, pen)
        scene.addLine(x1, dim_y, x2, dim_y, pen)
        scene.addLine(x1, dim_y, x1 + 8, dim_y - 4, pen)
        scene.addLine(x1, dim_y, x1 + 8, dim_y + 4, pen)
        scene.addLine(x2, dim_y, x2 - 8, dim_y - 4, pen)
        scene.addLine(x2, dim_y, x2 - 8, dim_y + 4, pen)
        label = scene.addText(f"{value:,} mm", self._dimension_font())
        label.setDefaultTextColor(QColor("#535C57"))
        label_rect = label.boundingRect()
        label.setPos((x1 + x2 - label_rect.width()) / 2, dim_y - label_rect.height() - 3)

    def _draw_vertical_dimension(self, y1: float, y2: float, wall_x: float, value: int) -> None:
        scene = self.scene()
        dim_x = wall_x - 40
        pen = QPen(QColor("#817D73"), 1)
        pen.setCosmetic(True)
        scene.addLine(wall_x - 3, y1, dim_x + 5, y1, pen)
        scene.addLine(wall_x - 3, y2, dim_x + 5, y2, pen)
        scene.addLine(dim_x, y1, dim_x, y2, pen)
        scene.addLine(dim_x, y1, dim_x - 4, y1 + 8, pen)
        scene.addLine(dim_x, y1, dim_x + 4, y1 + 8, pen)
        scene.addLine(dim_x, y2, dim_x - 4, y2 - 8, pen)
        scene.addLine(dim_x, y2, dim_x + 4, y2 - 8, pen)
        label = scene.addText(f"{value:,} mm", self._dimension_font())
        label.setDefaultTextColor(QColor("#535C57"))
        label.setRotation(-90)
        label.setPos(dim_x - label.boundingRect().height() - 3, (y1 + y2 + label.boundingRect().width()) / 2)

    def redraw(
        self,
        room: Room,
        cabinets: list[Cabinet] | Cabinet,
        selected_cabinet_id: str = "C1",
        selected_opening_id: str | None = None,
        selected_wall_id: str = "WEST",
        placed_products: list[PlacedProduct] | None = None,
        selected_product_id: str | None = None,
    ) -> None:
        if isinstance(cabinets, Cabinet):
            cabinets = [cabinets]
            selected_cabinet_id = cabinets[0].cabinet_id
        self._room, self._cabinets = room, cabinets
        self._selected_cabinet_id = selected_cabinet_id
        self._selected_opening_id = selected_opening_id
        self._selected_wall_id = selected_wall_id
        self._products = placed_products or []
        self._selected_product_id = selected_product_id
        scene = self.scene()
        scene.clear()
        self._cabinet_items.clear()
        self._product_items.clear()
        self._wall_items.clear()
        self._opening_items.clear()
        self._preview_item = None
        self._preview_label = None
        self._guide_items.clear()
        scale = min(680 / room.width, 510 / room.depth)
        ox, oy = 74.0, 68.0
        self._scale, self._ox, self._oy = scale, ox, oy
        rw, rd = room.width * scale, room.depth * scale

        grid_pen = QPen(QColor("#E7E2D9"), 0.8, Qt.PenStyle.DashLine)
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
                QColor("#60766F" if selected_wall else "#333B3C"),
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
            cw, cd = cabinet.footprint_width * scale, cabinet.footprint_depth * scale
            cabinet_x = ox + cabinet.position_x * scale
            cabinet_y = oy + cabinet.position_y * scale
            def plan_point(local_x: float, local_y: float) -> QPointF:
                w, d = cabinet.width, cabinet.depth
                rotated = {
                    0: (local_x, local_y),
                    90: (d - local_y, local_x),
                    180: (w - local_x, d - local_y),
                    270: (local_y, w - local_x),
                }[cabinet.orientation_degrees]
                return QPointF(cabinet_x + rotated[0] * scale, cabinet_y + rotated[1] * scale)
            outline = QColor("#60766F") if selected else QColor("#596560")
            footprint_pen = QPen(outline, 2.2 if selected else 1.2)
            footprint_pen.setCosmetic(True)
            if catalogue_item.category == "Wall Cabinets":
                footprint_pen.setStyle(Qt.PenStyle.DashLine)
            fill = QColor(PLAN_FINISH_COLOURS[cabinet.material])
            if catalogue_item.front_style == "corner":
                inset = min(cabinet.width, cabinet.depth) * 0.42
                cabinet_item = scene.addPolygon(QPolygonF([
                    plan_point(0, 0), plan_point(cabinet.width, 0),
                    plan_point(cabinet.width, cabinet.depth), plan_point(inset, cabinet.depth),
                    plan_point(inset, inset), plan_point(0, inset),
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
            front_pen = QPen(QColor("#50675E"), 1.7)
            front_pen.setCosmetic(True)
            front_line = scene.addLine(QLineF(plan_point(0, 0), plan_point(cabinet.width, 0)), front_pen)
            front_line.setZValue(cabinet_item.zValue() + 1)
            divisions = cabinet.drawer_count if catalogue_item.front_style == "drawers" else cabinet.door_count
            for index in range(1, divisions):
                x = cabinet.width * index / divisions
                scene.addLine(QLineF(plan_point(x, 0), plan_point(x, min(10 / scale, cabinet.depth))), QPen(QColor("#FFFFFF"), 1.2))
            compact_names = {
                "base_2_door": "BASE", "base_3_drawer": "DRAWERS",
                "base_4_drawer": "DRAWERS", "sink_base": "SINK",
                "open_shelf_base": "SHELF", "corner_base": "CORNER",
                "wall_2_door": "WALL", "wall_lift_up": "WALL",
                "wall_open_shelf": "SHELF", "corner_wall": "CORNER",
                "tall_pantry": "PANTRY", "oven_tall": "OVEN",
                "utility_tall": "UTILITY", "vanity_base": "VANITY",
                "vanity_drawer": "VANITY", "wardrobe_2_door": "WARDROBE",
                "wardrobe_open": "WARDROBE",
            }
            plan_name = compact_names.get(cabinet.cabinet_type_id, "CABINET")
            is_wall = catalogue_item.category == "Wall Cabinets"
            stacked = any(
                (get_catalogue_item(other.cabinet_type_id).category == "Wall Cabinets") != is_wall
                and other.position_x < cabinet.position_x + cabinet.footprint_width
                and cabinet.position_x < other.position_x + other.footprint_width
                and other.position_y < cabinet.position_y + cabinet.footprint_depth
                and cabinet.position_y < other.position_y + other.footprint_depth
                for other in cabinets if other.cabinet_id != cabinet.cabinet_id)
            label_font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
            label = scene.addText(f"{cabinet.cabinet_id} {plan_name}", label_font)
            if not stacked:
                label.setPlainText(f"{cabinet.cabinet_id} {plan_name}\n{cabinet.width} × {cabinet.depth} mm")
            if label.boundingRect().width() > max(1, cw - 6):
                label.setPlainText(f"{cabinet.cabinet_id} {plan_name}")
            if label.boundingRect().width() > max(1, cw - 6):
                label.setPlainText(cabinet.cabinet_id)
            label.setToolTip(f"{cabinet.cabinet_id} · {catalogue_item.name}\n"
                             f"{cabinet.width} × {cabinet.height} × {cabinet.depth} mm")
            label.setData(0, cabinet.cabinet_id)
            label.setDefaultTextColor(QColor("#365349") if selected else QColor("#293136"))
            label.setZValue(30)
            if label.boundingRect().height() > max(1, cd - 6):
                label.setPlainText(cabinet.cabinet_id)
            label_y = (cabinet_y + cd - label.boundingRect().height() - 3
                       if stacked and not is_wall else cabinet_y + 3)
            label.setPos(cabinet_x + 3, label_y)

        for product in self._products:
            definition = get_product(product.type_id)
            selected = product.item_id == selected_product_id
            x, y = ox + product.position_x * scale, oy + product.position_y * scale
            colour = QColor(product_colour(product.type_id, product.appearance))
            colour.setAlpha(185 if selected else (85 if definition.library == "Decorative Props" else 135))
            pen = QPen(QColor("#60766F" if selected else "#929A94"), 2.6 if selected else 1.4)
            if product.elevation_z:
                pen.setStyle(Qt.PenStyle.DashLine)
            footprint = scene.addRect(x, y, product.footprint_width * scale, product.footprint_depth * scale, pen, colour)
            footprint.setData(0, f"product:{product.item_id}")
            footprint.setToolTip(f"{product.item_id} · {definition.name}\n{product.width} × {product.depth} × {product.height} mm")
            footprint.setZValue(40)
            self._product_items[product.item_id] = footprint
            label_text = (product.item_id if definition.library == "Decorative Props"
                          else f"{product.item_id} · {definition.name.split()[-1].upper()}")
            label = scene.addText(label_text,
                                  QFont("Segoe UI", 7, QFont.Weight.DemiBold))
            label.setData(0, f"product:{product.item_id}")
            label.setDefaultTextColor(QColor("#173B44"))
            label.setPos(x + 3, y + 2)
            label.setZValue(41)

        self._draw_horizontal_dimension(ox, ox + rw, oy, room.width)
        self._draw_vertical_dimension(oy, oy + rd, ox, room.depth)
        scene.setSceneRect(10, 8, rw + 96, rd + 106)
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
        accent = QColor("#B49A77" if selected else ("#60766F" if opening.kind == "door" else "#819BA0"))
        if opening.kind == "window":
            window_pen = QPen(accent, 3)
            window_pen.setCosmetic(True)
            line = self.scene().addLine(start.x(), start.y(), end.x(), end.y(), window_pen)
            self._tag_item(line, key, 12)
            self._opening_items[opening.opening_id] = line
        else:
            left_hinge = opening.swing.startswith("Left")
            inward = opening.swing.endswith("In")
            hinge_u = opening.offset if left_hinge else opening.offset + opening.width
            direction = 1.0 if inward else -1.0
            hinge = self._wall_local_to_scene(opening.wall_id, hinge_u)
            leaf_end = self._wall_local_to_scene(opening.wall_id, hinge_u, direction * opening.width)
            leaf_pen = QPen(accent, 2)
            leaf_pen.setCosmetic(True)
            leaf = self.scene().addLine(hinge.x(), hinge.y(), leaf_end.x(), leaf_end.y(), leaf_pen)
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
            arc_pen = QPen(accent.lighter(115), 1.2, Qt.PenStyle.DashLine)
            arc_pen.setCosmetic(True)
            arc = self.scene().addPath(path, arc_pen)
            self._tag_item(arc, key, 11)
            self._opening_items[opening.opening_id] = leaf

        midpoint = (start + end) / 2
        label = self.scene().addText(
            f"{opening.opening_id}  {opening.width} mm\noffset {opening.offset} mm",
            QFont("Segoe UI", 8, QFont.Weight.Bold if selected else QFont.Weight.DemiBold),
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

    def begin_product_placement(self, type_id: str) -> None:
        self.cancel_interaction(emit_signal=False)
        get_product(type_id)
        self._pending_product_type_id = type_id
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()

    def cancel_interaction(self, *, emit_signal: bool = True) -> None:
        had_interaction = any((
            self._pending_type_id is not None,
            self._dragging_id is not None,
            self._pending_opening_kind is not None,
            self._dragging_opening_id is not None,
            self._wall_select_mode,
            self._pending_product_type_id is not None,
            self._dragging_product_id is not None,
        ))
        self._pending_type_id = None
        self._dragging_id = None
        self._pending_product_type_id = None
        self._dragging_product_id = None
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
        self._product_preview_error = None

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
        error = placement_error(self._room, self._cabinets, candidate, self._products)
        self._clear_preview()
        valid = error is None
        colour = QColor("#39A58A" if valid else "#C95145")
        colour.setAlpha(105)
        x = self._ox + candidate.position_x * self._scale
        y = self._oy + candidate.position_y * self._scale
        width, depth = candidate.footprint_width * self._scale, candidate.footprint_depth * self._scale
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
        if self._pending_product_type_id or self._dragging_product_id:
            product = (next(item for item in self._products if item.item_id == self._dragging_product_id)
                       if self._dragging_product_id else None)
            definition = get_product(product.type_id if product else self._pending_product_type_id)
            width = product.footprint_width if product else definition.width
            depth = product.footprint_depth if product else definition.depth
            x = round(model_point.x() - (self._drag_offset.x() if product else width / 2))
            y = round(model_point.y() - (self._drag_offset.y() if product else depth / 2))
            candidate = deepcopy(product) if product else PlacedProduct(
                "PREVIEW", definition.type_id, x, y, definition.elevation_z,
                definition.width, definition.depth, definition.height,
            )
            candidate.position_x, candidate.position_y = x, y
            error = product_placement_error(self._room, self._cabinets, self._products, candidate)
            self._clear_preview()
            valid = error is None
            colour = QColor("#39A58A" if valid else "#C95145")
            colour.setAlpha(95)
            self._preview_item = self.scene().addRect(
                self._ox + x * self._scale, self._oy + y * self._scale,
                width * self._scale, depth * self._scale,
                QPen(QColor("#147D83" if valid else "#9A2F29"), 2, Qt.PenStyle.DashLine), colour,
            )
            self._preview_item.setZValue(100)
            self._preview_position, self._preview_valid = (x, y), valid
            self._product_preview_error = error
            if error:
                self._preview_label = self.scene().addText(error, QFont("Segoe UI", 8, QFont.Weight.DemiBold))
                self._preview_label.setDefaultTextColor(QColor("#8E2822"))
                self._preview_label.setPos(self._ox + x * self._scale + 4, self._oy + y * self._scale - 24)
                self._preview_label.setZValue(101)
            return
        if self._pending_type_id:
            candidate = create_catalogue_cabinet(self._pending_type_id, "PREVIEW")
            candidate.position_x = round(model_point.x() - candidate.footprint_width / 2)
            candidate.position_y = round(model_point.y() - candidate.footprint_depth / 2)
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
        if self._pending_product_type_id:
            self._preview_from_cursor(model_point)
            if self._preview_valid and self._preview_position:
                self.productPlacementRequested.emit(self._pending_product_type_id, *self._preview_position)
            elif self._product_preview_error:
                self.placementRejected.emit(self._product_preview_error)
            event.accept()
            return
        item = self.itemAt(event.position().toPoint())
        item_data = item.data(0) if item else None
        if isinstance(item_data, str) and item_data.startswith("product:"):
            product_id = item_data.split(":", 1)[1]
            product = next(item for item in self._products if item.item_id == product_id)
            self.productSelected.emit(product_id)
            self._dragging_product_id = product_id
            self._drag_offset = QPointF(model_point.x() - product.position_x, model_point.y() - product.position_y)
            self._drag_started = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
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
        if self._pending_type_id or self._dragging_id or self._pending_product_type_id or self._dragging_product_id:
            self._preview_from_cursor(model_point)
            if self._dragging_id or self._dragging_product_id:
                self._drag_started = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_product_id:
            product_id = self._dragging_product_id
            if self._drag_started and self._preview_valid and self._preview_position:
                self.productMoveRequested.emit(product_id, *self._preview_position)
            self._dragging_product_id = None
            self._drag_started = False
            self._clear_preview()
            self.unsetCursor()
            event.accept()
            return
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
            self._pending_product_type_id,
            self._dragging_product_id,
        )):
            self.cancel_interaction()
            event.accept()
            return
        super().keyPressEvent(event)


class Cabinet3DView(QWidget):
    cabinetSelected = Signal(str)
    productSelected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cabinet3D")
        self._cabinet = Cabinet()
        self._cabinets = [self._cabinet]
        self._room = Room()
        self._products: list[PlacedProduct] = []
        self._selected_product_id: str | None = None
        self._selected_cabinet_id = self._cabinet.cabinet_id
        self._doors_visible = True
        self._presentation_mode = False
        self._room_walls_visible = True
        self._door_actors: list[object] = []
        self._handle_actors: list[object] = []
        self._handle_mount_actors: list[object] = []
        self._shelf_actors: list[object] = []
        self._selection_actors: list[object] = []
        self._environment_actors: list[object] = []
        self._room_wall_actors: list[object] = []
        self._pick_targets: dict[str, tuple[str, str]] = {}
        self._click_press_pos: QPoint | None = None
        self._click_dragged = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        self._plotter_closed = False
        self.plotter.set_background("#F6F4EF", top="#E8E5DF")
        self.plotter.enable_anti_aliasing("ssaa")
        layout.addWidget(self.plotter.interactor)
        self.plotter.interactor.installEventFilter(self)
        self.update_cabinet(self._cabinet, reset_camera=True)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self.plotter.interactor:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._click_press_pos = (
                    event.position().toPoint()
                    if event.button() == Qt.MouseButton.LeftButton
                    and event.modifiers() == Qt.KeyboardModifier.NoModifier else None
                )
                self._click_dragged = False
            elif event.type() == QEvent.Type.MouseMove and self._click_press_pos is not None:
                if (event.position().toPoint() - self._click_press_pos).manhattanLength() > 4:
                    self._click_dragged = True
            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                press = self._click_press_pos
                self._click_press_pos = None
                if press is not None and not self._click_dragged and (
                    event.position().toPoint() - press
                ).manhattanLength() <= 4:
                    # Let VTK finish its mouse release before a selection rebuilds the scene.
                    point = event.position().toPoint()
                    QTimer.singleShot(0, lambda point=point: self._pick_scene_at(point))
        return super().eventFilter(watched, event)

    @staticmethod
    def _actor_key(actor) -> str:
        return actor.GetAddressAsString("")

    def _register_pick_targets(self, before: set[str], kind: str, item_id: str) -> None:
        for name, actor in self.plotter.renderer.actors.items():
            if name not in before and "-selection" not in name and actor.GetPickable():
                self._pick_targets[self._actor_key(actor)] = (kind, item_id)

    def _pick_scene_at(self, point: QPoint) -> None:
        if self._plotter_closed or not self._pick_targets:
            return
        widget = self.plotter.interactor
        render_width, render_height = self.plotter.render_window.GetSize()
        if render_width <= 0 or render_height <= 0:
            return
        if not (0 <= point.x() < widget.width() and 0 <= point.y() < widget.height()):
            return
        picker = vtkCellPicker()
        picker.PickFromListOn()
        for actor in self.plotter.renderer.actors.values():
            if self._actor_key(actor) in self._pick_targets:
                picker.AddPickList(actor)
        x = round(point.x() * render_width / max(1, widget.width()))
        y = round((widget.height() - 1 - point.y()) * render_height / max(1, widget.height()))
        if not picker.Pick(x, y, 0, self.plotter.renderer):
            return  # Empty space follows the existing 2D rule: keep the selection.
        actor = picker.GetActor()
        target = self._pick_targets.get(self._actor_key(actor)) if actor is not None else None
        if target is None:
            return
        kind, item_id = target
        if kind == "cabinet":
            self.cabinetSelected.emit(item_id)
        else:
            self.productSelected.emit(item_id)

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
        finish_name = normalized_finish(finish) if finish else None
        grain = wood_texture(finish_name) if self._presentation_mode and finish_name in ("Walnut", "Natural Oak") else None
        if grain is not None:
            mesh = map_surface(mesh, "front")
        return self.plotter.add_mesh(
            mesh,
            name=name,
            color="#FFFFFF" if grain is not None else colour,
            texture=grain,
            edge_color=presentation_edge if self._presentation_mode else edge_colour,
            show_edges=True,
            line_width=1.4 if selected else (0.65 if self._presentation_mode else 0.8),
            ambient=max(0.78, surface.get("ambient", 0.40)) if self._presentation_mode else 0.28,
            diffuse=0.43 if self._presentation_mode else 0.72,
            specular=max(0.14, surface.get("specular", 0.12)) if self._presentation_mode else 0.08,
            specular_power=34 if self._presentation_mode else 14,
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
                pv.Light(position=(max_x + w * 0.65, min_y - d * 1.15, h * 1.7), focal_point=(cx, cy, h * 0.46), color="#FFF5E9", intensity=1.05),
                pv.Light(position=(min_x - w * 0.55, min_y - d * 0.35, h * 1.3), focal_point=(cx, cy, h * 0.5), color="#EDF2EE", intensity=0.70),
                pv.Light(position=(cx, max_y + d * 0.45, h * 1.55), focal_point=(cx, cy, h * 0.55), color="#FFF0DF", intensity=0.34),
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
            width=max(1200, cabinet.position_x + cabinet.footprint_width),
            depth=max(1200, cabinet.position_y + cabinet.footprint_depth),
        )
        self.update_scene(room, [cabinet], cabinet.cabinet_id, reset_camera)

    def update_scene(
        self,
        room: Room,
        cabinets: list[Cabinet],
        selected_cabinet_id: str | None,
        reset_camera: bool = False,
        placed_products: list[PlacedProduct] | None = None,
        selected_product_id: str | None = None,
    ) -> None:
        room.validate()
        for cabinet in cabinets:
            cabinet.validate()
        self._room = room
        self._products = placed_products or []
        self._selected_product_id = selected_product_id
        self._cabinets = cabinets
        self._selected_cabinet_id = selected_cabinet_id
        self._cabinet = next(
            (item for item in cabinets if item.cabinet_id == selected_cabinet_id),
            cabinets[0] if cabinets else None,
        )
        self.plotter.clear()
        self._pick_targets.clear()
        self._door_actors.clear()
        self._handle_actors.clear()
        self._handle_mount_actors.clear()
        self._shelf_actors.clear()
        self._selection_actors.clear()
        self._environment_actors.clear()
        self._room_wall_actors.clear()
        if self._presentation_mode:
            self.plotter.set_background("#F6F3ED", top="#E9E7E1")
            self._add_presentation_environment()
        else:
            self.plotter.set_background("#F6F4EF", top="#E8E5DF")
        for cabinet in cabinets:
            before = set(self.plotter.renderer.actors)
            self._add_cabinet_geometry(cabinet, cabinet.cabinet_id == selected_cabinet_id)
            self._register_pick_targets(before, "cabinet", cabinet.cabinet_id)
        for product in self._products:
            before = set(self.plotter.renderer.actors)
            self._add_product_geometry(product)
            self._register_pick_targets(before, "product", product.item_id)

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

    def _add_product_geometry(self, product: PlacedProduct) -> None:
        """Visual sample geometry from persisted dimensions; never BOM components."""
        definition = get_product(product.type_id)
        origin_x = min((item.position_x for item in self._cabinets), default=0)
        origin_y = min((item.position_y for item in self._cabinets), default=0)
        x, y, z = product.position_x - origin_x, product.position_y - origin_y, product.elevation_z
        w, d, h = product.width, product.depth, product.height
        colour = product_colour(product.type_id, product.appearance)
        name = f"product-{product.item_id}"
        if product.item_id == self._selected_product_id:
            outline = self._box(x - 5, x + product.footprint_width + 5,
                                y - 5, y + product.footprint_depth + 5, z - 5, z + h + 5)
            actor = self.plotter.add_mesh(outline, name=f"{name}-selection", style="wireframe",
                                          color="#147D83", opacity=0.60, line_width=2, pickable=False)
            actor.SetUseBounds(False)
        if product.type_id in CURATED_PROP_IDS:
            add_curated_prop_geometry(self.plotter, product, definition, x, y, z, name)
            return
        if definition.shape == "sink":
            wall = max(3.0, min(w, d) * 0.055)
            bottom_height = max(2.0, h * 0.12)
            parts = (
                (name, self._box(x, x + w, y, y + d, z, z + bottom_height), "#66767B"),
                (f"{name}-left-rim", self._box(x, x + wall, y, y + d, z + bottom_height, z + h), colour),
                (f"{name}-right-rim", self._box(x + w - wall, x + w, y, y + d, z + bottom_height, z + h), colour),
                (f"{name}-front-rim", self._box(x + wall, x + w - wall, y, y + wall,
                                                 z + bottom_height, z + h), colour),
                (f"{name}-back-rim", self._box(x + wall, x + w - wall, y + d - wall, y + d,
                                                z + bottom_height, z + h), colour),
            )
            for actor_name, mesh, part_colour in parts:
                self.plotter.add_mesh(mesh, name=actor_name, color=part_colour,
                                      show_edges=False, ambient=0.45, diffuse=0.55, specular=0.3)
            return
        if definition.shape == "tap":
            radius = max(3.0, min(w, d) * 0.09)
            base = pv.Cylinder(center=(x + w / 2, y + d * 0.25, z + radius),
                               radius=radius * 2, height=radius * 2)
            arc = pv.Spline([
                (x + w / 2, y + d * 0.25, z + radius),
                (x + w / 2, y + d * 0.25, z + h * 0.78),
                (x + w / 2, y + d * 0.42, z + h),
                (x + w / 2, y + d * 0.72, z + h * 0.84),
                (x + w / 2, y + d * 0.76, z + h * 0.62),
            ], n_points=32).tube(radius=radius)
            self.plotter.add_mesh(base, name=name, color=colour, specular=0.4)
            self.plotter.add_mesh(arc, name=f"{name}-spout", color=colour, specular=0.45)
            return
        if definition.shape in ("plant", "vase", "jar", "light"):
            radius = min(w, d) * 0.43
            body_height = h * 0.43 if definition.shape == "plant" else h
            cylinder = pv.Cylinder(center=(x + w / 2, y + d / 2, z + body_height / 2),
                                   radius=radius, height=body_height)
            self.plotter.add_mesh(cylinder, name=name, color=colour, ambient=0.4, diffuse=0.6)
            if definition.shape == "plant":
                leaves = pv.Sphere(radius=min(w, d) * 0.46,
                                   center=(x + w / 2, y + d / 2, z + h * 0.82))
                self.plotter.add_mesh(leaves, name=f"{name}-leaves", color="#52765A")
            return
        body = self._box(x, x + w, y, y + d, z, z + h)
        self.plotter.add_mesh(body, name=name, color=colour, show_edges=True,
                              edge_color="#68747A", ambient=0.38, diffuse=0.62, specular=0.14)
        if definition.shape in ("oven", "appliance", "fridge"):
            front = self._box(x + w * 0.08, x + w * 0.92, y - 3, y + 3,
                              z + h * 0.18, z + h * 0.82)
            self.plotter.add_mesh(front, name=f"{name}-front",
                                  color="#30383D" if definition.shape == "oven" else "#7F8C91")
            handle = self._box(x + w * 0.3, x + w * 0.7, y - 11, y - 3,
                               z + h * 0.78, z + h * 0.81)
            self.plotter.add_mesh(handle, name=f"{name}-handle", color="#C8D0D0")
        elif definition.shape == "hob":
            for index, (ix, iy) in enumerate(((0.28, 0.3), (0.72, 0.3), (0.28, 0.7), (0.72, 0.7))):
                zone = pv.Cylinder(center=(x + w * ix, y + d * iy, z + h + 2),
                                   radius=min(w, d) * 0.12, height=4)
                self.plotter.add_mesh(zone, name=f"{name}-zone-{index}", color="#A8B1B2")

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
                    map_surface(mesh, "side" if wall_id in ("WEST", "EAST") else "front"),
                    name=name,
                    colour="#FFFFFF",
                    texture=plaster_texture(),
                    wall=True,
                    opacity=opacity,
                    ambient=0.92,
                    diffuse=0.12,
                    specular=0.05,
                )
                segment_index += 1

        for opening in openings:
            self._add_opening_detail(opening, room_x0, room_y0, thickness)

    def _add_opening_detail(self, opening: Opening, room_x0: float, room_y0: float, thickness: float) -> None:
        trim = 30.0 if opening.kind == "window" else 42.0
        frame_colour = "#3D4847" if opening.kind == "window" else "#705139"
        inside_direction = {
            "WEST": (1, 0, 0), "EAST": (-1, 0, 0),
            "SOUTH": (0, -1, 0), "NORTH": (0, 1, 0),
        }[opening.wall_id]

        def inside(mesh: pv.PolyData, distance: float) -> pv.PolyData:
            # Presentation trim projects into the room, preventing coplanar
            # wall/trim faces from flickering during orbit and screenshots.
            return mesh.translate(tuple(distance * axis for axis in inside_direction), inplace=False)

        if opening.kind == "door":
            door_inset = 16.0
            door_u0, door_u1 = opening.offset + door_inset, opening.offset + opening.width - door_inset
            door_z0, door_z1 = opening.elevation + 12, opening.elevation + opening.height - 20
            leaf = self._wall_segment_mesh(
                opening.wall_id, door_u0, door_u1, door_z0, door_z1,
                room_x0, room_y0, thickness * 0.75,
            )
            self._add_environment_mesh(
                map_surface(inside(leaf, 2), "side" if opening.wall_id in ("WEST", "EAST") else "front"),
                name=f"presentation-opening-{opening.opening_id}-leaf",
                colour="#FFFFFF", texture=door_wood_texture(), wall=True,
                ambient=0.78, diffuse=0.25, specular=0.16,
            )
            rail, stile = min(78.0, opening.height * 0.055), min(57.0, opening.width * 0.07)
            door_parts = (
                (door_u0, door_u0 + stile, door_z0, door_z1),
                (door_u1 - stile, door_u1, door_z0, door_z1),
                (door_u0 + stile, door_u1 - stile, door_z0, door_z0 + rail),
                (door_u0 + stile, door_u1 - stile, door_z1 - rail, door_z1),
            )
            for index, (u0, u1, z0, z1) in enumerate(door_parts):
                face = self._wall_segment_mesh(
                    opening.wall_id, u0, u1, z0, z1, room_x0, room_y0, thickness * 0.36,
                )
                self._add_environment_mesh(
                    map_surface(inside(face, 7), "side" if opening.wall_id in ("WEST", "EAST") else "front"),
                    name=f"presentation-opening-{opening.opening_id}-door-moulding-{index}",
                    colour="#FFFFFF", texture=door_wood_texture("frame"), wall=True,
                    ambient=0.74, diffuse=0.24, specular=0.12,
                )
            inset_u0, inset_u1 = door_u0 + stile, door_u1 - stile
            inset_z0, inset_z1 = door_z0 + rail, door_z1 - rail
            bead = 11.0
            inner_beads = (
                (inset_u0, inset_u0 + bead, inset_z0, inset_z1),
                (inset_u1 - bead, inset_u1, inset_z0, inset_z1),
                (inset_u0 + bead, inset_u1 - bead, inset_z0, inset_z0 + bead),
                (inset_u0 + bead, inset_u1 - bead, inset_z1 - bead, inset_z1),
            )
            for index, (u0, u1, z0, z1) in enumerate(inner_beads):
                bead_mesh = self._wall_segment_mesh(
                    opening.wall_id, u0, u1, z0, z1, room_x0, room_y0, thickness * 0.25,
                )
                self._add_environment_mesh(
                    inside(bead_mesh, 4),
                    name=f"presentation-opening-{opening.opening_id}-panel-bead-{index}",
                    colour="#765139", wall=True, ambient=0.62, diffuse=0.32, specular=0.12,
                )
            handle_u = opening.offset + opening.width * (0.77 if "Left" in opening.swing else 0.23)
            handle_z = opening.elevation + min(1030, opening.height * 0.52)
            if opening.wall_id in ("WEST", "EAST"):
                wall_x = room_x0 if opening.wall_id == "WEST" else room_x0 + self._room.width
                handle_center = (wall_x + inside_direction[0] * 25, room_y0 + handle_u, handle_z)
                lever_direction = (0, 1, 0)
            else:
                wall_y = room_y0 if opening.wall_id == "NORTH" else room_y0 + self._room.depth
                handle_center = (room_x0 + handle_u, wall_y + inside_direction[1] * 25, handle_z)
                lever_direction = (1, 0, 0)
            rose_center = tuple(handle_center[index] - inside_direction[index] * 15 for index in range(3))
            self._add_environment_mesh(
                pv.Cylinder(center=rose_center, direction=inside_direction, radius=21, height=5, resolution=24),
                name=f"presentation-opening-{opening.opening_id}-rose",
                colour="#303634", wall=True, ambient=0.43, diffuse=0.48, specular=0.35,
            )
            spindle_center = tuple(handle_center[index] - inside_direction[index] * 7 for index in range(3))
            self._add_environment_mesh(
                pv.Cylinder(center=spindle_center, direction=inside_direction, radius=6, height=19, resolution=16),
                name=f"presentation-opening-{opening.opening_id}-spindle",
                colour="#3B4240", wall=True, ambient=0.40, diffuse=0.50, specular=0.34,
            )
            self._add_environment_mesh(
                pv.Cylinder(center=handle_center, direction=lever_direction, radius=7, height=105, resolution=20),
                name=f"presentation-opening-{opening.opening_id}-handle",
                colour="#343B38", wall=True, ambient=0.43, diffuse=0.48, specular=0.42,
            )
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
                inside(mesh, 9),
                name=f"presentation-opening-{opening.opening_id}-frame-{index}",
                colour=frame_colour,
                wall=True,
                ambient=0.30,
            )
        if opening.kind == "window":
            sill = self._wall_segment_mesh(
                opening.wall_id, opening.offset - 38, opening.offset + opening.width + 38,
                opening.elevation - 49, opening.elevation - 25,
                room_x0, room_y0, thickness + 68,
            )
            self._add_environment_mesh(
                inside(sill, 10), name=f"presentation-opening-{opening.opening_id}-sill",
                colour="#D8D0C5", wall=True, ambient=0.46, diffuse=0.55, specular=0.12,
            )
            u0 = opening.offset + trim
            u1 = opening.offset + opening.width - trim
            z0 = opening.elevation + trim
            z1 = opening.elevation + opening.height - trim
            if opening.wall_id == "WEST":
                backdrop = self._box(room_x0 - 90, room_x0 - 86, room_y0 + u0, room_y0 + u1, z0, z1)
            elif opening.wall_id == "EAST":
                east = room_x0 + self._room.width
                backdrop = self._box(east + 86, east + 90, room_y0 + u0, room_y0 + u1, z0, z1)
            elif opening.wall_id == "SOUTH":
                south = room_y0 + self._room.depth
                backdrop = self._box(room_x0 + u0, room_x0 + u1, south + 86, south + 90, z0, z1)
            else:
                backdrop = self._box(room_x0 + u0, room_x0 + u1, room_y0 - 90, room_y0 - 86, z0, z1)
            self._add_environment_mesh(
                map_surface(backdrop, "side" if opening.wall_id in ("WEST", "EAST") else "front"),
                name=f"presentation-opening-{opening.opening_id}-exterior",
                colour="#FFFFFF", texture=garden_texture(), wall=True,
                ambient=0.70, diffuse=0.32,
            )
            middle = opening.offset + opening.width / 2
            for pane_index, (pane_u0, pane_u1) in enumerate(((u0, middle - 14), (middle + 14, u1))):
                sash = min(24.0, (pane_u1 - pane_u0) * 0.09)
                sash_parts = (
                    (pane_u0, pane_u0 + sash, z0, z1),
                    (pane_u1 - sash, pane_u1, z0, z1),
                    (pane_u0 + sash, pane_u1 - sash, z0, z0 + sash),
                    (pane_u0 + sash, pane_u1 - sash, z1 - sash, z1),
                )
                for part_index, (su0, su1, sz0, sz1) in enumerate(sash_parts):
                    sash_mesh = self._wall_segment_mesh(
                        opening.wall_id, su0, su1, sz0, sz1,
                        room_x0, room_y0, thickness + 10,
                    )
                    self._add_environment_mesh(
                        inside(sash_mesh, 18),
                        name=f"presentation-opening-{opening.opening_id}-sash-{pane_index}-{part_index}",
                        colour="#414A48", wall=True, ambient=0.48, diffuse=0.45,
                        specular=0.28, specular_power=42,
                    )
                glass = self._wall_segment_mesh(
                    opening.wall_id, pane_u0 + sash, pane_u1 - sash,
                    z0 + sash, z1 - sash, room_x0, room_y0, max(5.0, thickness * 0.20),
                )
                self._add_environment_mesh(
                    inside(glass, 5),
                    name=(f"presentation-opening-{opening.opening_id}-glass"
                          if pane_index == 0 else f"presentation-opening-{opening.opening_id}-glass-{pane_index}"),
                    colour="#D6E0DC", wall=True, opacity=0.18,
                    ambient=0.32, diffuse=0.30, specular=0.72, specular_power=60,
                )
            mullion = self._wall_segment_mesh(
                opening.wall_id, middle - 14, middle + 14,
                opening.elevation + trim, opening.elevation + opening.height - trim,
                room_x0, room_y0, thickness + 10,
            )
            self._add_environment_mesh(
                inside(mullion, 15), name=f"presentation-opening-{opening.opening_id}-mullion",
                colour="#394342", wall=True, ambient=0.48, diffuse=0.43,
                specular=0.26, specular_power=42,
            )

    def _add_presentation_environment(self) -> None:
        """Add non-manufacturing room dressing in the project's millimetre coordinate system."""
        origin_x = min((item.position_x for item in self._cabinets), default=0)
        origin_y = min((item.position_y for item in self._cabinets), default=0)
        x0, x1 = -origin_x, self._room.width - origin_x
        y0, y1 = -origin_y, self._room.depth - origin_y
        wall_height, wall_thickness = float(self._room.height), 32.0

        floor = map_surface(self._box(x0, x1, y0, y1, -24, 0), "top")
        self._add_environment_mesh(floor, name="presentation-floor", colour="#FFFFFF",
                                   texture=floor_texture(), ambient=0.48, diffuse=0.50,
                                   specular=0.11, specular_power=28)
        ceiling = self._box(x0, x1, y0, y1, wall_height, wall_height + 16)
        self._add_environment_mesh(ceiling, name="presentation-ceiling", colour="#F2EBE1",
                                   wall=True, ambient=0.91, diffuse=0.10)
        for index, fraction in enumerate((0.22, 0.50, 0.78)):
            downlight = pv.Cylinder(
                center=(x0 + self._room.width * fraction, y0 + self._room.depth * 0.36, wall_height - 6),
                direction=(0, 0, 1), radius=32, height=8, resolution=28,
            )
            self._add_environment_mesh(downlight, name=f"presentation-ceiling-light-{index}",
                                       colour="#FFF0D4", wall=True, ambient=0.68, diffuse=0.32)
        self._add_segmented_wall("SOUTH", x0, y0, wall_height, wall_thickness, "#EEE5D8", 0.98)
        self._add_segmented_wall("WEST", x0, y0, wall_height, wall_thickness, "#E8DDD0", 0.98)
        # Keep camera-facing walls open. Their opening frames remain modeled so
        # a north/east opening is still identifiable without veiling furniture.
        for opening in (item for item in self._room.openings if item.wall_id in ("NORTH", "EAST")):
            self._add_opening_detail(opening, x0, y0, wall_thickness)

        back_baseboard = self._box(x0, x1, y1 - 12, y1 + 3, 0, 72)
        side_baseboard = self._box(x0 - 3, x0 + 12, y0, y1, 0, 72)
        self._add_environment_mesh(back_baseboard, name="presentation-back-junction", colour="#C9BDAE", wall=True)
        self._add_environment_mesh(side_baseboard, name="presentation-side-junction", colour="#C9BDAE", wall=True)

        base_units = [item for item in self._cabinets if get_catalogue_item(item.cabinet_type_id).category in ("Base Cabinets", "Vanity") and item.elevation_z == 0]
        if base_units:
            bx0 = min(item.position_x for item in base_units) - origin_x
            bx1 = max(item.position_x + item.footprint_width for item in base_units) - origin_x
            backsplash = map_surface(self._box(bx0, bx1, y1 - 10, y1 + 2, 760, 1360), "front")
            self._add_environment_mesh(backsplash, name="presentation-backsplash", colour="#FFFFFF",
                                       texture=backsplash_texture(), wall=True,
                                       opacity=0.98, ambient=0.90, diffuse=0.14, specular=0.10)

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
                    countertop = map_surface(
                        self._box(cell_x0, cell_x1, cell_y0, cell_y1, counter_z0, counter_z1),
                        "top", (counter_x0, counter_x1, counter_y0, counter_y1, counter_z0, counter_z1),
                    )
                    counter_name = (
                        f"presentation-countertop-{run_key}"
                        if counter_index == 0
                        else f"presentation-countertop-{run_key}-{counter_index}"
                    )
                    self._add_environment_mesh(
                        countertop,
                        name=counter_name,
                        colour="#FFFFFF",
                        texture=stone_texture(),
                        ambient=0.40,
                        diffuse=0.58,
                        specular=0.22,
                        specular_power=36,
                    )
                    counter_index += 1

            front_edge = self._box(
                counter_x0, counter_x1, counter_y0 - 5, counter_y0 + 3,
                counter_z0, counter_z1,
            )
            self._add_environment_mesh(
                front_edge,
                name=f"presentation-countertop-edge-{run_key}",
                colour="#494744",
                ambient=0.42,
                diffuse=0.52,
                specular=0.16,
            )
            back_cove = self._box(
                counter_x0, counter_x1, counter_y1 - 7, counter_y1 + 1,
                counter_z1 - 3, counter_z1 + 7,
            )
            self._add_environment_mesh(
                back_cove, name=f"presentation-countertop-back-cove-{run_key}",
                colour="#55514E", ambient=0.48, diffuse=0.46, specular=0.14,
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
                    "colour": "#B5C0C0", "ambient": 0.62, "diffuse": 0.38,
                    "specular": 0.46, "specular_power": 52,
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
                        colour="#788689" if index == 0 else "#A9B5B6",
                        ambient=0.56 if index == 0 else 0.64,
                        diffuse=0.37,
                        specular=0.42,
                        specular_power=48,
                    )
                drain = pv.Cylinder(
                    center=((sx0 + sx1) / 2, (sy0 + sy1) / 2, basin_bottom + 15),
                    direction=(0, 0, 1), radius=26, height=3, resolution=24,
                )
                self._add_environment_mesh(
                    drain, name=f"presentation-sink-{cabinet.cabinet_id}-drain",
                    colour="#4A5555", ambient=0.35, diffuse=0.45, specular=0.55,
                )

    def _add_cabinet_geometry(self, cabinet: Cabinet, selected: bool) -> None:
        before = set(self.plotter.renderer.actors)
        self._add_cabinet_geometry_unrotated(cabinet, selected)
        if cabinet.orientation_degrees == 0:
            return
        origin_x = min(item.position_x for item in self._cabinets)
        origin_y = min(item.position_y for item in self._cabinets)
        px, py = cabinet.position_x - origin_x, cabinet.position_y - origin_y
        w, d = cabinet.width, cabinet.depth
        # Rotate the actual cabinet actors (carcass, doors, handles, shelves,
        # selection) into the model's persisted, axis-aligned footprint.
        matrices = {
            90: ((0, -1, px + py + d), (1, 0, py - px)),
            180: ((-1, 0, 2 * px + w), (0, -1, 2 * py + d)),
            270: ((0, 1, px - py), (-1, 0, py + px + w)),
        }
        rows = matrices[cabinet.orientation_degrees]
        matrix = vtkMatrix4x4()
        for row_index, (xx, yy, offset) in enumerate(rows):
            matrix.SetElement(row_index, 0, xx)
            matrix.SetElement(row_index, 1, yy)
            matrix.SetElement(row_index, 3, offset)
        for name, actor in self.plotter.renderer.actors.items():
            if name not in before and hasattr(actor, "SetUserMatrix"):
                actor.SetUserMatrix(matrix)

    def _add_cabinet_geometry_unrotated(self, cabinet: Cabinet, selected: bool) -> None:
        w, h, d, t = cabinet.width, cabinet.height, cabinet.depth, cabinet.board_thickness
        item = get_catalogue_item(cabinet.cabinet_type_id)
        origin_x = min(item.position_x for item in self._cabinets)
        origin_y = min(item.position_y for item in self._cabinets)
        px, py, pz = cabinet.position_x - origin_x, cabinet.position_y - origin_y, cabinet.elevation_z
        body_colour = FINISH_COLOURS[cabinet.material]
        inside_colour = "#AD8B64" if cabinet.material == "Natural Oak" else body_colour
        edge_colour = ("#A56A38" if self._presentation_mode else "#60766F") if selected else "#49514F"
        if selected:
            selection_box = self._box(px - 6, px + w + 6, py - t - 16, py + d + 6, pz - 6, pz + h + 6)
            selection_actor = self.plotter.add_mesh(
                selection_box,
                name=f"{cabinet.cabinet_id}-selection",
                style="wireframe",
                color="#A87343" if self._presentation_mode else "#758A80",
                line_width=1.7,
                opacity=0.55 if self._presentation_mode else 0.36,
                pickable=False,
            )
            selection_actor.SetUseBounds(False)
            self._selection_actors.append(selection_actor)
            if self._presentation_mode:
                front_y = py - t - 17
                front = (
                    (px - 2, front_y, pz - 2),
                    (px + w + 2, front_y, pz - 2),
                    (px + w + 2, front_y, pz + h + 2),
                    (px - 2, front_y, pz + h + 2),
                )
                for index in range(4):
                    rim = self.plotter.add_mesh(
                        pv.Line(front[index], front[(index + 1) % 4]),
                        name=f"{cabinet.cabinet_id}-selection-front-{index}",
                        color="#B6783E", line_width=2.5,
                        render_lines_as_tubes=True, pickable=False,
                    )
                    rim.SetUseBounds(False)
                    self._selection_actors.append(rim)
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
                self._add_handle_mounts(
                    f"{cabinet.cabinet_id}-drawer-{drawer_index}",
                    ((px + w / 2 - min(220, w * 0.42) * 0.34, z0 + drawer_height * 0.72),
                     (px + w / 2 + min(220, w * 0.42) * 0.34, z0 + drawer_height * 0.72)),
                    door_back, handle_radius,
                )
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
                color=("#9A6235" if self._presentation_mode else "#147D83") if selected else "#303A42",
                metallic=0.75,
                roughness=0.24,
                smooth_shading=True,
                specular=0.9,
                specular_power=45,
            )
            self._handle_actors.append(handle_actor)
            if item.front_style != "lift_up":
                self._add_handle_mounts(
                    f"{cabinet.cabinet_id}-door-{door_index}",
                    ((handle_x, pz + h * 0.52 - handle_length * 0.34),
                     (handle_x, pz + h * 0.52 + handle_length * 0.34)),
                    door_back, handle_radius,
                )

    def _add_handle_mounts(
        self, name: str, positions: tuple[tuple[float, float], tuple[float, float]],
        door_back: float, radius: float,
    ) -> None:
        """Visual handle supports; no hardware or BOM quantities are inferred."""
        if not self._presentation_mode:
            return
        for index, (x, z) in enumerate(positions):
            mount = pv.Cylinder(
                center=(x, door_back - radius * 0.9, z),
                direction=(0, 1, 0), radius=max(2.6, radius * 0.62),
                height=radius * 3.4, resolution=12,
            )
            actor = self.plotter.add_mesh(
                mount, name=f"{name}-handle-mount-{index}",
                color="#414947", ambient=0.42, diffuse=0.46,
                specular=0.38, specular_power=38, smooth_shading=True,
            )
            self._handle_mount_actors.append(actor)

    def _scene_bounds(self) -> tuple[float, float, float, float, float]:
        if not self._cabinets:
            return (0, float(self._room.width), 0, float(self._room.depth), float(self._room.height))
        origin_x = min(item.position_x for item in self._cabinets)
        origin_y = min(item.position_y for item in self._cabinets)
        return (
            0,
            max(item.position_x + item.footprint_width for item in self._cabinets) - origin_x,
            0,
            max(item.position_y + item.footprint_depth for item in self._cabinets) - origin_y,
            max(item.elevation_z + item.height for item in self._cabinets),
        )

    def set_doors_visible(self, visible: bool, *, render: bool = True) -> None:
        self._doors_visible = visible
        for actor in [*self._door_actors, *self._handle_actors, *self._handle_mount_actors]:
            actor.SetVisibility(visible)
        if render:
            self.plotter.render()

    def set_presentation_mode(self, enabled: bool) -> None:
        if self._presentation_mode == enabled:
            return
        self._presentation_mode = enabled
        self.update_scene(self._room, self._cabinets, self._selected_cabinet_id, reset_camera=True,
                          placed_products=self._products, selected_product_id=self._selected_product_id)
        self.plotter.render()

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
            (cx - 630 + self._room.width * 0.18,
             y0 - self._room.depth * 0.75, self._room.height * 0.96),
            (cx - 630, y1 - 450, self._room.height * 0.43),
            (0, 0, 1),
        ]
        self.plotter.camera.view_angle = 41.0
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

    def close_plotter(self) -> None:
        """Release VTK/Qt resources while QApplication is still alive."""
        if not self._plotter_closed:
            self._plotter_closed = True
            self.plotter.close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.close_plotter()
        super().closeEvent(event)
