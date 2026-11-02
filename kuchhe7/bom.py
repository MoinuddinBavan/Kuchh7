from __future__ import annotations

from dataclasses import dataclass

from .catalogue import get_catalogue_item
from .models import Cabinet, Project


@dataclass(frozen=True)
class Component:
    name: str
    length_mm: float
    width_mm: float
    thickness_mm: float
    material: str
    quantity: int
    cabinet_id: str = ""
    cabinet_type: str = ""


def generate_bom(cabinet: Cabinet) -> list[Component]:
    """Generate a demo BOM. These rules are illustrative, not factory approved."""
    cabinet.validate()
    t = cabinet.board_thickness
    catalogue_item = get_catalogue_item(cabinet.cabinet_type_id)
    type_name = catalogue_item.name
    inside_width = cabinet.width - (2 * t)
    inside_height = cabinet.height - (2 * t)
    reveal = 2
    items = [
        Component("Left side panel", cabinet.height, cabinet.depth, t, cabinet.material, 1, cabinet.cabinet_id, type_name),
        Component("Right side panel", cabinet.height, cabinet.depth, t, cabinet.material, 1, cabinet.cabinet_id, type_name),
        Component("Top panel", inside_width, cabinet.depth, t, cabinet.material, 1, cabinet.cabinet_id, type_name),
        Component("Bottom panel", inside_width, cabinet.depth, t, cabinet.material, 1, cabinet.cabinet_id, type_name),
        Component("Back panel", inside_height, inside_width, 6, cabinet.material, 1, cabinet.cabinet_id, type_name),
    ]
    if cabinet.shelf_count:
        items.append(Component("Shelf", inside_width, max(1, cabinet.depth - 20), t, cabinet.material, cabinet.shelf_count, cabinet.cabinet_id, type_name))
    if cabinet.door_count:
        door_width = (cabinet.width - ((cabinet.door_count + 1) * reveal)) / cabinet.door_count
        door_height = cabinet.height - (2 * reveal)
        items.extend([
            Component("Door", door_height, door_width, t, cabinet.material, cabinet.door_count, cabinet.cabinet_id, type_name),
            Component("Concealed hinge", 0, 0, 0, "Hardware", cabinet.door_count * 2, cabinet.cabinet_id, type_name),
        ])
    if cabinet.drawer_count:
        drawer_height = (cabinet.height - ((cabinet.drawer_count + 1) * reveal)) / cabinet.drawer_count
        items.extend([
            Component("Drawer front", drawer_height, cabinet.width - 2 * reveal, t, cabinet.material, cabinet.drawer_count, cabinet.cabinet_id, type_name),
            Component("Drawer box side", max(1, cabinet.depth - 70), max(80, drawer_height - 55), 12, "Drawer board", cabinet.drawer_count * 2, cabinet.cabinet_id, type_name),
            Component("Drawer box front/back", inside_width - 26, max(80, drawer_height - 55), 12, "Drawer board", cabinet.drawer_count * 2, cabinet.cabinet_id, type_name),
            Component("Drawer bottom", inside_width - 26, max(1, cabinet.depth - 70), 6, "Drawer board", cabinet.drawer_count, cabinet.cabinet_id, type_name),
            Component("Drawer runner pair", 0, 0, 0, "Hardware", cabinet.drawer_count, cabinet.cabinet_id, type_name),
        ])
    if catalogue_item.front_style == "corner":
        items.append(Component("Corner return panel", cabinet.height, max(1, cabinet.depth - t), t, cabinet.material, 1, cabinet.cabinet_id, type_name))
    if catalogue_item.front_style == "sink":
        items.append(Component("Sink rail", inside_width, 100, t, cabinet.material, 2, cabinet.cabinet_id, type_name))
    if catalogue_item.front_style == "appliance":
        items.append(Component("Appliance opening rail", inside_width, 100, t, cabinet.material, 2, cabinet.cabinet_id, type_name))
    return items


def generate_project_bom(project: Project) -> list[Component]:
    """Return cabinet-identified BOM rows; a blank project has an empty BOM."""
    project.validate()
    return [component for cabinet in project.cabinets for component in generate_bom(cabinet)]

