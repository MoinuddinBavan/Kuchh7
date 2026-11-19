"""SYNTHETIC catalogue-first prices; no client-approved prices or cabinet rules."""

from __future__ import annotations

import csv
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.costing import cost_cabinet
from kuchhe7.document_exports import (export_issued_quotation_pdf,
                                       export_quotation_pdf, export_quotation_xlsx)
from kuchhe7.models import HardwareAssignment, PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.price_master import (PRICE_COLUMNS, CataloguePriceRule, PriceRecord,
                                  load_price_master)
from kuchhe7.pricing_setup import (apply_company_setup_to_new_project,
                                   load_company_price_setup, save_company_price_setup)
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation, issue_quotation_snapshot
from tests.test_stage7b1_costing import synthetic_master


def synthetic_setup():
    master = synthetic_master()
    master.catalogue_rules.append(CataloguePriceRule(
        "SYN-BASE-MARKUP", "base_2_door", "calculated", "INR", "2026-01-01",
        "approved", "Cashmere", markup_percent="20"))
    master.records.extend([
        PriceRecord("SYN-WHITE-18", "Board", "Warm White", "Synthetic white board", "m2",
                    "150", "INR", "2026-01-01", "approved", "18",
                    specification="SYNTHETIC white board"),
        PriceRecord("SYN-WHITE-6", "Board", "Warm White", "Synthetic white back", "m2",
                    "120", "INR", "2026-01-01", "approved", "6",
                    specification="SYNTHETIC white back"),
        PriceRecord("SYN-OVEN", "Appliance", "oven_freestanding", "Synthetic oven", "each",
                    "200", "INR", "2026-01-01", "approved", selling_unit="each"),
    ])
    master.catalogue_rules.append(CataloguePriceRule(
        "SYN-BASE-WHITE", "base_2_door", "calculated", "INR", "2026-01-01",
        "approved", "Warm White", markup_percent="20"))
    master.validate()
    return master


def priced_project():
    project = Project.sample_kitchen()
    project.cabinets = [project.cabinets[0]]
    project.select_cabinet("C1")
    project.cabinet.material = "Cashmere"
    project.price_master = synthetic_setup()
    project.quotation.currency = "INR"
    project.quotation.quotation_date = "2026-11-19"
    return project


def test_company_setup_precedes_design_and_project_copy_is_independent(tmp_path, monkeypatch):
    path = tmp_path / "company-price-master.json"
    monkeypatch.setenv("KUCHE7_PRICE_SETUP_PATH", str(path))
    assert load_company_price_setup().records == []
    save_company_price_setup(synthetic_setup())
    project = Project.empty("Synthetic new kitchen")
    apply_company_setup_to_new_project(project, load_company_price_setup())
    assert project.quotation.currency == "INR"
    assert len(project.price_master.catalogue_rules) == 2
    project.price_master.records[0].rate = "999"
    assert load_company_price_setup().records[0].rate == "100"
    bad = synthetic_setup()
    bad.records.append(PriceRecord("SYN-BAD-PRODUCT", "Appliance", "unknown_appliance",
                                   "Synthetic invalid ID", "each", "1", "INR", "2026-01-01", "approved"))
    with pytest.raises(ValueError, match="unknown product ID"):
        save_company_price_setup(bad, tmp_path / "invalid.json")
    assert not (tmp_path / "invalid.json").exists()


def test_catalogue_price_automatic_width_finish_hardware_and_prop_exclusion():
    project = priced_project()
    first = calculate_quotation(project)
    assert first.lines[0].pricing_mode == "calculated"
    assert first.lines[0].unit_price == Decimal("469.78")
    old_bom = generate_project_bom(project)
    project.cabinet.width = 1200
    project.validate()
    wider = calculate_quotation(project)
    assert wider.total > first.total
    assert generate_project_bom(project) != old_bom
    project.cabinet.material = "Warm White"
    project.validate()
    white = calculate_quotation(project)
    assert white.total > wider.total
    panel_cost = next(line for line in cost_cabinet(project.cabinet, project.price_master,
                                                   as_of="2026-11-19").lines
                      if line.component == "Top panel")
    assert panel_cost.source_id == "SYN-WHITE-18"
    assert panel_cost.match_key == "Warm White" and panel_cost.specification == "SYNTHETIC white board"
    project.hardware_assignments.append(HardwareAssignment("H1", "C1", "handle_bar", 2))
    with_handles = calculate_quotation(project)
    assert with_handles.total > white.total
    prop = get_product("plant_pot")
    bom = generate_project_bom(project)
    eligible = nest_project(project).eligible_count
    project.add_product(PlacedProduct("P1", prop.type_id, 100, 1000, prop.elevation_z,
                                      prop.width, prop.depth, prop.height))
    assert calculate_quotation(project) == with_handles
    assert generate_project_bom(project) == bom
    assert nest_project(project).eligible_count == eligible


def test_fixed_variant_is_exact_and_unsupported_custom_size_is_incomplete():
    project = priced_project()
    project.price_master.catalogue_rules = [CataloguePriceRule(
        "SYN-FIXED-900", "base_2_door", "fixed", "INR", "2026-01-01",
        "approved", "Cashmere", 900, 720, 600, fixed_price="650")]
    assert calculate_quotation(project).lines[0].unit_price == Decimal("650.00")
    project.cabinet.width = 901
    summary = calculate_quotation(project)
    assert summary.unpriced_ids == ("C1",)
    assert any("custom size" in reason for reason in summary.incomplete_reasons)
    with pytest.raises(ValueError, match="Complete all billable"):
        issue_quotation_snapshot(project)


def test_billable_appliance_automatic_and_manual_exception_identifiable():
    project = priced_project()
    oven = get_product("oven_freestanding")
    project.add_product(PlacedProduct("A1", oven.type_id, 100, 100, oven.elevation_z,
                                      oven.width, oven.depth, oven.height))
    assert calculate_quotation(project).total == Decimal("469.78")
    project.quotation.billable_product_ids = ["A1"]
    lines = calculate_quotation(project).lines
    assert lines[1].pricing_mode == "master" and lines[1].unit_price == 200
    project.quotation.unit_prices["C1"] = "900"
    lines = calculate_quotation(project).lines
    assert lines[0].pricing_mode == "manual exception" and lines[0].unit_price == 900


def test_live_export_issued_snapshot_and_persistence(tmp_path):
    project = priced_project()
    project.quotation.customer_name = "SYNTHETIC customer"
    project.quotation.quotation_number = "SYN-003"
    project.quotation.discount_percent = "10"
    project.quotation.tax_percent = "5"
    original = calculate_quotation(project)
    issued = issue_quotation_snapshot(project)
    project.cabinet.width = 1200
    project.price_master.records[0].rate = "200"
    changed = calculate_quotation(project)
    assert changed.total > original.total
    draft = load_workbook(export_quotation_xlsx(project, tmp_path / "draft.xlsx"), data_only=True).active
    assert "DRAFT" in draft["A1"].value
    assert draft["F6"].value == float(changed.lines[0].unit_price)
    assert b"DRAFT CUSTOMER QUOTATION" in export_quotation_pdf(project, tmp_path / "draft.pdf").read_bytes()
    assert b"ISSUED QUOTATION" in export_issued_quotation_pdf(project, tmp_path / "issued.pdf").read_bytes()
    reopened = load_project(save_project(project, tmp_path / "project.json"))
    assert reopened.quotation.issued_snapshot == issued
    assert calculate_quotation(reopened).total == changed.total
    assert reopened.price_master.catalogue_rules[0].rule_id == "SYN-BASE-MARKUP"


def test_rate_import_rejects_duplicates_currency_and_invalid_dates(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "stage7b3_synthetic_prices.csv"
    assert len(load_price_master(fixture).records) == 4
    rows = [vars(row).copy() for row in synthetic_setup().records[:2]]
    path = tmp_path / "synthetic-rates.csv"
    def write(items):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=PRICE_COLUMNS)
            writer.writeheader(); writer.writerows(items)
    write(rows)
    assert len(load_price_master(path).records) == 2
    write(rows + [rows[0]])
    with pytest.raises(ValueError, match="Duplicate price record ID"):
        load_price_master(path)
    different = deepcopy(rows[1]); different["currency"] = "USD"
    write([rows[0], different])
    with pytest.raises(ValueError, match="mixed currencies"):
        load_price_master(path)
    invalid = deepcopy(rows[1]); invalid["effective_date"] = "yesterday"
    write([rows[0], invalid])
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        load_price_master(path)
    unknown = deepcopy(rows[1]); unknown.update(record_id="SYN-UNKNOWN", category="Appliance",
                                              match_key="not_a_catalogue_product", unit="each",
                                              thickness_mm="", specification="")
    write([rows[0], unknown])
    with pytest.raises(ValueError, match="unknown product ID"):
        load_price_master(path)
    wrong_unit = deepcopy(rows[1]); wrong_unit.update(record_id="SYN-WRONG-UNIT", category="Hardware",
                                                     match_key="Concealed hinge", unit="m2")
    write([rows[0], wrong_unit])
    with pytest.raises(ValueError, match="not a supported rate unit"):
        load_price_master(path)


def test_price_setup_ui_exposes_rates_and_catalogue_rules(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("KUCHE7_PRICE_SETUP_PATH", str(tmp_path / "company.json"))
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.main_window import CompanyPriceSetupDialog

    app = QApplication.instance() or QApplication([])
    dialog = CompanyPriceSetupDialog()
    assert dialog.workspace.master_page.count() == 2
    assert dialog.project.cabinets == []
    dialog.project.price_master = synthetic_setup()
    dialog.workspace.refresh()
    assert dialog.workspace.rules_table.rowCount() == 2
    dialog.save_setup()
    assert len(load_company_price_setup().catalogue_rules) == 2
    dialog.deleteLater(); app.processEvents()


def test_csv_import_in_price_setup_preserves_catalogue_rules(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from kuchhe7.ui.pricing_workspace import PricingWorkspace

    app = QApplication.instance() or QApplication([])
    project = Project.empty("Synthetic import")
    project.price_master = synthetic_setup()
    fixture = Path(__file__).parent / "fixtures" / "stage7b3_synthetic_prices.csv"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(fixture), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    updates = []
    ui = PricingWorkspace(lambda: updates.append(True))
    ui.set_project(project)
    ui.import_master()
    assert updates
    assert len(project.price_master.records) == 4
    assert len(project.price_master.catalogue_rules) == 2
    ui.master_page.deleteLater(); ui.cost_page.deleteLater(); app.processEvents()
