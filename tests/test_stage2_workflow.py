"""Stage 2 2D-first product workflow and 3D spatial validation."""

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from openpyxl import load_workbook
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import APPLIANCES, FURNITURE, HARDWARE, PROPS, get_product
from kuchhe7.ui.main_window import MainWindow


def _placed(type_id: str, item_id: str, x: int, y: int) -> PlacedProduct:
    definition = get_product(type_id)
    return PlacedProduct(item_id, type_id, x, y, definition.elevation_z,
                         definition.width, definition.depth, definition.height)


def test_one_visible_library_browser_filters_all_four_groups():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.explorer_tabs.tabText(1) == "Libraries"
    assert window.explorer_tabs.isTabVisible(2)
    assert not window.explorer_tabs.isTabVisible(3)
    window.explorer_tabs.setCurrentWidget(window.library_page)
    window.library_combo.setCurrentText(FURNITURE)
    window.library_family_combo.setCurrentText("Wardrobe")
    assert window.library_list.count() == 2
    window.library_combo.setCurrentText(APPLIANCES)
    assert window.library_category_combo.findText("Cooking") >= 0
    window.library_category_combo.setCurrentText("Cooking")
    assert window.library_list.count() == 2
    assert all("Cooking" in window.library_list.item(i).text() for i in range(2))
    window.library_combo.setCurrentText(PROPS)
    assert window.library_list.count() >= 5
    window.library_combo.setCurrentText(HARDWARE)
    assert window.library_category_combo.findText("Handles") >= 0
    window.close()


def test_3d_volume_rejects_real_intersections_and_allows_intentional_stacking():
    project = Project.empty()
    project.add_cabinet(create_catalogue_cabinet("base_2_door", "C1", position_x=200, position_y=2600))
    with pytest.raises(ValueError, match="overlaps cabinet C1"):
        project.add_product(_placed("oven_freestanding", "A1", 250, 2600))
    project.add_product(_placed("plant_pot", "P1", 250, 2600))  # Above the base cabinet.
    project.add_product(_placed("sink_single", "A1", 1600, 900))
    project.add_product(_placed("tap_arc", "A2", 1750, 1050))  # Intended sink/tap pairing.
    with pytest.raises(ValueError, match="overlaps product A1"):
        project.add_product(_placed("hob_4_zone", "A3", 1600, 900))
    with pytest.raises(ValueError, match="outside the room"):
        project.add_product(_placed("fridge_tall", "A3", 3300, 100))

    floor_project = Project.empty()
    floor_project.add_product(_placed("oven_freestanding", "A1", 300, 300))
    with pytest.raises(ValueError, match="overlaps product A1"):
        floor_project.add_cabinet(create_catalogue_cabinet("base_2_door", "C1", position_x=300, position_y=300))


def test_product_edit_duplicate_move_delete_and_undo_redo_update_both_views():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window._place_product("oven_freestanding", 200, 400)
    assert window.project.selected_cabinet.width == 900
    first_actor = window.view3d.plotter.actors["product-A1"]
    first_bounds = first_actor.GetBounds()
    window.product_width_spin.setValue(700)
    assert window.project.placed_products[0].width == 700
    assert window.plan_view._product_items["A1"].rect().width() == pytest.approx(700 * window.plan_view._scale)
    assert window.view3d.plotter.actors["product-A1"].GetBounds()[1] - first_bounds[0] == pytest.approx(700)
    colour_before = window.view3d.plotter.actors["product-A1"].GetProperty().GetColor()
    window.product_appearance_combo.setCurrentText("Graphite")
    assert window.project.placed_products[0].appearance == "Graphite"
    assert "product-A1" in window.view3d.plotter.actors
    assert window.view3d.plotter.actors["product-A1"].GetProperty().GetColor() != colour_before
    window.duplicate_selected_object()
    assert [item.item_id for item in window.project.placed_products] == ["A1", "A2"]
    assert window.project.placed_products[1].appearance == "Graphite"
    assert window.project.placed_products[1].width == 700
    window.remove_selected_object()
    assert [item.item_id for item in window.project.placed_products] == ["A1"]
    window.undo_action.trigger()
    assert [item.item_id for item in window.project.placed_products] == ["A1", "A2"]
    window.undo_action.trigger()
    assert [item.item_id for item in window.project.placed_products] == ["A1"]
    window.select_product("A1")
    window.move_product("A1", 300, 500)
    assert (window.project.placed_products[0].position_x, window.project.placed_products[0].position_y) == (300, 500)
    window.undo_action.trigger()
    assert (window.project.placed_products[0].position_x, window.project.placed_products[0].position_y) == (200, 400)
    assert window.project.selected_cabinet.width == 900
    window.close()


def test_invalid_mouse_placement_shows_preview_and_preserves_project():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.show()
    app.processEvents()
    window.plan_toggle_button.click()
    app.processEvents()
    window.plan_view.begin_product_placement("oven_freestanding")
    view = window.plan_view
    collision = view.mapFromScene(view._ox + 1700 * view._scale,
                                  view._oy + 2800 * view._scale)
    QTest.mouseMove(view.viewport(), collision)
    assert not view._preview_valid
    assert "C1" in view._product_preview_error
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=collision)
    assert window.project.placed_products == []
    assert "C1" in window.placement_warning.text()
    valid = view.mapFromScene(view._ox + 500 * view._scale, view._oy + 500 * view._scale)
    QTest.mouseMove(view.viewport(), valid)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=valid)
    assert [item.item_id for item in window.project.placed_products] == ["A1"]
    view.begin_placement("base_2_door")
    QTest.mouseMove(view.viewport(), valid)
    assert not view._preview_valid  # Cabinet preview sees the placed oven.
    window.close()


def test_refined_sink_tap_meshes_and_appearance_round_trip(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._place_product("sink_single", 500, 900)
    window._place_product("tap_arc", 650, 1050)
    actors = window.view3d.plotter.actors
    assert "product-A1-left-rim" in actors and "product-A1-back-rim" in actors
    assert "product-A2-spout" in actors
    window.select_product("A1")
    window.product_appearance_combo.setCurrentText("Stainless")
    reopened = load_project(save_project(window.project, tmp_path / "products.json"))
    assert reopened.placed_products[0].appearance == "Stainless"
    assert [item.type_id for item in reopened.placed_products] == ["sink_single", "tap_arc"]
    window.close()


def test_duplicated_and_edited_props_remain_excluded_from_manufacturing(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    baseline_bom = deepcopy(generate_project_bom(window.project))
    baseline_nesting = nest_project(window.project)
    window._place_product("plant_pot", 300, 300)
    window.duplicate_selected_object()
    window.product_height_spin.setValue(400)
    saved = load_project(save_project(window.project, tmp_path / "visuals.json"))
    assert len(saved.placed_products) == 2
    assert generate_project_bom(saved) == baseline_bom
    assert nest_project(saved).eligible_count == baseline_nesting.eligible_count
    xlsx = load_workbook(export_bom_xlsx(saved, tmp_path / "visuals.xlsx"), data_only=True)["BOM"]
    assert xlsx.max_row - 4 == len(baseline_bom)
    dxf = ezdxf.readfile(export_front_elevation_dxf(saved, tmp_path / "visuals.dxf"))
    assert len(dxf.modelspace().query("LWPOLYLINE")) == 1
    window.remove_selected_product()
    assert generate_project_bom(window.project) == baseline_bom
    window.close()


def test_cabinet_duplicate_keeps_geometry_and_hardware_duplicates_as_metadata():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    source = deepcopy(window.project.selected_cabinet)
    window.duplicate_selected_object()
    assert [item.cabinet_id for item in window.project.cabinets] == ["C1", "C2"]
    duplicate = window.project.selected_cabinet
    assert (duplicate.width, duplicate.height, duplicate.depth, duplicate.material) == (
        source.width, source.height, source.depth, source.material)
    assert (duplicate.position_x, duplicate.position_y) != (source.position_x, source.position_y)
    window.undo_action.trigger()
    assert [item.cabinet_id for item in window.project.cabinets] == ["C1"]
    window.redo_action.trigger()
    assert [item.cabinet_id for item in window.project.cabinets] == ["C1", "C2"]

    window.library_combo.setCurrentText(HARDWARE)
    window.begin_library_placement()
    assert len(window.project.hardware_assignments) == 1
    window.duplicate_selected_object()
    assert len(window.project.hardware_assignments) == 2
    window.remove_selected_object()
    assert len(window.project.hardware_assignments) == 1
    assert len(window.project.cabinets) == 2
    window.close()
