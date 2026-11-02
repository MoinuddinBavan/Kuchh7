import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
from openpyxl import load_workbook
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import MAX_CABINETS, Project
from kuchhe7.openings import opening_furniture_conflict
from kuchhe7.persistence import load_project, save_project
from kuchhe7.presentation import connected_base_runs
from kuchhe7.ui.cad_views import FINISH_COLOURS, FINISH_SURFACES
from kuchhe7.ui.main_window import MainWindow


def test_complete_kitchen_has_six_coordinated_units_and_openings():
    project = Project.complete_kitchen_demo()
    assert MAX_CABINETS == 10
    assert [cabinet.cabinet_id for cabinet in project.cabinets] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert [cabinet.cabinet_type_id for cabinet in project.cabinets] == [
        "base_2_door", "base_3_drawer", "sink_base", "wall_2_door", "wall_open_shelf", "tall_pantry"
    ]
    assert [cabinet.width for cabinet in project.cabinets] == [800, 600, 800, 800, 600, 600]
    assert [cabinet.material for cabinet in project.cabinets] == [
        "Cashmere", "Warm White", "Cashmere", "Warm White", "Walnut", "Walnut"
    ]
    assert (project.room.width, project.room.depth, project.room.height) == (3600, 3200, 2600)
    assert [(opening.opening_id, opening.kind) for opening in project.room.openings] == [
        ("D1", "door"), ("W1", "window")
    ]
    assert all(
        opening_furniture_conflict(project.room, opening, cabinet) is None
        for opening in project.room.openings
        for cabinet in project.cabinets
    )
    project.validate()


def test_premium_render_finishes_are_distinct_without_changing_material_names():
    project = Project.complete_kitchen_demo()
    assert {cabinet.material for cabinet in project.cabinets} == {"Cashmere", "Warm White", "Walnut"}
    rendered = {name: FINISH_COLOURS[name] for name in ("Cashmere", "Warm White", "Walnut")}
    assert len(set(rendered.values())) == 3
    assert all(name in FINISH_SURFACES for name in rendered)


def test_connected_base_run_and_real_gap_splitting():
    project = Project.complete_kitchen_demo()
    runs = connected_base_runs(project.cabinets)
    assert [(run.cabinet_ids, run.x0, run.x1, run.top_z) for run in runs] == [
        (("C1", "C2", "C3"), 250, 2450, 720)
    ]

    project.select_cabinet("C2").width = 500
    project.validate()
    assert [run.cabinet_ids for run in connected_base_runs(project.cabinets)] == [
        ("C1", "C2"), ("C3",)
    ]


def test_complete_kitchen_save_reopen_bom_xlsx_and_dxf(tmp_path):
    project = Project.complete_kitchen_demo()
    reopened = load_project(save_project(project, tmp_path / "complete-kitchen.json"))
    assert reopened == project

    components = generate_project_bom(reopened)
    assert len(components) == 48
    assert {item.cabinet_id for item in components} == {"C1", "C2", "C3", "C4", "C5", "C6"}

    sheet = load_workbook(
        export_bom_xlsx(reopened, tmp_path / "complete-kitchen.xlsx"), data_only=True
    )["BOM"]
    assert {sheet.cell(row, 7).value for row in range(5, sheet.max_row + 1)} == {
        "C1", "C2", "C3", "C4", "C5", "C6"
    }

    document = ezdxf.readfile(export_front_elevation_dxf(reopened, tmp_path / "complete-kitchen.dxf"))
    outlines = list(document.modelspace().query("LWPOLYLINE"))
    all_x = [point[0] for outline in outlines for point in outline.get_points()]
    assert document.header["$INSUNITS"] == 4
    assert len(outlines) == 6
    assert min(all_x) == 0
    assert max(all_x) == 3100


def test_complete_demo_ui_renders_six_and_connected_presentation_geometry():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    application.processEvents()
    assert [cabinet.cabinet_id for cabinet in window.project.cabinets] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert all(any(name.startswith(f"C{number}-") for name in window.view3d.plotter.actors) for number in range(1, 7))
    assert window.project_tree.topLevelItem(0).child(1).childCount() == 6

    before = deepcopy(window.project.to_dict())
    window.presentation_view_action.setChecked(True)
    application.processEvents()
    names = set(window.view3d.plotter.actors)
    assert "presentation-countertop-C1" in names
    assert "presentation-plinth-C1" in names
    assert "presentation-sink-C3" in names
    assert not any(name.startswith("presentation-countertop-C2") for name in names)
    countertop_actors = [
        actor for name, actor in window.view3d.plotter.actors.items()
        if name == "presentation-countertop-C1" or name.startswith("presentation-countertop-C1-")
    ]
    countertop_bounds = [actor.mapper.dataset.bounds for actor in countertop_actors]
    assert min(bounds[0] for bounds in countertop_bounds) == -8
    assert max(bounds[1] for bounds in countertop_bounds) == 2208
    assert all(bounds[5] - bounds[4] == 32 for bounds in countertop_bounds)
    basin_bounds = window.view3d.plotter.actors["presentation-sink-C3"].mapper.dataset.bounds
    assert basin_bounds[4] < min(bounds[4] for bounds in countertop_bounds)
    assert window.project.to_dict() == before
    window.close()


def test_selected_unit_edit_is_isolated_and_updates_presentation_run():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    before = {cabinet.cabinet_id: deepcopy(cabinet) for cabinet in window.project.cabinets}
    window.select_cabinet("C2")
    window.width_spin.setValue(500)
    application.processEvents()
    assert window.project.selected_cabinet_id == "C2"
    assert window.project.selected_cabinet.width == 500
    assert all(window.project.select_cabinet(cabinet_id) == original for cabinet_id, original in before.items() if cabinet_id != "C2")

    window.select_cabinet("C2")
    window.presentation_view_action.setChecked(True)
    application.processEvents()
    names = set(window.view3d.plotter.actors)
    assert "presentation-countertop-C1" in names
    assert "presentation-countertop-C3" in names
    window.close()


def test_property_panel_follows_furniture_and_opening_selection():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window.show()
    application.processEvents()

    window.select_opening("D1")
    application.processEvents()
    assert window.opening_group.isVisibleTo(window.properties_dock)
    assert not window.cabinet_group.isVisibleTo(window.properties_dock)

    window.select_cabinet("C2")
    application.processEvents()
    assert not window.opening_group.isVisibleTo(window.properties_dock)
    assert window.cabinet_group.isVisibleTo(window.properties_dock)
    assert window.cabinet_id_label.text() == "C2"
    window.close()


def test_maximize_3d_restores_split_workspace_and_docks():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window.show()
    application.processEvents()
    before = deepcopy(window.project.to_dict())
    original_sizes = window.workspace_splitter.sizes()
    assert window.plan_panel.isVisible()

    window.maximize_3d_action.setChecked(True)
    application.processEvents()
    assert not window.plan_panel.isVisible()
    assert not window.explorer_dock.isVisible()
    assert not window.properties_dock.isVisible()
    assert not window.bom_dock.isVisible()
    assert window.maximize_3d_action.text() == "Restore Workspace"

    window.maximize_3d_action.setChecked(False)
    application.processEvents()
    assert window.plan_panel.isVisible()
    assert window.explorer_dock.isVisible()
    assert window.properties_dock.isVisible()
    assert window.bom_dock.isVisible()
    restored_sizes = window.workspace_splitter.sizes()
    assert abs(restored_sizes[0] - original_sizes[0]) <= 2
    assert abs(restored_sizes[1] - original_sizes[1]) <= 2
    assert window.project.to_dict() == before
    window.close()


def test_overlapping_plan_footprint_prioritizes_wall_unit():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window.show()
    application.processEvents()
    wall_unit = next(cabinet for cabinet in window.project.cabinets if cabinet.cabinet_id == "C4")
    overlap_scene_point = window.plan_view._wall_local_to_scene(
        "NORTH",
        wall_unit.position_x + wall_unit.width / 2,
        wall_unit.position_y + wall_unit.depth / 2,
    )
    QTest.mouseClick(
        window.plan_view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=window.plan_view.mapFromScene(overlap_scene_point),
    )
    application.processEvents()
    assert window.project.selected_cabinet_id == "C4"
    assert window.cabinet_id_label.text() == "C4"
    window.close()
