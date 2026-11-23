"""Synthetic Stage 10 rectangle and sheet-cost tests; no factory approval."""

from decimal import Decimal
import hashlib
import json

import ezdxf
import pytest

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.costing import PricingRule, cost_cabinet
from kuchhe7.nesting import (PanelInstance, SheetSettings, SheetSpecification,
                             group_panel_instances, nest_panels, nest_project,
                             project_panel_instances)
from kuchhe7.nesting_export import export_nesting_layout_dxf
from kuchhe7.nesting_validation import validate_nesting_result
from kuchhe7.models import Project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.price_master import CataloguePriceRule, PriceMaster, PriceRecord
from kuchhe7.quotation import calculate_quotation, get_issued_quotation_snapshot, issue_quotation_snapshot
from kuchhe7.pricing_refresh import master_revision
from kuchhe7.sheet_costing import allocate_project_sheet_cost
from kuchhe7.construction import synthetic_profile_for
from kuchhe7.ui.sheet_nesting import _project_nesting_signature
from kuchhe7.ui.sheet_nesting import SheetNestingWidget


def panel(number, length=60, width=60, *, finish="Cashmere", material="Cashmere",
          thickness=18, grain="undefined", part_id="C1-P01"):
    return PanelInstance("C1", "Test panel", length, width, thickness, material,
                         number, grain_direction=grain, part_id=part_id, finish=finish)


def spec(length=100, width=100, *, grain="undefined", rotation=True):
    return SheetSpecification("SYN-SHEET", "Cashmere", 18, length, width,
                              "Cashmere", grain_direction=grain, allow_rotation=rotation)


def test_area_lower_bound_does_not_replace_feasible_sheet_count():
    settings = SheetSettings(100, 100, 0, 0)
    items = [panel(1), panel(2)]  # 7,200 mm² < one 10,000 mm² sheet.
    result = nest_panels(items, settings, sheet_specs={("Cashmere", 18, "Cashmere", ""): spec()},
                         require_sheet_specs=True)
    validate_nesting_result(result)
    assert result.theoretical_minimum_sheets == 1
    assert result.sheet_count == 2
    assert result.eligible_count == result.placed_count == 2


def test_best_fit_improves_one_known_synthetic_fixture_and_shelf_remains_valid():
    sizes = [(740, 380), (680, 400), (220, 300), (520, 440),
             (440, 320), (500, 360), (560, 260), (520, 220), (380, 220)]
    items = [PanelInstance("C1", "Synthetic rectangle", length, width, 18,
                           "Cashmere", number, grain_direction="none")
             for number, (length, width) in enumerate(sizes, 1)]
    settings = SheetSettings(1000, 700, 3, 10)
    prior = nest_panels(items, settings, strategy="shelf")
    improved = nest_panels(items, settings)
    validate_nesting_result(prior)
    validate_nesting_result(improved)
    assert prior.sheet_count == 4
    assert improved.sheet_count == 3
    assert improved.utilization_percent > prior.utilization_percent


def test_finish_material_thickness_and_unknown_material_are_separate():
    items = [panel(1), panel(2, finish="Walnut"), panel(3, material="Walnut"),
             panel(4, thickness=6)]
    assert len(group_panel_instances(items)) == 4
    missing = nest_panels([panel(5, material="")], SheetSettings(100, 100, 0, 0))
    assert missing.unplaced_count == 1 and missing.sheet_count == 0
    assert "material" in missing.unplaced_panels[0].reason.lower()


def test_trim_clearance_and_kerf_are_checked_independently():
    settings = SheetSettings(130, 100, 3, 5, clearance_mm=8,
                             trim_left_mm=10, trim_right_mm=7,
                             trim_top_mm=2, trim_bottom_mm=4)
    items = [panel(1, 50, 40), panel(2, 50, 40)]
    result = nest_panels(items, settings, sheet_specs={("Cashmere", 18, "Cashmere", ""): spec(130, 100)})
    validate_nesting_result(result)
    assert settings.part_gap_mm == 8  # Kerf and clearance are not added twice.
    assert settings.usable_length_mm == 103
    assert result.sheet_count >= 1
    assert result.usable_area_mm2 < result.purchased_area_mm2
    assert result.trim_and_margin_area_mm2 == result.purchased_area_mm2 - result.usable_area_mm2


def test_grain_and_sheet_rotation_require_matching_orientation():
    item = panel(1, 80, 40, grain="lengthwise")
    settings = SheetSettings(50, 100, 0, 0)
    key = ("Cashmere", 18, "Cashmere", "")
    rotated = nest_panels([item], settings, sheet_specs={key: spec(50, 100, grain="widthwise")})
    validate_nesting_result(rotated)
    assert rotated.placed_panels[0].rotated
    blocked = nest_panels([item], settings, sheet_specs={key: spec(50, 100, grain="widthwise", rotation=False)})
    assert blocked.unplaced_count == 1
    unknown = nest_panels([item], settings, sheet_specs={key: spec(50, 100)})
    assert unknown.unplaced_count == 1


def test_offcuts_are_disjoint_candidates_not_all_unused_area():
    settings = SheetSettings(100, 100, 2, 0, min_offcut_length_mm=30,
                             min_offcut_width_mm=30)
    result = nest_panels([panel(1, 40, 40)], settings,
                         sheet_specs={("Cashmere", 18, "Cashmere", ""): spec()})
    validate_nesting_result(result)
    assert len(result.reusable_offcuts) == 2
    assert result.reusable_offcut_area_mm2 < result.usable_residual_area_mm2
    assert all(item.sheet_id == "SYN-SHEET" for item in result.reusable_offcuts)


def test_authoritative_cut_list_part_ids_and_profile_are_preserved():
    project = Project.complete_kitchen_demo()
    panels = project_panel_instances(project)
    assert len(panels) == sum(row.quantity for row in generate_project_bom(project)
                              if row.material != "Hardware")
    assert all(item.part_id.startswith(item.cabinet_id + "-P") for item in panels)
    result = nest_project(project)
    validate_nesting_result(result)
    assert result.eligible_count == result.placed_count + result.unplaced_count


def test_construction_profile_changes_invalidate_layout_signature():
    project = Project.complete_kitchen_demo()
    before = _project_nesting_signature(project)
    project.cabinets[0].construction_profile = synthetic_profile_for(project.cabinets[0]).to_dict()
    after = _project_nesting_signature(project)
    assert after != before


def test_sheet_master_grain_and_rotation_metadata_round_trip():
    record = PriceRecord("SYN-GRAIN", "Board", "Cashmere", "SYNTHETIC SHEET",
                         "sheet", "100", "INR", "2026-01-01", "approved",
                         "18", "2440", "1220", specification="SYNTHETIC BOARD",
                         finish="Cashmere", material_id="SYN-CASH18",
                         grain_direction="lengthwise", sheet_rotation_policy="forbidden")
    master = PriceMaster([record])
    reopened = PriceMaster.from_dict(master.to_dict())
    assert reopened.records[0].material_id == "SYN-CASH18"
    assert reopened.records[0].grain_direction == "lengthwise"
    assert reopened.records[0].sheet_rotation_policy == "forbidden"


def test_default_sheet_metadata_preserves_legacy_price_revision_identity():
    master = synthetic_two_cabinet_project().price_master
    old_shape = master.to_dict()
    for record in old_shape["records"]:
        for name in ("material_id", "grain_direction", "sheet_rotation_policy"):
            record.pop(name)
    prior_hash = hashlib.sha256(json.dumps(old_shape, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()[:16]
    assert master_revision(master) == prior_hash
    master.records[0].grain_direction = "lengthwise"
    assert master_revision(master) != prior_hash


def synthetic_two_cabinet_project():
    project = Project.empty("Stage 10 Synthetic Sheets")
    for ident, x in (("C1", 100), ("C2", 1100)):
        cabinet = create_catalogue_cabinet("base_2_door", ident,
                                          position_x=x, position_y=2500)
        cabinet.material = "Cashmere"
        project.add_cabinet(cabinet)
    project.quotation.currency = "INR"
    project.quotation.quotation_date = "2026-11-22"
    project.quotation.quotation_number = "SYN-STAGE10"
    project.quotation.customer_name = "Synthetic test"
    records = [PriceRecord(f"SYN-SHEET-{thickness}", "Board", "Cashmere",
                           "SYNTHETIC SHEET RATE", "sheet", rate, "INR",
                           "2026-01-01", "approved", str(thickness), "2440", "1220",
                           specification="SYNTHETIC BOARD", finish="Cashmere")
               for thickness, rate in ((18, "200"), (6, "100"))]
    records.append(PriceRecord("SYN-HINGE", "Hardware", "Concealed hinge",
                               "SYNTHETIC HINGE", "each", "10", "INR",
                               "2026-01-01", "approved"))
    rule = CataloguePriceRule("SYN-PROJECT-NEST", "base_2_door", "calculated",
                              "INR", "2026-01-01", status="approved",
                              markup_percent="20", cost_basis="project_nesting",
                              sheet_kerf_mm="3", sheet_margin_mm="10")
    project.price_master = PriceMaster(records, [rule])
    return project


def test_project_wide_sheet_cost_exactly_reconciles_without_double_charge(tmp_path):
    project = synthetic_two_cabinet_project()
    settings = SheetSettings(2440, 1220, 3, 10)
    allocation = allocate_project_sheet_cost(project, settings, as_of="2026-11-22", currency="INR")
    assert allocation.layout.unplaced_count == 0
    assert allocation.total == sum((row.amount for row in allocation.allocations), Decimal("0.00"))
    assert {row.cabinet_id for row in allocation.allocations} == {"C1", "C2"}
    quote = calculate_quotation(project)
    assert not quote.unpriced_ids and not quote.incomplete_reasons
    assert all(line.unit_price is not None for line in quote.lines)
    issued = issue_quotation_snapshot(project)
    project.cabinets[0].width -= 50
    current = calculate_quotation(project)
    assert get_issued_quotation_snapshot(project) == issued
    assert current.lines[0].unit_price != quote.lines[0].unit_price
    reopened = load_project(save_project(project, tmp_path / "stage10.json"))
    assert calculate_quotation(reopened) == current


def test_missing_sheet_rate_makes_draft_incomplete_without_area_fallback():
    project = synthetic_two_cabinet_project()
    project.price_master.records = [record for record in project.price_master.records
                                    if record.record_id != "SYN-SHEET-6"]
    quote = calculate_quotation(project)
    assert quote.unpriced_ids and quote.incomplete_reasons
    assert any("per-sheet rate" in reason for reason in quote.incomplete_reasons)


def test_directional_profile_needs_sheet_grain_axis_for_costing():
    project = synthetic_two_cabinet_project()
    cabinet = project.cabinets[0]
    profile = synthetic_profile_for(cabinet).to_dict()
    profile["grain_directions"] = {"Door": "lengthwise"}
    cabinet.construction_profile = profile
    with pytest.raises(ValueError, match="grain axis"):
        allocate_project_sheet_cost(project, SheetSettings(), as_of="2026-11-22", currency="INR")


def test_separate_nesting_dxf_is_dimensioned_and_does_not_mutate_project(tmp_path):
    project = synthetic_two_cabinet_project()
    original = project.to_dict()
    result = nest_project(project)
    path = export_nesting_layout_dxf(result, tmp_path / "synthetic_layout.dxf")
    drawing = ezdxf.readfile(path)
    assert drawing.header["$INSUNITS"] == 4
    outlines = [entity for entity in drawing.modelspace()
                if entity.dxf.layer == "PANEL_OUTLINES"]
    assert len(outlines) == result.placed_count
    assert project.to_dict() == original


def test_incomplete_nesting_layout_cannot_be_exported_as_complete_dxf(tmp_path):
    result = nest_panels([panel(1, length=3000, width=1300)], SheetSettings())
    assert result.unplaced_count == 1
    with pytest.raises(ValueError, match="incomplete"):
        export_nesting_layout_dxf(result, tmp_path / "incomplete.dxf")
    assert not (tmp_path / "incomplete.dxf").exists()


def test_nesting_workspace_uses_approved_sheets_and_marks_geometry_stale(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    project = synthetic_two_cabinet_project()
    view = SheetNestingWidget()
    view.set_project(project)
    view.use_master_sheets.setChecked(True)
    view.recalculate()
    assert view.result is not None and view.result.unplaced_count == 0
    assert all(group.sheet_specification.sheet_id.startswith("SYN-SHEET-")
               for group in view.result.groups)
    project.price_master.records[0].rate = "250"
    view.set_project(project)
    assert view.stale_label.text() == "Layout current"  # Price-only change.
    project.price_master.records[0].sheet_length_mm = "2500"
    view.set_project(project)
    assert "recalculate" in view.stale_label.text().lower()
    view.close()
    app.processEvents()


def test_failed_sheet_master_recalculation_does_not_show_old_layout_as_current(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    project = synthetic_two_cabinet_project()
    view = SheetNestingWidget()
    view.set_project(project)
    assert view.result is not None
    project.quotation.currency = ""
    view.use_master_sheets.setChecked(True)
    view.recalculate()
    assert view.result is None
    assert view.completeness_label.text() == "Layout unavailable"
    assert view.stat_placed.text() == "—"
    assert "currency" in view.warning_list.item(0).text().lower()
    view.close()
    app.processEvents()
