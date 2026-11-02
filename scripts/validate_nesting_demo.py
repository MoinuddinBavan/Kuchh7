"""Validate the v0.9 demonstration nesting result and print reproducible statistics."""

from kuchhe7.models import Project
from kuchhe7.nesting import SheetSettings, nest_project, rectangles_intersect


def main() -> None:
    project = Project.complete_kitchen_demo("AIZ Complete Kitchen Demo")
    settings = SheetSettings()
    result = nest_project(project, settings)

    assert result.eligible_count == result.placed_count + result.unplaced_count
    for group in result.groups:
        for sheet in group.sheets:
            for placed in sheet.placements:
                assert placed.x_mm >= settings.margin_mm
                assert placed.y_mm >= settings.margin_mm
                assert placed.right_mm <= settings.length_mm - settings.margin_mm
                assert placed.bottom_mm <= settings.width_mm - settings.margin_mm
            for index, first in enumerate(sheet.placements):
                for second in sheet.placements[index + 1 :]:
                    assert not rectangles_intersect(first, second, settings.kerf_mm)

    print(f"Project: {project.name}")
    print(f"Sheet: {settings.length_mm:g} x {settings.width_mm:g} mm")
    print(
        f"Eligible: {result.eligible_count}; placed: {result.placed_count}; "
        f"unplaced: {result.unplaced_count}; sheets: {result.sheet_count}"
    )
    print(
        f"Panel area: {result.total_panel_area_mm2 / 1_000_000:.3f} m2; "
        f"utilization: {result.utilization_percent:.1f}%"
    )
    for group in result.groups:
        print(
            f"- {group.material} / {group.thickness_mm:g} mm: "
            f"{len(group.placements)} placed, {len(group.unplaced)} unplaced, "
            f"{len(group.sheets)} sheet(s)"
        )


if __name__ == "__main__":
    main()
