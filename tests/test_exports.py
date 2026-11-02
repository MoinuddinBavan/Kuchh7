import ezdxf
from openpyxl import load_workbook

from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Cabinet, Project


def test_excel_export_contains_updated_bom(tmp_path):
    project = Project(cabinet=Cabinet(width=1200, material="Walnut"))
    path = export_bom_xlsx(project, tmp_path / "bom.xlsx")
    sheet = load_workbook(path, data_only=True)["BOM"]
    rows = list(sheet.iter_rows(min_row=5, values_only=True))
    top_panel = next(row for row in rows if row[0] == "Top panel")
    assert top_panel[1] == 1164
    assert top_panel[4] == "Walnut"


def test_dxf_export_uses_millimetres_and_door_division(tmp_path):
    project = Project(cabinet=Cabinet(width=1200, door_count=2))
    path = export_front_elevation_dxf(project, tmp_path / "elevation.dxf")
    document = ezdxf.readfile(path)
    assert document.header["$INSUNITS"] == 4
    lines = list(document.modelspace().query("LINE"))
    assert len(lines) == 1
    assert lines[0].dxf.start.x == 600
