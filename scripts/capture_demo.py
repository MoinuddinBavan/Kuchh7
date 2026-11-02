"""Launch v0.4.1 and capture the catalogue and premium sample presentations."""

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    application = QApplication([])
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    window = MainWindow()
    window.showMaximized()

    catalogue_path = Path("demo_output/kuchhe7-v0.4.1-catalogue.png")
    sample_path = Path("demo_output/kuchhe7-v0.4.1-premium-sample.png")
    catalogue_path.parent.mkdir(parents=True, exist_ok=True)

    def capture_catalogue() -> None:
        window.explorer_tabs.setCurrentIndex(1)
        window.catalogue_category_combo.setCurrentIndex(0)
        window.resizeDocks([window.explorer_dock], [420], Qt.Orientation.Horizontal)
        application.processEvents()
        pixmap = window.screen().grabWindow(int(window.winId()))
        if pixmap.isNull() or not pixmap.save(str(catalogue_path), "PNG"):
            application.exit(1)
            return
        window.load_sample_kitchen()
        window.explorer_tabs.setCurrentIndex(0)
        window.resizeDocks([window.explorer_dock], [330], Qt.Orientation.Horizontal)
        window.select_cabinet("C2")
        window.view3d.view_isometric()
        window.view3d.fit_all_cabinets()
        QTimer.singleShot(1200, capture_sample)

    def capture_sample() -> None:
        pixmap = window.screen().grabWindow(int(window.winId()))
        if pixmap.isNull() or not pixmap.save(str(sample_path), "PNG"):
            application.exit(1)
            return
        application.quit()

    QTimer.singleShot(2500, capture_catalogue)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
