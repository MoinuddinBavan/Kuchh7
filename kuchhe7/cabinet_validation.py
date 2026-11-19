"""Read-only comparison against supplied cabinet expectations.

No expected dimensions or prices are generated here. Missing reference sections
are reported as unchecked, not treated as passing acceptance criteria.
"""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory

import ezdxf

from .bom import generate_bom
from .costing import PricingRule, cost_cabinet
from .engineering_dxf import FRONT_ELEVATIONS, PANEL_OUTLINES, export_engineering_dxf
from .nesting import SheetSettings, nest_project
from .quotation import calculate_quotation

SECTIONS = ("cabinet", "components", "hardware", "bom_totals", "material_specifications",
            "cost", "selling_price", "quotation", "nesting", "drawing")


@dataclass(frozen=True)
class Difference:
    path: str
    expected: object
    actual: object
    difference: str


@dataclass
class ValidationReport:
    reference_id: str
    reference_status: str
    source_document: str
    cabinet_id: str
    tolerances: dict[str, str] = field(default_factory=dict)
    checked: list[str] = field(default_factory=list)
    unchecked_sections: list[str] = field(default_factory=list)
    mismatches: list[Difference] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return not self.mismatches

    def to_dict(self) -> dict:
        result = asdict(self)
        result["matched"] = self.matched
        result["all_supplied_expectations_match"] = self.matched and not self.unchecked_sections
        return result

    def to_markdown(self) -> str:
        label = "SYNTHETIC TEST ONLY" if self.reference_status == "synthetic" else "Client reference comparison"
        lines = [f"# {label}: {self.reference_id}", "",
                 f"Cabinet: `{self.cabinet_id}`  |  Source: {self.source_document}", "",
                 f"Checked fields: {len(self.checked)}  |  Mismatches: {len(self.mismatches)}", "",
                 "Unchecked sections: " + (", ".join(self.unchecked_sections) or "none"), ""]
        if self.mismatches:
            lines.extend(["| Field | Expected | Actual | Difference |", "|---|---|---|---|"])
            for item in self.mismatches:
                values = [item.path, item.expected, item.actual, item.difference]
                lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")
        else:
            lines.append("No mismatches among supplied expectations. This does not validate unchecked or unapproved rules.")
        return "\n".join(lines) + "\n"


def load_reference(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("expected"), dict):
        raise ValueError("Reference file must contain an expected object.")
    if data.get("reference_status") not in ("synthetic", "client_approved"):
        raise ValueError("Reference status must be synthetic or client_approved.")
    if not all(str(data.get(key, "")).strip() for key in ("reference_id", "cabinet_id", "source_document")):
        raise ValueError("Reference ID, cabinet ID and source document are required.")
    if data["reference_status"] == "client_approved" and not all(
            str(data.get(key, "")).strip() for key in ("approved_by", "revision")):
        raise ValueError("Client-approved references require approver and revision evidence.")
    unknown = set(data["expected"]) - set(SECTIONS)
    if unknown:
        raise ValueError("Unknown reference sections: " + ", ".join(sorted(unknown)))
    for path, tolerance in data.get("tolerances", {}).items():
        value = _decimal(tolerance)
        if not path.strip() or value is None or value < 0:
            raise ValueError("Reference tolerances must be non-negative numeric values keyed by field path.")
    return data


def _decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _compare(report: ValidationReport, path: str, expected: object, actual: object) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            report.mismatches.append(Difference(path, expected, actual, "type / record mismatch"))
            return
        for key, value in expected.items():
            if key not in actual:
                report.mismatches.append(Difference(f"{path}.{key}", value, "<missing>", "missing actual field"))
            else:
                _compare(report, f"{path}.{key}", value, actual[key])
        return
    report.checked.append(path)
    expected_number, actual_number = _decimal(expected), _decimal(actual)
    if expected_number is not None and actual_number is not None:
        if abs(expected_number - actual_number) > Decimal(report.tolerances.get(path, "0")):
            report.mismatches.append(Difference(path, expected, actual, str(actual_number - expected_number)))
    elif expected != actual:
        report.mismatches.append(Difference(path, expected, actual, "value differs"))


def _compare_named_rows(report: ValidationReport, path: str, expected: list[dict],
                        actual: list[dict], key: str = "name") -> None:
    if not isinstance(expected, list):
        raise ValueError(f"{path} reference must be a list.")
    expected_by_name = {str(row[key]): row for row in expected}
    actual_by_name = {str(row[key]): row for row in actual}
    if len(expected_by_name) != len(expected) or len(actual_by_name) != len(actual):
        raise ValueError(f"{path} has duplicate {key} values; use unique names in the reference.")
    for name, expected_row in expected_by_name.items():
        if name not in actual_by_name:
            report.mismatches.append(Difference(f"{path}.{name}", expected_row, "<missing>", "missing actual row"))
        else:
            _compare(report, f"{path}.{name}", expected_row, actual_by_name[name])
    for name, actual_row in actual_by_name.items():
        if name not in expected_by_name:
            report.mismatches.append(Difference(f"{path}.{name}", "<not expected>", actual_row, "unexpected actual row"))


def _compare_exact_map(report: ValidationReport, path: str, expected: dict, actual: dict) -> None:
    _compare(report, path, expected, actual)
    for key, value in actual.items():
        if key not in expected:
            report.mismatches.append(Difference(f"{path}.{key}", "<not expected>", value,
                                                "unexpected actual value"))


def _dimension_key(length: object, width: object) -> tuple[str, str]:
    return (format(Decimal(str(length)).normalize(), "f"),
            format(Decimal(str(width)).normalize(), "f"))


def _panel_rectangles_from_dxf(project, cabinet) -> tuple[int, list[dict]]:
    single = deepcopy(project)
    single.cabinets = [next(item for item in single.cabinets if item.cabinet_id == cabinet.cabinet_id)]
    single.select_cabinet(cabinet.cabinet_id)
    single.hardware_assignments = [item for item in single.hardware_assignments if item.cabinet_id == cabinet.cabinet_id]
    with TemporaryDirectory(prefix="kuche7-validation-") as folder:
        path = export_engineering_dxf(single, Path(folder) / "panels.dxf", PANEL_OUTLINES)
        drawing = ezdxf.readfile(path)
        rectangles = []
        for entity in drawing.modelspace().query('LWPOLYLINE[layer=="PANEL_OUTLINES"]'):
            points = [(float(x), float(y)) for x, y, *_ in entity.get_points()]
            rectangles.append((round(max(x for x, _ in points) - min(x for x, _ in points), 6),
                               round(max(y for _, y in points) - min(y for _, y in points), 6)))
        counts = Counter(rectangles)
        return drawing.header["$INSUNITS"], [
            {"length_mm": length, "width_mm": width, "quantity": count}
            for (length, width), count in sorted(counts.items())]


def _front_elevation_from_dxf(project, cabinet) -> dict:
    single = deepcopy(project)
    single.cabinets = [next(item for item in single.cabinets if item.cabinet_id == cabinet.cabinet_id)]
    single.select_cabinet(cabinet.cabinet_id)
    single.hardware_assignments = [item for item in single.hardware_assignments if item.cabinet_id == cabinet.cabinet_id]
    with TemporaryDirectory(prefix="kuche7-validation-") as folder:
        path = export_engineering_dxf(single, Path(folder) / "front.dxf", FRONT_ELEVATIONS)
        drawing = ezdxf.readfile(path)
        outlines = list(drawing.modelspace().query('LWPOLYLINE[layer=="ELEVATION_OUTLINES"]'))
        if len(outlines) != 1:
            return {"insunits": drawing.header["$INSUNITS"], "outline_count": len(outlines)}
        points = [(float(x), float(y)) for x, y, *_ in outlines[0].get_points()]
        return {"insunits": drawing.header["$INSUNITS"], "outline_count": 1,
                "width_mm": max(x for x, _ in points) - min(x for x, _ in points),
                "height_mm": max(y for _, y in points) - min(y for _, y in points)}


def compare_cabinet(project, reference: dict) -> ValidationReport:
    """Compare only explicitly supplied expectations; never mutate project data."""
    if not isinstance(reference, dict) or "expected" not in reference:
        raise ValueError("Use a validated cabinet reference object.")
    project = deepcopy(project)
    cabinet_id = str(reference["cabinet_id"])
    cabinet = next((item for item in project.cabinets if item.cabinet_id == cabinet_id), None)
    if cabinet is None:
        raise ValueError(f"Cabinet {cabinet_id} is not in the project.")
    project.validate()
    report = ValidationReport(reference["reference_id"], reference["reference_status"],
                              reference["source_document"], cabinet_id,
                              reference.get("tolerances", {}))
    expected = reference["expected"]
    report.unchecked_sections = [name for name in SECTIONS if name not in expected]
    components = generate_bom(cabinet)
    actual_components = [asdict(row) for row in components]
    for row in actual_components:
        row.pop("cabinet_id"); row.pop("cabinet_type")
    panel_rows = [row for row in components if row.length_mm > 0 and row.width_mm > 0 and row.thickness_mm > 0]
    hardware_rows = [row for row in components if row.material == "Hardware"]
    actual = {
        "cabinet": {key: getattr(cabinet, key) for key in
                    ("width", "height", "depth", "board_thickness", "door_count", "drawer_count",
                     "shelf_count", "material", "cabinet_type_id")},
        "components": actual_components,
        "hardware": {row.name: row.quantity for row in hardware_rows},
        "bom_totals": {"component_rows": len(components),
                       "panel_instances": sum(row.quantity for row in panel_rows),
                       "hardware_instances": sum(row.quantity for row in hardware_rows),
                       "total_component_quantity": sum(row.quantity for row in components)},
    }
    if "material_specifications" in expected:
        actual["material_specifications"] = {
            f"{material}|{thickness:g}": (record.specification if record else None)
            for material, thickness in sorted({(row.material, row.thickness_mm) for row in panel_rows})
            for record in [project.price_master.approved("Board", material, thickness,
                                                        as_of=project.quotation.quotation_date)]}
    rule = project.quotation.pricing_rules.get(cabinet_id, PricingRule())
    if "cost" in expected:
        result = cost_cabinet(cabinet, project.price_master,
                              hardware_assignments=project.hardware_assignments,
                              charge_quantities=rule.charge_quantities,
                              currency=project.quotation.currency,
                              as_of=project.quotation.quotation_date)
        actual["cost"] = {"status": result.status, "currency": result.currency,
                          "total": str(result.total) if result.total is not None else None,
                          "missing": list(result.missing),
                          "lines": [dict(component=line.component, source_id=line.source_id,
                                         unit=line.unit, quantity=str(line.quantity),
                                         rate=str(line.rate), amount=str(line.amount)) for line in result.lines]}
    if "selling_price" in expected or "quotation" in expected:
        quote = calculate_quotation(project)
        line = next(item for item in quote.lines if item.item_id == cabinet_id)
        actual["selling_price"] = {"pricing_mode": line.pricing_mode,
                                   "unit_price": str(line.unit_price) if line.unit_price is not None else None}
        actual["quotation"] = {key: str(getattr(quote, key)) for key in
                               ("subtotal", "discount", "taxable_amount", "tax", "total")}
        actual["quotation"]["unpriced_ids"] = list(quote.unpriced_ids)
    if "nesting" in expected:
        settings = SheetSettings(**reference.get("nesting_settings", {}))
        result = nest_project(project, settings)
        actual["nesting"] = {key: getattr(result, key) for key in
                             ("eligible_count", "placed_count", "unplaced_count", "sheet_count",
                              "total_panel_area_mm2", "utilization_percent")}
    if "drawing" in expected:
        units, rectangles = _panel_rectangles_from_dxf(project, cabinet)
        actual["drawing"] = {"type": PANEL_OUTLINES, "insunits": units,
                             "panel_rectangles": rectangles}
        if "front_elevation" in expected["drawing"]:
            actual["drawing"]["front_elevation"] = _front_elevation_from_dxf(project, cabinet)
    for name, values in expected.items():
        if name == "components":
            _compare_named_rows(report, name, values, actual[name])
        elif name == "drawing" and "panel_rectangles" in values:
            rectangles = values["panel_rectangles"]
            _compare(report, "drawing.type", values.get("type", PANEL_OUTLINES), actual[name]["type"])
            if "insunits" in values:
                _compare(report, "drawing.insunits", values["insunits"], actual[name]["insunits"])
            expected_counts = {_dimension_key(row["length_mm"], row["width_mm"]): row["quantity"] for row in rectangles}
            actual_counts = {_dimension_key(row["length_mm"], row["width_mm"]): row["quantity"]
                             for row in actual[name]["panel_rectangles"]}
            _compare_exact_map(report, "drawing.panel_rectangles", expected_counts, actual_counts)
            if "front_elevation" in values:
                _compare(report, "drawing.front_elevation", values["front_elevation"],
                         actual[name]["front_elevation"])
        elif name == "cost" and isinstance(values, dict) and "lines" in values:
            _compare(report, "cost", {key: value for key, value in values.items() if key != "lines"}, actual[name])
            _compare_named_rows(report, "cost.lines", values["lines"], actual[name]["lines"], key="component")
        elif name in ("hardware", "material_specifications"):
            _compare_exact_map(report, name, values, actual[name])
        else:
            _compare(report, name, values, actual[name])
    return report
