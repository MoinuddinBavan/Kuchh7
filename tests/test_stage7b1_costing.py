"""Synthetic prices only; these fixtures are not client-approved rates."""

import csv
from dataclasses import asdict
from decimal import Decimal

import ezdxf
import pytest
from openpyxl import Workbook, load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.costing import PricingRule, cost_cabinet
from kuchhe7.document_exports import export_quotation_pdf, export_quotation_xlsx
from kuchhe7.engineering_dxf import PANEL_OUTLINES, export_engineering_dxf
from kuchhe7.models import HardwareAssignment, PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.price_master import PRICE_COLUMNS, PriceMaster, PriceRecord, load_price_master, save_price_master
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation, issue_quotation_snapshot


def synthetic_master() -> PriceMaster:
    return PriceMaster([
        PriceRecord("SYN-BOARD-18", "Board", "Cashmere", "Synthetic 18 mm board", "m2",
                    "100", "INR", "2026-01-01", "approved", "18", "2440", "1220",
                    "SYNTHETIC test board specification"),
        PriceRecord("SYN-BACK-6", "Board", "Cashmere", "Synthetic 6 mm board", "m2",
                    "80", "INR", "2026-01-01", "approved", "6", specification="SYNTHETIC test back specification"),
        PriceRecord("SYN-HINGE", "Hardware", "Concealed hinge", "Synthetic hinge", "each",
                    "10", "INR", "2026-01-01", "approved"),
        PriceRecord("SYN-HANDLE", "Hardware", "handle_bar", "Synthetic handle", "each",
                    "7", "INR", "2026-01-01", "approved"),
        PriceRecord("SYN-LABOUR", "Labour", "assembly", "Synthetic hourly work", "hour",
                    "50", "INR", "2026-01-01", "approved"),
    ])


def sample() -> Project:
    project = Project.sample_kitchen()
    project.cabinets = [project.cabinets[0]]
    project.select_cabinet("C1")
    project.price_master = synthetic_master()
    project.quotation.quotation_date = "2026-11-19"
    project.quotation.currency = "INR"
    return project


def test_missing_rates_and_no_fictional_defaults():
    project = Project()
    assert project.price_master.records == []
    result = cost_cabinet(project.cabinet, project.price_master)
    assert result.status == "INCOMPLETE" and result.total is None
    assert any("approved rate missing" in reason for reason in result.missing)


def test_synthetic_mm2_to_m2_hardware_and_explicit_labour():
    project = sample()
    result = cost_cabinet(project.cabinet, project.price_master, currency="INR",
                          as_of="2026-11-19")
    assert result.status == "COMPLETE"
    assert result.total == Decimal("391.48")
    assert next(line for line in result.lines if line.component == "Top panel").quantity == Decimal("0.5184")
    assert next(line for line in result.lines if line.component == "Concealed hinge").amount == Decimal("40.00")
    with_labour = cost_cabinet(project.cabinet, project.price_master,
                               charge_quantities={"SYN-LABOUR": "2"}, currency="INR",
                               as_of="2026-11-19")
    assert with_labour.total == Decimal("491.48")
    assert not any("Labour" in line.component for line in result.lines)


def test_approved_dates_currency_and_sheet_rates_are_not_guessed():
    project = sample()
    assert cost_cabinet(project.cabinet, project.price_master, as_of="2025-12-31").status == "INCOMPLETE"
    assert cost_cabinet(project.cabinet, project.price_master, currency="USD",
                        as_of="2026-11-19").status == "INCOMPLETE"
    project.price_master.records[0].unit = "sheet"
    result = cost_cabinet(project.cabinet, project.price_master, currency="INR", as_of="2026-11-19")
    assert result.status == "INCOMPLETE"
    assert any("approved conversion rule" in reason for reason in result.missing)


def test_hardware_assignment_reconciliation_without_double_counting():
    project = sample()
    project.hardware_assignments = [HardwareAssignment("H1", "C1", "hinge_soft_close", 4),
                                    HardwareAssignment("H2", "C1", "handle_bar", 2)]
    result = cost_cabinet(project.cabinet, project.price_master,
                          hardware_assignments=project.hardware_assignments, currency="INR",
                          as_of="2026-11-19")
    assert result.total == Decimal("405.48")
    assert sum(line.component == "Concealed hinge" for line in result.lines) == 1
    project.hardware_assignments[0].quantity = 3
    conflict = cost_cabinet(project.cabinet, project.price_master,
                            hardware_assignments=project.hardware_assignments, currency="INR",
                            as_of="2026-11-19")
    assert conflict.status == "INCOMPLETE"
    assert any("reconcile" in reason for reason in conflict.missing)


def test_pricing_modes_and_manual_price_are_isolated():
    project = sample()
    project.quotation.unit_prices["C1"] = "999.99"
    assert calculate_quotation(project).lines[0].unit_price == Decimal("999.99")
    fixed = PricingRule(mode="fixed", approved=True, fixed_price="650")
    project.quotation.pricing_rules["C1"] = fixed
    assert calculate_quotation(project).lines[0].unit_price == Decimal("650.00")
    assert project.quotation.unit_prices["C1"] == "999.99"
    project.quotation.pricing_rules["C1"] = PricingRule(mode="calculated", approved=True, markup_percent="20")
    result = calculate_quotation(project)
    assert result.lines[0].unit_price == Decimal("469.78")
    assert result.lines[0].pricing_mode == "calculated"
    project.quotation.pricing_rules["C1"] = PricingRule(mode="calculated", approved=True,
                                                         gross_margin_percent="20")
    assert calculate_quotation(project).lines[0].unit_price == Decimal("489.35")
    assert project.quotation.unit_prices["C1"] == "999.99"
    with pytest.raises(ValueError, match="markup or gross margin"):
        PricingRule(mode="calculated", approved=True, markup_percent="20",
                    gross_margin_percent="20").validate()


def test_dimension_change_refreshes_draft_not_issued_snapshot(tmp_path):
    project = sample()
    project.quotation.customer_name = "Synthetic customer"
    project.quotation.quotation_number = "SYN-001"
    project.quotation.pricing_rules["C1"] = PricingRule(mode="calculated", approved=True, markup_percent="20")
    first = calculate_quotation(project).total
    snapshot = issue_quotation_snapshot(project)
    project.cabinet.width = 1200
    project.validate()
    assert calculate_quotation(project).total != first
    assert project.quotation.issued_snapshot == snapshot
    reopened = load_project(save_project(project, tmp_path / "priced-project.json"))
    assert reopened.to_dict()["schema_version"] == 8
    assert reopened.quotation.issued_snapshot == snapshot
    assert calculate_quotation(reopened).total == calculate_quotation(project).total
    assert reopened.price_master.records[0].rate == "100"


def test_price_master_json_csv_xlsx_import_and_validation(tmp_path):
    master = synthetic_master()
    assert load_price_master(save_price_master(master, tmp_path / "rates.json")).to_dict() == master.to_dict()
    rows = [asdict(record) for record in master.records]
    with (tmp_path / "rates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRICE_COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    assert load_price_master(tmp_path / "rates.csv").to_dict() == master.to_dict()
    workbook = Workbook(); sheet = workbook.active
    sheet.append(PRICE_COLUMNS)
    for record in master.records:
        sheet.append([getattr(record, field) for field in PRICE_COLUMNS])
    workbook.save(tmp_path / "rates.xlsx")
    assert load_price_master(tmp_path / "rates.xlsx").to_dict() == master.to_dict()
    (tmp_path / "broken.xlsx").write_bytes(b"not an Excel workbook")
    with pytest.raises(ValueError, match="valid XLSX"):
        load_price_master(tmp_path / "broken.xlsx")
    master.records[0].rate = ""
    with pytest.raises(ValueError, match="requires rate"):
        master.validate()


def test_legacy_project_props_and_existing_exports_unchanged(tmp_path):
    project = sample()
    old_data = project.to_dict()
    del old_data["price_master"]
    for key in ("currency", "pricing_rules", "issued_snapshot"):
        del old_data["quotation"][key]
    legacy = Project.from_dict(old_data)
    assert legacy.price_master.records == []
    before_bom = generate_project_bom(project)
    before_nesting = nest_project(project).eligible_count
    prop = get_product("plant_pot")
    project.add_product(PlacedProduct("P1", prop.type_id, 100, 1000, prop.elevation_z,
                                      prop.width, prop.depth, prop.height))
    assert generate_project_bom(project) == before_bom
    assert nest_project(project).eligible_count == before_nesting
    assert all(line.item_id != "P1" for line in calculate_quotation(project).lines)
    project.quotation.pricing_rules["C1"] = PricingRule(mode="fixed", approved=True, fixed_price="600")
    exported = load_workbook(export_quotation_xlsx(project, tmp_path / "quotation.xlsx"), data_only=True).active
    assert exported["F6"].value == 600
    assert exported["H6"].value == "fixed"
    assert b"Fixed" in export_quotation_pdf(project, tmp_path / "quotation.pdf").read_bytes()
    dxf = ezdxf.readfile(export_engineering_dxf(project, tmp_path / "panels.dxf", PANEL_OUTLINES))
    assert dxf.header["$INSUNITS"] == 4
    assert len(generate_project_bom(project)) == len(before_bom)


def test_price_master_and_cost_preview_ui(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.pricing_workspace import PricingWorkspace

    app = QApplication.instance() or QApplication([])
    project = sample()
    changes = []
    ui = PricingWorkspace(lambda: changes.append(True))
    ui.set_project(project)
    assert ui.master_table.rowCount() == len(project.price_master.records)
    assert "391.48" in ui.cost_total.text()
    ui.pricing_mode.setCurrentText("calculated")
    ui.rule_approved.setChecked(True)
    ui.markup.setText("20")
    ui.apply_rule()
    assert changes
    assert project.quotation.pricing_rules["C1"].mode == "calculated"
    assert "469.78" in ui.sell_preview.text()
    ui.master_page.deleteLater(); ui.cost_page.deleteLater()
    app.processEvents()


def test_automatic_draft_discount_tax_and_billable_appliance_rate():
    project = sample()
    appliance = get_product("oven_freestanding")
    project.add_product(PlacedProduct("A1", appliance.type_id, 100, 100, appliance.elevation_z,
                                      appliance.width, appliance.depth, appliance.height))
    project.price_master.records.append(PriceRecord(
        "SYN-OVEN", "Appliance", "oven_freestanding", "Synthetic supplied oven", "each",
        "200", "INR", "2026-01-01", "approved"))
    project.quotation.billable_product_ids = ["A1"]
    project.quotation.pricing_rules["C1"] = PricingRule(mode="fixed", approved=True, fixed_price="650")
    project.quotation.discount_percent = "10"
    project.quotation.tax_percent = "5"
    summary = calculate_quotation(project)
    assert summary.lines[1].pricing_mode == "master"
    assert (summary.subtotal, summary.discount, summary.taxable_amount,
            summary.tax, summary.total) == tuple(map(Decimal, ("850", "85", "765", "38.25", "803.25")))
    project.quotation.billable_product_ids = []
    assert calculate_quotation(project).total == Decimal("614.25")


def test_unapproved_rule_and_missing_cost_keep_quote_incomplete():
    project = sample()
    project.quotation.pricing_rules["C1"] = PricingRule(mode="calculated", approved=False, markup_percent="20")
    summary = calculate_quotation(project)
    assert summary.unpriced_ids == ("C1",)
    assert any("not approved" in reason for reason in summary.incomplete_reasons)
    project.quotation.pricing_rules["C1"].approved = True
    project.price_master.records.pop(0)
    summary = calculate_quotation(project)
    assert any("approved rate missing" in reason for reason in summary.incomplete_reasons)
    with pytest.raises(ValueError, match="Complete all billable"):
        issue_quotation_snapshot(project)


def test_documents_draft_refreshes_after_approved_rate_edit(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.documents_workspace import DocumentsWorkspace

    app = QApplication.instance() or QApplication([])
    project = sample()
    project.quotation.pricing_rules["C1"] = PricingRule(mode="calculated", approved=True, markup_percent="20")
    changed = []
    docs = DocumentsWorkspace(lambda: changed.append(True))
    docs.set_project(project)
    before = calculate_quotation(project).total
    docs.pricing_workspace.master_table.selectRow(0)
    docs.pricing_workspace.rate.setText("200")
    docs.pricing_workspace.apply_record()
    after = calculate_quotation(project).total
    assert changed and after > before
    assert str(after) in docs.totals_label.text()
    assert project.quotation.issued_snapshot is None
    docs.deleteLater(); app.processEvents()
