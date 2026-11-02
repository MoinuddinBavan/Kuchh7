import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import json

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.models import Cabinet, Project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.ui.main_window import MainWindow, NewProjectDialog


def _application():
    return QApplication.instance() or QApplication([])


def _add_default(window: MainWindow, cabinet_id: str = "C1") -> None:
    cabinet = create_catalogue_cabinet(
        "base_2_door", cabinet_id, position_x=200, position_y=2600
    )
    window.project.add_cabinet(cabinet)
    window.refresh_all(reset_camera=True)


def test_normal_startup_is_a_clean_empty_project():
    application = _application()
    window = MainWindow()
    application.processEvents()

    assert (window.project.room.width, window.project.room.depth, window.project.room.height) == (3600, 3200, 2600)
    assert window.project.cabinets == []
    assert window.project.room.openings == []
    assert window.project.selected_cabinet is None
    assert window.project.selected_cabinet_id is None
    assert window.bom_table.rowCount() == 0
    assert window.plan_view._cabinet_items == {}
    assert window.view3d.door_actor_count == 0
    assert window.manufacturing_preview.components == []
    assert window.sheet_nesting.result.eligible_count == 0
    assert not window._dirty
    window.close()


def test_new_project_dialog_creates_blank_project(monkeypatch):
    application = _application()
    window = MainWindow(start_empty=False)
    window._set_dirty(False)
    monkeypatch.setattr(NewProjectDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)

    window.new_project()
    application.processEvents()

    assert window.project.cabinets == []
    assert window.project.room.openings == []
    assert window.project.selected_cabinet is None
    assert window._dirty
    window.close()


def test_first_catalogue_add_is_c1_and_populates_all_views():
    application = _application()
    window = MainWindow()
    window.add_cabinet()
    application.processEvents()

    assert [item.cabinet_id for item in window.project.cabinets] == ["C1"]
    assert window.project.selected_cabinet_id == "C1"
    assert "C1" in window.plan_view._cabinet_items
    assert any(name.startswith("C1") for name in window.view3d.plotter.actors)
    assert window.bom_table.rowCount() == len(generate_project_bom(window.project)) > 0
    window.close()


def test_remove_last_cabinet_undo_and_redo_preserve_id():
    application = _application()
    window = MainWindow()
    _add_default(window)

    window.remove_selected_cabinet()
    application.processEvents()
    assert window.project.cabinets == []
    assert window.project.selected_cabinet is None
    assert window.bom_table.rowCount() == 0
    assert window.manufacturing_preview.cabinet is None
    assert window.sheet_nesting.result.eligible_count == 0

    window.undo_action.trigger()
    application.processEvents()
    assert [item.cabinet_id for item in window.project.cabinets] == ["C1"]
    assert window.project.selected_cabinet_id == "C1"

    window.redo_action.trigger()
    application.processEvents()
    assert window.project.cabinets == []
    assert window.project.selected_cabinet_id is None
    window.close()


def test_remove_one_from_multi_cabinet_project_synchronizes_views_and_bom():
    application = _application()
    window = MainWindow()
    window.load_sample_kitchen()
    before_rows = window.bom_table.rowCount()
    window.select_cabinet("C2")
    removed_rows = len([item for item in generate_project_bom(window.project) if item.cabinet_id == "C2"])

    window.remove_selected_cabinet()
    application.processEvents()

    assert [item.cabinet_id for item in window.project.cabinets] == ["C1", "C3"]
    assert "C2" not in window.plan_view._cabinet_items
    assert not any(name.startswith("C2") for name in window.view3d.plotter.actors)
    assert window.bom_table.rowCount() == before_rows - removed_rows
    assert window.project.selected_cabinet_id == "C3"
    window.close()


def test_delete_shortcut_works_in_plan_and_not_in_spinbox():
    application = _application()
    window = MainWindow()
    _add_default(window)
    window.show()
    window.plan_view.setFocus()
    QTest.keyClick(window.plan_view, Qt.Key.Key_Delete)
    application.processEvents()
    assert window.project.cabinets == []

    window.undo_action.trigger()
    window.room_width_spin.setFocus()
    QTest.keyClick(window.room_width_spin, Qt.Key.Key_Delete)
    application.processEvents()
    assert [item.cabinet_id for item in window.project.cabinets] == ["C1"]
    window.close()


def test_delete_shortcut_works_from_project_tree():
    application = _application()
    window = MainWindow()
    _add_default(window)
    window.show()
    window.project_tree.setFocus()
    QTest.keyClick(window.project_tree, Qt.Key.Key_Delete)
    application.processEvents()
    assert window.project.cabinets == []
    window.close()


def test_empty_project_save_and_reopen_round_trip(tmp_path):
    project = Project.empty("Blank Approval")
    path = save_project(project, tmp_path / "blank.json")
    reopened = load_project(path)

    assert reopened.name == "Blank Approval"
    assert reopened.cabinets == []
    assert reopened.selected_cabinet_id is None
    assert generate_project_bom(reopened) == []
    assert json.loads(path.read_text(encoding="utf-8"))["cabinets"] == []


def test_legacy_single_cabinet_json_still_opens(tmp_path):
    legacy = {
        "name": "Legacy",
        "project_type": "Kitchen",
        "room": {"width": 3600, "depth": 3200},
        "cabinet": {
            "width": 900, "height": 720, "depth": 600,
            "board_thickness": 18, "door_count": 2, "shelf_count": 1,
            "material": "Natural Oak",
        },
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    reopened = load_project(path)
    assert [item.cabinet_id for item in reopened.cabinets] == ["C1"]
    assert reopened.selected_cabinet.width == 900


def test_complete_demo_action_still_loads_six_units():
    application = _application()
    window = MainWindow()
    window.load_complete_kitchen_demo()
    application.processEvents()
    assert [item.cabinet_id for item in window.project.cabinets] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    window.close()


def test_dirty_confirmation_cancel_discard_and_save(monkeypatch):
    window = MainWindow(start_empty=False)
    window._set_dirty(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel)
    assert not window._confirm_replace_unsaved("test project")
    assert window._dirty

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    assert window._confirm_replace_unsaved("test project")

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(window, "save_project", lambda *args, **kwargs: window._set_dirty(False) or True)
    assert window._confirm_replace_unsaved("test project")
    assert not window._dirty
    window.close()


def test_dirty_open_cancel_does_not_show_file_dialog(monkeypatch):
    window = MainWindow(start_empty=False)
    window._set_dirty(True)
    called = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: called.append(True) or ("", ""))
    window.open_project()
    assert called == []
    assert len(window.project.cabinets) == 1
    window.close()


def test_room_dimensions_remain_editable_without_cabinets():
    application = _application()
    window = MainWindow()
    window.room_width_spin.setValue(4200)
    window.room_depth_spin.setValue(3500)
    application.processEvents()
    assert (window.project.room.width, window.project.room.depth) == (4200, 3500)
    assert window.project.cabinets == []
    assert window._dirty
    window.close()
