"""Draft BOM-based costing. No rates, allowances or selling rules are assumed."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

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


@dataclass(frozen=True)
class CabinetCost:
    cabinet_id: str
    lines: tuple[CostLine, ...]
    total: Decimal | None
    currency: str
    missing: tuple[str, ...]

    @property
    def status(self) -> str:
        return "INCOMPLETE" if self.missing else "COMPLETE"


def cost_cabinet(cabinet, master: PriceMaster, *, hardware_assignments=(),
                 charge_quantities: dict[str, str] | None = None,
                 currency: str = "", as_of: str | None = None) -> CabinetCost:
    """Cost BOM rectangles by m2 and BOM hardware by each; no wastage assumed.

    Sheet-priced boards remain incomplete: proportional sheet allocation would
    falsely imply a purchase/wastage rule. Extra charges need explicit units.
    """
    from .bom import generate_bom

    master.validate()
    lines: list[CostLine] = []
    missing: list[str] = []
    result_currency = currency

    def append(component: str, record, quantity: Decimal, calculation: str) -> None:
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
                              record.currency, calculation))

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
                       f"assigned {assignment.quantity} × {assignment.type_id}")
    for name, assigned_quantity in assigned_auto.items():
        if assigned_quantity != automatic.get(name, 0):
            missing.append(f"{name}: assigned {assigned_quantity} differs from BOM {automatic.get(name, 0)}; reconcile before costing")

    for component in components:
        if component.material == "Hardware":
            record = master.approved("Hardware", component.name, as_of=as_of)
            if record is not None and record.unit != "each":
                missing.append(f"{component.name}: rate unit must be each")
            else:
                append(component.name, record, Decimal(component.quantity),
                       f"BOM {component.quantity} each; matching assignments are not added again")
            continue
        record = master.approved("Board", component.material, component.thickness_mm, as_of=as_of)
        if record is not None and record.unit != "m2":
            missing.append(f"{component.name}: {record.unit} board rate needs an approved conversion rule")
            continue
        quantity = (Decimal(str(component.length_mm)) * Decimal(str(component.width_mm))
                    * component.quantity / Decimal("1000000"))
        append(component.name, record, quantity,
               f"{component.length_mm:g} × {component.width_mm:g} mm × {component.quantity} / 1,000,000 m2")

    for record_id, raw_quantity in (charge_quantities or {}).items():
        quantity = nonnegative_decimal(raw_quantity, f"Charge quantity for {record_id}")
        record = next((row for row in master.records if row.record_id == record_id
                       and row.status == "approved" and row.effective_date <= (as_of or date.today().isoformat())
                       and row.category in ("Labour", "Machining", "Finishing")), None)
        if record is not None and record.unit not in ("each", "hour"):
            missing.append(f"{record_id}: charge unit must be each or hour")
        else:
            append(f"Optional charge {record_id}", record, quantity,
                   f"explicit {quantity} {record.unit if record else 'units'}")

    total = sum((line.amount for line in lines), Decimal("0.00")).quantize(MONEY)
    return CabinetCost(cabinet.cabinet_id, tuple(lines), None if missing else total,
                       result_currency, tuple(missing))


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
