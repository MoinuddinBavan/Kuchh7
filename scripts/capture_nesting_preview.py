"""Launch the real v0.9 nesting workspace and capture client-demo views."""

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
    window.show_sheet_nesting()
    window.showMaximized()

    output = Path("demo_output")
    output.mkdir(parents=True, exist_ok=True)
    workspace_path = output / "kuchhe7-v0.9-nesting-workspace.png"
    sheet_path = output / "kuchhe7-v0.9-labeled-sheet.png"
    group_path = output / "kuchhe7-v0.9-material-group.png"
    warnings_path = output / "kuchhe7-v0.9-utilization-warnings.png"

    def save_widget(widget, path: Path) -> bool:
        application.processEvents()
        pixmap = widget.grab()
        return not pixmap.isNull() and pixmap.save(str(path), "PNG")

    def select_group(material: str, thickness: float) -> None:
        preview = window.sheet_nesting
        if preview.result is None:
            return
        for index, group in enumerate(preview.result.groups):
            if group.material == material and group.thickness_mm == thickness:
                preview.group_list.setCurrentRow(index)
                break

    def capture_workspace() -> None:
        select_group("Cashmere", 18)
        if not save_widget(window, workspace_path):
            application.exit(1)
            return
        QTimer.singleShot(500, capture_sheet)

    def capture_sheet() -> None:
        if not save_widget(window.sheet_nesting.sheet_view, sheet_path):
            application.exit(1)
            return
        select_group("Walnut", 18)
        QTimer.singleShot(500, capture_group)

    def capture_group() -> None:
        if not save_widget(window, group_path):
            application.exit(1)
            return
        preview = window.sheet_nesting
        preview.sheet_length_spin.setValue(700)
        preview.sheet_width_spin.setValue(500)
        preview.rotation_check.setChecked(False)
        preview.recalculate()
        select_group("Cashmere", 18)
        QTimer.singleShot(500, capture_warnings)

    def capture_warnings() -> None:
        if not save_widget(window, warnings_path):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(1400, capture_workspace)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
