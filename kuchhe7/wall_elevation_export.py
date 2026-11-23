"""Wall-only DXF routed through the established Complete Kitchen elevation builder."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from .complete_kitchen_dxf import _wall_elevations, associate_cabinets_to_walls


def export_wall_elevations_dxf(project, path: str | Path) -> Path:
    project.validate()
    destination = Path(path)
    if destination.suffix.lower() != ".dxf":
        raise ValueError("Wall elevations require a .dxf file.")
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1
    for name in ("SECTION_TITLES", "NOTES", "WALL_TITLES", "WALL_ELEVATIONS",
                 "DIMENSIONS", "WALL_OPENINGS", "WALL_CABINETS", "WALL_FRONT_DETAILS",
                 "WALL_ANNOTATIONS"):
        doc.layers.new(name)
    _wall_elevations(doc.modelspace(), project, associate_cabinets_to_walls(project), -200)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(destination)
    return destination
