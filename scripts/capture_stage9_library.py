"""Real Windows UI walkthrough using disposable SYNTHETIC company prices."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.catalogue import get_catalogue_item
from kuchhe7.document_exports import (export_bom_pdf, export_bom_template_xlsx,
                                       export_issued_quotation_pdf, export_issued_quotation_xlsx,
                                       export_quotation_pdf, export_quotation_xlsx)
from kuchhe7.engineering_dxf import PANEL_OUTLINES, export_engineering_dxf
from kuchhe7.models import Project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.persistence import load_project, save_project
from kuchhe7.pricing_setup import apply_company_setup_to_new_project, load_company_price_setup, save_company_price_setup
from kuchhe7.quotation import calculate_quotation, issue_quotation_snapshot
from kuchhe7.ui.cabinet_library_dialog import CabinetLibraryDialog
from kuchhe7.ui.main_window import MainWindow
from tests.test_stage7b3_catalogue_pricing import synthetic_setup


def main() -> int:
    output = (Path(sys.argv[1]) if len(sys.argv) > 1 else
              Path(__file__).resolve().parents[1] / "demo_output" / "stage9-synthetic")
    output.mkdir(parents=True, exist_ok=True)
    os.environ["KUCHE7_PRICE_SETUP_PATH"] = str(output / "company-prices.json")
    os.environ["KUCHE7_CABINET_LIBRARY_PATH"] = str(output / "cabinet-library.json")
    for name in ("company-prices.json", "cabinet-library.json"):
        # Use a unique disposable run directory if the caller wants to preserve old captures.
        if (output / name).exists():
            raise RuntimeError(f"Remove or choose a fresh disposable output directory before rerunning: {output / name}")
    save_company_price_setup(synthetic_setup())
    app = QApplication(sys.argv)
    app.setApplicationName("kuchhe7")
    app.setOrganizationName("AIZ INFOTECHS")
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    window = MainWindow()
    window.showMaximized()
    window.explorer_tabs.setCurrentWidget(window.library_page)

    def capture(widget, name):
        app.processEvents()
        QTest.qWait(250)
        path = output / name
        if not widget.grab().save(str(path)):
            raise RuntimeError(f"Could not capture {path}")
        print(path, flush=True)

    def fill_add():
        dialog = app.activeModalWidget()
        assert isinstance(dialog, CabinetLibraryDialog)
        dialog.product_id_edit.setText("SYNCLIENTBASE")
        dialog.name_edit.setText("Synthetic priced base")
        dialog.template_combo.setCurrentIndex(dialog.template_combo.findData("base_2_door"))
        dialog.finish_combo.setCurrentText("Cashmere")
        dialog.handle_spin.setValue(2)
        dialog.approved_check.setChecked(True)
        capture(dialog, "01-add-cabinet-details-pricing.png")
        dialog.tabs.setCurrentIndex(1)
        capture(dialog, "01b-add-cabinet-pricing.png")
        dialog._save_clicked()

    QTimer.singleShot(650, fill_add)
    window.create_library_cabinet()
    assert len(window.custom_library_items) == 1
    item = window.custom_library_items[0]
    capture(window, "02-custom-cabinet-in-library.png")

    window.project = Project.empty("Synthetic Stage 9 kitchen")
    window.project.custom_catalogue = list(window.custom_library_items)
    apply_company_setup_to_new_project(window.project, load_company_price_setup())
    window.refresh_all(reset_camera=True)
    window._place_catalogue_cabinet(item.type_id, 650, 2500)
    assert not calculate_quotation(window.project).unpriced_ids
    assert len(window.project.hardware_assignments) == 1
    window.project.quotation.customer_name = "SYNTHETIC customer"
    window.project.quotation.quotation_number = "SYN-STAGE9"
    window.refresh_all()
    capture(window, "03-placed-custom-cabinet.png")
    window.show_documents()
    window.documents_workspace.tabs.setCurrentIndex(0)
    capture(window, "03b-automatic-bom.png")
    window.documents_workspace.tabs.setCurrentIndex(1)
    capture(window, "04-automatic-quotation.png")
    before_resize = calculate_quotation(window.project).total
    issued = issue_quotation_snapshot(window.project)
    export_bom_template_xlsx(window.project, output / "custom-bom.xlsx")
    export_bom_pdf(window.project, output / "custom-bom.pdf")
    export_quotation_xlsx(window.project, output / "custom-draft-quotation.xlsx")
    export_quotation_pdf(window.project, output / "custom-draft-quotation.pdf")
    export_issued_quotation_xlsx(window.project, output / "custom-issued-quotation.xlsx")
    export_issued_quotation_pdf(window.project, output / "custom-issued-quotation.pdf")
    export_engineering_dxf(window.project, output / "custom-panels.dxf", PANEL_OUTLINES)
    window.project.cabinets[0].width = 1000
    window.project.validate()
    window.refresh_all()
    window.show_documents()
    window.documents_workspace.tabs.setCurrentIndex(1)
    assert calculate_quotation(window.project).total > before_resize
    assert window.project.quotation.issued_snapshot == issued
    capture(window, "04b-draft-after-resize-issued-frozen.png")
    save_project(window.project, output / "custom-project-after-resize.json")
    reopened = load_project(output / "custom-project-after-resize.json")
    assert calculate_quotation(reopened) == calculate_quotation(window.project)

    window.explorer_tabs.setCurrentWidget(window.library_page)
    for row in range(window.library_list.count()):
        if window.library_list.item(row).data(256) == item.type_id:
            window.library_list.setCurrentRow(row)
            break

    def fill_edit():
        dialog = app.activeModalWidget()
        assert isinstance(dialog, CabinetLibraryDialog)
        dialog.name_edit.setText("Synthetic priced base revision 2")
        dialog.width_spin.setValue(950)
        dialog.tabs.setCurrentIndex(1)
        capture(dialog, "05-edit-cabinet-pricing.png")
        dialog._save_clicked()

    QTimer.singleShot(650, fill_edit)
    window.edit_library_cabinet()
    assert len(window.custom_library_items) == 2
    assert get_catalogue_item(item.type_id).width == 900
    assert window.project.cabinets[0].cabinet_type_id == item.type_id
    assert window.project.quotation.issued_snapshot == issued
    capture(window, "06-revised-library-old-project-preserved.png")
    window.close()
    second = MainWindow()
    second.showMaximized()
    second.explorer_tabs.setCurrentWidget(second.library_page)
    assert len(second.custom_library_items) == 2
    for row in range(second.library_list.count()):
        if second.library_list.item(row).data(256) == second.custom_library_items[-1].type_id:
            second.library_list.setCurrentRow(row)
            break
    capture(second, "07-library-after-restart.png")
    second.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
