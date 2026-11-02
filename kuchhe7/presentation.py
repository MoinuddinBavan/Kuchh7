from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .catalogue import get_catalogue_item
from .models import Cabinet


@dataclass(frozen=True)
class BaseRun:
    """A contiguous, presentation-only run of compatible floor cabinets."""

    cabinet_ids: tuple[str, ...]
    x0: int
    x1: int
    y0: int
    y1: int
    top_z: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0


def connected_base_runs(
    cabinets: Iterable[Cabinet],
    *,
    gap_tolerance: int = 5,
    alignment_tolerance: int = 5,
) -> list[BaseRun]:
    """Group touching base/vanity cabinets without changing project geometry.

    Runs require matching back-wall alignment and top height. A real gap starts a
    new run, so presentation countertops and plinths never bridge unrelated units.
    """

    eligible = [
        cabinet
        for cabinet in cabinets
        if cabinet.elevation_z == 0
        and get_catalogue_item(cabinet.cabinet_type_id).category in ("Base Cabinets", "Vanity")
    ]
    eligible.sort(key=lambda cabinet: (cabinet.position_y + cabinet.depth, cabinet.height, cabinet.position_x))

    runs: list[list[Cabinet]] = []
    for cabinet in eligible:
        if not runs:
            runs.append([cabinet])
            continue
        previous = runs[-1][-1]
        same_back = abs(
            (cabinet.position_y + cabinet.depth) - (previous.position_y + previous.depth)
        ) <= alignment_tolerance
        same_top = abs(
            (cabinet.elevation_z + cabinet.height) - (previous.elevation_z + previous.height)
        ) <= alignment_tolerance
        gap = cabinet.position_x - (previous.position_x + previous.width)
        if same_back and same_top and -gap_tolerance <= gap <= gap_tolerance:
            runs[-1].append(cabinet)
        else:
            runs.append([cabinet])

    return [
        BaseRun(
            cabinet_ids=tuple(cabinet.cabinet_id for cabinet in run),
            x0=min(cabinet.position_x for cabinet in run),
            x1=max(cabinet.position_x + cabinet.width for cabinet in run),
            y0=min(cabinet.position_y for cabinet in run),
            y1=max(cabinet.position_y + cabinet.depth for cabinet in run),
            top_z=max(cabinet.elevation_z + cabinet.height for cabinet in run),
        )
        for run in runs
    ]
