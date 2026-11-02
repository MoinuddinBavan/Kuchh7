"""Launch the real v0.8 engineering workspace and capture client-demo views."""

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
    window.select_cabinet("C1")
    window.show_manufacturing_preview()
    window.showMaximized()

    output = Path("demo_output")
    output.mkdir(parents=True, exist_ok=True)
    exploded_path = output / "kuchhe7-v0.8-exploded-cabinet.png"
    drawing_path = output / "kuchhe7-v0.8-component-drawing.png"
    drilling_path = output / "kuchhe7-v0.8-drilling-preview.png"

    def save(path: Path) -> bool:
        application.processEvents()
        pixmap = window.grab()
        return not pixmap.isNull() and pixmap.save(str(path), "PNG")

    def capture_exploded() -> None:
        preview = window.manufacturing_preview
        preview.select_component("Left side panel")
        preview.drawing_tabs.setCurrentIndex(0)
        if not save(exploded_path):
            application.exit(1)
            return
        preview.select_component("Door")
        QTimer.singleShot(1000, capture_drawing)

    def capture_drawing() -> None:
        if not save(drawing_path):
            application.exit(1)
            return
        preview = window.manufacturing_preview
        preview.hole_diameter_spin.setValue(5)
        preview.edge_offset_spin.setValue(37)
        preview.hole_pitch_spin.setValue(96)
        preview.hole_count_spin.setValue(4)
        preview.drawing_tabs.setCurrentIndex(1)
        QTimer.singleShot(900, capture_drilling)

    def capture_drilling() -> None:
        if not save(drilling_path):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(2400, capture_exploded)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
