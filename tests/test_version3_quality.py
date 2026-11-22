"""Presentation-only visual regressions for the Version 3 room scene."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import numpy as np
import pyvista as pv
from PySide6.QtWidgets import QApplication

from kuchhe7.catalogue import catalogue_items
from kuchhe7.models import MATERIALS, Project
from kuchhe7.ui.cad_views import Cabinet3DView
from kuchhe7.ui.presentation_textures import (
    backsplash_texture, door_wood_texture, floor_texture, map_surface, plaster_texture,
    stone_texture, wood_texture,
)


def test_procedural_presentation_textures_are_deterministic_and_nonflat():
    for texture in (wood_texture("Walnut"), wood_texture("Natural Oak"),
                    stone_texture(), floor_texture()):
        pixels = texture.to_array()
        assert pixels.ndim == 3 and pixels.shape[2] >= 3
        assert np.std(pixels[:, :, :3]) > 3
    assert wood_texture("Walnut") is wood_texture("Walnut")
    assert plaster_texture() is plaster_texture()
    assert backsplash_texture() is backsplash_texture()
    assert door_wood_texture() is door_wood_texture()
    assert door_wood_texture("frame") is door_wood_texture("frame")
    mapped = map_surface(pv.Box(bounds=(0, 800, 0, 600, 0, 720)), "front")
    assert mapped.active_texture_coordinates is not None


def test_every_standard_cabinet_has_finish_matched_geometry_preview():
    root = Path(__file__).resolve().parents[1] / "kuchhe7" / "ui" / "cabinet_previews"
    files = [root / f"{item.type_id}--{finish.lower().replace(' ', '_').replace('/', '_')}.png"
             for item in catalogue_items() for finish in MATERIALS]
    assert len(files) == 75
    assert all(path.is_file() and path.stat().st_size > 100 for path in files)


def test_presentation_opening_dressing_is_visual_only_and_cad_mode_remains_clean():
    application = QApplication.instance() or QApplication([])
    project = Project.complete_kitchen_demo()
    before = project.to_dict()
    view = Cabinet3DView()
    view.update_scene(project.room, project.cabinets, project.selected_cabinet_id, True)
    view.set_presentation_mode(True)
    actor_names = set(view.plotter.actors)
    assert "presentation-opening-D1-leaf" in actor_names
    assert "presentation-opening-W1-mullion" in actor_names
    assert "presentation-opening-W1-exterior" in actor_names
    assert "presentation-opening-D1-handle" in actor_names
    assert "presentation-opening-D1-rose" in actor_names
    assert "presentation-opening-D1-spindle" in actor_names
    assert "presentation-opening-D1-door-moulding-0" in actor_names
    assert "presentation-opening-D1-panel-bead-0" in actor_names
    assert "presentation-opening-W1-sill" in actor_names
    assert "presentation-opening-W1-sash-0-0" in actor_names
    assert "presentation-opening-W1-glass-1" in actor_names
    assert "presentation-floor" in actor_names
    assert "presentation-sink-C3-drain" in actor_names
    assert any(name.startswith("presentation-countertop-") for name in actor_names)
    assert view.plotter.actors["presentation-back-wall"].GetTexture() is not None
    view.set_room_walls_visible(False)
    assert not view.plotter.actors["presentation-opening-D1-leaf"].GetVisibility()
    view.set_room_walls_visible(True)
    assert view.plotter.actors["presentation-opening-D1-leaf"].GetVisibility()
    door = project.room.openings[0]
    window = project.room.openings[1]
    room_y0 = -min(cabinet.position_y for cabinet in project.cabinets)
    leaf_bounds = view.plotter.actors["presentation-opening-D1-leaf"].GetBounds()
    sash_bounds = view.plotter.actors["presentation-opening-W1-sash-0-0"].GetBounds()
    assert room_y0 + door.offset <= leaf_bounds[2] < leaf_bounds[3] <= room_y0 + door.offset + door.width
    assert room_y0 + window.offset <= sash_bounds[2] < sash_bounds[3] <= room_y0 + window.offset + window.width
    mounts = [actor for name, actor in view.plotter.actors.items() if "-handle-mount-" in name]
    assert mounts
    view.set_doors_visible(False)
    assert all(not actor.GetVisibility() for actor in mounts)
    view.set_doors_visible(True)
    assert all(actor.GetVisibility() for actor in mounts)
    view.set_presentation_mode(False)
    assert view.environment_actor_count == 0
    assert project.to_dict() == before
    view.close()
