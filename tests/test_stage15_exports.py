"""Focused checks for the four grouped header exports and project dossier."""

import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
from PIL import Image
from PySide6.QtWidgets import QApplication, QDialog

from kuchhe7.models import Project
from kuchhe7.project_pdf import ProjectPdfOptions, SECTIONS, export_project_pdf
from kuchhe7.ui.cad_export_dialog import CadExportDialog, COMPLETE, SHEET_LAYOUT
from kuchhe7.ui.project_pdf_dialog import ProjectPdfDialog
from kuchhe7.wall_elevation_export import export_wall_elevations_dxf


def test_project_pdf_sections_and_dialog_defaults():
    app = QApplication.instance() or QApplication([])
    dialog = ProjectPdfDialog()
    try:
        assert len(SECTIONS) == 5
        assert dialog.options() == ProjectPdfOptions()
        dialog.section_checks["views"].setChecked(False)
        dialog.panel_check.setChecked(True)
        assert "views" not in dialog.options().sections
        assert dialog.options().include_panels
        for check in dialog.section_checks.values():
            check.setChecked(False)
        assert not dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()
    finally:
        dialog.close()


def test_project_pdf_uses_current_project_and_two_live_captures(tmp_path):
    app = QApplication.instance() or QApplication([])
    project = Project.complete_kitchen_demo()
    before = project.to_dict()
    source = io.BytesIO()
    Image.new("RGB", (1600, 900), "#bdb2a5").save(source, format="PNG")
    calls = []

    def capture(camera, resolution):
        calls.append((camera, resolution))
        return source.getvalue()

    path = export_project_pdf(project, tmp_path / "complete.pdf", capture_3d=capture)
    assert path.is_file() and path.stat().st_size > 10_000
    assert calls == [("Presentation", (3200, 1800)), ("Isometric", (3200, 1800))]
    assert project.to_dict() == before


def test_project_pdf_section_selection_and_validation(tmp_path):
    app = QApplication.instance() or QApplication([])
    project = Project.complete_kitchen_demo()
    options = ProjectPdfOptions(sections=("plan", "schedule"), paper="A4")
    path = export_project_pdf(project, tmp_path / "selected.pdf", options)
    assert path.is_file() and path.stat().st_size > 1_000
    try:
        ProjectPdfOptions(sections=()).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Empty PDF section selection should be rejected")


def test_cad_selector_disables_fake_dwg_and_stale_sheet():
    app = QApplication.instance() or QApplication([])
    dialog = CadExportDialog(sheet_available=False)
    try:
        assert dialog.drawing_type == COMPLETE
        assert dialog.drawing_format == "dxf"
        assert not dialog.format_combo.model().item(1).isEnabled()
        assert not dialog.drawing_combo.model().item(
            dialog.drawing_combo.findData(SHEET_LAYOUT)).isEnabled()
        assert dialog.drawing_combo.count() >= 9
    finally:
        dialog.close()


def test_wall_elevation_dxf_is_valid_and_in_millimetres(tmp_path):
    project = Project.complete_kitchen_demo()
    before = project.to_dict()
    path = export_wall_elevations_dxf(project, tmp_path / "walls.dxf")
    doc = ezdxf.readfile(path)
    assert doc.header["$INSUNITS"] == 4
    assert len(doc.modelspace()) > 0
    assert project.to_dict() == before


def test_project_pdf_cancel_and_export_error_leave_project_unchanged(tmp_path, monkeypatch):
    from kuchhe7.ui import main_window as module

    app = QApplication.instance() or QApplication([])
    window = module.MainWindow(start_empty=False)
    before = window.project.to_dict()
    try:
        class CancelDialog:
            def __init__(self, parent):
                pass

            def exec(self):
                return QDialog.DialogCode.Rejected

        monkeypatch.setattr(module, "ProjectPdfDialog", CancelDialog)
        monkeypatch.setattr(module.QFileDialog, "getSaveFileName",
                            lambda *args: (_ for _ in ()).throw(AssertionError("Save dialog opened")))
        window.export_project_document()

        class AcceptDialog(CancelDialog):
            def exec(self):
                return QDialog.DialogCode.Accepted

            def options(self):
                return ProjectPdfOptions(sections=("plan",))

        monkeypatch.setattr(module, "ProjectPdfDialog", AcceptDialog)
        monkeypatch.setattr(module.QFileDialog, "getSaveFileName",
                            lambda *args: (str(tmp_path / "error.pdf"), "PDF"))
        monkeypatch.setattr(module, "export_project_pdf",
                            lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("Synthetic export error")))
        warnings = []
        monkeypatch.setattr(module.QMessageBox, "warning",
                            lambda *args: warnings.append(args[-1]))
        window.export_project_document()
        assert warnings == ["Synthetic export error"]
        assert not (tmp_path / "error.pdf").exists()
        assert window.project.to_dict() == before
    finally:
        window.close()


def test_all_four_document_submenu_routes_preserve_issued_access(monkeypatch):
    from kuchhe7.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    called = []
    try:
        for name in ("export_bom_excel", "export_bom_pdf",
                     "export_quote_excel", "export_quote_pdf"):
            monkeypatch.setattr(window.documents_workspace, name,
                                lambda key=name: called.append(key))
        for menu in (window.export_bom_menu, window.export_quote_menu):
            for action in menu.actions():
                action.trigger()
        assert called == ["export_bom_excel", "export_bom_pdf",
                          "export_quote_excel", "export_quote_pdf"]
        assert window.documents_workspace.issued_excel_button.text() == "Export issued Excel"
        assert window.documents_workspace.issued_pdf_button.text() == "Export issued PDF"
        assert hasattr(window, "export_cut_list_action")
        assert hasattr(window, "engineering_export_action")
    finally:
        window.close()


def test_cad_export_rejects_dwg_filename_instead_of_mislabeling_dxf(tmp_path, monkeypatch):
    from kuchhe7.ui import main_window as module

    app = QApplication.instance() or QApplication([])
    window = module.MainWindow(start_empty=False)
    try:
        class AcceptedDxf:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted

            drawing_format = "dxf"
            drawing_type = COMPLETE

        monkeypatch.setattr(module, "CadExportDialog", AcceptedDxf)
        monkeypatch.setattr(module.QFileDialog, "getSaveFileName",
                            lambda *args: (str(tmp_path / "misleading.dwg"), "DXF"))
        monkeypatch.setattr(module, "export_complete_kitchen_dxf",
                            lambda *args: (_ for _ in ()).throw(AssertionError("DXF writer called")))
        warnings = []
        monkeypatch.setattr(module.QMessageBox, "warning",
                            lambda *args: warnings.append(args[-1]))
        window.export_cad_drawing()
        assert len(warnings) == 1 and "Genuine DWG" in warnings[0]
        assert not (tmp_path / "misleading.dwg").exists()
    finally:
        window.close()


def test_cad_export_default_routes_to_complete_kitchen_dxf(tmp_path, monkeypatch):
    from kuchhe7.ui import main_window as module

    app = QApplication.instance() or QApplication([])
    window = module.MainWindow(start_empty=False)
    window.project = Project.complete_kitchen_demo()
    output = tmp_path / "complete.dxf"
    try:
        class AcceptedDxf:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted

            drawing_format = "dxf"
            drawing_type = COMPLETE

        monkeypatch.setattr(module, "CadExportDialog", AcceptedDxf)
        monkeypatch.setattr(module.QFileDialog, "getSaveFileName",
                            lambda *args: (str(output), "DXF"))
        window.export_cad_drawing()
        assert output.is_file()
        drawing = ezdxf.readfile(output)
        assert drawing.header["$INSUNITS"] == 4
        assert len(drawing.modelspace()) > 100
    finally:
        window.close()
