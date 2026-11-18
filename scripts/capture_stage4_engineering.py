"""Generate sample DXFs and capture the native export dialog plus DXF previews."""

from __future__ import annotations

import sys
from pathlib import Path

import ezdxf
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.engineering_dxf import DRAWING_TYPES, export_engineering_dxf
from kuchhe7.models import Project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.ui.engineering_export_dialog import EngineeringExportDialog
from kuchhe7.ui.main_window import MainWindow


def render_dxf(path: Path, png: Path) -> None:
    """Render the actual DXF with ezdxf; this is not an external CAM import test."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    drawing = ezdxf.readfile(path)
    figure, axes = plt.subplots(figsize=(15, 10))
    Frontend(RenderContext(drawing), MatplotlibBackend(axes),
             config=Configuration(background_policy=BackgroundPolicy.WHITE)).draw_layout(drawing.modelspace())
    axes.set_aspect("equal")
    axes.autoscale()
    axes.set_axis_off()
    figure.savefig(png, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    window = MainWindow()
    window.project = Project.complete_kitchen_demo("AIZ Complete Kitchen Demo")
    window.refresh_all(reset_camera=True)
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output"
    output.mkdir(exist_ok=True)
    for drawing_type in DRAWING_TYPES:
        path = export_engineering_dxf(window.project, output / f"kuchhe7-stage4-{drawing_type}.dxf", drawing_type)
        image_path = output / f"kuchhe7-stage4-{drawing_type}-preview.png"
        render_dxf(path, image_path)
        print(path)
        print(image_path)

    dialog = EngineeringExportDialog(window)
    dialog.drawing_combo.setCurrentIndex(4)
    dialog.show()

    def capture() -> None:
        app.processEvents()
        path = output / "kuchhe7-stage4-engineering-export-dialog.png"
        if not dialog.grab().save(str(path)):
            raise RuntimeError(f"Could not capture {path}")
        print(path)
        dialog.close()
        window.view3d.plotter.close()
        window.close()
        app.quit()

    QTimer.singleShot(1300, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
