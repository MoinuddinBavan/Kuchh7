"""Create a separate, editable luxury kitchen with existing KÜCHE7 objects.

The cabinet and sheet calculations remain the application's illustrative rules.
This script deliberately refuses to overwrite an employee-edited project.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from kuchhe7.catalogue import create_catalogue_cabinet
from kuchhe7.models import Opening, PlacedProduct, Project, Room
from kuchhe7.persistence import load_project, save_project
from kuchhe7.product_libraries import get_product


DEFAULT_OUTPUT = Path("demo_projects/KUCHE7_LUXURY_L_SHAPED_ISLAND_KITCHEN.json")


def build_luxury_kitchen() -> Project:
    project = Project.empty("KÜCHE7 Luxury Walnut & Cashmere Island Kitchen")
    project.room = Room(width=6500, depth=5400, height=2800)

    # WEST entrance opens away from cabinetry. SOUTH daylight sits above the
    # sink; its volume is checked against every cabinet by Project.add_opening.
    project.add_opening(Opening("D1", "door", "WEST", 650, 900, 2100, 0, "Left In"))
    project.add_opening(Opening("W1", "window", "SOUTH", 1600, 1100, 1050, 1100))

    definitions = (
        # The long SOUTH run: cashmere, light stone visual top, walnut pantry.
        ("C1", "base_2_door", 650, 4800, 900, 850, 600, "Cashmere", 0, None),
        ("C2", "sink_base", 1550, 4800, 900, 850, 600, "Cashmere", 0, None),
        ("C3", "base_3_drawer", 2450, 4800, 800, 850, 600, "Warm White", 0, None),
        ("C4", "tall_pantry", 3900, 4800, 800, 2150, 600, "Walnut", 0, None),
        # The adjoining WEST run faces the central work area.
        ("C5", "base_2_door", 0, 3000, 900, 850, 600, "Cashmere", 90, None),
        ("C6", "base_3_drawer", 0, 3900, 900, 850, 600, "Walnut", 90, None),
        # Wall storage avoids the south-facing window opening.
        ("C7", "wall_2_door", 650, 5050, 900, 720, 350, "Warm White", 0, 1450),
        ("C8", "wall_open_shelf", 2800, 5050, 800, 720, 350, "Walnut", 0, 1450),
        # Freestanding, genuine base cabinets: 1800 × 900 mm island footprint.
        ("C9", "base_3_drawer", 2350, 2700, 900, 850, 900, "Walnut", 0, None),
        ("C10", "base_2_door", 3250, 2700, 900, 850, 900, "Cashmere", 0, None),
    )
    for cabinet_id, type_id, x, y, width, height, depth, finish, orientation, elevation in definitions:
        cabinet = create_catalogue_cabinet(type_id, cabinet_id, position_x=x, position_y=y)
        cabinet.width, cabinet.height, cabinet.depth = width, height, depth
        cabinet.material = finish
        cabinet.orientation_degrees = orientation
        if elevation is not None:
            cabinet.elevation_z = elevation
        project.add_cabinet(cabinet)

    # Real product-library meshes. Curated countertop props are placed at the
    # presentation top (cabinet height + 32 mm); each has a valid supporting
    # cabinet under the existing product-placement rules.
    decorations = (
        ("P1", "potted_green_plant", 760, 4940, 882),
        ("P2", "utensil_holder", 1150, 4950, 882),
        ("P3", "flower_vase", 2450, 2900, 882),
        ("P4", "fruit_bowl", 3500, 2900, 882),
        ("P5", "small_sculpture", 2910, 5100, 1705),
        ("P6", "floor_plant", 5400, 4200, 0),
    )
    for item_id, type_id, x, y, z in decorations:
        definition = get_product(type_id)
        project.add_product(PlacedProduct(item_id, type_id, x, y, z,
                                          definition.width, definition.depth, definition.height))

    # A separate catalogue appliance sits on the worktop. It is not a prop
    # and retains its existing unpriced/demo commercial treatment.
    hob = get_product("hob_4_zone")
    project.add_product(PlacedProduct("A1", hob.type_id, 0, 4050, 882,
                                      hob.width, hob.depth, hob.height))
    tap = get_product("tap_arc")
    project.add_product(PlacedProduct("A2", tap.type_id, 2200, 5150, 882,
                                      tap.width, tap.depth, tap.height))

    project.select_cabinet("C9")
    project.select_opening(None)
    project.validate()
    return project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Project already exists; refusing to overwrite: {args.output}")
    project = build_luxury_kitchen()
    path = save_project(project, args.output)
    reopened = load_project(path)
    if reopened.to_dict() != project.to_dict():
        raise RuntimeError("Saved luxury project did not reopen identically.")
    print(f"Saved {path} | cabinets={len(project.cabinets)} | openings={len(project.room.openings)} "
          f"| visual props={sum(item.item_id.startswith('P') for item in project.placed_products)}")


if __name__ == "__main__":
    main()
