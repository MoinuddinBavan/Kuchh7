"""Small, consistent outline icons for the desktop workspace navigation."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def outline_icon(name: str, colour: str = "#A9B9AD") -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if name == "select":
        painter.drawPolygon(QPolygonF([QPointF(5, 2), QPointF(5, 20), QPointF(10, 15),
                                       QPointF(14, 21), QPointF(17, 19), QPointF(13, 13),
                                       QPointF(20, 11)]))
    elif name == "plan":
        painter.drawRoundedRect(QRectF(3, 3, 18, 18), 1, 1)
        painter.drawLine(12, 3, 12, 21)
        painter.drawLine(3, 12, 21, 12)
    elif name == "front":
        painter.drawRoundedRect(QRectF(4, 4, 16, 16), 1, 1)
        painter.drawLine(12, 4, 12, 20)
        painter.drawLine(7, 17, 9, 17)
        painter.drawLine(15, 17, 17, 17)
    elif name == "undo" or name == "redo":
        painter.drawArc(QRectF(5, 5, 16, 15), 25 * 16, 270 * 16)
        if name == "undo":
            painter.drawLine(6, 10, 2, 7)
            painter.drawLine(2, 7, 8, 5)
        else:
            painter.drawLine(18, 5, 22, 7)
            painter.drawLine(22, 7, 16, 10)
    elif name == "save":
        painter.drawRoundedRect(QRectF(4, 3, 16, 18), 1.5, 1.5)
        painter.drawRect(QRectF(7, 3, 10, 7))
        painter.drawRoundedRect(QRectF(7, 14, 10, 7), 1, 1)
    elif name == "saved":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        painter.drawLine(7, 12, 11, 16)
        painter.drawLine(11, 16, 18, 8)
    elif name == "menu":
        painter.drawLine(4, 7, 20, 7)
        painter.drawLine(4, 12, 20, 12)
        painter.drawLine(4, 17, 20, 17)
    elif name == "snap":
        painter.drawLine(5, 4, 5, 14)
        painter.drawArc(QRectF(5, 8, 14, 12), 180 * 16, 180 * 16)
        painter.drawLine(19, 4, 19, 14)
        painter.drawLine(3, 4, 7, 4)
        painter.drawLine(17, 4, 21, 4)
    elif name == "grid":
        painter.drawRoundedRect(QRectF(3, 3, 18, 18), 1, 1)
        for value in (9, 15):
            painter.drawLine(value, 3, value, 21)
            painter.drawLine(3, value, 21, value)
    elif name == "interior":
        painter.drawLine(4, 5, 20, 5)
        painter.drawLine(4, 5, 4, 21)
        painter.drawLine(20, 5, 20, 21)
        painter.drawLine(4, 21, 20, 21)
        painter.drawLine(4, 14, 20, 14)
        painter.drawLine(8, 9, 16, 9)
    elif name == "unsaved":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        painter.drawLine(12, 7, 12, 13)
        painter.drawPoint(12, 17)
    elif name == "reset":
        painter.drawArc(QRectF(4, 4, 17, 17), 55 * 16, 285 * 16)
        painter.drawLine(4, 7, 4, 3)
        painter.drawLine(4, 3, 9, 5)
    elif name == "design":
        painter.drawPolygon(QPolygonF([QPointF(12, 2), QPointF(21, 7), QPointF(12, 12), QPointF(3, 7)]))
        painter.drawLine(3, 7, 3, 17)
        painter.drawLine(3, 17, 12, 22)
        painter.drawLine(12, 12, 12, 22)
        painter.drawLine(12, 22, 21, 17)
        painter.drawLine(21, 17, 21, 7)
    elif name == "library":
        for x in (3, 13):
            for y in (3, 13):
                painter.drawRoundedRect(QRectF(x, y, 8, 8), 1.5, 1.5)
    elif name == "layers":
        for top in (3, 9, 15):
            painter.drawPolyline(QPolygonF([QPointF(3, top + 2), QPointF(12, top + 7), QPointF(21, top + 2)]))
        painter.drawPolyline(QPolygonF([QPointF(3, 5), QPointF(12, 1), QPointF(21, 5)]))
    elif name == "project":
        painter.drawRoundedRect(QRectF(2, 7, 20, 14), 1.5, 1.5)
        painter.drawLine(2, 7, 9, 7)
        painter.drawLine(4, 4, 10, 4)
        painter.drawLine(10, 4, 13, 7)
    elif name == "materials":
        painter.drawRoundedRect(QRectF(4, 3, 16, 18), 2, 2)
        painter.drawLine(4, 11, 20, 11)
        painter.drawLine(12, 11, 12, 21)
    elif name == "engineering":
        painter.drawRoundedRect(QRectF(3, 5, 18, 15), 1.5, 1.5)
        painter.drawLine(3, 11, 21, 11)
        painter.drawLine(10, 11, 10, 20)
        painter.drawLine(14, 11, 14, 20)
    elif name == "nesting":
        painter.drawRoundedRect(QRectF(3, 3, 18, 18), 2, 2)
        painter.drawRect(QRectF(5, 5, 7, 9))
        painter.drawRect(QRectF(13, 5, 6, 5))
        painter.drawRect(QRectF(13, 11, 6, 8))
    elif name == "documents":
        painter.drawRoundedRect(QRectF(5, 2, 14, 20), 2, 2)
        for y in (8, 12, 16):
            painter.drawLine(8, y, 16, y)
    elif name == "assistant":
        painter.drawPolygon(QPolygonF([QPointF(12, 2), QPointF(14, 9), QPointF(21, 12),
                                       QPointF(14, 14), QPointF(12, 22), QPointF(10, 14),
                                       QPointF(3, 12), QPointF(10, 9)]))
    elif name == "render":
        painter.drawRoundedRect(QRectF(2, 4, 20, 16), 2, 2)
        painter.drawEllipse(QRectF(6, 7, 4, 4))
        painter.drawLine(3, 18, 9, 13)
        painter.drawLine(9, 13, 13, 16)
        painter.drawLine(13, 16, 18, 10)
        painter.drawLine(18, 10, 22, 15)
    elif name == "place":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        painter.drawLine(12, 7, 12, 17)
        painter.drawLine(7, 12, 17, 12)
    elif name == "move":
        painter.drawLine(12, 2, 12, 22)
        painter.drawLine(2, 12, 22, 12)
        for a, b in ((8, 6), (16, 6), (8, 18), (16, 18)):
            painter.drawLine(12, 2 if b == 6 else 22, a, b)
        painter.drawLine(2, 12, 6, 8)
        painter.drawLine(2, 12, 6, 16)
        painter.drawLine(22, 12, 18, 8)
        painter.drawLine(22, 12, 18, 16)
    elif name == "duplicate":
        painter.drawRoundedRect(QRectF(7, 7, 14, 14), 1.5, 1.5)
        painter.drawLine(3, 17, 3, 3)
        painter.drawLine(3, 3, 17, 3)
    elif name == "delete":
        painter.drawRoundedRect(QRectF(6, 7, 12, 14), 1, 1)
        painter.drawLine(4, 6, 20, 6)
        painter.drawLine(9, 3, 15, 3)
        painter.drawLine(10, 10, 10, 18)
        painter.drawLine(14, 10, 14, 18)
    elif name == "fit":
        for x0, x1, y0, y1 in ((3, 8, 3, 8), (16, 21, 3, 8),
                               (3, 8, 16, 21), (16, 21, 16, 21)):
            painter.drawLine(x0, y0, x1, y0)
            painter.drawLine(x0, y0, x0, y1)
    elif name == "maximize":
        painter.drawRoundedRect(QRectF(3, 3, 18, 18), 1, 1)
        painter.drawLine(3, 8, 21, 8)
        painter.drawLine(8, 3, 8, 8)
    elif name == "gear":
        painter.drawEllipse(QRectF(7, 7, 10, 10))
        painter.drawEllipse(QRectF(10, 10, 4, 4))
        for x0, y0, x1, y1 in ((12, 2, 12, 6), (12, 18, 12, 22),
                               (2, 12, 6, 12), (18, 12, 22, 12),
                               (5, 5, 8, 8), (16, 16, 19, 19),
                               (5, 19, 8, 16), (16, 8, 19, 5)):
            painter.drawLine(x0, y0, x1, y1)
    elif name == "help":
        painter.drawEllipse(QRectF(2, 2, 20, 20))
        painter.drawArc(QRectF(8, 6, 8, 8), 0, 180 * 16)
        painter.drawLine(12, 14, 12, 16)
        painter.drawPoint(12, 19)
    painter.end()
    return QIcon(pixmap)


def brand_mark() -> QPixmap:
    """Compact copper line mark for the application header only."""
    pixmap = QPixmap(46, 46)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#9F6639"), 3.1)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(QPointF(8, 4), QPointF(8, 42))
    painter.drawLine(QPointF(13, 4), QPointF(13, 42))
    painter.drawLine(QPointF(13, 24), QPointF(35, 5))
    painter.drawLine(QPointF(17, 26), QPointF(37, 42))
    painter.end()
    return pixmap
