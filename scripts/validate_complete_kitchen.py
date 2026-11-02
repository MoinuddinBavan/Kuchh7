"""Validate the v0.7 complete kitchen and regenerate its safe demo exports."""

from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.presentation import connected_base_runs


def main() -> None:
    output = Path("demo_output")
    project = Project.complete_kitchen_demo("AIZ Complete Kitchen Demo")
    project.validate()
    assert [cabinet.cabinet_id for cabinet in project.cabinets] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert connected_base_runs(project.cabinets)[0].cabinet_ids == ("C1", "C2", "C3")

    json_path = save_project(project, output / "complete-kitchen.json")
    xlsx_path = export_bom_xlsx(project, output / "complete-kitchen-bom.xlsx")
    dxf_path = export_front_elevation_dxf(project, output / "complete-kitchen-elevation.dxf")
    reopened = load_project(json_path)
    assert reopened == project

    sheet = load_workbook(xlsx_path, read_only=True)["BOM"]
    assert {sheet.cell(row, 7).value for row in range(5, sheet.max_row + 1)} == {
        "C1", "C2", "C3", "C4", "C5", "C6"
    }
    drawing = ezdxf.readfile(dxf_path)
    assert drawing.header["$INSUNITS"] == 4
    assert len(list(drawing.modelspace().query("LWPOLYLINE"))) == 6

    print(f"Validated complete project: {reopened.name}")
    print(f"Cabinets: {len(reopened.cabinets)}")
    print(f"BOM lines: {len(generate_project_bom(reopened))}")
    print(f"Created: {json_path}, {xlsx_path}, {dxf_path}")


if __name__ == "__main__":
    main()
