"""Create a revisioned cabinet and its Price Master rule in one desktop dialog."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSpinBox,
                               QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from ..catalogue import FINISHES, CatalogueItem, register_custom_items, unregister_custom_item
from ..costing import PricingRule, cost_cabinet, selling_price
from ..custom_catalogue import BASE_TEMPLATES, create_custom_revision
from ..models import Cabinet, HardwareAssignment
from ..price_master import CataloguePriceRule, PriceMaster


class CabinetLibraryDialog(QDialog):
    def __init__(self, items: list[CatalogueItem], master: PriceMaster,
                 selected: CatalogueItem | None = None,
                 selected_rule: CataloguePriceRule | None = None, parent=None) -> None:
        super().__init__(parent)
        self.items = items
        self.master = master
        self.selected = selected
        self.setWindowTitle("Edit Cabinet" if selected and selected.product_id else "Add Cabinet")
        self.resize(690, 780)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        details = QWidget()
        form = QFormLayout(details)
        self.product_id_edit = QLineEdit(selected.product_id if selected else "")
        self.product_id_edit.setPlaceholderText("Unique product ID, e.g. KITCHEN_BASE_A")
        self.product_id_edit.setReadOnly(bool(selected and selected.product_id))
        self.name_edit = QLineEdit(selected.name if selected else "")
        self.template_combo = QComboBox()
        for template in BASE_TEMPLATES.values():
            self.template_combo.addItem(f"{template.name} — {template.category}", template.type_id)
        self.category_label = QLabel()
        self.front_label = QLabel()
        self.width_spin = self._spin(300, 3000, selected.width if selected else 900)
        self.height_spin = self._spin(300, 3000, selected.height if selected else 720)
        self.depth_spin = self._spin(200, 1200, selected.depth if selected else 600)
        self.thickness_spin = self._spin(10, 50, selected.board_thickness if selected else 18)
        self.min_width_spin = self._spin(300, 3000, selected.min_width if selected else 300)
        self.max_width_spin = self._spin(300, 3000, selected.max_width if selected else 3000)
        self.min_height_spin = self._spin(300, 3000, selected.min_height if selected else 300)
        self.max_height_spin = self._spin(300, 3000, selected.max_height if selected else 3000)
        self.min_depth_spin = self._spin(200, 1200, selected.min_depth if selected else 200)
        self.max_depth_spin = self._spin(200, 1200, selected.max_depth if selected else 1200)
        self.door_spin = self._spin(0, 6, selected.door_count if selected else 2)
        self.drawer_spin = self._spin(0, 8, selected.drawer_count if selected else 0)
        self.shelf_spin = self._spin(0, 10, selected.shelf_count if selected else 1)
        self.finish_combo = QComboBox()
        self.finish_combo.addItems(FINISHES)
        self.finish_combo.setCurrentText((selected.default_finish or selected.supported_finishes[0]) if selected else "Cashmere")
        self.handle_spin = self._spin(0, 20, selected.hardware_defaults.get("handle_bar", 0) if selected else 0)
        for label, widget in (
            ("Product ID", self.product_id_edit), ("Cabinet name", self.name_edit),
            ("Existing construction template", self.template_combo),
            ("Category", self.category_label), ("Front type", self.front_label),
            ("Default width (mm)", self.width_spin), ("Default height (mm)", self.height_spin),
            ("Default depth (mm)", self.depth_spin), ("Board thickness (mm)", self.thickness_spin),
            ("Width range (mm)", self._range_widget(self.min_width_spin, self.max_width_spin)),
            ("Height range (mm)", self._range_widget(self.min_height_spin, self.max_height_spin)),
            ("Depth range (mm)", self._range_widget(self.min_depth_spin, self.max_depth_spin)),
            ("Doors", self.door_spin), ("Drawers", self.drawer_spin),
            ("Shelves", self.shelf_spin), ("Default board finish", self.finish_combo),
            ("Optional bar handles", self.handle_spin),
        ):
            form.addRow(label, widget)
        form.addRow(QLabel("Existing illustrative construction rules only. Built-in templates are not changed."))
        self.tabs.addTab(details, "1  Details")

        pricing = QWidget()
        price_form = QFormLayout(pricing)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(("Calculated", "Fixed"))
        self.currency_edit = QLineEdit("INR")
        self.fixed_edit = QLineEdit()
        self.fixed_edit.setPlaceholderText("Exact variant selling price")
        self.margin_combo = QComboBox()
        self.margin_combo.addItems(("Markup on cost", "Gross margin on sale"))
        self.percent_edit = QLineEdit("20")
        self.approved_check = QCheckBox("Mark this pricing rule approved for this local demo")
        self.approved_check.setChecked(False)
        if selected_rule:
            self.mode_combo.setCurrentText("Fixed" if selected_rule.mode == "fixed" else "Calculated")
            self.currency_edit.setText(selected_rule.currency)
            self.fixed_edit.setText(selected_rule.fixed_price)
            self.margin_combo.setCurrentIndex(1 if selected_rule.gross_margin_percent else 0)
            self.percent_edit.setText(selected_rule.gross_margin_percent or selected_rule.markup_percent)
            self.approved_check.setChecked(selected_rule.status == "approved")
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(210)
        for label, widget in (("Pricing method", self.mode_combo), ("Currency", self.currency_edit),
                              ("Fixed price", self.fixed_edit), ("Calculated rule", self.margin_combo),
                              ("Percentage", self.percent_edit), ("Approval", self.approved_check),
                              ("Cost and matched Price Master references", self.preview)):
            price_form.addRow(label, widget)
        price_form.addRow(QLabel("INCOMPLETE means approved material or hardware rates are missing. No default client prices ship."))
        self.tabs.addTab(pricing, "2  Pricing")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._save_clicked)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        if selected:
            self.template_combo.setCurrentIndex(max(0, self.template_combo.findData(selected.template_id or selected.type_id)))
        self.template_combo.currentIndexChanged.connect(self._template_changed)
        self.mode_combo.currentIndexChanged.connect(self._pricing_changed)
        for control in (self.width_spin, self.height_spin, self.depth_spin, self.thickness_spin,
                        self.door_spin, self.drawer_spin, self.shelf_spin, self.handle_spin):
            control.valueChanged.connect(self.refresh_preview)
        self.finish_combo.currentIndexChanged.connect(self.refresh_preview)
        self.currency_edit.textChanged.connect(self.refresh_preview)
        self.percent_edit.textChanged.connect(self.refresh_preview)
        self.fixed_edit.textChanged.connect(self.refresh_preview)
        self.approved_check.toggled.connect(self.refresh_preview)
        self.margin_combo.currentIndexChanged.connect(self.refresh_preview)
        self._template_changed()
        self._pricing_changed()

    @staticmethod
    def _spin(low: int, high: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        return spin

    @staticmethod
    def _range_widget(low: QSpinBox, high: QSpinBox) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(low)
        layout.addWidget(QLabel("to"))
        layout.addWidget(high)
        return widget

    def _template_changed(self) -> None:
        template = BASE_TEMPLATES[self.template_combo.currentData()]
        self.category_label.setText(template.category)
        self.front_label.setText(template.front_style.replace("_", " ").title())
        if not self.selected or not self.selected.product_id:
            for spin, value in ((self.width_spin, template.width), (self.height_spin, template.height),
                                (self.depth_spin, template.depth), (self.door_spin, template.door_count),
                                (self.drawer_spin, template.drawer_count), (self.shelf_spin, template.shelf_count)):
                spin.setValue(value)
        self.door_spin.setEnabled(template.front_style not in ("drawers", "open"))
        self.drawer_spin.setEnabled(template.front_style == "drawers")
        if template.front_style in ("drawers", "open"):
            self.door_spin.setValue(0)
        if template.front_style != "drawers":
            self.drawer_spin.setValue(0)
        self.refresh_preview()

    def _pricing_changed(self) -> None:
        fixed = self.mode_combo.currentText() == "Fixed"
        self.fixed_edit.setEnabled(fixed)
        self.margin_combo.setEnabled(not fixed)
        self.percent_edit.setEnabled(not fixed)
        self.refresh_preview()

    def refresh_preview(self, *_args) -> None:
        if not self.template_combo.currentData():
            return
        template = BASE_TEMPLATES[self.template_combo.currentData()]
        cabinet = Cabinet(width=self.width_spin.value(), height=self.height_spin.value(),
                          depth=self.depth_spin.value(), board_thickness=self.thickness_spin.value(),
                          door_count=self.door_spin.value(), drawer_count=self.drawer_spin.value(),
                          shelf_count=self.shelf_spin.value(), material=self.finish_combo.currentText(),
                          cabinet_id="PREVIEW", cabinet_type_id=template.type_id)
        try:
            assignments = ([HardwareAssignment("PREVIEW-H", "PREVIEW", "handle_bar", self.handle_spin.value())]
                           if self.handle_spin.value() else [])
            cost = cost_cabinet(cabinet, self.master, hardware_assignments=assignments,
                                currency=self.currency_edit.text().strip().upper(),
                                as_of=date.today().isoformat())
            lines = [f"{line.component}: {line.quantity} {line.unit} × {line.rate} = {line.amount} {line.currency} [{line.source_id}]"
                     for line in cost.lines]
            lines.extend(f"MISSING: {reason}" for reason in cost.missing)
            rule = PricingRule(mode="fixed" if self.mode_combo.currentText() == "Fixed" else "calculated",
                               approved=self.approved_check.isChecked(), fixed_price=self.fixed_edit.text().strip(),
                               markup_percent=self.percent_edit.text().strip() if self.margin_combo.currentIndex() == 0 else "",
                               gross_margin_percent=self.percent_edit.text().strip() if self.margin_combo.currentIndex() == 1 else "")
            price, reason = selling_price(cost, rule, currency=self.currency_edit.text().strip().upper())
            lines.append(f"Illustrative BOM cost: {cost.total if cost.total is not None else 'INCOMPLETE'}")
            lines.append(f"Draft selling price: {price if price is not None else 'INCOMPLETE'} {reason}")
            self.preview.setPlainText("\n".join(lines))
        except ValueError as error:
            self.preview.setPlainText(f"INCOMPLETE: {error}")

    def build(self) -> tuple[CatalogueItem, CataloguePriceRule]:
        template_id = self.template_combo.currentData()
        item = create_custom_revision(
            self.items, product_id=self.product_id_edit.text().strip(), name=self.name_edit.text().strip(),
            template_id=template_id, width=self.width_spin.value(), height=self.height_spin.value(),
            depth=self.depth_spin.value(), board_thickness=self.thickness_spin.value(),
            door_count=self.door_spin.value(), drawer_count=self.drawer_spin.value(),
            shelf_count=self.shelf_spin.value(), default_finish=self.finish_combo.currentText(),
            min_width=self.min_width_spin.value(), max_width=self.max_width_spin.value(),
            min_height=self.min_height_spin.value(), max_height=self.max_height_spin.value(),
            min_depth=self.min_depth_spin.value(), max_depth=self.max_depth_spin.value(),
            handle_quantity=self.handle_spin.value())
        fixed = self.mode_combo.currentText() == "Fixed"
        rule = CataloguePriceRule(
            rule_id=f"LIB-{item.product_id.upper()}-V{item.revision}", type_id=item.type_id,
            mode="fixed" if fixed else "calculated", currency=self.currency_edit.text().strip().upper(),
            effective_date=date.today().isoformat(),
            status="approved" if self.approved_check.isChecked() else "draft",
            material=item.default_finish,
            width_mm=item.width if fixed else 0, height_mm=item.height if fixed else 0,
            depth_mm=item.depth if fixed else 0, fixed_price=self.fixed_edit.text().strip() if fixed else "",
            markup_percent=self.percent_edit.text().strip() if not fixed and self.margin_combo.currentIndex() == 0 else "",
            gross_margin_percent=self.percent_edit.text().strip() if not fixed and self.margin_combo.currentIndex() == 1 else "")
        return item, rule

    def _save_clicked(self) -> None:
        item = None
        try:
            item, rule = self.build()
            register_custom_items([item])
            rule.validate()
        except ValueError as error:
            QMessageBox.warning(self, "Cabinet library", str(error))
            return
        finally:
            if item is not None:
                unregister_custom_item(item.type_id)
        self.accept()
