"""Capture the three v0.5 client-demo states from the real desktop window."""

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
    window.showMaximized()

    output = Path("demo_output")
    output.mkdir(parents=True, exist_ok=True)
    positioning_path = output / "kuchhe7-v0.5-positioning-preview.png"
    kitchen_path = output / "kuchhe7-v0.5-premium-kitchen.png"
    presentation_path = output / "kuchhe7-v0.5-presentation-repositioned.png"

    def save(path: Path) -> bool:
        application.processEvents()
        pixmap = window.screen().grabWindow(int(window.winId()))
        return not pixmap.isNull() and pixmap.save(str(path), "PNG")

    def capture_positioning() -> None:
        window.catalogue_category_combo.setCurrentText("Base Cabinets")
        window.catalogue_list.setCurrentRow(1)
        window.begin_catalogue_placement()
        window.plan_view.preview_model_position(250, 1800)
        if not save(positioning_path):
            application.exit(1)
            return
        window.plan_view.cancel_interaction(emit_signal=False)
        window.load_sample_kitchen()
        window.select_cabinet("C2")
        window.presentation_view_action.setChecked(False)
        window.view3d.view_isometric()
        window.view3d.fit_all_cabinets()
        QTimer.singleShot(1400, capture_kitchen)

    def capture_kitchen() -> None:
        if not save(kitchen_path):
            application.exit(1)
            return
        window.move_cabinet("C2", 950, 2850)
        window.presentation_view_action.setChecked(True)
        window.hide_room_walls_action.setChecked(False)
        window.view3d.view_presentation()
        QTimer.singleShot(1400, capture_presentation)

    def capture_presentation() -> None:
        if not save(presentation_path):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(2200, capture_positioning)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
