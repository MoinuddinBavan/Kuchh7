"""Regressions for two confirmed Stage 6 presentation defects."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.ui.main_window import MainWindow


def test_workspace_brand_caption_fits_and_exploded_view_is_legible():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = MainWindow(start_empty=False)
    window.show()
    try:
        for index in range(window.workspace_tabs.count()):
            window.workspace_tabs.setCurrentIndex(index)
            app.processEvents()
            caption = window.header_workspace_caption
            assert caption.toolTip() == window.workspace_tabs.tabText(index).upper()
            assert caption.fontMetrics().horizontalAdvance(caption.text()) <= caption.width()
        window.manufacturing_preview.exploded_view.update_cabinet(
            window.project.selected_cabinet, window.manufacturing_preview.components
        )
        app.processEvents()
        assert window.manufacturing_preview.exploded_view.plotter.camera.view_angle < 20
    finally:
        window.close()
