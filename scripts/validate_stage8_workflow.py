"""Reproducible Stage 8 workflow using SYNTHETIC rates, never client prices."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.costing import cost_cabinet
from kuchhe7.document_exports import (
    export_bom_pdf, export_bom_template_xlsx, export_issued_quotation_pdf,
    export_issued_quotation_xlsx, export_quotation_pdf, export_quotation_xlsx,
)
from kuchhe7.engineering_dxf import FRONT_ELEVATIONS, PANEL_OUTLINES, export_engineering_dxf
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.price_master import CataloguePriceRule, PriceRecord
from kuchhe7.pricing_refresh import apply_company_price_refresh, preview_company_price_refresh
from kuchhe7.pricing_setup import apply_company_setup_to_new_project
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation, issue_quotation_snapshot
from tests.test_stage7b3_catalogue_pricing import synthetic_setup


def _panel_dxf_sizes(path: Path) -> list[tuple[float, float]]:
    outlines = ezdxf.readfile(path).modelspace().query('LWPOLYLINE[layer=="PANEL_OUTLINES"]')
    sizes = []
    for outline in outlines:
        points = list(outline.get_points("xy"))
        sizes.append((round(max(x for x, _ in points) - min(x for x, _ in points), 5),
                      round(max(y for _, y in points) - min(y for _, y in points), 5)))
    return sorted(sizes)


def _quotation_excel_total(path: Path) -> float:
    sheet = load_workbook(path, data_only=True).active
    matches = [row[5].value for row in sheet.iter_rows() if row[4].value == "Total"]
    assert len(matches) == 1
    return float(matches[0])


def build_synthetic_project() -> tuple[Project, object]:
    """Three cabinet types with complete example prices, without manual unit prices."""
    company = synthetic_setup()
    company.records.extend([
        PriceRecord("SYN-DRAWER-12", "Board", "Drawer board", "Synthetic drawer board", "m2",
                    "90", "INR", "2026-01-01", "approved", "12", specification="SYNTHETIC drawer board"),
        PriceRecord("SYN-DRAWER-6", "Board", "Drawer board", "Synthetic drawer bottom", "m2",
                    "70", "INR", "2026-01-01", "approved", "6", specification="SYNTHETIC drawer bottom"),
        PriceRecord("SYN-RUNNER", "Hardware", "Drawer runner pair", "Synthetic runner pair", "each",
                    "15", "INR", "2026-01-01", "approved"),
    ])
    company.catalogue_rules.extend([
        CataloguePriceRule("SYN-WALL-RULE", "wall_2_door", "calculated", "INR", "2026-01-01",
                           "approved", "Warm White", markup_percent="20"),
        CataloguePriceRule("SYN-DRAWER-RULE", "base_3_drawer", "calculated", "INR", "2026-01-01",
                           "approved", "Warm White", markup_percent="20"),
    ])
    company.validate()
    project = Project.empty("SYNTHETIC Stage 8 workflow")
    apply_company_setup_to_new_project(project, company)
    project.quotation.customer_name = "SYNTHETIC customer"
    project.quotation.quotation_number = "SYN-STAGE8-001"
    project.quotation.quotation_date = "2026-11-19"
    project.quotation.discount_percent = "10"
    project.quotation.tax_percent = "5"
    c1 = create_catalogue_cabinet("base_2_door", "C1", position_x=650, position_y=2500)
    c1.material = "Cashmere"
    project.add_cabinet(c1)
    c2 = create_catalogue_cabinet("wall_2_door", "C2", position_x=650, position_y=2850)
    c2.material = "Warm White"
    project.add_cabinet(c2)
    c3 = create_catalogue_cabinet("base_3_drawer", "C3", position_x=1800, position_y=2500)
    project.add_cabinet(c3)
    return project, company


def validate_workflow(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    project, company = build_synthetic_project()
    bom = generate_project_bom(project)
    draft = calculate_quotation(project)
    assert not draft.unpriced_ids and not draft.incomplete_reasons
    assert not project.quotation.unit_prices
    costs = {cabinet.cabinet_id: cost_cabinet(
        cabinet, project.price_master, currency="INR", as_of="2026-11-19")
        for cabinet in project.cabinets}
    initial_cabinets = [deepcopy(cabinet) for cabinet in project.cabinets]
    assert all(cost.status == "COMPLETE" for cost in costs.values())
    nesting = nest_project(project)
    assert nesting.eligible_count == nesting.placed_count + nesting.unplaced_count
    assert nesting.unplaced_count == 0

    export_bom_template_xlsx(project, output_dir / "synthetic-bom.xlsx")
    export_bom_pdf(project, output_dir / "synthetic-bom.pdf")
    export_quotation_xlsx(project, output_dir / "synthetic-draft-quotation.xlsx")
    export_quotation_pdf(project, output_dir / "synthetic-draft-quotation.pdf")
    export_engineering_dxf(project, output_dir / "synthetic-front-elevations.dxf", FRONT_ELEVATIONS)
    export_engineering_dxf(project, output_dir / "synthetic-panel-outlines.dxf", PANEL_OUTLINES)
    assert ezdxf.readfile(output_dir / "synthetic-front-elevations.dxf").header["$INSUNITS"] == 4
    assert ezdxf.readfile(output_dir / "synthetic-panel-outlines.dxf").header["$INSUNITS"] == 4
    assert _panel_dxf_sizes(output_dir / "synthetic-panel-outlines.dxf") == sorted(
        (round(panel.length_mm, 5), round(panel.width_mm, 5)) for panel in nesting.eligible_panels)
    draft_sheet = load_workbook(output_dir / "synthetic-draft-quotation.xlsx", data_only=True).active
    assert draft_sheet["F6"].value == float(draft.lines[0].unit_price)
    assert _quotation_excel_total(output_dir / "synthetic-draft-quotation.xlsx") == float(draft.total)
    assert b"DRAFT CUSTOMER QUOTATION" in (output_dir / "synthetic-draft-quotation.pdf").read_bytes()

    oven = get_product("oven_freestanding")
    project.add_product(PlacedProduct("A1", oven.type_id, 100, 100, oven.elevation_z,
                                      oven.width, oven.depth, oven.height))
    project.quotation.billable_product_ids = ["A1"]
    oven_quote = calculate_quotation(project)
    assert any(line.item_id == "A1" and line.pricing_mode == "master" for line in oven_quote.lines)
    prop = get_product("plant_pot")
    project.add_product(PlacedProduct("P1", prop.type_id, 100, 1000, prop.elevation_z,
                                      prop.width, prop.depth, prop.height))
    assert calculate_quotation(project) == oven_quote
    assert generate_project_bom(project) == bom
    assert nest_project(project).eligible_count == nesting.eligible_count
    issued = deepcopy(issue_quotation_snapshot(project))
    export_issued_quotation_xlsx(project, output_dir / "synthetic-issued-quotation.xlsx")
    export_issued_quotation_pdf(project, output_dir / "synthetic-issued-quotation.pdf")
    assert _quotation_excel_total(output_dir / "synthetic-issued-quotation.xlsx") == float(issued["total"])
    assert b"ISSUED QUOTATION" in (output_dir / "synthetic-issued-quotation.pdf").read_bytes()

    c1 = project.cabinets[0]
    changes = []
    for field, value in (("width", 1000), ("height", 770), ("depth", 650), ("material", "Warm White")):
        before = calculate_quotation(project).total
        setattr(c1, field, value)
        project.validate()
        after = calculate_quotation(project).total
        assert after != before
        changes.append({"field": field, "value": value, "draft_before": str(before), "draft_after": str(after)})
        assert project.quotation.issued_snapshot == issued
    assert nest_project(project).total_panel_area_mm2 != nesting.total_panel_area_mm2
    current_nesting = nest_project(project)
    export_bom_template_xlsx(project, output_dir / "synthetic-updated-bom.xlsx")
    export_engineering_dxf(project, output_dir / "synthetic-updated-panel-outlines.dxf", PANEL_OUTLINES)
    assert _panel_dxf_sizes(output_dir / "synthetic-updated-panel-outlines.dxf") == sorted(
        (round(panel.length_mm, 5), round(panel.width_mm, 5)) for panel in current_nesting.eligible_panels)
    assert _panel_dxf_sizes(output_dir / "synthetic-updated-panel-outlines.dxf") != _panel_dxf_sizes(
        output_dir / "synthetic-panel-outlines.dxf")

    before_refresh = calculate_quotation(project).total
    updated_company = deepcopy(company)
    white_rate = next(row for row in updated_company.records if row.record_id == "SYN-WHITE-18")
    white_rate.rate = "200"
    white_rate.effective_date = "2026-11-19"
    preview = preview_company_price_refresh(project, updated_company)
    assert calculate_quotation(project).total == before_refresh
    apply_company_price_refresh(project, preview)
    after_refresh = calculate_quotation(project).total
    assert after_refresh != before_refresh
    assert project.quotation.issued_snapshot == issued

    save_project(project, output_dir / "synthetic-project.json")
    reopened = load_project(output_dir / "synthetic-project.json")
    assert reopened.to_dict() == project.to_dict()
    assert calculate_quotation(reopened) == calculate_quotation(project)
    assert reopened.quotation.issued_snapshot == issued
    report = {
        "notice": "SYNTHETIC demonstration rates and illustrative engineering only; no client approval.",
        "cabinets": [{"id": c.cabinet_id, "type": c.cabinet_type_id,
                      "dimensions_mm": [c.width, c.height, c.depth], "finish": c.material,
                      "bom_rows": sum(row.cabinet_id == c.cabinet_id for row in bom),
                      "cost": str(costs[c.cabinet_id].total),
                      "selling_price": str(next(line.unit_price for line in draft.lines if line.item_id == c.cabinet_id))}
                     for c in initial_cabinets],
        "initial_draft_total": str(draft.total),
        "issued_total": issued["total"],
        "after_appliance_total": str(oven_quote.total),
        "dimension_and_finish_changes": changes,
        "before_price_refresh": str(before_refresh),
        "after_price_refresh": str(after_refresh),
        "price_revision": project.pricing_revision,
        "nesting": {"eligible": nesting.eligible_count, "placed": nesting.placed_count,
                    "unplaced": nesting.unplaced_count, "sheets": nesting.sheet_count,
                    "utilization_percent": round(nesting.utilization_percent, 2)},
    }
    (output_dir / "validation-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo_output/stage8-synthetic")
    print(json.dumps(validate_workflow(target), indent=2))
