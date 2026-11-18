"""Stage 1 library integration and visual-only manufacturing boundary."""

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
from openpyxl import load_workbook
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import CATALOGUE, create_catalogue_cabinet, furniture_items, get_catalogue_item
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import HardwareAssignment, PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import APPLIANCES, FURNITURE, HARDWARE, LIBRARIES, PROPS, PRODUCTS, get_product, products_for
from kuchhe7.ui.main_window import MainWindow


def test_four_libraries_and_stable_furniture_catalogue():
    assert LIBRARIES == (FURNITURE, APPLIANCES, PROPS, HARDWARE)
    assert len(CATALOGUE) == 15
    assert {item.type_id for item in furniture_items("Wardrobe")} == {"wardrobe_2_door", "wardrobe_open"}
    assert all(furniture_items(family) for family in ("Kitchen", "Wardrobe", "Vanity"))
    assert len({item.type_id for item in PRODUCTS}) == len(PRODUCTS)
    assert all(products_for(library) for library in (APPLIANCES, PROPS, HARDWARE))
    assert all(item.treatment == "visual_only" for item in products_for(PROPS))
    assert get_catalogue_item("wardrobe_2_door").height == 2100


def test_products_and_hardware_save_reopen_without_changing_bom_or_nesting(tmp_path):
    project = Project.complete_kitchen_demo()
    before_bom = generate_project_bom(project)
    before_nesting = nest_project(project)
    prop = get_product("plant_pot")
    appliance = get_product("fridge_tall")
    project.add_product(PlacedProduct("P1", prop.type_id, 120, 500, prop.elevation_z,
                                      prop.width, prop.depth, prop.height))
    project.add_product(PlacedProduct("A1", appliance.type_id, 100, 1500, appliance.elevation_z,
                                      appliance.width, appliance.depth, appliance.height))
    project.add_hardware_assignment(HardwareAssignment("H1", "C1", "handle_bar", 2))
    assert generate_project_bom(project) == before_bom
    assert nest_project(project).eligible_count == before_nesting.eligible_count

    copied = deepcopy(project)
    copied.placed_products[0].width += 20
    assert generate_project_bom(copied) == before_bom
    reopened = load_project(save_project(copied, tmp_path / "libraries.json"))
    assert reopened.placed_products[0].width == prop.width + 20
    assert reopened.hardware_assignments[0].cabinet_id == "C1"
    assert generate_project_bom(reopened) == before_bom
    assert nest_project(reopened).placed_count == before_nesting.placed_count

    workbook = load_workbook(export_bom_xlsx(reopened, tmp_path / "libraries.xlsx"), data_only=True)["BOM"]
    assert workbook.max_row - 4 == len(before_bom)
    drawing = ezdxf.readfile(export_front_elevation_dxf(reopened, tmp_path / "libraries.dxf"))
    assert drawing.header["$INSUNITS"] == 4
    assert len(drawing.modelspace().query("LWPOLYLINE")) == len(project.cabinets)


def test_legacy_json_loads_with_empty_new_libraries(tmp_path):
    old = Project.sample_kitchen().to_dict()
    old.pop("placed_products")
    old.pop("hardware_assignments")
    old["schema_version"] = 6
    import json
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    loaded = load_project(path)
    assert loaded.placed_products == [] and loaded.hardware_assignments == []
    assert len(loaded.cabinets) == 3


def test_wardrobe_and_vanity_furniture_round_trip_with_existing_cabinet_schema(tmp_path):
    project = Project.empty("Furniture Families", "Wardrobe")
    project.add_cabinet(create_catalogue_cabinet("wardrobe_2_door", "C1", position_x=200, position_y=1600))
    project.add_cabinet(create_catalogue_cabinet("vanity_drawer", "C2", position_x=1700, position_y=2700))
    reopened = load_project(save_project(project, tmp_path / "furniture.json"))
    assert [item.cabinet_type_id for item in reopened.cabinets] == ["wardrobe_2_door", "vanity_drawer"]
    assert reopened.project_type == "Wardrobe"
    assert generate_project_bom(reopened) == generate_project_bom(project)


def test_prop_treatment_cannot_be_promoted_to_manufacturing():
    definition = get_product("plant_pot")
    product = PlacedProduct("P1", definition.type_id, 200, 200, definition.elevation_z,
                            definition.width, definition.depth, definition.height)
    product.manufacturing_treatment = "Supplier supplied"
    import pytest
    with pytest.raises(ValueError, match="visual only"):
        product.validate(Project.empty().room)


def test_desktop_library_placement_selection_editing_and_3d_visibility():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.library_combo.count() == 4
    for library in LIBRARIES:
        window.library_combo.setCurrentText(library)
        assert window.library_list.count() > 0
        assert not window.library_list.item(0).icon().isNull()
    window.library_combo.setCurrentText(PROPS)
    window.library_list.setCurrentRow(0)
    window.begin_library_placement()
    window.show()
    app.processEvents()
    view = window.plan_view
    point = view.mapFromScene(view._ox + 350 * view._scale, view._oy + 350 * view._scale)
    QTest.mouseMove(view.viewport(), point)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert len(window.project.placed_products) == 1
    assert "P1" in view._product_items
    assert "product-P1" in window.view3d.plotter.actors
    window.select_product("P1")
    assert window.product_group.isVisibleTo(window.properties_dock)
    before_bom = generate_project_bom(window.project)
    window.product_width_spin.setValue(240)
    app.processEvents()
    assert window.project.placed_products[0].width == 240
    assert generate_project_bom(window.project) == before_bom
    window.remove_selected_product()
    assert window.project.placed_products == []
    window.close()


def test_hardware_assignment_is_separate_from_existing_hardware_bom():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    before_bom = generate_project_bom(window.project)
    window.library_combo.setCurrentText(HARDWARE)
    window.library_list.setCurrentRow(0)
    window.begin_library_placement()
    app.processEvents()
    assert len(window.project.hardware_assignments) == 1
    assert window.project.hardware_assignments[0].cabinet_id == "C1"
    assert generate_project_bom(window.project) == before_bom
    window.undo_action.trigger()
    assert window.project.hardware_assignments == []
    window.redo_action.trigger()
    assert len(window.project.hardware_assignments) == 1
    window.remove_selected_cabinet()
    assert window.project.hardware_assignments == []
    window.undo_action.trigger()
    assert len(window.project.hardware_assignments) == 1
    window.close()


def test_wardrobe_and_appliance_can_be_placed_from_library_in_2d_and_render_in_3d():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    window.library_combo.setCurrentText(FURNITURE)
    window.library_family_combo.setCurrentText("Wardrobe")
    assert window.library_list.count() == 2
    window.library_list.setCurrentRow(0)
    window.begin_library_placement()
    view = window.plan_view
    app.processEvents()
    point = view.mapFromScene(view._ox + 950 * view._scale, view._oy + 2000 * view._scale)
    QTest.mouseMove(view.viewport(), point)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert window.project.cabinets[0].cabinet_type_id == "wardrobe_2_door"
    assert "C1" in view._cabinet_items
    assert "C1-left-side" in window.view3d.plotter.actors

    window.library_combo.setCurrentText(APPLIANCES)
    window.library_list.setCurrentRow(0)
    window.begin_library_placement()
    point = view.mapFromScene(view._ox + 450 * view._scale, view._oy + 450 * view._scale)
    QTest.mouseMove(view.viewport(), point)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert window.project.placed_products[0].type_id == "oven_freestanding"
    assert "A1" in view._product_items
    assert "product-A1" in window.view3d.plotter.actors
    window.select_product("A1")
    window.product_commercial_combo.setCurrentText("Client supplied")
    assert window.project.placed_products[0].commercial_treatment == "Client supplied"
    assert window.project.placed_products[0].manufacturing_treatment == "Review required"
    window.close()


def test_mouse_drag_of_resized_product_keeps_dimensions_and_visual_only_bom():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window._place_product("plant_pot", 300, 300)
    window.product_width_spin.setValue(280)
    window.show()
    app.processEvents()
    before_bom = generate_project_bom(window.project)
    view = window.plan_view
    product = window.project.placed_products[0]
    start = view.mapFromScene(view._product_items[product.item_id].sceneBoundingRect().center())
    target_scene = QPoint(round(view._ox + 730 * view._scale), round(view._oy + 760 * view._scale))
    target = view.mapFromScene(target_scene)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), target, delay=10)
    assert view._preview_valid
    assert view._preview_item.rect().width() == product.width * view._scale
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    app.processEvents()
    assert (product.position_x, product.position_y) != (300, 300)
    assert product.width == 280
    assert "product-P1" in window.view3d.plotter.actors
    assert generate_project_bom(window.project) == before_bom
    window.close()
