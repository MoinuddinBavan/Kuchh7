"""Quotation, document, compatibility, and manufacturing isolation checks."""

import os
import shutil
import subprocess
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from openpyxl import Workbook, load_workbook
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.document_exports import (ExcelLayout, export_bom_pdf, export_bom_template_xlsx,
                                       export_quotation_pdf, export_quotation_xlsx)
from kuchhe7.exports import export_front_elevation_dxf
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import get_product
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.main_window import MainWindow


def _product(type_id: str, item_id: str, x: int, y: int) -> PlacedProduct:
    item = get_product(type_id)
    return PlacedProduct(item_id, type_id, x, y, item.elevation_z,
                         item.width, item.depth, item.height)


def _quoted_project() -> Project:
    project = Project()
    project.add_product(_product("oven_freestanding", "A1", 100, 100))
    project.add_product(_product("plant_pot", "P1", 100, 1000))
    project.quotation.customer_name = "Example Customer"
    project.quotation.quotation_number = "DEMO-001"
    project.quotation.quotation_date = "2026-11-18"
    project.quotation.unit_prices = {"C1": "1000.00", "A1": "200.00"}
    project.quotation.billable_product_ids = ["A1"]
    project.quotation.discount_percent = "10"
    project.quotation.tax_percent = "5"
    project.validate()
    return project


def test_quotation_totals_and_explicit_billable_items():
    project = _quoted_project()
    result = calculate_quotation(project)
    assert [item.item_id for item in result.lines] == ["C1", "A1"]
    assert (result.subtotal, result.discount, result.taxable_amount,
            result.tax, result.total) == tuple(map(Decimal, ("1200", "120", "1080", "54", "1134")))
    project.quotation.billable_product_ids = []
    result = calculate_quotation(project)
    assert result.total == Decimal("945.00")
    assert result.lines[1].total is None
    assert generate_project_bom(project) == generate_project_bom(_quoted_project())


def test_unpriced_quote_is_incomplete_and_invalid_prices_are_rejected():
    project = _quoted_project()
    del project.quotation.unit_prices["C1"]
    assert calculate_quotation(project).unpriced_ids == ("C1",)
    project.quotation.unit_prices["C1"] = "-1"
    with pytest.raises(ValueError, match="non-negative"):
        project.validate()
    project.quotation.unit_prices["C1"] = "NaN"
    with pytest.raises(ValueError, match="finite"):
        project.validate()
    project.quotation.unit_prices["C1"] = "1000"
    project.quotation.tax_percent = "101"
    with pytest.raises(ValueError, match="cannot exceed"):
        project.validate()


def test_props_cannot_be_priced_and_never_enter_quote_after_reopen(tmp_path):
    project = _quoted_project()
    original_bom = generate_project_bom(project)
    original_nesting = nest_project(project).eligible_count
    project.add_product(_product("ceramic_vase", "P2", 500, 1000))
    project.placed_products[2].height += 20
    reopened = load_project(save_project(project, tmp_path / "quote.json"))
    assert [line.item_id for line in calculate_quotation(reopened).lines] == ["C1", "A1"]
    assert generate_project_bom(reopened) == original_bom
    assert nest_project(reopened).eligible_count == original_nesting
    assert reopened.quotation.customer_name == "Example Customer"
    assert reopened.quotation.unit_prices == project.quotation.unit_prices
    reopened.quotation.unit_prices["P1"] = "1"
    with pytest.raises(ValueError, match="Decorative props"):
        reopened.validate()


def test_legacy_project_without_quotation_field_opens():
    data = Project().to_dict()
    del data["quotation"]
    project = Project.from_dict(data)
    assert project.quotation.unit_prices == {}
    assert calculate_quotation(project).unpriced_ids == ("C1",)


def test_deleted_items_cannot_silently_transfer_saved_prices_to_new_ids():
    project = _quoted_project()
    project.remove_product("A1")
    project.remove_cabinet("C1")
    assert project.next_product_id("Appliances, Sinks & Taps") == "A2"
    assert project.next_cabinet_id() == "C2"
    assert calculate_quotation(project).lines == ()


def test_excel_documents_and_template_match_calculations(tmp_path):
    project = _quoted_project()
    bom = generate_project_bom(project)
    template = Workbook()
    template.active.title = "Client BOM"
    template.active["A25"] = "KEEP THIS CLIENT CELL"
    template_path = tmp_path / "template.xlsx"
    template.save(template_path)
    bom_path = export_bom_template_xlsx(project, tmp_path / "bom.xlsx", template_path=template_path,
                                         layout=ExcelLayout("Client BOM", 7))
    sheet = load_workbook(bom_path, data_only=True)["Client BOM"]
    assert sheet["A25"].value == "KEEP THIS CLIENT CELL"
    assert sheet["A8"].value == bom[0].name
    assert sheet["F8"].value == bom[0].quantity
    quote = load_workbook(export_quotation_xlsx(project, tmp_path / "quote.xlsx"), data_only=True)["Quotation"]
    assert quote["D2"].value == "Example Customer"
    assert quote["F6"].value == 1000
    assert quote["F7"].value == 200
    values = [cell.value for cell in quote["F"]]
    assert 1134 in values


def test_pdf_documents_contain_values_and_existing_dxf_works(tmp_path):
    project = _quoted_project()
    bom = export_bom_pdf(project, tmp_path / "bom.pdf")
    quote = export_quotation_pdf(project, tmp_path / "quote.pdf")
    assert bom.read_bytes().startswith(b"%PDF")
    assert quote.read_bytes().startswith(b"%PDF")
    if shutil.which("pdftotext"):
        bom_text = subprocess.check_output(["pdftotext", "-raw", str(bom), "-"], text=True)
        quote_text = subprocess.check_output(["pdftotext", "-raw", str(quote), "-"], text=True)
        assert "Left side panel" in bom_text
        assert "Example Customer" in quote_text
        assert "1134.00" in quote_text
    dxf = ezdxf.readfile(export_front_elevation_dxf(project, tmp_path / "elevation.dxf"))
    assert dxf.header["$INSUNITS"] == 4


def test_documents_workspace_tracks_active_project_and_edits_quote():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = _quoted_project()
    window.refresh_all()
    window.show_documents()
    docs = window.documents_workspace
    assert docs.bom_table.rowCount() == len(generate_project_bom(window.project))
    assert docs.quote_table.rowCount() == 2
    assert "1134.00" in docs.totals_label.text()
    docs.customer_edit.setText("Changed Customer")
    docs._update_field("customer_name", docs.customer_edit)
    assert window.project.quotation.customer_name == "Changed Customer"
    assert window._dirty
    docs._set_billable("A1", False)
    assert calculate_quotation(window.project).total == Decimal("945.00")
    window.workspace_tabs.setCurrentIndex(0)
    assert window.plan_view is not None and window.view3d is not None
    window.close()
