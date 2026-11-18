"""Local, explicitly approved demo rates. No prices are supplied by the application."""

from __future__ import annotations

import csv
import json
from zipfile import BadZipFile
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

CATEGORIES = ("Board", "Surface finish", "Laminate", "Edge banding", "Hardware", "Accessory",
              "Appliance", "Labour", "Machining", "Finishing")
UNITS = ("m2", "m", "each", "hour", "sheet")
STATUSES = ("draft", "approved")
PRICE_COLUMNS = ("record_id", "category", "match_key", "description", "unit", "rate", "currency",
                 "effective_date", "status", "thickness_mm", "sheet_length_mm", "sheet_width_mm",
                 "specification")


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

    def validate(self) -> None:
        if not self.record_id.strip() or not self.match_key.strip() or not self.description.strip():
            raise ValueError("Price record ID, match key and description are required.")
        if self.category not in CATEGORIES or self.unit not in UNITS or self.status not in STATUSES:
            raise ValueError(f"Unsupported price category, unit or status for {self.record_id}.")
        if self.rate != "":
            nonnegative_decimal(self.rate, f"Rate for {self.record_id}")
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha() or self.currency != self.currency.upper()):
            raise ValueError(f"Currency for {self.record_id} must be a three-letter uppercase code.")
        if self.effective_date:
            try:
                date.fromisoformat(self.effective_date)
            except ValueError as error:
                raise ValueError(f"Effective date for {self.record_id} must use YYYY-MM-DD.") from error
        for name in ("thickness_mm", "sheet_length_mm", "sheet_width_mm"):
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


@dataclass
class PriceMaster:
    records: list[PriceRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.records = [row if isinstance(row, PriceRecord) else PriceRecord(**row) for row in self.records]

    def validate(self) -> None:
        ids: set[str] = set()
        approved_keys: set[tuple[str, str, str, str]] = set()
        for record in self.records:
            record.validate()
            if record.record_id in ids:
                raise ValueError(f"Duplicate price record ID: {record.record_id}")
            ids.add(record.record_id)
            if record.status == "approved":
                key = (record.category, record.match_key.casefold(), record.thickness_mm,
                       record.effective_date)
                if key in approved_keys:
                    raise ValueError(f"Multiple approved rates match {record.category} {record.match_key} {record.thickness_mm}.")
                approved_keys.add(key)

    def approved(self, category: str, match_key: str, thickness_mm: float | None = None,
                 as_of: str | None = None) -> PriceRecord | None:
        thickness = "" if thickness_mm is None else str(Decimal(str(thickness_mm)).normalize())
        cutoff = as_of or date.today().isoformat()
        for record in sorted(self.records, key=lambda item: item.effective_date, reverse=True):
            if (record.status == "approved" and record.category == category
                    and record.effective_date <= cutoff
                    and record.match_key.casefold() == match_key.casefold()
                    and (thickness_mm is None or str(Decimal(record.thickness_mm).normalize()) == thickness)):
                return record
        return None

    def to_dict(self) -> dict:
        self.validate()
        return {"schema_version": 1, "records": [asdict(row) for row in self.records]}

    @classmethod
    def from_dict(cls, data: dict) -> "PriceMaster":
        if not isinstance(data, dict) or not isinstance(data.get("records", []), list):
            raise ValueError("Price master must contain a records list.")
        try:
            result = cls(data.get("records", []))
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
        return PriceMaster.from_dict(json.loads(source.read_text(encoding="utf-8")))
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            rows = list(reader)
    elif suffix == ".xlsx":
        try:
            sheet = load_workbook(source, read_only=True, data_only=True).active
        except (BadZipFile, InvalidFileException) as error:
            raise ValueError("Price list is not a valid XLSX workbook.") from error
        values = sheet.iter_rows(values_only=True)
        try:
            headers = [str(value or "").strip() for value in next(values)]
        except StopIteration as error:
            raise ValueError("Price list is empty.") from error
        rows = [dict(zip(headers, row)) for row in values if any(value is not None for value in row)]
    else:
        raise ValueError("Price master must be JSON, CSV or XLSX.")
    required = {"record_id", "category", "match_key", "description", "unit", "rate", "currency", "effective_date", "status"}
    if not required.issubset(headers):
        raise ValueError("Price list is missing required columns: " + ", ".join(sorted(required - set(headers))))
    normalized = [{key: "" if row.get(key) is None else str(row[key]).strip() for key in PRICE_COLUMNS} for row in rows]
    return PriceMaster.from_dict({"records": normalized})
