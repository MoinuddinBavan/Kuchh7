"""Capture the v0.4.2 technical CAD and premium presentation views."""

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
    window.select_cabinet("C2")
    window.showMaximized()

    output = Path("demo_output")
    output.mkdir(parents=True, exist_ok=True)
    cad_path = output / "kuchhe7-v0.4.2-technical-cad.png"
    presentation_path = output / "kuchhe7-v0.4.2-presentation.png"

    def capture_cad() -> None:
        window.presentation_view_action.setChecked(False)
        window.view3d.view_isometric()
        window.view3d.fit_all_cabinets()
        application.processEvents()
        pixmap = window.screen().grabWindow(int(window.winId()))
        if pixmap.isNull() or not pixmap.save(str(cad_path), "PNG"):
            application.exit(1)
            return
        window.presentation_view_action.setChecked(True)
        window.hide_room_walls_action.setChecked(False)
        window.view3d.view_presentation()
        QTimer.singleShot(1400, capture_presentation)

    def capture_presentation() -> None:
        pixmap = window.screen().grabWindow(int(window.winId()))
        if pixmap.isNull() or not pixmap.save(str(presentation_path), "PNG"):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(2600, capture_cad)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
