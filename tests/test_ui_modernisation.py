"""Focused regressions for the compact desktop presentation layout."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtWidgets import QApplication, QToolBar, QToolButton
from PySide6.QtCore import Qt

from kuchhe7.app import STYLE
from kuchhe7.ui.main_window import MainWindow


def test_premium_header_and_design_canvases_fit_client_window_sizes():
    app = QApplication.instance() or QApplication([])
    original_style = app.styleSheet()
    app.setStyleSheet(STYLE)
    window = MainWindow(start_empty=False)
    window.show()
    toolbar = window.findChild(QToolBar, "mainRibbon")
    menu_button = window.findChild(QToolButton, "headerMenu")
    assert menu_button is not None
    assert {action.text().replace("&", "") for action in menu_button.menu().actions()} >= {
        "File", "Edit", "View", "Design", "Manufacturing", "Help",
    }
    for width, height in ((1920, 1080), (1600, 900), (1366, 768)):
        window.resize(width, height)
        app.processEvents()
        export_button = window.findChild(QToolButton, "headerExport")
        assert export_button is not None
        assert window.export_dxf_action in export_button.menu().actions()
        assert toolbar.height() <= 74
        assert window.plan_view.width() >= (200 if width <= 1366 else 220)
        assert window.view3d.width() > window.plan_view.width() * 2
        assert window.properties_dock.width() >= 290
        controls = window.viewport_view_button.parentWidget()
        # Offscreen Qt can report an oversized popup strip; physical Windows
        # captures cover the constrained widths. Assert the no-overlap layout
        # wherever the available scene width can actually hold both cards.
        if window.design_stage.width() >= window.plan_panel.geometry().right() + controls.width() + 24:
            assert not controls.geometry().intersects(window.plan_panel.geometry())
    window.close()
    app.setStyleSheet(original_style)


def test_bom_preview_can_collapse_restore_and_survives_workspace_switch():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.show()
    app.processEvents()
    rows = window.bom_table.rowCount()
    project_before = window.project.to_dict()
    assert not window.bom_preview_action.isChecked()
    assert not window.bom_dock.isVisible()
    window.workspace_tabs.setCurrentWidget(window.manufacturing_preview)
    window.workspace_tabs.setCurrentWidget(window.workspace_splitter)
    assert not window.bom_dock.isVisible()
    window.bom_preview_action.trigger()
    assert window.bom_dock.isVisible()
    assert window.bom_table.rowCount() == rows
    window.bom_preview_action.trigger()
    assert not window.bom_dock.isVisible()
    assert window.project.to_dict() == project_before
    window.close()


def test_object_cards_plan_expansion_and_workspace_rail_keep_design_data():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.load_complete_kitchen_demo()
    window.show()
    app.processEvents()
    assert window.object_list.count() >= 6
    compact_width = window.plan_view.width()
    window.plan_toggle_button.click()
    app.processEvents()
    assert window.design_stage.plan_expanded
    assert window.plan_view.width() > compact_width
    assert not window.viewport_view_button.parentWidget().isVisible()
    window.plan_expand_button.click()
    app.processEvents()
    assert not window.design_stage.plan_expanded
    assert window.viewport_view_button.parentWidget().isVisible()
    c2 = next(window.object_list.item(index) for index in range(window.object_list.count())
              if window.object_list.item(index).data(Qt.ItemDataRole.UserRole) == "C2")
    window.object_list.itemClicked.emit(c2)
    assert window.project.selected_cabinet_id == "C2"
    assert window.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == "C2"
    assert "C2" in window.inspector_title.text()
    design_before = window.project.to_dict()
    window._navigate_workspace(window.documents_workspace)
    assert window.workspace_tabs.currentWidget() is window.documents_workspace
    window._navigate_workspace(window.workspace_splitter, library=True)
    assert window.explorer_tabs.currentWidget() is window.library_page
    assert window.project.to_dict() == design_before
    window.close()


def test_version3_navigation_cards_and_inspector_preserve_project():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.show()
    app.processEvents()
    before = window.project.to_dict()
    c1 = window.object_list.item(0)
    assert "C1" in c1.text()
    assert "W" in c1.text() and "H" in c1.text() and "D" in c1.text()
    assert {name for _, _, name in window.rail_buttons} >= {
        "design", "library", "project", "materials", "engineering",
        "nesting", "documents", "assistant", "render",
    }
    window._navigate_rail(window.workspace_splitter, "project")
    assert window.explorer_tabs.currentWidget() is window.project_tree
    window._navigate_rail(window.workspace_splitter, "materials")
    assert window.material_combo.isVisible()
    assert window.workspace_tabs.currentWidget() is window.workspace_splitter
    assert window.project.to_dict() == before
    window.close()


def test_interior_view_button_and_view_menu_share_existing_actions():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.load_complete_kitchen_demo()
    window.show()
    app.processEvents()
    before = window.project.to_dict()
    selected_before = window.project.selected_cabinet_id

    interior = window.findChild(QToolButton, "viewportInteriorButton")
    options = window.findChild(QToolButton, "viewportViewMenu")
    assert interior is not None and interior.isVisible() and not interior.isChecked()
    assert options is not None and options.isVisible()
    assert {window.reset_3d_action, window.presentation_camera_action,
            window.hide_room_walls_action, window.show_interior_action,
            window.snap_action, window.grid_snap_action} <= set(options.menu().actions())
    assert window.show_interior_action in window.view_menu.actions()

    window.presentation_view_action.setChecked(True)
    assert len(window.project.room.openings) == 2
    camera_before = tuple(window.view3d.plotter.camera.position)
    assert window.view3d._room_wall_actors
    assert window.view3d._door_actors and window.view3d._shelf_actors
    interior.click()
    app.processEvents()
    assert interior.isChecked() and window.show_interior_action.isChecked()
    assert not window.view3d.doors_visible
    assert all(not actor.GetVisibility() for actor in window.view3d._door_actors)
    assert all(actor.GetVisibility() for actor in window.view3d._shelf_actors)

    window.hide_room_walls_action.setChecked(True)
    assert all(not actor.GetVisibility() for actor in window.view3d._room_wall_actors)
    window.hide_room_walls_action.setChecked(False)
    assert all(actor.GetVisibility() for actor in window.view3d._room_wall_actors)
    window.show_interior_action.trigger()  # The View menu action controls the same button.
    app.processEvents()
    assert not interior.isChecked() and window.view3d.doors_visible
    assert all(actor.GetVisibility() for actor in window.view3d._door_actors)
    assert tuple(window.view3d.plotter.camera.position) == camera_before
    assert window.project.selected_cabinet_id == selected_before
    assert window.project.to_dict() == before
    window.close()


def test_compact_view_menu_keeps_reset_and_snap_controls_available():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.show()
    app.processEvents()
    options = window.viewport_view_button.menu()
    assert window.reset_3d_action in options.actions()
    window.front_view_action.trigger()
    front = tuple(window.view3d.plotter.camera.position)
    window.reset_3d_action.trigger()
    assert tuple(window.view3d.plotter.camera.position) != front
    window.snap_action.setChecked(False)
    assert not window.plan_view._snap_enabled
    window.snap_action.setChecked(True)
    window.grid_snap_action.setChecked(False)
    assert not window.plan_view._grid_snap_enabled
    window.grid_snap_action.setChecked(True)
    window.close()
