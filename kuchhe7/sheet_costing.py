"""Explicit project-wide sheet allocation for demonstration costing.

An allocation is made only from a newly calculated, validated, complete layout
and approved per-sheet rates. It does not represent a factory purchase order.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .nesting import (NestingResult, PanelInstance, SheetSettings, SheetSpecification,
                      group_panel_instances, nest_project)
from .nesting_validation import validate_nesting_result

CENT = Decimal("0.01")


@dataclass(frozen=True)
class SheetCostAllocation:
    cabinet_id: str
    sheet_id: str
    rate_record_id: str
    material: str
    finish: str
    thickness_mm: float
    allocated_sheets: int
    amount: Decimal
    currency: str
    source_part_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProjectSheetCost:
    layout: NestingResult
    allocations: tuple[SheetCostAllocation, ...]
    total: Decimal
    currency: str

    def cabinet_allocations(self, cabinet_id: str) -> tuple[SheetCostAllocation, ...]:
        return tuple(line for line in self.allocations if line.cabinet_id == cabinet_id)


def settings_for_pricing_rule(rule) -> SheetSettings:
    """Only explicit policy kerf/margin are used; sheet sizes come from rates."""
    rule.validate()
    return SheetSettings(kerf_mm=float(rule.sheet_kerf_mm),
                         margin_mm=float(rule.sheet_margin_mm),
                         allow_rotation=rule.sheet_allow_rotation)


def approved_sheet_specifications(master, panels: list[PanelInstance], as_of: str,
                                  currency: str) -> tuple[dict[tuple, SheetSpecification], dict[tuple, object]]:
    """Require one exact approved sheet SKU for every material/finish/thickness group."""
    specifications = {}
    rate_records = {}
    for key in group_panel_instances(panels):
        material, thickness = key[:2]
        finish = key[2] if len(key) > 2 else ""
        material_id = key[3] if len(key) > 3 else ""
        candidates = [record for record in master.records
                      if record.category == "Board" and record.unit == "sheet"
                      and record.status == "approved" and record.effective_date <= as_of
                      and record.currency == currency
                      and record.match_key.casefold() == material.casefold()
                      and record.thickness_mm
                      and Decimal(record.thickness_mm) == Decimal(str(thickness))
                      and (not record.finish or record.finish == finish)
                      and (not record.material_id or record.material_id == material_id)]
        if not candidates:
            raise ValueError(f"No approved {currency} per-sheet rate for {material} {thickness:g} mm, finish {finish or 'unspecified'}.")
        record = max(candidates, key=lambda item: (bool(item.finish), item.effective_date, item.record_id))
        grain = record.grain_direction
        rotation = record.sheet_rotation_policy == "allowed"
        spec = SheetSpecification(record.record_id, material, thickness,
                                  float(record.sheet_length_mm), float(record.sheet_width_mm),
                                  finish, material_id, grain, rotation,
                                  record.supplier_reference, record.effective_date, "approved")
        spec.validate()
        specifications[key] = spec
        rate_records[key] = record
    return specifications, rate_records


def allocate_project_sheet_cost(project, settings: SheetSettings, *, as_of: str,
                                currency: str) -> ProjectSheetCost:
    """Fresh live layout; exact cent reconciliation across cabinets per sheet group."""
    from .nesting import project_panel_instances

    project.price_master.validate()
    panels = project_panel_instances(project)
    specs, rates = approved_sheet_specifications(project.price_master, panels, as_of, currency)
    for key, items in group_panel_instances(panels).items():
        if (any(item.grain_direction in ("lengthwise", "widthwise") for item in items)
                and specs[key].grain_direction not in ("lengthwise", "widthwise")):
            raise ValueError(f"Approved sheet grain axis is missing for {specs[key].sheet_id}.")
    layout = nest_project(project, settings, sheet_specs=specs, require_sheet_specs=True)
    validate_nesting_result(layout)
    if layout.unplaced_count:
        raise ValueError(f"Nesting is incomplete: {layout.unplaced_count} manufactured panels unplaced.")
    allocations = []
    total = Decimal("0.00")
    for group in layout.groups:
        key = (group.material, group.thickness_mm, group.finish, group.material_id)
        if key not in rates:
            key = (group.material, group.thickness_mm)
        record = rates[key]
        group_total = (Decimal(len(group.sheets)) * Decimal(record.rate)).quantize(CENT, rounding=ROUND_HALF_UP)
        total += group_total
        by_cabinet: dict[str, list[PanelInstance]] = {}
        for placement in group.placements:
            by_cabinet.setdefault(placement.panel.cabinet_id, []).append(placement.panel)
        group_area = sum((Decimal(str(panel.area_mm2)) for parts in by_cabinet.values()
                          for panel in parts), Decimal(0))
        remainder = group_total
        ids = sorted(by_cabinet)
        for index, cabinet_id in enumerate(ids):
            parts = by_cabinet[cabinet_id]
            area = sum((Decimal(str(panel.area_mm2)) for panel in parts), Decimal(0))
            amount = (remainder if index == len(ids) - 1 else
                      (group_total * area / group_area).quantize(CENT, rounding=ROUND_HALF_UP))
            remainder -= amount
            allocations.append(SheetCostAllocation(
                cabinet_id, group.sheet_specification.sheet_id, record.record_id,
                group.material, group.finish, group.thickness_mm, len(group.sheets),
                amount, currency, tuple(sorted({panel.part_id for panel in parts}))))
    if sum((line.amount for line in allocations), Decimal("0.00")) != total:
        raise ValueError("Shared sheet allocation does not reconcile to purchased sheet cost.")
    return ProjectSheetCost(layout, tuple(allocations), total, currency)
