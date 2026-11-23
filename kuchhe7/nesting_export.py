"""Separate 1:1 DXF of a validated demonstration sheet layout.

This contains panel rectangles and annotation, never toolpaths or machine cuts.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf

from .nesting import NestingResult
from .nesting_validation import validate_nesting_result


def export_nesting_layout_dxf(result: NestingResult, path: str | Path) -> Path:
    validate_nesting_result(result)
    if result.unplaced_count:
        raise ValueError("Layout incomplete; resolve unplaced panels before exporting a sheet drawing.")
    destination = Path(path)
    drawing = ezdxf.new("R2010")
    drawing.units = ezdxf.units.MM
    drawing.header["$INSUNITS"] = 4
    drawing.header["$MEASUREMENT"] = 1
    for layer, colour in (("SHEET_BOUNDARY", 7), ("USABLE_BOUNDARY", 8),
                          ("PANEL_OUTLINES", 3), ("PART_LABELS", 2),
                          ("GRAIN_ANNOTATION", 4), ("LAYOUT_NOTES", 1)):
        drawing.layers.new(layer, dxfattribs={"color": colour})
    space = drawing.modelspace()
    cursor_x = 0.0
    for group in result.groups:
        spec = group.sheet_specification
        if spec is None:
            continue
        for sheet in group.sheets:
            ox = cursor_x
            length, width = spec.length_mm, spec.width_mm
            space.add_lwpolyline([(ox, 0), (ox + length, 0),
                                  (ox + length, width), (ox, width)], close=True,
                                 dxfattribs={"layer": "SHEET_BOUNDARY"})
            left = result.settings.margin_mm + result.settings.trim_left_mm
            top = result.settings.margin_mm + result.settings.trim_top_mm
            right = length - result.settings.margin_mm - result.settings.trim_right_mm
            bottom = width - result.settings.margin_mm - result.settings.trim_bottom_mm
            space.add_lwpolyline([(ox + left, top), (ox + right, top),
                                  (ox + right, bottom), (ox + left, bottom)], close=True,
                                 dxfattribs={"layer": "USABLE_BOUNDARY"})
            header = (f"DEMONSTRATION ONLY | {spec.sheet_id} | {group.material} "
                      f"{group.finish} {group.thickness_mm:g}mm | sheet {sheet.sheet_number}")
            space.add_text(header, height=28, dxfattribs={"layer": "LAYOUT_NOTES",
                                                          "insert": (ox, -50)})
            for placement in sheet.placements:
                x = ox + placement.x_mm
                y = placement.y_mm
                x2 = x + placement.placed_length_mm
                y2 = y + placement.placed_width_mm
                space.add_lwpolyline([(x, y), (x2, y), (x2, y2), (x, y2)],
                                     close=True, dxfattribs={"layer": "PANEL_OUTLINES"})
                panel = placement.panel
                label = (f"{panel.instance_id} {panel.cabinet_id} {panel.component_name} "
                         f"{panel.length_mm:g}x{panel.width_mm:g}mm"
                         f"{' ROT90' if placement.rotated else ''}")
                space.add_text(label, height=16, dxfattribs={"layer": "PART_LABELS",
                                                            "insert": (x + 5, y + 24)})
                if panel.grain_direction in ("lengthwise", "widthwise"):
                    note = f"GRAIN {panel.grain_direction.upper()}"
                    space.add_text(note, height=14,
                                   dxfattribs={"layer": "GRAIN_ANNOTATION",
                                               "insert": (x + 5, y + 44)})
            cursor_x += length + 150
    destination.parent.mkdir(parents=True, exist_ok=True)
    drawing.saveas(destination)
    return destination
