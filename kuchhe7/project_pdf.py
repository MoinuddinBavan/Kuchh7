"""Vector project dossier from the current design and existing engineering data.

All dimensions come from Project, the engineering plan geometry, the cabinet
BOM, and the existing wall-association service. This is a presentation document,
not an approved fabrication drawing or a substitute for editable DXF.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import ezdxf
from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen
from PySide6.QtWidgets import QApplication

from .bom import generate_project_bom
from .catalogue import get_catalogue_item
from .complete_kitchen_dxf import associate_cabinets_to_walls
from .cut_list import generate_cut_list
from .engineering_dxf import _cabinet_footprints, _room_geometry
from .openings import cabinet_wall_bounds, wall_length


SECTIONS = (
    ("plan", "2D Kitchen Plan"),
    ("views", "3D Kitchen Views"),
    ("walls", "Wall Elevations"),
    ("engineering", "Engineering Drawing Sheets"),
    ("schedule", "Cabinet Schedule"),
)
NAVY = QColor("#172A3C")
TEAL = QColor("#147D83")
BRONZE = QColor("#A76637")
INK = QColor("#344453")
PALE = QColor("#F7F9FB")


@dataclass(frozen=True)
class ProjectPdfOptions:
    sections: tuple[str, ...] = tuple(key for key, _ in SECTIONS)
    paper: str = "A3"
    quality: str = "High resolution"
    include_panels: bool = False

    def validate(self) -> None:
        known = {key for key, _ in SECTIONS}
        if not self.sections or len(self.sections) != len(set(self.sections)) or not set(self.sections) <= known:
            raise ValueError("Choose at least one valid Project PDF section.")
        if self.paper not in ("A3", "A4"):
            raise ValueError("Project PDF paper must be A3 or A4 landscape.")
        if self.quality not in ("High resolution", "Standard resolution"):
            raise ValueError("Unknown 3D image quality setting.")


def _font(size: int, bold: bool = False) -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def _text(p: QPainter, value: str, box: QRectF, size: int = 11,
          *, bold: bool = False, colour: QColor = INK,
          align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter) -> None:
    p.setFont(_font(size, bold))
    p.setPen(colour)
    p.drawText(box, align | Qt.TextFlag.TextWordWrap, value)


def _page_frame(p: QPainter, project, title: str, section: str,
                page: int, total: int, width: int, height: int) -> None:
    p.fillRect(QRectF(0, 0, width, height), Qt.GlobalColor.white)
    p.fillRect(QRectF(0, 0, width, 11), NAVY)
    _text(p, "KÜCHE7  /  DESIGN STUDIO", QRectF(50, 28, 360, 30), 18, bold=True, colour=NAVY)
    _text(p, project.name, QRectF(420, 30, width - 470, 26), 12,
          align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    p.setPen(QPen(QColor("#D5DEE2"), 1))
    p.drawLine(50, 68, width - 50, 68)
    _text(p, title, QRectF(50, 77, width - 100, 43), 23, bold=True, colour=NAVY)
    _text(p, f"{section}  |  {project.project_type}  |  mm  |  NOT TO SCALE",
          QRectF(50, 117, width - 100, 21), 10, colour=TEAL)
    p.setPen(QPen(QColor("#D5DEE2"), 1))
    p.drawLine(50, height - 51, width - 50, height - 51)
    _text(p, f"{date.today().isoformat()}  ·  Illustrative design/engineering; not factory approved",
          QRectF(50, height - 44, width - 180, 26), 9)
    _text(p, f"{page} / {total}", QRectF(width - 125, height - 44, 75, 26), 10,
          bold=True, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


def _plan_document(project):
    """Reuse the authoritative DXF plan geometry without writing a temporary file."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _room_geometry(msp, project)
    _cabinet_footprints(msp, project)
    return doc


def _draw_plan(p: QPainter, project, width: int, height: int, *, technical: bool = False) -> None:
    room = project.room
    target = QRectF(70, 152, width - 140, height - 255)
    margin = 310.0
    scale = min(target.width() / (room.width + 2 * margin),
                target.height() / (room.depth + 2 * margin))
    left = target.center().x() - room.width * scale / 2
    top = target.center().y() - room.depth * scale / 2

    def point(x: float, y: float):
        return left + x * scale, top + (room.depth - y) * scale

    msp = _plan_document(project).modelspace()
    for entity in msp:
        layer = entity.dxf.layer
        if layer not in ("ROOM_WALLS", "DOORS", "WINDOWS", "CABINET_FOOTPRINTS", "DIMENSIONS"):
            continue
        colour = (TEAL if layer == "WINDOWS" else BRONZE if layer == "CABINET_FOOTPRINTS"
                  else QColor("#77858A") if layer == "DIMENSIONS" else NAVY)
        p.setPen(QPen(colour, 1.4 if layer == "CABINET_FOOTPRINTS" else 2.3 if layer == "ROOM_WALLS" else 1.0))
        if entity.dxftype() == "LINE":
            x0, y0 = point(entity.dxf.start.x, entity.dxf.start.y)
            x1, y1 = point(entity.dxf.end.x, entity.dxf.end.y)
            p.drawLine(int(x0), int(y0), int(x1), int(y1))
        elif entity.dxftype() == "LWPOLYLINE":
            coords = [point(x, y) for x, y in entity.get_points("xy")]
            for first, second in zip(coords, coords[1:] + (coords[:1] if entity.closed else [])):
                p.drawLine(int(first[0]), int(first[1]), int(second[0]), int(second[1]))

    for cabinet in project.cabinets:
        x = cabinet.position_x + cabinet.footprint_width / 2
        y = room.depth - cabinet.position_y - cabinet.footprint_depth / 2
        sx, sy = point(x, y)
        # Vertically stacked wall/base footprints need separate readable labels.
        offset = -29 if cabinet.elevation_z else 18
        _text(p, cabinet.cabinet_id, QRectF(sx - 30, sy + offset - 10, 60, 20),
              10, bold=True, colour=NAVY, align=Qt.AlignmentFlag.AlignCenter)
    for opening in room.openings:
        if opening.wall_id in ("NORTH", "SOUTH"):
            x = opening.offset + opening.width / 2
            y = room.depth if opening.wall_id == "NORTH" else 0
        else:
            x = 0 if opening.wall_id == "WEST" else room.width
            y = room.depth - opening.offset - opening.width / 2
        sx, sy = point(x, y)
        _text(p, f"{opening.opening_id} {opening.kind} {opening.width} mm",
              QRectF(sx - 90, sy - (35 if opening.wall_id == "NORTH" else -8), 180, 20),
              9, colour=TEAL, align=Qt.AlignmentFlag.AlignCenter)
    _text(p, f"NORTH  ·  {room.width:,} mm", QRectF(left, top - 45, room.width * scale, 22),
          11, bold=True, align=Qt.AlignmentFlag.AlignCenter)
    _text(p, f"SOUTH  ·  {room.width:,} mm", QRectF(left, top + room.depth * scale + 20,
          room.width * scale, 22), 11, bold=True, align=Qt.AlignmentFlag.AlignCenter)
    _text(p, f"WEST · {room.depth:,} mm", QRectF(left - 115, top + room.depth * scale / 2 - 12,
          105, 24), 10, bold=True)
    _text(p, f"EAST · {room.depth:,} mm", QRectF(left + room.width * scale + 12,
          top + room.depth * scale / 2 - 12, 105, 24), 10, bold=True)
    if technical:
        _text(p, "DXF-derived room and cabinet footprints. Cabinet orientations are stored in room coordinates.",
              QRectF(65, height - 99, width - 130, 26), 10)


def _draw_image(p: QPainter, data: bytes, width: int, height: int) -> None:
    image = QImage.fromData(data, "PNG")
    if image.isNull() or image.width() < 800 or image.height() < 450:
        raise ValueError("The 3D viewport did not provide a usable high-resolution PNG.")
    available = QRectF(60, 151, width - 120, height - 245)
    ratio = min(available.width() / image.width(), available.height() / image.height())
    drawn = QRectF(available.center().x() - image.width() * ratio / 2,
                   available.center().y() - image.height() * ratio / 2,
                   image.width() * ratio, image.height() * ratio)
    p.drawImage(drawn, image)
    _text(p, f"Actual KÜCHE7 3D viewport · {image.width()} × {image.height()} px · presentation image only",
          QRectF(60, height - 87, width - 120, 24), 10)


def _draw_wall(p: QPainter, project, wall, assignments, width: int, height: int) -> None:
    room = project.room
    length = wall_length(room, wall.wall_id)
    rect = QRectF(74, 184, width - 148, height - 370)
    scale = min(rect.width() / length, rect.height() / room.height)
    x0 = rect.center().x() - length * scale / 2
    y0 = rect.center().y() - room.height * scale / 2
    p.setPen(QPen(NAVY, 2))
    p.drawRect(QRectF(x0, y0, length * scale, room.height * scale))
    for opening in room.openings:
        if opening.wall_id != wall.wall_id:
            continue
        box = QRectF(x0 + opening.offset * scale,
                     y0 + (room.height - opening.elevation - opening.height) * scale,
                     opening.width * scale, opening.height * scale)
        p.setPen(QPen(TEAL, 2))
        p.drawRect(box)
        _text(p, f"{opening.opening_id} {opening.kind} · {opening.width}×{opening.height} · sill {opening.elevation} mm",
              QRectF(box.x(), max(148, box.y() - 27), max(180, box.width()), 23), 9, colour=TEAL)
    associated = [c for c in project.cabinets if assignments[c.cabinet_id].wall_id == wall.wall_id]
    for cabinet in associated:
        bounds = cabinet_wall_bounds(room, cabinet, wall.wall_id)
        box = QRectF(x0 + bounds.u0 * scale,
                     y0 + (room.height - cabinet.elevation_z - cabinet.height) * scale,
                     (bounds.u1 - bounds.u0) * scale, cabinet.height * scale)
        p.fillRect(box, QColor("#F4ECE4"))
        p.setPen(QPen(BRONZE, 1.5))
        p.drawRect(box)
        _text(p, cabinet.cabinet_id, box.adjusted(4, 4, -4, -4), 11, bold=True,
              colour=NAVY, align=Qt.AlignmentFlag.AlignCenter)
    _text(p, f"Wall length {length:,} mm     Height {room.height:,} mm     Associated cabinets {len(associated)}",
          QRectF(75, height - 168, width - 150, 26), 12, bold=True)
    detail = ";  ".join(f"{c.cabinet_id}: W {c.width} H {c.height} Z {c.elevation_z} mm"
                       for c in associated) or "No associated cabinets"
    _text(p, detail, QRectF(75, height - 140, width - 150, 58), 10)


def _draw_table(p: QPainter, headers: tuple[str, ...], rows: list[tuple[str, ...]],
                width: int, height: int, *, column_fractions: tuple[float, ...]) -> None:
    x0, y0, content_width = 55.0, 160.0, width - 110.0
    row_height = 35 if width > 900 else 30
    widths = [content_width * part for part in column_fractions]
    p.fillRect(QRectF(x0, y0, content_width, row_height), NAVY)
    x = x0
    for label, cell_width in zip(headers, widths):
        _text(p, label, QRectF(x + 5, y0, cell_width - 8, row_height), 9,
              bold=True, colour=QColor("#FFFFFF"))
        x += cell_width
    y = y0 + row_height
    for index, row in enumerate(rows):
        if index % 2 == 0:
            p.fillRect(QRectF(x0, y, content_width, row_height), PALE)
        x = x0
        for value, cell_width in zip(row, widths):
            _text(p, str(value), QRectF(x + 5, y + 1, cell_width - 8, row_height - 2), 9)
            x += cell_width
        y += row_height


def _draw_panel_details(p: QPainter, rows, width: int, height: int) -> None:
    cell_height = (height - 235) / 2
    cell_width = (width - 145) / 2
    for index, row in enumerate(rows):
        col, line = index % 2, index // 2
        x, y = 60 + col * (cell_width + 25), 158 + line * (cell_height + 18)
        p.setPen(QPen(QColor("#CBD5D8"), 1))
        p.drawRect(QRectF(x, y, cell_width, cell_height))
        _text(p, f"{row.part_id} · {row.part_name}", QRectF(x + 12, y + 9, cell_width - 24, 27),
              12, bold=True)
        scale = min((cell_width - 70) / row.finished_length_mm,
                    (cell_height - 115) / row.finished_width_mm)
        dw, dh = row.finished_length_mm * scale, row.finished_width_mm * scale
        p.setPen(QPen(BRONZE, 2))
        p.drawRect(QRectF(x + (cell_width - dw) / 2, y + 49 + (cell_height - 115 - dh) / 2, dw, dh))
        _text(p, f"{row.finished_length_mm:g} × {row.finished_width_mm:g} × {row.thickness_mm:g} mm  ·  Qty {row.quantity}",
              QRectF(x + 12, y + cell_height - 58, cell_width - 24, 22), 10)
        _text(p, f"{row.material} · Grain {row.grain_direction} · {row.manufacturing_status}",
              QRectF(x + 12, y + cell_height - 36, cell_width - 24, 21), 9)


def export_project_pdf(project, path: str | Path, options: ProjectPdfOptions = ProjectPdfOptions(),
                       capture_3d: Callable[[str, tuple[int, int]], bytes] | None = None) -> Path:
    """Write one vector-backed PDF; capture_3d must use the live PyVista scene."""
    # The desktop application owns Qt's font database. Creating a temporary
    # application here can produce PDFs with missing-glyph boxes on Windows.
    if QApplication.instance() is None:
        raise RuntimeError("Project PDF export requires the running Qt desktop application.")
    options.validate()
    project.validate()
    if "views" in options.sections and capture_3d is None:
        raise ValueError("A live 3D viewport is required for the selected 3D section.")
    destination = Path(path)
    if destination.suffix.lower() != ".pdf":
        raise ValueError("Project document must have a .pdf extension.")
    width, height = (1191, 842) if options.paper == "A3" else (842, 595)
    assignments = associate_cabinets_to_walls(project)
    bom = generate_project_bom(project)
    cut_rows = generate_cut_list(project)
    pages: list[tuple[str, str, Callable[[QPainter], None]]] = []
    requested = set(options.sections)
    if "plan" in requested:
        pages.append(("2D Kitchen Plan", "Room, openings and cabinet footprints",
                      lambda p: _draw_plan(p, project, width, height)))
    if "views" in requested:
        resolution = (3200, 1800) if options.quality == "High resolution" else (1600, 900)
        for label, camera in (("Main Architectural Perspective", "Presentation"),
                              ("Overall Isometric View", "Isometric")):
            image = capture_3d(camera, resolution)
            pages.append(("3D Kitchen Views", label,
                          lambda p, data=image: _draw_image(p, data, width, height)))
    if "walls" in requested:
        relevant_walls = [wall for wall in project.room.walls
                          if any(opening.wall_id == wall.wall_id for opening in project.room.openings)
                          or any(item.wall_id == wall.wall_id for item in assignments.values())]
        for wall in relevant_walls:
            pages.append(("Wall Elevations", f"{wall.wall_id} · {wall.label}",
                          lambda p, item=wall: _draw_wall(p, project, item, assignments, width, height)))
        free = [c for c in project.cabinets if assignments[c.cabinet_id].wall_id is None]
        if free:
            rows = [(c.cabinet_id, get_catalogue_item(c.cabinet_type_id).name,
                     f"{c.width} × {c.height} × {c.depth}", f"X {c.position_x} · Y {c.position_y} · Z {c.elevation_z}")
                    for c in free]
            pages.append(("Wall Elevations", "Island / Free-standing cabinets",
                          lambda p, items=rows: _draw_table(p, ("ID", "Cabinet", "W × H × D mm", "Room location mm"),
                                                            items, width, height,
                                                            column_fractions=(.12, .36, .21, .31))))
    if "engineering" in requested:
        pages.append(("Engineering Drawing Sheets", "Complete kitchen technical arrangement",
                      lambda p: _draw_plan(p, project, width, height, technical=True)))
        per_page = 13 if width > 900 else 9
        rows = [(c.cabinet_id, c.name, f"{c.length_mm:g} × {c.width_mm:g} × {c.thickness_mm:g}",
                 c.material, str(c.quantity)) for c in bom]
        for index in range(0, max(1, len(rows)), per_page):
            chunk = rows[index:index + per_page]
            pages.append(("Engineering Drawing Sheets", "BOM panel and hardware references",
                          lambda p, items=chunk: _draw_table(p,
                              ("Cabinet", "Part", "L × W × T mm", "Material", "Qty"), items,
                              width, height, column_fractions=(.11, .31, .28, .21, .09))))
        if options.include_panels:
            for index in range(0, len(cut_rows), 4):
                chunk = cut_rows[index:index + 4]
                pages.append(("Engineering Drawing Sheets", "Individual panel outlines · illustrative",
                              lambda p, items=chunk: _draw_panel_details(p, items, width, height)))
    if "schedule" in requested:
        rows = []
        for cabinet in project.cabinets:
            panel_materials = {row.material for row in bom
                               if row.cabinet_id == cabinet.cabinet_id and row.thickness_mm > 0}
            material = next(iter(panel_materials)) if len(panel_materials) == 1 else "See BOM"
            rows.append((cabinet.cabinet_id, get_catalogue_item(cabinet.cabinet_type_id).name,
                         assignments[cabinet.cabinet_id].wall_id or "Island / Free-standing",
                         str(cabinet.width), str(cabinet.height), str(cabinet.depth),
                         material, cabinet.material, "1"))
        per_page = 14 if width > 900 else 9
        for index in range(0, max(1, len(rows)), per_page):
            chunk = rows[index:index + per_page]
            pages.append(("Cabinet Schedule", "All manufactured cabinets · one row per cabinet",
                          lambda p, items=chunk: _draw_table(p,
                              ("ID", "Cabinet type", "Wall / location", "W", "H", "D", "Material", "Finish", "Qty"),
                              items, width, height,
                              column_fractions=(.05, .20, .16, .06, .06, .06, .19, .17, .05))))

    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(destination))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A3 if options.paper == "A3"
                                 else QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setResolution(144)
    writer.setTitle(f"KÜCHE7 | {project.name} | Project Document")
    writer.setCreator("KÜCHE7 Design Studio / AIZ INFOTECHS")
    painter = QPainter()
    if not painter.begin(writer):
        raise OSError(f"Could not create Project PDF: {destination}")
    try:
        for number, (section, title, draw) in enumerate(pages, 1):
            if number > 1 and not writer.newPage():
                raise OSError("Could not add a Project PDF page.")
            painter.setViewport(0, 0, writer.width(), writer.height())
            painter.setWindow(0, 0, width, height)
            _page_frame(painter, project, title, section, number, len(pages), width, height)
            draw(painter)
    finally:
        painter.end()
    return destination
