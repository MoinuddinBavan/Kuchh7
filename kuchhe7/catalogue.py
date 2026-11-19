from __future__ import annotations

from dataclasses import dataclass, field


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


def catalogue_item_from_dict(data: dict) -> "CatalogueItem":
    values = dict(data)
    if "supported_finishes" in values:
        values["supported_finishes"] = tuple(values["supported_finishes"])
    return CatalogueItem(**values)


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
    product_id: str = ""
    template_id: str = ""
    revision: int = 0
    default_finish: str = ""
    min_width: int = 300
    max_width: int = 3000
    min_height: int = 300
    max_height: int = 3000
    min_depth: int = 200
    max_depth: int = 1200
    hardware_defaults: dict[str, int] = field(default_factory=dict)


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

# Keep the original 15-model catalogue stable for existing projects and UI.
WARDROBE_CATALOGUE = (
    CatalogueItem("wardrobe_2_door", "Wardrobe", "Two-door Wardrobe", 1200, 2100, 600, door_count=2, shelf_count=4),
    CatalogueItem("wardrobe_open", "Wardrobe", "Open Wardrobe Shelves", 900, 2100, 550, shelf_count=5, front_style="open"),
)
FURNITURE_FAMILIES = ("Kitchen", "Wardrobe", "Vanity")
_CUSTOM_BY_ID: dict[str, CatalogueItem] = {}
_COMPANY_CUSTOM_IDS: set[str] = set()


def register_custom_items(items: tuple[CatalogueItem, ...] | list[CatalogueItem], *, company: bool = False) -> None:
    """Register immutable custom revisions for lookup by saved projects."""
    for item in items:
        if not item.product_id or not item.template_id or item.revision < 1:
            raise ValueError("Custom cabinet requires product ID, template and revision.")
        if item.type_id in CATALOGUE_BY_ID or item.type_id in {row.type_id for row in WARDROBE_CATALOGUE}:
            raise ValueError(f"Custom cabinet ID conflicts with a built-in model: {item.type_id}")
        prior = _CUSTOM_BY_ID.get(item.type_id)
        if prior is not None and prior != item:
            raise ValueError(f"Custom cabinet revision {item.type_id} has changed; use a new revision.")
        _CUSTOM_BY_ID[item.type_id] = item
        if company:
            _COMPANY_CUSTOM_IDS.add(item.type_id)


def custom_items() -> tuple[CatalogueItem, ...]:
    return tuple(_CUSTOM_BY_ID.values())


def set_company_custom_items(items: list[CatalogueItem]) -> None:
    register_custom_items(items)
    _COMPANY_CUSTOM_IDS.clear()
    _COMPANY_CUSTOM_IDS.update(item.type_id for item in items)


def unregister_custom_item(type_id: str) -> None:
    """Discard an unsaved new revision after a failed local save."""
    _CUSTOM_BY_ID.pop(type_id, None)
    _COMPANY_CUSTOM_IDS.discard(type_id)


def current_custom_items() -> tuple[CatalogueItem, ...]:
    latest: dict[str, CatalogueItem] = {}
    for item in _CUSTOM_BY_ID.values():
        if item.type_id not in _COMPANY_CUSTOM_IDS:
            continue
        if item.product_id not in latest or item.revision > latest[item.product_id].revision:
            latest[item.product_id] = item
    return tuple(sorted(latest.values(), key=lambda item: (item.category, item.name)))


def furniture_items(family: str) -> tuple[CatalogueItem, ...]:
    if family == "Kitchen":
        return tuple(item for item in CATALOGUE if item.category != "Vanity") + tuple(
            item for item in current_custom_items() if item.category not in ("Vanity", "Wardrobe"))
    if family == "Wardrobe":
        return WARDROBE_CATALOGUE + tuple(item for item in current_custom_items() if item.category == "Wardrobe")
    if family == "Vanity":
        return tuple(item for item in CATALOGUE if item.category == "Vanity") + tuple(
            item for item in current_custom_items() if item.category == "Vanity")
    raise ValueError(f"Unsupported furniture family: {family}")


def get_catalogue_item(type_id: str) -> CatalogueItem:
    try:
        return {**CATALOGUE_BY_ID, **{item.type_id: item for item in WARDROBE_CATALOGUE}, **_CUSTOM_BY_ID}[type_id]
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
        material=item.default_finish or item.supported_finishes[0],
        cabinet_id=cabinet_id,
        cabinet_type_id=item.type_id,
        position_x=position_x,
        position_y=0 if position_y is None else position_y,
        elevation_z=item.elevation_z,
    )
