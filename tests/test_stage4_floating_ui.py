"""Stage 4 checks for the live floating plan and viewport control strip."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

from kuchhe7.app import STYLE
from kuchhe7.models import Project
from kuchhe7.ui.main_window import MainWindow


def _window():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(STYLE)
    window = MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    window.show()
    application.processEvents()
    return application, window


def test_compact_plan_is_live_readable_and_clears_toolbar_at_small_size():
    application, window = _window()
    try:
        for width, height in ((1366, 768), (1600, 900), (1920, 1080)):
            window.resize(width, height)
            application.processEvents()
            plan = window.plan_panel.geometry()
            controls_widget = window.viewport_view_button.parentWidget()
            controls = controls_widget.geometry()
            assert window.plan_room_dimensions.text() == "3,600 × 3,200 mm"
            assert not window.plan_panel.mask().isEmpty()
            if window.design_stage.width() >= plan.right() + controls.width() + 12:
                assert not plan.intersects(controls)
            else:
                # Qt's offscreen screen can cap a requested top-level window;
                # icon-only controls remain usable when two cards cannot fit.
                assert all(button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
                           for button in controls_widget.findChildren(QToolButton))
            assert window.plan_view.scene().items()
            if width == 1366:
                assert plan.width() <= 220
        compact_width = window.plan_view.width()
        window.plan_expand_button.click()
        application.processEvents()
        assert window.design_stage.plan_expanded
        assert window.plan_view.width() > compact_width
        assert not window.viewport_view_button.parentWidget().isVisible()
        window.plan_expand_button.click()
        application.processEvents()
        assert not window.design_stage.plan_expanded
        assert window.viewport_view_button.parentWidget().isVisible()
        window.project.room.width = 3700
        window.refresh_visuals()
        assert window.plan_room_dimensions.text() == "3,700 × 3,200 mm"
    finally:
        window.close()


def test_viewport_strip_icons_and_disabled_state_follow_existing_actions():
    application, window = _window()
    try:
        controls = window.viewport_view_button.parentWidget()
        buttons = {button.text(): button for button in controls.findChildren(QToolButton)}
        assert set(buttons) == {"Front", "Isometric", "Fit", "Expand", "Interior", "View"}
        assert all(not button.icon().isNull() for button in buttons.values())
        assert len({button.toolButtonStyle() for button in buttons.values()}) == 1
        window.front_view_action.setEnabled(False)
        application.processEvents()
        assert not buttons["Front"].isEnabled()
        window.front_view_action.setEnabled(True)
        application.processEvents()
        assert buttons["Front"].isEnabled()
        buttons["Interior"].click()
        assert window.show_interior_action.isChecked()
        window.show_interior_action.trigger()
        assert not buttons["Interior"].isChecked()
        assert window.hide_room_walls_action in buttons["View"].menu().actions()
    finally:
        window.close()


def test_cabinet_selection_stays_synchronized_in_compact_and_expanded_plan():
    application, window = _window()
    try:
        window.resize(1366, 768)
        application.processEvents()
        for cabinet_id, expanded in (("C6", False), ("C3", True)):
            if expanded:
                window.plan_expand_button.click()
                application.processEvents()
            footprint = window.plan_view._cabinet_items[cabinet_id]
            position = window.plan_view.mapFromScene(footprint.sceneBoundingRect().center())
            QTest.mouseClick(window.plan_view.viewport(), Qt.MouseButton.LeftButton,
                             pos=position)
            application.processEvents()
            assert window.project.selected_cabinet_id == cabinet_id
            assert window.view3d._selected_cabinet_id == cabinet_id
            assert window.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == cabinet_id
    finally:
        window.close()
