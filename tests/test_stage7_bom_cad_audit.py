"""Synthetic Stage 7 regression checks; no client-approved construction claims."""

from __future__ import annotations

import json
from copy import deepcopy

import ezdxf
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.ui.manufacturing_preview import engineering_components
from kuchhe7.engineering_dxf import CNC_PROTOTYPE, KITCHEN_LAYOUT, PANEL_OUTLINES, eligible_panel_instances, export_engineering_dxf
from kuchhe7.models import Cabinet, PlacedProduct, Project
from kuchhe7.nesting import expand_panel_instances, nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation
from scripts.validate_stage7_bom_cad import REFERENCE, compare_synthetic_bom, run, verify_dxf_geometry


def _part(project: Project, cabinet_id: str, name: str):
    return next(row for row in generate_project_bom(project)
                if row.cabinet_id == cabinet_id and row.name == name)


def test_six_cabinet_static_synthetic_reference_matches_all_components():
    project = Project.complete_kitchen_demo()
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    rows, mismatches = compare_synthetic_bom(project, reference)
    assert reference["reference_status"] == "synthetic"
    assert len(rows) == len(generate_project_bom(project)) == 48
    assert {row["cabinet_id"] for row in rows} == {f"C{i}" for i in range(1, 7)}
    assert not mismatches


def test_dimension_finish_and_position_recalculation_is_isolated():
    project = Project.complete_kitchen_demo()
    before = deepcopy(generate_project_bom(project))
    c2 = project.select_cabinet("C2")
    c2.width = 550
    assert _part(project, "C2", "Top panel").length_mm == 514
    assert _part(project, "C2", "Drawer front").width_mm == 546
    c2.depth = 550
    assert _part(project, "C2", "Left side panel").width_mm == 550
    assert _part(project, "C2", "Drawer box side").length_mm == 480
    c2.height = 700
    assert _part(project, "C2", "Left side panel").length_mm == 700
    assert _part(project, "C2", "Back panel").length_mm == 664
    assert engineering_components(c2) == [row for row in generate_project_bom(project)
                                          if row.cabinet_id == "C2"]
    c2.material = "Graphite"
    assert _part(project, "C2", "Top panel").material == "Graphite"
    assert [row for row in generate_project_bom(project) if row.cabinet_id != "C2"] == [
        row for row in before if row.cabinet_id != "C2"]
    after_design_change = deepcopy(generate_project_bom(project))
    c2.position_x += 50
    assert generate_project_bom(project) == after_design_change


def test_cabinet_edit_reaches_bom_nesting_and_cad(tmp_path):
    project = Project.complete_kitchen_demo()
    cabinet = project.select_cabinet("C2")
    cabinet.width = 550
    cabinet.depth = 550
    assert _part(project, "C2", "Top panel").length_mm == 514
    assert any(part.cabinet_id == "C2" and part.component_name == "Top panel"
               and part.length_mm == 514 for part in expand_panel_instances(generate_project_bom(project)))
    doc = ezdxf.readfile(export_engineering_dxf(project, tmp_path / "edited.dxf", KITCHEN_LAYOUT))
    footprints = list(doc.modelspace().query('LWPOLYLINE[layer=="CABINET_FOOTPRINTS"]'))
    points = list(footprints[1].get_points("xy"))
    assert points[0] == (cabinet.position_x, project.room.depth - cabinet.position_y - cabinet.depth)
    assert points[1][0] - points[0][0] == 550
    assert points[2][1] - points[1][1] == 550


def test_supported_construction_options_regenerate_demo_components():
    project = Project.complete_kitchen_demo()
    cabinet = project.select_cabinet("C1")
    cabinet.board_thickness = 20
    cabinet.shelf_count = 2
    cabinet.door_count = 1
    assert _part(project, "C1", "Top panel").length_mm == 760
    assert _part(project, "C1", "Shelf").quantity == 2
    assert _part(project, "C1", "Door").quantity == 1
    assert _part(project, "C1", "Concealed hinge").quantity == 2


def test_add_duplicate_remove_and_reopen_preserve_bom(tmp_path):
    project = Project.empty()
    first = Cabinet(cabinet_id="C1", position_x=100, position_y=2500)
    second = deepcopy(first)
    second.cabinet_id = "C2"
    second.position_x = 1100
    project.add_cabinet(first)
    project.add_cabinet(second)
    assert sum(row.quantity for row in generate_project_bom(project)) == 2 * sum(
        row.quantity for row in generate_project_bom(Project(cabinet=deepcopy(first))))
    reopened = load_project(save_project(project, tmp_path / "cabinet-duplicates.json"))
    assert generate_project_bom(reopened) == generate_project_bom(project)
    reopened.remove_cabinet("C2")
    assert {row.cabinet_id for row in generate_project_bom(reopened)} == {"C1"}


def test_rotated_cabinet_dxf_uses_actual_footprint(tmp_path):
    project = Project.empty()
    cabinet = Cabinet(cabinet_id="C1", width=900, depth=600, position_x=100,
                      position_y=100, orientation_degrees=90)
    project.add_cabinet(cabinet)
    path = export_engineering_dxf(project, tmp_path / "rotated-layout.dxf", KITCHEN_LAYOUT)
    doc = ezdxf.readfile(path)
    assert doc.header["$INSUNITS"] == 4 and not doc.audit().has_errors
    outline = next(iter(doc.modelspace().query('LWPOLYLINE[layer=="CABINET_FOOTPRINTS"]')))
    points = list(outline.get_points("xy"))
    assert points == [(100, 2200), (700, 2200), (700, 3100), (100, 3100)]
    labels = [entity.dxf.text for entity in doc.modelspace().query('TEXT[layer=="CABINET_LABELS"]')]
    assert any("ROT 90 deg" in label for label in labels)


def test_visual_prop_does_not_change_bom_or_panel_export(tmp_path):
    project = Project.complete_kitchen_demo()
    baseline = deepcopy(generate_project_bom(project))
    eligible = len(expand_panel_instances(baseline))
    quotation = calculate_quotation(project)
    nesting = nest_project(project)
    definition = get_product("plant_pot")
    prop = PlacedProduct("P1", "plant_pot", 2200, 1000, definition.elevation_z,
                         definition.width, definition.depth, definition.height)
    project.add_product(prop)
    reopened = load_project(save_project(project, tmp_path / "visual-prop.json"))
    assert reopened.placed_products[0].item_id == "P1"
    assert generate_project_bom(reopened) == baseline
    assert calculate_quotation(reopened) == quotation
    assert nest_project(reopened) == nesting
    assert len(eligible_panel_instances(reopened)) == eligible
    panel_doc = ezdxf.readfile(export_engineering_dxf(
        reopened, tmp_path / "panels.dxf", PANEL_OUTLINES))
    assert len(panel_doc.modelspace().query('LWPOLYLINE[layer=="PANEL_OUTLINES"]')) == eligible
    assert "P1" not in [entity.dxf.text for entity in panel_doc.modelspace().query("TEXT")]
    cnc_doc = ezdxf.readfile(export_engineering_dxf(
        reopened, tmp_path / "cnc-prototype.dxf", CNC_PROTOTYPE))
    assert len(cnc_doc.modelspace().query('LWPOLYLINE[layer=="CNC_PANEL_OUTLINES"]')) == eligible


def test_stage7_audit_exports_real_readable_documents(tmp_path):
    result = run(tmp_path)
    assert result["mismatches"] == []
    assert result["geometry"]["cabinet_footprints"] == 6
    assert result["geometry"]["front_elevations"] == 6
    assert result["geometry"]["panel_outlines"] == result["panel_instances"] == 66
    assert result["component_quantity"] == 85
    assert result["hardware_quantity"] == 19
    assert (tmp_path / "six-cabinet-bom.pdf").read_bytes().startswith(b"%PDF")
    workbook = load_workbook(tmp_path / "six-cabinet-bom.xlsx", read_only=True, data_only=True)
    assert len(list(workbook["BOM"].iter_rows(min_row=5, values_only=True))) == 48
    assert (tmp_path / "expected_vs_actual_bom.md").exists()
