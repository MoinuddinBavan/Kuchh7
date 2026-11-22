"""Independent synthetic price oracle; no values are client-approved rates."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet, register_custom_items
from kuchhe7.construction import synthetic_profile_for
from kuchhe7.costing import PricingRule, cost_cabinet, selling_price
from kuchhe7.custom_catalogue import create_custom_revision
from kuchhe7.document_exports import (export_issued_quotation_pdf, export_issued_quotation_xlsx,
                                       export_quotation_pdf, export_quotation_xlsx)
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.price_master import CataloguePriceRule, PriceMaster, PriceRecord
from kuchhe7.pricing_refresh import master_revision
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation, get_issued_quotation_snapshot, issue_quotation_snapshot


DATE = "2026-01-01"
AS_OF = "2026-11-22"
# Frozen expectations calculated separately from the Stage 8 synthetic cut-list
# rectangles with Decimal line rounding; no production costing code is called.
EXPECTED_COST = {"C1": "460.03", "C2": "521.13", "C3": "374.23",
                 "C4": "375.72", "C5": "263.10", "C6": "979.69"}
EXPECTED_SALE = {"C1": "552.04", "C2": "625.36", "C3": "449.08",
                 "C4": "450.86", "C5": "315.72", "C6": "1175.63"}


def _record(record_id, category, key, unit, rate, thickness="", **extra):
    return PriceRecord(record_id, category, key, "SYNTHETIC TEST RATE", unit,
                       rate, "INR", DATE, "approved", thickness,
                       specification="SYNTHETIC TEST MATERIAL" if category == "Board" else "",
                       **extra)


def synthetic_master(with_sheets=False):
    boards = [
        ("CASH18", "Cashmere", "18", "100"), ("CASH6", "Cashmere", "6", "80"),
        ("WHITE18", "Warm White", "18", "110"), ("WHITE6", "Warm White", "6", "90"),
        ("WALNUT18", "Walnut", "18", "120"), ("WALNUT6", "Walnut", "6", "95"),
        ("DRAWER12", "Drawer board", "12", "60"), ("DRAWER6", "Drawer board", "6", "50"),
    ]
    records = [_record("SYN-" + key, "Board", material, "m2", rate, thickness)
               for key, material, thickness, rate in boards]
    records.extend([
        _record("SYN-HINGE", "Hardware", "Concealed hinge", "each", "10"),
        _record("SYN-RUNNER", "Hardware", "Drawer runner pair", "each", "20"),
        _record("SYN-EDGE", "Edge banding", "Synthetic ABS", "m", "5", "1",
                band_width_mm="22"),
        _record("SYN-ASSEMBLY", "Labour", "assembly", "each", "50"),
    ])
    if with_sheets:
        records.extend([
            _record("SYN-SHEET18", "Board", "Cashmere", "sheet", "200", "18",
                    sheet_length_mm="2440", sheet_width_mm="1220"),
            _record("SYN-SHEET6", "Board", "Cashmere", "sheet", "150", "6",
                    sheet_length_mm="2440", sheet_width_mm="1220"),
        ])
    return PriceMaster(records)


def profiled_project():
    project = Project.complete_kitchen_demo("Stage 9 Synthetic Pricing")
    project.quotation.currency = "INR"
    project.quotation.quotation_date = AS_OF
    project.quotation.customer_name = "Synthetic test customer"
    project.quotation.quotation_number = "SYN-STAGE9"
    for cabinet in project.cabinets:
        cabinet.construction_profile = synthetic_profile_for(cabinet).to_dict()
    project.cabinets[0].construction_profile["edge_banding"] = {
        "Door": [{"edge": "front", "material": "Synthetic ABS", "thickness_mm": 1,
                  "width_mm": 22}]
    }
    project.cabinets[0].construction_profile["grain_directions"] = {"Door": "lengthwise"}
    project.cabinets[0].construction_profile["compensate_cut_for_banding"] = True
    master = synthetic_master()
    master.catalogue_rules = [CataloguePriceRule(
        f"SYN-RULE-{cabinet.cabinet_id}", cabinet.cabinet_type_id, "calculated", "INR", DATE,
        status="approved", markup_percent="20", charge_quantities={"SYN-ASSEMBLY": "1"},
        overhead_percent="10",
    ) for cabinet in project.cabinets]
    project.price_master = master
    project.pricing_revision = {"source": "synthetic", "revision": master_revision(master)}
    return project


def test_six_cabinet_cost_and_selling_prices_match_independent_static_oracle():
    project = profiled_project()
    assert len(generate_project_bom(project)) == 47
    for cabinet in project.cabinets:
        rule = PricingRule(mode="calculated", approved=True, markup_percent="20",
                           overhead_percent="10")
        cost = cost_cabinet(cabinet, project.price_master,
                            charge_quantities={"SYN-ASSEMBLY": "1"},
                            currency="INR", as_of=AS_OF, policy=rule)
        assert cost.status == "COMPLETE", (cabinet.cabinet_id, cost.missing)
        assert cost.total == Decimal(EXPECTED_COST[cabinet.cabinet_id])
        assert selling_price(cost, rule, currency="INR")[0] == Decimal(EXPECTED_SALE[cabinet.cabinet_id])
        assert cost.profile_revision == "1.0-synthetic"
        assert cost.price_master_revision == master_revision(project.price_master)
        assert all(line.source_part_ids for line in cost.lines if line.cost_category in ("Board", "Hardware", "Edge banding"))
    quote = calculate_quotation(project)
    assert {line.item_id: line.unit_price for line in quote.lines if line.category == "Furniture"} == {
        key: Decimal(value) for key, value in EXPECTED_SALE.items()}
    assert quote.subtotal == Decimal("3568.69")
    assert not quote.unpriced_ids and not quote.incomplete_reasons


def test_edge_rate_match_zero_rate_and_missing_rate_are_distinct():
    project = profiled_project()
    cabinet = project.cabinets[0]
    policy = PricingRule(mode="calculated", approved=True, markup_percent="20")
    full = cost_cabinet(cabinet, project.price_master, currency="INR", as_of=AS_OF, policy=policy)
    assert next(line for line in full.lines if line.cost_category == "Edge banding").quantity == Decimal("1.432")
    project.price_master.records = [r for r in project.price_master.records if r.record_id != "SYN-EDGE"]
    missing = cost_cabinet(cabinet, project.price_master, currency="INR", as_of=AS_OF, policy=policy)
    assert missing.total is None and any("edge rate missing" in reason for reason in missing.missing)
    project.price_master.records.append(_record("SYN-EDGE-ZERO", "Edge banding", "Synthetic ABS",
                                                "m", "0", "1", band_width_mm="22"))
    zero = cost_cabinet(cabinet, project.price_master, currency="INR", as_of=AS_OF, policy=policy)
    assert zero.status == "COMPLETE"
    assert any(line.cost_category == "Edge banding" and line.amount == Decimal("0.00") for line in zero.lines)


def test_finished_cut_sheet_yield_and_nesting_bases_are_explicit():
    project = profiled_project()
    cabinet = project.cabinets[0]
    master = synthetic_master(with_sheets=True)
    finished = cost_cabinet(cabinet, master, currency="INR", as_of=AS_OF)
    cut = cost_cabinet(cabinet, master, currency="INR", as_of=AS_OF,
                       policy=PricingRule(cost_basis="cut_area"))
    assert finished.status == cut.status == "COMPLETE"
    assert cut.total < finished.total  # Explicit 1 mm door edge compensation.
    yield_rule = PricingRule(cost_basis="sheet_yield", sheet_yield_percent="80")
    estimated = cost_cabinet(cabinet, master, currency="INR", as_of=AS_OF, policy=yield_rule)
    assert estimated.total == Decimal("597.16")
    assert sorted(line.quantity for line in estimated.lines if line.unit == "sheet") == [Decimal(1), Decimal(2)]
    nested = cost_cabinet(cabinet, master, currency="INR", as_of=AS_OF,
                          policy=PricingRule(cost_basis="nesting_sheets", sheet_kerf_mm="3",
                                             sheet_margin_mm="10"))
    assert nested.status == "COMPLETE"
    assert all("cabinet-isolated" in line.calculation for line in nested.lines if line.unit == "sheet")
    with pytest.raises(ValueError, match="twice"):
        PricingRule(cost_basis="sheet_yield", sheet_yield_percent="80",
                    material_wastage_percent="5").validate()


def test_dimension_finish_profile_and_rate_change_recalculate_draft_without_moving_cost():
    project = profiled_project()
    first = calculate_quotation(project).total
    cabinet = project.cabinets[0]
    cabinet.position_x += 5
    assert calculate_quotation(project).total == first
    cabinet.position_x -= 5
    cabinet.width -= 50
    assert calculate_quotation(project).total != first
    cabinet.width += 50
    cabinet.construction_profile["back_thickness_mm"] = 18
    assert calculate_quotation(project).total != first
    cabinet.construction_profile["back_thickness_mm"] = 6
    cabinet.material = "Walnut"
    assert calculate_quotation(project).total != first
    cabinet.material = "Cashmere"
    cabinet.door_count = 1
    assert calculate_quotation(project).total != first
    cabinet.door_count = 2
    cabinet.shelf_count = 2
    assert calculate_quotation(project).total != first
    cabinet.shelf_count = 1
    cabinet.depth -= 50
    assert calculate_quotation(project).total != first
    cabinet.depth += 50
    cabinet.height += 20
    assert calculate_quotation(project).total != first
    cabinet.height -= 20
    project.price_master.records[0].rate = "200"
    assert calculate_quotation(project).total > first


def test_fixed_manual_override_issued_snapshot_and_exports(tmp_path):
    project = profiled_project()
    project.price_master.catalogue_rules[0].mode = "fixed"
    project.price_master.catalogue_rules[0].fixed_price = "700"
    project.price_master.catalogue_rules[0].width_mm = 800
    project.price_master.catalogue_rules[0].height_mm = 720
    project.price_master.catalogue_rules[0].depth_mm = 600
    project.price_master.catalogue_rules[0].markup_percent = ""
    assert calculate_quotation(project).lines[0].unit_price == Decimal("700.00")
    project.quotation.unit_prices["C2"] = "650"
    assert calculate_quotation(project).lines[1].unit_price == Decimal("650.00")
    project.quotation.discount_percent = "10"
    project.quotation.tax_percent = "5"  # Synthetic test input, not a prescribed tax.
    draft = calculate_quotation(project)
    issued = issue_quotation_snapshot(project)
    old_total = issued["total"]
    project.cabinets[0].width -= 50
    project.price_master.records[0].rate = "500"
    assert get_issued_quotation_snapshot(project)["total"] == old_total
    assert calculate_quotation(project).total != draft.total
    xlsx = export_issued_quotation_xlsx(project, tmp_path / "issued.xlsx")
    pdf = export_issued_quotation_pdf(project, tmp_path / "issued.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
    workbook = load_workbook(xlsx, read_only=True, data_only=True)
    values = [cell for row in workbook.active.iter_rows(values_only=True) for cell in row]
    assert float(Decimal(old_total)) in values
    assert export_quotation_xlsx(project, tmp_path / "draft.xlsx").exists()
    assert export_quotation_pdf(project, tmp_path / "draft.pdf").read_bytes().startswith(b"%PDF")


def test_profiled_library_price_flows_to_project_and_survives_reopen(tmp_path):
    profile = synthetic_profile_for(Project.complete_kitchen_demo().cabinets[0]).to_dict()
    item = create_custom_revision([], product_id="SYNPRICED", name="Synthetic priced base",
                                  template_id="base_2_door", width=800, height=720, depth=600,
                                  board_thickness=18, door_count=2, drawer_count=0, shelf_count=1,
                                  default_finish="Cashmere", min_width=600, max_width=1200,
                                  min_height=600, max_height=900, min_depth=500, max_depth=700,
                                  construction_profile=profile)
    register_custom_items([item])
    project = Project.empty("Synthetic library placement")
    project.custom_catalogue = [item]
    project.price_master = synthetic_master()
    project.price_master.catalogue_rules.append(CataloguePriceRule(
        "SYN-LIB-PRICE", item.type_id, "calculated", "INR", DATE,
        status="approved", markup_percent="20"))
    project.quotation.currency = "INR"
    project.quotation.quotation_date = AS_OF
    placed = create_catalogue_cabinet(item.type_id, "C1", position_x=100, position_y=2500)
    project.add_cabinet(placed)
    assert placed.construction_profile["cabinet_type_id"] == item.type_id
    assert calculate_quotation(project).lines[0].unit_price is not None
    reopened = load_project(save_project(project, tmp_path / "priced.json"))
    assert calculate_quotation(reopened) == calculate_quotation(project)


def test_decorative_prop_is_excluded_from_all_prices():
    project = profiled_project()
    before_bom = deepcopy(generate_project_bom(project))
    before_quote = calculate_quotation(project)
    definition = get_product("potted_green_plant")
    project.add_product(PlacedProduct("P-STAGE9", definition.type_id, 300, 2650,
                                      definition.elevation_z, definition.width,
                                      definition.depth, definition.height))
    assert generate_project_bom(project) == before_bom
    assert calculate_quotation(project) == before_quote
