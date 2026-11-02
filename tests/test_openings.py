import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from openpyxl import load_workbook
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Cabinet, Opening, Project, Room
from kuchhe7.openings import opening_furniture_conflict
from kuchhe7.persistence import load_project, save_project
from kuchhe7.ui.main_window import MainWindow


def test_door_and_window_creation_and_wall_validation():
    project = Project()
    door = project.add_opening(Opening("D1", "door", "WEST", 200, 900, 2100, 0, "Left In"))
    window = project.add_opening(Opening("W1", "window", "NORTH", 1200, 1200, 1000, 1000))
    assert [item.opening_id for item in project.room.openings] == ["D1", "W1"]
    assert door.wall_id == "WEST" and window.elevation == 1000

    with pytest.raises(ValueError, match="extends beyond wall"):
        project.validate_opening(Opening("W2", "window", "NORTH", 3300, 600, 800, 1000))


def test_overlapping_openings_are_rejected():
    project = Project()
    project.add_opening(Opening("D1", "door", "WEST", 100, 900, 2100))
    with pytest.raises(ValueError, match="overlaps opening D1"):
        project.add_opening(Opening("W1", "window", "WEST", 700, 900, 800, 1000))


def test_door_swing_and_window_volumes_detect_furniture_conflicts():
    room = Room()
    door = Opening("D1", "door", "WEST", 200, 900, 2100, 0, "Left In")
    in_swing = Cabinet(cabinet_id="C2", width=300, depth=300, position_x=300, position_y=500)
    assert "swing clearance" in opening_furniture_conflict(room, door, in_swing)

    outward = deepcopy(door)
    outward.swing = "Left Out"
    assert opening_furniture_conflict(room, outward, in_swing) is None

    window = Opening("W1", "window", "WEST", 1500, 900, 900, 1050)
    wall_unit = create_catalogue_cabinet("wall_2_door", "C3", position_x=0, position_y=1600)
    assert "window W1" in opening_furniture_conflict(room, window, wall_unit)
    base = Cabinet(cabinet_id="C4", width=500, position_x=0, position_y=1600)
    assert opening_furniture_conflict(room, window, base) is None


def test_legacy_json_gets_rectangular_walls_without_openings(tmp_path):
    legacy = {
        "schema_version": 4,
        "name": "v0.5 room",
        "project_type": "Kitchen",
        "room": {"width": 3600, "depth": 3200},
        "cabinets": [Cabinet(position_x=1350, position_y=2600).__dict__],
        "selected_cabinet_id": "C1",
    }
    path = tmp_path / "legacy-v05.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    project = load_project(path)
    assert [wall.wall_id for wall in project.room.walls] == ["NORTH", "EAST", "SOUTH", "WEST"]
    assert project.room.openings == []
    assert project.room.height == 2600


def test_openings_round_trip_without_changing_bom_or_exports(tmp_path):
    project = Project.sample_kitchen()
    before_bom = generate_project_bom(project)
    reopened = load_project(save_project(project, tmp_path / "room-openings.json"))
    assert reopened == project
    assert [item.opening_id for item in reopened.room.openings] == ["D1", "W1"]
    assert generate_project_bom(reopened) == before_bom

    sheet = load_workbook(export_bom_xlsx(reopened, tmp_path / "room-openings.xlsx"), data_only=True)["BOM"]
    assert sheet.max_row == len(before_bom) + 4
    drawing = ezdxf.readfile(export_front_elevation_dxf(reopened, tmp_path / "room-openings.dxf"))
    assert len(list(drawing.modelspace().query("LWPOLYLINE"))) == 3
    assert drawing.header["$INSUNITS"] == 4


def test_opening_edit_remove_and_undo_redo():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    window.select_opening("D1")
    window.opening_width_spin.setValue(850)
    application.processEvents()
    assert window.project.selected_opening.width == 850
    window.undo_action.trigger()
    assert window.project.selected_opening.width == 900
    window.redo_action.trigger()
    assert window.project.selected_opening.width == 850

    window.remove_selected_opening()
    assert not any(item.opening_id == "D1" for item in window.project.room.openings)
    window.undo_action.trigger()
    assert any(item.opening_id == "D1" for item in window.project.room.openings)
    window.close()


def test_mouse_based_door_placement_and_repositioning():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    application.processEvents()
    view = window.plan_view

    window.select_wall("WEST")
    window.begin_opening_placement("door")
    click_scene = QPoint(round(view._ox), round(view._oy + 650 * view._scale))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(click_scene))
    application.processEvents()
    assert len(window.project.room.openings) == 1
    assert window.project.room.openings[0].offset == pytest.approx(200, abs=10)
    window.undo_action.trigger()
    assert window.project.room.openings == []
    window.redo_action.trigger()
    assert len(window.project.room.openings) == 1

    door_item = view._opening_items["D1"]
    start = view.mapFromScene(door_item.sceneBoundingRect().center())
    target_scene = QPoint(round(view._ox), round(view._oy + 450 * view._scale))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), view.mapFromScene(target_scene), delay=10)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(target_scene))
    application.processEvents()
    assert window.project.room.openings[0].offset != 200
    moved_offset = window.project.room.openings[0].offset
    window.undo_action.trigger()
    assert window.project.room.openings[0].offset == pytest.approx(200, abs=10)
    window.redo_action.trigger()
    assert window.project.room.openings[0].offset == moved_offset
    window.close()


def test_presentation_room_uses_segmented_walls_and_opening_geometry():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    window.presentation_view_action.setChecked(True)
    application.processEvents()
    actor_names = set(window.view3d.plotter.actors)
    assert "presentation-back-wall" in actor_names
    assert "presentation-side-wall" in actor_names
    assert any(name.startswith("presentation-opening-D1-frame") for name in actor_names)
    assert "presentation-opening-W1-glass" in actor_names
    assert any(name.startswith("presentation-side-wall-") for name in actor_names)
    window.close()
