"""Focused UI checks for the right inspector; project rules live in existing tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from kuchhe7.app import STYLE
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.product_libraries import get_product
from kuchhe7.ui.main_window import MainWindow


def _window():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    window.show()
    app.processEvents()
    return app, window


def test_cabinet_inspector_tracks_selection_and_switches_content_without_editing_project():
    app, window = _window()
    try:
        window.select_cabinet("C2")
        before = window.project.to_dict()
        assert window.cabinet_id_label.text() == "C2"
        assert window.project.selected_cabinet.material in window.cabinet_category_label.text()
        assert window.cabinet_group.isVisible()
        assert not window.inspector_thumbnail.pixmap().isNull()
        window._show_inspector_tab("material")
        app.processEvents()
        assert window.material_card.isVisible()
        assert not window.position_card.isVisible()
        window._show_inspector_tab("details")
        app.processEvents()
        assert window.configuration_card.isVisible()
        assert not window.dimensions_card.isVisible()
        window._show_inspector_tab("properties")
        app.processEvents()
        assert window.position_card.isVisible() and window.dimensions_card.isVisible()
        assert window.project.to_dict() == before
    finally:
        window.close()


def test_opening_room_and_wall_selection_never_show_stale_cabinet_editor():
    app, window = _window()
    try:
        before = window.project.to_dict()
        for opening_id, kind in (("D1", "Door"), ("W1", "Window")):
            window.select_opening(opening_id)
            app.processEvents()
            assert window.opening_group.isVisible()
            assert not window.cabinet_group.isVisible()
            assert window.cabinet_id_label.text() == opening_id
            assert window.cabinet_type_label.text() == kind
            assert not window.inspector_thumbnail.pixmap().isNull()
            assert window.opening_swing_combo.isVisible() == (kind == "Door")
        window.select_wall("WEST")
        app.processEvents()
        assert window.room_group.isVisible() and not window.cabinet_group.isVisible()
        assert window.cabinet_id_label.text() == "WEST"
        room_item = window.project_tree.topLevelItem(0).child(0)
        assert room_item.data(0, Qt.ItemDataRole.UserRole) == "room"
        window._tree_item_clicked(room_item)
        app.processEvents()
        assert window.cabinet_type_label.text() == "Room"
        assert window.room_width_spin.isVisible()
        assert window.project.to_dict() == before
    finally:
        window.close()


def test_cabinet_configuration_uses_visible_fields_only():
    app, window = _window()
    try:
        window.select_cabinet("C1")
        app.processEvents()
        assert window.door_field.isVisible()
        assert window.shelf_field.isVisible()
        assert not window.drawer_field.isVisible()
        window.select_cabinet("C2")
        app.processEvents()
        assert window.drawer_field.isVisible()
        assert not window.door_field.isVisible()
    finally:
        window.close()


def test_placed_product_identity_and_controls_replace_cabinet_inspector():
    app, window = _window()
    try:
        definition = get_product("plant_pot")
        product = PlacedProduct("P1", definition.type_id, 120, 500, definition.elevation_z,
                                definition.width, definition.depth, definition.height)
        window.project.add_product(product)
        window.refresh_all()
        before = window.project.to_dict()
        window.select_product("P1")
        app.processEvents()
        assert window.product_group.isVisible()
        assert not window.cabinet_group.isVisible()
        assert window.cabinet_id_label.text() == "P1"
        assert window.cabinet_type_label.text() == definition.name
        assert not window.inspector_thumbnail.pixmap().isNull()
        assert window.product_x_spin.value() == product.position_x
        assert window.project.to_dict() == before
    finally:
        window.close()
