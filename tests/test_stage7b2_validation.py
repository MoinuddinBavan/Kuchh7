"""Stage 7B.2 uses synthetic expectations only; no factory approval is implied."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.cabinet_validation import compare_cabinet, load_reference
from kuchhe7.costing import PricingRule
from kuchhe7.document_exports import (export_issued_quotation_pdf, export_issued_quotation_xlsx,
                                       export_quotation_xlsx)
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.price_master import PriceMaster, PriceRecord
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation, get_issued_quotation_snapshot, issue_quotation_snapshot

REFERENCE = Path(__file__).parent / "fixtures" / "stage7b2_synthetic_reference.json"


def synthetic_project() -> Project:
    project = Project.sample_kitchen("Synthetic cabinet validation")
    project.cabinets = [project.cabinets[0]]
    project.select_cabinet("C1")
    project.price_master = PriceMaster([
        PriceRecord("SYN-BOARD-18", "Board", "Cashmere", "Synthetic board", "m2", "100", "INR",
                    "2026-01-01", "approved", "18", "2440", "1220", "SYNTHETIC test board specification"),
        PriceRecord("SYN-BACK-6", "Board", "Cashmere", "Synthetic back", "m2", "80", "INR",
                    "2026-01-01", "approved", "6", specification="SYNTHETIC test back specification"),
        PriceRecord("SYN-HINGE", "Hardware", "Concealed hinge", "Synthetic hinge", "each", "10",
                    "INR", "2026-01-01", "approved"),
    ])
    project.quotation.currency = "INR"
    project.quotation.quotation_date = "2026-11-19"
    project.quotation.customer_name = "Synthetic customer"
    project.quotation.quotation_number = "SYN-001"
    project.quotation.discount_percent = "10"
    project.quotation.tax_percent = "5"
    project.quotation.pricing_rules["C1"] = PricingRule(mode="calculated", approved=True, markup_percent="20")
    project.validate()
    return project


def test_full_synthetic_reference_matches_all_supplied_sections():
    project = synthetic_project()
    original = project.to_dict()
    report = compare_cabinet(project, load_reference(REFERENCE))
    assert report.mismatches == [], report.to_markdown()
    assert project.to_dict() == original
    assert report.unchecked_sections == []
    assert report.to_dict()["all_supplied_expectations_match"]
    assert report.reference_status == "synthetic"  # Matching a fixture never approves production.
    assert len(report.checked) > 25


def test_dimension_change_reports_expected_actual_and_difference():
    project = synthetic_project()
    project.cabinet.width = 1200
    project.validate()
    report = compare_cabinet(project, load_reference(REFERENCE))
    by_path = {item.path: item for item in report.mismatches}
    assert by_path["cabinet.width"].expected == 900
    assert by_path["cabinet.width"].actual == 1200
    assert by_path["cabinet.width"].difference == "300"
    assert any(item.path.startswith("components.Door.width_mm") for item in report.mismatches)
    assert any(item.path.startswith("cost.") for item in report.mismatches)
    assert any(item.path.startswith("selling_price.") for item in report.mismatches)
    assert any(item.path.startswith("drawing.panel_rectangles") for item in report.mismatches)


def test_rate_change_affects_draft_cost_and_quote_not_bom_or_nesting():
    project = synthetic_project()
    before_bom = generate_project_bom(project)
    before_nesting = nest_project(project)
    project.price_master.records[0].rate = "200"
    report = compare_cabinet(project, load_reference(REFERENCE))
    assert not any(item.path.startswith(("components", "hardware", "bom_totals", "drawing", "nesting"))
                   for item in report.mismatches)
    assert any(item.path == "cost.total" for item in report.mismatches)
    assert any(item.path == "quotation.total" for item in report.mismatches)
    assert generate_project_bom(project) == before_bom
    assert nest_project(project) == before_nesting


def test_missing_material_rate_and_prop_exclusion_are_visible():
    project = synthetic_project()
    prop = get_product("plant_pot")
    project.add_product(PlacedProduct("P1", prop.type_id, 100, 1000, prop.elevation_z,
                                      prop.width, prop.depth, prop.height))
    assert compare_cabinet(project, load_reference(REFERENCE)).mismatches == []
    project.cabinet.material = "Walnut"
    project.validate()
    report = compare_cabinet(project, load_reference(REFERENCE))
    assert any(item.path.startswith("material_specifications.") for item in report.mismatches)
    assert any(item.path == "cost.status" for item in report.mismatches)
    assert any(item.path == "quotation.unpriced_ids" for item in report.mismatches)
    assert all(line.item_id != "P1" for line in calculate_quotation(project).lines)


def test_issued_exports_use_saved_snapshot_after_dimension_rate_and_tax_change(tmp_path):
    project = synthetic_project()
    saved = deepcopy(issue_quotation_snapshot(project))
    project.cabinet.width = 1200
    project.price_master.records[0].rate = "250"
    project.quotation.tax_percent = "17"
    project.validate()
    assert calculate_quotation(project).total != Decimal(saved["total"])
    assert get_issued_quotation_snapshot(project) == saved
    issued_xlsx = load_workbook(export_issued_quotation_xlsx(project, tmp_path / "issued.xlsx"),
                                data_only=True).active
    draft_xlsx = load_workbook(export_quotation_xlsx(project, tmp_path / "draft.xlsx"),
                               data_only=True).active
    assert issued_xlsx["A1"].value.startswith("KÜCHE7 ISSUED")
    assert issued_xlsx["F6"].value == float(saved["lines"][0]["unit_price"])
    assert float(saved["total"]) in [cell.value for cell in issued_xlsx["F"]]
    assert float(saved["total"]) not in [cell.value for cell in draft_xlsx["F"]]
    issued_pdf = export_issued_quotation_pdf(project, tmp_path / "issued.pdf").read_bytes()
    assert b"ISSUED QUOTATION SNAPSHOT" in issued_pdf
    assert saved["total"].encode() in issued_pdf
    reopened = load_project(save_project(project, tmp_path / "project.json"))
    assert get_issued_quotation_snapshot(reopened) == saved
    assert export_issued_quotation_pdf(reopened, tmp_path / "reopened.pdf").read_bytes() == issued_pdf


def test_legacy_snapshot_exports_without_repricing_and_invalid_snapshot_fails(tmp_path):
    project = synthetic_project()
    issue_quotation_snapshot(project)
    for key in ("project_name", "discount_percent", "tax_percent", "taxable_amount"):
        del project.quotation.issued_snapshot[key]
    project.cabinet.width = 1200
    assert get_issued_quotation_snapshot(project)["total"] == "443.94"
    sheet = load_workbook(export_issued_quotation_xlsx(project, tmp_path / "legacy-issued.xlsx"),
                          data_only=True).active
    assert sheet["B2"].value == "Not captured in legacy snapshot"
    project.quotation.issued_snapshot["total"] = "999"
    with pytest.raises(ValueError, match="do not reconcile"):
        export_issued_quotation_pdf(project, tmp_path / "invalid.pdf")


def test_reference_requires_explicit_status_and_approval_evidence(tmp_path):
    reference = load_reference(REFERENCE)
    assert reference["reference_status"] == "synthetic"
    reference["reference_status"] = "client_approved"
    import json
    path = tmp_path / "false-approval.json"
    path.write_text(json.dumps(reference), encoding="utf-8")
    with pytest.raises(ValueError, match="approver and revision"):
        load_reference(path)


def test_documents_ui_distinguishes_draft_and_issued(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.documents_workspace import DocumentsWorkspace

    app = QApplication.instance() or QApplication([])
    project = synthetic_project()
    docs = DocumentsWorkspace(lambda: None)
    docs.set_project(project)
    assert "LIVE DRAFT" in docs.totals_label.text()
    assert not docs.issued_excel_button.isEnabled()
    issue_quotation_snapshot(project)
    docs.refresh()
    assert docs.issued_excel_button.isEnabled() and docs.issued_pdf_button.isEnabled()
    assert "frozen" in docs.issued_label.text()
    project.cabinet.width = 1200
    docs.refresh()
    assert "443.94" in docs.issued_label.text()
    assert "443.94" not in docs.totals_label.text()
    docs.deleteLater(); app.processEvents()


def test_nesting_marks_layout_stale_until_regenerated(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.sheet_nesting import SheetNestingWidget

    app = QApplication.instance() or QApplication([])
    project = synthetic_project()
    ui = SheetNestingWidget()
    ui.set_project(project)
    assert ui.stale_label.text() == "Layout current"
    project.cabinet.material = "Walnut"
    project.validate()
    ui.set_project(project)
    assert "recalculate" in ui.stale_label.text().lower()
    ui.recalculate()
    assert ui.stale_label.text() == "Layout current"
    assert all(group.material == "Walnut" for group in ui.result.groups)
    ui.deleteLater(); app.processEvents()


def test_reference_cli_writes_match_and_mismatch_reports(tmp_path, capsys):
    from scripts.validate_cabinet_reference import main

    project_path = save_project(synthetic_project(), tmp_path / "project.json")
    report_path = tmp_path / "match.md"
    json_path = tmp_path / "match.json"
    assert main(["--project", str(project_path), "--reference", str(REFERENCE),
                 "--report", str(report_path), "--json-report", str(json_path)]) == 0
    assert "SYNTHETIC TEST ONLY" in report_path.read_text(encoding="utf-8")
    assert '"matched": true' in json_path.read_text(encoding="utf-8")
    project = load_project(project_path)
    project.cabinet.width = 1200
    save_project(project, project_path)
    assert main(["--project", str(project_path), "--reference", str(REFERENCE),
                 "--report", str(tmp_path / "mismatch.md")]) == 1
    assert "cabinet.width | 900 | 1200 | 300" in (tmp_path / "mismatch.md").read_text(encoding="utf-8")
    capsys.readouterr()
