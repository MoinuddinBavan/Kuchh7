"""Validate the v0.4.1 premium catalogue sample and write presentation outputs."""

from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import get_catalogue_item
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.persistence import load_project, save_project


def main() -> None:
    output = Path("demo_output")
    project = Project.sample_kitchen("AIZ Premium Catalogue Sample")
    assert [cabinet.material for cabinet in project.cabinets] == ["Cashmere", "Warm White", "Walnut"]
    assert [get_catalogue_item(cabinet.cabinet_type_id).category for cabinet in project.cabinets] == [
        "Base Cabinets", "Wall Cabinets", "Tall Units"
    ]
    assert project.cabinets[1].elevation_z == 1400

    json_path = save_project(project, output / "premium-sample.json")
    xlsx_path = export_bom_xlsx(project, output / "premium-sample-bom.xlsx")
    dxf_path = export_front_elevation_dxf(project, output / "premium-sample-elevation.dxf")
    reopened = load_project(json_path)
    assert reopened == project

    sheet = load_workbook(xlsx_path, read_only=True)["BOM"]
    assert sheet["H4"].value == "Cabinet Type"
    assert {sheet.cell(row, 7).value for row in range(5, sheet.max_row + 1)} == {"C1", "C2", "C3"}
    assert ezdxf.readfile(dxf_path).header["$INSUNITS"] == 4

    print(f"Validated premium project: {reopened.name}")
    print("Furniture: " + ", ".join(get_catalogue_item(item.cabinet_type_id).name for item in reopened.cabinets))
    print("Finishes: " + ", ".join(item.material for item in reopened.cabinets))
    print(f"BOM lines: {len(generate_project_bom(reopened))}")
    print(f"Created: {json_path}, {xlsx_path}, {dxf_path}")


if __name__ == "__main__":
    main()
