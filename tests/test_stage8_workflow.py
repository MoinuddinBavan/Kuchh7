"""Stage 8 end-to-end regression with explicitly synthetic pricing."""

from __future__ import annotations

import ezdxf
from openpyxl import load_workbook

from kuchhe7.ui.sheet_nesting import SheetNestingWidget
from scripts.validate_stage8_workflow import build_synthetic_project, validate_workflow


def test_synthetic_three_cabinet_workflow_and_documents(tmp_path):
    report = validate_workflow(tmp_path)
    assert [row["type"] for row in report["cabinets"]] == [
        "base_2_door", "wall_2_door", "base_3_drawer"]
    assert report["nesting"]["eligible"] == report["nesting"]["placed"]
    assert report["issued_total"] != report["after_price_refresh"]
    assert report["before_price_refresh"] != report["after_price_refresh"]
    assert load_workbook(tmp_path / "synthetic-bom.xlsx").active.max_row > 20
    for name in ("synthetic-front-elevations.dxf", "synthetic-panel-outlines.dxf"):
        assert ezdxf.readfile(tmp_path / name).header["$INSUNITS"] == 4
    for name in ("synthetic-bom.pdf", "synthetic-draft-quotation.pdf", "synthetic-issued-quotation.pdf"):
        assert (tmp_path / name).stat().st_size > 500


def test_nesting_stale_badge_requires_explicit_recalculation(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    project, _company = build_synthetic_project()
    widget = SheetNestingWidget()
    widget.set_project(project)
    before = widget.result.total_panel_area_mm2
    project.cabinets[0].width += 100
    project.validate()
    widget.set_project(project)
    assert "recalculate" in widget.stale_label.text().lower()
    assert widget.result.total_panel_area_mm2 == before
    widget.recalculate()
    assert widget.stale_label.text() == "Layout current"
    assert widget.result.total_panel_area_mm2 != before
    widget.deleteLater()
    app.processEvents()
