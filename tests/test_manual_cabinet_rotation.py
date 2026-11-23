"""Manual room orientation uses the existing cabinet footprint and history."""

from copy import deepcopy

import ezdxf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsLineItem

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.complete_kitchen_dxf import export_complete_kitchen_dxf
from kuchhe7.costing import cost_cabinet
from kuchhe7.cut_list import generate_cut_list
from kuchhe7.engineering_dxf import KITCHEN_LAYOUT, export_engineering_dxf
from kuchhe7.models import Cabinet, Opening, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.main_window import MainWindow


def _window(project):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=True)
    window.project = project
    window.refresh_all(reset_camera=True)
    app.processEvents()
    return window


def test_rotate_cycle_undo_redo_and_2d_3d_sync(tmp_path):
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=800, depth=600,
                                position_x=0, position_y=1000))
    window = _window(project)
    try:
        before = deepcopy(generate_project_bom(window.project))
        before_cut_list = deepcopy(generate_cut_list(window.project))
        before_nesting = nest_project(window.project)
        before_cost = cost_cabinet(window.project.selected_cabinet, window.project.price_master)
        before_quote = calculate_quotation(window.project)
        original_position = (window.project.selected_cabinet.position_x,
                             window.project.selected_cabinet.position_y)
        assert window.rotate_tool_button.isEnabled()
        assert [action.text() for action in window.rotate_tool_button.menu().actions()] == [
            "Rotate Left 90°", "Rotate Right 90°",
        ]
        for expected in (90, 180, 270, 0):
            window.rotate_right_action.trigger()
            cabinet = window.project.selected_cabinet
            assert cabinet.orientation_degrees == expected
            assert (cabinet.position_x, cabinet.position_y) == original_position
            assert window.plan_view._selected_cabinet_id == "C1"
            assert window.view3d._selected_cabinet_id == "C1"
            footprint = window.plan_view._cabinet_items["C1"].rect()
            assert footprint.width() / window.plan_view._scale == pytest.approx(cabinet.footprint_width)
            assert footprint.height() / window.plan_view._scale == pytest.approx(cabinet.footprint_depth)
            bounds = window.view3d.plotter.actors["C1-door-0"].GetBounds()
            if expected in (90, 270):
                assert bounds[1] - bounds[0] < bounds[3] - bounds[2]
            else:
                assert bounds[1] - bounds[0] > bounds[3] - bounds[2]
            scale = window.plan_view._scale
            px = window.plan_view._ox + cabinet.position_x * scale
            py = window.plan_view._oy + cabinet.position_y * scale
            front_lines = [item.line() for item in window.plan_view.scene().items()
                           if isinstance(item, QGraphicsLineItem)
                           and item.pen().color() == QColor("#50675E")]
            expected_edge = {
                0: ("y", py), 90: ("x", px + cabinet.depth * scale),
                180: ("y", py + cabinet.depth * scale), 270: ("x", px),
            }[expected]
            assert any(
                (line.x1() == pytest.approx(expected_edge[1])
                 and line.x2() == pytest.approx(expected_edge[1]))
                if expected_edge[0] == "x" else
                (line.y1() == pytest.approx(expected_edge[1])
                 and line.y2() == pytest.approx(expected_edge[1]))
                for line in front_lines
            )
        assert generate_project_bom(window.project) == before
        assert generate_cut_list(window.project) == before_cut_list
        assert nest_project(window.project) == before_nesting
        assert cost_cabinet(window.project.selected_cabinet, window.project.price_master) == before_cost
        assert calculate_quotation(window.project) == before_quote
        window.rotate_left_action.trigger()
        assert window.project.selected_cabinet.orientation_degrees == 270
        window.undo_stack.undo()
        assert window.project.selected_cabinet.orientation_degrees == 0
        window.undo_stack.redo()
        assert window.project.selected_cabinet.orientation_degrees == 270
        saved = tmp_path / "rotated.json"
        save_project(window.project, saved)
        assert load_project(saved).selected_cabinet.orientation_degrees == 270
        assert generate_project_bom(load_project(saved)) == before
    finally:
        window.close()


def test_invalid_rotation_keeps_history_and_original_footprint():
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=500, depth=900,
                                position_x=3000, position_y=1000))
    window = _window(project)
    try:
        count = window.undo_stack.count()
        window.rotate_right_action.trigger()
        assert window.project.selected_cabinet.orientation_degrees == 0
        assert window.undo_stack.count() == count
        assert "outside" in window.placement_warning.text().lower()

        other = Project.empty()
        other.add_cabinet(Cabinet(cabinet_id="C1", width=600, depth=500,
                                  position_x=1550, position_y=1000))
        other.add_cabinet(Cabinet(cabinet_id="C2", width=500, depth=800,
                                  position_x=1000, position_y=1000))
        window.project = other
        window.refresh_all(reset_camera=True)
        window.select_cabinet("C2")
        count = window.undo_stack.count()
        window.rotate_right_action.trigger()
        assert window.project.selected_cabinet.orientation_degrees == 0
        assert window.undo_stack.count() == count
        assert "overlaps C1" in window.placement_warning.text()
    finally:
        window.close()


def test_3d_selection_rotation_updates_dxf_without_changing_bom(tmp_path):
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=800, depth=600,
                                position_x=0, position_y=1000))
    window = _window(project)
    try:
        bom = deepcopy(generate_project_bom(window.project))
        window._select_cabinet_from_3d("C1")
        window.rotate_right_action.trigger()
        assert window.project.selected_cabinet.orientation_degrees == 90
        assert window.plan_view._selected_cabinet_id == "C1"
        assert generate_project_bom(window.project) == bom
        layout = ezdxf.readfile(export_engineering_dxf(
            window.project, tmp_path / "layout.dxf", KITCHEN_LAYOUT))
        footprint = next(entity for entity in layout.modelspace().query("LWPOLYLINE")
                         if entity.dxf.layer == "CABINET_FOOTPRINTS")
        points = list(footprint.get_points("xy"))
        assert points[1][0] - points[0][0] == 600
        assert points[2][1] - points[1][1] == 800
        complete = ezdxf.readfile(export_complete_kitchen_dxf(
            window.project, tmp_path / "complete.dxf"))
        assert complete.header["$INSUNITS"] == 4
        assert len(list(complete.modelspace())) > 0
    finally:
        window.close()


def test_2d_click_selection_rotates_only_the_chosen_cabinet():
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=800, depth=600,
                                position_x=300, position_y=800))
    project.add_cabinet(Cabinet(cabinet_id="C2", width=800, depth=600,
                                position_x=2000, position_y=800))
    window = _window(project)
    try:
        window.plan_view.resize(700, 500)
        window.plan_view.show()
        QApplication.processEvents()
        item = window.plan_view._cabinet_items["C1"]
        point = window.plan_view.mapFromScene(item.sceneBoundingRect().center())
        QTest.mouseClick(window.plan_view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QApplication.processEvents()
        assert window.project.selected_cabinet_id == "C1"
        window.rotate_right_action.trigger()
        assert window.project.selected_cabinet.orientation_degrees == 90
        assert next(c for c in window.project.cabinets if c.cabinet_id == "C2").orientation_degrees == 0
        window.select_room_for_inspector()
        assert not window.rotate_tool_button.isEnabled()
    finally:
        window.close()


@pytest.mark.parametrize("kind,swing", [("window", "Left In"), ("door", "Right Out")])
def test_rotation_cannot_enter_an_existing_wall_opening(kind, swing):
    project = Project.empty()
    project.add_opening(Opening("W1" if kind == "window" else "D1", kind, "EAST",
                                offset=1000, width=800, height=700 if kind == "window" else 2100,
                                elevation=300 if kind == "window" else 0, swing=swing))
    project.add_cabinet(Cabinet(cabinet_id="C1", width=500, depth=900,
                                position_x=2700, position_y=1000))
    window = _window(project)
    try:
        window.select_cabinet("C1")
        count = window.undo_stack.count()
        window.rotate_right_action.trigger()
        assert window.project.selected_cabinet.orientation_degrees == 0
        assert window.undo_stack.count() == count
        assert kind in window.placement_warning.text()
    finally:
        window.close()


@pytest.mark.parametrize("type_id", [
    "base_2_door", "base_3_drawer", "sink_base", "wall_2_door",
    "wall_open_shelf", "tall_pantry", "corner_base", "corner_wall",
])
def test_existing_cabinet_types_validate_all_room_orientations(type_id):
    project = Project.empty()
    cabinet = create_catalogue_cabinet(type_id, "C1", position_x=1000, position_y=1000)
    project.add_cabinet(cabinet)
    original = deepcopy(generate_project_bom(project))
    for angle in (90, 180, 270, 0):
        cabinet.orientation_degrees = angle
        project.validate_cabinet_placement(cabinet)
        assert generate_project_bom(project) == original
