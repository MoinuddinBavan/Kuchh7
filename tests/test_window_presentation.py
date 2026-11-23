"""Presentation-only wall and backsplash geometry around editable openings."""

import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.cut_list import generate_cut_list
from kuchhe7.models import Opening, Project, Room
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.ui.cad_views import Cabinet3DView, south_backsplash_rectangles
from kuchhe7.ui.main_window import MainWindow
from scripts.create_luxury_island_demo import DEFAULT_OUTPUT


def _crosses_aperture(bounds, opening):
    return (bounds[0] < opening.offset + opening.width
            and bounds[1] > opening.offset
            and bounds[4] < opening.elevation + opening.height
            and bounds[5] > opening.elevation)


def _view(project):
    QApplication.instance() or QApplication([])
    view = Cabinet3DView()
    view.update_scene(project.room, project.cabinets, project.selected_cabinet_id, True,
                      placed_products=project.placed_products)
    view.set_presentation_mode(True)
    return view


def test_luxury_window_wall_and_backsplash_have_real_opening_clearance():
    project = load_project(DEFAULT_OUTPUT)
    before = project.to_dict()
    opening = next(item for item in project.room.openings if item.kind == "window")
    view = _view(project)
    try:
        actors = view.plotter.renderer.actors
        backsplash = [(name, actor.GetBounds()) for name, actor in actors.items()
                      if name.startswith("presentation-backsplash")]
        wall = [(name, actor.GetBounds()) for name, actor in actors.items()
                if name.startswith("presentation-back-wall")]
        assert backsplash and wall
        assert all(not _crosses_aperture(bounds, opening) for _, bounds in backsplash + wall)
        assert all(bounds[0] >= 650 and bounds[1] <= 3250 for _, bounds in backsplash)
        glass = actors["presentation-opening-W1-glass"]
        assert glass.GetVisibility()
        assert opening.offset < glass.GetBounds()[0] < glass.GetBounds()[1] < opening.offset + opening.width
        assert "presentation-opening-W1-sill" in actors
        assert "presentation-opening-D1-leaf" in actors
        assert project.to_dict() == before
    finally:
        view.close()


def test_resized_repositioned_window_rebuilds_cleanly_and_persists(tmp_path):
    project = load_project(DEFAULT_OUTPUT)
    manufacturing_before = (generate_project_bom(project), generate_cut_list(project), nest_project(project))
    project.replace_opening(Opening("W1", "window", "SOUTH", 1700, 900, 1050, 1120))
    reopened = load_project(save_project(project, tmp_path / "repositioned-window.json"))
    assert reopened.room.openings[1].offset == 1700
    assert reopened.room.openings[1].width == 900
    assert reopened.room.openings[1].elevation == 1120
    assert (generate_project_bom(reopened), generate_cut_list(reopened), nest_project(reopened)) == manufacturing_before
    view = _view(reopened)
    try:
        opening = reopened.room.openings[1]
        assert all(not _crosses_aperture(actor.GetBounds(), opening)
                   for name, actor in view.plotter.renderer.actors.items()
                   if name.startswith(("presentation-backsplash", "presentation-back-wall")))
        view.update_scene(reopened.room, reopened.cabinets, reopened.selected_cabinet_id, True,
                          placed_products=reopened.placed_products)
        assert "presentation-opening-W1-glass" in view.plotter.renderer.actors
    finally:
        view.close()


def test_south_door_trim_clips_adjacent_backsplash_and_other_wall_window_remains_visible():
    project = Project.empty("Opening geometry fixture")
    project.room = Room(width=3600, depth=3200, height=2600)
    project.add_opening(Opening("D1", "door", "SOUTH", 1450, 900, 2100, 0, "Left In"))
    project.add_opening(Opening("W1", "window", "NORTH", 1200, 900, 900, 1100))
    cabinet = create_catalogue_cabinet("base_2_door", "C1", position_x=500, position_y=2600)
    cabinet.width = 950
    project.add_cabinet(cabinet)
    project.validate()
    rectangles = south_backsplash_rectangles(project.room, project.cabinets)
    assert rectangles and max(item[1] for item in rectangles) == 1408
    view = _view(project)
    try:
        assert "presentation-opening-D1-leaf" in view.plotter.renderer.actors
        assert "presentation-opening-W1-glass" in view.plotter.renderer.actors
    finally:
        view.close()


def test_existing_six_cabinet_west_window_keeps_south_backsplash():
    project = Project.complete_kitchen_demo()
    baseline = deepcopy(project.to_dict())
    rectangles = south_backsplash_rectangles(project.room, project.cabinets)
    assert len(rectangles) == 1
    assert rectangles[0][:4] == (250.0, 2450.0, 760.0, 1360.0)
    assert project.to_dict() == baseline


def test_luxury_window_remains_selectable_and_editable_in_2d_inspector():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.project = load_project(DEFAULT_OUTPUT)
        before_bom = generate_project_bom(window.project)
        window.refresh_all(reset_camera=True)
        window.presentation_view_action.setChecked(True)
        window.resize(1600, 900)
        window.show()
        window._set_plan_expanded(True)
        application.processEvents()
        hit = window.plan_view.mapFromScene(
            window.plan_view._opening_items["W1"].sceneBoundingRect().center()
        )
        QTest.mouseClick(window.plan_view.viewport(), Qt.MouseButton.LeftButton, pos=hit)
        application.processEvents()
        assert window.plan_view._selected_opening_id == "W1"
        assert window._inspector_context == "opening"
        window.opening_width_spin.setValue(1000)
        window.opening_offset_spin.setValue(1650)
        window.opening_height_spin.setValue(1000)
        window.opening_elevation_spin.setValue(1150)
        application.processEvents()
        opening = window.project.selected_opening
        assert (opening.offset, opening.width, opening.height, opening.elevation) == (1650, 1000, 1000, 1150)
        assert generate_project_bom(window.project) == before_bom
        assert all(not _crosses_aperture(actor.GetBounds(), opening)
                   for name, actor in window.view3d.plotter.renderer.actors.items()
                   if name.startswith(("presentation-backsplash", "presentation-back-wall")))
    finally:
        window.close()
