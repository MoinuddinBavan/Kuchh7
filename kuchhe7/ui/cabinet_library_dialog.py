"""Create a revisioned cabinet and its Price Master rule in one desktop dialog."""

from __future__ import annotations

from datetime import date
from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QScrollArea, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from ..catalogue import FINISHES, CatalogueItem, register_custom_items, unregister_custom_item
from ..costing import PricingRule, cost_cabinet, selling_price
from ..construction import ConstructionProfile, synthetic_profile_for
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
        self.imported_profile = deepcopy(selected.construction_profile) if selected else None
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(("Legacy demonstration rules", "Synthetic Stage 8 profile"))
        if self.imported_profile is not None:
            self.profile_combo.addItem("Saved profile snapshot")
            self.profile_combo.setCurrentIndex(2)
        self.import_profile_button = QPushButton("Import profile JSON…")
        self.import_profile_button.clicked.connect(self._import_profile)
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
            ("Construction profile", self.profile_combo),
            ("Profile file", self.import_profile_button),
        ):
            form.addRow(label, widget)
        form.addRow(QLabel("Existing illustrative construction rules only. Built-in templates are not changed."))
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setWidget(details)
        self.tabs.addTab(details_scroll, "1  Details")

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
        self.cost_basis_combo = QComboBox()
        for label, basis in (("Finished panel area estimate", "finished_area"),
                             ("Cut panel area estimate", "cut_area"),
                             ("Sheet estimate (explicit yield)", "sheet_yield"),
                             ("Cabinet-only nesting sheets", "nesting_sheets")):
            self.cost_basis_combo.addItem(label, basis)
        self.material_wastage_edit = QLineEdit()
        self.edge_wastage_edit = QLineEdit()
        self.overhead_edit = QLineEdit()
        self.sheet_yield_edit = QLineEdit()
        self.sheet_kerf_edit = QLineEdit()
        self.sheet_margin_edit = QLineEdit()
        self.sheet_rotate_check = QCheckBox("Allow 90-degree rotation where grain permits")
        self.sheet_rotate_check.setChecked(True)
        if selected_rule:
            self.mode_combo.setCurrentText("Fixed" if selected_rule.mode == "fixed" else "Calculated")
            self.currency_edit.setText(selected_rule.currency)
            self.fixed_edit.setText(selected_rule.fixed_price)
            self.margin_combo.setCurrentIndex(1 if selected_rule.gross_margin_percent else 0)
            self.percent_edit.setText(selected_rule.gross_margin_percent or selected_rule.markup_percent)
            self.approved_check.setChecked(selected_rule.status == "approved")
            self.cost_basis_combo.setCurrentIndex(max(0, self.cost_basis_combo.findData(selected_rule.cost_basis)))
            self.material_wastage_edit.setText(selected_rule.material_wastage_percent)
            self.edge_wastage_edit.setText(selected_rule.edge_wastage_percent)
            self.overhead_edit.setText(selected_rule.overhead_percent)
            self.sheet_yield_edit.setText(selected_rule.sheet_yield_percent)
            self.sheet_kerf_edit.setText(selected_rule.sheet_kerf_mm)
            self.sheet_margin_edit.setText(selected_rule.sheet_margin_mm)
            self.sheet_rotate_check.setChecked(selected_rule.sheet_allow_rotation)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(210)
        for label, widget in (("Pricing method", self.mode_combo), ("Currency", self.currency_edit),
                              ("Fixed price", self.fixed_edit), ("Calculated rule", self.margin_combo),
                              ("Percentage", self.percent_edit), ("Approval", self.approved_check),
                              ("Material cost basis", self.cost_basis_combo),
                              ("Material wastage % (optional)", self.material_wastage_edit),
                              ("Edge wastage % (optional)", self.edge_wastage_edit),
                              ("Overhead % (optional)", self.overhead_edit),
                              ("Sheet yield % (sheet estimate)", self.sheet_yield_edit),
                              ("Kerf mm (nesting sheets)", self.sheet_kerf_edit),
                              ("Margin mm (nesting sheets)", self.sheet_margin_edit),
                              ("Nesting rotation", self.sheet_rotate_check),
                              ("Cost and matched Price Master references", self.preview)):
            price_form.addRow(label, widget)
        price_form.addRow(QLabel("INCOMPLETE means approved material or hardware rates are missing. No default client prices ship."))
        pricing_scroll = QScrollArea()
        pricing_scroll.setWidgetResizable(True)
        pricing_scroll.setWidget(pricing)
        self.tabs.addTab(pricing_scroll, "2  Pricing")
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
        self.profile_combo.currentIndexChanged.connect(self.refresh_preview)
        self.cost_basis_combo.currentIndexChanged.connect(self.refresh_preview)
        for control in (self.material_wastage_edit, self.edge_wastage_edit, self.overhead_edit,
                        self.sheet_yield_edit, self.sheet_kerf_edit, self.sheet_margin_edit):
            control.textChanged.connect(self.refresh_preview)
        self.sheet_rotate_check.toggled.connect(self.refresh_preview)
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

    def _import_profile(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import demonstration construction profile", "", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            profile = ConstructionProfile.from_dict(json.loads(Path(filename).read_text(encoding="utf-8")))
            self.imported_profile = profile.to_dict()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Construction profile", str(error))
            return
        if self.profile_combo.count() == 2:
            self.profile_combo.addItem("Imported profile snapshot")
        else:
            self.profile_combo.setItemText(2, "Imported profile snapshot")
        self.profile_combo.setCurrentIndex(2)
        self.refresh_preview()

    def _profile_data_for(self, cabinet: Cabinet) -> dict | None:
        choice = self.profile_combo.currentIndex()
        if choice == 0:
            return None
        if choice == 1:
            return synthetic_profile_for(cabinet).to_dict()
        if self.imported_profile is None:
            raise ValueError("Select a construction profile JSON file.")
        result = deepcopy(self.imported_profile)
        result["cabinet_type_id"] = cabinet.cabinet_type_id
        ConstructionProfile.from_dict(result).validate_for(cabinet)
        return result

    def _pricing_policy(self) -> PricingRule:
        return PricingRule(
            mode="fixed" if self.mode_combo.currentText() == "Fixed" else "calculated",
            approved=self.approved_check.isChecked(), fixed_price=self.fixed_edit.text().strip(),
            markup_percent=self.percent_edit.text().strip() if self.margin_combo.currentIndex() == 0 else "",
            gross_margin_percent=self.percent_edit.text().strip() if self.margin_combo.currentIndex() == 1 else "",
            cost_basis=self.cost_basis_combo.currentData(),
            material_wastage_percent=self.material_wastage_edit.text().strip(),
            edge_wastage_percent=self.edge_wastage_edit.text().strip(),
            overhead_percent=self.overhead_edit.text().strip(),
            sheet_yield_percent=self.sheet_yield_edit.text().strip(),
            sheet_kerf_mm=self.sheet_kerf_edit.text().strip(),
            sheet_margin_mm=self.sheet_margin_edit.text().strip(),
            sheet_allow_rotation=self.sheet_rotate_check.isChecked(),
        )

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
            cabinet.construction_profile = self._profile_data_for(cabinet)
            assignments = ([HardwareAssignment("PREVIEW-H", "PREVIEW", "handle_bar", self.handle_spin.value())]
                           if self.handle_spin.value() else [])
            rule = self._pricing_policy()
            cost = cost_cabinet(cabinet, self.master, hardware_assignments=assignments,
                                currency=self.currency_edit.text().strip().upper(),
                                as_of=date.today().isoformat(), policy=rule)
            lines = [f"{line.component}: {line.quantity} {line.unit} × {line.rate} = {line.amount} {line.currency} [{line.source_id}]"
                     for line in cost.lines]
            lines.extend(f"MISSING: {reason}" for reason in cost.missing)
            price, reason = selling_price(cost, rule, currency=self.currency_edit.text().strip().upper())
            lines.append(f"{cost.material_basis} BOM cost: {cost.total if cost.total is not None else 'INCOMPLETE'}")
            lines.append(f"Profile {cost.profile_id}/{cost.profile_revision}; Price Master {cost.price_master_revision}")
            lines.append(f"Draft selling price: {price if price is not None else 'INCOMPLETE'} {reason}")
            self.preview.setPlainText("\n".join(lines))
        except ValueError as error:
            self.preview.setPlainText(f"INCOMPLETE: {error}")

    def build(self) -> tuple[CatalogueItem, CataloguePriceRule]:
        template_id = self.template_combo.currentData()
        preview_cabinet = Cabinet(width=self.width_spin.value(), height=self.height_spin.value(),
                                  depth=self.depth_spin.value(), board_thickness=self.thickness_spin.value(),
                                  door_count=self.door_spin.value(), drawer_count=self.drawer_spin.value(),
                                  shelf_count=self.shelf_spin.value(), material=self.finish_combo.currentText(),
                                  cabinet_id="PREVIEW", cabinet_type_id=template_id)
        profile_data = self._profile_data_for(preview_cabinet)
        item = create_custom_revision(
            self.items, product_id=self.product_id_edit.text().strip(), name=self.name_edit.text().strip(),
            template_id=template_id, width=self.width_spin.value(), height=self.height_spin.value(),
            depth=self.depth_spin.value(), board_thickness=self.thickness_spin.value(),
            door_count=self.door_spin.value(), drawer_count=self.drawer_spin.value(),
            shelf_count=self.shelf_spin.value(), default_finish=self.finish_combo.currentText(),
            min_width=self.min_width_spin.value(), max_width=self.max_width_spin.value(),
            min_height=self.min_height_spin.value(), max_height=self.max_height_spin.value(),
            min_depth=self.min_depth_spin.value(), max_depth=self.max_depth_spin.value(),
            handle_quantity=self.handle_spin.value(), construction_profile=profile_data)
        fixed = self.mode_combo.currentText() == "Fixed"
        policy = self._pricing_policy()
        rule = CataloguePriceRule(
            rule_id=f"LIB-{item.product_id.upper()}-V{item.revision}", type_id=item.type_id,
            mode="fixed" if fixed else "calculated", currency=self.currency_edit.text().strip().upper(),
            effective_date=date.today().isoformat(),
            status="approved" if self.approved_check.isChecked() else "draft",
            material=item.default_finish,
            width_mm=item.width if fixed else 0, height_mm=item.height if fixed else 0,
            depth_mm=item.depth if fixed else 0, fixed_price=self.fixed_edit.text().strip() if fixed else "",
            markup_percent=self.percent_edit.text().strip() if not fixed and self.margin_combo.currentIndex() == 0 else "",
            gross_margin_percent=self.percent_edit.text().strip() if not fixed and self.margin_combo.currentIndex() == 1 else "",
            cost_basis=policy.cost_basis,
            material_wastage_percent=policy.material_wastage_percent,
            edge_wastage_percent=policy.edge_wastage_percent,
            overhead_percent=policy.overhead_percent,
            sheet_yield_percent=policy.sheet_yield_percent,
            sheet_kerf_mm=policy.sheet_kerf_mm,
            sheet_margin_mm=policy.sheet_margin_mm,
            sheet_allow_rotation=policy.sheet_allow_rotation)
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
