"""Capture the live-draft versus frozen-issued UI with a synthetic project."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.persistence import load_project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.quotation import issue_quotation_snapshot
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    project_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "stage7b2_synthetic_project.json"
    project = load_project(project_path)
    issue_quotation_snapshot(project)
    project.cabinet.width = 1200
    project.validate()
    window = MainWindow()
    window.project = project
    window.refresh_all(reset_camera=True)
    window.show_documents()
    window.documents_workspace.tabs.setCurrentIndex(1)
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output" / "stage7b2-draft-vs-issued-synthetic.png"
    output.parent.mkdir(exist_ok=True)

    def capture() -> None:
        app.processEvents()
        if not window.grab().save(str(output)):
            raise RuntimeError(f"Unable to capture {output}")
        print(output)
        window.close()
        app.quit()

    QTimer.singleShot(1500, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
