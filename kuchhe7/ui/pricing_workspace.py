"""Price master and draft costing controls inside the existing documents workspace."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..costing import PricingRule, cost_cabinet, selling_price
from ..price_master import CATEGORIES, UNITS, PriceRecord, load_price_master, save_price_master


class PricingWorkspace:
    """Two pages managed by DocumentsWorkspace; all mutations mark the project dirty."""

    def __init__(self, on_change) -> None:
        self.project = None
        self._on_change = on_change
        self.master_page = QWidget()
        self.cost_page = QWidget()
        self._build_master()
        self._build_cost()

    def _build_master(self) -> None:
        layout = QVBoxLayout(self.master_page)
        layout.addWidget(QLabel("Rates are empty until entered or imported. Approval is user-declared; client validation remains required."))
        self.master_table = QTableWidget(0, 9)
        self.master_table.setHorizontalHeaderLabels(
            ["ID", "Category", "Match key", "Description", "Unit", "Rate", "Currency", "Effective", "Status"])
        self.master_table.setAlternatingRowColors(True)
        self.master_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.master_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.master_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.master_table.horizontalHeader().setStretchLastSection(True)
        self.master_table.itemSelectionChanged.connect(self._load_selected_record)
        layout.addWidget(self.master_table, 2)
        forms = QHBoxLayout()
        left_form, right_form = QFormLayout(), QFormLayout()
        forms.addLayout(left_form); forms.addLayout(right_form)
        self.record_id = QLineEdit()
        self.category = QComboBox(); self.category.addItems(CATEGORIES)
        self.match_key = QLineEdit()
        self.description = QLineEdit()
        self.unit = QComboBox(); self.unit.addItems(UNITS)
        self.rate = QLineEdit(); self.rate.setPlaceholderText("Blank until supplied")
        self.currency = QLineEdit(); self.currency.setPlaceholderText("ISO code, e.g. INR")
        self.effective_date = QLineEdit(); self.effective_date.setPlaceholderText("YYYY-MM-DD")
        self.status = QComboBox(); self.status.addItems(["draft", "approved"])
        self.thickness = QLineEdit(); self.thickness.setPlaceholderText("Required for Board, mm")
        self.sheet_length = QLineEdit(); self.sheet_length.setPlaceholderText("Optional, mm")
        self.sheet_width = QLineEdit(); self.sheet_width.setPlaceholderText("Optional, mm")
        self.specification = QLineEdit(); self.specification.setPlaceholderText("Required for approved Board records")
        for index, (label, widget) in enumerate((("Stable ID", self.record_id), ("Category", self.category),
                              ("Matches BOM material / hardware type", self.match_key),
                              ("Description", self.description), ("Unit", self.unit),
                              ("Rate", self.rate), ("Currency", self.currency),
                              ("Effective date", self.effective_date), ("Status", self.status),
                              ("Board thickness", self.thickness), ("Sheet length", self.sheet_length),
                              ("Sheet width", self.sheet_width), ("Material specification", self.specification))):
            (left_form if index % 2 == 0 else right_form).addRow(label, widget)
        layout.addLayout(forms)
        buttons = QHBoxLayout()
        for label, callback in (("Add / update record", self.apply_record), ("Remove record", self.remove_record),
                                ("Import JSON / CSV / XLSX", self.import_master),
                                ("Save master JSON", self.export_master)):
            button = QPushButton(label); button.clicked.connect(callback); buttons.addWidget(button)
        layout.addLayout(buttons)
        self.master_message = QLabel("Board costing uses approved m2 rates by material and thickness; hardware uses approved each rates.")
        layout.addWidget(self.master_message)

    def _build_cost(self) -> None:
        layout = QVBoxLayout(self.cost_page)
        layout.addWidget(QLabel("Draft component cost from the current illustrative BOM. No wastage, labour or margin is assumed."))
        self.cost_cabinet = QLabel("No cabinet selected")
        self.cost_cabinet.setObjectName("canvasTitle")
        layout.addWidget(self.cost_cabinet)
        self.cost_table = QTableWidget(0, 7)
        self.cost_table.setHorizontalHeaderLabels(["Component / charge", "Rate ID", "Calculation", "Qty / units", "Rate", "Amount", "Currency"])
        self.cost_table.setAlternatingRowColors(True)
        self.cost_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cost_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.cost_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.cost_table, 2)
        self.cost_total = QLabel()
        self.cost_total.setObjectName("canvasTitle")
        layout.addWidget(self.cost_total)
        self.cost_warning = QLabel()
        self.cost_warning.setWordWrap(True)
        self.cost_warning.setStyleSheet("color: #A03E35; font-weight: 600;")
        layout.addWidget(self.cost_warning)
        form = QFormLayout()
        self.pricing_mode = QComboBox(); self.pricing_mode.addItems(["manual", "fixed", "calculated"])
        self.rule_approved = QCheckBox("User marks this pricing rule approved")
        self.fixed_price = QLineEdit(); self.fixed_price.setPlaceholderText("Approved fixed selling price")
        self.markup = QLineEdit(); self.markup.setPlaceholderText("Use markup OR gross margin")
        self.gross_margin = QLineEdit(); self.gross_margin.setPlaceholderText("Must be below 100%")
        self.charges = QLineEdit(); self.charges.setPlaceholderText("Optional: rate_ID=quantity, rate_ID=quantity")
        for label, widget in (("Quotation pricing mode", self.pricing_mode), ("Approval", self.rule_approved),
                              ("Fixed selling price", self.fixed_price), ("Markup % on cost", self.markup),
                              ("Gross margin % of sale", self.gross_margin),
                              ("Explicit optional charges", self.charges)):
            form.addRow(label, widget)
        layout.addLayout(form)
        button = QPushButton("Apply draft pricing rule")
        button.clicked.connect(self.apply_rule)
        layout.addWidget(button)
        self.sell_preview = QLabel()
        layout.addWidget(self.sell_preview)
        layout.addWidget(QLabel("Draft only. An issued quotation snapshot in the Quotation tab remains frozen."))

    def set_project(self, project) -> None:
        self.project = project
        self.refresh()

    def refresh(self) -> None:
        if self.project is None:
            return
        selected_id = self.record_id.text().strip()
        self.master_table.blockSignals(True)
        self.master_table.setRowCount(len(self.project.price_master.records))
        for row, record in enumerate(self.project.price_master.records):
            values = (record.record_id, record.category, record.match_key, record.description,
                      record.unit, record.rate, record.currency, record.effective_date, record.status)
            for col, value in enumerate(values):
                self.master_table.setItem(row, col, QTableWidgetItem(str(value)))
            if record.record_id == selected_id:
                self.master_table.selectRow(row)
        self.master_table.blockSignals(False)
        cabinet = self.project.selected_cabinet
        if cabinet is None:
            self.cost_cabinet.setText("No cabinet selected")
            self.cost_table.setRowCount(0)
            self.cost_total.setText("")
            self.cost_warning.setText("")
            return
        self.cost_cabinet.setText(f"{cabinet.cabinet_id} — {cabinet.width} × {cabinet.height} × {cabinet.depth} mm")
        rule = self.project.quotation.pricing_rules.get(cabinet.cabinet_id, PricingRule())
        self.pricing_mode.setCurrentText(rule.mode)
        self.rule_approved.setChecked(rule.approved)
        self.fixed_price.setText(rule.fixed_price)
        self.markup.setText(rule.markup_percent)
        self.gross_margin.setText(rule.gross_margin_percent)
        self.charges.setText(", ".join(f"{key}={value}" for key, value in rule.charge_quantities.items()))
        cost = cost_cabinet(cabinet, self.project.price_master,
                            hardware_assignments=self.project.hardware_assignments,
                            charge_quantities=rule.charge_quantities,
                            currency=self.project.quotation.currency,
                            as_of=self.project.quotation.quotation_date)
        self.cost_table.setRowCount(len(cost.lines))
        for row, line in enumerate(cost.lines):
            for col, value in enumerate((line.component, line.source_id, line.calculation,
                                         str(line.quantity), str(line.rate), str(line.amount), line.currency)):
                self.cost_table.setItem(row, col, QTableWidgetItem(value))
        self.cost_total.setText(f"BOM rate coverage {cost.status} — component subtotal {cost.total if cost.total is not None else 'pending'} {cost.currency}")
        self.cost_warning.setText("\n".join(cost.missing) if cost.missing else "BOM-based component subtotal; omitted categories are not assumed.")
        price, reason = selling_price(cost, rule, currency=self.project.quotation.currency)
        self.sell_preview.setText(f"Draft selling price: {price} {self.project.quotation.currency}" if price is not None
                                  else f"Draft selling price incomplete: {reason}")

    def _load_selected_record(self) -> None:
        row = self.master_table.currentRow()
        if self.project is None or row < 0 or row >= len(self.project.price_master.records):
            return
        record = self.project.price_master.records[row]
        for widget, value in ((self.record_id, record.record_id), (self.match_key, record.match_key),
                              (self.description, record.description), (self.rate, record.rate),
                              (self.currency, record.currency), (self.effective_date, record.effective_date),
                              (self.thickness, record.thickness_mm), (self.sheet_length, record.sheet_length_mm),
                              (self.sheet_width, record.sheet_width_mm),
                              (self.specification, record.specification)):
            widget.setText(value)
        self.category.setCurrentText(record.category)
        self.unit.setCurrentText(record.unit)
        self.status.setCurrentText(record.status)

    def apply_record(self) -> None:
        if self.project is None:
            return
        record = PriceRecord(self.record_id.text().strip(), self.category.currentText(), self.match_key.text().strip(),
                             self.description.text().strip(), self.unit.currentText(), self.rate.text().strip(),
                             self.currency.text().strip(), self.effective_date.text().strip(), self.status.currentText(),
                             self.thickness.text().strip(), self.sheet_length.text().strip(),
                             self.sheet_width.text().strip(), self.specification.text().strip())
        try:
            candidate = deepcopy(self.project.price_master)
            candidate.records = [row for row in candidate.records if row.record_id != record.record_id] + [record]
            candidate.validate()
        except ValueError as error:
            self.master_message.setText(str(error)); return
        self.project.price_master = candidate
        self._on_change(); self.refresh()
        self.master_message.setText(f"Saved rate record {record.record_id} in this project. Save the project to persist it.")

    def remove_record(self) -> None:
        if self.project is None:
            return
        record_id = self.record_id.text().strip()
        if not any(row.record_id == record_id for row in self.project.price_master.records):
            self.master_message.setText("Select a price record first."); return
        self.project.price_master.records = [row for row in self.project.price_master.records if row.record_id != record_id]
        self.record_id.clear(); self._on_change(); self.refresh()

    def import_master(self) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getOpenFileName(self.master_page, "Import price master", "",
                                               "Price lists (*.json *.csv *.xlsx)")
        if not path:
            return
        try:
            candidate = load_price_master(path)
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.warning(self.master_page, "Price list import", str(error)); return
        if QMessageBox.question(self.master_page, "Replace project price master",
                                f"Replace {len(self.project.price_master.records)} existing records with {len(candidate.records)} imported records?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.project.price_master = candidate
        self._on_change(); self.refresh()
        self.master_message.setText(f"Imported {len(candidate.records)} records from {Path(path).name}.")

    def export_master(self) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getSaveFileName(self.master_page, "Save price master", "Kuche7-price-master.json",
                                              "JSON (*.json)")
        if path:
            try:
                save_price_master(self.project.price_master, path)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self.master_page, "Price master save", str(error))

    def apply_rule(self) -> None:
        if self.project is None or self.project.selected_cabinet is None:
            return
        try:
            charges = {}
            for entry in self.charges.text().split(","):
                if entry.strip():
                    key, value = entry.split("=", 1)
                    charges[key.strip()] = value.strip()
            rule = PricingRule(self.pricing_mode.currentText(), self.rule_approved.isChecked(),
                               self.fixed_price.text().strip(), self.markup.text().strip(),
                               self.gross_margin.text().strip(), charges)
            rule.validate()
        except (ValueError, TypeError) as error:
            self.cost_warning.setText(str(error)); return
        self.project.quotation.pricing_rules[self.project.selected_cabinet_id] = rule
        self._on_change(); self.refresh()
