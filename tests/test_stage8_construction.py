"""Synthetic construction validation; none of these values are factory approved."""
from __future__ import annotations

from copy import deepcopy

import ezdxf
import pytest
from openpyxl import load_workbook

from kuchhe7.bom import generate_bom, generate_project_bom
from kuchhe7.complete_kitchen_dxf import export_complete_kitchen_dxf
from kuchhe7.construction import ConstructionProfile, synthetic_profile_for
from kuchhe7.cut_list import cut_list_summary, edge_banding_totals, export_cut_list_xlsx, generate_cut_list
from kuchhe7.engineering_dxf import PANEL_OUTLINES, export_engineering_dxf
from kuchhe7.exports import export_bom_xlsx
from kuchhe7.models import HardwareAssignment, PlacedProduct, Project
from kuchhe7.nesting import SheetSettings, expand_panel_instances, nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import get_product


def _profiled_project():
    project = Project.complete_kitchen_demo()
    for cabinet in project.cabinets:
        cabinet.construction_profile = synthetic_profile_for(cabinet).to_dict()
    return project


def _part(project, cabinet_id, name):
    return next(c for c in generate_project_bom(project)
                if c.cabinet_id == cabinet_id and c.name == name)


def test_legacy_six_cabinet_bom_is_unchanged():
    project = Project.complete_kitchen_demo()
    assert len(generate_project_bom(project)) == 48
    assert len(generate_cut_list(project)) == 43
    assert cut_list_summary(project)["panel_quantity"] == 66
    assert cut_list_summary(project)["hardware_quantity"] == 19


def test_all_six_explicit_profile_families_and_synthetic_sink_difference():
    project = _profiled_project()
    assert len(project.cabinets) == 6
    assert len(generate_project_bom(project)) == 47
    assert len(generate_cut_list(project)) == 42
    assert _part(project, "C1", "Door").quantity == 2
    assert _part(project, "C2", "Drawer front").quantity == 3
    assert _part(project, "C2", "Drawer runner pair").quantity == 3
    assert _part(project, "C3", "Sink rail").quantity == 2
    assert not any(c.cabinet_id == "C3" and c.name in ("Back panel", "Shelf")
                   for c in generate_project_bom(project))
    assert _part(project, "C4", "Door").quantity == 2
    assert not any(c.cabinet_id == "C5" and c.name == "Door" for c in generate_project_bom(project))
    assert _part(project, "C6", "Left side panel").length_mm == 2100


def test_profile_requires_identity_revision_and_complete_rules():
    project = Project.complete_kitchen_demo()
    cabinet = project.cabinets[0]
    data = synthetic_profile_for(cabinet).to_dict()
    del data["back_thickness_mm"]
    cabinet.construction_profile = data
    with pytest.raises(ValueError, match="Incomplete"):
        generate_bom(cabinet)
    data = synthetic_profile_for(cabinet).to_dict()
    data["revision"] = ""
    cabinet.construction_profile = data
    with pytest.raises(ValueError, match="revision"):
        generate_bom(cabinet)


def test_panel_dimensions_thickness_finish_and_hardware_are_traceable():
    project = _profiled_project()
    cabinet = project.cabinets[0]
    assert (cabinet.width, cabinet.height, cabinet.depth, cabinet.board_thickness) == (800, 720, 600, 18)
    top = _part(project, "C1", "Top panel")
    back = _part(project, "C1", "Back panel")
    door = _part(project, "C1", "Door")
    assert (top.length_mm, top.width_mm, top.thickness_mm) == (764, 600, 18)
    assert (back.length_mm, back.width_mm, back.thickness_mm) == (684, 764, 6)
    assert (door.length_mm, door.width_mm, door.quantity) == (716, 397, 2)
    assert (door.material, door.profile_revision) == ("Cashmere", "1.0-synthetic")
    assert _part(project, "C1", "Concealed hinge").quantity == 4


def test_edge_banding_cut_compensation_grain_and_nesting():
    project = _profiled_project()
    cabinet = project.cabinets[0]
    data = cabinet.construction_profile
    data["edge_banding"] = {
        "Door": [{"edge": "front", "material": "Synthetic ABS", "thickness_mm": 1,
                  "width_mm": 22}]
    }
    data["grain_directions"] = {"Door": "lengthwise"}
    data["compensate_cut_for_banding"] = True
    door = _part(project, "C1", "Door")
    assert (door.cut_length_mm, door.cut_width_mm, door.grain_direction) == (716, 396, "lengthwise")
    rows = generate_cut_list(project)
    assert edge_banding_totals(rows) == {("Synthetic ABS", 1, 22): 1432}
    instances = [p for p in expand_panel_instances(generate_project_bom(project))
                 if p.cabinet_id == "C1" and p.component_name == "Door"]
    assert len(instances) == 2
    assert all((p.length_mm, p.width_mm, p.grain_direction) == (716, 396, "lengthwise")
               for p in instances)
    nested = nest_project(project, SheetSettings(allow_rotation=True))
    assert all(not p.rotated for p in nested.placed_panels
               if p.panel.cabinet_id == "C1" and p.panel.component_name == "Door")


def test_explicit_hardware_and_material_separation():
    project = _profiled_project()
    cabinet = project.cabinets[0]
    cabinet.construction_profile["extra_hardware"] = {"Synthetic handle": 2}
    cabinet.construction_profile["panel_materials"] = {"Back panel": "Synthetic back board"}
    assert _part(project, "C1", "Synthetic handle").quantity == 2
    assert _part(project, "C1", "Back panel").material == "Synthetic back board"
    assert cut_list_summary(project)["hardware_quantity"] == 21
    assert "Synthetic back board" in cut_list_summary(project)["by_material_m2"]


def test_profile_hardware_cannot_duplicate_assigned_fitting():
    project = _profiled_project()
    project.cabinets[0].construction_profile["extra_hardware"] = {"Bar Handle · Sample": 2}
    project.add_hardware_assignment(HardwareAssignment("H-STAGE8", "C1", "handle_bar", 2))
    with pytest.raises(ValueError, match="both assigned hardware"):
        generate_project_bom(project)


def test_dimension_and_configuration_changes_are_isolated():
    project = _profiled_project()
    before_other = [c for c in generate_project_bom(project) if c.cabinet_id != "C1"]
    cabinet = project.cabinets[0]
    cabinet.width -= 100
    cabinet.depth -= 50
    cabinet.board_thickness = 20
    cabinet.door_count = 1
    cabinet.shelf_count = 2
    cabinet.material = "Walnut"
    assert _part(project, "C1", "Top panel").length_mm == 660
    assert _part(project, "C1", "Shelf").quantity == 2
    assert _part(project, "C1", "Door").quantity == 1
    assert _part(project, "C1", "Left side panel").width_mm == 550
    assert _part(project, "C1", "Top panel").material == "Walnut"
    assert [c for c in generate_project_bom(project) if c.cabinet_id != "C1"] == before_other


def test_profile_snapshot_survives_save_and_reopen(tmp_path):
    project = _profiled_project()
    project.cabinets[0].construction_profile["revision"] = "synthetic-2"
    before = generate_project_bom(project)
    opened = load_project(save_project(project, tmp_path / "profiled.json"))
    assert opened.cabinets[0].construction_profile["revision"] == "synthetic-2"
    assert generate_project_bom(opened) == before
    assert generate_cut_list(opened) == generate_cut_list(project)


def test_cut_list_reconciles_bom_and_wall_assignments():
    project = _profiled_project()
    rows = generate_cut_list(project)
    panels = [c for c in generate_project_bom(project) if c.length_mm > 0 and c.width_mm > 0]
    assert sum(r.quantity for r in rows) == sum(c.quantity for c in panels) == 65
    assert len({r.part_id for r in rows}) == len(rows)
    assert all(r.project_name == project.name and r.wall_note and r.cabinet_id for r in rows)
    assert sum(cut_list_summary(project)["by_cabinet_count"].values()) == 65
    assert sum(cut_list_summary(project)["by_wall_count"].values()) == 65


def test_xlsx_and_engineering_dxfs_follow_profiled_bom(tmp_path):
    project = _profiled_project()
    workbook = load_workbook(export_bom_xlsx(project, tmp_path / "bom.xlsx"), read_only=True)
    assert workbook["BOM"].max_row == 51
    cut = load_workbook(export_cut_list_xlsx(project, tmp_path / "cut.xlsx"), read_only=True)
    assert cut["Cut List"].max_row == 47
    drawing = ezdxf.readfile(export_engineering_dxf(project, tmp_path / "panels.dxf", PANEL_OUTLINES))
    assert len(drawing.modelspace().query('LWPOLYLINE[layer=="PANEL_OUTLINES"]')) == 65
    complete = ezdxf.readfile(export_complete_kitchen_dxf(project, tmp_path / "complete.dxf"))
    assert complete.header["$INSUNITS"] == 4
    assert len(complete.modelspace().query('LWPOLYLINE[layer=="CNC_CUT_OUTER"]')) == 65


def test_adding_visual_props_does_not_change_manufacturing_outputs():
    project = _profiled_project()
    before_bom = deepcopy(generate_project_bom(project))
    before_cut = generate_cut_list(project)
    prop = get_product("potted_green_plant")
    project.add_product(PlacedProduct("P-STAGE8", prop.type_id, 300, 2650, prop.elevation_z,
                                      prop.width, prop.depth, prop.height))
    assert generate_project_bom(project) == before_bom
    assert generate_cut_list(project) == before_cut
    assert cut_list_summary(project)["panel_quantity"] == 65
