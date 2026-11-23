"""Write Stage 10 synthetic nesting evidence; no client material data is used."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import ezdxf

from kuchhe7.bom import generate_project_bom
from kuchhe7.construction import synthetic_profile_for
from kuchhe7.cut_list import cut_list_summary
from kuchhe7.models import Project
from kuchhe7.nesting import SheetSettings, group_panel_instances, nest_project, project_panel_instances
from kuchhe7.nesting_export import export_nesting_layout_dxf
from kuchhe7.nesting_validation import validate_nesting_result
from kuchhe7.persistence import save_project
from kuchhe7.price_master import PriceMaster, PriceRecord, save_price_master
from kuchhe7.sheet_costing import allocate_project_sheet_cost, approved_sheet_specifications


def write_validation(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    project = Project.complete_kitchen_demo("Stage 10 SYNTHETIC Manufacturing")
    project.quotation.currency = "INR"
    project.quotation.quotation_date = date.today().isoformat()
    for cabinet in project.cabinets:
        cabinet.construction_profile = synthetic_profile_for(cabinet).to_dict()
    project.cabinets[0].construction_profile["grain_directions"] = {"Door": "lengthwise"}
    panels = project_panel_instances(project)
    records = []
    for number, key in enumerate(group_panel_instances(panels), 1):
        material, thickness, finish, _ = key
        records.append(PriceRecord(
            f"SYN-SHEET-{number:02d}", "Board", material,
            "SYNTHETIC TEST SHEET; NOT CLIENT-APPROVED", "sheet", "100",
            "INR", "2026-01-01", "approved", str(thickness), "2440", "1220",
            specification="SYNTHETIC TEST BOARD", finish=finish,
            supplier_reference="SYNTHETIC TEST ONLY", grain_direction="lengthwise"))
    project.price_master = PriceMaster(records)
    settings = SheetSettings(2440, 1220, 3, 10, True, False,
                             clearance_mm=5, trim_left_mm=8, trim_right_mm=6,
                             trim_top_mm=4, trim_bottom_mm=7,
                             min_offcut_length_mm=150, min_offcut_width_mm=100)
    specs, _ = approved_sheet_specifications(project.price_master, panels,
                                              date.today().isoformat(), "INR")
    start = perf_counter()
    previous = nest_project(project, settings, strategy="shelf",
                            sheet_specs=specs, require_sheet_specs=True)
    previous_seconds = perf_counter() - start
    validate_nesting_result(previous)
    start = perf_counter()
    allocation = allocate_project_sheet_cost(project, settings,
                                             as_of=date.today().isoformat(), currency="INR")
    optimized_seconds = perf_counter() - start
    result = allocation.layout
    validate_nesting_result(result)
    if result.unplaced_count or result.eligible_count != 65:
        raise ValueError("Synthetic Stage 8 panel reconciliation failed.")
    if sum((line.amount for line in allocation.allocations), Decimal("0.00")) != allocation.total:
        raise ValueError("Shared sheet price allocation failed.")
    drawing_path = export_nesting_layout_dxf(result, output / "SYNTHETIC_sheet_layouts.dxf")
    drawing = ezdxf.readfile(drawing_path)
    outlines = [item for item in drawing.modelspace() if item.dxf.layer == "PANEL_OUTLINES"]
    if len(outlines) != result.placed_count or drawing.header["$INSUNITS"] != 4:
        raise ValueError("Sheet DXF readback differs from the validated layout.")
    save_project(project, output / "SYNTHETIC_project.json")
    save_price_master(project.price_master, output / "SYNTHETIC_sheet_price_master.json")
    manifest = []
    sheets = []
    for group in result.groups:
        spec = group.sheet_specification
        for sheet in group.sheets:
            placements = []
            for placed in sheet.placements:
                panel = placed.panel
                row = {"instance_id": panel.instance_id, "part_id": panel.part_id,
                       "cabinet_id": panel.cabinet_id, "wall_id": panel.wall_id,
                       "component": panel.component_name, "material": panel.material,
                       "finish": panel.finish, "thickness_mm": panel.thickness_mm,
                       "profile_id": panel.profile_id, "profile_revision": panel.profile_revision,
                       "sheet_id": spec.sheet_id, "sheet_number": sheet.sheet_number,
                       "x_mm": placed.x_mm, "y_mm": placed.y_mm,
                       "cut_length_mm": panel.length_mm, "cut_width_mm": panel.width_mm,
                       "placed_length_mm": placed.placed_length_mm,
                       "placed_width_mm": placed.placed_width_mm,
                       "rotated": placed.rotated, "grain_direction": panel.grain_direction}
                manifest.append(row)
                placements.append(row)
            sheets.append({"sheet_id": spec.sheet_id, "sheet_number": sheet.sheet_number,
                           "material": group.material, "finish": group.finish,
                           "thickness_mm": group.thickness_mm,
                           "purchased_length_mm": spec.length_mm,
                           "purchased_width_mm": spec.width_mm,
                           "placed_area_mm2": sheet.placed_area_mm2,
                           "purchased_utilization_percent":
                               100 * sheet.placed_area_mm2 / (spec.length_mm * spec.width_mm),
                           "placements": placements,
                           "candidate_offcuts": [asdict(item) for item in result.reusable_offcuts
                                                 if item.sheet_id == spec.sheet_id
                                                 and item.sheet_number == sheet.sheet_number]})
    summary = cut_list_summary(project)
    report = {"warning": "SYNTHETIC DEMONSTRATION LAYOUT ONLY; NOT APPROVED FOR FACTORY OR CNC USE",
              "bom_rows": len(generate_project_bom(project)),
              "panel_instances": summary["panel_quantity"],
              "hardware_units": summary["hardware_quantity"],
              "required_panels": result.eligible_count, "placed_panels": result.placed_count,
              "unplaced_panels": result.unplaced_count,
              "material_groups": len(result.groups), "sheets": result.sheet_count,
              "theoretical_minimum_sheets": result.theoretical_minimum_sheets,
              "purchased_area_mm2": result.purchased_area_mm2,
              "usable_area_mm2": result.usable_area_mm2,
              "placed_area_mm2": result.placed_area_mm2,
              "trim_and_margin_area_mm2": result.trim_and_margin_area_mm2,
              "usable_residual_area_mm2": result.usable_residual_area_mm2,
              "candidate_reusable_offcuts": len(result.reusable_offcuts),
              "candidate_offcut_area_mm2": result.reusable_offcut_area_mm2,
              "purchased_sheet_utilization_percent": result.utilization_percent,
              "usable_area_utilization_percent": result.usable_utilization_percent,
              "old_shelf_sheets": previous.sheet_count,
              "old_shelf_utilization_percent": previous.utilization_percent,
              "old_shelf_seconds": previous_seconds,
              "new_auto_seconds": optimized_seconds,
              "selected_strategy": result.strategy,
              "synthetic_sheet_cost_inr": str(allocation.total),
              "allocated_cost_inr": str(sum((line.amount for line in allocation.allocations),
                                            Decimal("0.00"))),
              "settings": asdict(settings)}
    for name, content in (("SYNTHETIC_summary.json", report),
                          ("SYNTHETIC_panel_manifest.json", manifest),
                          ("SYNTHETIC_sheets.json", sheets),
                          ("SYNTHETIC_cost_allocations.json",
                           [dict(asdict(line), amount=str(line.amount)) for line in allocation.allocations])):
        (output / name).write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    target = Path("demo_output/stage10_nesting/validation")
    result = write_validation(target)
    print(json.dumps({key: result[key] for key in
                      ("bom_rows", "panel_instances", "hardware_units", "material_groups",
                       "sheets", "unplaced_panels", "synthetic_sheet_cost_inr")}, indent=2))
