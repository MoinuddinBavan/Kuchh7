"""One self-contained demonstration kitchen DXF from the saved project and BOM.

All entities are in model-space millimetres. The panel outlines are generic
1:1 rectangles, not an approved nesting, machining or machine program.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import ezdxf

from .bom import Component, generate_project_bom
from .catalogue import get_catalogue_item
from .engineering_dxf import (
    _cabinet_footprints, _closed_rectangle, _horizontal_dimension, _layer,
    _line, _room_geometry, _text,
)
from .models import Project
from .openings import cabinet_wall_bounds, wall_length
from .product_libraries import get_product


# This is a grouping threshold for drawing presentation, not an installation
# clearance or approved construction requirement.
DRAWING_WALL_ASSOCIATION_LIMIT_MM = 300
BACK_WALL_FOR_ORIENTATION = {0: "SOUTH", 90: "WEST", 180: "NORTH", 270: "EAST"}


@dataclass(frozen=True)
class WallAssignment:
    wall_id: str | None
    note: str


@dataclass(frozen=True)
class PartRecord:
    part_id: str
    wall_id: str | None
    component: Component
    finish: str

    @property
    def panel_area_m2(self) -> float:
        item = self.component
        if min(item.length_mm, item.width_mm, item.thickness_mm) <= 0:
            return 0.0
        return item.length_mm * item.width_mm * item.quantity / 1_000_000


def associate_cabinets_to_walls(project: Project) -> dict[str, WallAssignment]:
    """Choose one closest stored room wall; explain ties and distant cabinets."""
    project.validate()
    result: dict[str, WallAssignment] = {}
    wall_ids = [wall.wall_id for wall in project.room.walls]
    for cabinet in project.cabinets:
        distances = {wall_id: cabinet_wall_bounds(project.room, cabinet, wall_id).v0
                     for wall_id in wall_ids}
        nearest = min(distances.values())
        if nearest > DRAWING_WALL_ASSOCIATION_LIMIT_MM:
            result[cabinet.cabinet_id] = WallAssignment(
                None, f"UNASSIGNED: nearest wall {nearest:g} mm away; confirm intended wall")
            continue
        tied = [wall_id for wall_id in wall_ids if abs(distances[wall_id] - nearest) < 1e-7]
        preferred = BACK_WALL_FOR_ORIENTATION[cabinet.orientation_degrees]
        chosen = preferred if preferred in tied else tied[0]
        tie_rule = "cabinet orientation" if preferred in tied else "stored wall order"
        note = (f"AMBIGUOUS near {'/'.join(tied)}; assigned {chosen} using {tie_rule}"
                if len(tied) > 1 else f"Nearest wall; gap {nearest:g} mm")
        result[cabinet.cabinet_id] = WallAssignment(chosen, note)
    return result


def _part_records(project: Project, assignments: dict[str, WallAssignment]) -> list[PartRecord]:
    cabinets = {cabinet.cabinet_id: cabinet for cabinet in project.cabinets}
    ordinal: dict[str, int] = {}
    records = []
    for component in generate_project_bom(project):
        cabinet_id = component.cabinet_id
        ordinal[cabinet_id] = ordinal.get(cabinet_id, 0) + 1
        records.append(PartRecord(
            f"{cabinet_id}-P{ordinal[cabinet_id]:02d}",
            assignments[cabinet_id].wall_id,
            component,
            cabinets[cabinet_id].material,
        ))
    return records


def _section(msp, title: str, y: float, *, detail: str = "") -> None:
    _text(msp, title, 0, y, "SECTION_TITLES", 85)
    _line(msp, (0, y - 35), (5000, y - 35), "SECTION_TITLES")
    if detail:
        _text(msp, detail, 0, y - 95, "NOTES", 35)


def _wall_elevations(msp, project: Project, assignments: dict[str, WallAssignment], top: float) -> float:
    _section(msp, "B - WALL-WISE FRONT ELEVATIONS", top)
    top -= 300
    for wall in project.room.walls:
        wall_id = wall.wall_id
        length = wall_length(project.room, wall_id)
        base = top - project.room.height
        _text(msp, f"WALL {wall_id} - {wall.label}", 0, top + 90, "WALL_TITLES", 55)
        _closed_rectangle(msp, 0, base, length, project.room.height, "WALL_ELEVATIONS")
        _horizontal_dimension(msp, 0, length, base - 125, length, "DIMENSIONS")
        _text(msp, f"WALL HEIGHT {project.room.height} mm", length + 80, top - 60,
              "WALL_TITLES", 35)
        for opening in project.room.openings:
            if opening.wall_id != wall_id:
                continue
            _closed_rectangle(msp, opening.offset, base + opening.elevation,
                              opening.width, opening.height, "WALL_OPENINGS")
            _text(msp, f"{opening.opening_id} {opening.kind.upper()} {opening.width} x "
                  f"{opening.height} mm / Z {opening.elevation}",
                  opening.offset + 15, base + opening.elevation + opening.height + 35,
                  "WALL_ANNOTATIONS", 25)
        cabinets = sorted((cabinet for cabinet in project.cabinets
                           if assignments[cabinet.cabinet_id].wall_id == wall_id),
                          key=lambda item: (cabinet_wall_bounds(project.room, item, wall_id).u0,
                                            item.elevation_z, item.cabinet_id))
        previous_right = 0.0
        for index, cabinet in enumerate(cabinets):
            bounds = cabinet_wall_bounds(project.room, cabinet, wall_id)
            projected_width = bounds.u1 - bounds.u0
            _closed_rectangle(msp, bounds.u0, base + cabinet.elevation_z,
                              projected_width, cabinet.height, "WALL_CABINETS")
            if BACK_WALL_FOR_ORIENTATION[cabinet.orientation_degrees] == wall_id:
                style = get_catalogue_item(cabinet.cabinet_type_id).front_style
                if style == "drawers" and cabinet.drawer_count:
                    for division in range(1, cabinet.drawer_count):
                        z = base + cabinet.elevation_z + cabinet.height * division / cabinet.drawer_count
                        _line(msp, (bounds.u0, z), (bounds.u1, z), "WALL_FRONT_DETAILS")
                elif cabinet.door_count:
                    for division in range(1, cabinet.door_count):
                        u = bounds.u0 + projected_width * division / cabinet.door_count
                        _line(msp, (u, base + cabinet.elevation_z),
                              (u, base + cabinet.elevation_z + cabinet.height), "WALL_FRONT_DETAILS")
            _text(msp, cabinet.cabinet_id, bounds.u0 + 15,
                  base + cabinet.elevation_z + cabinet.height / 2, "WALL_ANNOTATIONS", 35)
            _text(msp, f"{cabinet.cabinet_id}: U {bounds.u0:g}-{bounds.u1:g}; "
                  f"Z {cabinet.elevation_z}; {projected_width:g} x {cabinet.height}; "
                  f"gap from previous projection {max(0, bounds.u0 - previous_right):g} mm",
                  0, base - 280 - index * 50, "WALL_ANNOTATIONS", 27)
            previous_right = max(previous_right, bounds.u1)
        if not cabinets:
            _text(msp, "No associated cabinets", 0, base - 260, "WALL_ANNOTATIONS", 32)
        _text(msp, "Countertop height: not defined as engineering project data",
              0, base - 350 - len(cabinets) * 50, "NOTES", 27)
        top = base - max(750, 450 + len(cabinets) * 50)
    return top


def _cabinet_details(msp, project: Project, assignments: dict[str, WallAssignment], top: float,
                     records: list[PartRecord]) -> float:
    _section(msp, "C - CABINET MANUFACTURING REFERENCES", top,
             detail="Illustrative construction only; dimensions in mm; no approved machining definitions")
    y = top - 180
    for cabinet in project.cabinets:
        wall_id = assignments[cabinet.cabinet_id].wall_id or "UNASSIGNED"
        item = get_catalogue_item(cabinet.cabinet_type_id)
        parts = [record.part_id for record in records if record.component.cabinet_id == cabinet.cabinet_id]
        _text(msp, f"{cabinet.cabinet_id} | {item.name} | WALL {wall_id} | "
              f"W {cabinet.width} H {cabinet.height} D {cabinet.depth} | "
              f"X {cabinet.position_x} Y {cabinet.position_y} Z {cabinet.elevation_z} | "
              f"ROT {cabinet.orientation_degrees}", 0, y, "CABINET_DETAILS", 32)
        _text(msp, f"Finish {cabinet.material} | Board {cabinet.board_thickness} mm | "
              f"Doors {cabinet.door_count} Drawers {cabinet.drawer_count} Shelves {cabinet.shelf_count} | "
              f"BOM refs {', '.join(parts)}", 0, y - 46, "CABINET_DETAILS", 26)
        _text(msp, assignments[cabinet.cabinet_id].note, 0, y - 90, "NOTES", 23)
        for assignment in project.hardware_assignments:
            if assignment.cabinet_id == cabinet.cabinet_id:
                _text(msp, f"Assigned hardware metadata: {assignment.assignment_id} "
                      f"{get_product(assignment.type_id).name} x {assignment.quantity}; "
                      "not an additional generic BOM row", 0, y - 122, "NOTES", 23)
        y -= 200
    return y - 180


_HEADERS = ("Part ID", "Cabinet", "Wall", "Component", "Material", "Finish",
            "L mm", "W mm", "T mm", "Qty", "Area m2", "Grain", "Edge")
_COLUMNS = (0, 220, 430, 690, 1410, 1920, 2400, 2660, 2920, 3140,
            3340, 3700, 4050)


def _bom_table(msp, title: str, records: list[PartRecord], top: float) -> float:
    _text(msp, title, 0, top, "BOM_TITLES", 48)
    y = top - 75
    for label, x in zip(_HEADERS, _COLUMNS):
        _text(msp, label, x, y, "BOM_HEADERS", 25)
    _line(msp, (0, y - 15), (4550, y - 15), "BOM_RULES")
    y -= 55
    for record in records:
        item = record.component
        values = (record.part_id, item.cabinet_id, record.wall_id or "UNASSIGNED",
                  item.name, item.material, record.finish,
                  f"{item.length_mm:g}", f"{item.width_mm:g}", f"{item.thickness_mm:g}",
                  str(item.quantity), f"{record.panel_area_m2:.3f}", "N/A", "N/A")
        for value, x in zip(values, _COLUMNS):
            _text(msp, value, x, y, "BOM_ROWS", 24)
        y -= 44
    if not records:
        _text(msp, "No associated BOM components", 0, y, "NOTES", 28)
        y -= 50
    panel_qty = sum(item.component.quantity for item in records if item.panel_area_m2 > 0)
    hardware_qty = sum(item.component.quantity for item in records if item.component.material == "Hardware")
    _text(msp, f"TOTAL: {len(records)} BOM rows; {panel_qty} panels; "
          f"{hardware_qty} hardware units; {sum(item.panel_area_m2 for item in records):.3f} m2 panel area",
          0, y - 15, "BOM_TOTALS", 32)
    return y - 125


def _panel_contours(doc, msp, records: list[PartRecord], top: float) -> None:
    _section(msp, "F/G - PANEL CUTTING CONTOURS / CNC-ORIENTED LAYERS", top,
             detail="1:1 rectangles from BOM; NOT nested, production approved or machine validated")
    _text(msp, "CNC MACHINE COMPATIBILITY NOT YET VALIDATED", 0, top - 145, "NOTES", 40)
    _text(msp, "Drilling, pockets, routing and toolpaths: UNAVAILABLE - no approved project definitions",
          0, top - 210, "NOTES", 30)
    if "KUCHE7_MASTER" not in doc.appids:
        doc.appids.new("KUCHE7_MASTER")
    x, row_top, row_height = 0.0, top - 390, 0.0
    for record in records:
        item = record.component
        if min(item.length_mm, item.width_mm, item.thickness_mm) <= 0:
            continue
        cut_length = item.cut_length_mm if item.cut_length_mm is not None else item.length_mm
        cut_width = item.cut_width_mm if item.cut_width_mm is not None else item.width_mm
        for instance in range(1, item.quantity + 1):
            if x and x + cut_length > 6000:
                x, row_top, row_height = 0.0, row_top - row_height - 160, 0.0
            lower_y = row_top - cut_width
            entity = _closed_rectangle(msp, x, lower_y, cut_length, cut_width,
                                       "CNC_CUT_OUTER")
            entity.set_xdata("KUCHE7_MASTER", [
                (1000, f"PART={record.part_id}-{instance:02d}"),
                (1000, f"CABINET={item.cabinet_id}"),
                (1000, f"WALL={record.wall_id or 'UNASSIGNED'}"),
                (1000, f"COMPONENT={item.name}"),
                (1000, f"MATERIAL={item.material}"),
                (1000, f"PROFILE={item.profile_id or 'LEGACY-DEMO'}:{item.profile_revision or 'legacy'}"),
                (1000, f"GRAIN={item.grain_direction}"),
                (1000, "EDGES=" + ";".join(rule.edge + ":" + rule.material
                                              for rule in item.edge_banding)),
                (1040, float(cut_length)), (1040, float(cut_width)),
                (1040, float(item.thickness_mm)), (1070, instance),
            ])
            label = (f"{record.part_id}-{instance:02d} | {item.cabinet_id} | "
                     f"WALL {record.wall_id or 'UNASSIGNED'} | {item.name} | "
                     f"{cut_length:g} x {cut_width:g} x {item.thickness_mm:g} | {item.material}")
            _text(msp, label, x, row_top + 35, "PANEL_ANNOTATIONS", 23)
            x += max(cut_length, len(label) * 14) + 130
            row_height = max(row_height, cut_width)


def build_complete_kitchen_drawing(project: Project):
    """Build one R2010 model-space drawing without modifying the project."""
    project.validate()
    assignments = associate_cabinets_to_walls(project)
    records = _part_records(project, assignments)
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    for name, color in (
        ("SECTION_TITLES", 7), ("NOTES", 8), ("ROOM_WALLS", 7),
        ("DOORS", 3), ("WINDOWS", 5), ("DIMENSIONS", 4), ("LABELS", 7),
        ("CABINET_FOOTPRINTS", 2), ("CABINET_LABELS", 7),
        ("WALL_TITLES", 7), ("WALL_ELEVATIONS", 8), ("WALL_OPENINGS", 5),
        ("WALL_CABINETS", 2), ("WALL_FRONT_DETAILS", 8),
        ("WALL_ANNOTATIONS", 7), ("CABINET_DETAILS", 7),
        ("BOM_TITLES", 7), ("BOM_HEADERS", 4), ("BOM_RULES", 8),
        ("BOM_ROWS", 7), ("BOM_TOTALS", 2), ("PANEL_ANNOTATIONS", 7),
        ("CNC_CUT_OUTER", 2), ("CNC_CUT_INNER", 8), ("CNC_DRILL", 8),
        ("CNC_POCKET", 8), ("CNC_ROUTE", 8), ("CNC_REFERENCE", 8),
    ):
        _layer(doc, name, color)
    msp = doc.modelspace()
    _text(msp, f"KUCHE7 COMPLETE KITCHEN | {project.name}", 0,
          project.room.depth + 460, "SECTION_TITLES", 90)
    _text(msp, "ILLUSTRATIVE ENGINEERING DRAWING | ALL GEOMETRY IN mm | NOT FACTORY APPROVED",
          0, project.room.depth + 345, "NOTES", 35)
    _text(msp, "A - COMPLETE KITCHEN PLAN", 0, project.room.depth + 220,
          "SECTION_TITLES", 65)
    _room_geometry(msp, project)
    _cabinet_footprints(msp, project)
    plan_schedule_bottom = -420 - max(0, (len(project.cabinets) - 1) // 2) * 160 - 100
    top = _wall_elevations(msp, project, assignments, plan_schedule_bottom - 700)
    top = _cabinet_details(msp, project, assignments, top - 150, records)
    specified = any(record.component.edge_banding or record.component.grain_direction != "undefined"
                    for record in records)
    _section(msp, "D - COMPLETE KITCHEN BOM", top,
             detail=("Specified grain/edge metadata on panel contours; DEMO profile, not factory approved"
                     if specified else "Grain/edge: N/A (not specified); hardware from illustrative BOM only"))
    top = _bom_table(msp, "ALL CABINETS - MATERIAL SCHEDULE", records, top - 175)
    _section(msp, "E - WALL-WISE MATERIAL SCHEDULES", top)
    top -= 175
    for wall in project.room.walls:
        top = _bom_table(msp, f"WALL {wall.wall_id} - {wall.label}",
                         [record for record in records if record.wall_id == wall.wall_id], top)
    unassigned = [record for record in records if record.wall_id is None]
    if unassigned:
        top = _bom_table(msp, "UNASSIGNED CABINETS - REVIEW WALL ASSOCIATION", unassigned, top)
    _panel_contours(doc, msp, records, top - 180)
    return doc


def export_complete_kitchen_dxf(project: Project, path: str | Path) -> Path:
    """Export one complete, self-contained DXF; never labels it as a DWG."""
    destination = Path(path)
    if destination.suffix.lower() != ".dxf":
        raise ValueError("Complete kitchen export must use a genuine .dxf extension.")
    document = build_complete_kitchen_drawing(project)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(destination)
    return destination
