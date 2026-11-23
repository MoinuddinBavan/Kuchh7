"""Project-authored SVG icons for the compact Design Studio header only.

The paths live in Python source, so PyInstaller bundles them with this module.
QtSvg renders them at the requested device resolution instead of stretching a
fixed 24 px bitmap. All icons use the same 24 px grid and 1.8 px round stroke.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QMenu, QToolButton


_PATHS: dict[str, str] = {
    "select": '<path d="M4 3v17l4.7-4.6 3.3 5.9 2.5-1.4-3.3-5.8H18Z"/>',
    "place": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    "move": '<path d="M12 2v20M2 12h20M9 5l3-3 3 3M9 19l3 3 3-3M5 9l-3 3 3 3M19 9l3 3-3 3"/>',
    "rotate_left": '<path d="M4 8V3m0 5h5M4.8 8A8.5 8.5 0 1 1 3.5 13"/><path d="m11 8-3 4 3 4"/>',
    "rotate_right": '<path d="M20 8V3m0 5h-5M19.2 8A8.5 8.5 0 1 0 20.5 13"/><path d="m13 8 3 4-3 4"/>',
    "duplicate": '<rect x="8" y="8" width="13" height="13" rx="1.5"/><path d="M16 8V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h4"/>',
    "delete": '<path d="M4 7h16M9 4h6M6 7l1 14h10l1-14M10 10v8M14 10v8"/>',
    "front": '<path d="M3 4h18v16H3zM12 4v16M6 17h3M15 17h3"/>',
    "isometric": '<path d="m12 2 9 5-9 5-9-5 9-5ZM3 7v10l9 5 9-5V7M12 12v10"/>',
    "fit": '<path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5"/>',
    "snap": '<path d="M5 3v10a7 7 0 0 0 14 0V3M5 8h4M15 8h4M5 3h4M15 3h4"/>',
    "grid": '<rect x="3" y="3" width="18" height="18" rx="1"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>',
    "interior": '<path d="M4 3h16v18H4zM4 10h16M4 16h16M8 6h8"/>',
    "reset": '<path d="M20 11a8 8 0 1 1-2.5-5.8M20 3v6h-6"/>',
    "maximize": '<path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5M3 3l5 5M21 3l-5 5M3 21l5-5M21 21l-5-5"/>',
    "undo": '<path d="M9 6 4 11l5 5M4 11h10a6 6 0 0 1 0 12"/>',
    "redo": '<path d="m15 6 5 5-5 5M20 11H10a6 6 0 0 0 0 12"/>',
    "save": '<path d="M4 3h14l3 3v15H3V3h1ZM7 3v7h10V3M7 21v-7h10v7"/>',
    "export": '<path d="M12 3v12M8 7l4-4 4 4M4 14v6h16v-6"/>',
    "chevron_down": '<path d="m5 9 7 7 7-7"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "saved": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "unsaved": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 17h.01"/>',
    "plan": '<rect x="3" y="3" width="18" height="18" rx="1"/><path d="M12 3v18M3 12h18"/>',
    "presentation": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1"/><path d="m3 17 6-5 4 3 4-5 4 5"/>',
}


def _svg(name: str, colour: str) -> bytes:
    if name not in _PATHS:
        raise ValueError(f"Unknown top icon: {name}")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" stroke="'
        + colour
        + '" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round">'
        + _PATHS[name]
        + '</svg>'
    ).encode("utf-8")


class _VectorIconEngine(QIconEngine):
    def __init__(self, name: str, colour: str, active_colour: str) -> None:
        super().__init__()
        self.name = name
        self.colour = colour
        self.active_colour = active_colour
        self._renderers: dict[str, QSvgRenderer] = {}

    def clone(self) -> _VectorIconEngine:
        return _VectorIconEngine(self.name, self.colour, self.active_colour)

    def _renderer(self, colour: str) -> QSvgRenderer:
        if colour not in self._renderers:
            renderer = QSvgRenderer(QByteArray(_svg(self.name, colour)))
            if not renderer.isValid():
                raise ValueError(f"Invalid SVG for top icon: {self.name}")
            self._renderers[colour] = renderer
        return self._renderers[colour]

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        colour = "#A6AAA5" if mode == QIcon.Mode.Disabled else (
            self.active_colour if state == QIcon.State.On else self.colour
        )
        self._renderer(colour).render(painter, rect)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        result = QPixmap(size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return result


def top_icon(name: str, colour: str = "#343B35", active_colour: str = "#A76637") -> QIcon:
    """Return a crisp SVG icon, including selected and disabled appearances."""
    return QIcon(_VectorIconEngine(name, colour, active_colour))


def top_label_pixmap(name: str, colour: str, logical_size: int = 19) -> QPixmap:
    """Render QLabel-only status symbols at 3× for high-DPI displays."""
    image = top_icon(name, colour).pixmap(QSize(logical_size * 3, logical_size * 3))
    image.setDevicePixelRatio(3)
    return image


class AnchoredExportMenu(QMenu):
    """Keep the dropdown beside Export rather than beyond the app's right edge."""

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        button = self.parentWidget()
        if button is None:
            return
        screen = self.screen().availableGeometry()
        target = button.mapToGlobal(QPoint(button.width() - self.width(), button.height()))
        x = max(screen.left(), min(target.x(), screen.right() - self.width() + 1))
        y = target.y()
        if y + self.height() > screen.bottom() + 1:
            y = button.mapToGlobal(QPoint(0, 0)).y() - self.height()
        y = max(screen.top(), min(y, screen.bottom() - self.height() + 1))
        self.move(x, y)


class PremiumExportButton(QToolButton):
    """One-click export dropdown with its icon, label and chevron in one face."""

    def __init__(self) -> None:
        super().__init__()
        self.setText("Export")
        self.setFixedSize(116, 42)
        self.setMouseTracking(True)
        self._export_icon = top_icon("export", "#FFFFFF", "#FFFFFF")
        self._chevron_icon = top_icon("chevron_down", "#FFFFFF", "#FFFFFF")

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = "#7F4B29" if self.isDown() else "#95582D" if self.underMouse() else "#A76637"
        painter.setBrush(QColor(background))
        painter.setPen(QPen(QColor("#95592D"), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 13, 13)
        self._export_icon.paint(painter, QRect(12, 11, 19, 19))
        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRect(39, 0, 54, self.height()), Qt.AlignmentFlag.AlignVCenter, "Export")
        self._chevron_icon.paint(painter, QRect(97, 15, 12, 12))
        painter.end()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().leaveEvent(event)
        self.update()
