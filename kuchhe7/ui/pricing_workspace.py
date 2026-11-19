"""Price master and draft costing controls inside the existing documents workspace."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..catalogue import CATALOGUE, WARDROBE_CATALOGUE
from ..costing import PricingRule, cost_cabinet, selling_price
from ..price_master import (CATEGORIES, UNITS, CataloguePriceRule, PriceRecord,
                            load_price_master, save_price_master)
from ..quotation import resolve_cabinet_pricing_rule


class PricingWorkspace:
    """Two pages managed by DocumentsWorkspace; all mutations mark the project dirty."""

    def __init__(self, on_change, *, context_name: str = "project") -> None:
        self.project = None
        self._on_change = on_change
        self.context_name = context_name
        self.master_page = QTabWidget()
        self.rates_page = QWidget()
        self.cost_page = QWidget()
        self._build_master()
        self._build_catalogue_rules()
        self._build_cost()

    def _build_master(self) -> None:
        layout = QVBoxLayout(self.rates_page)
        layout.addWidget(QLabel("No rates are supplied by default. Enter or import rates; approval is user-declared and requires client validation."))
        self.master_table = QTableWidget(0, 11)
        self.master_table.setHorizontalHeaderLabels(
            ["ID", "Category", "Match key", "Description", "Rate unit", "Rate", "Currency", "Effective", "Status", "Purchase unit", "Selling unit"])
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
        self.purchase_unit = QComboBox(); self.purchase_unit.addItems(["", *UNITS])
        self.selling_unit = QComboBox(); self.selling_unit.addItems(["", *UNITS])
        for index, (label, widget) in enumerate((("Stable ID", self.record_id), ("Category", self.category),
                              ("Matches BOM material / hardware type", self.match_key),
                              ("Description", self.description), ("Unit", self.unit),
                              ("Rate", self.rate), ("Currency", self.currency),
                              ("Effective date", self.effective_date), ("Status", self.status),
                              ("Board thickness", self.thickness), ("Sheet length", self.sheet_length),
                              ("Sheet width", self.sheet_width), ("Material specification", self.specification),
                              ("Purchase unit (metadata)", self.purchase_unit),
                              ("Selling unit (metadata)", self.selling_unit))):
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
        self.master_page.addTab(self.rates_page, "Material & product rates")

    def _build_catalogue_rules(self) -> None:
        self.rules_page = QWidget()
        layout = QVBoxLayout(self.rules_page)
        layout.addWidget(QLabel("Company catalogue selling rules. Fixed prices match an exact size; calculated prices use the current illustrative BOM."))
        self.rules_table = QTableWidget(0, 9)
        self.rules_table.setHorizontalHeaderLabels(
            ["Rule ID", "Product ID", "Finish", "Mode", "Size mm", "Price / margin", "Currency", "Effective", "Status"])
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.horizontalHeader().setStretchLastSection(True)
        self.rules_table.itemSelectionChanged.connect(self._load_selected_catalogue_rule)
        layout.addWidget(self.rules_table, 2)
        form = QFormLayout()
        self.catalogue_rule_id = QLineEdit()
        self.catalogue_type = QComboBox()
        for item in (*CATALOGUE, *WARDROBE_CATALOGUE):
            self.catalogue_type.addItem(f"{item.name} ({item.type_id})", item.type_id)
        self.catalogue_finish = QComboBox()
        self.catalogue_finish.addItems(["Any supported finish", "Warm White", "Cashmere", "Natural Oak", "Walnut", "Graphite"])
        self.catalogue_mode = QComboBox(); self.catalogue_mode.addItems(["calculated", "fixed"])
        self.catalogue_currency = QLineEdit(); self.catalogue_currency.setPlaceholderText("INR")
        self.catalogue_date = QLineEdit(); self.catalogue_date.setPlaceholderText("YYYY-MM-DD")
        self.catalogue_status = QComboBox(); self.catalogue_status.addItems(["draft", "approved"])
        self.catalogue_width = QLineEdit(); self.catalogue_height = QLineEdit(); self.catalogue_depth = QLineEdit()
        self.catalogue_fixed = QLineEdit(); self.catalogue_markup = QLineEdit(); self.catalogue_margin = QLineEdit()
        self.catalogue_charges = QLineEdit(); self.catalogue_charges.setPlaceholderText("Optional rate_ID=quantity, ...")
        for label, widget in (("Rule ID", self.catalogue_rule_id), ("Furniture product", self.catalogue_type),
                              ("Finish", self.catalogue_finish), ("Mode", self.catalogue_mode),
                              ("Currency", self.catalogue_currency), ("Effective date", self.catalogue_date),
                              ("Approval status", self.catalogue_status), ("Exact width mm (fixed only)", self.catalogue_width),
                              ("Exact height mm (fixed only)", self.catalogue_height),
                              ("Exact depth mm (fixed only)", self.catalogue_depth),
                              ("Fixed selling price", self.catalogue_fixed), ("Markup %", self.catalogue_markup),
                              ("Gross margin %", self.catalogue_margin), ("Optional process charges", self.catalogue_charges)):
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        for label, callback in (("Add / update catalogue rule", self.apply_catalogue_rule),
                                ("Remove catalogue rule", self.remove_catalogue_rule)):
            button = QPushButton(label); button.clicked.connect(callback); buttons.addWidget(button)
        layout.addLayout(buttons)
        self.rule_message = QLabel("No selling rule is assumed until an approved rule is configured.")
        self.rule_message.setWordWrap(True)
        layout.addWidget(self.rule_message)
        self.master_page.addTab(self.rules_page, "Catalogue selling rules")

    def _build_cost(self) -> None:
        layout = QVBoxLayout(self.cost_page)
        layout.addWidget(QLabel("Draft component cost from the current illustrative BOM. No wastage, labour or margin is assumed."))
        self.cost_cabinet = QLabel("No cabinet selected")
        self.cost_cabinet.setObjectName("canvasTitle")
        layout.addWidget(self.cost_cabinet)
        self.cost_table = QTableWidget(0, 9)
        self.cost_table.setHorizontalHeaderLabels(["Component / charge", "Material / product key", "Specification", "Rate ID", "Calculation", "Qty / units", "Rate", "Amount", "Currency"])
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
        button = QPushButton("Apply cabinet pricing exception")
        button.clicked.connect(self.apply_rule)
        layout.addWidget(button)
        reset_button = QPushButton("Clear cabinet exception; use catalogue rule")
        reset_button.clicked.connect(self.clear_rule_override)
        layout.addWidget(reset_button)
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
                      record.unit, record.rate, record.currency, record.effective_date, record.status,
                      record.purchase_unit, record.selling_unit)
            for col, value in enumerate(values):
                self.master_table.setItem(row, col, QTableWidgetItem(str(value)))
            if record.record_id == selected_id:
                self.master_table.selectRow(row)
        self.master_table.blockSignals(False)
        selected_rule = self.catalogue_rule_id.text().strip()
        self.rules_table.blockSignals(True)
        self.rules_table.setRowCount(len(self.project.price_master.catalogue_rules))
        for row, rule in enumerate(self.project.price_master.catalogue_rules):
            size = (f"{rule.width_mm} x {rule.height_mm} x {rule.depth_mm}"
                    if rule.mode == "fixed" else "Any size")
            value = rule.fixed_price if rule.mode == "fixed" else (
                f"Markup {rule.markup_percent}%" if rule.markup_percent else f"Margin {rule.gross_margin_percent}%")
            for col, cell in enumerate((rule.rule_id, rule.type_id, rule.material or "Any", rule.mode,
                                        size, value, rule.currency, rule.effective_date, rule.status)):
                self.rules_table.setItem(row, col, QTableWidgetItem(str(cell)))
            if rule.rule_id == selected_rule:
                self.rules_table.selectRow(row)
        self.rules_table.blockSignals(False)
        cabinet = self.project.selected_cabinet
        if cabinet is None:
            self.cost_cabinet.setText("No cabinet selected")
            self.cost_table.setRowCount(0)
            self.cost_total.setText("")
            self.cost_warning.setText("")
            return
        self.cost_cabinet.setText(f"{cabinet.cabinet_id} — {cabinet.width} × {cabinet.height} × {cabinet.depth} mm")
        rule, source = resolve_cabinet_pricing_rule(self.project, cabinet)
        rule = rule or PricingRule()
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
            for col, value in enumerate((line.component, line.match_key, line.specification,
                                         line.source_id, line.calculation, str(line.quantity),
                                         str(line.rate), str(line.amount), line.currency)):
                self.cost_table.setItem(row, col, QTableWidgetItem(value))
        self.cost_total.setText(f"BOM rate coverage {cost.status} — component subtotal {cost.total if cost.total is not None else 'pending'} {cost.currency}")
        self.cost_warning.setText("\n".join(cost.missing) if cost.missing else "BOM-based component subtotal; omitted categories are not assumed.")
        price, reason = selling_price(cost, rule, currency=self.project.quotation.currency)
        self.sell_preview.setText(
            f"{source} — draft selling price: {price} {self.project.quotation.currency}" if price is not None
            else f"{source} — draft selling price incomplete: {reason}")

    @staticmethod
    def _parse_charges(raw: str) -> dict[str, str]:
        charges = {}
        for entry in raw.split(","):
            if entry.strip():
                key, value = entry.split("=", 1)
                charges[key.strip()] = value.strip()
        return charges

    def _load_selected_catalogue_rule(self) -> None:
        row = self.rules_table.currentRow()
        if self.project is None or row < 0 or row >= len(self.project.price_master.catalogue_rules):
            return
        rule = self.project.price_master.catalogue_rules[row]
        for widget, value in ((self.catalogue_rule_id, rule.rule_id), (self.catalogue_currency, rule.currency),
                              (self.catalogue_date, rule.effective_date), (self.catalogue_width, rule.width_mm or ""),
                              (self.catalogue_height, rule.height_mm or ""), (self.catalogue_depth, rule.depth_mm or ""),
                              (self.catalogue_fixed, rule.fixed_price), (self.catalogue_markup, rule.markup_percent),
                              (self.catalogue_margin, rule.gross_margin_percent),
                              (self.catalogue_charges, ", ".join(f"{key}={value}" for key, value in rule.charge_quantities.items()))):
            widget.setText(str(value))
        self.catalogue_type.setCurrentIndex(self.catalogue_type.findData(rule.type_id))
        self.catalogue_finish.setCurrentText(rule.material or "Any supported finish")
        self.catalogue_mode.setCurrentText(rule.mode)
        self.catalogue_status.setCurrentText(rule.status)

    def apply_catalogue_rule(self) -> None:
        if self.project is None:
            return
        try:
            rule = CataloguePriceRule(
                rule_id=self.catalogue_rule_id.text().strip(), type_id=self.catalogue_type.currentData(),
                mode=self.catalogue_mode.currentText(), currency=self.catalogue_currency.text().strip(),
                effective_date=self.catalogue_date.text().strip(), status=self.catalogue_status.currentText(),
                material="" if self.catalogue_finish.currentIndex() == 0 else self.catalogue_finish.currentText(),
                width_mm=int(self.catalogue_width.text() or 0), height_mm=int(self.catalogue_height.text() or 0),
                depth_mm=int(self.catalogue_depth.text() or 0), fixed_price=self.catalogue_fixed.text().strip(),
                markup_percent=self.catalogue_markup.text().strip(),
                gross_margin_percent=self.catalogue_margin.text().strip(),
                charge_quantities=self._parse_charges(self.catalogue_charges.text()))
            candidate = deepcopy(self.project.price_master)
            candidate.catalogue_rules = [item for item in candidate.catalogue_rules if item.rule_id != rule.rule_id] + [rule]
            candidate.validate()
        except (ValueError, TypeError) as error:
            self.rule_message.setText(str(error)); return
        self.project.price_master = candidate
        self._on_change(); self.refresh()
        self.rule_message.setText(f"Saved catalogue rule {rule.rule_id}. Save the project or company setup to persist it.")

    def remove_catalogue_rule(self) -> None:
        if self.project is None:
            return
        rule_id = self.catalogue_rule_id.text().strip()
        if not any(item.rule_id == rule_id for item in self.project.price_master.catalogue_rules):
            self.rule_message.setText("Select a catalogue rule first."); return
        self.project.price_master.catalogue_rules = [item for item in self.project.price_master.catalogue_rules
                                                       if item.rule_id != rule_id]
        self.catalogue_rule_id.clear(); self._on_change(); self.refresh()

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
        self.purchase_unit.setCurrentText(record.purchase_unit)
        self.selling_unit.setCurrentText(record.selling_unit)

    def apply_record(self) -> None:
        if self.project is None:
            return
        record = PriceRecord(self.record_id.text().strip(), self.category.currentText(), self.match_key.text().strip(),
                             self.description.text().strip(), self.unit.currentText(), self.rate.text().strip(),
                             self.currency.text().strip(), self.effective_date.text().strip(), self.status.currentText(),
                             self.thickness.text().strip(), self.sheet_length.text().strip(),
                             self.sheet_width.text().strip(), self.specification.text().strip(),
                             self.purchase_unit.currentText(), self.selling_unit.currentText())
        try:
            candidate = deepcopy(self.project.price_master)
            candidate.records = [row for row in candidate.records if row.record_id != record.record_id] + [record]
            candidate.validate()
        except ValueError as error:
            self.master_message.setText(str(error)); return
        self.project.price_master = candidate
        self._on_change(); self.refresh()
        self.master_message.setText(f"Updated rate record {record.record_id}. Save the {self.context_name} to persist it.")

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
            if Path(path).suffix.lower() in (".csv", ".xlsx"):
                candidate.catalogue_rules = deepcopy(self.project.price_master.catalogue_rules)
                candidate.validate()
                approved_currencies = {row.currency for row in candidate.records if row.status == "approved"}
                approved_currencies.update(row.currency for row in candidate.catalogue_rules if row.status == "approved")
                if len(approved_currencies) > 1:
                    raise ValueError("Imported rates conflict with approved catalogue rule currencies.")
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.warning(self.master_page, "Price list import", str(error)); return
        if QMessageBox.question(self.master_page, "Import price master",
                                f"Replace {len(self.project.price_master.records)} existing rate records with {len(candidate.records)} imported records? "
                                + ("Catalogue selling rules will be preserved." if Path(path).suffix.lower() in (".csv", ".xlsx")
                                   else "Catalogue selling rules will also be replaced from JSON."),
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
            charges = self._parse_charges(self.charges.text())
            rule = PricingRule(self.pricing_mode.currentText(), self.rule_approved.isChecked(),
                               self.fixed_price.text().strip(), self.markup.text().strip(),
                               self.gross_margin.text().strip(), charges)
            rule.validate()
        except (ValueError, TypeError) as error:
            self.cost_warning.setText(str(error)); return
        self.project.quotation.pricing_rules[self.project.selected_cabinet_id] = rule
        self._on_change(); self.refresh()

    def clear_rule_override(self) -> None:
        if self.project is None or self.project.selected_cabinet_id is None:
            return
        cabinet_id = self.project.selected_cabinet_id
        had_exception = cabinet_id in self.project.quotation.pricing_rules or cabinet_id in self.project.quotation.unit_prices
        self.project.quotation.pricing_rules.pop(cabinet_id, None)
        self.project.quotation.unit_prices.pop(cabinet_id, None)
        if had_exception:
            self._on_change(); self.refresh()
