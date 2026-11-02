"""Capture the three v0.6 room-opening demonstration states."""

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
    window.load_sample_kitchen()
    window.showMaximized()

    output = Path("demo_output")
    output.mkdir(parents=True, exist_ok=True)
    drawing_path = output / "kuchhe7-v0.6-room-openings.png"
    door_path = output / "kuchhe7-v0.6-selected-door.png"
    presentation_path = output / "kuchhe7-v0.6-presentation-openings.png"

    def save(path: Path) -> bool:
        application.processEvents()
        pixmap = window.screen().grabWindow(int(window.winId()))
        return not pixmap.isNull() and pixmap.save(str(path), "PNG")

    def capture_room() -> None:
        window.presentation_view_action.setChecked(False)
        window.view3d.view_isometric()
        if not save(drawing_path):
            application.exit(1)
            return
        window.select_opening("D1")
        QTimer.singleShot(900, capture_door)

    def capture_door() -> None:
        if not save(door_path):
            application.exit(1)
            return
        window.presentation_view_action.setChecked(True)
        window.hide_room_walls_action.setChecked(False)
        window.view3d.view_presentation()
        QTimer.singleShot(1500, capture_presentation)

    def capture_presentation() -> None:
        if not save(presentation_path):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(2200, capture_room)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
