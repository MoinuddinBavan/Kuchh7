"""Capture the native pricing workspace with clearly synthetic test rates."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.costing import PricingRule
from kuchhe7.models import Project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.price_master import PriceMaster, PriceRecord
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    window = MainWindow()
    project = Project.sample_kitchen("SYNTHETIC COSTING DEMO")
    project.price_master = PriceMaster([
        PriceRecord("SYN-B18", "Board", "Cashmere", "SYNTHETIC board rate, 18 mm", "m2", "100", "INR", "2026-01-01", "approved", "18", "2440", "1220", "SYNTHETIC test board specification"),
        PriceRecord("SYN-B6", "Board", "Cashmere", "SYNTHETIC back rate, 6 mm", "m2", "80", "INR", "2026-01-01", "approved", "6", specification="SYNTHETIC test back specification"),
        PriceRecord("SYN-H1", "Hardware", "Concealed hinge", "SYNTHETIC hinge rate", "each", "10", "INR", "2026-01-01", "approved"),
    ])
    project.quotation.currency = "INR"
    project.quotation.quotation_date = "2026-11-19"
    project.quotation.pricing_rules["C1"] = PricingRule(mode="calculated", approved=True, markup_percent="20")
    window.project = project
    window.refresh_all(reset_camera=True)
    window.show_documents()
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output"
    output.mkdir(exist_ok=True)

    def capture_master() -> None:
        window.documents_workspace.tabs.setCurrentIndex(2)
        app.processEvents()
        path = output / "kuchhe7-stage7b1-price-master-synthetic.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Cannot save {path}")
        print(path)
        QTimer.singleShot(700, capture_cost)

    def capture_cost() -> None:
        window.documents_workspace.tabs.setCurrentIndex(3)
        app.processEvents()
        path = output / "kuchhe7-stage7b1-cost-breakdown-synthetic.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Cannot save {path}")
        print(path)
        window.close()
        app.quit()

    QTimer.singleShot(1700, capture_master)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
