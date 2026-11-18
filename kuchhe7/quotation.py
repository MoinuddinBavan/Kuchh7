"""Customer quotation calculations; no catalogue or factory prices are inferred."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .catalogue import get_catalogue_item
from .costing import PricingRule, cost_cabinet, selling_price
from .product_libraries import APPLIANCES, get_product

MONEY = Decimal("0.01")


def _decimal(value: str | int | Decimal, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{label} must be a number.") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be a non-negative finite number.")
    return result


@dataclass
class QuotationData:
    customer_name: str = ""
    quotation_number: str = ""
    quotation_date: str = field(default_factory=lambda: date.today().isoformat())
    discount_percent: str = "0"
    tax_percent: str = "0"
    unit_prices: dict[str, str] = field(default_factory=dict)
    billable_product_ids: list[str] = field(default_factory=list)
    currency: str = ""
    pricing_rules: dict[str, PricingRule] = field(default_factory=dict)
    issued_snapshot: dict | None = None

    def __post_init__(self) -> None:
        self.pricing_rules = {key: value if isinstance(value, PricingRule) else PricingRule(**value)
                              for key, value in self.pricing_rules.items()}

    def validate(self, project: object) -> None:
        try:
            date.fromisoformat(self.quotation_date)
        except ValueError as error:
            raise ValueError("Quotation date must use YYYY-MM-DD.") from error
        for label, value in (("Discount", self.discount_percent), ("Tax", self.tax_percent)):
            if _decimal(value, label) > 100:
                raise ValueError(f"{label} percentage cannot exceed 100.")
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha()
                              or self.currency != self.currency.upper()):
            raise ValueError("Quotation currency must be a three-letter uppercase code.")
        for item_id, rule in self.pricing_rules.items():
            if item_id.startswith("P"):
                raise ValueError("Decorative props cannot have quotation pricing rules.")
            rule.validate()
        prop_ids = {item.item_id for item in project.placed_products
                    if get_product(item.type_id).library != APPLIANCES}
        for item_id, price in self.unit_prices.items():
            if item_id in prop_ids or item_id.startswith("P"):
                raise ValueError("Decorative props cannot have quotation prices.")
            _decimal(price, f"Unit price for {item_id}")
        if len(self.billable_product_ids) != len(set(self.billable_product_ids)):
            raise ValueError("Billable product IDs must be unique.")
        if set(self.billable_product_ids) & prop_ids or any(
            item_id.startswith("P") for item_id in self.billable_product_ids
        ):
            raise ValueError("Decorative props cannot be marked billable.")


@dataclass(frozen=True)
class QuoteLine:
    item_id: str
    description: str
    category: str
    quantity: int
    unit_price: Decimal | None
    total: Decimal | None
    billable: bool
    pricing_mode: str = "manual"


@dataclass(frozen=True)
class QuoteSummary:
    lines: tuple[QuoteLine, ...]
    subtotal: Decimal
    discount: Decimal
    taxable_amount: Decimal
    tax: Decimal
    total: Decimal
    unpriced_ids: tuple[str, ...]
    incomplete_reasons: tuple[str, ...] = ()


def calculate_quotation(project: object) -> QuoteSummary:
    """Calculate a live draft; legacy manual prices are never overwritten."""
    settings = project.quotation
    settings.validate(project)
    lines: list[QuoteLine] = []
    unpriced: list[str] = []
    incomplete: list[str] = []

    def append(item_id: str, description: str, category: str, billable: bool,
               cabinet=None, product=None) -> None:
        mode = "manual"
        price = None
        if billable:
            rule = settings.pricing_rules.get(item_id)
            if cabinet is not None and rule is not None and rule.mode != "manual":
                mode = rule.mode
                cost = cost_cabinet(cabinet, project.price_master,
                                    hardware_assignments=project.hardware_assignments,
                                    charge_quantities=rule.charge_quantities,
                                    currency=settings.currency,
                                    as_of=settings.quotation_date)
                price, reason = selling_price(cost, rule, currency=settings.currency)
                if reason:
                    incomplete.append(f"{item_id}: {reason}")
                incomplete.extend(f"{item_id}: {entry}" for entry in cost.missing if mode == "calculated")
            elif item_id in settings.unit_prices:
                price = _decimal(settings.unit_prices[item_id], f"Unit price for {item_id}")
            elif product is not None:
                record = project.price_master.approved("Appliance", product.type_id,
                                                       as_of=settings.quotation_date)
                if record is not None and record.unit == "each" and record.currency == settings.currency:
                    price = _decimal(record.rate, f"Appliance rate {record.record_id}")
                    mode = "master"
        if billable and price is None:
            unpriced.append(item_id)
        amount = price.quantize(MONEY, rounding=ROUND_HALF_UP) if price is not None else None
        lines.append(QuoteLine(item_id, description, category, 1, amount, amount, billable, mode))

    for cabinet in project.cabinets:
        append(cabinet.cabinet_id, get_catalogue_item(cabinet.cabinet_type_id).name,
               "Furniture", True, cabinet=cabinet)
    for product in project.placed_products:
        definition = get_product(product.type_id)
        if definition.library == APPLIANCES:
            append(product.item_id, definition.name, definition.category,
                   product.item_id in settings.billable_product_ids, product=product)
    subtotal = sum((line.total or Decimal("0") for line in lines), Decimal("0")).quantize(MONEY)
    discount = (subtotal * _decimal(settings.discount_percent, "Discount") / 100).quantize(MONEY, rounding=ROUND_HALF_UP)
    taxable = subtotal - discount
    tax = (taxable * _decimal(settings.tax_percent, "Tax") / 100).quantize(MONEY, rounding=ROUND_HALF_UP)
    return QuoteSummary(tuple(lines), subtotal, discount, taxable, tax,
                        taxable + tax, tuple(unpriced), tuple(incomplete))


def issue_quotation_snapshot(project: object) -> dict:
    """Freeze reviewed draft values; later project edits do not mutate this record."""
    summary = calculate_quotation(project)
    if summary.unpriced_ids or summary.incomplete_reasons:
        raise ValueError("Complete all billable prices and pricing rules before issuing a snapshot.")
    if not project.quotation.customer_name.strip() or not project.quotation.quotation_number.strip():
        raise ValueError("Customer and quotation number are required for an issued snapshot.")
    if not project.quotation.currency:
        raise ValueError("Quotation currency is required for an issued snapshot.")
    snapshot = {
        "customer_name": project.quotation.customer_name,
        "quotation_number": project.quotation.quotation_number,
        "quotation_date": project.quotation.quotation_date,
        "currency": project.quotation.currency,
        "lines": [{"item_id": line.item_id, "description": line.description,
                   "quantity": line.quantity, "unit_price": str(line.unit_price),
                   "total": str(line.total), "pricing_mode": line.pricing_mode}
                  for line in summary.lines if line.billable],
        "subtotal": str(summary.subtotal), "discount": str(summary.discount),
        "tax": str(summary.tax), "total": str(summary.total),
    }
    project.quotation.issued_snapshot = snapshot
    return snapshot
