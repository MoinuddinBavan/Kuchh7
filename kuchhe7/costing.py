"""Draft BOM-based costing. No rates, allowances or selling rules are assumed."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from .price_master import PriceMaster, nonnegative_decimal
from .product_libraries import get_product

MONEY = Decimal("0.01")
AUTOMATIC_HARDWARE = {"hinge_soft_close": "Concealed hinge", "runner_pair": "Drawer runner pair"}
PRICING_MODES = ("manual", "fixed", "calculated")


@dataclass
class PricingRule:
    mode: str = "manual"
    approved: bool = False
    fixed_price: str = ""
    markup_percent: str = ""
    gross_margin_percent: str = ""
    charge_quantities: dict[str, str] = field(default_factory=dict)
    cost_basis: str = "finished_area"
    material_wastage_percent: str = ""
    edge_wastage_percent: str = ""
    overhead_percent: str = ""
    sheet_yield_percent: str = ""
    sheet_kerf_mm: str = ""
    sheet_margin_mm: str = ""
    sheet_allow_rotation: bool = True

    def validate(self) -> None:
        if self.mode not in PRICING_MODES:
            raise ValueError("Unsupported cabinet pricing mode.")
        if self.fixed_price:
            nonnegative_decimal(self.fixed_price, "Fixed selling price")
        if self.markup_percent and self.gross_margin_percent:
            raise ValueError("Choose markup or gross margin, not both.")
        if self.markup_percent:
            nonnegative_decimal(self.markup_percent, "Markup percentage")
        if self.gross_margin_percent and nonnegative_decimal(self.gross_margin_percent, "Gross margin percentage") >= 100:
            raise ValueError("Gross margin percentage must be below 100.")
        for record_id, quantity in self.charge_quantities.items():
            if not record_id.strip():
                raise ValueError("Charge record ID is required.")
            nonnegative_decimal(quantity, f"Charge quantity for {record_id}")
        if self.cost_basis not in ("finished_area", "cut_area", "sheet_yield", "nesting_sheets", "project_nesting"):
            raise ValueError("Unsupported material cost basis.")
        for label, value in (("Material wastage", self.material_wastage_percent),
                             ("Edge wastage", self.edge_wastage_percent),
                             ("Overhead", self.overhead_percent)):
            if value and nonnegative_decimal(value, label) > 100:
                raise ValueError(f"{label} percentage must not exceed 100.")
        if self.cost_basis == "sheet_yield" and (not self.sheet_yield_percent or
                not 0 < nonnegative_decimal(self.sheet_yield_percent, "Sheet yield") <= 100):
            raise ValueError("Sheet estimate needs an explicit yield between 0 and 100%.")
        if self.cost_basis in ("sheet_yield", "nesting_sheets", "project_nesting") and self.material_wastage_percent:
            raise ValueError("Sheet costing already includes layout allowance; do not add material wastage twice.")
        if self.cost_basis in ("nesting_sheets", "project_nesting"):
            if not self.sheet_kerf_mm or not self.sheet_margin_mm:
                raise ValueError("Nesting-sheet costing requires explicit kerf and edge margin.")
            nonnegative_decimal(self.sheet_kerf_mm, "Nesting kerf")
            nonnegative_decimal(self.sheet_margin_mm, "Nesting margin")
        if not isinstance(self.sheet_allow_rotation, bool):
            raise ValueError("Sheet rotation setting must be a boolean.")


@dataclass(frozen=True)
class CostLine:
    component: str
    source_id: str
    unit: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal
    currency: str
    calculation: str
    match_key: str = ""
    specification: str = ""
    source_part_ids: tuple[str, ...] = ()
    cost_category: str = ""
    supplier_reference: str = ""


@dataclass(frozen=True)
class CabinetCost:
    cabinet_id: str
    lines: tuple[CostLine, ...]
    total: Decimal | None
    currency: str
    missing: tuple[str, ...]
    profile_id: str = "LEGACY-DEMO"
    profile_revision: str = "legacy"
    price_master_revision: str = ""
    material_basis: str = "finished_area"

    @property
    def status(self) -> str:
        return "INCOMPLETE" if self.missing else "COMPLETE"


def cost_cabinet(cabinet, master: PriceMaster, *, hardware_assignments=(),
                 charge_quantities: dict[str, str] | None = None,
                 currency: str = "", as_of: str | None = None,
                 policy: PricingRule | None = None,
                 project_sheet_cost=None) -> CabinetCost:
    """Cost the authoritative BOM using an explicit selling-rule material basis.

    Default finished-area costing preserves the older demonstration workflow.
    Sheet options are cabinet-isolated estimates, not shared project purchases.
    """
    from .bom import generate_bom
    from .nesting import SheetSettings, expand_panel_instances, nest_panels
    from .pricing_refresh import master_revision

    master.validate()
    policy = policy or PricingRule()
    policy.validate()
    basis = policy.cost_basis
    lines: list[CostLine] = []
    missing: list[str] = []
    result_currency = currency

    def append(component: str, record, quantity: Decimal, calculation: str,
               part_ids: tuple[str, ...] = ()) -> None:
        nonlocal result_currency
        if record is None:
            missing.append(f"{component}: approved rate missing")
            return
        if result_currency and record.currency != result_currency:
            missing.append(f"{component}: currency {record.currency} differs from {result_currency}")
            return
        result_currency = record.currency
        rate = nonnegative_decimal(record.rate, f"Rate {record.record_id}")
        amount = (quantity * rate).quantize(MONEY, rounding=ROUND_HALF_UP)
        lines.append(CostLine(component, record.record_id, record.unit, quantity, rate, amount,
                              record.currency, calculation, record.match_key, record.specification,
                              part_ids, record.category, record.supplier_reference))

    def allowance(label: str, record, quantity: Decimal, percent: str,
                  part_ids: tuple[str, ...]) -> None:
        if record is not None and percent:
            rate = nonnegative_decimal(percent, label)
            if rate:
                append(label, record, quantity * rate / 100,
                       f"explicit {rate}% of {quantity} {record.unit}", part_ids)

    components = generate_bom(cabinet)
    automatic = {row.name: row.quantity for row in components if row.material == "Hardware"}
    assigned_auto: dict[str, int] = {}
    for assignment in hardware_assignments:
        if assignment.cabinet_id != cabinet.cabinet_id:
            continue
        if assignment.type_id in AUTOMATIC_HARDWARE:
            name = AUTOMATIC_HARDWARE[assignment.type_id]
            assigned_auto[name] = assigned_auto.get(name, 0) + assignment.quantity
        else:
            definition = get_product(assignment.type_id)
            record = (master.approved("Hardware", assignment.type_id, as_of=as_of)
                      or master.approved("Accessory", assignment.type_id, as_of=as_of))
            if record is not None and record.unit != "each":
                missing.append(f"{definition.name}: rate unit must be each")
            else:
                append(definition.name, record, Decimal(assignment.quantity),
                       f"assigned {assignment.quantity} x {assignment.type_id}",
                       (f"{cabinet.cabinet_id}:ASSIGN:{assignment.assignment_id}",))
    for name, assigned_quantity in assigned_auto.items():
        if assigned_quantity != automatic.get(name, 0):
            missing.append(f"{name}: assigned {assigned_quantity} differs from BOM {automatic.get(name, 0)}; reconcile before costing")

    panel_groups: dict[tuple[str, float], list[tuple[object, str]]] = {}
    for ordinal, component in enumerate(components, 1):
        part_id = f"{cabinet.cabinet_id}-P{ordinal:02d}"
        if component.material == "Hardware":
            record = master.approved("Hardware", component.name, as_of=as_of)
            if record is not None and record.unit != "each":
                missing.append(f"{component.name}: rate unit must be each")
            else:
                append(component.name, record, Decimal(component.quantity),
                       f"BOM {component.quantity} each; matching assignments are not added again",
                       (part_id,))
            continue
        panel_groups.setdefault((component.material, component.thickness_mm), []).append((component, part_id))
        if basis in ("finished_area", "cut_area"):
            length = component.length_mm if basis == "finished_area" else (
                component.cut_length_mm if component.cut_length_mm is not None else component.length_mm)
            width = component.width_mm if basis == "finished_area" else (
                component.cut_width_mm if component.cut_width_mm is not None else component.width_mm)
            record = master.approved("Board", component.material, component.thickness_mm,
                                     as_of=as_of, unit="m2")
            if record is None:
                other = master.approved("Board", component.material, component.thickness_mm, as_of=as_of)
                if other is not None:
                    missing.append(f"{component.name}: {other.unit} board rate needs an approved conversion rule")
            quantity = (Decimal(str(length)) * Decimal(str(width)) * component.quantity
                        / Decimal("1000000"))
            if record is not None or master.approved("Board", component.material, component.thickness_mm,
                                                      as_of=as_of) is None:
                append(component.name, record, quantity,
                       f"{basis}: {length:g} x {width:g} mm x {component.quantity} / 1,000,000 m2",
                       (part_id,))
            allowance(f"Material wastage: {component.name}", record, quantity,
                      policy.material_wastage_percent, (part_id,))
        for band in component.edge_banding:
            record = master.approved("Edge banding", band.material, band.thickness_mm,
                                     as_of=as_of, band_width_mm=band.width_mm, unit="m")
            edge_length = component.length_mm if band.edge in ("front", "back") else component.width_mm
            quantity = Decimal(str(edge_length)) * component.quantity / 1000
            if record is None:
                missing.append(f"{part_id} {band.edge}: approved {band.material} {band.thickness_mm:g} x {band.width_mm:g} mm edge rate missing")
            else:
                append(f"{component.name} {band.edge} edge", record, quantity,
                       f"BOM {edge_length:g} mm x {component.quantity} / 1,000 m", (part_id,))
                allowance(f"Edge wastage: {component.name} {band.edge}", record,
                          quantity, policy.edge_wastage_percent, (part_id,))

    if basis in ("sheet_yield", "nesting_sheets"):
        for (material, thickness), entries in panel_groups.items():
            record = master.approved("Board", material, thickness, as_of=as_of, unit="sheet")
            part_ids = tuple(part_id for _, part_id in entries)
            if record is None:
                missing.append(f"{material} {thickness:g} mm: approved per-sheet rate missing")
                continue
            sheet_area = Decimal(record.sheet_length_mm) * Decimal(record.sheet_width_mm)
            panels = [component for component, _ in entries]
            if basis == "sheet_yield":
                cut_area = sum((Decimal(str(c.cut_length_mm if c.cut_length_mm is not None else c.length_mm))
                                * Decimal(str(c.cut_width_mm if c.cut_width_mm is not None else c.width_mm))
                                * c.quantity for c in panels), Decimal(0))
                effective_area = sheet_area * nonnegative_decimal(policy.sheet_yield_percent, "Sheet yield") / 100
                sheets = (cut_area / effective_area).to_integral_value(rounding=ROUND_CEILING)
                detail = f"cabinet sheet estimate; cut area {cut_area} mm2 / explicit {policy.sheet_yield_percent}% yield"
            else:
                settings = SheetSettings(
                    length_mm=float(record.sheet_length_mm), width_mm=float(record.sheet_width_mm),
                    kerf_mm=float(policy.sheet_kerf_mm), margin_mm=float(policy.sheet_margin_mm),
                    allow_rotation=policy.sheet_allow_rotation)
                layout = nest_panels(expand_panel_instances(panels), settings)
                if layout.unplaced_count:
                    missing.append(f"{material} {thickness:g} mm: {layout.unplaced_count} panels unplaced in cabinet-isolated nesting")
                    continue
                sheets = Decimal(layout.sheet_count)
                detail = (f"cabinet-isolated demonstration nesting: {layout.sheet_count} sheets; "
                          f"kerf {policy.sheet_kerf_mm} mm, margin {policy.sheet_margin_mm} mm")
            append(f"Board sheets: {material} {thickness:g} mm", record, sheets, detail, part_ids)

    if basis == "project_nesting":
        if project_sheet_cost is None:
            missing.append("Current validated project-wide sheet allocation is required.")
        else:
            current_panels = expand_panel_instances(components)
            from_layout = [item for item in project_sheet_cost.layout.eligible_panels
                           if item.cabinet_id == cabinet.cabinet_id]
            def signature(panel):
                return (panel.instance_id, panel.length_mm, panel.width_mm,
                        panel.material, panel.thickness_mm, panel.grain_direction,
                        panel.profile_id or "LEGACY-DEMO", panel.profile_revision or "legacy")
            if sorted(map(signature, current_panels)) != sorted(map(signature, from_layout)):
                missing.append("Project-wide sheet allocation is stale for this cabinet.")
            elif project_sheet_cost.currency != (currency or project_sheet_cost.currency):
                missing.append("Project-wide sheet allocation currency differs from quotation.")
            else:
                for allocation in project_sheet_cost.cabinet_allocations(cabinet.cabinet_id):
                    lines.append(CostLine(
                        f"Shared sheet allocation: {allocation.material} {allocation.thickness_mm:g} mm",
                        allocation.rate_record_id, "allocation", Decimal(1),
                        allocation.amount, allocation.amount, allocation.currency,
                        f"{allocation.allocated_sheets} purchased sheet(s) for group {allocation.sheet_id}; "
                        "group cost apportioned by cut-panel area with exact cent reconciliation",
                        allocation.material, allocation.finish, allocation.source_part_ids,
                        "Board", allocation.sheet_id))

    for record_id, raw_quantity in (charge_quantities or {}).items():
        quantity = nonnegative_decimal(raw_quantity, f"Charge quantity for {record_id}")
        record = next((row for row in master.records if row.record_id == record_id
                       and row.status == "approved" and row.effective_date <= (as_of or date.today().isoformat())
                       and row.category in ("Labour", "Machining", "Finishing", "Installation",
                                            "Transport", "Handling", "Packaging", "Overhead")), None)
        if record is not None and record.unit not in ("each", "hour"):
            missing.append(f"{record_id}: charge unit must be each or hour")
        else:
            append(f"Optional charge {record_id}", record, quantity,
                   f"explicit {quantity} {record.unit if record else 'units'}")

    if policy.overhead_percent:
        if any(row.record_id in (charge_quantities or {}) and row.category == "Overhead"
               for row in master.records):
            missing.append("Overhead is configured both as a percentage and an explicit charge.")
        else:
            percentage = nonnegative_decimal(policy.overhead_percent, "Overhead")
            base = sum((line.amount for line in lines), Decimal("0.00"))
            amount = (base * percentage / 100).quantize(MONEY, rounding=ROUND_HALF_UP)
            lines.append(CostLine("Configured overhead", "PRICING-RULE", "%", base, percentage,
                                  amount, result_currency, f"explicit {percentage}% of cost subtotal",
                                  cost_category="Overhead"))
    total = sum((line.amount for line in lines), Decimal("0.00")).quantize(MONEY)
    snapshot = cabinet.construction_profile or {}
    return CabinetCost(cabinet.cabinet_id, tuple(lines), None if missing else total,
                       result_currency, tuple(missing), snapshot.get("profile_id", "LEGACY-DEMO"),
                       snapshot.get("revision", "legacy"), master_revision(master), basis)


def selling_price(cost: CabinetCost, rule: PricingRule, *, currency: str = "") -> tuple[Decimal | None, str]:
    """Return a draft selling price or an explicit reason it is incomplete."""
    rule.validate()
    if rule.mode == "manual":
        return None, "Manual price is entered in the quotation."
    if not rule.approved:
        return None, "Pricing rule is not approved."
    if rule.mode == "fixed":
        if not rule.fixed_price or not currency:
            return None, "Approved fixed price and quotation currency are required."
        return nonnegative_decimal(rule.fixed_price, "Fixed selling price").quantize(MONEY, rounding=ROUND_HALF_UP), ""
    if cost.status != "COMPLETE" or cost.total is None:
        return None, "Cabinet cost is incomplete."
    if not currency or cost.currency != currency:
        return None, "Quotation and approved cost currencies must match."
    if rule.markup_percent:
        percentage = nonnegative_decimal(rule.markup_percent, "Markup percentage")
        amount = cost.total * (Decimal("1") + percentage / 100)
    elif rule.gross_margin_percent:
        percentage = nonnegative_decimal(rule.gross_margin_percent, "Gross margin percentage")
        amount = cost.total / (Decimal("1") - percentage / 100)
    else:
        return None, "Approved markup or gross margin rule is required."
    return amount.quantize(MONEY, rounding=ROUND_HALF_UP), ""
