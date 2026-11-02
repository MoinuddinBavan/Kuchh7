from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby

from .bom import Component, generate_project_bom
from .models import Project


@dataclass(frozen=True)
class SheetSettings:
    length_mm: float = 2440
    width_mm: float = 1220
    kerf_mm: float = 3
    margin_mm: float = 10
    allow_rotation: bool = True
    grain_rotation_restricted: bool = False

    def validate(self) -> None:
        if self.length_mm <= 0 or self.width_mm <= 0:
            raise ValueError("Sheet length and width must be positive.")
        if self.kerf_mm < 0 or self.margin_mm < 0:
            raise ValueError("Kerf and margin cannot be negative.")
        if self.length_mm <= 2 * self.margin_mm or self.width_mm <= 2 * self.margin_mm:
            raise ValueError("Edge margins leave no usable sheet area.")


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

    @property
    def instance_id(self) -> str:
        return f"{self.cabinet_id}:{self.component_name}:{self.instance_number}"

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


@dataclass
class SheetLayout:
    sheet_number: int
    placements: list[PlacedPanel] = field(default_factory=list)

    @property
    def placed_area_mm2(self) -> float:
        return sum(item.panel.area_mm2 for item in self.placements)


@dataclass
class NestingGroup:
    material: str
    thickness_mm: float
    sheets: list[SheetLayout] = field(default_factory=list)
    unplaced: list[UnplacedPanel] = field(default_factory=list)

    @property
    def placements(self) -> list[PlacedPanel]:
        return [placement for sheet in self.sheets for placement in sheet.placements]


@dataclass
class NestingResult:
    settings: SheetSettings
    groups: list[NestingGroup]
    eligible_panels: list[PanelInstance]

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
        sheet_area = self.sheet_count * self.settings.length_mm * self.settings.width_mm
        return (100 * self.placed_area_mm2 / sheet_area) if sheet_area else 0.0


def expand_panel_instances(components: list[Component]) -> list[PanelInstance]:
    """Expand eligible BOM rows into individual rectangular panel records."""
    panels: list[PanelInstance] = []
    for component in components:
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
                    length_mm=component.length_mm,
                    width_mm=component.width_mm,
                    thickness_mm=component.thickness_mm,
                    material=component.material,
                    instance_number=instance_number,
                    cabinet_type=component.cabinet_type,
                )
            )
    return panels


def project_panel_instances(project: Project) -> list[PanelInstance]:
    return expand_panel_instances(generate_project_bom(project))


def group_panel_instances(panels: list[PanelInstance]) -> dict[tuple[str, float], list[PanelInstance]]:
    ordered = sorted(panels, key=lambda item: (item.material.casefold(), item.thickness_mm, item.instance_id))
    return {
        key: list(items)
        for key, items in groupby(ordered, key=lambda item: (item.material, item.thickness_mm))
    }


@dataclass
class _Shelf:
    y_mm: float
    height_mm: float
    next_x_mm: float


def _orientations(panel: PanelInstance, settings: SheetSettings) -> list[tuple[float, float, bool]]:
    orientations = [(panel.length_mm, panel.width_mm, False)]
    if (
        settings.allow_rotation
        and not settings.grain_rotation_restricted
        and panel.length_mm != panel.width_mm
    ):
        orientations.append((panel.width_mm, panel.length_mm, True))
    return orientations


def _fits_sheet(panel: PanelInstance, settings: SheetSettings) -> bool:
    usable_length = settings.length_mm - (2 * settings.margin_mm)
    usable_width = settings.width_mm - (2 * settings.margin_mm)
    return any(length <= usable_length and width <= usable_width for length, width, _ in _orientations(panel, settings))


def _place_on_sheet(
    panel: PanelInstance,
    sheet: SheetLayout,
    shelves: list[_Shelf],
    settings: SheetSettings,
) -> PlacedPanel | None:
    length_limit = settings.length_mm - settings.margin_mm
    width_limit = settings.width_mm - settings.margin_mm
    orientations = _orientations(panel, settings)

    for shelf in shelves:
        for length, width, rotated in orientations:
            if width <= shelf.height_mm and shelf.next_x_mm + length <= length_limit:
                placement = PlacedPanel(
                    panel, sheet.sheet_number, shelf.next_x_mm, shelf.y_mm, length, width, rotated
                )
                shelf.next_x_mm += length + settings.kerf_mm
                sheet.placements.append(placement)
                return placement

    next_y = settings.margin_mm
    if shelves:
        next_y = max(shelf.y_mm + shelf.height_mm for shelf in shelves) + settings.kerf_mm
    for length, width, rotated in orientations:
        if settings.margin_mm + length <= length_limit and next_y + width <= width_limit:
            shelf = _Shelf(next_y, width, settings.margin_mm + length + settings.kerf_mm)
            shelves.append(shelf)
            placement = PlacedPanel(
                panel, sheet.sheet_number, settings.margin_mm, next_y, length, width, rotated
            )
            sheet.placements.append(placement)
            return placement
    return None


def nest_panels(panels: list[PanelInstance], settings: SheetSettings | None = None) -> NestingResult:
    """Pack rectangles with a deterministic decreasing-area first-fit shelf heuristic.

    The result is deliberately not an optimal cutting solution. Every material and
    thickness group is packed independently and no machining output is produced.
    """
    settings = settings or SheetSettings()
    settings.validate()
    groups: list[NestingGroup] = []
    for (material, thickness), group_panels in group_panel_instances(panels).items():
        group = NestingGroup(material, thickness)
        ordered = sorted(
            group_panels,
            key=lambda item: (-item.area_mm2, -max(item.length_mm, item.width_mm), item.instance_id),
        )
        shelf_sets: list[list[_Shelf]] = []
        for panel in ordered:
            if not _fits_sheet(panel, settings):
                group.unplaced.append(
                    UnplacedPanel(
                        panel,
                        f"{panel.length_mm:g} x {panel.width_mm:g} mm exceeds the usable sheet area",
                    )
                )
                continue
            placed = False
            for sheet, shelves in zip(group.sheets, shelf_sets):
                if _place_on_sheet(panel, sheet, shelves, settings) is not None:
                    placed = True
                    break
            if not placed:
                sheet = SheetLayout(len(group.sheets) + 1)
                shelves: list[_Shelf] = []
                group.sheets.append(sheet)
                shelf_sets.append(shelves)
                if _place_on_sheet(panel, sheet, shelves, settings) is None:
                    group.unplaced.append(UnplacedPanel(panel, "No valid shelf position was found"))
                    group.sheets.pop()
                    shelf_sets.pop()
        groups.append(group)
    return NestingResult(settings, groups, list(panels))


def nest_project(project: Project, settings: SheetSettings | None = None) -> NestingResult:
    return nest_panels(project_panel_instances(project), settings)


def rectangles_intersect(first: PlacedPanel, second: PlacedPanel, clearance_mm: float = 0) -> bool:
    """Return True when two placed rectangles overlap, optionally including clearance."""
    return not (
        first.right_mm + clearance_mm <= second.x_mm
        or second.right_mm + clearance_mm <= first.x_mm
        or first.bottom_mm + clearance_mm <= second.y_mm
        or second.bottom_mm + clearance_mm <= first.y_mm
    )
