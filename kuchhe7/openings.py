from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Cabinet, Opening, Room


WALL_IDS = ("NORTH", "EAST", "SOUTH", "WEST")
WALL_LABELS = {
    "NORTH": "North / front wall",
    "EAST": "East / right wall",
    "SOUTH": "South / cabinet wall",
    "WEST": "West / left wall",
}
OPENING_KINDS = ("door", "window")
DOOR_SWINGS = ("Left In", "Right In", "Left Out", "Right Out")
WALL_THICKNESS_MM = 80


@dataclass(frozen=True)
class WallLocalBounds:
    """Furniture bounds expressed along a wall (u) and inward from it (v)."""

    u0: float
    u1: float
    v0: float
    v1: float


def wall_length(room: Room, wall_id: str) -> int:
    if wall_id in ("NORTH", "SOUTH"):
        return room.width
    if wall_id in ("EAST", "WEST"):
        return room.depth
    raise ValueError(f"Unsupported wall identifier: {wall_id}")


def cabinet_wall_bounds(room: Room, cabinet: Cabinet, wall_id: str) -> WallLocalBounds:
    if wall_id == "NORTH":
        return WallLocalBounds(
            cabinet.position_x,
            cabinet.position_x + cabinet.width,
            cabinet.position_y,
            cabinet.position_y + cabinet.depth,
        )
    if wall_id == "SOUTH":
        return WallLocalBounds(
            cabinet.position_x,
            cabinet.position_x + cabinet.width,
            room.depth - (cabinet.position_y + cabinet.depth),
            room.depth - cabinet.position_y,
        )
    if wall_id == "WEST":
        return WallLocalBounds(
            cabinet.position_y,
            cabinet.position_y + cabinet.depth,
            cabinet.position_x,
            cabinet.position_x + cabinet.width,
        )
    if wall_id == "EAST":
        return WallLocalBounds(
            cabinet.position_y,
            cabinet.position_y + cabinet.depth,
            room.width - (cabinet.position_x + cabinet.width),
            room.width - cabinet.position_x,
        )
    raise ValueError(f"Unsupported wall identifier: {wall_id}")


def intervals_overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and a1 > b0


def openings_intersect(first: Opening, second: Opening) -> bool:
    return (
        first.wall_id == second.wall_id
        and intervals_overlap(first.offset, first.offset + first.width, second.offset, second.offset + second.width)
        and intervals_overlap(
            first.elevation,
            first.elevation + first.height,
            second.elevation,
            second.elevation + second.height,
        )
    )


def _door_swing_intersects(bounds: WallLocalBounds, opening: Opening) -> bool:
    if not opening.swing.endswith("In"):
        return False
    radius = float(opening.width)
    hinge = float(opening.offset if opening.swing.startswith("Left") else opening.offset + opening.width)
    sector_u0 = hinge if opening.swing.startswith("Left") else hinge - radius
    sector_u1 = hinge + radius if opening.swing.startswith("Left") else hinge
    overlap_u0 = max(bounds.u0, sector_u0)
    overlap_u1 = min(bounds.u1, sector_u1)
    overlap_v0 = max(bounds.v0, 0.0)
    overlap_v1 = min(bounds.v1, radius)
    if overlap_u0 >= overlap_u1 or overlap_v0 >= overlap_v1:
        return False
    closest_u = min(max(hinge, overlap_u0), overlap_u1)
    closest_v = max(0.0, overlap_v0)
    return (closest_u - hinge) ** 2 + closest_v**2 < radius**2


def opening_furniture_conflict(room: Room, opening: Opening, cabinet: Cabinet) -> str | None:
    cabinet_z0 = cabinet.elevation_z
    cabinet_z1 = cabinet.elevation_z + cabinet.height
    opening_z0 = opening.elevation
    opening_z1 = opening.elevation + opening.height
    if not intervals_overlap(cabinet_z0, cabinet_z1, opening_z0, opening_z1):
        return None

    bounds = cabinet_wall_bounds(room, cabinet, opening.wall_id)
    along_opening = intervals_overlap(bounds.u0, bounds.u1, opening.offset, opening.offset + opening.width)
    touches_wall_zone = bounds.v0 < WALL_THICKNESS_MM and bounds.v1 > 0
    if opening.kind == "window" and along_opening and touches_wall_zone:
        return f"{cabinet.cabinet_id} intersects window {opening.opening_id} opening volume."
    if opening.kind == "door":
        if along_opening and touches_wall_zone:
            return f"{cabinet.cabinet_id} blocks door {opening.opening_id} opening."
        if _door_swing_intersects(bounds, opening):
            return f"{cabinet.cabinet_id} conflicts with door {opening.opening_id} swing clearance."
    return None


def opening_error(room: Room, openings: list[Opening], opening: Opening) -> str | None:
    try:
        opening.validate(room)
    except ValueError as error:
        return str(error)
    for other in openings:
        if other.opening_id != opening.opening_id and openings_intersect(opening, other):
            return f"{opening.opening_id} overlaps opening {other.opening_id} on wall {opening.wall_id}."
    return None
