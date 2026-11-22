"""Focused checks for the project-authored SVG header icon renderer."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from kuchhe7.ui.top_svg_icons import _PATHS, top_icon


def test_every_top_icon_renders_at_normal_and_high_resolution():
    QApplication.instance() or QApplication([])
    assert len(_PATHS) >= 19
    for name in _PATHS:
        icon = top_icon(name)
        for size in (20, 40):
            image = icon.pixmap(QSize(size, size)).toImage()
            assert not image.isNull(), name
            assert any(image.pixelColor(x, y).alpha() > 0
                       for x in range(size) for y in range(size)), name


def test_top_icon_has_distinct_active_and_disabled_states():
    QApplication.instance() or QApplication([])
    icon = top_icon("snap", "#343B35", "#A76637")
    normal = icon.pixmap(QSize(20, 20), QIcon.Mode.Normal, QIcon.State.Off).toImage()
    active = icon.pixmap(QSize(20, 20), QIcon.Mode.Normal, QIcon.State.On).toImage()
    disabled = icon.pixmap(QSize(20, 20), QIcon.Mode.Disabled, QIcon.State.Off).toImage()
    assert normal != active
    assert normal != disabled
