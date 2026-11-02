"""Capture the final v1.0 client-approval views from the native application."""

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
    premium_path = output / "kuchhe7-v1.0-premium-kitchen.png"
    engineering_path = output / "kuchhe7-v1.0-exploded-engineering.png"
    nesting_path = output / "kuchhe7-v1.0-sheet-nesting.png"

    def save(path: Path) -> bool:
        application.processEvents()
        pixmap = window.grab()
        return not pixmap.isNull() and pixmap.save(str(path), "PNG")

    def capture_premium() -> None:
        window.workspace_tabs.setCurrentWidget(window.workspace_splitter)
        window.presentation_view_action.setChecked(True)
        window.view3d.view_presentation()
        QTimer.singleShot(1200, save_premium)

    def save_premium() -> None:
        if not save(premium_path):
            application.exit(1)
            return
        window.select_cabinet("C1")
        window.show_manufacturing_preview()
        window.manufacturing_preview.select_component("Door")
        window.manufacturing_preview.drawing_tabs.setCurrentIndex(0)
        QTimer.singleShot(900, capture_engineering)

    def capture_engineering() -> None:
        if not save(engineering_path):
            application.exit(1)
            return
        window.show_sheet_nesting()
        preview = window.sheet_nesting
        if preview.result is not None:
            for index, group in enumerate(preview.result.groups):
                if group.material == "Cashmere" and group.thickness_mm == 18:
                    preview.group_list.setCurrentRow(index)
                    break
        QTimer.singleShot(600, capture_nesting)

    def capture_nesting() -> None:
        if not save(nesting_path):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(1600, capture_premium)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
