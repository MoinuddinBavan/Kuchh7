"""Revisioned custom cabinet library with synthetic prices only."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet, get_catalogue_item, register_custom_items
from kuchhe7.custom_catalogue import create_custom_revision, load_custom_catalogue, save_custom_catalogue
from kuchhe7.document_exports import (export_bom_pdf, export_bom_template_xlsx,
                                       export_quotation_pdf, export_quotation_xlsx)
from kuchhe7.engineering_dxf import PANEL_OUTLINES, export_engineering_dxf
from kuchhe7.models import HardwareAssignment, Project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.price_master import CataloguePriceRule
from kuchhe7.pricing_setup import apply_company_setup_to_new_project
from kuchhe7.quotation import calculate_quotation, issue_quotation_snapshot
from tests.test_stage7b3_catalogue_pricing import synthetic_setup


def _item(product_id="SYNSTAGE9", items=None, **changes):
    values = dict(product_id=product_id, name="Synthetic custom base", template_id="base_2_door",
                  width=900, height=720, depth=600, board_thickness=18, door_count=2,
                  drawer_count=0, shelf_count=1, default_finish="Cashmere",
                  min_width=600, max_width=1200, min_height=600, max_height=900,
                  min_depth=500, max_depth=700, handle_quantity=2)
    values.update(changes)
    return create_custom_revision(items or [], **values)


def _rule(item, mode="calculated", **changes):
    values = dict(rule_id=f"SYN-{item.product_id}-V{item.revision}", type_id=item.type_id,
                  mode=mode, currency="INR", effective_date="2026-01-01", status="approved",
                  material=item.default_finish, markup_percent="20" if mode == "calculated" else "",
                  width_mm=item.width if mode == "fixed" else 0,
                  height_mm=item.height if mode == "fixed" else 0,
                  depth_mm=item.depth if mode == "fixed" else 0,
                  fixed_price="700" if mode == "fixed" else "")
    values.update(changes)
    return CataloguePriceRule(**values)


def _project(item, rule):
    register_custom_items([item])
    master = synthetic_setup()
    master.catalogue_rules.append(rule)
    project = Project.empty("Synthetic custom cabinet")
    project.custom_catalogue = [item]
    apply_company_setup_to_new_project(project, master)
    project.quotation.quotation_date = "2026-11-19"
    cabinet = create_catalogue_cabinet(item.type_id, "C1", position_x=650, position_y=2500)
    project.add_cabinet(cabinet)
    project.add_hardware_assignment(HardwareAssignment("H1", "C1", "handle_bar", 2))
    return project


def test_custom_library_persists_and_builtin_remains_unchanged(tmp_path):
    original = get_catalogue_item("base_2_door")
    item = _item()
    path = save_custom_catalogue([item], tmp_path / "library.json")
    loaded = load_custom_catalogue(path)
    assert loaded == [item]
    assert get_catalogue_item(item.type_id) == item
    assert get_catalogue_item("base_2_door") == original
    assert create_catalogue_cabinet(item.type_id, "C1").material == "Cashmere"


def test_custom_calculated_price_bom_resize_and_project_reopen(tmp_path):
    item = _item("SYNSTAGE9A")
    project = _project(item, _rule(item))
    assert project.quotation.unit_prices == {}
    initial = calculate_quotation(project)
    assert initial.lines[0].pricing_mode == "calculated"
    assert initial.lines[0].unit_price is not None
    assert any(row.name == "Door" for row in generate_project_bom(project))
    first = initial.total
    project.cabinets[0].width = 1000
    project.validate()
    assert calculate_quotation(project).total > first
    with pytest.raises(ValueError, match="supported range"):
        project.cabinets[0].width = 1300
        project.validate()
    project.cabinets[0].width = 1000
    reopened = load_project(save_project(project, tmp_path / "custom-project.json"))
    assert reopened.custom_catalogue == [item]
    assert calculate_quotation(reopened) == calculate_quotation(project)
    for path in (export_bom_template_xlsx(reopened, tmp_path / "bom.xlsx"),
                 export_bom_pdf(reopened, tmp_path / "bom.pdf"),
                 export_quotation_xlsx(reopened, tmp_path / "quote.xlsx"),
                 export_quotation_pdf(reopened, tmp_path / "quote.pdf"),
                 export_engineering_dxf(reopened, tmp_path / "panels.dxf", PANEL_OUTLINES)):
        assert path.stat().st_size > 100


def test_fixed_variant_not_reused_after_resize_and_missing_rates_incomplete():
    item = _item("SYNSTAGE9B")
    project = _project(item, _rule(item, mode="fixed"))
    assert calculate_quotation(project).lines[0].unit_price == Decimal("700.00")
    project.cabinets[0].width = 1000
    quote = calculate_quotation(project)
    assert quote.unpriced_ids == ("C1",)
    assert any("custom size" in reason for reason in quote.incomplete_reasons)
    project.cabinets[0].width = 900
    project.price_master.catalogue_rules = [_rule(item)]
    project.price_master.records = [row for row in project.price_master.records if row.record_id != "SYN-BOARD-18"]
    quote = calculate_quotation(project)
    assert quote.unpriced_ids == ("C1",)
    assert any("incomplete" in reason.lower() for reason in quote.incomplete_reasons)


def test_unapproved_library_rule_requires_review_before_quotation():
    item = _item("SYNSTAGE9D")
    project = _project(item, _rule(item, status="draft"))
    quote = calculate_quotation(project)
    assert quote.unpriced_ids == ("C1",)
    with pytest.raises(ValueError, match="Complete all billable"):
        issue_quotation_snapshot(project)


def test_edit_creates_immutable_revision_and_issued_quote_stays_frozen(tmp_path):
    first = _item("SYNSTAGE9C")
    project = _project(first, _rule(first))
    project.quotation.customer_name = "Synthetic customer"
    project.quotation.quotation_number = "SYN-9"
    issued = deepcopy(issue_quotation_snapshot(project))
    second = _item("SYNSTAGE9C", [first], name="Synthetic revised base", width=950)
    save_custom_catalogue([first, second], tmp_path / "library.json")
    assert second.revision == 2 and first.type_id != second.type_id
    assert get_catalogue_item(first.type_id) == first
    assert project.cabinets[0].cabinet_type_id == first.type_id
    assert project.quotation.issued_snapshot == issued
    reopened = load_project(save_project(project, tmp_path / "old-project.json"))
    assert reopened.cabinets[0].cabinet_type_id == first.type_id
    assert reopened.quotation.issued_snapshot == issued


def test_props_and_legacy_projects_remain_unchanged():
    project = Project.from_dict(Project.sample_kitchen().to_dict())
    assert project.custom_catalogue == []
    assert calculate_quotation(project).unpriced_ids  # no fabricated client price


def test_dialog_builds_pricing_on_same_screen(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from kuchhe7.ui.cabinet_library_dialog import CabinetLibraryDialog

    app = QApplication.instance() or QApplication([])
    dialog = CabinetLibraryDialog([], synthetic_setup())
    dialog.product_id_edit.setText("SYNSTAGE9UI")
    dialog.name_edit.setText("Synthetic UI base")
    dialog.template_combo.setCurrentIndex(dialog.template_combo.findData("base_2_door"))
    dialog.finish_combo.setCurrentText("Cashmere")
    dialog.profile_combo.setCurrentIndex(1)
    dialog.cost_basis_combo.setCurrentIndex(dialog.cost_basis_combo.findData("cut_area"))
    dialog.edge_wastage_edit.setText("5")
    dialog.approved_check.setChecked(True)
    item, rule = dialog.build()
    assert item.product_id == "SYNSTAGE9UI"
    assert rule.mode == "calculated" and rule.status == "approved"
    assert item.construction_profile["profile_id"] == "K7-DEMO-base_2_door"
    assert rule.cost_basis == "cut_area" and rule.edge_wastage_percent == "5"
    assert "SYN-BOARD-18" in dialog.preview.toPlainText()
    dialog.deleteLater()
    app.processEvents()


def test_main_window_addition_assigns_optional_handles_once_and_restarts(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("KUCHE7_CABINET_LIBRARY_PATH", str(tmp_path / "library.json"))
    monkeypatch.setenv("KUCHE7_PRICE_SETUP_PATH", str(tmp_path / "company.json"))
    from PySide6.QtWidgets import QApplication
    from kuchhe7.pricing_setup import save_company_price_setup
    from kuchhe7.ui.main_window import MainWindow

    item = _item("SYNSTAGE9WINDOW")
    save_custom_catalogue([item])
    master = synthetic_setup()
    master.catalogue_rules.append(_rule(item))
    save_company_price_setup(master)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = Project.empty("Synthetic window project")
    window.project.custom_catalogue = [item]
    apply_company_setup_to_new_project(window.project, master)
    window._apply_cabinet_addition(create_catalogue_cabinet(item.type_id, "C1", position_x=650, position_y=2500), True)
    assert len(window.project.hardware_assignments) == 1
    assert window.project.hardware_assignments[0].quantity == 2
    quote = calculate_quotation(window.project)
    assert quote.lines[0].unit_price == Decimal("486.58")
    window._apply_cabinet_addition(window.project.cabinets[0], False)
    assert window.project.hardware_assignments == []
    window.close()
    second = MainWindow()
    assert any(row.type_id == item.type_id for row in second.custom_library_items)
    second.close()
    app.processEvents()
