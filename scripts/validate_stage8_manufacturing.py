"""Build Stage 8 synthetic validation artifacts without changing client projects."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import ezdxf

from kuchhe7.bom import generate_project_bom
from kuchhe7.complete_kitchen_dxf import export_complete_kitchen_dxf
from kuchhe7.construction import synthetic_profile_for
from kuchhe7.cut_list import cut_list_summary, export_cut_list_xlsx, generate_cut_list
from kuchhe7.document_exports import export_bom_pdf
from kuchhe7.engineering_dxf import PANEL_OUTLINES, export_engineering_dxf
from kuchhe7.exports import export_bom_xlsx
from kuchhe7.models import Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import save_project


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    project = Project.complete_kitchen_demo("Stage 8 Synthetic Construction Validation")
    for cabinet in project.cabinets:
        cabinet.construction_profile = synthetic_profile_for(cabinet).to_dict()
    # Explicit test-only banding and grain. No values are attributed to the client.
    project.cabinets[0].construction_profile["edge_banding"] = {
        "Door": [{"edge": "front", "material": "Synthetic ABS", "thickness_mm": 1,
                  "width_mm": 22}]
    }
    project.cabinets[0].construction_profile["grain_directions"] = {"Door": "lengthwise"}
    project.cabinets[0].construction_profile["compensate_cut_for_banding"] = True
    bom = generate_project_bom(project)
    rows = generate_cut_list(project)
    summary = cut_list_summary(project)
    nested = nest_project(project)
    export_bom_xlsx(project, output / "stage8-synthetic-bom.xlsx")
    export_bom_pdf(project, output / "stage8-synthetic-bom.pdf")
    export_cut_list_xlsx(project, output / "stage8-synthetic-cut-list.xlsx")
    export_engineering_dxf(project, output / "stage8-synthetic-panel-outlines.dxf", PANEL_OUTLINES)
    export_complete_kitchen_dxf(project, output / "stage8-synthetic-complete-kitchen.dxf")
    save_project(project, output / "stage8-synthetic-six-cabinet.json")
    (output / "stage8-synthetic-base-profile.json").write_text(
        json.dumps(project.cabinets[0].construction_profile, indent=2), encoding="utf-8"
    )
    with (output / "stage8-synthetic-cut-list.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Project", "Wall", "Cabinet", "Part ID", "Part", "Material", "Finish",
                         "Finished L mm", "Finished W mm", "Cut L mm", "Cut W mm", "T mm",
                         "Qty", "Grain", "Edge banding", "Profile", "Revision", "Status"])
        for row in rows:
            writer.writerow([row.project_name, row.wall_id or "UNASSIGNED", row.cabinet_id,
                             row.part_id, row.part_name, row.material, row.finish,
                             row.finished_length_mm, row.finished_width_mm,
                             row.cut_length_mm, row.cut_width_mm, row.thickness_mm,
                             row.quantity, row.grain_direction,
                             "; ".join(f"{rule.edge}:{rule.material}:{rule.thickness_mm:g}x{rule.width_mm:g}"
                                       for rule in row.edge_banding),
                             row.profile_id, row.profile_revision, row.manufacturing_status])
    outlines = ezdxf.readfile(output / "stage8-synthetic-panel-outlines.dxf")
    complete = ezdxf.readfile(output / "stage8-synthetic-complete-kitchen.dxf")
    panel_count = summary["panel_quantity"]
    report = {
        "status": "SYNTHETIC VALIDATION ONLY / NOT FACTORY APPROVED",
        "project": project.name,
        "cabinet_types": [cabinet.cabinet_type_id for cabinet in project.cabinets],
        "bom_rows": len(bom),
        "cut_list_rows": len(rows),
        "panel_quantity": panel_count,
        "nesting_eligible_count": nested.eligible_count,
        "nesting_placed_count": nested.placed_count,
        "nesting_unplaced_count": nested.unplaced_count,
        "engineering_dxf_contours": len(outlines.modelspace().query('LWPOLYLINE[layer=="PANEL_OUTLINES"]')),
        "complete_dxf_contours": len(complete.modelspace().query('LWPOLYLINE[layer=="CNC_CUT_OUTER"]')),
        "summary": {**summary, "edge_banding_mm": [
            {"material": material, "thickness_mm": thickness, "width_mm": width, "total_mm": total}
            for (material, thickness, width), total in summary["edge_banding_mm"].items()]},
        "expected_vs_actual": {
            "C1 top length mm": {"expected": 764, "actual": next(c.length_mm for c in bom if c.cabinet_id == "C1" and c.name == "Top panel")},
            "C1 door cut width mm": {"expected": 396, "actual": next(c.cut_width_mm for c in bom if c.cabinet_id == "C1" and c.name == "Door")},
            "C1 door banding total mm": {"expected": 1432, "actual": summary["edge_banding_mm"][("Synthetic ABS", 1, 22)]},
            "panels": {"expected": 65, "actual": panel_count},
        },
    }
    assert panel_count == nested.eligible_count == report["engineering_dxf_contours"] == report["complete_dxf_contours"]
    assert all(item["expected"] == item["actual"] for item in report["expected_vs_actual"].values())
    (output / "stage8-validation-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo_output/stage8_manufacturing")
    result = run(destination)
    print(json.dumps({key: result[key] for key in ("bom_rows", "panel_quantity", "nesting_eligible_count",
                                                  "engineering_dxf_contours", "complete_dxf_contours")}, indent=2))
