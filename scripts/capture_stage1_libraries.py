"""Launch the real Windows UI and capture the four Stage 1 library views."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.models import PlacedProduct
from kuchhe7.platform_support import ui_font_family
from kuchhe7.product_libraries import APPLIANCES, FURNITURE, HARDWARE, PROPS, get_product
from kuchhe7.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font_family = ui_font_family()
    app.setFont(QFont(font_family, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{font_family}'"))
    window = MainWindow()
    window.load_complete_kitchen_demo()
    for item_id, type_id, x, y in (("A1", "oven_freestanding", 1300, 900),
                                    ("P1", "plant_pot", 460, 2670)):
        definition = get_product(type_id)
        window.project.add_product(PlacedProduct(item_id, type_id, x, y, definition.elevation_z,
                                                 definition.width, definition.depth, definition.height))
    window.refresh_all(reset_camera=True)
    window.presentation_view_action.setChecked(True)
    window.explorer_tabs.setCurrentIndex(2)
    window.showMaximized()
    output = Path(__file__).resolve().parents[1] / "demo_output"
    output.mkdir(exist_ok=True)
    views = ((FURNITURE, "furniture"), (APPLIANCES, "appliances"),
             (PROPS, "props"), (HARDWARE, "hardware"))

    def capture(index: int = 0) -> None:
        if index == len(views):
            window.close()
            app.quit()
            return
        library, slug = views[index]
        window.library_combo.setCurrentText(library)
        if library == FURNITURE:
            window.library_family_combo.setCurrentText("Wardrobe")
            window.select_cabinet("C1")
        elif library == APPLIANCES:
            window.select_product("A1")
        elif library == PROPS:
            window.select_product("P1")
        else:
            window.select_cabinet("C1")
        app.processEvents()
        path = output / f"kuchhe7-stage1-{slug}.png"
        if not window.grab().save(str(path)):
            raise RuntimeError(f"Could not save screenshot: {path}")
        print(path)
        QTimer.singleShot(650, lambda: capture(index + 1))

    QTimer.singleShot(1800, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
