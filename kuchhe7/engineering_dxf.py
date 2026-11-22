"""Dimensioned demonstration drawings derived from the existing project and BOM.

Plan DXF origin is the south-west room corner: DXF X equals model X and
DXF Y equals room depth minus model Y. The project model itself is unchanged.
These files contain no drilling, toolpaths, nesting or machine instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from pathlib import Path

import ezdxf

from .bom import Component, generate_project_bom
from .catalogue import get_catalogue_item
from .models import Opening, Project
from .openings import WALL_IDS, wall_length

ROOM_PLAN = "room_plan"
KITCHEN_LAYOUT = "kitchen_layout"
FRONT_ELEVATIONS = "front_elevations"
PANEL_OUTLINES = "panel_outlines"
CNC_PROTOTYPE = "cnc_prototype"
DRAWING_TYPES = (ROOM_PLAN, KITCHEN_LAYOUT, FRONT_ELEVATIONS, PANEL_OUTLINES, CNC_PROTOTYPE)
DRAWING_LABELS = {
    ROOM_PLAN: "Room Plan",
    KITCHEN_LAYOUT: "Kitchen Layout",
    FRONT_ELEVATIONS: "Cabinet Front Elevations",
    PANEL_OUTLINES: "Cabinet Panel Outlines",
    CNC_PROTOTYPE: "CNC-Targeted Generic Prototype",
}


@dataclass(frozen=True)
class CncDxfProfile:
    """Generic DXF settings awaiting the client's accepted CAM sample/specification."""

    outline_layer: str = "CNC_PANEL_OUTLINES"
    label_layer: str = "CNC_LABELS"
    origin_x_mm: float = 0.0
    origin_y_mm: float = 0.0
    geometry_type: str = "LWPOLYLINE"
    include_labels: bool = False

    def validate(self) -> None:
        if self.geometry_type not in ("LWPOLYLINE", "POLYLINE"):
            raise ValueError("Prototype supports only closed LWPOLYLINE or POLYLINE outlines.")
        for name in (self.outline_layer, self.label_layer):
            if not name or any(char in name for char in '<>/\\":;?*|=') or len(name) > 255:
                raise ValueError("Invalid DXF layer name in CNC profile.")
        if self.outline_layer.upper() == self.label_layer.upper():
            raise ValueError("CNC outline and annotation layers must be different.")
        if not all(-1_000_000 <= value <= 1_000_000 for value in (self.origin_x_mm, self.origin_y_mm)):
            raise ValueError("CNC prototype origin is outside the supported range.")


def _layer(doc, name: str, color: int) -> None:
    if name not in doc.layers:
        doc.layers.new(name, dxfattribs={"color": color})


def _text(msp, value: str, x: float, y: float, layer: str, height: float = 38) -> None:
    # DXF text uses simple ASCII to avoid font substitution in client CAD tools.
    safe = value.encode("ascii", "replace").decode("ascii")
    msp.add_text(safe, dxfattribs={"height": height, "layer": layer}).set_placement((x, y))


def _line(msp, start, end, layer: str) -> None:
    msp.add_line(start, end, dxfattribs={"layer": layer})


def _closed_rectangle(msp, x: float, y: float, width: float, height: float,
                      layer: str, geometry_type: str = "LWPOLYLINE"):
    points = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    if geometry_type == "POLYLINE":
        entity = msp.add_polyline2d(points, close=True, dxfattribs={"layer": layer})
    else:
        entity = msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
    return entity


def _horizontal_dimension(msp, x0: float, x1: float, y: float, value: float,
                          layer: str) -> None:
    _line(msp, (x0, y), (x1, y), layer)
    for x in (x0, x1):
        _line(msp, (x, y - 24), (x, y + 24), layer)
    _text(msp, f"{value:g} mm", (x0 + x1) / 2 - 70, y + 34, layer, 32)


def _vertical_dimension(msp, y0: float, y1: float, x: float, value: float,
                        layer: str) -> None:
    _line(msp, (x, y0), (x, y1), layer)
    for y in (y0, y1):
        _line(msp, (x - 24, y), (x + 24, y), layer)
    _text(msp, f"{value:g} mm", x - 130, (y0 + y1) / 2, layer, 32)


def _wall_point(project: Project, wall_id: str, offset: float, inward: float = 0) -> tuple[float, float]:
    room = project.room
    if wall_id == "NORTH":
        return offset, room.depth - inward
    if wall_id == "SOUTH":
        return offset, inward
    if wall_id == "WEST":
        return inward, room.depth - offset
    if wall_id == "EAST":
        return room.width - inward, room.depth - offset
    raise ValueError(f"Unsupported wall identifier: {wall_id}")


def _draw_opening(msp, project: Project, opening: Opening) -> None:
    start = _wall_point(project, opening.wall_id, opening.offset)
    end = _wall_point(project, opening.wall_id, opening.offset + opening.width)
    if opening.kind == "window":
        _line(msp, start, end, "WINDOWS")
    else:
        left = opening.swing.startswith("Left")
        inward = opening.swing.endswith("In")
        hinge_u = opening.offset if left else opening.offset + opening.width
        direction = 1 if inward else -1
        hinge = _wall_point(project, opening.wall_id, hinge_u)
        leaf_end = _wall_point(project, opening.wall_id, hinge_u, direction * opening.width)
        _line(msp, hinge, leaf_end, "DOORS")
        arc_points = []
        for step in range(17):
            angle = (pi / 2) * step / 16
            u = hinge_u + (opening.width * cos(angle) if left else -opening.width * cos(angle))
            arc_points.append(_wall_point(project, opening.wall_id, u,
                                          direction * opening.width * sin(angle)))
        msp.add_lwpolyline(arc_points, dxfattribs={"layer": "DOORS"})
    midpoint = _wall_point(project, opening.wall_id, opening.offset + opening.width / 2)
    _text(msp, f"{opening.opening_id} {opening.kind.upper()} {opening.width} mm",
          midpoint[0] + 28, midpoint[1] + 35, "LABELS", 42)
    _text(msp, f"offset {opening.offset} mm / sill {opening.elevation} mm / H {opening.height} mm",
          midpoint[0] + 28, midpoint[1] + 90, "LABELS", 29)


def _room_geometry(msp, project: Project) -> None:
    room = project.room
    for wall_id in WALL_IDS:
        openings = sorted((item for item in room.openings if item.wall_id == wall_id),
                          key=lambda item: item.offset)
        wall_end = wall_length(room, wall_id)
        cursor = 0
        for opening in openings:
            # Window sills still have wall below them; plan shows an opening break.
            if opening.offset > cursor:
                _line(msp, _wall_point(project, wall_id, cursor),
                      _wall_point(project, wall_id, opening.offset), "ROOM_WALLS")
            _draw_opening(msp, project, opening)
            cursor = max(cursor, opening.offset + opening.width)
        if cursor < wall_end:
            _line(msp, _wall_point(project, wall_id, cursor),
                  _wall_point(project, wall_id, wall_end), "ROOM_WALLS")
        label_point = _wall_point(project, wall_id, wall_end / 2)
        _text(msp, wall_id, label_point[0] + 35, label_point[1] + 95, "LABELS", 28)
    _horizontal_dimension(msp, 0, room.width, -175, room.width, "DIMENSIONS")
    _vertical_dimension(msp, 0, room.depth, -175, room.depth, "DIMENSIONS")
    _text(msp, "PLAN ORIGIN: SOUTH-WEST (0,0). MODEL Y = ROOM DEPTH - DXF Y.",
          0, -280, "NOTES", 27)


def _cabinet_footprints(msp, project: Project) -> None:
    for index, cabinet in enumerate(project.cabinets):
        x = cabinet.position_x
        footprint_width, footprint_depth = cabinet.footprint_width, cabinet.footprint_depth
        y = project.room.depth - cabinet.position_y - footprint_depth
        _closed_rectangle(msp, x, y, footprint_width, footprint_depth, "CABINET_FOOTPRINTS")
        # Compact footprint ID plus a schedule below the plan keeps vertically
        # stacked base/wall units individually identifiable at full-room zoom.
        _text(msp, cabinet.cabinet_id, x + 20,
              y + (footprint_depth - 75 if cabinet.elevation_z else 65),
              "CABINET_LABELS", 52)
        _horizontal_dimension(msp, x, x + footprint_width, y - 65, footprint_width, "DIMENSIONS")
        schedule_x = (index % 2) * 1850
        schedule_y = -420 - (index // 2) * 160
        item_name = get_catalogue_item(cabinet.cabinet_type_id).name
        _text(msp, f"{cabinet.cabinet_id} {item_name}", schedule_x, schedule_y, "CABINET_LABELS", 43)
        _text(msp, f"X {cabinet.position_x} Y {cabinet.position_y} Z {cabinet.elevation_z}",
              schedule_x, schedule_y - 50, "CABINET_LABELS", 35)
        _text(msp, f"{cabinet.width} x {cabinet.depth} x {cabinet.height} mm / ROT {cabinet.orientation_degrees} deg",
              schedule_x, schedule_y - 100, "CABINET_LABELS", 35)


def _front_elevations(msp, project: Project) -> None:
    for cabinet in project.cabinets:
        x, y = cabinet.position_x, cabinet.elevation_z
        _closed_rectangle(msp, x, y, cabinet.width, cabinet.height, "ELEVATION_OUTLINES")
        style = get_catalogue_item(cabinet.cabinet_type_id).front_style
        divisions = cabinet.drawer_count if style == "drawers" else cabinet.door_count
        for index in range(1, divisions):
            if style == "drawers":
                line_y = y + cabinet.height * index / divisions
                _line(msp, (x, line_y), (x + cabinet.width, line_y), "ELEVATION_DETAILS")
            else:
                line_x = x + cabinet.width * index / divisions
                _line(msp, (line_x, y), (line_x, y + cabinet.height), "ELEVATION_DETAILS")
        _text(msp, f"{cabinet.cabinet_id} {get_catalogue_item(cabinet.cabinet_type_id).name}",
              x + 15, y + cabinet.height + 55, "LABELS", 30)
        _text(msp, f"Z {cabinet.elevation_z} mm", x + 15, y + cabinet.height + 92, "LABELS", 25)
        _horizontal_dimension(msp, x, x + cabinet.width, y - 70, cabinet.width, "DIMENSIONS")
        _vertical_dimension(msp, y, y + cabinet.height, x - 65, cabinet.height, "DIMENSIONS")


def eligible_panel_instances(project: Project) -> list[tuple[Component, int]]:
    """Expand only BOM rows with positive L/W/T; hardware and props stay out."""
    return [(component, number) for component in generate_project_bom(project)
            if component.length_mm > 0 and component.width_mm > 0 and component.thickness_mm > 0
            for number in range(1, component.quantity + 1)]


def _panel_outlines(doc, msp, project: Project, profile: CncDxfProfile | None) -> None:
    cnc = profile is not None
    outline_layer = profile.outline_layer if cnc else "PANEL_OUTLINES"
    label_layer = profile.label_layer if cnc else "PANEL_LABELS"
    if cnc:
        _layer(doc, outline_layer, 2)
        _layer(doc, label_layer, 7)
        if "KUCHE7_DEMO" not in doc.appids:
            doc.appids.new("KUCHE7_DEMO")
    x0 = profile.origin_x_mm if cnc else 0
    y0 = profile.origin_y_mm if cnc else 0
    x, y, row_height = x0, y0, 0.0
    max_row_width = 6000.0
    gap = 150.0 if not cnc or profile.include_labels else 100.0
    for component, instance in eligible_panel_instances(project):
        length = component.cut_length_mm if component.cut_length_mm is not None else component.length_mm
        width = component.cut_width_mm if component.cut_width_mm is not None else component.width_mm
        title = f"{component.cabinet_id} {component.name} #{instance}"
        detail = f"{length:g} x {width:g} x {component.thickness_mm:g} mm / {component.material}"
        allocation_width = max(length, len(title) * 16, len(detail) * 12) if (not cnc or profile.include_labels) else length
        if x > x0 and x + allocation_width > x0 + max_row_width:
            x, y, row_height = x0, y + row_height + gap, 0.0
        entity = _closed_rectangle(msp, x, y, length, width, outline_layer,
                                   profile.geometry_type if cnc else "LWPOLYLINE")
        if cnc:
            entity.set_xdata("KUCHE7_DEMO", [(1000, component.cabinet_id),
                                             (1000, component.name),
                                             (1000, component.material),
                                             (1000, component.profile_id or "LEGACY-DEMO"),
                                             (1000, component.profile_revision or "legacy"),
                                             (1000, component.grain_direction),
                                             (1000, ";".join(rule.edge + ":" + rule.material
                                                             for rule in component.edge_banding)),
                                             (1040, float(component.thickness_mm)),
                                             (1070, instance)])
        if not cnc or profile.include_labels:
            _text(msp, title, x, y - 48, label_layer, 25)
            _text(msp, detail, x, y - 80, label_layer, 21)
        x += allocation_width + gap
        row_height = max(row_height, width)
    if not cnc:
        _text(msp, "DEMONSTRATION PANEL OUTLINES FROM BOM - NOT APPROVED FOR CUTTING OR DRILLING",
              0, -160, "NOTES", 30)


def export_engineering_dxf(project: Project, path: str | Path, drawing_type: str,
                           *, cnc_profile: CncDxfProfile | None = None) -> Path:
    """Export a selected engineering drawing; CNC mode is a generic prototype."""
    if drawing_type not in DRAWING_TYPES:
        raise ValueError(f"Unknown engineering drawing type: {drawing_type}")
    project.validate()
    if drawing_type == CNC_PROTOTYPE:
        cnc_profile = cnc_profile or CncDxfProfile()
        cnc_profile.validate()
    elif cnc_profile is not None:
        raise ValueError("CNC profile applies only to the generic CNC prototype.")
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    for name, color in (("ROOM_WALLS", 7), ("DOORS", 3), ("WINDOWS", 5),
                        ("DIMENSIONS", 4), ("LABELS", 7), ("NOTES", 8),
                        ("CABINET_FOOTPRINTS", 2), ("CABINET_LABELS", 7),
                        ("ELEVATION_OUTLINES", 2), ("ELEVATION_DETAILS", 8),
                        ("PANEL_OUTLINES", 2), ("PANEL_LABELS", 7)):
        _layer(doc, name, color)
    msp = doc.modelspace()
    if drawing_type in (ROOM_PLAN, KITCHEN_LAYOUT):
        _room_geometry(msp, project)
        if drawing_type == KITCHEN_LAYOUT:
            _cabinet_footprints(msp, project)
    elif drawing_type == FRONT_ELEVATIONS:
        _front_elevations(msp, project)
    else:
        _panel_outlines(doc, msp, project, cnc_profile)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(destination)
    return destination
