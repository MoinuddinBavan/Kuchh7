"""Both VTK widgets must finalize before their Qt surfaces are destroyed."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtWidgets import QApplication

from kuchhe7.ui.main_window import MainWindow


def test_main_window_closes_cabinet_and_hidden_exploded_plotters_once(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    plotters = (window.view3d.plotter, window.manufacturing_preview.exploded_view.plotter)
    calls = [0, 0]
    for index, plotter in enumerate(plotters):
        original = plotter.close

        def close_once(original=original, index=index):
            calls[index] += 1
            original()

        monkeypatch.setattr(plotter, "close", close_once)
    window.close()
    window.close_3d_views()
    assert calls == [1, 1]
    window.deleteLater()
    app.processEvents()
