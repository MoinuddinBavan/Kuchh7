from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from math import ceil

from .bom import Component, generate_project_bom
from .cut_list import CutListRow, generate_cut_list
from .models import Project


@dataclass(frozen=True)
class SheetSettings:
    length_mm: float = 2440
    width_mm: float = 1220
    kerf_mm: float = 3
    margin_mm: float = 10
    allow_rotation: bool = True
    grain_rotation_restricted: bool = False
    clearance_mm: float = 0
    trim_left_mm: float = 0
    trim_right_mm: float = 0
    trim_top_mm: float = 0
    trim_bottom_mm: float = 0
    min_offcut_length_mm: float = 0
    min_offcut_width_mm: float = 0
    sheet_grain_direction: str = "undefined"

    def validate(self) -> None:
        if self.length_mm <= 0 or self.width_mm <= 0:
            raise ValueError("Sheet length and width must be positive.")
        for name in ("kerf_mm", "margin_mm", "clearance_mm", "trim_left_mm",
                     "trim_right_mm", "trim_top_mm", "trim_bottom_mm",
                     "min_offcut_length_mm", "min_offcut_width_mm"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative.")
        if self.sheet_grain_direction not in ("undefined", "none", "lengthwise", "widthwise"):
            raise ValueError("Unsupported sheet grain direction.")
        if self.usable_length_mm <= 0 or self.usable_width_mm <= 0:
            raise ValueError("Trimming and margins leave no usable sheet area.")

    @property
    def usable_x_mm(self) -> float:
        return self.margin_mm + self.trim_left_mm

    @property
    def usable_y_mm(self) -> float:
        return self.margin_mm + self.trim_top_mm

    @property
    def usable_length_mm(self) -> float:
        return self.length_mm - 2 * self.margin_mm - self.trim_left_mm - self.trim_right_mm

    @property
    def usable_width_mm(self) -> float:
        return self.width_mm - 2 * self.margin_mm - self.trim_top_mm - self.trim_bottom_mm

    @property
    def part_gap_mm(self) -> float:
        """One separation envelope; the larger configured requirement governs."""
        return max(self.kerf_mm, self.clearance_mm)


@dataclass(frozen=True)
class SheetSpecification:
    sheet_id: str
    material: str
    thickness_mm: float
    length_mm: float
    width_mm: float
    finish: str = ""
    material_id: str = ""
    grain_direction: str = "undefined"
    allow_rotation: bool = True
    supplier_reference: str = ""
    revision: str = ""
    status: str = "synthetic"

    def validate(self) -> None:
        if not self.sheet_id or not self.material or self.thickness_mm <= 0:
            raise ValueError("Sheet ID, material and positive thickness are required.")
        if self.length_mm <= 0 or self.width_mm <= 0:
            raise ValueError("Purchased sheet dimensions must be positive.")
        if self.grain_direction not in ("undefined", "none", "lengthwise", "widthwise"):
            raise ValueError("Unsupported sheet grain direction.")


@dataclass(frozen=True)
class PanelInstance:
    cabinet_id: str
    component_name: str
    length_mm: float
    width_mm: float
    thickness_mm: float
    material: str
    instance_number: int
    cabinet_type: str = ""
    grain_direction: str = "undefined"
    profile_id: str = ""
    profile_revision: str = ""
    part_id: str = ""
    wall_id: str = ""
    finish: str = ""
    material_id: str = ""
    finished_length_mm: float = 0
    finished_width_mm: float = 0

    @property
    def instance_id(self) -> str:
        return (f"{self.part_id}:{self.instance_number}" if self.part_id else
                f"{self.cabinet_id}:{self.component_name}:{self.instance_number}")

    @property
    def area_mm2(self) -> float:
        return self.length_mm * self.width_mm


@dataclass(frozen=True)
class PlacedPanel:
    panel: PanelInstance
    sheet_number: int
    x_mm: float
    y_mm: float
    placed_length_mm: float
    placed_width_mm: float
    rotated: bool = False

    @property
    def right_mm(self) -> float:
        return self.x_mm + self.placed_length_mm

    @property
    def bottom_mm(self) -> float:
        return self.y_mm + self.placed_width_mm


@dataclass(frozen=True)
class UnplacedPanel:
    panel: PanelInstance
    reason: str


@dataclass(frozen=True)
class ReusableOffcut:
    sheet_id: str
    sheet_number: int
    material: str
    thickness_mm: float
    finish: str
    x_mm: float
    y_mm: float
    length_mm: float
    width_mm: float
    grain_direction: str
    reusability_status: str = "candidate_for_review"


@dataclass
class SheetLayout:
    sheet_number: int
    placements: list[PlacedPanel] = field(default_factory=list)
    free_rectangles: list[tuple[float, float, float, float]] = field(default_factory=list)

    @property
    def placed_area_mm2(self) -> float:
        return sum(item.panel.area_mm2 for item in self.placements)


@dataclass
class NestingGroup:
    material: str
    thickness_mm: float
    sheets: list[SheetLayout] = field(default_factory=list)
    unplaced: list[UnplacedPanel] = field(default_factory=list)
    finish: str = ""
    material_id: str = ""
    sheet_specification: SheetSpecification | None = None

    @property
    def placements(self) -> list[PlacedPanel]:
        return [placement for sheet in self.sheets for placement in sheet.placements]


@dataclass
class NestingResult:
    settings: SheetSettings
    groups: list[NestingGroup]
    eligible_panels: list[PanelInstance]
    strategy: str = "auto"

    @property
    def placed_panels(self) -> list[PlacedPanel]:
        return [placement for group in self.groups for placement in group.placements]

    @property
    def unplaced_panels(self) -> list[UnplacedPanel]:
        return [panel for group in self.groups for panel in group.unplaced]

    @property
    def sheet_count(self) -> int:
        return sum(len(group.sheets) for group in self.groups)

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_panels)

    @property
    def placed_count(self) -> int:
        return len(self.placed_panels)

    @property
    def unplaced_count(self) -> int:
        return len(self.unplaced_panels)

    @property
    def total_panel_area_mm2(self) -> float:
        return sum(panel.area_mm2 for panel in self.eligible_panels)

    @property
    def placed_area_mm2(self) -> float:
        return sum(panel.panel.area_mm2 for panel in self.placed_panels)

    @property
    def unplaced_area_mm2(self) -> float:
        return sum(panel.panel.area_mm2 for panel in self.unplaced_panels)

    @property
    def utilization_percent(self) -> float:
        sheet_area = sum(
            (group.sheet_specification.length_mm * group.sheet_specification.width_mm
             if group.sheet_specification else self.settings.length_mm * self.settings.width_mm)
            * len(group.sheets) for group in self.groups)
        return (100 * self.placed_area_mm2 / sheet_area) if sheet_area else 0.0

    @property
    def purchased_area_mm2(self) -> float:
        return sum((group.sheet_specification.length_mm * group.sheet_specification.width_mm
                    if group.sheet_specification else self.settings.length_mm * self.settings.width_mm)
                   * len(group.sheets) for group in self.groups)

    @property
    def usable_area_mm2(self) -> float:
        return sum((group.sheet_specification.length_mm - 2 * self.settings.margin_mm
                    - self.settings.trim_left_mm - self.settings.trim_right_mm)
                   * (group.sheet_specification.width_mm - 2 * self.settings.margin_mm
                      - self.settings.trim_top_mm - self.settings.trim_bottom_mm)
                   * len(group.sheets) for group in self.groups if group.sheet_specification)

    @property
    def trim_and_margin_area_mm2(self) -> float:
        return self.purchased_area_mm2 - self.usable_area_mm2

    @property
    def usable_utilization_percent(self) -> float:
        return 100 * self.placed_area_mm2 / self.usable_area_mm2 if self.usable_area_mm2 else 0.0

    @property
    def usable_residual_area_mm2(self) -> float:
        """Includes clearances and small remnants; it is not all irreversible waste."""
        return self.usable_area_mm2 - self.placed_area_mm2

    @property
    def reusable_offcuts(self) -> list[ReusableOffcut]:
        output = []
        for group in self.groups:
            spec = group.sheet_specification
            if spec is None:
                continue
            for sheet in group.sheets:
                for x, y, length, width in sheet.free_rectangles:
                    if (length >= self.settings.min_offcut_length_mm
                            and width >= self.settings.min_offcut_width_mm
                            and length > 0 and width > 0):
                        output.append(ReusableOffcut(
                            spec.sheet_id, sheet.sheet_number, group.material,
                            group.thickness_mm, group.finish, x, y, length, width,
                            spec.grain_direction))
        return output

    @property
    def reusable_offcut_area_mm2(self) -> float:
        return sum(item.length_mm * item.width_mm for item in self.reusable_offcuts)

    @property
    def theoretical_minimum_sheets(self) -> int:
        return sum(ceil(sum(panel.area_mm2 for panel in self.eligible_panels
                            if panel.material == group.material
                            and panel.thickness_mm == group.thickness_mm
                            and panel.finish == group.finish
                            and panel.material_id == group.material_id) /
                        ((group.sheet_specification.length_mm - 2 * self.settings.margin_mm
                          - self.settings.trim_left_mm - self.settings.trim_right_mm)
                         * (group.sheet_specification.width_mm - 2 * self.settings.margin_mm
                            - self.settings.trim_top_mm - self.settings.trim_bottom_mm)))
                   for group in self.groups if group.sheet_specification)


def expand_panel_instances(components: list[Component]) -> list[PanelInstance]:
    """Expand eligible BOM rows into individual rectangular panel records."""
    panels: list[PanelInstance] = []
    ordinals: dict[str, int] = {}
    for component in components:
        ordinals[component.cabinet_id] = ordinals.get(component.cabinet_id, 0) + 1
        if (
            component.quantity <= 0
            or component.length_mm <= 0
            or component.width_mm <= 0
            or component.thickness_mm <= 0
            or component.material.strip().casefold() == "hardware"
        ):
            continue
        for instance_number in range(1, component.quantity + 1):
            panels.append(
                PanelInstance(
                    cabinet_id=component.cabinet_id,
                    component_name=component.name,
                    length_mm=component.cut_length_mm if component.cut_length_mm is not None else component.length_mm,
                    width_mm=component.cut_width_mm if component.cut_width_mm is not None else component.width_mm,
                    thickness_mm=component.thickness_mm,
                    material=component.material,
                    instance_number=instance_number,
                    cabinet_type=component.cabinet_type,
                    grain_direction=component.grain_direction,
                    profile_id=component.profile_id,
                    profile_revision=component.profile_revision,
                    part_id=f"{component.cabinet_id}-P{ordinals[component.cabinet_id]:02d}",
                    finish=component.material,
                    finished_length_mm=component.length_mm,
                    finished_width_mm=component.width_mm,
                )
            )
    return panels


def expand_cut_list_instances(rows: list[CutListRow]) -> list[PanelInstance]:
    """Preserve the authoritative cut-list part, wall and profile for each panel."""
    panels: list[PanelInstance] = []
    for row in rows:
        if row.quantity < 0:
            raise ValueError(f"Negative panel quantity for {row.part_id}.")
        if row.quantity == 0:
            continue
        if min(row.cut_length_mm, row.cut_width_mm, row.thickness_mm) <= 0:
            raise ValueError(f"Invalid cut dimensions for {row.part_id}.")
        for number in range(1, row.quantity + 1):
            panels.append(PanelInstance(
                row.cabinet_id, row.part_name, row.cut_length_mm, row.cut_width_mm,
                row.thickness_mm, row.material, number, grain_direction=row.grain_direction,
                profile_id=row.profile_id, profile_revision=row.profile_revision,
                part_id=row.part_id, wall_id=row.wall_id or "", finish=row.finish,
                finished_length_mm=row.finished_length_mm,
                finished_width_mm=row.finished_width_mm,
            ))
    return panels


def project_panel_instances(project: Project) -> list[PanelInstance]:
    return expand_cut_list_instances(generate_cut_list(project))


def _group_key(panel: PanelInstance) -> tuple:
    if not panel.finish and not panel.material_id:
        return panel.material, panel.thickness_mm
    return panel.material, panel.thickness_mm, panel.finish, panel.material_id


def group_panel_instances(panels: list[PanelInstance]) -> dict[tuple, list[PanelInstance]]:
    ordered = sorted(panels, key=lambda item: (*_group_key(item), item.instance_id))
    return {
        key: list(items)
        for key, items in groupby(ordered, key=_group_key)
    }


@dataclass
class _Shelf:
    y_mm: float
    height_mm: float
    next_x_mm: float


def _orientations(panel: PanelInstance, settings: SheetSettings) -> list[tuple[float, float, bool]]:
    if panel.grain_direction not in ("none", "undefined", "lengthwise", "widthwise"):
        raise ValueError(f"Unsupported grain direction for {panel.instance_id}.")
    orientations = []
    for rotated in (False, True):
        if rotated and (not settings.allow_rotation or settings.grain_rotation_restricted
                        or panel.length_mm == panel.width_mm):
            continue
        if panel.grain_direction in ("lengthwise", "widthwise"):
            if settings.sheet_grain_direction in ("lengthwise", "widthwise"):
                aligned = panel.grain_direction == settings.sheet_grain_direction
                if aligned == rotated:
                    continue
            elif rotated:
                # An undefined sheet grain does not approve a directional turn.
                continue
        orientations.append((panel.width_mm if rotated else panel.length_mm,
                             panel.length_mm if rotated else panel.width_mm, rotated))
    return orientations


def _fits_sheet(panel: PanelInstance, settings: SheetSettings) -> bool:
    usable_length = settings.usable_length_mm
    usable_width = settings.usable_width_mm
    return any(length <= usable_length and width <= usable_width for length, width, _ in _orientations(panel, settings))


def _place_on_sheet(
    panel: PanelInstance,
    sheet: SheetLayout,
    shelves: list[_Shelf],
    settings: SheetSettings,
) -> PlacedPanel | None:
    length_limit = settings.usable_x_mm + settings.usable_length_mm
    width_limit = settings.usable_y_mm + settings.usable_width_mm
    orientations = _orientations(panel, settings)

    for shelf in shelves:
        for length, width, rotated in orientations:
            if width <= shelf.height_mm and shelf.next_x_mm + length <= length_limit:
                placement = PlacedPanel(
                    panel, sheet.sheet_number, shelf.next_x_mm, shelf.y_mm, length, width, rotated
                )
                shelf.next_x_mm += length + settings.part_gap_mm
                sheet.placements.append(placement)
                return placement

    next_y = settings.usable_y_mm
    if shelves:
        next_y = max(shelf.y_mm + shelf.height_mm for shelf in shelves) + settings.part_gap_mm
    for length, width, rotated in orientations:
        if settings.usable_x_mm + length <= length_limit and next_y + width <= width_limit:
            shelf = _Shelf(next_y, width, settings.usable_x_mm + length + settings.part_gap_mm)
            shelves.append(shelf)
            placement = PlacedPanel(
                panel, sheet.sheet_number, settings.usable_x_mm, next_y, length, width, rotated
            )
            sheet.placements.append(placement)
            return placement
    return None


def _place_best_fit(panel: PanelInstance, sheets: list[SheetLayout],
                    settings: SheetSettings) -> bool:
    candidates = []
    for sheet in sheets:
        for index, (x, y, free_length, free_width) in enumerate(sheet.free_rectangles):
            for length, width, rotated in _orientations(panel, settings):
                if length <= free_length and width <= free_width:
                    candidates.append((free_length * free_width - length * width,
                                       min(free_length - length, free_width - width),
                                       sheet.sheet_number, y, x, rotated, index,
                                       sheet, length, width))
    if not candidates:
        return False
    _, _, _, y, x, rotated, index, sheet, length, width = min(candidates, key=lambda row: row[:7])
    free_x, free_y, free_length, free_width = sheet.free_rectangles.pop(index)
    sheet.placements.append(PlacedPanel(panel, sheet.sheet_number, x, y, length, width, rotated))
    gap = settings.part_gap_mm
    right_length = free_length - length - gap
    bottom_width = free_width - width - gap
    # Disjoint guillotine partitions. Residual strips consumed by the envelope
    # are not reported as reusable offcuts.
    if right_length > 0:
        sheet.free_rectangles.append((free_x + length + gap, free_y, right_length, free_width))
    if bottom_width > 0:
        sheet.free_rectangles.append((free_x, free_y + width + gap, length, bottom_width))
    sheet.free_rectangles.sort(key=lambda item: (item[1], item[0], item[2], item[3]))
    return True


def nest_panels(panels: list[PanelInstance], settings: SheetSettings | None = None,
                *, strategy: str = "auto",
                sheet_specs: dict[tuple, SheetSpecification] | None = None,
                require_sheet_specs: bool = False) -> NestingResult:
    """Deterministic best-fit guillotine rectangles, or the prior shelf fallback.

    Neither strategy proves optimality or constitutes executable machine cuts.
    """
    settings = settings or SheetSettings()
    settings.validate()
    if strategy not in ("auto", "best_fit_guillotine", "shelf"):
        raise ValueError("Unsupported nesting strategy.")
    if strategy == "auto":
        best = nest_panels(panels, settings, strategy="best_fit_guillotine",
                           sheet_specs=sheet_specs, require_sheet_specs=require_sheet_specs)
        fallback = nest_panels(panels, settings, strategy="shelf",
                               sheet_specs=sheet_specs, require_sheet_specs=require_sheet_specs)
        return min((best, fallback),
                   key=lambda result: (result.unplaced_count, result.sheet_count,
                                       0 if result.strategy == "best_fit_guillotine" else 1))
    groups: list[NestingGroup] = []
    for key, group_panels in group_panel_instances(panels).items():
        material, thickness = key[:2]
        finish = key[2] if len(key) > 2 else ""
        material_id = key[3] if len(key) > 3 else ""
        group = NestingGroup(material, thickness, finish=finish, material_id=material_id)
        if not material.strip():
            group.unplaced.extend(UnplacedPanel(item, "Material specification is missing")
                                  for item in group_panels)
            groups.append(group)
            continue
        if thickness <= 0:
            group.unplaced.extend(UnplacedPanel(item, "Panel thickness must be positive")
                                  for item in group_panels)
            groups.append(group)
            continue
        spec = (sheet_specs or {}).get(key) or (sheet_specs or {}).get((material, thickness))
        if spec is None and not require_sheet_specs:
            spec = SheetSpecification("DEMO-DEFAULT", material, thickness,
                                      settings.length_mm, settings.width_mm, finish,
                                      material_id, settings.sheet_grain_direction)
        if spec is None:
            group.unplaced.extend(UnplacedPanel(item, "No explicit compatible sheet specification")
                                  for item in group_panels)
            groups.append(group)
            continue
        spec.validate()
        if (spec.material.casefold() != material.casefold() or spec.thickness_mm != thickness
                or (spec.finish and spec.finish != finish)
                or (spec.material_id and spec.material_id != material_id)):
            raise ValueError(f"Sheet {spec.sheet_id} is incompatible with {material} {thickness:g} mm {finish}.")
        group.sheet_specification = spec
        group_settings = SheetSettings(
            spec.length_mm, spec.width_mm, settings.kerf_mm, settings.margin_mm,
            settings.allow_rotation and spec.allow_rotation, settings.grain_rotation_restricted,
            settings.clearance_mm, settings.trim_left_mm, settings.trim_right_mm,
            settings.trim_top_mm, settings.trim_bottom_mm,
            settings.min_offcut_length_mm, settings.min_offcut_width_mm,
            spec.grain_direction)
        group_settings.validate()
        ordered = sorted(
            group_panels,
            key=lambda item: (-item.area_mm2, -max(item.length_mm, item.width_mm), item.instance_id),
        )
        shelf_sets: list[list[_Shelf]] = []
        for panel in ordered:
            if panel.length_mm <= 0 or panel.width_mm <= 0:
                group.unplaced.append(UnplacedPanel(panel, "Cut dimensions must be positive"))
                continue
            if not _fits_sheet(panel, group_settings):
                group.unplaced.append(
                    UnplacedPanel(
                        panel,
                        f"{panel.length_mm:g} x {panel.width_mm:g} mm exceeds the usable sheet area or grain orientation",
                    )
                )
                continue
            placed = False
            for sheet, shelves in zip(group.sheets, shelf_sets):
                if ((strategy == "shelf" and _place_on_sheet(panel, sheet, shelves, group_settings) is not None)
                        or (strategy != "shelf" and _place_best_fit(panel, [sheet], group_settings))):
                    placed = True
                    break
            if not placed:
                sheet = SheetLayout(len(group.sheets) + 1)
                if strategy != "shelf":
                    sheet.free_rectangles.append((group_settings.usable_x_mm,
                                                  group_settings.usable_y_mm,
                                                  group_settings.usable_length_mm,
                                                  group_settings.usable_width_mm))
                shelves: list[_Shelf] = []
                group.sheets.append(sheet)
                shelf_sets.append(shelves)
                added = (_place_on_sheet(panel, sheet, shelves, group_settings) is not None
                         if strategy == "shelf" else _place_best_fit(panel, [sheet], group_settings))
                if not added:
                    group.unplaced.append(UnplacedPanel(panel, "No valid shelf position was found"))
                    group.sheets.pop()
                    shelf_sets.pop()
        if strategy == "shelf":
            usable_right = group_settings.usable_x_mm + group_settings.usable_length_mm
            usable_bottom = group_settings.usable_y_mm + group_settings.usable_width_mm
            for sheet, shelves in zip(group.sheets, shelf_sets):
                for shelf in shelves:
                    if shelf.next_x_mm < usable_right:
                        sheet.free_rectangles.append((shelf.next_x_mm, shelf.y_mm,
                                                      usable_right - shelf.next_x_mm,
                                                      shelf.height_mm))
                if shelves:
                    bottom_y = max(shelf.y_mm + shelf.height_mm for shelf in shelves) + group_settings.part_gap_mm
                    if bottom_y < usable_bottom:
                        sheet.free_rectangles.append((group_settings.usable_x_mm, bottom_y,
                                                      group_settings.usable_length_mm,
                                                      usable_bottom - bottom_y))
        groups.append(group)
    return NestingResult(settings, groups, list(panels), strategy)


def nest_project(project: Project, settings: SheetSettings | None = None, **options) -> NestingResult:
    return nest_panels(project_panel_instances(project), settings, **options)


def rectangles_intersect(first: PlacedPanel, second: PlacedPanel, clearance_mm: float = 0) -> bool:
    """Return True when two placed rectangles overlap, optionally including clearance."""
    return not (
        first.right_mm + clearance_mm <= second.x_mm
        or second.right_mm + clearance_mm <= first.x_mm
        or first.bottom_mm + clearance_mm <= second.y_mm
        or second.bottom_mm + clearance_mm <= first.y_mm
    )
