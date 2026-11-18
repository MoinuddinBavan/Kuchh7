"""Capture the actual Stage 5B desktop workspace and source 3D PNG."""

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
    window.load_complete_kitchen_demo()
    window.presentation_view_action.setChecked(True)
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output"
    output.mkdir(exist_ok=True)

    def capture() -> None:
        window.show_realistic_rendering()
        # Exercise the button while the 3D viewport is behind this tab.
        if not window.realistic_render_workspace.capture():
            raise RuntimeError(window.realistic_render_workspace.status_label.text())
        source = window.realistic_render_workspace.source_png
        if source is None:
            raise RuntimeError(window.realistic_render_workspace.status_label.text())
        source_path = output / "kuchhe7-stage5b-original-3d.png"
        source_path.write_bytes(source)
        app.processEvents()
        workspace_path = output / "kuchhe7-stage5b-rendering-workspace.png"
        if not window.grab().save(str(workspace_path)):
            raise RuntimeError(f"Could not capture {workspace_path}")
        print(source_path)
        print(workspace_path)
        window.view3d.plotter.close()
        window.close()
        app.quit()

    QTimer.singleShot(1400, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
