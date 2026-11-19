"""SYNTHETIC price-refresh, 2D readability and Qt shutdown regressions."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.costing import PricingRule
from kuchhe7.document_exports import (export_bom_pdf, export_bom_template_xlsx,
                                       export_issued_quotation_pdf, export_issued_quotation_xlsx,
                                       export_quotation_pdf, export_quotation_xlsx)
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.pricing_setup import (apply_company_setup_to_new_project,
                                   save_company_price_setup)
from kuchhe7.price_master import CataloguePriceRule, PriceRecord
from kuchhe7.pricing_refresh import (apply_company_price_refresh, master_revision,
                                     preview_company_price_refresh)
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation, issue_quotation_snapshot
from tests.test_stage7b3_catalogue_pricing import priced_project, synthetic_setup


def test_preview_is_read_only_and_refresh_recalculates_draft_not_issued(tmp_path):
    project = priced_project()
    project.quotation.customer_name = "SYNTHETIC customer"
    project.quotation.quotation_number = "SYN-REFRESH"
    issued = deepcopy(issue_quotation_snapshot(project))
    old_total = calculate_quotation(project).total
    original = deepcopy(project.to_dict())
    original_bom = generate_project_bom(project)
    company = synthetic_setup()
    company.records[0].rate = "200"
    company.records.append(PriceRecord(
        "SYN-NEW-HANDLE", "Hardware", "handle_bar", "SYNTHETIC new handle", "each",
        "8", "INR", "2026-01-02", "approved"))
    company.records = [row for row in company.records if row.record_id != "SYN-LABOUR"]
    preview = preview_company_price_refresh(project, company)
    assert project.to_dict() == original
    assert any(row.record_id == "SYN-BOARD-18" and row.old_value.startswith("100")
               and row.new_value.startswith("200") for row in preview.changes)
    assert any(row.change == "Added" and row.record_id == "SYN-NEW-HANDLE" for row in preview.changes)
    assert any(row.change == "Missing from company" and row.record_id == "SYN-LABOUR" for row in preview.changes)
    assert Decimal(preview.proposed_draft_total) > old_total
    apply_company_price_refresh(project, preview)
    assert calculate_quotation(project).total == Decimal(preview.proposed_draft_total)
    assert project.quotation.issued_snapshot == issued
    assert generate_project_bom(project) == original_bom
    assert project.pricing_revision["revision"] == preview.source_revision
    assert project.pricing_revision["latest_effective_date"] == "2026-01-02"
    reopened = load_project(save_project(project, tmp_path / "refreshed.json"))
    assert reopened.pricing_revision == project.pricing_revision
    assert reopened.quotation.issued_snapshot == issued
    assert calculate_quotation(reopened).total == calculate_quotation(project).total
    bom_sheet = load_workbook(export_bom_template_xlsx(project, tmp_path / "bom.xlsx"), data_only=True).active
    assert bom_sheet["A5"].value == "Left side panel"
    assert export_bom_pdf(project, tmp_path / "bom.pdf").stat().st_size > 100
    draft_sheet = load_workbook(export_quotation_xlsx(project, tmp_path / "draft.xlsx"), data_only=True).active
    issued_sheet = load_workbook(export_issued_quotation_xlsx(project, tmp_path / "issued.xlsx"), data_only=True).active
    assert draft_sheet["F6"].value == float(calculate_quotation(project).lines[0].unit_price)
    assert issued_sheet["F6"].value == float(issued["lines"][0]["unit_price"])
    assert b"DRAFT CUSTOMER QUOTATION" in export_quotation_pdf(project, tmp_path / "draft.pdf").read_bytes()
    assert b"ISSUED QUOTATION" in export_issued_quotation_pdf(project, tmp_path / "issued.pdf").read_bytes()


def test_manual_exceptions_survive_reviewed_refresh():
    project = priced_project()
    project.quotation.unit_prices["C1"] = "777"
    company = synthetic_setup()
    company.records[0].rate = "300"
    preview = preview_company_price_refresh(project, company)
    assert preview.manual_exception_ids == ("C1",)
    apply_company_price_refresh(project, preview)
    assert project.quotation.unit_prices["C1"] == "777"
    assert calculate_quotation(project).lines[0].unit_price == Decimal("777")
    project.quotation.pricing_rules["C1"] = PricingRule(mode="fixed", approved=True, fixed_price="800")
    second = preview_company_price_refresh(project, synthetic_setup())
    assert second.manual_exception_ids == ("C1",)
    apply_company_price_refresh(project, second)
    assert project.quotation.pricing_rules["C1"].fixed_price == "800"
    assert calculate_quotation(project).lines[0].unit_price == Decimal("800")


def test_new_project_stores_company_revision_without_draft_company_records():
    company = synthetic_setup()
    company.records.append(PriceRecord("SYN-DRAFT", "Hardware", "handle_bar",
                                       "Synthetic future rate", "each", "9", "INR",
                                       "2026-01-02", "draft"))
    project = Project.empty("Synthetic new project")
    apply_company_setup_to_new_project(project, company)
    assert project.pricing_revision["source"] == "company_price_setup"
    assert project.pricing_revision["revision"] == master_revision(project.price_master)
    assert all(row.status == "approved" for row in project.price_master.records)
    cabinet = create_catalogue_cabinet("base_2_door", "C1", position_x=650, position_y=2600)
    cabinet.material = "Cashmere"
    project.add_cabinet(cabinet)
    assert generate_project_bom(project)
    assert calculate_quotation(project).lines[0].unit_price == Decimal("469.78")


def test_legacy_project_without_revision_still_opens():
    data = priced_project().to_dict()
    data.pop("pricing_revision")
    reopened = Project.from_dict(data)
    assert reopened.pricing_revision == {}
    assert calculate_quotation(reopened).total == calculate_quotation(priced_project()).total


def test_currency_guard_and_stale_preview_rejection():
    project = priced_project()
    company = synthetic_setup()
    company.records[0].currency = "USD"
    with pytest.raises(ValueError, match="mixed currencies"):
        preview_company_price_refresh(project, company)
    company = synthetic_setup()
    for record in company.records:
        record.currency = "USD"
    for rule in company.catalogue_rules:
        rule.currency = "USD"
    with pytest.raises(ValueError, match="Project quotation uses INR"):
        preview_company_price_refresh(project, company)
    company = synthetic_setup()
    preview = preview_company_price_refresh(project, company)
    project.price_master.records[0].rate = "900"
    with pytest.raises(ValueError, match="changed after this preview"):
        apply_company_price_refresh(project, preview)
    assert project.price_master.records[0].rate == "900"


def test_refresh_removes_missing_rules_and_marks_draft_incomplete():
    project = priced_project()
    company = synthetic_setup()
    company.catalogue_rules = []
    preview = preview_company_price_refresh(project, company)
    assert any(row.kind == "Catalogue rule" and row.change == "Missing from company"
               for row in preview.changes)
    assert preview.proposed_incomplete
    apply_company_price_refresh(project, preview)
    assert calculate_quotation(project).unpriced_ids == ("C1",)


def test_width_height_depth_finish_appliance_and_props_recalculate():
    project = priced_project()
    project.cabinet.position_y = 2500  # leave room for a deeper valid test cabinet
    project.validate()
    base = calculate_quotation(project).total
    for field, increment in (("width", 100), ("height", 50), ("depth", 50)):
        before = calculate_quotation(project).total
        setattr(project.cabinet, field, getattr(project.cabinet, field) + increment)
        project.validate()
        assert calculate_quotation(project).total > before
    project.cabinet.material = "Warm White"
    project.validate()
    assert calculate_quotation(project).total > base
    oven = get_product("oven_freestanding")
    project.add_product(PlacedProduct("A1", oven.type_id, 100, 100, oven.elevation_z,
                                      oven.width, oven.depth, oven.height))
    project.quotation.billable_product_ids = ["A1"]
    with_oven = calculate_quotation(project)
    assert with_oven.lines[-1].pricing_mode == "master"
    bom = generate_project_bom(project)
    prop = get_product("plant_pot")
    project.add_product(PlacedProduct("P1", prop.type_id, 200, 1000, prop.elevation_z,
                                      prop.width, prop.depth, prop.height))
    assert calculate_quotation(project) == with_oven
    assert generate_project_bom(project) == bom


def test_two_catalogue_cabinets_price_from_shared_company_rules():
    project = priced_project()
    wall = create_catalogue_cabinet("wall_2_door", "C2", position_x=650, position_y=2850)
    project.price_master.catalogue_rules.append(CataloguePriceRule(
        "SYN-WALL", "wall_2_door", "calculated", "INR", "2026-01-01",
        "approved", "Warm White", markup_percent="20"))
    project.add_cabinet(wall)
    project.validate()
    summary = calculate_quotation(project)
    assert [line.item_id for line in summary.lines] == ["C1", "C2"]
    assert all(line.unit_price is not None and line.pricing_mode == "calculated"
               for line in summary.lines)
    assert {row.cabinet_id for row in generate_project_bom(project)} == {"C1", "C2"}


def test_refresh_dialog_shows_changes_and_preserves_project_until_accept(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.pricing_refresh_dialog import PricingRefreshDialog

    app = QApplication.instance() or QApplication([])
    project = priced_project()
    company = synthetic_setup(); company.records[0].rate = "200"
    preview = preview_company_price_refresh(project, company)
    dialog = PricingRefreshDialog(preview)
    assert dialog.table.rowCount() == len(preview.changes)
    assert "LIVE DRAFT" in dialog.draft_label.text()
    assert project.price_master.records[0].rate == "100"
    dialog.reject()
    assert project.price_master.records[0].rate == "100"
    dialog.deleteLater(); app.processEvents()


def test_complete_kitchen_plan_labels_fit_and_do_not_overlap(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QGraphicsTextItem
    from kuchhe7.ui.cad_views import RoomPlanView

    app = QApplication.instance() or QApplication([])
    project = Project.complete_kitchen_demo()
    view = RoomPlanView()
    view.redraw(project.room, project.cabinets, project.selected_cabinet_id,
                project.selected_opening_id, "WEST", project.placed_products, None)
    labels = {item.data(0): item for item in view.scene().items()
              if isinstance(item, QGraphicsTextItem) and item.data(0) in
              {cabinet.cabinet_id for cabinet in project.cabinets}}
    assert len(labels) == 6
    for cabinet in project.cabinets:
        label = labels[cabinet.cabinet_id]
        footprint = view._cabinet_items[cabinet.cabinet_id]
        assert label.sceneBoundingRect().width() <= footprint.sceneBoundingRect().width()
        assert footprint.sceneBoundingRect().contains(label.sceneBoundingRect().center())
    for first_id, first in labels.items():
        for second_id, second in labels.items():
            if first_id < second_id:
                assert not first.sceneBoundingRect().intersects(second.sceneBoundingRect())
    view.deleteLater(); app.processEvents()


def test_main_window_closes_plotter_once_before_qt_shutdown(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    calls = []
    original = window.view3d.plotter.close
    def close_once():
        calls.append(True)
        original()
    monkeypatch.setattr(window.view3d.plotter, "close", close_once)
    window.show()
    app.processEvents()
    window.close()
    window.view3d.close_plotter()
    assert len(calls) == 1
    window.deleteLater(); app.processEvents()


def test_main_window_reviewed_refresh_updates_draft_and_marks_dirty(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("KUCHE7_PRICE_SETUP_PATH", str(tmp_path / "company.json"))
    from PySide6.QtWidgets import QApplication, QDialog
    from kuchhe7.ui.main_window import MainWindow
    from kuchhe7.ui.pricing_refresh_dialog import PricingRefreshDialog

    app = QApplication.instance() or QApplication([])
    company = synthetic_setup(); company.records[0].rate = "200"
    save_company_price_setup(company)
    window = MainWindow()
    window.project = priced_project()
    window.refresh_all()
    before = calculate_quotation(window.project).total
    monkeypatch.setattr(PricingRefreshDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window.refresh_company_prices()
    assert window._dirty
    assert calculate_quotation(window.project).total > before
    assert window.project.pricing_revision["revision"]
    window.close(); window.deleteLater(); app.processEvents()
