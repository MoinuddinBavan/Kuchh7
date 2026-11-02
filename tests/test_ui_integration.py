import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsTextItem, QMessageBox

from kuchhe7.ui.main_window import MainWindow
from kuchhe7.catalogue import CATALOGUE, create_catalogue_cabinet
from kuchhe7.models import Room


def test_width_control_updates_2d_3d_and_bom():
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.width_spin.setValue(1200)
    application.processEvents()

    assert window.project.cabinet.width == 1200
    plan_text = "\n".join(
        item.toPlainText()
        for item in window.plan_view.scene().items()
        if isinstance(item, QGraphicsTextItem)
    )
    assert "1200 × 600 mm" in plan_text
    assert window.view3d.plotter.bounds.x_max == 1200

    table_rows = {
        window.bom_table.item(row, 0).text(): window.bom_table.item(row, 1).text()
        for row in range(window.bom_table.rowCount())
    }
    assert table_rows["Top panel"] == "1164 mm"
    window.close()


def test_interior_visibility_geometry_and_camera_controls():
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    application.processEvents()

    assert window.view3d.door_actor_count == 2
    assert window.view3d.handle_actor_count == 2
    assert window.view3d.shelf_actor_count == 1
    assert all(actor.GetVisibility() for actor in window.view3d._door_actors)

    window.show_interior_action.setChecked(True)
    application.processEvents()
    assert not window.view3d.doors_visible
    assert all(not actor.GetVisibility() for actor in window.view3d._door_actors)
    assert all(actor.GetVisibility() for actor in window.view3d._shelf_actors)

    window.front_view_action.trigger()
    application.processEvents()
    front_position = tuple(window.view3d.plotter.camera.position)
    assert front_position[1] < 0
    window.isometric_view_action.trigger()
    application.processEvents()
    isometric_position = tuple(window.view3d.plotter.camera.position)
    assert isometric_position != front_position
    window.reset_3d_action.trigger()
    application.processEvents()
    assert tuple(window.view3d.plotter.camera.position) == isometric_position
    window.close()


def test_room_resize_updates_scaled_plan_dimensions():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.room_width_spin.setValue(5000)
    window.room_depth_spin.setValue(4200)
    application.processEvents()
    plan_text = "\n".join(
        item.toPlainText()
        for item in window.plan_view.scene().items()
        if isinstance(item, QGraphicsTextItem)
    )
    assert "5,000 mm" in plan_text
    assert "4,200 mm" in plan_text
    assert window.plan_view.scene().sceneRect().width() > 0
    assert window.plan_view.scene().sceneRect().height() > 0
    window.close()


def test_sample_selection_and_isolated_cabinet_editing():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    application.processEvents()

    assert len(window.project.cabinets) == 3
    assert window.view3d.door_actor_count == 5
    assert window.view3d.handle_actor_count == 5
    assert window.view3d.shelf_actor_count == 3
    assert len(window.view3d._selection_actors) == 1

    original_widths = {item.cabinet_id: item.width for item in window.project.cabinets}
    original_heights = {item.cabinet_id: item.height for item in window.project.cabinets}
    window.select_cabinet("C2")
    window.height_spin.setValue(780)
    application.processEvents()
    assert window.project.selected_cabinet_id == "C2"
    assert window.project.cabinet.height == 780
    assert next(item for item in window.project.cabinets if item.cabinet_id == "C1").width == original_widths["C1"]
    assert next(item for item in window.project.cabinets if item.cabinet_id == "C1").height == 720
    assert next(item for item in window.project.cabinets if item.cabinet_id == "C3").width == original_widths["C3"]
    assert next(item for item in window.project.cabinets if item.cabinet_id == "C3").height == original_heights["C3"]
    assert window.cabinet_id_label.text() == "C2"
    assert window.project_tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == "C2"

    plan_text = "\n".join(
        item.toPlainText()
        for item in window.plan_view.scene().items()
        if isinstance(item, QGraphicsTextItem)
    )
    assert all(cabinet_id in plan_text for cabinet_id in ("C1", "C2", "C3"))
    window.close()


def test_tree_and_2d_plan_select_cabinets():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_action.trigger()
    window.show()
    application.processEvents()

    c2_item = next(
        item
        for iterator_index in range(window.project_tree.topLevelItem(0).child(1).childCount())
        if (item := window.project_tree.topLevelItem(0).child(1).child(iterator_index)).data(0, Qt.ItemDataRole.UserRole) == "C2"
    )
    window.project_tree.itemClicked.emit(c2_item, 0)
    application.processEvents()
    assert window.project.selected_cabinet_id == "C2"

    c3_footprint = next(
        item
        for item in window.plan_view.scene().items()
        if isinstance(item, QGraphicsRectItem) and item.data(0) == "C3"
    )
    click_position = window.plan_view.mapFromScene(c3_footprint.sceneBoundingRect().center())
    QTest.mouseClick(window.plan_view.viewport(), Qt.MouseButton.LeftButton, pos=click_position)
    application.processEvents()
    assert window.project.selected_cabinet_id == "C3"
    assert window.cabinet_id_label.text() == "C3"
    window.close()


def test_fit_all_and_reset_frame_complete_sample():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    application.processEvents()
    assert all(any(name.startswith(cabinet_id) for name in window.view3d.plotter.actors) for cabinet_id in ("C1", "C2", "C3"))
    window.view3d.plotter.camera.zoom(3)
    assert window.view3d.plotter.camera.view_angle < 30
    window.fit_all_action.trigger()
    application.processEvents()
    assert window.view3d.plotter.camera.view_angle == 30
    window.front_view_action.trigger()
    front_position = tuple(window.view3d.plotter.camera.position)
    window.reset_3d_action.trigger()
    application.processEvents()
    assert tuple(window.view3d.plotter.camera.position) != front_position
    window.close()


def test_loading_sample_requires_confirmation_when_project_is_dirty(monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.width_spin.setValue(1000)
    application.processEvents()
    assert window._dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    window.load_sample_kitchen()
    assert len(window.project.cabinets) == 1
    assert window.project.cabinet.width == 1000
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window.load_sample_kitchen()
    assert [item.cabinet_id for item in window.project.cabinets] == ["C1", "C2", "C3"]
    window.close()


def test_invalid_position_edit_is_rejected_with_warning():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    window.select_cabinet("C3")
    window.position_x_spin.setValue(1500)
    application.processEvents()
    assert window.project.cabinet.position_x == 2150
    assert window.position_x_spin.value() == 2150
    assert window.placement_warning.isVisibleTo(window.properties_dock)
    assert "overlaps C1" in window.placement_warning.text()
    window.close()


def test_catalogue_adds_selected_type_and_properties_adapt():
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.catalogue_category_combo.setCurrentText("Base Cabinets")
    window.catalogue_list.setCurrentRow(1)
    window.add_cabinet()
    application.processEvents()

    assert window.project.selected_cabinet.cabinet_type_id == "base_3_drawer"
    assert window.project.selected_cabinet.drawer_count == 3
    assert window.cabinet_type_label.text() == "3-Drawer Base Cabinet"
    assert window.drawer_spin.isVisibleTo(window.properties_dock)
    assert not window.door_spin.isVisibleTo(window.properties_dock)
    assert window.view3d.door_actor_count == 5  # C1 doors plus C2 drawer fronts
    window.close()


def test_catalogue_all_view_contains_headings_and_every_product():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.catalogue_category_combo.setCurrentIndex(0)
    application.processEvents()
    product_ids = [
        window.catalogue_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(window.catalogue_list.count())
        if window.catalogue_list.item(row).data(Qt.ItemDataRole.UserRole)
    ]
    assert len(product_ids) == len(CATALOGUE) == 15
    assert all(not window.catalogue_list.item(row).icon().isNull() for row in range(window.catalogue_list.count())
               if window.catalogue_list.item(row).data(Qt.ItemDataRole.UserRole))
    window.close()


def test_six_representative_types_have_distinct_geometry():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    room = Room()

    def actor_names(type_id: str) -> set[str]:
        cabinet = create_catalogue_cabinet(type_id, "C1")
        cabinet.position_y = room.depth - cabinet.depth
        window.view3d.update_scene(room, [cabinet], "C1", True)
        application.processEvents()
        return set(window.view3d.plotter.actors)

    assert any("-door-" in name for name in actor_names("base_2_door"))
    assert any("-drawer-" in name for name in actor_names("base_3_drawer"))
    open_names = actor_names("open_shelf_base")
    assert any("-shelf-" in name for name in open_names) and not any("-door-" in name for name in open_names)
    wall = create_catalogue_cabinet("wall_2_door", "C1")
    wall.position_y = room.depth - wall.depth
    window.view3d.update_scene(room, [wall], "C1", True)
    assert window.view3d.plotter.bounds.z_min >= 1400
    tall = create_catalogue_cabinet("tall_pantry", "C1")
    tall.position_y = room.depth - tall.depth
    window.view3d.update_scene(room, [tall], "C1", True)
    assert window.view3d.plotter.bounds.z_max == 2100
    assert any("corner-return" in name for name in actor_names("corner_base"))
    window.close()


def test_premium_finish_selection_updates_selected_cabinet():
    application = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.material_combo.setCurrentText("Graphite")
    application.processEvents()
    assert window.project.selected_cabinet.material == "Graphite"
    window.close()
