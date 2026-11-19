"""Capture real Windows UI workspaces with a synthetic, disposable project."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.platform_support import ui_font_family
from kuchhe7.ui.main_window import MainWindow
from scripts.validate_stage8_workflow import build_synthetic_project


def main() -> int:
    output = Path(__file__).resolve().parents[1] / "demo_output" / "stage8-synthetic"
    output.mkdir(parents=True, exist_ok=True)
    os.environ["KUCHE7_PRICE_SETUP_PATH"] = str(output / "disposable-company-setup.json")
    app = QApplication(sys.argv)
    app.setApplicationName("kuchhe7")
    app.setOrganizationName("AIZ INFOTECHS")
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    window = MainWindow()
    window.project, _company = build_synthetic_project()
    window.project.select_cabinet("C1")
    window.refresh_all(reset_camera=True)
    window.showMaximized()

    steps = [
        ("01-design-studio.png", lambda: window.workspace_tabs.setCurrentWidget(window.workspace_splitter)),
        ("02-furniture-library.png", lambda: window.explorer_tabs.setCurrentWidget(window.library_page)),
        ("02b-appliance-library.png", lambda: window.library_combo.setCurrentIndex(1)),
        ("02c-props-library.png", lambda: window.library_combo.setCurrentIndex(2)),
        ("02d-hardware-library.png", lambda: window.library_combo.setCurrentIndex(3)),
        ("03-presentation-view.png", lambda: (window.explorer_tabs.setCurrentIndex(0), window._set_presentation_view(True))),
        ("04-engineering-preview.png", window.show_manufacturing_preview),
        ("04b-drilling-preview.png", lambda: window.manufacturing_preview.drawing_tabs.setCurrentIndex(1)),
        ("05-sheet-nesting.png", window.show_sheet_nesting),
        ("05b-company-price-setup.png", lambda: (window.show_documents(), window.documents_workspace.tabs.setCurrentIndex(2))),
        ("06-cost-breakdown.png", lambda: (window.show_documents(), window.documents_workspace.tabs.setCurrentIndex(3))),
        ("07-bom-review.png", lambda: (window.show_documents(), window.documents_workspace.tabs.setCurrentIndex(0))),
        ("08-quotation.png", lambda: (window.show_documents(), window.documents_workspace.tabs.setCurrentIndex(1))),
    ]

    def take(index: int = 0) -> None:
        if index >= len(steps):
            window.close()
            app.quit()
            return
        name, action = steps[index]
        action()
        app.processEvents()

        def save() -> None:
            target = output / name
            if not window.grab().save(str(target)):
                raise RuntimeError(f"Could not capture {target}")
            print(target, flush=True)
            QTimer.singleShot(300, lambda: take(index + 1))

        QTimer.singleShot(750, save)

    QTimer.singleShot(1500, take)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
