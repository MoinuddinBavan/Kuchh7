"""Capture the actual desktop UI with clearly SYNTHETIC catalogue-first prices."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.persistence import load_project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.price_master import CataloguePriceRule
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.main_window import CompanyPriceSetupDialog, MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    root = Path(__file__).resolve().parents[1]
    project = load_project(root / "tests" / "fixtures" / "stage7b2_synthetic_project.json")
    project.quotation.pricing_rules.clear()
    project.price_master.catalogue_rules = [CataloguePriceRule(
        "SYN-CAT-BASE", "base_2_door", "calculated", "INR", "2026-01-01",
        "approved", "Cashmere", markup_percent="20")]
    window = MainWindow()
    window.project = project
    window.refresh_all(reset_camera=True)
    window.show_documents()
    window.documents_workspace.tabs.setCurrentIndex(1)
    window.showMaximized()
    output = root / "demo_output"
    output.mkdir(exist_ok=True)

    def capture_before() -> None:
        app.processEvents()
        path = output / "stage7b3-before-900-synthetic.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Unable to capture {path}")
        print(f"BEFORE {calculate_quotation(window.project).total} INR {path}")
        window.width_spin.setValue(1200)
        QTimer.singleShot(900, capture_after)

    def capture_after() -> None:
        app.processEvents()
        if window.project.cabinet.width != 1200:
            raise RuntimeError("Cabinet width did not update through the desktop control")
        path = output / "stage7b3-after-1200-synthetic.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Unable to capture {path}")
        print(f"AFTER {calculate_quotation(window.project).total} INR {path}")
        setup_dialog = CompanyPriceSetupDialog(window)
        setup_dialog.project.price_master = deepcopy(window.project.price_master)
        setup_dialog.workspace.refresh()
        setup_dialog.workspace.master_page.setCurrentIndex(1)
        setup_dialog.workspace.rules_table.selectRow(0)
        setup_dialog.show()

        def capture_setup() -> None:
            app.processEvents()
            setup_path = output / "stage7b3-company-price-setup-synthetic.png"
            if not setup_dialog.grab().save(str(setup_path)):
                raise RuntimeError(f"Unable to capture {setup_path}")
            print(f"PRICE SETUP {setup_path}")
            setup_dialog.workspace.master_page.setCurrentIndex(0)
            setup_dialog.workspace.master_table.selectRow(0)
            app.processEvents()
            rates_path = output / "stage7b3-company-rates-synthetic.png"
            if not setup_dialog.grab().save(str(rates_path)):
                raise RuntimeError(f"Unable to capture {rates_path}")
            print(f"RATE RECORDS {rates_path}")
            setup_dialog.close()
            window.close()
            app.quit()

        QTimer.singleShot(700, capture_setup)

    QTimer.singleShot(1500, capture_before)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
