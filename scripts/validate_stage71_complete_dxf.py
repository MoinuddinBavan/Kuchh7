"""Generate and read back the single Stage 7.1 synthetic kitchen DXF."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import ezdxf

from kuchhe7.bom import generate_project_bom
from kuchhe7.complete_kitchen_dxf import associate_cabinets_to_walls, export_complete_kitchen_dxf
from kuchhe7.models import Project
from kuchhe7.nesting import expand_panel_instances
from kuchhe7.persistence import load_project, save_project
from scripts.validate_stage7_bom_cad import raw_dxf_pairs, raw_entities, raw_insunits


ROOT = Path(__file__).resolve().parents[1]


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    sample = Project.complete_kitchen_demo("Stage 7.1 Synthetic Complete Kitchen")
    saved = save_project(sample, output / "synthetic-project.json")
    project = load_project(saved)
    before = project.to_dict()
    drawing_path = export_complete_kitchen_dxf(project, output / "KUCHE7_COMPLETE_KITCHEN.dxf")
    assert project.to_dict() == before
    doc = ezdxf.readfile(drawing_path)
    audit = doc.audit()
    pairs = raw_dxf_pairs(drawing_path)
    raw = raw_entities(pairs)
    assert doc.header["$INSUNITS"] == raw_insunits(pairs) == 4
    assert doc.units == ezdxf.units.MM and not audit.has_errors

    def entities(layer: str, kind: str | None = None):
        return [item for item in doc.modelspace()
                if item.dxf.layer == layer and (kind is None or item.dxftype() == kind)]

    assert len(entities("CABINET_FOOTPRINTS", "LWPOLYLINE")) == len(project.cabinets) == 6
    assert len(entities("WALL_ELEVATIONS", "LWPOLYLINE")) == len(project.room.walls) == 4
    assert len(entities("WALL_OPENINGS", "LWPOLYLINE")) == len(project.room.openings) == 2
    assert len(entities("WALL_CABINETS", "LWPOLYLINE")) == len(project.cabinets)
    for wall, outline in zip(project.room.walls, entities("WALL_ELEVATIONS", "LWPOLYLINE")):
        points = list(outline.get_points("xy"))
        expected_length = project.room.width if wall.wall_id in ("NORTH", "SOUTH") else project.room.depth
        assert abs(points[1][0] - points[0][0] - expected_length) < 1e-7
        assert abs(points[2][1] - points[1][1] - project.room.height) < 1e-7
    wall_bases = {wall.wall_id: list(outline.get_points("xy"))[0][1]
                  for wall, outline in zip(project.room.walls,
                                           entities("WALL_ELEVATIONS", "LWPOLYLINE"))}
    opening_outlines = entities("WALL_OPENINGS", "LWPOLYLINE")
    for opening, outline in zip(project.room.openings, opening_outlines):
        points = list(outline.get_points("xy"))
        assert points[0] == (opening.offset, wall_bases[opening.wall_id] + opening.elevation)
        assert points[1][0] - points[0][0] == opening.width
        assert points[2][1] - points[1][1] == opening.height
    for cabinet, outline in zip(project.cabinets, entities("CABINET_FOOTPRINTS", "LWPOLYLINE")):
        points = list(outline.get_points("xy"))
        assert points[0] == (cabinet.position_x,
                             project.room.depth - cabinet.position_y - cabinet.footprint_depth)
        assert points[1][0] - points[0][0] == cabinet.footprint_width
        assert points[2][1] - points[1][1] == cabinet.footprint_depth

    bom = generate_project_bom(project)
    ids = [item.dxf.text for item in entities("BOM_ROWS", "TEXT")
           if item.dxf.text.startswith(tuple(cabinet.cabinet_id + "-P" for cabinet in project.cabinets))]
    assert len(bom) == 48 and len(ids) == 96
    assert set(Counter(ids).values()) == {2}
    panels = entities("CNC_CUT_OUTER", "LWPOLYLINE")
    expected_panels = expand_panel_instances(bom)
    assert len(panels) == len(expected_panels) == 66
    assert all(item.closed for item in panels)
    for outline, expected in zip(panels, expected_panels):
        points = list(outline.get_points("xy"))
        assert abs(points[1][0] - points[0][0] - expected.length_mm) < 1e-7
        assert abs(points[2][1] - points[1][1] - expected.width_mm) < 1e-7
    cad_panel_area_m2 = sum(
        (points[1][0] - points[0][0]) * (points[2][1] - points[1][1]) / 1_000_000
        for outline in panels for points in [list(outline.get_points("xy"))]
    )
    bom_panel_area_m2 = sum(item.length_mm * item.width_mm * item.quantity / 1_000_000
                           for item in bom if min(item.length_mm, item.width_mm,
                                                  item.thickness_mm) > 0)
    assert abs(cad_panel_area_m2 - bom_panel_area_m2) < 1e-7
    assert not entities("CNC_CUT_OUTER", "TEXT")
    raw_contours = [entity for entity in raw if entity[0] == "LWPOLYLINE"
                    and (8, "CNC_CUT_OUTER") in entity[1]]
    assert len(raw_contours) == len(panels)
    assert not any((8, layer) in entity[1] for entity in raw
                   for layer in ("CNC_DRILL", "CNC_POCKET", "CNC_ROUTE"))

    assignments = associate_cabinets_to_walls(project)
    assert all(item.wall_id == "SOUTH" for item in assignments.values())
    result = {
        "status": "PASS - SYNTHETIC DEMONSTRATION ONLY",
        "drawing": str(drawing_path.resolve()),
        "format": "DXF R2010; not DWG",
        "units": "mm (INSUNITS=4)",
        "project_unchanged": True,
        "room_mm": [project.room.width, project.room.depth, project.room.height],
        "walls": [wall.wall_id for wall in project.room.walls],
        "openings": [opening.opening_id for opening in project.room.openings],
        "wall_associations": {key: value.wall_id for key, value in assignments.items()},
        "cabinet_footprints": len(project.cabinets),
        "wall_elevations": len(entities("WALL_ELEVATIONS", "LWPOLYLINE")),
        "bom_rows": len(bom),
        "complete_bom_row_ids": len(ids) // 2,
        "wallwise_bom_row_ids": len(ids) // 2,
        "panel_contours": len(panels),
        "hardware_units": sum(item.quantity for item in bom if item.material == "Hardware"),
        "panel_area_m2": round(bom_panel_area_m2, 3),
        "cad_contour_area_m2": round(cad_panel_area_m2, 3),
        "raw_dxf_contour_count": len(raw_contours),
        "dxf_audit_errors": len(audit.errors),
        "drilling_pocket_route_entities": 0,
        "dwg": "PENDING - no permitted, installed converter and independent DWG reader",
        "specific_cnc_machine_compatibility": "NOT VALIDATED",
    }
    (output / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo_output" / "stage71"
    print(json.dumps(run(target), indent=2))
