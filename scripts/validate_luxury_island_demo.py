"""Validate the saved luxury project and write disposable demo evidence.

Outputs are demonstration drawings and quantities, not factory instructions.
The saved project is read only.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.complete_kitchen_dxf import associate_cabinets_to_walls, export_complete_kitchen_dxf
from kuchhe7.cut_list import export_cut_list_xlsx, generate_cut_list
from kuchhe7.exports import export_bom_xlsx
from kuchhe7.nesting import nest_project
from kuchhe7.nesting_export import export_nesting_layout_dxf
from kuchhe7.nesting_validation import validate_nesting_result
from kuchhe7.persistence import load_project
from kuchhe7.quotation import calculate_quotation
from scripts.create_luxury_island_demo import DEFAULT_OUTPUT


def main() -> None:
    source = DEFAULT_OUTPUT
    output = Path("demo_output/luxury_island/validation")
    output.mkdir(parents=True, exist_ok=True)
    project = load_project(source)
    project.validate()
    original = project.to_dict()
    bare = deepcopy(project)
    bare.placed_products = [item for item in bare.placed_products if not item.item_id.startswith("P")]

    bom = generate_project_bom(project)
    cut_list = generate_cut_list(project)
    layout = nest_project(project)
    validate_nesting_result(layout)
    quote = calculate_quotation(project)
    assert generate_project_bom(bare) == bom
    assert generate_cut_list(bare) == cut_list
    assert nest_project(bare) == layout
    assert calculate_quotation(bare) == quote
    assert layout.eligible_count == layout.placed_count + layout.unplaced_count
    assert layout.unplaced_count == 0

    walls = associate_cabinets_to_walls(project)
    assert all(walls[identity].wall_id is None for identity in ("C9", "C10"))
    assert {row.cabinet_id for row in cut_list} >= {"C9", "C10"}
    island = [item for item in project.cabinets if item.cabinet_id in ("C9", "C10")]
    south_base = [item for item in project.cabinets
                  if item.position_y == 4800 and item.elevation_z == 0]
    south_aisle_mm = min(item.position_y for item in south_base) - max(
        item.position_y + item.footprint_depth for item in island)
    west_base = [item for item in project.cabinets if item.orientation_degrees == 90]
    west_aisle_mm = min(item.position_x for item in island) - max(
        item.position_x + item.footprint_width for item in west_base)
    assert south_aisle_mm == 1200 and west_aisle_mm == 1750

    bom_xlsx = export_bom_xlsx(project, output / "luxury_island_bom.xlsx")
    cut_xlsx = export_cut_list_xlsx(project, output / "luxury_island_cut_list.xlsx")
    complete_dxf = export_complete_kitchen_dxf(project, output / "luxury_island_complete_kitchen.dxf")
    layout_dxf = export_nesting_layout_dxf(layout, output / "luxury_island_sheet_layout_demo.dxf")
    assert load_workbook(bom_xlsx, read_only=True).sheetnames
    assert load_workbook(cut_xlsx, read_only=True).sheetnames
    for path in (complete_dxf, layout_dxf):
        assert ezdxf.readfile(path).header["$INSUNITS"] == 4
    assert project.to_dict() == original

    report = {
        "disclaimer": "Illustrative KÜCHE7 demo; cabinet construction, nesting and costs are not factory approved.",
        "project": project.name,
        "room_mm": [project.room.width, project.room.depth, project.room.height],
        "cabinets": len(project.cabinets),
        "cabinet_ids": [item.cabinet_id for item in project.cabinets],
        "openings": [vars(item) for item in project.room.openings],
        "visual_props": [item.type_id for item in project.placed_products if item.item_id.startswith("P")],
        "appliances": [item.type_id for item in project.placed_products if item.item_id.startswith("A")],
        "island_wall_association": {identity: walls[identity].wall_id for identity in ("C9", "C10")},
        "south_aisle_mm": south_aisle_mm,
        "west_aisle_mm": west_aisle_mm,
        "bom_rows": len(bom),
        "cut_list_rows": len(cut_list),
        "eligible_panels": layout.eligible_count,
        "placed_panels": layout.placed_count,
        "unplaced_panels": layout.unplaced_count,
        "demo_sheets": layout.sheet_count,
        "quotation_unpriced_ids": list(quote.unpriced_ids),
        "quotation_incomplete_reasons": list(quote.incomplete_reasons),
        "props_excluded_from_bom_cut_nesting_quotation": True,
        "export_files": [str(path) for path in (bom_xlsx, cut_xlsx, complete_dxf, layout_dxf)],
    }
    (output / "project_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "cabinets", "south_aisle_mm", "west_aisle_mm", "bom_rows", "cut_list_rows",
        "eligible_panels", "placed_panels", "unplaced_panels", "demo_sheets")}, indent=2))


if __name__ == "__main__":
    main()
