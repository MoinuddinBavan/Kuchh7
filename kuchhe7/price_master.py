"""Local, explicitly approved demo rates. No prices are supplied by the application."""

from __future__ import annotations

import csv
import json
from zipfile import BadZipFile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .catalogue import get_catalogue_item, normalized_finish
from .product_libraries import APPLIANCES, HARDWARE, get_product

CATEGORIES = ("Board", "Surface finish", "Laminate", "Edge banding", "Hardware", "Accessory",
              "Appliance", "Labour", "Machining", "Finishing", "Installation",
              "Transport", "Handling", "Packaging", "Overhead")
UNITS = ("m2", "m", "each", "hour", "sheet")
STATUSES = ("draft", "approved")
PRICE_COLUMNS = ("record_id", "category", "match_key", "description", "unit", "rate", "currency",
                 "effective_date", "status", "thickness_mm", "sheet_length_mm", "sheet_width_mm",
                 "specification", "purchase_unit", "selling_unit", "band_width_mm",
                 "supplier_reference", "finish", "material_id", "grain_direction",
                 "sheet_rotation_policy")


@dataclass
class CataloguePriceRule:
    """Approved selling rule for a catalogue type, optionally a finish and exact size."""

    rule_id: str
    type_id: str
    mode: str
    currency: str
    effective_date: str
    status: str = "draft"
    material: str = ""
    width_mm: int = 0
    height_mm: int = 0
    depth_mm: int = 0
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
        if not self.rule_id.strip():
            raise ValueError("Catalogue pricing rule ID is required.")
        item = get_catalogue_item(self.type_id)
        if self.material and normalized_finish(self.material) not in item.supported_finishes:
            raise ValueError(f"Unsupported finish for pricing rule {self.rule_id}.")
        if self.mode not in ("fixed", "calculated") or self.status not in STATUSES:
            raise ValueError(f"Invalid mode or approval status for pricing rule {self.rule_id}.")
        if len(self.currency) != 3 or not self.currency.isalpha() or self.currency != self.currency.upper():
            raise ValueError(f"Pricing rule {self.rule_id} needs an uppercase currency code.")
        try:
            date.fromisoformat(self.effective_date)
        except ValueError as error:
            raise ValueError(f"Pricing rule {self.rule_id} needs an effective date.") from error
        if self.mode == "fixed":
            if any(not isinstance(value, int) or value <= 0 for value in
                   (self.width_mm, self.height_mm, self.depth_mm)):
                raise ValueError("Fixed catalogue price requires exact positive width, height and depth.")
            nonnegative_decimal(self.fixed_price, "Fixed catalogue price")
            if not self.fixed_price:
                raise ValueError("Fixed catalogue price is required.")
        else:
            if any((self.width_mm, self.height_mm, self.depth_mm)):
                raise ValueError("Calculated catalogue rules apply to a type/finish, not a fixed size.")
            if bool(self.markup_percent) == bool(self.gross_margin_percent):
                raise ValueError("Calculated catalogue rule needs either markup or gross margin.")
            if self.markup_percent:
                nonnegative_decimal(self.markup_percent, "Markup")
            if self.gross_margin_percent and nonnegative_decimal(self.gross_margin_percent, "Gross margin") >= 100:
                raise ValueError("Gross margin must be below 100%.")
        for key, value in self.charge_quantities.items():
            if not key.strip():
                raise ValueError("Charge record ID is required.")
            nonnegative_decimal(value, f"Charge quantity for {key}")
        if self.cost_basis not in ("finished_area", "cut_area", "sheet_yield", "nesting_sheets", "project_nesting"):
            raise ValueError("Unsupported cabinet material cost basis.")
        for label, value in (("Material wastage", self.material_wastage_percent),
                             ("Edge wastage", self.edge_wastage_percent),
                             ("Overhead", self.overhead_percent)):
            if value and nonnegative_decimal(value, label) > 100:
                raise ValueError(f"{label} percentage must not exceed 100.")
        if self.cost_basis == "sheet_yield":
            if not self.sheet_yield_percent or not 0 < nonnegative_decimal(self.sheet_yield_percent, "Sheet yield") <= 100:
                raise ValueError("Sheet estimate needs an explicit yield between 0 and 100%.")
        if self.cost_basis in ("sheet_yield", "nesting_sheets", "project_nesting") and self.material_wastage_percent:
            raise ValueError("Sheet costing already includes layout allowance; do not add material wastage twice.")
        if self.cost_basis in ("nesting_sheets", "project_nesting"):
            if not self.sheet_kerf_mm or not self.sheet_margin_mm:
                raise ValueError("Nesting-sheet costing needs explicit kerf and margin settings.")
            nonnegative_decimal(self.sheet_kerf_mm, "Nesting kerf")
            nonnegative_decimal(self.sheet_margin_mm, "Nesting margin")
        if not isinstance(self.sheet_allow_rotation, bool):
            raise ValueError("Sheet rotation setting must be a boolean.")


def nonnegative_decimal(value: object, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{label} must be a number.") from error
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label} must be a non-negative finite number.")
    return number


@dataclass
class PriceRecord:
    record_id: str
    category: str
    match_key: str
    description: str
    unit: str
    rate: str = ""
    currency: str = ""
    effective_date: str = ""
    status: str = "draft"
    thickness_mm: str = ""
    sheet_length_mm: str = ""
    sheet_width_mm: str = ""
    specification: str = ""
    purchase_unit: str = ""
    selling_unit: str = ""
    band_width_mm: str = ""
    supplier_reference: str = ""
    finish: str = ""
    material_id: str = ""
    grain_direction: str = "undefined"
    sheet_rotation_policy: str = "allowed"

    def validate(self) -> None:
        if not self.record_id.strip() or not self.match_key.strip() or not self.description.strip():
            raise ValueError("Price record ID, match key and description are required.")
        if self.category not in CATEGORIES or self.unit not in UNITS or self.status not in STATUSES:
            raise ValueError(f"Unsupported price category, unit or status for {self.record_id}.")
        if ((self.purchase_unit and self.purchase_unit not in UNITS)
                or (self.selling_unit and self.selling_unit not in UNITS)):
            raise ValueError(f"Purchase and selling units for {self.record_id} must be supported units.")
        if self.rate != "":
            nonnegative_decimal(self.rate, f"Rate for {self.record_id}")
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha() or self.currency != self.currency.upper()):
            raise ValueError(f"Currency for {self.record_id} must be a three-letter uppercase code.")
        if self.effective_date:
            try:
                date.fromisoformat(self.effective_date)
            except ValueError as error:
                raise ValueError(f"Effective date for {self.record_id} must use YYYY-MM-DD.") from error
        for name in ("thickness_mm", "sheet_length_mm", "sheet_width_mm", "band_width_mm"):
            value = getattr(self, name)
            if value and nonnegative_decimal(value, f"{name} for {self.record_id}") <= 0:
                raise ValueError(f"{name} for {self.record_id} must be positive.")
        if self.status == "approved" and (not self.rate or not self.currency or not self.effective_date):
            raise ValueError(f"Approved rate {self.record_id} requires rate, currency and effective date.")
        if self.category == "Board" and not self.thickness_mm:
            raise ValueError(f"Board record {self.record_id} requires thickness in mm.")
        if self.category == "Board" and self.status == "approved" and not self.specification.strip():
            raise ValueError(f"Approved board record {self.record_id} requires a material specification.")
        if self.unit == "sheet" and (not self.sheet_length_mm or not self.sheet_width_mm):
            raise ValueError(f"Sheet record {self.record_id} requires sheet dimensions.")
        if self.grain_direction not in ("undefined", "none", "lengthwise", "widthwise"):
            raise ValueError(f"Invalid sheet grain direction for {self.record_id}.")
        if self.sheet_rotation_policy not in ("allowed", "forbidden"):
            raise ValueError(f"Invalid sheet rotation policy for {self.record_id}.")


@dataclass
class PriceMaster:
    records: list[PriceRecord] = field(default_factory=list)
    catalogue_rules: list[CataloguePriceRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.records = [row if isinstance(row, PriceRecord) else PriceRecord(**row) for row in self.records]
        self.catalogue_rules = [row if isinstance(row, CataloguePriceRule) else CataloguePriceRule(**row)
                                for row in self.catalogue_rules]

    def validate(self) -> None:
        ids: set[str] = set()
        approved_keys: set[tuple[str, str, str, str]] = set()
        for record in self.records:
            record.validate()
            if record.record_id in ids:
                raise ValueError(f"Duplicate price record ID: {record.record_id}")
            ids.add(record.record_id)
            if record.status == "approved":
                sheet_identity = (record.finish, record.material_id) if record.unit == "sheet" else ("", "")
                key = (record.category, record.match_key.casefold(), record.thickness_mm,
                       record.band_width_mm, record.unit, record.effective_date, *sheet_identity)
                if key in approved_keys:
                    raise ValueError(f"Multiple approved rates match {record.category} {record.match_key} {record.thickness_mm}.")
                approved_keys.add(key)
        rule_ids: set[str] = set()
        approved_rules: set[tuple] = set()
        for rule in self.catalogue_rules:
            rule.validate()
            if rule.rule_id in rule_ids:
                raise ValueError(f"Duplicate catalogue pricing rule ID: {rule.rule_id}")
            rule_ids.add(rule.rule_id)
            if rule.status == "approved":
                key = (rule.type_id, normalized_finish(rule.material), rule.mode, rule.currency,
                       rule.effective_date, rule.width_mm, rule.height_mm, rule.depth_mm)
                if key in approved_rules:
                    raise ValueError(f"Duplicate approved catalogue pricing rule for {rule.type_id}.")
                approved_rules.add(key)

    def cabinet_rule(self, cabinet, *, currency: str, as_of: str) -> tuple[CataloguePriceRule | None, str]:
        """Resolve the most specific approved rule; never reuse a fixed price for a custom size."""
        candidates = [row for row in self.catalogue_rules
                      if row.status == "approved" and row.type_id == cabinet.cabinet_type_id
                      and row.effective_date <= as_of and row.currency == currency
                      and (not row.material or normalized_finish(row.material) == normalized_finish(cabinet.material))]
        exact = [row for row in candidates if row.mode == "fixed" and
                 (row.width_mm, row.height_mm, row.depth_mm) ==
                 (cabinet.width, cabinet.height, cabinet.depth)]
        calculated = [row for row in candidates if row.mode == "calculated"]
        eligible = exact or calculated
        if eligible:
            return max(eligible, key=lambda row: (bool(row.material), row.effective_date)), ""
        if any(row.mode == "fixed" for row in candidates):
            return None, f"No approved fixed price for {cabinet.width} x {cabinet.height} x {cabinet.depth} mm; custom size needs a calculated rule or approved variant."
        return None, "No approved catalogue pricing rule for this product, finish, date and currency."

    def approved(self, category: str, match_key: str, thickness_mm: float | None = None,
                 as_of: str | None = None, *, band_width_mm: float | None = None,
                 unit: str | None = None) -> PriceRecord | None:
        thickness = "" if thickness_mm is None else str(Decimal(str(thickness_mm)).normalize())
        band_width = "" if band_width_mm is None else str(Decimal(str(band_width_mm)).normalize())
        cutoff = as_of or date.today().isoformat()
        for record in sorted(self.records, key=lambda item: item.effective_date, reverse=True):
            if (record.status == "approved" and record.category == category
                    and record.effective_date <= cutoff
                    and record.match_key.casefold() == match_key.casefold()
                    and (unit is None or record.unit == unit)
                    and (thickness_mm is None or (record.thickness_mm and str(Decimal(record.thickness_mm).normalize()) == thickness))
                    and (band_width_mm is None or (record.band_width_mm and str(Decimal(record.band_width_mm).normalize()) == band_width))):
                return record
        return None

    def to_dict(self) -> dict:
        self.validate()
        return {"schema_version": 2, "records": [asdict(row) for row in self.records],
                "catalogue_rules": [asdict(row) for row in self.catalogue_rules]}

    @classmethod
    def from_dict(cls, data: dict) -> "PriceMaster":
        if (not isinstance(data, dict) or not isinstance(data.get("records", []), list)
                or not isinstance(data.get("catalogue_rules", []), list)):
            raise ValueError("Price master must contain a records list.")
        try:
            result = cls(data.get("records", []), data.get("catalogue_rules", []))
        except TypeError as error:
            raise ValueError("Price master contains an invalid record.") from error
        result.validate()
        return result


def save_price_master(master: PriceMaster, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(master.to_dict(), indent=2), encoding="utf-8")
    return destination


def load_price_master(path: str | Path) -> PriceMaster:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".json":
        master = PriceMaster.from_dict(json.loads(source.read_text(encoding="utf-8")))
        _validate_import_currency(master)
        _validate_import_product_ids(master)
        _validate_import_rate_units(master)
        return master
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            rows = list(reader)
    elif suffix == ".xlsx":
        try:
            workbook = load_workbook(source, read_only=True, data_only=True)
            sheet = workbook.active
        except (BadZipFile, InvalidFileException) as error:
            raise ValueError("Price list is not a valid XLSX workbook.") from error
        values = sheet.iter_rows(values_only=True)
        try:
            headers = [str(value or "").strip() for value in next(values)]
        except StopIteration as error:
            raise ValueError("Price list is empty.") from error
        rows = [dict(zip(headers, row)) for row in values if any(value is not None for value in row)]
        workbook.close()
    else:
        raise ValueError("Price master must be JSON, CSV or XLSX.")
    required = {"record_id", "category", "match_key", "description", "unit", "rate", "currency", "effective_date", "status"}
    if not required.issubset(headers):
        raise ValueError("Price list is missing required columns: " + ", ".join(sorted(required - set(headers))))
    if len(headers) != len(set(headers)):
        raise ValueError("Price list has duplicate column headings.")
    normalized = [{key: ("" if row.get(key) is None else
                         row[key].date().isoformat() if key == "effective_date" and isinstance(row[key], datetime) else
                         row[key].isoformat() if key == "effective_date" and isinstance(row[key], date) else
                         str(row[key]).strip()) for key in PRICE_COLUMNS} for row in rows]
    for row in normalized:
        row["grain_direction"] = row["grain_direction"] or "undefined"
        row["sheet_rotation_policy"] = row["sheet_rotation_policy"] or "allowed"
    master = PriceMaster.from_dict({"records": normalized})
    _validate_import_currency(master)
    _validate_import_product_ids(master)
    _validate_import_rate_units(master)
    return master


def _validate_import_currency(master: PriceMaster) -> None:
    currencies = {row.currency for row in master.records if row.status == "approved"}
    currencies.update(row.currency for row in master.catalogue_rules if row.status == "approved")
    if len(currencies) > 1:
        raise ValueError("Imported approved rates and rules contain mixed currencies; import one currency at a time.")


def _validate_import_product_ids(master: PriceMaster) -> None:
    """Import guard only; legacy project records may contain historical custom IDs."""
    for record in master.records:
        if record.category not in ("Appliance", "Accessory", "Hardware"):
            continue
        if record.category == "Hardware" and record.match_key in ("Concealed hinge", "Drawer runner pair"):
            continue
        try:
            product = get_product(record.match_key)
        except ValueError as error:
            raise ValueError(f"Imported price record {record.record_id} has an unknown product ID {record.match_key}.") from error
        expected = APPLIANCES if record.category == "Appliance" else HARDWARE
        if product.library != expected:
            raise ValueError(f"Imported price record {record.record_id} has a product ID from the wrong library.")


def _validate_import_rate_units(master: PriceMaster) -> None:
    """Reject an unsupported rate basis; never infer purchase-to-cost conversion."""
    allowed = {"Board": {"m2", "sheet"}, "Hardware": {"each"},
               "Accessory": {"each"}, "Appliance": {"each"},
               "Labour": {"each", "hour"}, "Machining": {"each", "hour"},
               "Finishing": {"each", "hour"}, "Surface finish": {"m2"},
               "Laminate": {"m2", "sheet"}, "Edge banding": {"m"},
               "Installation": {"each", "hour"}, "Transport": {"each", "hour"},
               "Handling": {"each", "hour"}, "Packaging": {"each", "hour"},
               "Overhead": {"each", "hour"}}
    for record in master.records:
        if record.unit not in allowed[record.category]:
            raise ValueError(f"Imported price record {record.record_id} uses {record.unit}, "
                             f"which is not a supported rate unit for {record.category}.")


def validate_company_price_setup(master: PriceMaster) -> None:
    """Apply the same import guards before a company setup is saved."""
    master.validate()
    _validate_import_currency(master)
    _validate_import_product_ids(master)
    _validate_import_rate_units(master)
