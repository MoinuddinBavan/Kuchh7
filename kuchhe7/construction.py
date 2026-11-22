"""Versioned, explicit cabinet construction snapshots for demonstration validation.

Profiles are stored on individual cabinets. No profile is inferred from a finish or
catalogue name; legacy projects retain the original illustrative BOM. The synthetic
factory below is test data, never a client-approved construction specification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

from .catalogue import get_catalogue_item

GRAIN_DIRECTIONS = {"lengthwise", "widthwise", "none", "undefined"}
EDGES = {"front", "back", "left", "right"}
DEMO_STATUS = "DEMO / NOT FACTORY APPROVED"


@dataclass(frozen=True)
class EdgeBandingRule:
    edge: str
    material: str
    thickness_mm: float
    width_mm: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EdgeBandingRule":
        try:
            rule = cls(**data)
        except TypeError as error:
            raise ValueError(f"Incomplete edge-banding rule: {error}") from error
        if (not isinstance(rule.edge, str) or rule.edge not in EDGES
                or not isinstance(rule.material, str) or not rule.material.strip()
                or any(not isinstance(value, (int, float)) or isinstance(value, bool)
                       or not isfinite(value) or value <= 0
                       for value in (rule.thickness_mm, rule.width_mm))):
            raise ValueError("Edge banding needs a valid edge, material, thickness and width.")
        return rule


@dataclass(frozen=True)
class ConstructionProfile:
    profile_id: str
    revision: str
    cabinet_type_id: str
    status: str
    back_thickness_mm: float
    door_thickness_mm: float
    drawer_box_thickness_mm: float
    drawer_bottom_thickness_mm: float
    door_reveal_mm: float
    shelf_depth_clearance_mm: float
    drawer_depth_clearance_mm: float
    drawer_height_clearance_mm: float
    drawer_width_clearance_mm: float
    back_inset_mm: float
    include_back: bool
    include_shelves: bool
    top_bottom_fit: str
    hinges_per_door: int
    runner_pairs_per_drawer: int
    panel_materials: dict[str, str] = field(default_factory=dict)
    grain_directions: dict[str, str] = field(default_factory=dict)
    edge_banding: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    extra_hardware: dict[str, int] = field(default_factory=dict)
    compensate_cut_for_banding: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConstructionProfile":
        if not isinstance(data, dict):
            raise ValueError("Construction profile must be a JSON object.")
        try:
            return cls(**data)
        except TypeError as error:
            raise ValueError(f"Incomplete or unsupported construction profile: {error}") from error

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate_for(self, cabinet) -> None:
        if (not isinstance(self.profile_id, str) or not self.profile_id.strip()
                or not isinstance(self.revision, str) or not self.revision.strip()):
            raise ValueError("Construction profile ID and revision are required.")
        if self.cabinet_type_id != cabinet.cabinet_type_id:
            raise ValueError("Construction profile cabinet type does not match the cabinet.")
        if self.status != DEMO_STATUS:
            raise ValueError("Only explicitly labelled demonstration profiles are supported.")
        if self.top_bottom_fit != "between_sides":
            raise ValueError("Only the documented between-sides fit is implemented.")
        positive = (
            "back_thickness_mm", "door_thickness_mm", "drawer_box_thickness_mm",
            "drawer_bottom_thickness_mm",
        )
        nonnegative = (
            "door_reveal_mm", "shelf_depth_clearance_mm", "drawer_depth_clearance_mm",
            "drawer_height_clearance_mm", "drawer_width_clearance_mm", "back_inset_mm",
        )
        for key in positive:
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or value <= 0:
                raise ValueError(f"Construction profile {key} must be positive.")
        for key in nonnegative:
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or value < 0:
                raise ValueError(f"Construction profile {key} cannot be negative.")
        if (not isinstance(self.hinges_per_door, int) or isinstance(self.hinges_per_door, bool)
                or not isinstance(self.runner_pairs_per_drawer, int) or isinstance(self.runner_pairs_per_drawer, bool)
                or self.hinges_per_door < 0 or self.runner_pairs_per_drawer < 0):
            raise ValueError("Hardware quantities cannot be negative.")
        if not isinstance(self.include_back, bool) or not isinstance(self.include_shelves, bool):
            raise ValueError("Back and shelf inclusion must be explicit booleans.")
        if not isinstance(self.compensate_cut_for_banding, bool):
            raise ValueError("Cut compensation must be an explicit boolean.")
        if not isinstance(self.panel_materials, dict) or not isinstance(self.grain_directions, dict) or not isinstance(self.edge_banding, dict) or not isinstance(self.extra_hardware, dict):
            raise ValueError("Profile part assignments must be JSON objects.")
        for name, material in self.panel_materials.items():
            if (not isinstance(name, str) or not name.strip()
                    or not isinstance(material, str) or not material.strip()
                    or material.casefold() == "hardware"):
                raise ValueError("Panel material assignments need a part name and material.")
        for name, direction in self.grain_directions.items():
            if (not isinstance(name, str) or not name.strip()
                    or not isinstance(direction, str) or direction not in GRAIN_DIRECTIONS):
                raise ValueError("Unsupported or missing panel grain direction.")
        for name, rules in self.edge_banding.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(rules, list):
                raise ValueError("Edge banding needs a part name.")
            parsed = [EdgeBandingRule.from_dict(rule) for rule in rules]
            if len({rule.edge for rule in parsed}) != len(parsed):
                raise ValueError(f"Duplicate edge-banding side for {name}.")
        for name, quantity in self.extra_hardware.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
                raise ValueError("Extra hardware needs a name and nonnegative integer quantity.")
            if name in ("Concealed hinge", "Drawer runner pair"):
                raise ValueError(f"{name} already has an explicit profile rule; do not duplicate it as extra hardware.")
        t = cabinet.board_thickness
        if cabinet.width <= 2 * t + 2 * self.back_inset_mm:
            raise ValueError("Profile back inset leaves no usable cabinet width.")
        if cabinet.height <= 2 * t + 2 * self.back_inset_mm:
            raise ValueError("Profile back inset leaves no usable cabinet height.")
        if cabinet.depth <= self.shelf_depth_clearance_mm or cabinet.depth <= self.drawer_depth_clearance_mm:
            raise ValueError("Profile clearance leaves no usable cabinet depth.")


def synthetic_profile_for(cabinet) -> ConstructionProfile:
    """Complete, versioned synthetic fixture; applying it is always explicit."""
    style = get_catalogue_item(cabinet.cabinet_type_id).front_style
    return ConstructionProfile(
        profile_id=f"K7-DEMO-{cabinet.cabinet_type_id}", revision="1.0-synthetic",
        cabinet_type_id=cabinet.cabinet_type_id, status=DEMO_STATUS,
        back_thickness_mm=6, door_thickness_mm=cabinet.board_thickness,
        drawer_box_thickness_mm=12, drawer_bottom_thickness_mm=6,
        door_reveal_mm=2, shelf_depth_clearance_mm=20,
        drawer_depth_clearance_mm=70, drawer_height_clearance_mm=55,
        drawer_width_clearance_mm=26, back_inset_mm=0,
        include_back=style != "sink", include_shelves=style != "sink",
        top_bottom_fit="between_sides", hinges_per_door=2,
        runner_pairs_per_drawer=1,
    )
