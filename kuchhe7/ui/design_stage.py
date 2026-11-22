"""Presentation-first Design Studio container for the existing 2D and 3D views.

The room editor remains the authoritative interactive plan. Its compact card
can expand over the viewer for accurate placement without creating a second
scene or changing project coordinates.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QToolButton, QWidget
from PySide6.QtGui import QColor, QPainterPath, QRegion


class DesignStage(QWidget):
    def __init__(self, model_panel: QWidget, plan_panel: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("designStage")
        self.model_panel = model_panel
        self.plan_panel = plan_panel
        self.model_panel.setParent(self)
        self.plan_panel.setParent(self)
        self.plan_panel.setObjectName("floatingPlan")
        shadow = QGraphicsDropShadowEffect(self.plan_panel)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(50, 39, 30, 43))
        self.plan_panel.setGraphicsEffect(shadow)
        self.plan_expanded = False
        self._controls_compact = False
        self._overlays: list[QWidget] = []

    def add_overlay(self, widget: QWidget) -> None:
        widget.setParent(self)
        self._overlays.append(widget)
        widget.raise_()
        self._layout_children()

    def set_plan_expanded(self, expanded: bool) -> None:
        self.plan_expanded = expanded
        self._layout_children()
        self.plan_panel.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._layout_children()

    def _layout_children(self) -> None:
        if not self.model_panel:
            return
        width, height = self.width(), self.height()
        self.model_panel.setGeometry(QRect(0, 0, width, height))
        if self.plan_expanded:
            plan_width = min(max(480, int(width * 0.66)), max(1, width - 32))
            plan_height = max(200, height - 42)
            self.plan_panel.setGeometry(20, 20, plan_width, min(plan_height, height - 24))
        else:
            # The small workspace keeps a usable plan without veiling the
            # left-hand base cabinet. Full-size editing remains one click away.
            plan_width = min(280, max(205, round(width * 0.30)))
            plan_height = min(242, max(178, round(height * 0.36)))
            self.plan_panel.setGeometry(14, max(14, height - plan_height - 18),
                                        plan_width, plan_height)
        rounded = QPainterPath()
        rounded.addRoundedRect(QRectF(self.plan_panel.rect()), 16, 16)
        self.plan_panel.setMask(QRegion(rounded.toFillPolygon().toPolygon()))
        self.model_panel.lower()
        if self.plan_panel.isVisible():
            self.plan_panel.raise_()
        if self._overlays:
            badge = self._overlays[0]
            badge.setGeometry(18, 16, badge.sizeHint().width(), 34)
            badge.raise_()
        if len(self._overlays) > 1:
            controls = self._overlays[1]
            controls.setVisible(not self.plan_expanded)
            if not self.plan_expanded:
                available = width - self.plan_panel.geometry().right() - 22
                buttons = controls.findChildren(QToolButton)
                if self._controls_compact:
                    for button in buttons:
                        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                compact = controls.sizeHint().width() > available
                if compact:
                    for button in buttons:
                        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                self._controls_compact = compact
                controls_width = controls.sizeHint().width()
                controls_height = max(48, controls.sizeHint().height())
                centered = max(12, (width - controls_width) // 2)
                clear_of_plan = self.plan_panel.geometry().right() + 10
                controls_x = min(max(centered, clear_of_plan), max(12, width - controls_width - 12))
                controls.setGeometry(controls_x, max(14, height - controls_height - 16),
                                     controls_width, controls_height)
                controls.raise_()
        if len(self._overlays) > 2:
            selection = self._overlays[2]
            card_width = min(280, max(180, width - plan_width - 54))
            selection.setGeometry(max(12, width - card_width - 18),
                                  16, card_width, 57)
            selection.raise_()
