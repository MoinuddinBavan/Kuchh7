"""Launch the real v0.7 window and capture the complete kitchen views."""

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
    window.showMaximized()

    output = Path("demo_output")
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / "kuchhe7-v0.7-complete-plan.png"
    technical_path = output / "kuchhe7-v0.7-complete-technical.png"
    presentation_path = output / "kuchhe7-v0.7-complete-presentation.png"
    base_run_path = output / "kuchhe7-v0.7-connected-base-run.png"

    def save(path: Path) -> bool:
        application.processEvents()
        pixmap = window.grab()
        return not pixmap.isNull() and pixmap.save(str(path), "PNG")

    def capture_plan() -> None:
        window.presentation_view_action.setChecked(False)
        window.workspace_splitter.setSizes([930, 420])
        window.view3d.view_isometric()
        if not save(plan_path):
            application.exit(1)
            return
        window.workspace_splitter.setSizes([500, 850])
        QTimer.singleShot(900, capture_technical)

    def capture_technical() -> None:
        window.view3d.view_isometric()
        if not save(technical_path):
            application.exit(1)
            return
        window.presentation_view_action.setChecked(True)
        window.hide_room_walls_action.setChecked(False)
        window.view3d.view_presentation()
        QTimer.singleShot(1400, capture_presentation)

    def capture_presentation() -> None:
        if not save(presentation_path):
            application.exit(1)
            return
        window.view3d.plotter.camera_position = [
            (2850, -1650, 1780),
            (1100, 260, 620),
            (0, 0, 1),
        ]
        window.view3d.plotter.camera.view_angle = 25
        window.view3d.plotter.render()
        QTimer.singleShot(1000, capture_base_run)

    def capture_base_run() -> None:
        if not save(base_run_path):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(2200, capture_plan)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
