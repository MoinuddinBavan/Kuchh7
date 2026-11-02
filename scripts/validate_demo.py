"""Run the first-client-demo data workflow and write local sample outputs."""

from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.persistence import load_project, save_project


def main() -> None:
    output = Path("demo_output")
    project = Project.sample_kitchen("AIZ Multi-Cabinet Demo")
    project.select_cabinet("C2")
    project.cabinet.height = 760

    bom = generate_project_bom(project)
    assert len(bom) == 24
    assert {item.cabinet_id for item in bom} == {"C1", "C2", "C3"}

    json_path = save_project(project, output / "sample-kitchen.json")
    xlsx_path = export_bom_xlsx(project, output / "sample-kitchen-bom.xlsx")
    dxf_path = export_front_elevation_dxf(project, output / "sample-kitchen-elevation.dxf")

    reopened = load_project(json_path)
    assert reopened == project
    assert load_workbook(xlsx_path, read_only=True)["BOM"]["A5"].value == "Left side panel"
    assert ezdxf.readfile(dxf_path).header["$INSUNITS"] == 4
    print(f"Validated project: {reopened.name}")
    print(f"Cabinets: {', '.join(item.cabinet_id for item in reopened.cabinets)}")
    print(f"Selected cabinet: {reopened.selected_cabinet_id}")
    print(f"BOM lines: {len(generate_project_bom(reopened))}")
    print(f"Created: {json_path}, {xlsx_path}, {dxf_path}")


if __name__ == "__main__":
    main()
