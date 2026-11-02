import json

import ezdxf
import pytest
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Cabinet, MAX_CABINETS, Project
from kuchhe7.persistence import load_project, save_project


def test_sample_kitchen_has_three_valid_unique_cabinets():
    project = Project.sample_kitchen()
    assert [cabinet.cabinet_id for cabinet in project.cabinets] == ["C1", "C2", "C3"]
    assert [cabinet.width for cabinet in project.cabinets] == [900, 600, 800]
    assert all(cabinet.position_y + cabinet.depth == project.room.depth for cabinet in project.cabinets)
    project.validate()


def test_add_select_remove_and_maximum_limit():
    project = Project()
    x, y = project.find_available_back_wall_position()
    second = project.add_cabinet(Cabinet(width=600, door_count=1, cabinet_id="C2", position_x=x, position_y=y))
    assert project.selected_cabinet is second
    x, y = project.find_available_back_wall_position(width=500)
    project.add_cabinet(Cabinet(width=500, cabinet_id="C3", position_x=x, position_y=y))
    for number in range(4, MAX_CABINETS + 1):
        project.add_cabinet(Cabinet(
            width=300,
            depth=200,
            cabinet_id=f"C{number}",
            position_x=(number - 4) * 350,
            position_y=0,
        ))
    with pytest.raises(ValueError, match="maximum"):
        project.add_cabinet(Cabinet(width=300, depth=200, cabinet_id="C11", position_x=2800, position_y=0))
    project.remove_cabinet("C2")
    assert len(project.cabinets) == MAX_CABINETS - 1
    assert "C2" not in {cabinet.cabinet_id for cabinet in project.cabinets}


def test_overlap_and_out_of_bounds_are_rejected():
    project = Project.sample_kitchen()
    project.select_cabinet("C3")
    project.cabinet.position_x = 1500
    with pytest.raises(ValueError, match="overlaps"):
        project.validate()
    project.cabinet.position_x = 3200
    with pytest.raises(ValueError, match="outside"):
        project.validate()


def test_v02_json_migrates_without_losing_cabinet_data(tmp_path):
    old_data = {
        "name": "Legacy Kitchen",
        "project_type": "Kitchen",
        "room": {"width": 3600, "depth": 3200},
        "cabinet": {
            "width": 1200,
            "height": 760,
            "depth": 580,
            "board_thickness": 18,
            "door_count": 3,
            "shelf_count": 2,
            "material": "Walnut",
        },
    }
    old_path = tmp_path / "v02.json"
    old_path.write_text(json.dumps(old_data), encoding="utf-8")
    migrated = load_project(old_path)
    assert len(migrated.cabinets) == 1
    assert migrated.cabinet.cabinet_id == "C1"
    assert migrated.cabinet.width == 1200
    assert migrated.cabinet.height == 760
    assert migrated.cabinet.material == "Walnut"
    assert migrated.cabinet.position_x == 1200
    assert migrated.cabinet.position_y == 2620
    reopened = load_project(save_project(migrated, tmp_path / "v03.json"))
    assert reopened == migrated


def test_combined_bom_and_exports_include_all_cabinets(tmp_path):
    project = Project.sample_kitchen()
    components = generate_project_bom(project)
    assert len(components) == 24
    assert {item.cabinet_id for item in components} == {"C1", "C2", "C3"}
    assert sum(item.quantity for item in components if item.name == "Door") == 5
    assert sum(item.quantity for item in components if item.name == "Concealed hinge") == 10

    workbook_path = export_bom_xlsx(project, tmp_path / "combined.xlsx")
    sheet = load_workbook(workbook_path, data_only=True)["BOM"]
    assert sheet["G4"].value == "Cabinet ID"
    assert sheet["H4"].value == "Cabinet Type"
    assert {sheet.cell(row, 7).value for row in range(5, sheet.max_row + 1)} == {"C1", "C2", "C3"}

    dxf_path = export_front_elevation_dxf(project, tmp_path / "combined.dxf")
    document = ezdxf.readfile(dxf_path)
    assert document.header["$INSUNITS"] == 4
    assert len(list(document.modelspace().query("LWPOLYLINE"))) == 3
    assert len(list(document.modelspace().query("LINE"))) == 2
    cabinet_outlines = list(document.modelspace().query("LWPOLYLINE"))
    all_x = [point[0] for outline in cabinet_outlines for point in outline.get_points()]
    assert min(all_x) == 0
    assert max(all_x) == 2300
