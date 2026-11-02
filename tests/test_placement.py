import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from copy import deepcopy

import ezdxf
from openpyxl import load_workbook
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Cabinet, Project, Room
from kuchhe7.persistence import load_project, save_project
from kuchhe7.placement import placement_error, snap_position, volumes_intersect
from kuchhe7.ui.main_window import MainWindow


def test_spatial_validation_allows_vertical_stacking_but_rejects_real_intersection():
    base = Cabinet(cabinet_id="C1", position_x=400, position_y=2600)
    wall = create_catalogue_cabinet("wall_2_door", "C2", position_x=450, position_y=2850)
    assert not volumes_intersect(base, wall)
    assert placement_error(Room(), [base], wall) is None

    lowered = deepcopy(wall)
    lowered.elevation_z = 600
    assert volumes_intersect(base, lowered)
    assert "overlaps C1 in 3D" in placement_error(Room(), [base], lowered)


def test_grid_wall_and_cabinet_edge_snapping_and_disabled_state():
    room = Room()
    fixed = Cabinet(cabinet_id="C1", position_x=600, position_y=2600)
    candidate = Cabinet(cabinet_id="C2", width=600, position_x=1493, position_y=2594)
    snapped = snap_position(candidate, room, [fixed], scale_pixels_per_mm=1.0)
    assert (snapped.x, snapped.y) == (1500, 2600)
    assert snapped.vertical_guides == (1500,)
    assert snapped.horizontal_guides == (2600,)

    candidate.position_x, candidate.position_y = 47, 1147
    grid = snap_position(candidate, room, [fixed], scale_pixels_per_mm=0.2)
    assert (grid.x, grid.y) == (0, 1100)

    raw = snap_position(candidate, room, [fixed], scale_pixels_per_mm=0.2, snap_enabled=False)
    assert (raw.x, raw.y) == (47, 1147)


def test_move_history_coordinates_persistence_and_exports(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    before_bom = generate_project_bom(window.project)
    window.move_cabinet("C1", 1800, 2200)
    application.processEvents()
    assert (window.project.cabinet.position_x, window.project.cabinet.position_y) == (1800, 2200)
    assert window._dirty

    window.undo_stack.undo()
    assert (window.project.cabinet.position_x, window.project.cabinet.position_y) == (1350, 2600)
    window.undo_stack.redo()
    assert (window.project.cabinet.position_x, window.project.cabinet.position_y) == (1800, 2200)
    assert generate_project_bom(window.project) == before_bom

    reopened = load_project(save_project(window.project, tmp_path / "moved.json"))
    assert (reopened.cabinet.position_x, reopened.cabinet.position_y) == (1800, 2200)
    sheet = load_workbook(export_bom_xlsx(reopened, tmp_path / "moved.xlsx"), data_only=True)["BOM"]
    assert sheet.max_row == len(before_bom) + 4
    drawing = ezdxf.readfile(export_front_elevation_dxf(reopened, tmp_path / "moved.dxf"))
    assert drawing.header["$INSUNITS"] == 4
    window.close()


def test_invalid_move_is_rejected_without_mutating_coordinates():
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    original = (window.project.cabinet.position_x, window.project.cabinet.position_y)
    window.move_cabinet("C1", -10, 2000)
    application.processEvents()
    assert (window.project.cabinet.position_x, window.project.cabinet.position_y) == original
    assert "negative" in window.placement_warning.text() or "outside" in window.placement_warning.text()
    assert window.undo_stack.count() == 0
    window.close()


def test_mouse_driven_drag_updates_model_and_undo_redo():
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.snap_action.setChecked(False)
    window.show()
    application.processEvents()
    view = window.plan_view
    item = view._cabinet_items["C1"]
    start = view.mapFromScene(item.sceneBoundingRect().center())
    target_scene = QPoint(
        round(view._ox + (1900 + window.project.cabinet.width / 2) * view._scale),
        round(view._oy + (2200 + window.project.cabinet.depth / 2) * view._scale),
    )
    target = view.mapFromScene(target_scene)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), target, delay=10)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    application.processEvents()
    moved = (window.project.cabinet.position_x, window.project.cabinet.position_y)
    assert abs(moved[0] - 1900) <= 10
    assert abs(moved[1] - 2200) <= 10
    window.undo_action.trigger()
    assert (window.project.cabinet.position_x, window.project.cabinet.position_y) == (1350, 2600)
    window.redo_action.trigger()
    assert (window.project.cabinet.position_x, window.project.cabinet.position_y) == moved
    window.close()


def test_mouse_catalogue_placement_preview_commit_and_escape():
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.snap_action.setChecked(False)
    window.show()
    application.processEvents()
    view = window.plan_view

    window.catalogue_category_combo.setCurrentText("Base Cabinets")
    window.catalogue_list.setCurrentRow(1)
    window.begin_catalogue_placement()
    assert view.preview_model_position(200, 1800)
    center_scene = QPoint(
        round(view._ox + (200 + 300) * view._scale),
        round(view._oy + (1800 + 300) * view._scale),
    )
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(center_scene))
    application.processEvents()
    assert len(window.project.cabinets) == 2
    placed = window.project.selected_cabinet
    assert placed.cabinet_type_id == "base_3_drawer"
    assert abs(placed.position_x - 200) <= 10
    assert abs(placed.position_y - 1800) <= 10

    window.begin_catalogue_placement()
    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert view._pending_type_id is None
    assert len(window.project.cabinets) == 2
    window.close()
