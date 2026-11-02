import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
from openpyxl import load_workbook
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.ui.main_window import MainWindow


def _cabinet_actor_names(window: MainWindow) -> set[str]:
    return {name for name in window.view3d.plotter.actors if name.startswith(("C1-", "C2-", "C3-"))}


def test_presentation_toggle_adds_room_without_changing_project():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    application.processEvents()
    before = deepcopy(window.project.to_dict())
    cad_actors = _cabinet_actor_names(window)

    assert not window.view3d.presentation_mode
    assert window.view3d.environment_actor_count == 0
    assert not any(name.startswith("presentation-") for name in window.view3d.plotter.actors)

    window.presentation_view_action.setChecked(True)
    application.processEvents()
    names = set(window.view3d.plotter.actors)
    assert window.view3d.presentation_mode
    assert window.view3d.environment_actor_count >= 7
    assert {"presentation-floor", "presentation-back-wall", "presentation-side-wall"} <= names
    assert {"presentation-countertop-C1", "presentation-plinth-C1", "presentation-backsplash"} <= names
    assert window.project.to_dict() == before

    floor_bounds = window.view3d.plotter.actors["presentation-floor"].mapper.dataset.bounds
    assert floor_bounds[1] - floor_bounds[0] == window.project.room.width
    assert floor_bounds[3] - floor_bounds[2] == window.project.room.depth

    window.presentation_view_action.setChecked(False)
    application.processEvents()
    assert not window.view3d.presentation_mode
    assert window.view3d.environment_actor_count == 0
    assert _cabinet_actor_names(window) == cad_actors
    assert window.project.to_dict() == before
    window.close()


def test_room_walls_can_be_hidden_while_floor_remains_visible():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    window.presentation_view_action.setChecked(True)
    application.processEvents()

    window.hide_room_walls_action.setChecked(True)
    application.processEvents()
    assert all(not actor.GetVisibility() for actor in window.view3d._room_wall_actors)
    assert window.view3d.plotter.actors["presentation-floor"].GetVisibility()
    assert all(any(name.startswith(cabinet_id) for name in window.view3d.plotter.actors)
               for cabinet_id in ("C1", "C2", "C3"))

    window.hide_room_walls_action.setChecked(False)
    assert all(actor.GetVisibility() for actor in window.view3d._room_wall_actors)
    window.close()


def test_view_switching_preserves_bom_xlsx_and_dxf(tmp_path):
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_sample_kitchen()
    before_project = deepcopy(window.project.to_dict())
    before_bom = generate_project_bom(window.project)

    for _ in range(3):
        window.presentation_view_action.setChecked(True)
        window.view3d.fit_all_cabinets()
        window.presentation_view_action.setChecked(False)
    application.processEvents()

    assert window.project.to_dict() == before_project
    assert generate_project_bom(window.project) == before_bom
    workbook = load_workbook(export_bom_xlsx(window.project, tmp_path / "presentation-check.xlsx"), data_only=True)["BOM"]
    assert workbook["A1"].value == "kuchhe7 Demonstration BOM - NOT FACTORY APPROVED"
    document = ezdxf.readfile(export_front_elevation_dxf(window.project, tmp_path / "presentation-check.dxf"))
    assert document.header["$INSUNITS"] == 4
    assert len(list(document.modelspace().query("LWPOLYLINE"))) == 3
    assert not any(name.startswith("presentation-") for name in _cabinet_actor_names(window))
    window.close()
