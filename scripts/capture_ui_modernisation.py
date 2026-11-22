"""Capture the existing native UI at client demonstration sizes for visual QA."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QToolBar, QToolButton

from kuchhe7.app import STYLE
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.product_libraries import PROPS, get_product
from kuchhe7.ui.main_window import MainWindow


def capture(window: MainWindow, app: QApplication, path: Path, width: int, height: int) -> dict:
    window.resize(width, height)
    window.show()
    app.processEvents()
    QTest.qWait(350)
    app.processEvents()
    window.grab().save(str(path))
    toolbar = window.findChild(QToolBar, "mainRibbon")
    export_button = window.findChild(QToolButton, "headerExport")
    properties = window.properties_dock.findChild(QScrollArea)
    return {
        "requested": [width, height],
        "actual": [window.width(), window.height()],
        "plan": [window.plan_view.width(), window.plan_view.height()],
        "model": [window.view3d.width(), window.view3d.height()],
        "explorer": window.explorer_dock.width(),
        "properties": window.properties_dock.width(),
        "bom_height": window.bom_dock.height(),
        "toolbar_height": toolbar.height(),
        "export_action_visible": export_button.isVisible() and export_button.geometry().right() <= toolbar.width(),
        "properties_horizontal_scroll": properties.horizontalScrollBar().maximum(),
    }


def main() -> int:
    phase = sys.argv[1]
    output = Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    family = ui_font_family()
    app.setFont(QFont(family, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{family}'"))
    window = MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    if "--props" in sys.argv[3:]:
        for index, (type_id, x, y) in enumerate((
            ("potted_green_plant", 300, 2650),
            ("flower_vase", 600, 2650),
            ("fruit_bowl", 1340, 2650),
            ("floor_plant", 3000, 1500),
        ), 1):
            item = get_product(type_id)
            window.project.add_product(PlacedProduct(
                f"P{index}", type_id, x, y, item.elevation_z,
                item.width, item.depth, item.height,
            ))
    window.refresh_all(reset_camera=True)
    window._set_presentation_view(True)
    window.view3d.view_presentation()
    metrics = {}
    for width, height in ((1920, 1080), (1600, 900), (1366, 768)):
        metrics[f"{width}x{height}"] = capture(
            window, app, output / f"{phase}_design_{width}x{height}.png", width, height,
        )
        if width == 1600:
            window.properties_dock.grab().save(str(output / f"{phase}_properties.png"))
    window.resize(1600, 900)
    if hasattr(window, "plan_toggle_button"):
        window.plan_toggle_button.click()
        capture(window, app, output / f"{phase}_plan_expanded.png", 1600, 900)
        window.plan_toggle_button.click()
    window.library_combo.setCurrentText(PROPS)
    window.explorer_tabs.setCurrentWidget(window.library_page)
    window.library_list.setCurrentRow(6)
    capture(window, app, output / f"{phase}_libraries.png", 1600, 900)
    window.workspace_tabs.setCurrentWidget(window.realistic_render_workspace)
    capture(window, app, output / f"{phase}_rendering.png", 1600, 900)
    for name, workspace in (
        ("manufacturing", window.manufacturing_preview),
        ("nesting", window.sheet_nesting),
        ("documents", window.documents_workspace),
        ("assistant", window.ai_design_workspace),
    ):
        window.workspace_tabs.setCurrentWidget(workspace)
        capture(window, app, output / f"{phase}_{name}.png", 1600, 900)
    (output / f"{phase}_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
