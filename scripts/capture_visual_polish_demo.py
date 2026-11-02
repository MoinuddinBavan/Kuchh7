"""Capture the four client-facing v0.7.1 visual-polish states."""

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    application = QApplication([])
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window.select_cabinet("C2")
    window.presentation_view_action.setChecked(True)
    window.showMaximized()

    output = Path("demo_output")
    output.mkdir(parents=True, exist_ok=True)
    premium_path = output / "kuchhe7-v0.7.1-premium-kitchen.png"
    maximized_path = output / "kuchhe7-v0.7.1-maximized-3d.png"
    sink_path = output / "kuchhe7-v0.7.1-sink-countertop.png"
    combined_path = output / "kuchhe7-v0.7.1-combined-workspace.png"

    def save(path: Path) -> bool:
        application.processEvents()
        pixmap = window.grab()
        return not pixmap.isNull() and pixmap.save(str(path), "PNG")

    def capture_premium() -> None:
        window.workspace_splitter.setSizes([500, 850])
        window.view3d.view_presentation()
        if not save(premium_path):
            application.exit(1)
            return
        window.maximize_3d_action.setChecked(True)
        QTimer.singleShot(1200, capture_maximized)

    def capture_maximized() -> None:
        window.view3d.view_presentation()
        if not save(maximized_path):
            application.exit(1)
            return
        window.view3d.plotter.camera_position = [
            (2780, -1180, 1500),
            (1720, 255, 650),
            (0, 0, 1),
        ]
        window.view3d.plotter.camera.view_angle = 24
        window.view3d.plotter.reset_camera_clipping_range()
        window.view3d.plotter.render()
        QTimer.singleShot(1000, capture_sink)

    def capture_sink() -> None:
        if not save(sink_path):
            application.exit(1)
            return
        window.maximize_3d_action.setChecked(False)
        window.workspace_splitter.setSizes([710, 640])
        window.select_cabinet("C4")
        window.view3d.view_presentation()
        QTimer.singleShot(1200, capture_combined)

    def capture_combined() -> None:
        if not save(combined_path):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(2400, capture_premium)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
