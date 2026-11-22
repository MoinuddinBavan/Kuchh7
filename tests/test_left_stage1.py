"""Behavior checks for the presentation-only left sidebar refresh."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from kuchhe7.models import Project
from kuchhe7.ui.main_window import MainWindow
from kuchhe7.ui.sidebar_cards import KIND_ROLE, PREVIEW_ROLE, cached_cabinet_preview


def _window():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    window.show()
    app.processEvents()
    return app, window


def test_cabinet_thumbnail_is_high_resolution_and_cached():
    QApplication.instance() or QApplication([])
    preview = cached_cabinet_preview("base_2_door", "Cashmere")
    assert not preview.isNull()
    assert preview.width() >= 300 and preview.height() >= 200
    assert cached_cabinet_preview("base_2_door", "Cashmere") is preview


def test_cabinet_cards_are_live_selectable_and_collapsible():
    app, window = _window()
    try:
        before = window.project.to_dict()
        assert window.cabinet_count_label.text() == "Cabinets (6)"
        assert len(window._cabinet_card_items) == 6
        assert all(item.data(PREVIEW_ROLE) is not None for item in window._cabinet_card_items)
        c2 = window._cabinet_card_items[1]
        window.object_list.itemClicked.emit(c2)
        app.processEvents()
        assert window.project.selected_cabinet_id == "C2"
        assert "C2" in window.inspector_title.text()
        assert window.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == "C2"
        window.cabinet_collapse_button.click()
        assert all(item.isHidden() for item in window._cabinet_card_items)
        window.cabinet_collapse_button.click()
        assert all(not item.isHidden() for item in window._cabinet_card_items)
        assert window.project.to_dict() == {**before, "selected_cabinet_id": "C2"}
    finally:
        window.close()


def test_appliance_cards_open_existing_library_and_other_objects_remain_accessible():
    app, window = _window()
    try:
        before = window.project.to_dict()
        appliances = window._appliance_card_items
        assert appliances and all(item.data(PREVIEW_ROLE) is not None for item in appliances)
        assert all(str(item.data(Qt.ItemDataRole.UserRole)).startswith("catalogue:")
                   for item in appliances)
        assert any(item.data(KIND_ROLE) == "object" and
                   str(item.data(Qt.ItemDataRole.UserRole)).startswith("opening:")
                   for item in (window.object_list.item(i)
                                for i in range(window.object_list.count())))
        assert window.object_list.horizontalScrollBar().maximum() == 0
        window.object_list.itemClicked.emit(appliances[0])
        app.processEvents()
        assert window.explorer_tabs.currentWidget() is window.library_page
        assert window.workspace_tabs.currentWidget() is window.workspace_splitter
        window.explorer_tabs.setCurrentWidget(window.explorer_tabs.widget(0))
        window.browse_library_button.click()
        assert window.explorer_tabs.currentWidget() is window.library_page
        assert window.project.to_dict() == before
    finally:
        window.close()
