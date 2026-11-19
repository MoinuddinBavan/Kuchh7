"""Capture a Windows desktop walkthrough with SYNTHETIC company prices only."""

from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.models import Project
from kuchhe7.persistence import load_project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.price_master import CataloguePriceRule
from kuchhe7.pricing_refresh import apply_company_price_refresh, preview_company_price_refresh
from kuchhe7.pricing_setup import save_company_price_setup
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.main_window import MainWindow
from kuchhe7.ui.pricing_refresh_dialog import PricingRefreshDialog


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / "demo_output"
    output.mkdir(exist_ok=True)
    os.environ["KUCHE7_PRICE_SETUP_PATH"] = str(output / "stage7b4-company-synthetic.json")
    app = QApplication(sys.argv)
    app.setApplicationName("kuchhe7")
    app.setOrganizationName("AIZ INFOTECHS")
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    project = load_project(root / "tests" / "fixtures" / "stage7b2_synthetic_project.json")
    project.quotation.pricing_rules.clear()  # catalogue rule supplies this demonstration price
    project.price_master.catalogue_rules = [CataloguePriceRule(
        "SYN-BASE", "base_2_door", "calculated", "INR", "2026-01-01",
        "approved", "Cashmere", markup_percent="20")]
    company = deepcopy(project.price_master)
    company.records[0].rate = "200"
    save_company_price_setup(company)
    window = MainWindow()
    window.project = project
    window.refresh_all(reset_camera=True)
    window.show_documents()
    window.documents_workspace.tabs.setCurrentIndex(1)
    window.showMaximized()

    def save_image(widget, name: str) -> None:
        app.processEvents()
        path = output / name
        if not widget.grab().save(str(path)):
            raise RuntimeError(f"Unable to capture {path}")
        print(path)

    def before() -> None:
        print(f"BEFORE {calculate_quotation(window.project).total} INR")
        save_image(window, "stage7b4-before-company-refresh-synthetic.png")
        preview = preview_company_price_refresh(window.project, company)
        dialog = PricingRefreshDialog(preview, window)
        dialog.show()

        def show_preview() -> None:
            save_image(dialog, "stage7b4-company-refresh-review-synthetic.png")
            dialog.close()
            apply_company_price_refresh(window.project, preview)
            window.refresh_all()
            window.documents_workspace.tabs.setCurrentIndex(1)
            QTimer.singleShot(550, after)

        QTimer.singleShot(550, show_preview)

    def after() -> None:
        print(f"AFTER {calculate_quotation(window.project).total} INR")
        save_image(window, "stage7b4-after-company-refresh-synthetic.png")
        window.documents_workspace.tabs.setCurrentIndex(3)
        QTimer.singleShot(550, cost)

    def cost() -> None:
        save_image(window, "stage7b4-cost-breakdown-synthetic.png")
        window.project = Project.complete_kitchen_demo("SYNTHETIC plan-label review")
        window.refresh_all(reset_camera=True)
        window.workspace_tabs.setCurrentWidget(window.workspace_splitter)
        QTimer.singleShot(700, plan)

    def plan() -> None:
        save_image(window, "stage7b4-complete-kitchen-plan.png")
        window.close()
        app.quit()

    QTimer.singleShot(1500, before)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
