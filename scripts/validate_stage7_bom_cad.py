"""Stage 7 synthetic BOM/DXF audit; never certifies factory construction."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from kuchhe7.bom import generate_project_bom
from kuchhe7.document_exports import export_bom_pdf
from kuchhe7.engineering_dxf import (
    FRONT_ELEVATIONS, KITCHEN_LAYOUT, PANEL_OUTLINES, ROOM_PLAN,
    eligible_panel_instances, export_engineering_dxf,
)
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.nesting import expand_panel_instances
from kuchhe7.persistence import load_project, save_project


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "fixtures" / "stage7_six_cabinet_synthetic_bom.json"


def expected_number(value: object) -> float:
    return float(Fraction(str(value)))


def compare_synthetic_bom(project: Project, reference: dict) -> tuple[list[dict], list[str]]:
    """Compare static arithmetic expectations against the authoritative BOM."""
    actual_by_cabinet = {cabinet.cabinet_id: {} for cabinet in project.cabinets}
    for component in generate_project_bom(project):
        actual_by_cabinet[component.cabinet_id][component.name] = component
    rows: list[dict] = []
    mismatches: list[str] = []
    if set(actual_by_cabinet) != set(reference["cabinets"]):
        mismatches.append("Cabinet ID set differs from synthetic reference")
    for cabinet in project.cabinets:
        expected = reference["cabinets"].get(cabinet.cabinet_id)
        if expected is None:
            continue
        if (cabinet.cabinet_type_id, [cabinet.width, cabinet.height, cabinet.depth], cabinet.material) != (
            expected["type_id"], expected["size"], expected["material"]
        ):
            mismatches.append(f"{cabinet.cabinet_id}: cabinet input differs")
        actual_parts = actual_by_cabinet[cabinet.cabinet_id]
        names = {entry[0] for entry in expected["components"]}
        if names != set(actual_parts):
            mismatches.append(f"{cabinet.cabinet_id}: component names differ: {names ^ set(actual_parts)}")
        for name, length, width, thickness, material, quantity in expected["components"]:
            actual = actual_parts.get(name)
            expected_values = [expected_number(length), expected_number(width),
                               expected_number(thickness), material, quantity]
            actual_values = ([actual.length_mm, actual.width_mm, actual.thickness_mm,
                              actual.material, actual.quantity] if actual else [None] * 5)
            equal = actual is not None and all(
                abs(left - right) < 1e-7 if isinstance(left, (float, int)) and isinstance(right, (float, int))
                else left == right
                for left, right in zip(expected_values, actual_values)
            )
            if not equal:
                mismatches.append(f"{cabinet.cabinet_id}/{name}: expected {expected_values}, actual {actual_values}")
            rows.append(dict(cabinet_id=cabinet.cabinet_id, component=name,
                             expected=expected_values, actual=actual_values,
                             result="MATCH" if equal else "MISMATCH"))
    return rows, mismatches


def raw_dxf_pairs(path: Path) -> list[tuple[int, str]]:
    """Read ASCII DXF group-code pairs independently of ezdxf's entity API."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) % 2:
        raise ValueError(f"Incomplete DXF group-code pair: {path.name}")
    return [(int(lines[index].strip()), lines[index + 1].strip())
            for index in range(0, len(lines), 2)]


def raw_insunits(pairs: list[tuple[int, str]]) -> int | None:
    for index, pair in enumerate(pairs[:-1]):
        if pair == (9, "$INSUNITS"):
            return int(pairs[index + 1][1])
    return None


def raw_entities(pairs: list[tuple[int, str]]) -> list[tuple[str, list[tuple[int, str]]]]:
    result: list[tuple[str, list[tuple[int, str]]]] = []
    in_entities = False
    pending_section = False
    current: tuple[str, list[tuple[int, str]]] | None = None
    for code, value in pairs:
        if code == 0 and value == "SECTION":
            pending_section = True
            continue
        if pending_section and code == 2:
            in_entities = value == "ENTITIES"
            pending_section = False
            continue
        if code == 0 and value == "ENDSEC":
            if current:
                result.append(current)
                current = None
            in_entities = False
            continue
        if not in_entities:
            continue
        if code == 0:
            if current:
                result.append(current)
            current = (value, [])
        elif current:
            current[1].append((code, value))
    return result


def entity_layer(entity: tuple[str, list[tuple[int, str]]]) -> str:
    return next((value for code, value in entity[1] if code == 8), "0")


def polyline_points(entity: tuple[str, list[tuple[int, str]]]) -> list[tuple[float, float]]:
    points: list[list[float]] = []
    for code, value in entity[1]:
        if code == 10:
            points.append([float(value), 0.0])
        elif code == 20 and points:
            points[-1][1] = float(value)
    return [(x, y) for x, y in points]


def line_points(entity: tuple[str, list[tuple[int, str]]]) -> tuple[tuple[float, float], tuple[float, float]]:
    values = dict(entity[1])
    return ((float(values[10]), float(values[20])),
            (float(values[11]), float(values[21])))


def verify_dxf_geometry(project: Project, paths: dict[str, Path]) -> dict:
    """Check ezdxf audit plus independent ASCII entity/coordinate extraction."""
    parsed = {}
    for kind, path in paths.items():
        doc = ezdxf.readfile(path)
        audit = doc.audit()
        pairs = raw_dxf_pairs(path)
        assert doc.header["$INSUNITS"] == raw_insunits(pairs) == 4, kind
        assert doc.units == ezdxf.units.MM and not audit.has_errors, kind
        parsed[kind] = raw_entities(pairs)

    room = parsed[ROOM_PLAN]
    walls = [entity for entity in room if entity[0] == "LINE" and entity_layer(entity) == "ROOM_WALLS"]
    doors = [entity for entity in room if entity_layer(entity) == "DOORS"]
    windows = [entity for entity in room if entity_layer(entity) == "WINDOWS"]
    texts = [next((value for code, value in entity[1] if code == 1), "")
             for entity in room if entity[0] == "TEXT"]
    assert len(walls) == 6 and len(doors) == 2 and len(windows) == 1
    assert ((0.0, 0.0), (float(project.room.width), 0.0)) in [line_points(item) for item in walls]
    assert ((0.0, float(project.room.depth)),
            (float(project.room.width), float(project.room.depth))) in [line_points(item) for item in walls]
    sample_door = next(item for item in project.room.openings if item.opening_id == "D1")
    sample_window = next(item for item in project.room.openings if item.opening_id == "W1")
    assert sample_door.wall_id == sample_window.wall_id == "WEST"
    assert ((0.0, project.room.depth - sample_window.offset),
            (0.0, project.room.depth - sample_window.offset - sample_window.width)) == line_points(windows[0])
    door_leaf = next(item for item in doors if item[0] == "LINE")
    assert line_points(door_leaf) == ((0.0, project.room.depth - sample_door.offset),
                                     (float(sample_door.width), project.room.depth - sample_door.offset))
    assert f"{project.room.width} mm" in texts and f"{project.room.depth} mm" in texts
    assert any(text.startswith("D1 DOOR") for text in texts)
    assert any(text.startswith("W1 WINDOW") for text in texts)

    layout = parsed[KITCHEN_LAYOUT]
    footprints = [entity for entity in layout
                  if entity[0] == "LWPOLYLINE" and entity_layer(entity) == "CABINET_FOOTPRINTS"]
    assert len(footprints) == len(project.cabinets)
    for cabinet, outline in zip(project.cabinets, footprints):
        x, y = cabinet.position_x, project.room.depth - cabinet.position_y - cabinet.footprint_depth
        points = polyline_points(outline)
        assert points == [(x, y), (x + cabinet.footprint_width, y),
                          (x + cabinet.footprint_width, y + cabinet.footprint_depth),
                          (x, y + cabinet.footprint_depth)]

    elevations = [entity for entity in parsed[FRONT_ELEVATIONS]
                  if entity[0] == "LWPOLYLINE" and entity_layer(entity) == "ELEVATION_OUTLINES"]
    assert len(elevations) == len(project.cabinets)
    for cabinet, outline in zip(project.cabinets, elevations):
        x, z = cabinet.position_x, cabinet.elevation_z
        assert polyline_points(outline) == [(x, z), (x + cabinet.width, z),
                                           (x + cabinet.width, z + cabinet.height),
                                           (x, z + cabinet.height)]

    panels = [entity for entity in parsed[PANEL_OUTLINES]
              if entity[0] == "LWPOLYLINE" and entity_layer(entity) == "PANEL_OUTLINES"]
    eligible = eligible_panel_instances(project)
    assert len(panels) == len(eligible)
    for (component, _instance), outline in zip(eligible, panels):
        points = polyline_points(outline)
        assert abs(points[1][0] - points[0][0] - component.length_mm) < 1e-6
        assert abs(points[2][1] - points[1][1] - component.width_mm) < 1e-6
    assert len(expand_panel_instances(generate_project_bom(project))) == len(panels)
    return dict(room_wall_segments=len(walls), door_entities=len(doors),
                window_entities=len(windows), cabinet_footprints=len(footprints),
                front_elevations=len(elevations), panel_outlines=len(panels),
                units="mm", dxf_version="R2010")


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert reference["reference_status"] == "synthetic"
    project = Project.complete_kitchen_demo("Stage 7 Synthetic Six-Cabinet Validation")
    project_path = save_project(project, output / "six-cabinet-synthetic-project.json")
    reopened = load_project(project_path)
    before = reopened.to_dict()
    rows, mismatches = compare_synthetic_bom(reopened, reference)
    assert not mismatches, "\n".join(mismatches)

    xlsx = export_bom_xlsx(reopened, output / "six-cabinet-bom.xlsx")
    pdf = export_bom_pdf(reopened, output / "six-cabinet-bom.pdf")
    dxf_paths = {
        kind: export_engineering_dxf(reopened, output / f"six-cabinet-{kind}.dxf", kind)
        for kind in (ROOM_PLAN, KITCHEN_LAYOUT, FRONT_ELEVATIONS, PANEL_OUTLINES)
    }
    legacy = export_front_elevation_dxf(reopened, output / "six-cabinet-legacy-elevation.dxf")
    assert ezdxf.readfile(legacy).header["$INSUNITS"] == 4
    geometry = verify_dxf_geometry(reopened, dxf_paths)
    components = generate_project_bom(reopened)
    workbook_rows = list(load_workbook(xlsx, data_only=True)["BOM"].iter_rows(min_row=5, values_only=True))
    assert len(workbook_rows) == len(components)
    for component, row in zip(components, workbook_rows):
        expected_row = (component.name, component.length_mm, component.width_mm,
                        component.thickness_mm, component.material, component.quantity,
                        component.cabinet_id, component.cabinet_type)
        assert row[0] == expected_row[0] and row[4:] == expected_row[4:]
        assert all(abs(float(row[index]) - float(expected_row[index])) < 1e-7
                   for index in (1, 2, 3))
    pdf_bytes = pdf.read_bytes()
    assert pdf_bytes.startswith(b"%PDF") and all(
        name.encode("ascii") in pdf_bytes for name in ("Left side panel", "Concealed hinge", "Drawer runner pair")
    )
    assert reopened.to_dict() == before

    audit = dict(reference_status="SYNTHETIC TEST ONLY", reference=str(REFERENCE),
                 cabinet_ids=[cabinet.cabinet_id for cabinet in reopened.cabinets],
                 bom_rows=len(components), component_quantity=sum(row.quantity for row in components),
                 panel_instances=len(eligible_panel_instances(reopened)),
                 hardware_quantity=sum(row.quantity for row in components if row.material == "Hardware"),
                 expected_actual_matches=len(rows), mismatches=mismatches,
                 geometry=geometry, dwg="NOT GENERATED: no DWG converter installed; legal use unresolved",
                 files={"project_json": str(project_path), "bom_xlsx": str(xlsx), "bom_pdf": str(pdf),
                        "legacy_elevation_dxf": str(legacy),
                        **{f"{kind}_dxf": str(path) for kind, path in dxf_paths.items()}})
    (output / "validation.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    lines = ["# Stage 7 synthetic expected-versus-actual BOM", "",
             "These expected values are independent arithmetic examples, not client-approved construction.", "",
             "| Cabinet | Component | Expected L × W × T mm; material; qty | Actual | Result |",
             "|---|---|---|---|---|"]
    for row in rows:
        def formatted(values):
            return (f"{values[0]:g} × {values[1]:g} × {values[2]:g}; "
                    f"{values[3]}; {values[4]}")
        lines.append(f"| {row['cabinet_id']} | {row['component']} | {formatted(row['expected'])} | "
                     f"{formatted(row['actual'])} | {row['result']} |")
    (output / "expected_vs_actual_bom.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo_output" / "stage7_validation"
    print(json.dumps(run(target), indent=2))
