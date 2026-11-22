"""Native Qt/VTK click coverage for the existing six-cabinet demo scene."""

import os
import sys

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.models import PlacedProduct
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.main_window import MainWindow


pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen",
    reason="Native Windows Qt/VTK render window is required for pixel picking",
)


def _window():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.load_complete_action.trigger()
    window.resize(1600, 900)
    window.show()
    app.processEvents()
    QTest.qWait(150)
    window.view3d.view_front()
    return app, window


def _actor_point(window, name: str) -> QPoint:
    view = window.view3d
    actor = view.plotter.renderer.actors[name]
    renderer = view.plotter.renderer
    renderer.SetWorldPoint(*actor.GetCenter(), 1)
    renderer.WorldToDisplay()
    x, y, _ = renderer.GetDisplayPoint()
    width, height = view.plotter.render_window.GetSize()
    assert width > 0 and height > 0
    widget = view.plotter.interactor
    point = QPoint(round(x * widget.width() / width),
                   round(widget.height() - 1 - y * widget.height() / height))
    assert widget.rect().contains(point)
    return point


def _click_actor(app, window, name: str) -> None:
    QTest.mouseClick(window.view3d.plotter.interactor, Qt.MouseButton.LeftButton,
                     pos=_actor_point(window, name))
    app.processEvents()
    QTest.qWait(25)  # QTimer defers picking until VTK finishes the release event.


def test_clicking_each_cabinet_part_synchronizes_project_plan_sidebar_and_inspector():
    app, window = _window()
    try:
        window.select_cabinet("C6")
        before = window.project.to_dict()
        dirty = window._dirty
        for cabinet_id, part in (
            ("C1", "door-0"), ("C2", "drawer-1"), ("C3", "door-0"),
            ("C4", "door-0"), ("C5", "back"), ("C6", "door-0"),
        ):
            camera = window.view3d.plotter.camera_position
            _click_actor(app, window, f"{cabinet_id}-{part}")
            assert window.project.selected_cabinet_id == cabinet_id
            assert window.plan_view._selected_cabinet_id == cabinet_id
            assert window.view3d._selected_cabinet_id == cabinet_id
            assert window.cabinet_id_label.text() == cabinet_id
            assert window.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == cabinet_id
            assert window.object_list.currentItem().data(Qt.ItemDataRole.UserRole) == cabinet_id
            current_camera = window.view3d.plotter.camera_position
            assert np.allclose(current_camera.position, camera.position)
            assert np.allclose(current_camera.focal_point, camera.focal_point)
            assert np.allclose(current_camera.viewup, camera.viewup)
            assert window._dirty == dirty
        after = window.project.to_dict()
        before["selected_cabinet_id"] = "C6"
        assert after == before
    finally:
        window.close()


def test_empty_click_drag_modes_and_rebuild_keep_cabinet_picking(tmp_path):
    app, window = _window()
    try:
        _click_actor(app, window, "C2-drawer-1")
        widget = window.view3d.plotter.interactor
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(widget.width() - 4, 4))
        app.processEvents()
        assert window.project.selected_cabinet_id == "C2"
        point = _actor_point(window, "C6-door-0")
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(widget, point + QPoint(25, 20))
        QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=point)
        app.processEvents()
        QTest.qWait(25)
        assert window.project.selected_cabinet_id == "C2"

        window._set_presentation_view(True)
        window.view3d.view_front()
        _click_actor(app, window, "C6-door-0")
        assert window.project.selected_cabinet_id == "C6"
        window.show_interior_action.setChecked(True)
        _click_actor(app, window, "C5-back")
        assert window.project.selected_cabinet_id == "C5"
        window.hide_room_walls_action.setChecked(True)
        _click_actor(app, window, "C2-drawer-1")
        assert window.project.selected_cabinet_id == "C2"
        window.view3d.view_isometric()
        _click_actor(app, window, "C6-door-0")
        assert window.project.selected_cabinet_id == "C6"
        window._set_presentation_view(False)
        window.view3d.view_front()
        _click_actor(app, window, "C2-drawer-1")
        window.width_spin.setValue(550)
        app.processEvents()
        _click_actor(app, window, "C1-door-0")
        assert window.project.selected_cabinet_id == "C1"
        path = save_project(window.project, tmp_path / "picked-demo.json")
        window.project = load_project(path)
        window.refresh_all(reset_camera=True)
        window.view3d.view_front()
        _click_actor(app, window, "C2-drawer-1")
        assert window.project.selected_cabinet_id == "C2"
        assert window.project.selected_cabinet.width == 550
    finally:
        window.close()


def test_3d_prop_selection_remains_visual_only():
    app, window = _window()
    try:
        definition = get_product("floor_plant")
        before_bom = generate_project_bom(window.project)
        before_quote = calculate_quotation(window.project)
        before_nesting = nest_project(window.project)
        window.project.add_product(PlacedProduct(
            "P1", definition.type_id, 3000, 1500, definition.elevation_z,
            definition.width, definition.depth, definition.height,
        ))
        window.refresh_visuals(reset_camera=True)
        window.view3d.view_front()
        _click_actor(app, window, "product-P1-ceramic-pot")
        assert window.selected_product_id == "P1"
        assert window.cabinet_id_label.text() == "P1"
        assert generate_project_bom(window.project) == before_bom
        assert calculate_quotation(window.project) == before_quote
        assert nest_project(window.project) == before_nesting
    finally:
        window.close()
