import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QApplication, QGraphicsRectItem

from kuchhe7.bom import Component, generate_project_bom
from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.nesting import (
    PanelInstance,
    SheetSettings,
    expand_panel_instances,
    group_panel_instances,
    nest_panels,
    nest_project,
    rectangles_intersect,
)
from kuchhe7.ui.main_window import MainWindow
from kuchhe7.ui.sheet_nesting import DISCLAIMER


def panel(length, width, *, material="Cashmere", thickness=18, number=1):
    return PanelInstance("C1", "Test panel", length, width, thickness, material, number)


def test_bom_quantity_expansion_and_hardware_exclusion():
    components = [
        Component("Door", 716, 397, 18, "Cashmere", 2, "C1"),
        Component("Concealed hinge", 0, 0, 0, "Hardware", 4, "C1"),
    ]
    expanded = expand_panel_instances(components)
    assert len(expanded) == 2
    assert [item.instance_number for item in expanded] == [1, 2]
    assert {item.component_name for item in expanded} == {"Door"}


def test_material_and_thickness_groups_are_never_mixed():
    panels = [
        panel(700, 500, material="Cashmere", thickness=18, number=1),
        panel(700, 500, material="Cashmere", thickness=6, number=2),
        panel(700, 500, material="Walnut", thickness=18, number=3),
    ]
    groups = group_panel_instances(panels)
    assert set(groups) == {("Cashmere", 18), ("Cashmere", 6), ("Walnut", 18)}
    result = nest_panels(panels)
    for group in result.groups:
        assert {(item.panel.material, item.panel.thickness_mm) for item in group.placements} <= {
            (group.material, group.thickness_mm)
        }


def test_placements_respect_boundaries_margins_kerf_and_do_not_overlap():
    settings = SheetSettings(length_mm=1000, width_mm=700, kerf_mm=7, margin_mm=20)
    result = nest_panels([panel(300, 200, number=index) for index in range(1, 7)], settings)
    assert result.unplaced_count == 0
    for group in result.groups:
        for sheet in group.sheets:
            for placed in sheet.placements:
                assert placed.x_mm >= settings.margin_mm
                assert placed.y_mm >= settings.margin_mm
                assert placed.right_mm <= settings.length_mm - settings.margin_mm
                assert placed.bottom_mm <= settings.width_mm - settings.margin_mm
            for index, first in enumerate(sheet.placements):
                for second in sheet.placements[index + 1 :]:
                    assert not rectangles_intersect(first, second, settings.kerf_mm)


def test_rotation_and_grain_direction_restriction():
    candidate = panel(1100, 2200)
    rotatable = nest_panels([candidate], SheetSettings(2440, 1220, 3, 10, True, False))
    assert rotatable.placed_count == 1
    assert rotatable.placed_panels[0].rotated is True

    grain_locked = nest_panels([candidate], SheetSettings(2440, 1220, 3, 10, True, True))
    assert grain_locked.placed_count == 0
    assert grain_locked.unplaced_count == 1


def test_oversized_parts_report_a_specific_warning():
    result = nest_panels([panel(3000, 1300)])
    assert result.sheet_count == 0
    assert result.unplaced_count == 1
    assert result.unplaced_area_mm2 == 3_900_000
    assert result.placed_area_mm2 == 0
    assert "exceeds the usable sheet area" in result.unplaced_panels[0].reason


def test_utilization_and_quantity_reconciliation():
    panels = [panel(100, 100, number=1), panel(100, 100, number=2)]
    result = nest_panels(panels, SheetSettings(500, 500, 0, 0, False, False))
    assert result.total_panel_area_mm2 == 20_000
    assert result.placed_area_mm2 == 20_000
    assert result.unplaced_area_mm2 == 0
    assert result.sheet_count == 1
    assert result.utilization_percent == pytest.approx(8.0)
    assert result.eligible_count == result.placed_count + result.unplaced_count


def test_project_nesting_tracks_authoritative_bom_after_dimension_change():
    project = Project.complete_kitchen_demo()
    before = nest_project(project)
    before_top = next(
        item.panel for item in before.placed_panels
        if item.panel.cabinet_id == "C1" and item.panel.component_name == "Top panel"
    )
    project.selected_cabinet.width = 700
    after = nest_project(project)
    after_top = next(
        item.panel for item in after.placed_panels
        if item.panel.cabinet_id == "C1" and item.panel.component_name == "Top panel"
    )
    assert before_top.length_mm == 764
    assert after_top.length_mm == 664
    eligible_quantity = sum(
        component.quantity
        for component in generate_project_bom(project)
        if component.length_mm > 0 and component.width_mm > 0 and component.thickness_mm > 0
    )
    assert after.eligible_count == eligible_quantity


def test_nesting_does_not_change_existing_xlsx_or_dxf_exports(tmp_path):
    project = Project.complete_kitchen_demo()
    before = project.to_dict()
    nest_project(project)
    workbook_path = export_bom_xlsx(project, tmp_path / "bom.xlsx")
    dxf_path = export_front_elevation_dxf(project, tmp_path / "elevation.dxf")
    rows = list(load_workbook(workbook_path, data_only=True)["BOM"].iter_rows(min_row=5, values_only=True))
    document = ezdxf.readfile(dxf_path)
    assert len(rows) == len(generate_project_bom(project))
    assert document.header["$INSUNITS"] == 4
    assert project.to_dict() == before


def test_sheet_nesting_is_separate_interactive_workspace():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window.show_sheet_nesting()
    application.processEvents()

    preview = window.sheet_nesting
    assert window.workspace_tabs.currentWidget() is preview
    assert preview.result is not None
    assert preview.result.eligible_count == preview.eligible_bom_quantity()
    assert preview.completeness_label.text() == "Layout complete"
    assert preview.group_list.count() == len(preview.result.groups)
    assert preview.disclaimer_label.text() == DISCLAIMER

    selectable = [
        item for item in preview.sheet_view.scene().items()
        if isinstance(item, QGraphicsRectItem) and isinstance(item.data(0), int)
    ]
    assert selectable
    selectable[0].setSelected(True)
    application.processEvents()
    assert preview.part_cabinet.text().startswith("C")
    assert preview.part_name.text() != "—"
    preview.kerf_spin.setValue(4)
    assert "settings changed" in preview.stale_label.text().lower()
    preview.recalculate()
    assert preview.result.settings.kerf_mm == 4
    preview.sheet_length_spin.setValue(700)
    preview.sheet_width_spin.setValue(500)
    preview.rotation_check.setChecked(False)
    preview.recalculate()
    assert preview.result.unplaced_count > 0
    assert preview.completeness_label.text().startswith("Layout incomplete")
    assert preview.stat_total_area.text() != preview.stat_placed_area.text()
    assert preview.stat_unplaced_area.text() != "0.000 m²"
    window.close()


def test_dimension_change_marks_layout_stale_until_recalculation():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_complete_kitchen_demo()
    window.show_sheet_nesting()
    preview = window.sheet_nesting
    original_signature = preview._generated_signature
    window.workspace_tabs.setCurrentWidget(window.workspace_splitter)
    window.select_cabinet("C1")
    window.width_spin.setValue(700)
    application.processEvents()

    assert preview._generated_signature == original_signature
    assert "recalculate" in preview.stale_label.text().lower()
    preview.recalculate()
    assert preview._generated_signature != original_signature
    assert preview.stale_label.text() == "Layout current"
    window.close()
