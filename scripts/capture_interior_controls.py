"""Capture the real Design Studio's existing Interior and wall controls."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.models import Project
from kuchhe7.platform_support import ui_font_family
from kuchhe7.ui.main_window import MainWindow

from capture_ui_modernisation import capture


def main() -> int:
    output = Path("demo_output/version3_interior_controls")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    family = ui_font_family()
    app.setFont(QFont(family, 9))
    app.setStyleSheet(STYLE.replace("'Segoe UI'", f"'{family}'"))
    window = MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    original_project = window.project.to_dict()
    window.refresh_all(reset_camera=True)
    window.presentation_view_action.setChecked(True)
    window.view3d.view_presentation()

    capture(window, app, output / "interior_off_1600x900.png", 1600, 900)
    window.interior_view_button.click()
    capture(window, app, output / "interior_on_1600x900.png", 1600, 900)
    window.hide_room_walls_action.setChecked(True)
    capture(window, app, output / "interior_walls_hidden_1600x900.png", 1600, 900)
    window.hide_room_walls_action.setChecked(False)
    window.show_interior_action.setChecked(False)
    capture(window, app, output / "interior_restored_1600x900.png", 1600, 900)

    result = {
        "cabinet_count": len(window.project.cabinets),
        "opening_count": len(window.project.room.openings),
        "door_actors": window.view3d.door_actor_count,
        "shelf_actors": window.view3d.shelf_actor_count,
        "room_wall_actors": len(window.view3d._room_wall_actors),
        "doors_restored": window.view3d.doors_visible,
        "walls_restored": not window.hide_room_walls_action.isChecked(),
        "project_unchanged": window.project.to_dict() == original_project,
    }
    (output / "interior_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
