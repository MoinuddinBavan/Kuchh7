from __future__ import annotations

import json
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .exports import export_bom_xlsx, export_front_elevation_dxf
from .persistence import load_project, save_project


def run_release_smoke(window, application: QApplication, output_directory: str | Path) -> None:
    """Exercise the packaged client-demo flow without development-path dependencies."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "packaged-smoke-report.json"
    try:
        assert window.project.cabinets == []
        assert window.project.selected_cabinet is None
        assert window.bom_table.rowCount() == 0
        window.add_cabinet()
        application.processEvents()
        assert [item.cabinet_id for item in window.project.cabinets] == ["C1"]
        window.remove_selected_cabinet()
        application.processEvents()
        assert window.project.cabinets == []
        assert window.manufacturing_preview.cabinet is None
        assert window.sheet_nesting.result.eligible_count == 0
        window.undo_action.trigger()
        assert [item.cabinet_id for item in window.project.cabinets] == ["C1"]
        window.redo_action.trigger()
        assert window.project.cabinets == []
        window._set_dirty(False)
        window.load_complete_kitchen_demo()
        assert len(window.project.cabinets) == 6

        window.workspace_tabs.setCurrentWidget(window.workspace_splitter)
        window.presentation_view_action.setChecked(True)
        window.select_cabinet("C1")
        window.width_spin.setValue(700)
        application.processEvents()
        assert window.project.selected_cabinet.width == 700

        window.maximize_3d_action.setChecked(True)
        application.processEvents()
        assert window._workspace_3d_maximized
        window.maximize_3d_action.setChecked(False)
        application.processEvents()
        assert not window._workspace_3d_maximized

        window.show_manufacturing_preview()
        window.manufacturing_preview.select_component("Door")
        window.manufacturing_preview.drawing_tabs.setCurrentIndex(1)
        application.processEvents()
        assert window.manufacturing_preview.cabinet.cabinet_id == "C1"

        window.show_sheet_nesting()
        window.sheet_nesting.recalculate()
        application.processEvents()
        nesting = window.sheet_nesting.result
        assert nesting is not None
        assert nesting.eligible_count == nesting.placed_count + nesting.unplaced_count

        project_path = save_project(window.project, output / "packaged-complete-kitchen.json")
        workbook_path = export_bom_xlsx(window.project, output / "packaged-complete-kitchen-bom.xlsx")
        dxf_path = export_front_elevation_dxf(
            window.project, output / "packaged-complete-kitchen-elevation.dxf"
        )
        reopened = load_project(project_path)
        assert reopened.to_dict() == window.project.to_dict()
        window.project = reopened
        window.refresh_all(reset_camera=True)

        window.show_sheet_nesting()
        window.showMaximized()
        application.processEvents()
        screenshot_path = output / "kuchhe7-v1.0.1-windows-application-launch.png"
        assert window.grab().save(str(screenshot_path), "PNG")

        report = {
            "status": "passed",
            "empty_startup_verified": True,
            "cabinet_count": len(reopened.cabinets),
            "edited_c1_width_mm": reopened.cabinets[0].width,
            "eligible_panels": nesting.eligible_count,
            "placed_panels": nesting.placed_count,
            "unplaced_panels": nesting.unplaced_count,
            "used_sheets": nesting.sheet_count,
            "utilization_percent": round(nesting.utilization_percent, 1),
            "project_json": str(project_path.resolve()),
            "xlsx": str(workbook_path.resolve()),
            "dxf": str(dxf_path.resolve()),
            "screenshot": str(screenshot_path.resolve()),
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        application.quit()
    except Exception as error:  # pragma: no cover - exercised by packaged release validation
        report_path.write_text(
            json.dumps(
                {"status": "failed", "error": str(error), "traceback": traceback.format_exc()},
                indent=2,
            ),
            encoding="utf-8",
        )
        application.exit(2)
