"""Native VTK picking followed by manual cabinet rotation."""

import os
import sys

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.models import Cabinet, Project
from kuchhe7.ui.main_window import MainWindow


pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen",
    reason="Requires the native Windows Qt/VTK render window",
)


def test_click_cabinet_in_3d_then_rotate_and_undo():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=True)
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=800, depth=600,
                                position_x=1000, position_y=1000))
    project.add_cabinet(Cabinet(cabinet_id="C2", width=600, depth=600,
                                position_x=2000, position_y=1000))
    window.project = project
    window.refresh_all(reset_camera=True)
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    try:
        window.view3d.view_front()
        actor = window.view3d.plotter.renderer.actors["C1-door-0"]
        renderer = window.view3d.plotter.renderer
        renderer.SetWorldPoint(*actor.GetCenter(), 1)
        renderer.WorldToDisplay()
        x, y, _ = renderer.GetDisplayPoint()
        width, height = window.view3d.plotter.render_window.GetSize()
        widget = window.view3d.plotter.interactor
        point = QPoint(round(x * widget.width() / width),
                       round(widget.height() - 1 - y * widget.height() / height))
        assert widget.rect().contains(point)
        assert window.project.selected_cabinet_id == "C2"
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point)
        app.processEvents()
        QTest.qWait(30)
        assert window.project.selected_cabinet_id == "C1"
        assert window.rotate_tool_button.isEnabled()
        window.rotate_right_action.trigger()
        assert window.project.selected_cabinet.orientation_degrees == 90
        assert window.plan_view._selected_cabinet_id == "C1"
        window.undo_stack.undo()
        assert window.project.selected_cabinet.orientation_degrees == 0
    finally:
        window.close()
