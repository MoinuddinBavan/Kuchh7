"""Focused regressions for the existing header and Design Studio controls."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtGui import QUndoCommand
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton, QWidget

from kuchhe7.app import STYLE
from kuchhe7.models import Project
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


def test_header_uses_live_project_and_save_state(tmp_path):
    app, window = _window()
    try:
        assert window.project.name == window.header_project_title.text()
        assert "3600 × 3200 mm" in window.header_project_meta.text()
        assert "6 cabinets" in window.header_project_meta.text()
        assert "2 openings" in window.header_project_meta.text()
        assert window.header_dirty_label.text() == "All changes saved"
        window._set_dirty(True)
        assert window.header_dirty_label.text() == "Unsaved changes"
        assert window.header_dirty_label.property("dirty") is True
        window.project_path = tmp_path / "header-save.json"
        window.findChild(QPushButton, "headerSave").click()
        app.processEvents()
        assert window.project_path.is_file()
        assert window.header_dirty_label.text() == "All changes saved"
        export = window.findChild(QToolButton, "headerExport")
        labels = [action.text() for action in export.menu().actions()]
        assert labels == ["Export BOM", "Export Quotation", "Export Project PDF", "Export CAD Drawing"]
        assert [action.text() for action in window.export_bom_menu.actions()] == ["XLSX…", "PDF…"]
        assert [action.text() for action in window.export_quote_menu.actions()] == ["XLSX…", "PDF…"]
        called = []
        window.documents_workspace.export_bom_pdf = lambda: called.append("bom-pdf")
        window.export_bom_menu.actions()[1].trigger()
        assert called == ["bom-pdf"]
        app_menu = window.findChild(QToolButton, "headerMenu").menu()
        assert {"File", "Edit", "View", "Design", "Manufacturing"} <= {
            action.text().replace("&", "") for action in app_menu.actions()
        }
    finally:
        window.close()


def test_export_icon_and_chevron_both_open_the_same_menu():
    app, window = _window()
    try:
        export = window.findChild(QToolButton, "headerExport")
        menu = export.menu()
        openings = []
        menu.aboutToShow.connect(lambda: openings.append(menu.geometry()))
        for point in (QPoint(20, 20), QPoint(105, 20)):
            QTimer.singleShot(80, menu.hide)
            QTest.mouseClick(export, Qt.MouseButton.LeftButton, pos=point)
            QTest.qWait(100)
            app.processEvents()
            assert not menu.isVisible()
        assert len(openings) == 2
        window.resize(1366, 768)
        app.processEvents()
        menu.popup(export.mapToGlobal(QPoint(0, export.height())))
        app.processEvents()
        frame = window.frameGeometry()
        assert menu.geometry().left() >= frame.left()
        assert menu.geometry().right() <= frame.right()
        assert menu.screen().availableGeometry().contains(menu.geometry())
        menu.hide()
    finally:
        window.close()


def test_undo_redo_and_view_controls_remain_connected():
    app, window = _window()
    try:
        changes = []

        class Change(QUndoCommand):
            def redo(self):
                changes.append("done")

            def undo(self):
                changes.pop()

        window.undo_stack.push(Change())
        assert window.header_undo_button.isEnabled()
        window.header_undo_button.click()
        assert changes == []
        window.header_redo_button.click()
        assert changes == ["done"]

        window.plan_toggle_button.click()
        assert window.design_stage.plan_expanded and window.plan_toggle_button.isChecked()
        window.technical_view_button.click()
        assert not window.design_stage.plan_expanded
        assert window.technical_view_button.isChecked()
        window.presentation_mode_button.click()
        assert window.presentation_view_action.isChecked()
        assert window.technical_view_button.isChecked()
        window.interior_view_button.click()
        assert window.show_interior_action.isChecked() and not window.view3d.doors_visible
        window.interior_view_button.click()
        assert window.view3d.doors_visible
        tools = {button.text(): button for button in window.findChildren(QToolButton, "designToolButton")}
        assert set(tools) == {
            "Select", "Place", "Move", "Rotate", "Snap", "Grid", "Duplicate", "Delete",
            "Front", "Isometric", "Interior", "Reset", "Max", "Fit",
        }
        tools["Snap"].click()
        assert not window.snap_action.isChecked() and not tools["Snap"].isChecked()
        tools["Snap"].click()
        tools["Grid"].click()
        assert not window.grid_snap_action.isChecked() and not tools["Grid"].isChecked()
        tools["Grid"].click()
        tools["Interior"].click()
        assert window.show_interior_action.isChecked() and window.interior_view_button.isChecked()
        tools["Interior"].click()
        assert not window.show_interior_action.isChecked()
        tools["Place"].click()
        assert window.explorer_tabs.currentWidget() is window.library_page
        tools["Select"].click()
        assert window.design_stage.plan_expanded
        window.technical_view_button.click()
        tools["Front"].click()
        front = tuple(window.view3d.plotter.camera.position)
        tools["Isometric"].click()
        assert tuple(window.view3d.plotter.camera.position) != front
        tools["Reset"].click()
        tools["Fit"].click()
        tools["Max"].click()
        assert window.maximize_3d_action.isChecked() and tools["Max"].isChecked()
        tools["Max"].click()
        assert not window.maximize_3d_action.isChecked()
    finally:
        window.close()


def test_header_and_design_tools_fit_target_widths():
    app, window = _window()
    try:
        export = window.findChild(QToolButton, "headerExport")
        title = window.findChild(QWidget, "designTitle")
        view_buttons = [window.technical_view_button, window.plan_toggle_button,
                        window.presentation_mode_button]
        for width, height in ((1920, 1080), (1600, 900), (1366, 768)):
            window.resize(width, height)
            app.processEvents()
            assert export.isVisible() and export.geometry().right() <= export.parentWidget().width()
            assert title.geometry().right() < view_buttons[0].geometry().left()
            assert view_buttons[-1].geometry().right() <= view_buttons[-1].parentWidget().width()
            if width == 1366:
                assert all(not window.design_tool_buttons[caption].isVisible()
                           for caption in ("Snap", "Grid", "Interior", "Max"))
                assert window.show_interior_action in window.view_menu.actions()
            for button in window.findChildren(QToolButton, "designToolButton"):
                if button.isVisible():
                    assert button.geometry().right() <= button.parentWidget().width()
    finally:
        window.close()
