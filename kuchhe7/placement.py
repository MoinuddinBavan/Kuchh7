from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Cabinet, PlacedProduct, Room


@dataclass(frozen=True)
class SnapResult:
    x: int
    y: int
    vertical_guides: tuple[int, ...] = ()
    horizontal_guides: tuple[int, ...] = ()


def volumes_intersect(first: Cabinet, second: Cabinet) -> bool:
    """Return True only when cabinet bounding volumes intersect on X, Y and Z."""
    first_width = getattr(first, "footprint_width", first.width)
    first_depth = getattr(first, "footprint_depth", first.depth)
    second_width = getattr(second, "footprint_width", second.width)
    second_depth = getattr(second, "footprint_depth", second.depth)
    return (
        first.position_x < second.position_x + second_width
        and first.position_x + first_width > second.position_x
        and first.position_y < second.position_y + second_depth
        and first.position_y + first_depth > second.position_y
        and first.elevation_z < second.elevation_z + second.height
        and first.elevation_z + first.height > second.elevation_z
    )


def placement_error(room: Room, cabinets: list[Cabinet], candidate: Cabinet,
                    products: list[PlacedProduct] | None = None) -> str | None:
    from .openings import opening_furniture_conflict

    if candidate.position_x < 0 or candidate.position_y < 0:
        return f"{candidate.cabinet_id} is outside the room boundaries."
    if candidate.position_x + candidate.footprint_width > room.width or candidate.position_y + candidate.footprint_depth > room.depth:
        return f"{candidate.cabinet_id} is outside the {room.width} × {room.depth} mm room boundaries."
    for other in cabinets:
        if other.cabinet_id != candidate.cabinet_id and volumes_intersect(candidate, other):
            return f"{candidate.cabinet_id} overlaps {other.cabinet_id} in 3D. Adjust its position."
    for product in products or []:
        if volumes_intersect(candidate, product):
            if product.type_id == "small_sculpture":
                from .catalogue import get_catalogue_item

                if get_catalogue_item(candidate.cabinet_type_id).front_style == "open":
                    t = candidate.board_thickness
                    tops = [candidate.elevation_z + t
                            + (candidate.height - 2 * t) * (index + 1) / (candidate.shelf_count + 1)
                            + t / 2 for index in range(candidate.shelf_count)]
                    if (product.position_x >= candidate.position_x
                            and product.position_y >= candidate.position_y
                            and product.position_x + product.footprint_width <= candidate.position_x + candidate.footprint_width
                            and product.position_y + product.footprint_depth <= candidate.position_y + candidate.footprint_depth
                            and any(abs(product.elevation_z - top) <= 8 for top in tops)):
                        continue
            return f"{candidate.cabinet_id} overlaps product {product.item_id} in 3D."
    for opening in room.openings:
        conflict = opening_furniture_conflict(room, opening, candidate)
        if conflict:
            return conflict
    return None


def product_placement_error(
    room: Room, cabinets: list[Cabinet], products: list[PlacedProduct], candidate: PlacedProduct,
) -> str | None:
    """Check room and 3D volumes without applying installation standards."""
    try:
        candidate.validate(room)
    except ValueError as error:
        return str(error)
    from .product_libraries import CURATED_PROP_IDS
    from .catalogue import get_catalogue_item

    support = None
    if candidate.type_id in CURATED_PROP_IDS:
        if candidate.type_id == "floor_plant":
            if candidate.elevation_z != 0:
                return "Floor Plant must rest on the floor (elevation 0 mm)."
        else:
            for cabinet in cabinets:
                fits = (candidate.position_x >= cabinet.position_x
                        and candidate.position_y >= cabinet.position_y
                        and candidate.position_x + candidate.footprint_width
                        <= cabinet.position_x + cabinet.footprint_width
                        and candidate.position_y + candidate.footprint_depth
                        <= cabinet.position_y + cabinet.footprint_depth)
                if not fits:
                    continue
                if candidate.type_id == "small_sculpture":
                    if get_catalogue_item(cabinet.cabinet_type_id).front_style != "open":
                        continue
                    thickness = cabinet.board_thickness
                    shelf_tops = [cabinet.elevation_z + thickness
                                  + (cabinet.height - 2 * thickness) * (index + 1) / (cabinet.shelf_count + 1)
                                  + thickness / 2
                                  for index in range(cabinet.shelf_count)]
                    if any(abs(candidate.elevation_z - top) <= 8 for top in shelf_tops):
                        support = cabinet
                        break
                elif (cabinet.elevation_z == 0
                      and get_catalogue_item(cabinet.cabinet_type_id).front_style != "open"
                      and 0 <= candidate.elevation_z - (cabinet.elevation_z + cabinet.height) <= 40):
                    support = cabinet
                    break
            if support is None:
                return (f"{candidate.item_id} needs a supporting "
                        + ("open cabinet shelf." if candidate.type_id == "small_sculpture"
                           else "cabinet countertop."))
    for cabinet in cabinets:
        if cabinet is not support and volumes_intersect(candidate, cabinet):
            return f"{candidate.item_id} overlaps cabinet {cabinet.cabinet_id} in 3D."
    for other in products:
        if other.item_id == candidate.item_id or not volumes_intersect(candidate, other):
            continue
        # Sample tap and sink are intentionally allowed to share space.
        if {candidate.type_id, other.type_id} == {"tap_arc", "sink_single"}:
            continue
        return f"{candidate.item_id} overlaps product {other.item_id} in 3D."
    return None


def snap_position(
    candidate: Cabinet,
    room: Room,
    cabinets: list[Cabinet],
    *,
    scale_pixels_per_mm: float,
    snap_enabled: bool = True,
    grid_enabled: bool = True,
    grid_mm: int = 100,
    tolerance_pixels: float = 12.0,
) -> SnapResult:
    """Snap a top-left footprint position using a pixel-consistent tolerance."""
    raw_x, raw_y = float(candidate.position_x), float(candidate.position_y)
    if not snap_enabled:
        return SnapResult(round(raw_x), round(raw_y))

    tolerance_mm = tolerance_pixels / max(scale_pixels_per_mm, 0.0001)
    x_targets = {0, room.width - candidate.footprint_width}
    y_targets = {0, room.depth - candidate.footprint_depth}
    for other in cabinets:
        if other.cabinet_id == candidate.cabinet_id:
            continue
        x_targets.update({
            other.position_x,
            other.position_x + other.footprint_width,
            other.position_x - candidate.footprint_width,
            other.position_x + other.footprint_width - candidate.footprint_width,
        })
        y_targets.update({
            other.position_y,
            other.position_y + other.footprint_depth,
            other.position_y - candidate.footprint_depth,
            other.position_y + other.footprint_depth - candidate.footprint_depth,
        })

    def nearest(value: float, targets: set[int]) -> tuple[float, int | None]:
        valid = [(abs(value - target), target) for target in targets if abs(value - target) <= tolerance_mm]
        if not valid:
            return value, None
        _distance, target = min(valid, key=lambda pair: (pair[0], pair[1]))
        return float(target), target

    snapped_x, guide_x = nearest(raw_x, x_targets)
    snapped_y, guide_y = nearest(raw_y, y_targets)
    if grid_enabled:
        if guide_x is None:
            grid_x = round(raw_x / grid_mm) * grid_mm
            if abs(raw_x - grid_x) <= tolerance_mm:
                snapped_x = float(grid_x)
        if guide_y is None:
            grid_y = round(raw_y / grid_mm) * grid_mm
            if abs(raw_y - grid_y) <= tolerance_mm:
                snapped_y = float(grid_y)

    return SnapResult(
        round(snapped_x),
        round(snapped_y),
        () if guide_x is None else (guide_x,),
        () if guide_y is None else (guide_y,),
    )
