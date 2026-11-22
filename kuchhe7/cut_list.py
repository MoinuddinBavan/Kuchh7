"""Auditable panel cut list derived only from the authoritative cabinet BOM.

Finished panel area, compensated cut size, and sheet consumption are distinct.
All existing and synthetic construction data remain demonstration-only.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .bom import Component, generate_project_bom
from .complete_kitchen_dxf import associate_cabinets_to_walls
from .construction import DEMO_STATUS, EdgeBandingRule
from .models import Project
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


@dataclass(frozen=True)
class CutListRow:
    project_name: str
    wall_id: str | None
    wall_note: str
    cabinet_id: str
    bom_row: int
    part_id: str
    part_name: str
    material: str
    finish: str
    finished_length_mm: float
    finished_width_mm: float
    cut_length_mm: float
    cut_width_mm: float
    thickness_mm: float
    quantity: int
    grain_direction: str
    edge_banding: tuple[EdgeBandingRule, ...]
    profile_id: str
    profile_revision: str
    manufacturing_status: str = DEMO_STATUS

    @property
    def finished_area_m2(self) -> float:
        return self.finished_length_mm * self.finished_width_mm * self.quantity / 1_000_000

    @property
    def cut_area_m2(self) -> float:
        return self.cut_length_mm * self.cut_width_mm * self.quantity / 1_000_000

    def edge_length_mm(self, rule: EdgeBandingRule) -> float:
        return self.finished_length_mm if rule.edge in ("front", "back") else self.finished_width_mm


def is_panel(component: Component) -> bool:
    return min(component.length_mm, component.width_mm, component.thickness_mm) > 0 and component.material != "Hardware"


def generate_cut_list(project: Project) -> list[CutListRow]:
    """Keep one traceable row per BOM panel row; never merge by size alone."""
    project.validate()
    assignments = associate_cabinets_to_walls(project)
    cabinets = {cabinet.cabinet_id: cabinet for cabinet in project.cabinets}
    ordinals: dict[str, int] = defaultdict(int)
    rows = []
    for component in generate_project_bom(project):
        ordinals[component.cabinet_id] += 1
        if not is_panel(component):
            continue
        cabinet = cabinets[component.cabinet_id]
        assignment = assignments[component.cabinet_id]
        rows.append(CutListRow(
            project.name, assignment.wall_id, assignment.note,
            component.cabinet_id, ordinals[component.cabinet_id],
            f"{component.cabinet_id}-P{ordinals[component.cabinet_id]:02d}",
            component.name, component.material, cabinet.material,
            component.length_mm, component.width_mm,
            component.cut_length_mm if component.cut_length_mm is not None else component.length_mm,
            component.cut_width_mm if component.cut_width_mm is not None else component.width_mm,
            component.thickness_mm, component.quantity, component.grain_direction,
            component.edge_banding, component.profile_id or "LEGACY-DEMO",
            component.profile_revision or "legacy",
        ))
    return rows


def edge_banding_totals(rows: list[CutListRow]) -> dict[tuple[str, float, float], float]:
    """Return required linear millimetres by material, band thickness and width."""
    totals: dict[tuple[str, float, float], float] = defaultdict(float)
    for row in rows:
        for rule in row.edge_banding:
            totals[(rule.material, rule.thickness_mm, rule.width_mm)] += row.edge_length_mm(rule) * row.quantity
    return dict(totals)


def cut_list_summary(project: Project) -> dict:
    """Separate panel, hardware and banding quantities without sheet-yield claims."""
    rows = generate_cut_list(project)
    bom = generate_project_bom(project)
    by_material: dict[str, float] = defaultdict(float)
    by_thickness: dict[float, int] = defaultdict(int)
    by_cabinet: dict[str, int] = defaultdict(int)
    by_wall: dict[str, int] = defaultdict(int)
    by_part: dict[str, int] = defaultdict(int)
    banding_by_cabinet: dict[str, float] = defaultdict(float)
    hardware_by_cabinet: dict[str, int] = defaultdict(int)
    for row in rows:
        by_material[row.material] += row.finished_area_m2
        by_thickness[row.thickness_mm] += row.quantity
        by_cabinet[row.cabinet_id] += row.quantity
        by_wall[row.wall_id or "UNASSIGNED"] += row.quantity
        by_part[row.part_name] += row.quantity
        banding_by_cabinet[row.cabinet_id] += sum(
            row.edge_length_mm(rule) * row.quantity for rule in row.edge_banding
        )
    for component in bom:
        if component.material == "Hardware":
            hardware_by_cabinet[component.cabinet_id] += component.quantity
    return {
        "panel_quantity": sum(row.quantity for row in rows),
        "hardware_quantity": sum(c.quantity for c in bom if c.material == "Hardware"),
        "finished_panel_area_m2": sum(row.finished_area_m2 for row in rows),
        "cut_rectangle_area_m2": sum(row.cut_area_m2 for row in rows),
        "by_material_m2": dict(by_material),
        "by_thickness_count": dict(by_thickness),
        "by_cabinet_count": dict(by_cabinet),
        "by_wall_count": dict(by_wall),
        "by_part_count": dict(by_part),
        "edge_banding_mm": edge_banding_totals(rows),
        "edge_banding_by_cabinet_mm": dict(banding_by_cabinet),
        "hardware_by_cabinet_count": dict(hardware_by_cabinet),
    }


def export_cut_list_xlsx(project: Project, path: str | Path) -> Path:
    """Export the BOM-derived demonstration cut schedule with explicit caveats."""
    destination = Path(path)
    book = Workbook()
    sheet = book.active
    sheet.title = "Cut List"
    sheet.append(["KÜCHE7 DEMONSTRATION CUT LIST — NOT FACTORY APPROVED"])
    sheet.append(["Project", project.name, "Dimensions", "millimetres"])
    sheet.append(["Finished and cut rectangles are distinct; sheet yield and machine operations are not included."])
    sheet.append([])
    headers = ["Wall", "Cabinet ID", "BOM row", "Part ID", "Part", "Material", "Finish",
               "Finished L", "Finished W", "Cut L", "Cut W", "Thickness", "Qty", "Grain",
               "Edge banding", "Profile ID", "Revision", "Status"]
    sheet.append(headers)
    for row in generate_cut_list(project):
        edges = "; ".join(f"{rule.edge}: {rule.material} {rule.thickness_mm:g} x {rule.width_mm:g} mm"
                          for rule in row.edge_banding)
        sheet.append([row.wall_id or "UNASSIGNED", row.cabinet_id, row.bom_row,
                      row.part_id, row.part_name, row.material, row.finish,
                      row.finished_length_mm, row.finished_width_mm,
                      row.cut_length_mm, row.cut_width_mm, row.thickness_mm,
                      row.quantity, row.grain_direction, edges,
                      row.profile_id, row.profile_revision, row.manufacturing_status])
    sheet.freeze_panes = "A6"
    sheet.auto_filter.ref = f"A5:R{sheet.max_row}"
    for cell in sheet[5]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="172A3C")
    for column in "ABCDEFGHIJKLMNOPQR":
        sheet.column_dimensions[column].width = 17 if column not in "EOPR" else 28
    destination.parent.mkdir(parents=True, exist_ok=True)
    book.save(destination)
    return destination
