"""Independent geometric checks for demonstration sheet layouts.

This validates a result without using its placement/search algorithm. It does
not certify a machine cutting sequence or factory process.
"""

from __future__ import annotations

from collections import Counter

from .nesting import NestingResult

TOLERANCE_MM = 1e-6


def validate_nesting_result(result: NestingResult) -> None:
    expected = Counter(panel.instance_id for panel in result.eligible_panels)
    actual = Counter(placed.panel.instance_id for placed in result.placed_panels)
    actual.update(item.panel.instance_id for item in result.unplaced_panels)
    if expected != actual or any(count != 1 for count in expected.values()):
        raise ValueError("Nesting has lost, duplicated or non-unique panel instances.")

    gap = result.settings.part_gap_mm
    for group in result.groups:
        spec = group.sheet_specification
        if group.sheets and spec is None:
            raise ValueError("Allocated sheet has no specification.")
        if spec is None:
            continue
        left = result.settings.margin_mm + result.settings.trim_left_mm
        top = result.settings.margin_mm + result.settings.trim_top_mm
        right = spec.length_mm - result.settings.margin_mm - result.settings.trim_right_mm
        bottom = spec.width_mm - result.settings.margin_mm - result.settings.trim_bottom_mm
        for sheet in group.sheets:
            for index, (x, y, length, width) in enumerate(sheet.free_rectangles):
                if (length <= 0 or width <= 0 or x < left - TOLERANCE_MM
                        or y < top - TOLERANCE_MM or x + length > right + TOLERANCE_MM
                        or y + width > bottom + TOLERANCE_MM):
                    raise ValueError("Residual rectangle exceeds the usable sheet boundary.")
                for placed in sheet.placements:
                    if not (x + length <= placed.x_mm + TOLERANCE_MM or
                            placed.right_mm <= x + TOLERANCE_MM or
                            y + width <= placed.y_mm + TOLERANCE_MM or
                            placed.bottom_mm <= y + TOLERANCE_MM):
                        raise ValueError("Residual rectangle overlaps a placed panel.")
                for other_x, other_y, other_length, other_width in sheet.free_rectangles[index + 1:]:
                    if not (x + length <= other_x + TOLERANCE_MM or
                            other_x + other_length <= x + TOLERANCE_MM or
                            y + width <= other_y + TOLERANCE_MM or
                            other_y + other_width <= y + TOLERANCE_MM):
                        raise ValueError("Residual rectangles overlap and cannot represent distinct offcuts.")
            for first_index, first in enumerate(sheet.placements):
                panel = first.panel
                if (panel.material != group.material or panel.thickness_mm != group.thickness_mm
                        or panel.finish != group.finish or panel.material_id != group.material_id):
                    raise ValueError(f"Incompatible panel on sheet {spec.sheet_id}.")
                required_size = ((panel.width_mm, panel.length_mm) if first.rotated else
                                 (panel.length_mm, panel.width_mm))
                if (abs(first.placed_length_mm - required_size[0]) > TOLERANCE_MM or
                        abs(first.placed_width_mm - required_size[1]) > TOLERANCE_MM):
                    raise ValueError(f"Panel {panel.instance_id} has incorrect cut size.")
                if first.rotated and (not result.settings.allow_rotation or not spec.allow_rotation
                                      or result.settings.grain_rotation_restricted):
                    raise ValueError(f"Panel {panel.instance_id} was rotated without permission.")
                if panel.grain_direction in ("lengthwise", "widthwise"):
                    if spec.grain_direction in ("lengthwise", "widthwise"):
                        aligned = panel.grain_direction == spec.grain_direction
                        if aligned == first.rotated:
                            raise ValueError(f"Panel {panel.instance_id} violates sheet grain.")
                    elif first.rotated:
                        raise ValueError(f"Panel {panel.instance_id} rotated with unknown sheet grain.")
                if (first.x_mm < left - TOLERANCE_MM or first.y_mm < top - TOLERANCE_MM
                        or first.right_mm > right + TOLERANCE_MM
                        or first.bottom_mm > bottom + TOLERANCE_MM):
                    raise ValueError(f"Panel {panel.instance_id} exceeds usable sheet boundary.")
                for second in sheet.placements[first_index + 1:]:
                    separated = (first.right_mm + gap <= second.x_mm + TOLERANCE_MM or
                                 second.right_mm + gap <= first.x_mm + TOLERANCE_MM or
                                 first.bottom_mm + gap <= second.y_mm + TOLERANCE_MM or
                                 second.bottom_mm + gap <= first.y_mm + TOLERANCE_MM)
                    if not separated:
                        raise ValueError(f"Panels {panel.instance_id} and {second.panel.instance_id} overlap or lack clearance.")


def nesting_fingerprint(result: NestingResult) -> tuple:
    """Stable input signature for checking a displayed layout against current inputs."""
    return (result.settings, result.strategy,
            tuple(sorted((panel.instance_id, panel.material, panel.finish, panel.material_id,
                          panel.thickness_mm, panel.length_mm, panel.width_mm,
                          panel.grain_direction, panel.profile_id, panel.profile_revision)
                         for panel in result.eligible_panels)),
            tuple((group.material, group.thickness_mm, group.finish, group.material_id,
                   group.sheet_specification) for group in result.groups))
