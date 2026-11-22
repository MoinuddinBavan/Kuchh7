"""Paint the project sidebar's existing list items as compact product cards.

The delegate changes presentation only. Item IDs, selection, keyboard navigation,
and the existing QListWidget signals remain owned by the original list widget.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from ..catalogue import get_catalogue_item
from .catalogue_preview import catalogue_thumbnail


KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
NAME_ROLE = KIND_ROLE + 1
DETAIL_ROLE = KIND_ROLE + 2
PREVIEW_ROLE = KIND_ROLE + 3
EXPANDED_ROLE = KIND_ROLE + 4
TALL_ROLE = KIND_ROLE + 5


@lru_cache(maxsize=80)
def cached_cabinet_preview(type_id: str, finish: str) -> QPixmap:
    """Reuse immutable presentation thumbnails during frequent sidebar refreshes."""
    return catalogue_thumbnail(get_catalogue_item(type_id), finish)


def appliance_card_preview(definition) -> QPixmap | None:
    """Small sidebar illustrations for existing oven and hob catalogue entries."""
    if definition.shape not in ("oven", "hob"):
        return None
    pixmap = QPixmap(160, 100)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    backdrop = QLinearGradient(0, 0, 0, 100)
    backdrop.setColorAt(0, QColor("#F5EDE4"))
    backdrop.setColorAt(1, QColor("#DED0BF"))
    painter.fillRect(QRectF(0, 0, 160, 100), backdrop)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(66, 52, 39, 30))
    painter.drawEllipse(QRectF(31, 86, 102, 8))
    if definition.shape == "oven":
        steel = QLinearGradient(42, 0, 119, 0)
        steel.setColorAt(0, QColor("#34383A"))
        steel.setColorAt(0.23, QColor("#929593"))
        steel.setColorAt(0.85, QColor("#626868"))
        steel.setColorAt(1, QColor("#272C2F"))
        painter.setBrush(steel)
        painter.drawRoundedRect(QRectF(43, 7, 74, 83), 3, 3)
        painter.setBrush(QColor("#20272B"))
        painter.drawRoundedRect(QRectF(49, 32, 62, 46), 2, 2)
        glow = QLinearGradient(0, 39, 0, 75)
        glow.setColorAt(0, QColor("#332D28"))
        glow.setColorAt(0.55, QColor("#BD713A"))
        glow.setColorAt(1, QColor("#292826"))
        painter.setBrush(glow)
        painter.drawRect(QRectF(54, 37, 52, 36))
        painter.setPen(QPen(QColor("#D6B88C"), 1.3))
        painter.drawLine(57, 64, 103, 64)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#B9C0BE"))
        painter.drawRoundedRect(QRectF(54, 25, 52, 3), 1.5, 1.5)
        for x in (55, 66, 93, 104):
            painter.setBrush(QColor("#BBC2BF"))
            painter.drawEllipse(QRectF(x, 13, 5, 5))
    else:
        top = QPolygonF([QPointF(19, 33), QPointF(129, 33), QPointF(144, 74), QPointF(31, 74)])
        painter.setBrush(QColor("#252B2D"))
        painter.setPen(QPen(QColor("#8C8E88"), 2))
        painter.drawPolygon(top)
        painter.setPen(QPen(QColor("#555D5B"), 2))
        for x, y, rx, ry in ((48, 44, 15, 8), (96, 44, 15, 8),
                             (50, 59, 16, 8), (100, 59, 16, 8)):
            painter.drawEllipse(QRectF(x - rx, y - ry, rx * 2, ry * 2))
            painter.drawEllipse(QRectF(x - 5, y - 3, 10, 6))
        painter.setPen(QPen(QColor("#C8C1B4"), 1.5))
        painter.drawLine(46, 45, 100, 62)
        painter.drawLine(100, 45, 46, 62)
    painter.end()
    return pixmap


class SidebarCardDelegate(QStyledItemDelegate):
    """Draw rounded cards and headings without replacing selectable Qt items."""

    def paint(self, painter: QPainter, option, index) -> None:
        kind = index.data(KIND_ROLE)
        if kind is None:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(3, 2, -3, -2)
        if kind == "section":
            font = QFont(option.font)
            font.setPointSizeF(9.5)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#292B26"))
            painter.drawText(rect.adjusted(5, 0, -25, 0), Qt.AlignmentFlag.AlignVCenter,
                             index.data(NAME_ROLE) or "")
            if index.data(EXPANDED_ROLE) is not None:
                arrow = "⌃" if index.data(EXPANDED_ROLE) else "⌄"
                painter.drawText(rect.adjusted(rect.width() - 22, 0, 0, 0),
                                 Qt.AlignmentFlag.AlignCenter, arrow)
            painter.restore()
            return

        selected = bool(option.state & QStyle.StateFlag.State_Selected) and kind != "appliance"
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        shadow = QRectF(rect).translated(0, 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(81, 63, 43, 17))
        painter.drawRoundedRect(shadow, 9, 9)
        painter.setPen(QPen(QColor("#A76637" if selected else "#EAE4DC"),
                            1.35 if selected else 0.8))
        painter.setBrush(QColor("#FFF8EF" if selected else "#FBF7F2" if hovered else "#FFFFFF"))
        painter.drawRoundedRect(rect, 9, 9)

        image_width = 93 if kind == "cabinet" else 83
        image = QRectF(rect.left() + 6, rect.top() + 3, image_width, rect.height() - 6)
        clip = QPainterPath()
        clip.addRoundedRect(image, 6, 6)
        painter.fillPath(clip, QColor("#EDE3D8"))
        preview = index.data(PREVIEW_ROLE)
        if isinstance(preview, QPixmap) and not preview.isNull():
            if (kind == "cabinet" and not index.data(TALL_ROLE)
                    and preview.width() >= 300 and preview.height() >= 220):
                preview = preview.copy(18, 10, preview.width() - 36, preview.height() - 20)
            scaled = preview.scaled(int(image.width()), int(image.height()),
                                    Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
            painter.save()
            painter.setClipPath(clip)
            painter.drawPixmap(int(image.center().x() - scaled.width() / 2),
                               int(image.center().y() - scaled.height() / 2), scaled)
            painter.restore()

        text_x = image.right() + 8
        text_width = max(20, rect.right() - text_x - (21 if selected else 7))
        name = str(index.data(NAME_ROLE) or "")
        detail = str(index.data(DETAIL_ROLE) or "")
        name_font = QFont(option.font)
        name_font.setPointSizeF(9.5)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(QColor("#282A26"))
        name = painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(text_width))
        painter.drawText(QRectF(text_x, rect.top() + 9, text_width, 20),
                         Qt.AlignmentFlag.AlignVCenter, name)
        detail_font = QFont(option.font)
        detail_font.setPointSizeF(8.0)
        painter.setFont(detail_font)
        painter.setPen(QColor("#55584E"))
        detail = painter.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight,
                                                  int(rect.right() - text_x - 6))
        painter.drawText(QRectF(text_x, rect.top() + 31, rect.right() - text_x - 6, 17),
                         Qt.AlignmentFlag.AlignVCenter, detail)

        if selected:
            cx, cy = rect.right() - 14, rect.top() + 16
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#A76637"))
            painter.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))
            painter.setPen(QPen(QColor("#FFFFFF"), 1.8))
            painter.drawLine(int(cx - 4), int(cy), int(cx - 1), int(cy + 3))
            painter.drawLine(int(cx - 1), int(cy + 3), int(cx + 5), int(cy - 4))
        painter.restore()
