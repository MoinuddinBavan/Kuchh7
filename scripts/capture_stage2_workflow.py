"""Capture the Stage 2 library, edit, duplicate and validation workflow on Windows."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.platform_support import ui_font_family
from kuchhe7.product_libraries import APPLIANCES, PROPS
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = ui_font_family()
    app.setFont(QFont(font, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font}'"))
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window._place_product("oven_freestanding", 1300, 900)
    window._place_product("plant_pot", 460, 2670)
    window.presentation_view_action.setChecked(True)
    window.explorer_tabs.setCurrentWidget(window.library_page)
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output"
    output.mkdir(exist_ok=True)

    def save(name: str) -> None:
        app.processEvents()
        path = output / f"kuchhe7-stage2-{name}.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Could not capture {path}")
        print(path)

    def first() -> None:
        window.library_combo.setCurrentText(APPLIANCES)
        window.library_category_combo.setCurrentText("Cooking")
        window.select_product("A1")
        window.view3d.fit_all_cabinets()
        save("browse-and-edit")
        QTimer.singleShot(650, second)

    def second() -> None:
        window.duplicate_selected_object()
        window.view3d.fit_all_cabinets()
        save("duplicated-product")
        QTimer.singleShot(650, third)

    def third() -> None:
        window.library_combo.setCurrentText(PROPS)
        window.select_product("P1")
        save("visual-only-prop")
        QTimer.singleShot(650, fourth)

    def fourth() -> None:
        window.plan_view.begin_product_placement("fridge_tall")
        view = window.plan_view
        collision = view.mapFromScene(view._ox + 650 * view._scale,
                                      view._oy + 2850 * view._scale)
        QTest.mouseMove(view.viewport(), collision)
        save("collision-preview")
        window.close()
        app.quit()

    QTimer.singleShot(1800, first)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
