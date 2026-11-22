"""Curated decorative models remain visual-only across project workflows."""

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.costing import cost_cabinet
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import PlacedProduct, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import CURATED_PROP_IDS, PROPS, get_product, products_for
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.catalogue_preview import product_thumbnail
from kuchhe7.ui.main_window import MainWindow


POSITIONS = {
    "potted_green_plant": (300, 2650),
    "flower_vase": (600, 2650),
    "floor_plant": (3000, 1500),
    "decorative_vase": (1110, 2650),
    "fruit_bowl": (1340, 2650),
    "utensil_holder": (1710, 2650),
    "decorative_tray": (1960, 2650),
    "small_sculpture": (1150, 2900),
}


def populated_project():
    project = Project.complete_kitchen_demo()
    for index, (type_id, (x, y)) in enumerate(POSITIONS.items(), 1):
        definition = get_product(type_id)
        project.add_product(PlacedProduct(
            f"P{index}", type_id, x, y, definition.elevation_z,
            definition.width, definition.depth, definition.height,
        ))
    return project


def test_eight_curated_products_have_unique_ids_thumbnails_and_visual_treatment():
    app = QApplication.instance() or QApplication([])
    assert len(CURATED_PROP_IDS) == 8
    assert CURATED_PROP_IDS.issubset({item.type_id for item in products_for(PROPS)})
    for type_id in CURATED_PROP_IDS:
        item = get_product(type_id)
        assert item.treatment == "visual_only"
        assert min(item.width, item.depth, item.height) > 0
        assert not product_thumbnail(item).isNull()


def test_props_require_real_support_and_rotated_footprint_stays_inside_room():
    project = populated_project()
    assert len(project.placed_products) == 8
    floating = deepcopy(project.placed_products[0])
    floating.item_id = "P9"
    floating.elevation_z = 1050
    with pytest.raises(ValueError, match="supporting cabinet countertop"):
        project.add_product(floating)
    floor = deepcopy(project.placed_products[2])
    floor.item_id = "P9"
    floor.elevation_z = 500
    with pytest.raises(ValueError, match="rest on the floor"):
        project.add_product(floor)
    rotated = deepcopy(project.placed_products[6])
    rotated.orientation_degrees = 90
    assert (rotated.footprint_width, rotated.footprint_depth) == (rotated.depth, rotated.width)
    project.validate_product_placement(rotated)
    rotated.position_x = project.room.width - rotated.footprint_width + 1
    with pytest.raises(ValueError, match="outside the room"):
        project.validate_product_placement(rotated)


def test_props_persist_and_never_change_bom_nesting_excel_or_dxf(tmp_path):
    bare = Project.complete_kitchen_demo()
    with_props = populated_project()
    assert generate_project_bom(with_props) == generate_project_bom(bare)
    assert nest_project(with_props) == nest_project(bare)
    assert calculate_quotation(with_props) == calculate_quotation(bare)
    assert [cost_cabinet(item, with_props.price_master) for item in with_props.cabinets] == [
        cost_cabinet(item, bare.price_master) for item in bare.cabinets]
    with_props.placed_products[0].orientation_degrees = 180
    reopened = load_project(save_project(with_props, tmp_path / "props.json"))
    assert [item.type_id for item in reopened.placed_products] == list(POSITIONS)
    assert reopened.placed_products[0].orientation_degrees == 180
    assert generate_project_bom(reopened) == generate_project_bom(bare)
    assert nest_project(reopened) == nest_project(bare)
    assert calculate_quotation(reopened) == calculate_quotation(bare)
    before = load_workbook(export_bom_xlsx(bare, tmp_path / "before.xlsx"), data_only=True)
    after = load_workbook(export_bom_xlsx(reopened, tmp_path / "after.xlsx"), data_only=True)
    assert list(before["BOM"].values) == list(after["BOM"].values)
    before_dxf = ezdxf.readfile(export_front_elevation_dxf(bare, tmp_path / "before.dxf"))
    after_dxf = ezdxf.readfile(export_front_elevation_dxf(reopened, tmp_path / "after.dxf"))
    assert [entity.dxftype() for entity in before_dxf.modelspace()] == [
        entity.dxftype() for entity in after_dxf.modelspace()]


def test_curated_prop_3d_meshes_and_ui_edit_history():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.project = populated_project()
    window.selected_product_id = "P1"
    window.refresh_visuals(reset_camera=True)
    actor_names = window.view3d.plotter.actors
    for index, type_id in enumerate(POSITIONS, 1):
        assert len([name for name in actor_names if name.startswith(f"product-P{index}-")]) >= 2, type_id
    window.select_product("P1")
    window.product_orientation_combo.setCurrentIndex(1)
    assert window.project.placed_products[0].orientation_degrees == 90
    window.undo_action.trigger()
    assert window.project.placed_products[0].orientation_degrees == 0
    window.redo_action.trigger()
    assert window.project.placed_products[0].orientation_degrees == 90
    window.close()


def test_curated_prop_duplicate_delete_and_undo_preserve_visual_only_rule():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    definition = get_product("potted_green_plant")
    window.project.add_product(PlacedProduct(
        "P1", definition.type_id, 300, 2650, definition.elevation_z,
        definition.width, definition.depth, definition.height))
    window.selected_product_id = "P1"
    window.refresh_visuals()
    bom = generate_project_bom(window.project)
    window.duplicate_selected_object()
    assert len(window.project.placed_products) == 2
    assert all(item.commercial_treatment == "Visual only" for item in window.project.placed_products)
    assert generate_project_bom(window.project) == bom
    window.remove_selected_product()
    assert len(window.project.placed_products) == 1
    window.undo_action.trigger()
    assert len(window.project.placed_products) == 2
    window.undo_action.trigger()
    assert len(window.project.placed_products) == 1
    window.close()
