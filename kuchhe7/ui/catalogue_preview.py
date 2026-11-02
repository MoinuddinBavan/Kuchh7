from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

from ..catalogue import CatalogueItem


PREVIEW_COLOURS = {
    "Warm White": "#E8E5DE",
    "Cashmere": "#BDB2A5",
    "Natural Oak": "#B99568",
    "Walnut": "#694B39",
    "Graphite": "#43474A",
}


def catalogue_thumbnail(item: CatalogueItem, finish: str = "Cashmere") -> QPixmap:
    """Draw a compact preview directly from the catalogue geometry definition."""
    pixmap = QPixmap(92, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

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
