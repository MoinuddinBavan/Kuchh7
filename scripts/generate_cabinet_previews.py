"""Render the existing cabinet meshes into small, local catalogue previews.

Run this after changing the demonstration furniture geometry or finish palette.
The PNGs are presentation assets. No project or manufacturing data is changed.
"""

from __future__ import annotations

from pathlib import Path

import pyvista as pv
from PySide6.QtWidgets import QApplication

from kuchhe7.catalogue import catalogue_items, create_catalogue_cabinet
from kuchhe7.models import MATERIALS, Room
from kuchhe7.ui.cad_views import Cabinet3DView


def preview_path(type_id: str, finish: str) -> Path:
    slug = finish.lower().replace(" ", "_").replace("/", "_")
    return Path(__file__).resolve().parents[1] / "kuchhe7" / "ui" / "cabinet_previews" / f"{type_id}--{slug}.png"


def main() -> int:
    application = QApplication.instance() or QApplication([])
    view = Cabinet3DView()
    # Render above display resolution so Qt can downsample sharp door gaps and handles.
    view.resize(360, 240)
    view.show()
    application.processEvents()
    view.plotter.hide_axes()
    count = 0
    try:
        for definition in catalogue_items():
            for finish in MATERIALS:
                cabinet = create_catalogue_cabinet(definition.type_id, "Preview")
                cabinet.material = finish
                view._presentation_mode = True
                view._cabinets = [cabinet]
                view._room = Room(max(1200, cabinet.width), max(1200, cabinet.depth))
                view.plotter.clear()
                view.plotter.set_background("#F7F1E9", top="#E6D8C8")
                view._add_cabinet_geometry(cabinet, selected=False)
                view._configure_lighting()
                height = cabinet.height
                z = cabinet.elevation_z
                if definition.category not in ("Wall Cabinets", "Tall Units"):
                    floor = pv.Plane(
                        center=(cabinet.width / 2, cabinet.depth * 0.42, z - 8),
                        direction=(0, 0, 1),
                        i_size=max(cabinet.width * 5, 4200),
                        j_size=max(cabinet.depth * 5, 3600),
                    )
                    floor_actor = view.plotter.add_mesh(
                        floor, color="#E7DACB", ambient=0.72, diffuse=0.28,
                        specular=0.04, pickable=False,
                    )
                    floor_actor.SetUseBounds(False)
                for actor in view.plotter.renderer.actors.values():
                    if actor.GetUseBounds():
                        surface = actor.GetProperty()
                        surface.SetAmbient({"Warm White": 0.61, "Cashmere": 0.49,
                                            "Walnut": 0.50}.get(finish, 0.50))
                        surface.SetDiffuse(0.62)
                view.plotter.camera_position = [
                    (cabinet.width * 0.97, -max(cabinet.width, height) * 1.85, z + height * 1.05),
                    (cabinet.width / 2, cabinet.depth * 0.38, z + height * 0.48),
                    (0, 0, 1),
                ]
                view.plotter.camera.view_angle = 31
                view.plotter.reset_camera()
                view.plotter.camera.zoom(1.02 if height > 1300 else 1.15)
                view.plotter.render()
                application.processEvents()
                path = preview_path(definition.type_id, finish)
                path.parent.mkdir(parents=True, exist_ok=True)
                view.plotter.screenshot(str(path))
                count += 1
    finally:
        view.close()
    print(f"Rendered {count} cabinet previews")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
