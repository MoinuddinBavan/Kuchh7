"""Stage 7.1: one self-contained, demonstration-only kitchen drawing."""

from __future__ import annotations

import os
from collections import Counter
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from kuchhe7.bom import generate_project_bom
from kuchhe7.complete_kitchen_dxf import (
    associate_cabinets_to_walls, export_complete_kitchen_dxf,
)
from kuchhe7.models import Cabinet, PlacedProduct, Project
from kuchhe7.nesting import expand_panel_instances
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import get_product
from kuchhe7.ui.main_window import MainWindow


def _drawing(project: Project, tmp_path):
    path = export_complete_kitchen_dxf(project, tmp_path / "KUCHE7_COMPLETE_KITCHEN.dxf")
    document = ezdxf.readfile(path)
    assert document.header["$INSUNITS"] == 4
    assert document.units == ezdxf.units.MM
    assert not document.audit().has_errors
    return document


def _layer(document, name: str):
    return [item for item in document.modelspace() if item.dxf.layer == name]


def test_single_dxf_contains_plan_four_walls_and_named_sections(tmp_path):
    project = Project.complete_kitchen_demo()
    document = _drawing(project, tmp_path)
    assert len(_layer(document, "ROOM_WALLS")) == 6
    assert len(_layer(document, "CABINET_FOOTPRINTS")) == 6
    assert len(_layer(document, "WALL_ELEVATIONS")) == len(project.room.walls) == 4
    assert len(_layer(document, "WALL_OPENINGS")) == 2
    assert len(_layer(document, "WALL_CABINETS")) == 6
    assert len(_layer(document, "WALL_FRONT_DETAILS")) == 6
    titles = [item.dxf.text for item in _layer(document, "SECTION_TITLES") if item.dxftype() == "TEXT"]
    for section in ("A - COMPLETE KITCHEN PLAN", "B - WALL-WISE FRONT ELEVATIONS",
                    "C - CABINET MANUFACTURING REFERENCES", "D - COMPLETE KITCHEN BOM",
                    "E - WALL-WISE MATERIAL SCHEDULES", "F/G - PANEL CUTTING CONTOURS"):
        assert any(text.startswith(section) for text in titles)
    wall_titles = [item.dxf.text for item in _layer(document, "WALL_TITLES")
                   if " - " in item.dxf.text]
    assert {f"WALL {wall.wall_id}" for wall in project.room.walls} == {
        text.split(" - ")[0] for text in wall_titles}


def test_sample_wall_association_and_bom_tables_reconcile(tmp_path):
    project = Project.complete_kitchen_demo()
    assignments = associate_cabinets_to_walls(project)
    assert {item.wall_id for item in assignments.values()} == {"SOUTH"}
    document = _drawing(project, tmp_path)
    bom = generate_project_bom(project)
    part_ids = [item.dxf.text for item in _layer(document, "BOM_ROWS")
                if item.dxftype() == "TEXT" and "-P" in item.dxf.text]
    counts = Counter(part_ids)
    assert len(bom) == len(counts) == 48
    assert set(counts.values()) == {2}  # One complete row, one wall-wise row.
    all_rows = [item for item in _layer(document, "BOM_ROWS") if item.dxftype() == "TEXT"]
    assert len(all_rows) == 2 * len(bom) * 13
    totals = [item.dxf.text for item in _layer(document, "BOM_TOTALS")]
    assert any("66 panels" in text and "19 hardware units" in text for text in totals)
    assert any("0 panels" in text for text in totals)  # Empty walls remain visible.


def test_panel_contours_are_unique_closed_traceable_and_nonoverlapping(tmp_path):
    project = Project.complete_kitchen_demo()
    document = _drawing(project, tmp_path)
    contours = _layer(document, "CNC_CUT_OUTER")
    assert len(contours) == len(expand_panel_instances(generate_project_bom(project))) == 66
    assert all(item.dxftype() == "LWPOLYLINE" and item.closed for item in contours)
    assert not any(item.dxftype() == "TEXT" for item in contours)
    identifiers = []
    rectangles = []
    for entity in contours:
        metadata = entity.get_xdata("KUCHE7_MASTER")
        strings = [value for code, value in metadata if code == 1000]
        identifiers.append(strings[0])
        assert "CABINET=" in strings[1] and "WALL=" in strings[2]
        points = list(entity.get_points("xy"))
        assert len(points) == 4
        assert points[1][0] > points[0][0] and points[2][1] > points[1][1]
        rectangles.append((points[0][0], points[0][1], points[2][0], points[2][1]))
    expected_panels = expand_panel_instances(generate_project_bom(project))
    for entity, expected in zip(contours, expected_panels):
        points = list(entity.get_points("xy"))
        assert points[1][0] - points[0][0] == pytest.approx(expected.length_mm)
        assert points[2][1] - points[1][1] == pytest.approx(expected.width_mm)
        metadata = [value for code, value in entity.get_xdata("KUCHE7_MASTER") if code == 1000]
        assert f"CABINET={expected.cabinet_id}" in metadata
        assert f"COMPONENT={expected.component_name}" in metadata
    assert len(set(identifiers)) == len(identifiers)
    for index, (ax0, ay0, ax1, ay1) in enumerate(rectangles):
        for bx0, by0, bx1, by1 in rectangles[index + 1:]:
            assert not (ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0)
    for empty_layer in ("CNC_CUT_INNER", "CNC_DRILL", "CNC_POCKET", "CNC_ROUTE"):
        assert not _layer(document, empty_layer)


def test_rotated_cabinet_uses_one_wall_and_preserves_footprint(tmp_path):
    project = Project.empty()
    cabinet = Cabinet(cabinet_id="C1", width=800, depth=600, position_x=0,
                      position_y=1000, orientation_degrees=90)
    project.add_cabinet(cabinet)
    assert associate_cabinets_to_walls(project)["C1"].wall_id == "WEST"
    document = _drawing(project, tmp_path)
    footprint = _layer(document, "CABINET_FOOTPRINTS")[0]
    points = list(footprint.get_points("xy"))
    assert points[1][0] - points[0][0] == 600
    assert points[2][1] - points[1][1] == 800
    assert len(_layer(document, "WALL_CABINETS")) == 1
    wall_cabinet = _layer(document, "WALL_CABINETS")[0]
    wall_points = list(wall_cabinet.get_points("xy"))
    assert wall_points[1][0] - wall_points[0][0] == 800
    assert len(_layer(document, "CNC_CUT_OUTER")) == len(expand_panel_instances(generate_project_bom(project)))


def test_two_wall_layout_has_one_wall_schedule_per_part(tmp_path):
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=800, position_x=600, position_y=2600))
    project.add_cabinet(Cabinet(cabinet_id="C2", width=700, depth=500, position_x=0,
                                position_y=1200, orientation_degrees=90))
    assignments = associate_cabinets_to_walls(project)
    assert {key: value.wall_id for key, value in assignments.items()} == {"C1": "SOUTH", "C2": "WEST"}
    document = _drawing(project, tmp_path)
    part_ids = [item.dxf.text for item in _layer(document, "BOM_ROWS") if "-P" in item.dxf.text]
    assert len(set(part_ids)) == len(generate_project_bom(project))
    assert set(Counter(part_ids).values()) == {2}
    titles = [item.dxf.text for item in _layer(document, "BOM_TITLES")]
    assert any(text.startswith("WALL SOUTH") for text in titles)
    assert any(text.startswith("WALL WEST") for text in titles)


@pytest.mark.parametrize(
    ("orientation", "x", "y", "wall"),
    [(0, 600, 2600, "SOUTH"), (90, 0, 1000, "WEST"),
     (180, 600, 0, "NORTH"), (270, 3000, 1000, "EAST")],
)
def test_all_four_rotations_associate_with_their_back_wall(orientation, x, y, wall):
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=800, depth=600,
                                position_x=x, position_y=y,
                                orientation_degrees=orientation))
    assert associate_cabinets_to_walls(project)["C1"].wall_id == wall


def test_corner_tie_is_reported_and_still_assigned_once(tmp_path):
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", position_x=0, position_y=0,
                                orientation_degrees=180))
    assignment = associate_cabinets_to_walls(project)["C1"]
    assert assignment.wall_id == "NORTH" and "AMBIGUOUS" in assignment.note
    document = _drawing(project, tmp_path)
    assert len(_layer(document, "WALL_CABINETS")) == 1


def test_distant_cabinet_is_reported_unassigned_not_counted_twice(tmp_path):
    project = Project.empty()
    project.add_cabinet(Cabinet(cabinet_id="C1", width=500, depth=400,
                                position_x=1500, position_y=1200))
    assignment = associate_cabinets_to_walls(project)["C1"]
    assert assignment.wall_id is None and "UNASSIGNED" in assignment.note
    document = _drawing(project, tmp_path)
    assert any("UNASSIGNED CABINETS" in item.dxf.text for item in _layer(document, "BOM_TITLES"))
    ids = [item.dxf.text for item in _layer(document, "BOM_ROWS") if "-P" in item.dxf.text]
    assert set(Counter(ids).values()) == {2}


def test_save_reopen_and_visual_prop_do_not_change_manufacturing_drawing(tmp_path):
    project = Project.complete_kitchen_demo()
    baseline = _drawing(project, tmp_path)
    definition = get_product("plant_pot")
    project.add_product(PlacedProduct("P1", "plant_pot", 2200, 1000,
                                      definition.elevation_z, definition.width,
                                      definition.depth, definition.height))
    reopened = load_project(save_project(project, tmp_path / "kitchen.json"))
    assert reopened.placed_products[0].item_id == "P1"
    after = _drawing(reopened, tmp_path)
    for layer in ("CABINET_FOOTPRINTS", "WALL_CABINETS", "BOM_ROWS", "CNC_CUT_OUTER"):
        assert len(_layer(after, layer)) == len(_layer(baseline, layer))
    assert [item.dxf.text for item in after.modelspace() if item.dxftype() == "TEXT"] == [
        item.dxf.text for item in baseline.modelspace() if item.dxftype() == "TEXT"]


def test_export_does_not_mutate_project_or_create_fake_dwg(tmp_path):
    project = Project.complete_kitchen_demo()
    before = deepcopy(project.to_dict())
    _drawing(project, tmp_path)
    assert project.to_dict() == before
    with pytest.raises(ValueError, match=".dxf"):
        export_complete_kitchen_dxf(project, tmp_path / "KUCHE7_COMPLETE_KITCHEN.dwg")
    assert not (tmp_path / "KUCHE7_COMPLETE_KITCHEN.dwg").exists()


def test_cabinet_dimension_change_updates_master_plan_bom_and_panel(tmp_path):
    project = Project.complete_kitchen_demo()
    edited = project.select_cabinet("C2")
    edited.width = 550
    edited.depth = 550
    document = _drawing(project, tmp_path)
    footprint = _layer(document, "CABINET_FOOTPRINTS")[1]
    points = list(footprint.get_points("xy"))
    assert points[1][0] - points[0][0] == 550
    assert points[2][1] - points[1][1] == 550
    assert any(item.dxf.text == "514" for item in _layer(document, "BOM_ROWS")
               if item.dxftype() == "TEXT")
    top_panel = next(item for item in _layer(document, "CNC_CUT_OUTER")
                     if {"CABINET=C2", "COMPONENT=Top panel"} <= {
                         value for code, value in item.get_xdata("KUCHE7_MASTER") if code == 1000})
    panel_points = list(top_panel.get_points("xy"))
    assert panel_points[1][0] - panel_points[0][0] == 514
    assert panel_points[2][1] - panel_points[1][1] == 550


def test_ui_exposes_one_file_export_without_removing_older_actions(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.complete_kitchen_export_action in window.menuBar().actions()[0].menu().actions()
    assert window.engineering_export_action in window.menuBar().actions()[0].menu().actions()
    path = tmp_path / "KUCHE7_COMPLETE_KITCHEN.dxf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    window.project = Project.complete_kitchen_demo()
    window.complete_kitchen_export_action.trigger()
    assert path.is_file() and ezdxf.readfile(path).header["$INSUNITS"] == 4
    window.close()
