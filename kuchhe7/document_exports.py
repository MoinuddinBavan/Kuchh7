"""Presentation documents; calculations remain in bom.py and quotation.py."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .bom import generate_project_bom
from .quotation import calculate_quotation

NAVY = "172A3C"
TEAL = "147D83"


@dataclass(frozen=True)
class ExcelLayout:
    """A supplied workbook can reserve a BOM sheet and specify where rows start."""

    sheet_name: str = "BOM"
    header_row: int = 4


def export_bom_template_xlsx(project, path: str | Path, *, template_path: str | Path | None = None,
                             layout: ExcelLayout = ExcelLayout()) -> Path:
    project.validate()
    if layout.header_row < 4:
        raise ValueError("BOM header row must be at least 4.")
    workbook = load_workbook(template_path) if template_path else Workbook()
    sheet = workbook[layout.sheet_name] if layout.sheet_name in workbook else workbook.active
    sheet.title = layout.sheet_name
    sheet.cell(1, 1, "KÜCHE7 Demonstration BOM — illustrative engineering quantities; not factory approved")
    sheet.cell(2, 1, "Project")
    sheet.cell(2, 2, project.name)
    sheet.cell(2, 3, "Type")
    sheet.cell(2, 4, project.project_type)
    headers = ("Component", "Length (mm)", "Width (mm)", "Thickness (mm)",
               "Material", "Quantity", "Cabinet ID", "Cabinet Type")
    for column, value in enumerate(headers, 1):
        cell = sheet.cell(layout.header_row, column, value)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=TEAL)
    for row, component in enumerate(generate_project_bom(project), layout.header_row + 1):
        values = (component.name, component.length_mm, component.width_mm,
                  component.thickness_mm, component.material, component.quantity,
                  component.cabinet_id, component.cabinet_type)
        for column, value in enumerate(values, 1):
            sheet.cell(row, column, value)
    for column, width in zip("ABCDEFGH", (27, 15, 15, 18, 20, 12, 14, 30)):
        sheet.column_dimensions[column].width = max(sheet.column_dimensions[column].width or 0, width)
    sheet.freeze_panes = f"A{layout.header_row + 1}"
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(destination)
    return destination


def export_quotation_xlsx(project, path: str | Path) -> Path:
    summary = calculate_quotation(project)
    data = project.quotation
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quotation"
    sheet.append(["KÜCHE7 Customer Quotation — demonstration; prices entered by user"])
    sheet.append(["Project", project.name, "Customer", data.customer_name])
    sheet.append(["Quote no.", data.quotation_number, "Date", data.quotation_date])
    sheet.append([])
    sheet.append(["ID", "Sellable item", "Category", "Qty", "Unit price", "Line total", "Status"])
    for line in summary.lines:
        sheet.append([line.item_id, line.description, line.category, line.quantity,
                      float(line.unit_price) if line.unit_price is not None else None,
                      float(line.total) if line.total is not None else None,
                      "Billable" if line.billable else "Client supplied / excluded"])
    row = sheet.max_row + 2
    for label, value in (("Subtotal", summary.subtotal),
                         (f"Discount ({data.discount_percent}%)", summary.discount),
                         ("After discount", summary.taxable_amount),
                         (f"Tax ({data.tax_percent}%)", summary.tax),
                         ("Total", summary.total)):
        sheet.cell(row, 5, label)
        sheet.cell(row, 6, float(value)).number_format = '#,##0.00'
        row += 1
    if summary.unpriced_ids:
        sheet.cell(row + 1, 1, "INCOMPLETE — prices missing: " + ", ".join(summary.unpriced_ids))
    sheet.cell(row + 2, 1, "Demonstration quotation. Currency and commercial terms require client approval.")
    for cell in sheet[5]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=TEAL)
    for column, width in zip("ABCDEFG", (15, 32, 24, 10, 18, 18, 30)):
        sheet.column_dimensions[column].width = width
    for cells in sheet.iter_rows(min_row=6, max_row=5 + len(summary.lines), min_col=5, max_col=6):
        for cell in cells:
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal="right")
    sheet.freeze_panes = "A6"
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(destination)
    return destination


def _pdf(path: str | Path, title: str, subtitle: str, headers: tuple[str, ...],
         rows: list[tuple[str, ...]], footer: list[str]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pages: list[list[str]] = [[]]
    y = 795

    def safe(value: str) -> str:
        value = value.replace("Ü", "U").replace("ü", "u").replace("—", "-").replace("–", "-")
        value = value.encode("ascii", "replace").decode("ascii")
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def write(value: str, x: float, *, bold: bool = False, size: int = 9,
              colour: str = NAVY) -> None:
        r, g, b = (int(colour[index:index + 2], 16) / 255 for index in (0, 2, 4))
        font = "F2" if bold else "F1"
        pages[-1].append(f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg {x:.1f} {y:.1f} Td ({safe(value)}) Tj ET")

    def next_line(height: int = 17) -> None:
        nonlocal y
        y -= height

    def new_page() -> None:
        nonlocal y
        pages.append([])
        y = 795
        write(title + " (continued)", 42, bold=True, size=12, colour=TEAL)
        next_line(28)

    write(title, 42, bold=True, size=16, colour=TEAL)
    next_line(28)
    write(subtitle[:100], 42)
    next_line(30)
    widths = ([45, 175, 78, 34, 72, 65, 80] if len(headers) == 7
              else [105, 46, 46, 46, 72, 26, 42, 128])
    starts = [42]
    for width in widths[:-1]:
        starts.append(starts[-1] + width)

    def table_row(values: tuple[str, ...], bold: bool = False) -> None:
        for value, x, width in zip(values, starts, widths):
            # Approximate Helvetica 8pt glyph width and keep columns separate.
            write(str(value)[:max(4, int(width / 4.4))], x, bold=bold, size=8,
                  colour=TEAL if bold else NAVY)
        next_line(18)

    table_row(headers, bold=True)
    for row in rows:
        if y < 65:
            new_page()
            table_row(headers, bold=True)
        table_row(row)
    next_line(12)
    for entry in footer:
        if y < 55:
            new_page()
        write(entry[:105], 42, bold=entry.startswith(("TOTAL", "INCOMPLETE")))
        next_line()

    # Small, deterministic PDF with extractable Helvetica text and no extra dependency.
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")  # Page tree filled after page objects are allocated.
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    page_ids: list[int] = []
    for commands in pages:
        page_id = len(objects) + 1
        content_id = page_id + 1
        page_ids.append(page_id)
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                        f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                        f"/Contents {content_id} 0 R >>").encode("ascii"))
        stream = "\n".join(commands).encode("ascii")
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
    kids = " ".join(f"{item} 0 R" for item in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, content in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii") + content + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    destination.write_bytes(output)
    return destination


def export_bom_pdf(project, path: str | Path) -> Path:
    components = generate_project_bom(project)
    rows = [(item.name, str(item.length_mm), str(item.width_mm), str(item.thickness_mm),
             item.material, str(item.quantity), item.cabinet_id, item.cabinet_type)
            for item in components]
    return _pdf(path, "KÜCHE7 | BILL OF MATERIALS", f"{project.name}  /  {project.project_type}",
                ("Component", "L mm", "W mm", "T mm", "Material", "Qty", "Cabinet", "Type"),
                rows, ["Illustrative engineering quantities only — not factory approved."])


def export_quotation_pdf(project, path: str | Path) -> Path:
    summary = calculate_quotation(project)
    data = project.quotation
    rows = [(line.item_id, line.description, line.category, str(line.quantity),
             str(line.unit_price) if line.unit_price is not None else "—",
             str(line.total) if line.total is not None else "—",
             "Billable" if line.billable else "Excluded") for line in summary.lines]
    footer = [f"Subtotal: {summary.subtotal}",
              f"Discount ({data.discount_percent}%): {summary.discount}",
              f"Tax after discount ({data.tax_percent}%): {summary.tax}",
              f"TOTAL: {summary.total}"]
    if summary.unpriced_ids:
        footer.append("INCOMPLETE — missing prices: " + ", ".join(summary.unpriced_ids))
    footer.append("Demonstration quotation; currency and commercial terms require client approval.")
    return _pdf(path, "KÜCHE7 | CUSTOMER QUOTATION",
                f"{project.name}  /  {data.customer_name or 'Customer pending'}  /  {data.quotation_number or 'No number'}  /  {data.quotation_date}",
                ("ID", "Item", "Category", "Qty", "Unit price", "Total", "Status"), rows, footer)
