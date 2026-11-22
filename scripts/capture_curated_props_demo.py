"""Capture local client-demo screenshots; no AI or project file writes."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.models import PlacedProduct, Project
from kuchhe7.product_libraries import PROPS, get_product
from kuchhe7.ui.main_window import MainWindow


POSITIONS = {
    "potted_green_plant": (300, 2650),
    "flower_vase": (600, 2650),
    "floor_plant": (3000, 1500),
    "decorative_vase": (1110, 2650),
    "fruit_bowl": (1340, 2650),
    "utensil_holder": (1710, 2650),
    "decorative_tray": (1960, 2650),
    "small_sculpture": (1150, 2900),
}


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "demo_output/curated_props")
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    window.resize(1800, 1000)
    window.show()
    window.workspace_tabs.setCurrentIndex(0)
    window._set_presentation_view(True)
    window.refresh_visuals(reset_camera=True)
    window.view3d.view_presentation()
    QTest.qWait(700)
    window.grab().save(str(destination / "kitchen_without_props.png"))

    for index, (type_id, (x, y)) in enumerate(POSITIONS.items(), 1):
        definition = get_product(type_id)
        window.project.add_product(PlacedProduct(
            f"P{index}", type_id, x, y, definition.elevation_z,
            definition.width, definition.depth, definition.height,
        ))
    window.selected_product_id = None
    window.refresh_visuals(reset_camera=True)
    window.view3d.view_presentation()
    QTest.qWait(900)
    window.grab().save(str(destination / "kitchen_with_props.png"))
    window.library_combo.setCurrentText(PROPS)
    window.explorer_tabs.setCurrentWidget(window.library_page)
    window.library_list.setCurrentRow(6)
    QTest.qWait(300)
    window.grab().save(str(destination / "decorative_props_library.png"))
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
