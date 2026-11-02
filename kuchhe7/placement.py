from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Cabinet, Room


@dataclass(frozen=True)
class SnapResult:
    x: int
    y: int
    vertical_guides: tuple[int, ...] = ()
    horizontal_guides: tuple[int, ...] = ()


def volumes_intersect(first: Cabinet, second: Cabinet) -> bool:
    """Return True only when cabinet bounding volumes intersect on X, Y and Z."""
    return (
        first.position_x < second.position_x + second.width
        and first.position_x + first.width > second.position_x
        and first.position_y < second.position_y + second.depth
        and first.position_y + first.depth > second.position_y
        and first.elevation_z < second.elevation_z + second.height
        and first.elevation_z + first.height > second.elevation_z
    )


def placement_error(room: Room, cabinets: list[Cabinet], candidate: Cabinet) -> str | None:
    from .openings import opening_furniture_conflict

    if candidate.position_x < 0 or candidate.position_y < 0:
        return f"{candidate.cabinet_id} is outside the room boundaries."
    if candidate.position_x + candidate.width > room.width or candidate.position_y + candidate.depth > room.depth:
        return f"{candidate.cabinet_id} is outside the {room.width} × {room.depth} mm room boundaries."
    for other in cabinets:
        if other.cabinet_id != candidate.cabinet_id and volumes_intersect(candidate, other):
            return f"{candidate.cabinet_id} overlaps {other.cabinet_id} in 3D. Adjust its position."
    for opening in room.openings:
        conflict = opening_furniture_conflict(room, opening, candidate)
        if conflict:
            return conflict
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
    x_targets = {0, room.width - candidate.width}
    y_targets = {0, room.depth - candidate.depth}
    for other in cabinets:
        if other.cabinet_id == candidate.cabinet_id:
            continue
        x_targets.update({
            other.position_x,
            other.position_x + other.width,
            other.position_x - candidate.width,
            other.position_x + other.width - candidate.width,
        })
        y_targets.update({
            other.position_y,
            other.position_y + other.depth,
            other.position_y - candidate.depth,
            other.position_y + other.depth - candidate.depth,
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
