"""BOM review and customer quotation workspace for the active project."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..bom import generate_project_bom
from ..document_exports import (export_bom_pdf, export_bom_template_xlsx,
                                 export_issued_quotation_pdf, export_issued_quotation_xlsx,
                                 export_quotation_pdf, export_quotation_xlsx)
from ..quotation import calculate_quotation
from ..quotation import issue_quotation_snapshot
from .pricing_workspace import PricingWorkspace


def _read_only_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().hide()
    return table


class DocumentsWorkspace(QWidget):
    def __init__(self, on_change, parent=None) -> None:
        super().__init__(parent)
        self.project = None
        self._on_change = on_change
        self._loading = False
        self.bom_template_path: Path | None = None
        outer = QVBoxLayout(self)
        title = QLabel("BOM & CUSTOMER QUOTATION")
        title.setObjectName("canvasTitle")
        outer.addWidget(title)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        self._build_bom()
        self._build_quote()
        self.pricing_workspace = PricingWorkspace(lambda: (on_change(), self.refresh()))
        self.tabs.addTab(self.pricing_workspace.master_page, "Price Setup")
        self.tabs.addTab(self.pricing_workspace.cost_page, "Cost Breakdown")

    def _build_bom(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Illustrative component dimensions and quantities — not factory approved."))
        self.bom_table = _read_only_table(["Cabinet", "Component", "Length mm", "Width mm", "Thickness mm",
                                            "Material", "Qty", "Furniture type"])
        layout.addWidget(self.bom_table)
        actions = QHBoxLayout()
        for label, callback in (("Export BOM Excel", self.export_bom_excel),
                                ("Export BOM PDF", self.export_bom_pdf)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        template_button = QPushButton("Choose Excel template…")
        template_button.clicked.connect(self.choose_bom_template)
        actions.addWidget(template_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.template_label = QLabel("Default demonstration layout")
        layout.addWidget(self.template_label)
        self.tabs.addTab(page, "BOM Review")

    def _build_quote(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.customer_edit = QLineEdit()
        self.number_edit = QLineEdit()
        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        self.discount_edit = QLineEdit()
        self.tax_edit = QLineEdit()
        self.currency_edit = QLineEdit()
        self.currency_edit.setPlaceholderText("Three-letter currency code")
        for label, widget, key in (
            ("Customer", self.customer_edit, "customer_name"),
            ("Quotation number", self.number_edit, "quotation_number"),
            ("Date", self.date_edit, "quotation_date"),
            ("Discount %", self.discount_edit, "discount_percent"),
            ("Tax % (after discount)", self.tax_edit, "tax_percent"),
            ("Currency", self.currency_edit, "currency"),
        ):
            form.addRow(label, widget)
            widget.editingFinished.connect(lambda key=key, widget=widget: self._update_field(key, widget))
        layout.addLayout(form)
        layout.addWidget(QLabel("Draft prices resolve from approved Price Setup rules. Manual prices are explicit exceptions. Appliances require billable selection; props never appear here."))
        self.quote_table = _read_only_table(["ID", "Item", "Category", "Qty", "Billable", "Unit price", "Line total", "Pricing mode"])
        quote_header = self.quote_table.horizontalHeader()
        quote_header.setStretchLastSection(False)
        quote_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((65, 280, 150, 55, 170, 130, 135, 115)):
            self.quote_table.setColumnWidth(column, width)
        quote_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.quote_table)
        self.totals_label = QLabel()
        self.totals_label.setObjectName("canvasTitle")
        layout.addWidget(self.totals_label)
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: #A03E35; font-weight: 600;")
        layout.addWidget(self.warning_label)
        self.issued_label = QLabel("No issued quotation snapshot. Draft values remain live.")
        layout.addWidget(self.issued_label)
        actions = QHBoxLayout()
        for label, callback in (("Export Quotation Excel", self.export_quote_excel),
                                ("Export Quotation PDF", self.export_quote_pdf)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.issued_excel_button = QPushButton("Export issued Excel")
        self.issued_excel_button.clicked.connect(self.export_issued_quote_excel)
        actions.addWidget(self.issued_excel_button)
        self.issued_pdf_button = QPushButton("Export issued PDF")
        self.issued_pdf_button.clicked.connect(self.export_issued_quote_pdf)
        actions.addWidget(self.issued_pdf_button)
        actions.addStretch()
        issue_button = QPushButton("Record issued snapshot…")
        issue_button.clicked.connect(self._issue_snapshot)
        actions.addWidget(issue_button)
        layout.addLayout(actions)
        self.tabs.addTab(page, "Customer Quotation")

    def set_project(self, project) -> None:
        self.project = project
        self.pricing_workspace.set_project(project)
        self.refresh()

    def refresh(self) -> None:
        if self.project is None:
            return
        self._loading = True
        try:
            data = self.project.quotation
            for widget, value in ((self.customer_edit, data.customer_name),
                                  (self.number_edit, data.quotation_number),
                                  (self.date_edit, data.quotation_date),
                                  (self.discount_edit, data.discount_percent),
                                  (self.tax_edit, data.tax_percent),
                                  (self.currency_edit, data.currency)):
                if not widget.hasFocus():
                    widget.setText(str(value))
            items = generate_project_bom(self.project)
            self.bom_table.setRowCount(len(items))
            for row, item in enumerate(items):
                for col, value in enumerate((item.cabinet_id, item.name, item.length_mm,
                                             item.width_mm, item.thickness_mm, item.material,
                                             item.quantity, item.cabinet_type)):
                    display = (f"{value:.2f}".rstrip("0").rstrip(".")
                               if col in (2, 3, 4) and isinstance(value, float) else str(value))
                    cell = QTableWidgetItem(display)
                    if col in (2, 3, 4, 6):
                        cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.bom_table.setItem(row, col, cell)
            summary = calculate_quotation(self.project)
            self.quote_table.setRowCount(len(summary.lines))
            for row, line in enumerate(summary.lines):
                for col, value in enumerate((line.item_id, line.description, line.category, line.quantity)):
                    self.quote_table.setItem(row, col, QTableWidgetItem(str(value)))
                if line.category == "Furniture":
                    self.quote_table.setItem(row, 4, QTableWidgetItem("Yes"))
                else:
                    check = QCheckBox("Supplied / billable")
                    check.setChecked(line.billable)
                    check.toggled.connect(lambda checked, item_id=line.item_id: self._set_billable(item_id, checked))
                    self.quote_table.setCellWidget(row, 4, check)
                manual_edit = line.pricing_mode in ("unconfigured", "manual exception")
                price = QLineEdit(data.unit_prices.get(line.item_id, "") if manual_edit
                                  else (str(line.unit_price) if line.unit_price is not None else ""))
                price.setPlaceholderText("Manual exception" if manual_edit else "Price pending")
                price.setEnabled(manual_edit)
                price.editingFinished.connect(lambda item_id=line.item_id, field=price: self._set_price(item_id, field.text()))
                self.quote_table.setCellWidget(row, 5, price)
                self.quote_table.setItem(row, 6, QTableWidgetItem(str(line.total) if line.total is not None else "—"))
                self.quote_table.setItem(row, 7, QTableWidgetItem(line.pricing_mode.title()))
            self.totals_label.setText(
                f"LIVE DRAFT — Subtotal {summary.subtotal}    Discount {summary.discount}    "
                f"Tax {summary.tax}    Total {summary.total}"
            )
            self.warning_label.setText(
                "INCOMPLETE — " + "; ".join(
                    (["prices missing for " + ", ".join(summary.unpriced_ids)] if summary.unpriced_ids else [])
                    + list(summary.incomplete_reasons))
                if summary.unpriced_ids or summary.incomplete_reasons
                else "Prices are demonstration inputs; currency and terms require client approval."
            )
            snapshot = data.issued_snapshot
            self.issued_label.setText(
                f"Issued snapshot {snapshot['quotation_number']}: {snapshot['total']} {snapshot.get('currency', '')} — frozen"
                if snapshot else "No issued quotation snapshot. Draft values remain live.")
            self.issued_excel_button.setEnabled(snapshot is not None)
            self.issued_pdf_button.setEnabled(snapshot is not None)
            self.pricing_workspace.refresh()
        finally:
            self._loading = False

    def _update_field(self, key: str, widget: QLineEdit) -> None:
        if self._loading or self.project is None:
            return
        previous = getattr(self.project.quotation, key)
        value = widget.text().strip()
        if value == previous:
            return
        setattr(self.project.quotation, key, value)
        try:
            self.project.quotation.validate(self.project)
        except ValueError as error:
            setattr(self.project.quotation, key, previous)
            widget.setText(str(previous))
            self.warning_label.setText(str(error))
            return
        self._on_change()
        self.refresh()

    def _set_price(self, item_id: str, value: str) -> None:
        if self._loading or self.project is None:
            return
        prices = self.project.quotation.unit_prices
        previous = prices.get(item_id)
        value = value.strip()
        if value == (previous or ""):
            return
        if value:
            prices[item_id] = value
        else:
            prices.pop(item_id, None)
        try:
            self.project.quotation.validate(self.project)
        except ValueError as error:
            if previous is None:
                prices.pop(item_id, None)
            else:
                prices[item_id] = previous
            self.warning_label.setText(str(error))
            self.refresh()
            return
        self._on_change()
        self.refresh()

    def _set_billable(self, item_id: str, checked: bool) -> None:
        if self._loading or self.project is None:
            return
        ids = self.project.quotation.billable_product_ids
        if checked and item_id not in ids:
            ids.append(item_id)
        elif not checked and item_id in ids:
            ids.remove(item_id)
        self._on_change()
        self.refresh()

    def _export(self, title: str, suffix: str, callback) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, title, f"{self.project.name}-{title}.{suffix}",
                                              "Excel Workbook (*.xlsx)" if suffix == "xlsx" else "PDF (*.pdf)")
        if not path:
            return
        try:
            callback(self.project, path)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Document export", str(error))

    def export_bom_excel(self) -> None:
        self._export("BOM", "xlsx", lambda project, path: export_bom_template_xlsx(
            project, path, template_path=self.bom_template_path))

    def choose_bom_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select client BOM template", "", "Excel Workbook (*.xlsx)")
        if path:
            self.bom_template_path = Path(path)
            self.template_label.setText(f"Excel template: {self.bom_template_path.name}")

    def export_bom_pdf(self) -> None:
        self._export("BOM", "pdf", export_bom_pdf)

    def export_quote_excel(self) -> None:
        self._export("Quotation", "xlsx", export_quotation_xlsx)

    def export_quote_pdf(self) -> None:
        self._export("Quotation", "pdf", export_quotation_pdf)

    def export_issued_quote_excel(self) -> None:
        self._export("Issued Quotation", "xlsx", export_issued_quotation_xlsx)

    def export_issued_quote_pdf(self) -> None:
        self._export("Issued Quotation", "pdf", export_issued_quotation_pdf)

    def _issue_snapshot(self) -> None:
        if self.project is None:
            return
        replacing = self.project.quotation.issued_snapshot is not None
        prompt = ("Replace the existing issued snapshot with the current complete draft?"
                  if replacing else "Freeze the current complete quotation as an issued snapshot?")
        if QMessageBox.question(self, "Record issued quotation snapshot",
                                prompt + " Future edits will change only the draft.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            issue_quotation_snapshot(self.project)
        except ValueError as error:
            self.warning_label.setText(str(error)); return
        self._on_change()
        self.refresh()
