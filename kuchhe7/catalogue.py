from __future__ import annotations

from dataclasses import dataclass


FINISHES = (
    "Warm White",
    "Cashmere",
    "Natural Oak",
    "Walnut",
    "Graphite",
)

LEGACY_FINISH_ALIASES = {
    "White Matte": "Warm White",
    "Cashmere / Greige Matte": "Cashmere",
    "Graphite Grey": "Graphite",
}


def normalized_finish(finish: str) -> str:
    """Return the presentation finish while accepting saved v0.4 names."""
    return LEGACY_FINISH_ALIASES.get(finish, finish)


@dataclass(frozen=True)
class CatalogueItem:
    type_id: str
    category: str
    name: str
    width: int
    height: int
    depth: int
    board_thickness: int = 18
    door_count: int = 0
    drawer_count: int = 0
    shelf_count: int = 1
    front_style: str = "doors"
    elevation_z: int = 0
    supported_finishes: tuple[str, ...] = FINISHES


CATALOGUE = (
    CatalogueItem("base_2_door", "Base Cabinets", "2-Door Base Cabinet", 900, 720, 600, door_count=2),
    CatalogueItem("base_3_drawer", "Base Cabinets", "3-Drawer Base Cabinet", 600, 720, 600, drawer_count=3, shelf_count=0, front_style="drawers"),
    CatalogueItem("base_4_drawer", "Base Cabinets", "4-Drawer Base Cabinet", 800, 720, 600, drawer_count=4, shelf_count=0, front_style="drawers"),
    CatalogueItem("sink_base", "Base Cabinets", "Sink Base Cabinet", 900, 720, 600, door_count=2, shelf_count=0, front_style="sink"),
    CatalogueItem("open_shelf_base", "Base Cabinets", "Open Shelf Base Cabinet", 600, 720, 600, shelf_count=2, front_style="open"),
    CatalogueItem("corner_base", "Base Cabinets", "Corner Base Cabinet", 900, 720, 900, door_count=2, front_style="corner"),
    CatalogueItem("wall_2_door", "Wall Cabinets", "2-Door Wall Cabinet", 800, 720, 350, door_count=2, elevation_z=1400),
    CatalogueItem("wall_lift_up", "Wall Cabinets", "Lift-up Wall Cabinet", 600, 600, 350, door_count=1, front_style="lift_up", elevation_z=1400),
    CatalogueItem("wall_open_shelf", "Wall Cabinets", "Open Shelf Wall Unit", 600, 720, 350, shelf_count=2, front_style="open", elevation_z=1400),
    CatalogueItem("corner_wall", "Wall Cabinets", "Corner Wall Cabinet", 650, 720, 650, door_count=1, front_style="corner", elevation_z=1400),
    CatalogueItem("tall_pantry", "Tall Units", "Tall Pantry Cabinet", 800, 2100, 600, door_count=2, shelf_count=4),
    CatalogueItem("oven_tall", "Tall Units", "Oven / Appliance Tall Unit", 600, 2100, 600, door_count=2, shelf_count=2, front_style="appliance"),
    CatalogueItem("utility_tall", "Tall Units", "Utility Tall Cabinet", 600, 2100, 600, door_count=2, shelf_count=3),
    CatalogueItem("vanity_base", "Vanity", "Vanity Base Cabinet", 900, 720, 500, door_count=2, shelf_count=0, front_style="sink"),
    CatalogueItem("vanity_drawer", "Vanity", "Vanity Drawer Unit", 800, 720, 500, drawer_count=2, shelf_count=0, front_style="drawers"),
)

CATALOGUE_BY_ID = {item.type_id: item for item in CATALOGUE}
CATEGORIES = tuple(dict.fromkeys(item.category for item in CATALOGUE))


def get_catalogue_item(type_id: str) -> CatalogueItem:
    try:
        return CATALOGUE_BY_ID[type_id]
    except KeyError as error:
        raise ValueError(f"Unsupported cabinet type: {type_id}") from error


def catalogue_items(category: str | None = None) -> tuple[CatalogueItem, ...]:
    if category is None:
        return CATALOGUE
    return tuple(item for item in CATALOGUE if item.category == category)


def create_catalogue_cabinet(type_id: str, cabinet_id: str, *, position_x: int = 0, position_y: int | None = None):
    from .models import Cabinet

    item = get_catalogue_item(type_id)
    return Cabinet(
        width=item.width,
        height=item.height,
        depth=item.depth,
        board_thickness=item.board_thickness,
        door_count=item.door_count,
        drawer_count=item.drawer_count,
        shelf_count=item.shelf_count,
        material=item.supported_finishes[0],
        cabinet_id=cabinet_id,
        cabinet_type_id=item.type_id,
        position_x=position_x,
        position_y=0 if position_y is None else position_y,
        elevation_z=item.elevation_z,
    )
