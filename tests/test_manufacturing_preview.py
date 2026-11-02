import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_bom
from kuchhe7.exports import export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.ui.main_window import MainWindow
from kuchhe7.ui.manufacturing_preview import DISCLAIMER, engineering_components


def test_engineering_components_are_the_authoritative_bom_rows():
    project = Project.complete_kitchen_demo()
    cabinet = project.selected_cabinet
    assert engineering_components(cabinet) == generate_bom(cabinet)
    assert {component.cabinet_id for component in engineering_components(cabinet)} == {"C1"}


def test_exploded_preview_contains_panels_shelf_doors_and_hardware():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    preview = window.manufacturing_preview
    application.processEvents()

    assert {"Left side panel", "Right side panel", "Top panel", "Bottom panel", "Back panel", "Shelf", "Door", "Concealed hinge"} <= set(preview.exploded_view._component_actors)
    assert preview.components == generate_bom(window.project.selected_cabinet)
    assert DISCLAIMER.startswith("Engineering feasibility demo")
    window.close()


def test_preview_follows_selected_cabinet_and_dimension_changes():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window.select_cabinet("C1")
    window.width_spin.setValue(700)
    application.processEvents()

    preview = window.manufacturing_preview
    top_panel = next(component for component in preview.components if component.name == "Top panel")
    assert preview.cabinet.cabinet_id == "C1"
    assert top_panel.length_mm == 664
    assert preview.components == generate_bom(window.project.selected_cabinet)

    window.select_cabinet("C2")
    application.processEvents()
    assert preview.cabinet.cabinet_id == "C2"
    assert any(component.name == "Drawer front" for component in preview.components)
    assert preview.components == generate_bom(window.project.selected_cabinet)
    window.close()


def test_component_selection_updates_detail_and_dimensioned_drawing():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    preview = window.manufacturing_preview
    preview.select_component("Door")
    application.processEvents()
    component = next(item for item in generate_bom(window.project.selected_cabinet) if item.name == "Door")

    assert preview.selected_component == component
    assert preview.detail_name.text() == "Door"
    assert preview.detail_length.text() == f"{component.length_mm:g} mm"
    assert preview.detail_width.text() == f"{component.width_mm:g} mm"
    assert preview.detail_thickness.text() == f"{component.thickness_mm:g} mm"
    assert preview.detail_material.text() == component.material
    assert preview.detail_quantity.text() == str(component.quantity)
    assert preview.detail_cabinet.text() == "C1"
    assert preview.component_drawing._component == component
    window.close()


def test_drilling_parameters_are_configurable_preview_only_and_not_in_dxf(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    preview = window.manufacturing_preview
    preview.select_component("Door")
    before = deepcopy(window.project.to_dict())
    preview.hole_diameter_spin.setValue(8)
    preview.edge_offset_spin.setValue(42)
    preview.hole_pitch_spin.setValue(128)
    preview.hole_count_spin.setValue(5)
    application.processEvents()

    assert preview.drilling_parameters.hole_diameter_mm == 8
    assert preview.drilling_parameters.edge_offset_mm == 42
    assert preview.drilling_parameters.pitch_mm == 128
    assert preview.drilling_parameters.hole_count == 5
    assert window.project.to_dict() == before

    document = ezdxf.readfile(export_front_elevation_dxf(window.project, tmp_path / "no-drilling.dxf"))
    assert len(list(document.modelspace().query("CIRCLE"))) == 0
    assert len(list(document.modelspace().query("POINT"))) == 0
    assert len(list(document.modelspace().query("LWPOLYLINE"))) == 6
    window.close()


def test_manufacturing_preview_is_a_separate_workspace():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    assert window.workspace_tabs.currentWidget() is window.workspace_splitter
    window.manufacturing_preview_action.trigger()
    application.processEvents()
    assert window.workspace_tabs.currentWidget() is window.manufacturing_preview
    assert window.manufacturing_preview.cabinet.cabinet_id == "C1"
    assert not window.maximize_3d_action.isEnabled()
    window.workspace_tabs.setCurrentWidget(window.workspace_splitter)
    assert window.maximize_3d_action.isEnabled()
    window.close()
