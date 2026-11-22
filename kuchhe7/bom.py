from __future__ import annotations

from dataclasses import dataclass

from .catalogue import get_catalogue_item
from .construction import ConstructionProfile, EdgeBandingRule
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
    profile_id: str = ""
    profile_revision: str = ""
    grain_direction: str = "undefined"
    edge_banding: tuple[EdgeBandingRule, ...] = ()
    cut_length_mm: float | None = None
    cut_width_mm: float | None = None


def generate_bom(cabinet: Cabinet) -> list[Component]:
    """Generate a demo BOM. These rules are illustrative, not factory approved."""
    if cabinet.construction_profile is not None:
        return _generate_profile_bom(cabinet)
    return _generate_legacy_bom(cabinet)


def _generate_legacy_bom(cabinet: Cabinet) -> list[Component]:
    """Frozen v0.9 illustrative rules for every project without an explicit profile."""
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


def _generate_profile_bom(cabinet: Cabinet) -> list[Component]:
    """Calculate the same part families using a selected, stored demo rule snapshot."""
    cabinet.validate()
    profile = ConstructionProfile.from_dict(cabinet.construction_profile)
    t = cabinet.board_thickness
    inside_width = cabinet.width - 2 * t
    inside_height = cabinet.height - 2 * t
    reveal = profile.door_reveal_mm
    drawer_height = ((cabinet.height - (cabinet.drawer_count + 1) * reveal) / cabinet.drawer_count
                     if cabinet.drawer_count else 0)
    door_width = ((cabinet.width - (cabinet.door_count + 1) * reveal) / cabinet.door_count
                  if cabinet.door_count else 0)
    if cabinet.door_count and (door_width <= 0 or cabinet.height <= 2 * reveal):
        raise ValueError("Door reveals leave no usable door panel.")
    if cabinet.drawer_count and (drawer_height <= 0 or inside_width <= profile.drawer_width_clearance_mm):
        raise ValueError("Drawer clearances leave no usable drawer panel.")
    type_name = get_catalogue_item(cabinet.cabinet_type_id).name

    def panel(name, length, width, thickness, quantity, material=None):
        if quantity <= 0:
            return None
        if min(length, width, thickness) <= 0:
            raise ValueError(f"{name} has nonpositive dimensions under {profile.profile_id}.")
        banding = tuple(EdgeBandingRule.from_dict(item)
                        for item in profile.edge_banding.get(name, []))
        cut_length, cut_width = length, width
        if profile.compensate_cut_for_banding:
            cut_length -= sum(rule.thickness_mm for rule in banding if rule.edge in ("left", "right"))
            cut_width -= sum(rule.thickness_mm for rule in banding if rule.edge in ("front", "back"))
            if min(cut_length, cut_width) <= 0:
                raise ValueError(f"Edge compensation leaves no usable cut size for {name}.")
        return Component(
            name, length, width, thickness,
            profile.panel_materials.get(name, material or cabinet.material), quantity,
            cabinet.cabinet_id, type_name, profile.profile_id, profile.revision,
            profile.grain_directions.get(name, "undefined"), banding,
            cut_length, cut_width,
        )

    def hardware(name, quantity):
        return Component(name, 0, 0, 0, "Hardware", quantity, cabinet.cabinet_id,
                         type_name, profile.profile_id, profile.revision)

    items = [
        panel("Left side panel", cabinet.height, cabinet.depth, t, 1),
        panel("Right side panel", cabinet.height, cabinet.depth, t, 1),
        panel("Top panel", inside_width, cabinet.depth, t, 1),
        panel("Bottom panel", inside_width, cabinet.depth, t, 1),
    ]
    if profile.include_back:
        items.append(panel("Back panel", inside_height - 2 * profile.back_inset_mm,
                           inside_width - 2 * profile.back_inset_mm,
                           profile.back_thickness_mm, 1))
    if profile.include_shelves and cabinet.shelf_count:
        items.append(panel("Shelf", inside_width, cabinet.depth - profile.shelf_depth_clearance_mm,
                           t, cabinet.shelf_count))
    if cabinet.door_count:
        items.append(panel("Door", cabinet.height - 2 * reveal, door_width,
                           profile.door_thickness_mm, cabinet.door_count))
        if profile.hinges_per_door:
            items.append(hardware("Concealed hinge", cabinet.door_count * profile.hinges_per_door))
    if cabinet.drawer_count:
        items.extend([
            panel("Drawer front", drawer_height, cabinet.width - 2 * reveal, t, cabinet.drawer_count),
            panel("Drawer box side", cabinet.depth - profile.drawer_depth_clearance_mm,
                  max(80, drawer_height - profile.drawer_height_clearance_mm),
                  profile.drawer_box_thickness_mm, cabinet.drawer_count * 2, "Drawer board"),
            panel("Drawer box front/back", inside_width - profile.drawer_width_clearance_mm,
                  max(80, drawer_height - profile.drawer_height_clearance_mm),
                  profile.drawer_box_thickness_mm, cabinet.drawer_count * 2, "Drawer board"),
            panel("Drawer bottom", inside_width - profile.drawer_width_clearance_mm,
                  cabinet.depth - profile.drawer_depth_clearance_mm,
                  profile.drawer_bottom_thickness_mm, cabinet.drawer_count, "Drawer board"),
        ])
        if profile.runner_pairs_per_drawer:
            items.append(hardware("Drawer runner pair", cabinet.drawer_count * profile.runner_pairs_per_drawer))
    style = get_catalogue_item(cabinet.cabinet_type_id).front_style
    if style == "corner":
        items.append(panel("Corner return panel", cabinet.height, cabinet.depth - t, t, 1))
    if style in ("sink", "appliance"):
        name = "Sink rail" if style == "sink" else "Appliance opening rail"
        items.append(panel(name, inside_width, 100, t, 2))
    for name, quantity in sorted(profile.extra_hardware.items()):
        if quantity:
            items.append(hardware(name, quantity))
    actual = [item for item in items if item is not None]
    part_names = {item.name for item in actual if item.material != "Hardware"}
    unknown = (set(profile.panel_materials) | set(profile.grain_directions)
               | set(profile.edge_banding)) - part_names
    if unknown:
        raise ValueError(f"Profile assigns panel specifications to absent part(s): {', '.join(sorted(unknown))}.")
    return actual


def generate_project_bom(project: Project) -> list[Component]:
    """Return cabinet-identified BOM rows; a blank project has an empty BOM."""
    project.validate()
    from .product_libraries import get_product
    for assignment in project.hardware_assignments:
        cabinet = next((item for item in project.cabinets
                        if item.cabinet_id == assignment.cabinet_id), None)
        if cabinet is None or cabinet.construction_profile is None:
            continue
        extras = cabinet.construction_profile.get("extra_hardware", {})
        if get_product(assignment.type_id).name in extras:
            raise ValueError(
                f"{cabinet.cabinet_id}: {assignment.type_id} is both assigned hardware and "
                "profile extra hardware; reconcile it before generating the BOM."
            )
    return [component for cabinet in project.cabinets for component in generate_bom(cabinet)]

