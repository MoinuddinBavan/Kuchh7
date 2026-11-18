"""Customer quotation calculations; no catalogue or factory prices are inferred."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .catalogue import get_catalogue_item
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

    def validate(self, project: object) -> None:
        try:
            date.fromisoformat(self.quotation_date)
        except ValueError as error:
            raise ValueError("Quotation date must use YYYY-MM-DD.") from error
        for label, value in (("Discount", self.discount_percent), ("Tax", self.tax_percent)):
            if _decimal(value, label) > 100:
                raise ValueError(f"{label} percentage cannot exceed 100.")
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


@dataclass(frozen=True)
class QuoteSummary:
    lines: tuple[QuoteLine, ...]
    subtotal: Decimal
    discount: Decimal
    taxable_amount: Decimal
    tax: Decimal
    total: Decimal
    unpriced_ids: tuple[str, ...]


def calculate_quotation(project: object) -> QuoteSummary:
    """Tax is applied after percentage discount; prices are user supplied only."""
    settings = project.quotation
    settings.validate(project)
    lines: list[QuoteLine] = []
    unpriced: list[str] = []

    def append(item_id: str, description: str, category: str, billable: bool) -> None:
        price = (_decimal(settings.unit_prices[item_id], f"Unit price for {item_id}")
                 if item_id in settings.unit_prices and billable else None)
        if billable and price is None:
            unpriced.append(item_id)
        amount = price.quantize(MONEY, rounding=ROUND_HALF_UP) if price is not None else None
        lines.append(QuoteLine(item_id, description, category, 1, amount, amount, billable))

    for cabinet in project.cabinets:
        append(cabinet.cabinet_id, get_catalogue_item(cabinet.cabinet_type_id).name, "Furniture", True)
    for product in project.placed_products:
        definition = get_product(product.type_id)
        if definition.library == APPLIANCES:
            append(product.item_id, definition.name, definition.category,
                   product.item_id in settings.billable_product_ids)
    subtotal = sum((line.total or Decimal("0") for line in lines), Decimal("0")).quantize(MONEY)
    discount = (subtotal * _decimal(settings.discount_percent, "Discount") / 100).quantize(MONEY, rounding=ROUND_HALF_UP)
    taxable = subtotal - discount
    tax = (taxable * _decimal(settings.tax_percent, "Tax") / 100).quantize(MONEY, rounding=ROUND_HALF_UP)
    return QuoteSummary(tuple(lines), subtotal, discount, taxable, tax,
                        taxable + tax, tuple(unpriced))
