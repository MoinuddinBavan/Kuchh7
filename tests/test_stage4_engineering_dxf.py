"""Stage 4 DXF geometry, layers, profile and regression verification."""

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from kuchhe7.bom import generate_project_bom
from kuchhe7.engineering_dxf import (
    CNC_PROTOTYPE, DRAWING_TYPES, FRONT_ELEVATIONS, KITCHEN_LAYOUT,
    PANEL_OUTLINES, ROOM_PLAN, CncDxfProfile, eligible_panel_instances,
    export_engineering_dxf,
)
from kuchhe7.exports import export_front_elevation_dxf
from kuchhe7.models import Opening, PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.engineering_export_dialog import EngineeringExportDialog
from kuchhe7.ui.main_window import MainWindow


def _doc(project, path, kind, **kwargs):
    document = ezdxf.readfile(export_engineering_dxf(project, path, kind, **kwargs))
    assert document.header["$INSUNITS"] == 4
    assert document.units == ezdxf.units.MM
    assert not document.audit().has_errors
    return document


def test_all_five_drawings_open_with_millimetres_and_expected_layers(tmp_path):
    project = Project.complete_kitchen_demo()
    expected = {
        ROOM_PLAN: {"ROOM_WALLS", "DOORS", "WINDOWS", "DIMENSIONS"},
        KITCHEN_LAYOUT: {"ROOM_WALLS", "CABINET_FOOTPRINTS", "CABINET_LABELS"},
        FRONT_ELEVATIONS: {"ELEVATION_OUTLINES", "ELEVATION_DETAILS", "DIMENSIONS"},
        PANEL_OUTLINES: {"PANEL_OUTLINES", "PANEL_LABELS"},
        CNC_PROTOTYPE: {"CNC_PANEL_OUTLINES"},
    }
    for kind in DRAWING_TYPES:
        document = _doc(project, tmp_path / f"{kind}.dxf", kind)
        actual = {entity.dxf.layer for entity in document.modelspace()}
        assert expected[kind] <= actual


def test_room_plan_segments_openings_and_actual_dimensions(tmp_path):
    project = Project.complete_kitchen_demo()
    doc = _doc(project, tmp_path / "room.dxf", ROOM_PLAN)
    walls = list(doc.modelspace().query('LINE[layer=="ROOM_WALLS"]'))
    assert len(walls) == 6  # West wall split by the sample door and window.
    assert any(line.dxf.start.x == 0 and line.dxf.start.y == 3200
               and line.dxf.end.x == 3600 and line.dxf.end.y == 3200 for line in walls)
    assert any(line.dxf.start.x == 0 and line.dxf.start.y == 0
               and line.dxf.end.x == 3600 and line.dxf.end.y == 0 for line in walls)
    windows = list(doc.modelspace().query('LINE[layer=="WINDOWS"]'))
    assert len(windows) == 1
    assert {windows[0].dxf.start.y, windows[0].dxf.end.y} == {1700, 800}
    labels = [item.dxf.text for item in doc.modelspace().query("TEXT")]
    assert "3600 mm" in labels and "3200 mm" in labels
    assert any("D1 DOOR 900 mm" in value for value in labels)
    assert any("W1 WINDOW 900 mm" in value for value in labels)


def test_room_plan_respects_other_walls_and_outward_door_swing(tmp_path):
    project = Project.empty()
    project.room.openings = [
        Opening("D1", "door", "NORTH", 500, 800, 2100, 0, "Right Out"),
        Opening("W1", "window", "EAST", 900, 600, 900, 1000),
    ]
    doc = _doc(project, tmp_path / "other-walls.dxf", ROOM_PLAN)
    windows = list(doc.modelspace().query('LINE[layer=="WINDOWS"]'))
    assert len(windows) == 1
    assert {windows[0].dxf.start.y, windows[0].dxf.end.y} == {2300, 1700}
    leaves = list(doc.modelspace().query('LINE[layer=="DOORS"]'))
    assert len(leaves) == 1
    assert leaves[0].dxf.start.x == leaves[0].dxf.end.x == 1300
    assert leaves[0].dxf.end.y == 4000  # Outward from north wall.


def test_kitchen_footprints_match_saved_model_positions_and_sizes(tmp_path):
    project = Project.complete_kitchen_demo()
    reopened = load_project(save_project(project, tmp_path / "kitchen.json"))
    doc = _doc(reopened, tmp_path / "kitchen.dxf", KITCHEN_LAYOUT)
    footprints = list(doc.modelspace().query('LWPOLYLINE[layer=="CABINET_FOOTPRINTS"]'))
    assert len(footprints) == len(reopened.cabinets)
    for cabinet, outline in zip(reopened.cabinets, footprints):
        points = list(outline.get_points("xy"))
        x, y = points[0]
        assert (x, y) == (cabinet.position_x,
                          reopened.room.depth - cabinet.position_y - cabinet.depth)
        assert points[1][0] - x == cabinet.width
        assert points[2][1] - y == cabinet.depth
        assert outline.closed


def test_elevation_dimensions_and_legacy_dxf_remain_separate(tmp_path):
    project = Project.complete_kitchen_demo()
    doc = _doc(project, tmp_path / "engineering-elevation.dxf", FRONT_ELEVATIONS)
    outlines = list(doc.modelspace().query('LWPOLYLINE[layer=="ELEVATION_OUTLINES"]'))
    assert len(outlines) == len(project.cabinets)
    for cabinet, entity in zip(project.cabinets, outlines):
        points = list(entity.get_points("xy"))
        assert points[0] == (cabinet.position_x, cabinet.elevation_z)
        assert points[1][0] - points[0][0] == cabinet.width
        assert points[2][1] - points[1][1] == cabinet.height
    old = ezdxf.readfile(export_front_elevation_dxf(project, tmp_path / "legacy.dxf"))
    assert len(old.modelspace().query("LWPOLYLINE")) == len(project.cabinets)
    assert old.header["$INSUNITS"] == 4


def test_panel_instances_match_authoritative_bom_and_exclude_hardware(tmp_path):
    project = Project.complete_kitchen_demo()
    instances = eligible_panel_instances(project)
    expected = sum(component.quantity for component in generate_project_bom(project)
                   if component.length_mm > 0 and component.width_mm > 0 and component.thickness_mm > 0)
    assert len(instances) == expected
    doc = _doc(project, tmp_path / "panels.dxf", PANEL_OUTLINES)
    outlines = list(doc.modelspace().query('LWPOLYLINE[layer=="PANEL_OUTLINES"]'))
    assert len(outlines) == expected
    for (component, number), outline in zip(instances, outlines):
        points = list(outline.get_points("xy"))
        assert outline.closed
        assert points[1][0] - points[0][0] == pytest.approx(component.length_mm)
        assert points[2][1] - points[1][1] == pytest.approx(component.width_mm)
        assert component.thickness_mm > 0 and number <= component.quantity
    bounds = [entity.get_points("xy") for entity in outlines]
    rectangles = [(points[0][0], points[0][1], points[2][0], points[2][1]) for points in bounds]
    for index, (ax0, ay0, ax1, ay1) in enumerate(rectangles):
        for bx0, by0, bx1, by1 in rectangles[index + 1:]:
            assert not (ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0)


def test_generic_cnc_profile_custom_layers_origin_closed_entities_and_xdata(tmp_path):
    project = Project()
    profile = CncDxfProfile("CUT_DEMO", "ANNOTATIONS", 25, 40, "POLYLINE", False)
    doc = _doc(project, tmp_path / "generic-cnc.dxf", CNC_PROTOTYPE, cnc_profile=profile)
    outlines = list(doc.modelspace().query('POLYLINE[layer=="CUT_DEMO"]'))
    assert len(outlines) == len(eligible_panel_instances(project))
    assert len(doc.modelspace().query("TEXT")) == 0
    first = outlines[0]
    assert first.is_closed
    assert (first.vertices[0].dxf.location.x, first.vertices[0].dxf.location.y) == (25, 40)
    xdata = first.get_xdata("KUCHE7_DEMO")
    assert any(value == "C1" for code, value in xdata if code == 1000)
    with pytest.raises(ValueError, match="closed"):
        CncDxfProfile(geometry_type="SPLINE").validate()


def test_props_appliances_and_hardware_metadata_never_become_panels(tmp_path):
    project = Project()
    baseline = deepcopy(generate_project_bom(project))
    expected = len(eligible_panel_instances(project))
    for type_id, item_id, x, y in (("oven_freestanding", "A1", 100, 200),
                                   ("plant_pot", "P1", 100, 1000)):
        definition = get_product(type_id)
        project.add_product(PlacedProduct(item_id, type_id, x, y, definition.elevation_z,
                                          definition.width, definition.depth, definition.height))
    assert generate_project_bom(project) == baseline
    assert len(eligible_panel_instances(project)) == expected
    assert nest_project(project).eligible_count == nest_project(Project()).eligible_count
    assert calculate_quotation(project).lines[0].item_id == "C1"
    assert len(_doc(project, tmp_path / "cnc.dxf", CNC_PROTOTYPE)
               .modelspace().query('LWPOLYLINE[layer=="CNC_PANEL_OUTLINES"]')) == expected


def test_dialog_and_main_window_offer_one_engineering_export_workflow():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    dialog = EngineeringExportDialog(window)
    assert dialog.drawing_combo.count() == 5
    assert not dialog.profile_panel.isVisible()
    dialog.drawing_combo.setCurrentIndex(4)
    assert dialog.drawing_type == CNC_PROTOTYPE
    assert dialog.cnc_profile().outline_layer == "CNC_PANEL_OUTLINES"
    assert "not verified" not in dialog.warning.text().lower() or "validate" in dialog.warning.text().lower()
    assert window.engineering_export_action in window.menuBar().actions()[0].menu().actions()
    dialog.close()
    window.close()


def test_main_window_engineering_action_writes_selected_dxf(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    destination = tmp_path / "from-ui.dxf"
    monkeypatch.setattr(EngineeringExportDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(destination), ""))
    window.export_engineering_drawing()
    drawing = ezdxf.readfile(destination)
    assert drawing.header["$INSUNITS"] == 4
    assert len(drawing.modelspace().query('LINE[layer=="ROOM_WALLS"]')) == 4
    window.close()
