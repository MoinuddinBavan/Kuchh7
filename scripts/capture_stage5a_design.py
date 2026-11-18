"""Capture actual Stage 5A prompt, proposal and editable result on Windows."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.platform_support import ui_font_family
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    window = MainWindow()
    window.show_ai_design()
    window.ai_design_workspace.prompt_edit.setPlainText(
        "Modern L-shaped kitchen in Cashmere with a sink cabinet, wall cabinet and plant"
    )
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output"
    output.mkdir(exist_ok=True)

    def save(name: str) -> None:
        app.processEvents()
        path = output / f"kuchhe7-stage5a-{name}.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Could not capture {path}")
        print(path)

    def prompt() -> None:
        save("prompt-entry")
        window.ai_design_workspace.prompt_edit.setPlainText("U-shaped rotating kitchen with a 5000 mm cabinet")
        window.generate_design_proposal(window.ai_design_workspace.prompt_edit.toPlainText(), "replace")
        QTimer.singleShot(700, invalid_proposal)

    def invalid_proposal() -> None:
        save("unsupported-request")
        window.ai_design_workspace.prompt_edit.setPlainText("Compact straight kitchen in Warm White")
        window.generate_design_proposal(window.ai_design_workspace.prompt_edit.toPlainText(), "replace")
        QTimer.singleShot(700, straight_proposal)

    def straight_proposal() -> None:
        save("straight-proposal")
        window.ai_design_workspace.prompt_edit.setPlainText(
            "Modern L-shaped kitchen in Cashmere with a sink cabinet, wall cabinet and plant"
        )
        window.generate_design_proposal(window.ai_design_workspace.prompt_edit.toPlainText(), "replace")
        QTimer.singleShot(900, proposal)

    def proposal() -> None:
        save("validated-proposal")
        if not window.apply_design_proposal():
            raise RuntimeError("The empty-project demonstration proposal could not be applied")
        window.presentation_view_action.setChecked(True)
        window.select_cabinet("C3")
        window.width_spin.setValue(550)
        window.view3d.fit_all_cabinets()
        QTimer.singleShot(1300, final_result)

    def final_result() -> None:
        save("editable-2d-3d-result")
        window.view3d.plotter.close()
        window.close()
        app.quit()

    QTimer.singleShot(1500, prompt)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
