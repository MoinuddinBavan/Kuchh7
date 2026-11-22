from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF

from ..catalogue import CatalogueItem
from ..product_libraries import ProductDefinition


PREVIEW_COLOURS = {
    "Warm White": "#E8E5DE",
    "Cashmere": "#BDB2A5",
    "Natural Oak": "#B99568",
    "Walnut": "#694B39",
    "Graphite": "#43474A",
}


def product_thumbnail(item: ProductDefinition) -> QPixmap:
    """Compact drawing derived from sample dimensions and product geometry."""
    pixmap = QPixmap(76, 60)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if item.shape in {
        "potted_green_plant", "floor_plant", "flower_vase", "decorative_vase",
        "fruit_bowl", "utensil_holder", "decorative_tray", "small_sculpture",
    }:
        painter.setPen(QPen(QColor("#58646A"), 1.2))
        if item.shape in ("potted_green_plant", "floor_plant"):
            painter.setBrush(QColor("#B9AEA0"))
            painter.drawRoundedRect(QRectF(26, 36, 24, 18), 4, 4)
            painter.setBrush(QColor("#4E7855"))
            for px, py, rx, ry in ((15, 18, 17, 11), (28, 10, 19, 14),
                                   (44, 18, 17, 11), (25, 25, 25, 13)):
                painter.drawEllipse(QRectF(px, py, rx, ry))
        elif item.shape in ("flower_vase", "decorative_vase"):
            painter.setBrush(QColor(item.colour))
            painter.drawEllipse(QRectF(27, 27, 22, 27))
            painter.drawRect(QRectF(34, 20, 8, 12))
            for px, py in ((24, 11), (37, 6), (50, 12)):
                painter.setPen(QPen(QColor("#69816A" if item.shape == "flower_vase" else "#8F7862"), 1.6))
                painter.drawLine(QPointF(38, 24), QPointF(px + 3, py + 3))
                painter.setBrush(QColor("#D9A7A1" if item.shape == "flower_vase" else "#BAA184"))
                painter.drawEllipse(QRectF(px, py, 7, 7))
        elif item.shape == "fruit_bowl":
            painter.setBrush(QColor("#D2C3A8"))
            painter.drawEllipse(QRectF(15, 27, 47, 24))
            for px, colour in ((25, "#B98550"), (36, "#A5B16C"), (47, "#A65E4C")):
                painter.setBrush(QColor(colour))
                painter.drawEllipse(QRectF(px, 22, 13, 13))
        elif item.shape == "utensil_holder":
            painter.setPen(QPen(QColor("#9A7453"), 3))
            for px, top in ((28, 8), (37, 5), (47, 11)):
                painter.drawLine(QPointF(38, 43), QPointF(px, top))
            painter.setPen(QPen(QColor("#58646A"), 1.2))
            painter.setBrush(QColor("#D2C6B5"))
            painter.drawRoundedRect(QRectF(27, 27, 24, 26), 4, 4)
        elif item.shape == "decorative_tray":
            painter.setBrush(QColor("#A89B8B"))
            painter.drawRoundedRect(QRectF(10, 37, 56, 12), 4, 4)
            painter.setBrush(QColor("#E5DFD3"))
            for px in (25, 44):
                painter.drawRoundedRect(QRectF(px, 25, 12, 16), 3, 3)
        else:
            painter.setBrush(QColor("#D6CEC2"))
            painter.drawEllipse(QRectF(23, 44, 30, 9))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#C3B8A9"), 7))
            painter.drawEllipse(QRectF(28, 14, 22, 33))
        painter.end()
        return pixmap
    width = min(49.0, max(23.0, 42.0 * item.width / max(item.width, item.height)))
    height = min(42.0, max(21.0, 42.0 * item.height / max(item.width, item.height)))
    if item.shape in ("hob", "sink", "board"):
        width, height = 47.0, 25.0
    x, y = (76 - width) / 2, (60 - height) / 2
    painter.setPen(QPen(QColor("#57656B"), 1.3))
    painter.setBrush(QColor(item.colour))
    if item.shape in ("plant", "vase", "jar", "light", "tap"):
        painter.drawRoundedRect(QRectF(x, y, width, height), min(12.0, width / 2), 7.0)
        if item.shape == "plant":
            painter.setBrush(QColor("#52765A"))
            painter.drawEllipse(QRectF(x - 4, y - 5, width + 8, height * 0.55))
    else:
        painter.drawRoundedRect(QRectF(x, y, width, height), 2.0, 2.0)
        if item.shape in ("oven", "fridge", "appliance"):
            painter.setBrush(QColor("#30383D"))
            painter.drawRect(QRectF(x + 4, y + 5, width - 8, height * 0.55))
    painter.end()
    return pixmap


def catalogue_thumbnail(item: CatalogueItem, finish: str = "Cashmere") -> QPixmap:
    """Draw a room-lit furniture preview from the catalogue definition."""
    preview_name = f"{item.type_id}--{finish.lower().replace(' ', '_').replace('/', '_')}.png"
    rendered = Path(__file__).resolve().parent / "cabinet_previews" / preview_name
    if rendered.is_file():
        return QPixmap(str(rendered))
    pixmap = QPixmap(92, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    wall = QLinearGradient(0, 0, 0, 57)
    wall.setColorAt(0, QColor("#F8F1E8"))
    wall.setColorAt(1, QColor("#E8DCCD"))
    painter.fillRect(QRectF(0, 0, 92, 57), wall)
    painter.fillRect(QRectF(0, 57, 92, 15), QColor("#D2BEA5"))
    painter.setPen(QPen(QColor("#BEAA91"), 0.7))
    painter.drawLine(QPointF(0, 57), QPointF(92, 57))

    body = QColor(PREVIEW_COLOURS.get(finish, PREVIEW_COLOURS["Cashmere"]))
    edge = QColor("#46545D")
    side = body.darker(116)
    interior = QColor("#DDD6CC")
    hardware = QColor("#42494D")

    available_height = 57 if item.category == "Tall Units" else 43
    aspect = min(1.55, max(0.62, item.width / item.height))
    front_height = available_height
    front_width = min(57.0, max(29.0, front_height * aspect))
    if item.category == "Wall Cabinets":
        front_height = 34
    x = 45 - front_width / 2
    y = 64 - front_height
    depth_offset = min(11.0, max(6.0, item.depth / max(item.width, 1) * 12))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(61, 48, 35, 42))
    painter.drawEllipse(QRectF(x - 7, 61, front_width + depth_offset + 15, 6))

    if item.front_style == "corner":
        front = QPolygonF([
            QPointF(x, y), QPointF(x + front_width, y), QPointF(x + front_width, y + front_height),
            QPointF(x + front_width * 0.56, y + front_height),
            QPointF(x + front_width * 0.56, y + front_height * 0.55),
            QPointF(x, y + front_height * 0.55),
        ])
        painter.setPen(QPen(edge, 1.2))
        painter.setBrush(body)
        painter.drawPolygon(front)
    else:
        painter.setPen(QPen(edge, 1.2))
        painter.setBrush(side)
        painter.drawPolygon(QPolygonF([
            QPointF(x + front_width, y), QPointF(x + front_width + depth_offset, y - depth_offset * 0.55),
            QPointF(x + front_width + depth_offset, y + front_height - depth_offset * 0.55),
            QPointF(x + front_width, y + front_height),
        ]))
        painter.setBrush(body)
        painter.drawRect(QRectF(x, y, front_width, front_height))

    if item.front_style == "open":
        painter.setBrush(interior)
        painter.drawRect(QRectF(x + 3, y + 3, front_width - 6, front_height - 6))
        for index in range(1, item.shelf_count + 1):
            shelf_y = y + 3 + (front_height - 6) * index / (item.shelf_count + 1)
            painter.drawLine(QPointF(x + 3, shelf_y), QPointF(x + front_width - 3, shelf_y))
    elif item.front_style == "drawers":
        for index in range(1, item.drawer_count):
            split_y = y + front_height * index / item.drawer_count
            painter.drawLine(QPointF(x, split_y), QPointF(x + front_width, split_y))
        painter.setPen(QPen(hardware, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for index in range(item.drawer_count):
            handle_y = y + front_height * (index + 0.68) / item.drawer_count
            painter.drawLine(QPointF(x + front_width * 0.34, handle_y), QPointF(x + front_width * 0.66, handle_y))
    else:
        painter.setPen(QPen(edge, 1.0))
        for index in range(1, max(1, item.door_count)):
            split_x = x + front_width * index / item.door_count
            painter.drawLine(QPointF(split_x, y), QPointF(split_x, y + front_height))
        if item.front_style == "appliance":
            painter.fillRect(QRectF(x + 3, y + front_height * 0.34, front_width - 6, front_height * 0.31), QColor("#343A3E"))
        painter.setPen(QPen(hardware, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        handle_count = max(1, item.door_count)
        for index in range(handle_count):
            handle_x = x + front_width * (index + 0.5) / handle_count
            if item.front_style == "lift_up":
                painter.drawLine(QPointF(x + front_width * 0.34, y + front_height * 0.78), QPointF(x + front_width * 0.66, y + front_height * 0.78))
                break
            painter.drawLine(QPointF(handle_x, y + front_height * 0.43), QPointF(handle_x, y + front_height * 0.62))

    if item.category == "Wall Cabinets":
        painter.setPen(QPen(QColor("#93A2AA"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(12, 66), QPointF(80, 66))
    painter.end()
    return pixmap
