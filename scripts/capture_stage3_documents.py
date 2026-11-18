"""Capture Stage 3 desktop screens and illustrative document outputs."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.document_exports import (export_bom_pdf, export_bom_template_xlsx,
                                       export_quotation_pdf, export_quotation_xlsx)
from kuchhe7.models import Project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    window = MainWindow()
    window.project = Project.complete_kitchen_demo("AIZ Complete Kitchen Demo")
    quote = window.project.quotation
    quote.customer_name = "Example Client — demonstration"
    quote.quotation_number = "DEMO-2026-001"
    quote.quotation_date = "2026-11-18"
    quote.discount_percent = "5"
    quote.tax_percent = "0"
    quote.unit_prices = {cabinet.cabinet_id: str(1000 + index * 250)
                         for index, cabinet in enumerate(window.project.cabinets)}
    window.refresh_all(reset_camera=True)
    window.show_documents()
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output"
    output.mkdir(exist_ok=True)
    documents = {
        "kuchhe7-stage3-sample-bom.xlsx": export_bom_template_xlsx,
        "kuchhe7-stage3-sample-bom.pdf": export_bom_pdf,
        "kuchhe7-stage3-sample-quotation.xlsx": export_quotation_xlsx,
        "kuchhe7-stage3-sample-quotation.pdf": export_quotation_pdf,
    }
    for name, exporter in documents.items():
        path = exporter(window.project, output / name)
        print(path)

    def capture() -> None:
        app.processEvents()
        bom = output / "kuchhe7-stage3-bom-review.png"
        if not window.grab().save(str(bom)):
            raise RuntimeError(f"Unable to capture {bom}")
        print(bom)
        window.documents_workspace.tabs.setCurrentIndex(1)
        QTimer.singleShot(900, capture_quote)

    def capture_quote() -> None:
        app.processEvents()
        quote_path = output / "kuchhe7-stage3-quotation.png"
        if not window.grab().save(str(quote_path)):
            raise RuntimeError(f"Unable to capture {quote_path}")
        print(quote_path)
        window.close()
        app.quit()

    QTimer.singleShot(1400, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
