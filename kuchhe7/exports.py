from __future__ import annotations

from pathlib import Path

import ezdxf
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .bom import generate_project_bom
from .catalogue import get_catalogue_item
from .models import Project


def export_bom_xlsx(project: Project, path: str | Path) -> Path:
    destination = Path(path)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "BOM"
    sheet.append(["kuchhe7 Demonstration BOM - NOT FACTORY APPROVED"])
    sheet.append(["Project", project.name, "Type", project.project_type])
    sheet.append([])
    headers = ["Component", "Length (mm)", "Width (mm)", "Thickness (mm)", "Material", "Quantity", "Cabinet ID", "Cabinet Type"]
    sheet.append(headers)
    for component in generate_project_bom(project):
        sheet.append([
            component.name,
            component.length_mm,
            component.width_mm,
            component.thickness_mm,
            component.material,
            component.quantity,
            component.cabinet_id,
            component.cabinet_type,
        ])
    navy = "172A3C"
    teal = "147D83"
    sheet["A1"].font = Font(bold=True, color="FFFFFF", size=14)
    sheet["A1"].fill = PatternFill("solid", fgColor=navy)
    sheet.merge_cells("A1:H1")
    for cell in sheet[4]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=teal)
    sheet.freeze_panes = "A5"
    widths = [26, 15, 15, 17, 20, 12, 13, 28]
    for column, width in zip("ABCDEFGH", widths):
        sheet.column_dimensions[column].width = width
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(destination)
    return destination


def export_front_elevation_dxf(project: Project, path: str | Path) -> Path:
    destination = Path(path)
    project.validate()
    document = ezdxf.new("R2010", setup=True)
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    origin_x = min((cabinet.position_x for cabinet in project.cabinets), default=0)
    max_height = max((cabinet.elevation_z + cabinet.height for cabinet in project.cabinets), default=0)
    for cabinet in project.cabinets:
        width, height = cabinet.width, cabinet.height
        x0 = cabinet.position_x - origin_x
        y0 = cabinet.elevation_z
        modelspace.add_lwpolyline([(x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height)], close=True)
        item = get_catalogue_item(cabinet.cabinet_type_id)
        if item.front_style == "drawers" and cabinet.drawer_count:
            for index in range(1, cabinet.drawer_count):
                y = y0 + height * index / cabinet.drawer_count
                modelspace.add_line((x0, y), (x0 + width, y))
        elif cabinet.door_count:
            for index in range(1, cabinet.door_count):
                x = x0 + width * index / cabinet.door_count
                modelspace.add_line((x, y0), (x, y0 + height))
        modelspace.add_text(cabinet.cabinet_id, height=24).set_placement((x0 + 12, y0 + height - 36))
    arrangement_width = max(
        (cabinet.position_x + cabinet.width for cabinet in project.cabinets), default=origin_x
    ) - origin_x
    modelspace.add_text(
        f"kuchhe7 DEMO - {project.name} - arrangement {arrangement_width} mm",
        height=max(20, max_height * 0.035),
    ).set_placement((0, max_height + 60))
    document.header["$INSUNITS"] = 4
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(destination)
    return destination

