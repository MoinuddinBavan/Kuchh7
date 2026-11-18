"""Stage 5A local/remote interpretation and guarded proposal workflow."""

import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import ezdxf
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from kuchhe7.ai_design import (
    DesignIntent, HttpJsonDesignProvider, LocalRuleBasedProvider, RequestedItem,
    build_proposal, parse_provider_response, project_fingerprint,
)
from kuchhe7.bom import generate_project_bom
from kuchhe7.engineering_dxf import CNC_PROTOTYPE, eligible_panel_instances, export_engineering_dxf
from kuchhe7.models import Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.quotation import calculate_quotation
from kuchhe7.ui.main_window import MainWindow


def test_local_interpretation_uses_catalogue_and_labels_rotation_limit():
    project = Project.empty()
    intent = LocalRuleBasedProvider().interpret(
        "Modern L-shaped kitchen in Cashmere with a plant and oven", project
    )
    assert intent.layout == "L footprint"
    assert intent.items[0].type_id == "corner_base"
    assert all(item.orientation_degrees == 0 for item in intent.items)
    assert any("rotation" in warning for warning in intent.warnings)
    assert any(item.type_id == "plant_pot" for item in intent.items)
    assert all(item.finish == "Cashmere" for item in intent.items if item.type_id.endswith("base"))


def test_local_straight_design_is_structured_and_respects_current_room():
    project = Project.empty()
    intent = LocalRuleBasedProvider().interpret("compact straight kitchen", project)
    proposal = build_proposal(project, intent, source="Local demo", mode="replace")
    assert len(proposal.items) == 4
    assert len(proposal.after_project.cabinets) == 4
    assert proposal.after_project.room is not project.room
    assert project.cabinets == []
    assert all(item.x + item.width <= project.room.width for item in proposal.items)
    proposal.after_project.validate()


def test_unsupported_prompt_and_catalogue_ids_show_warnings_without_changes():
    project = Project.empty()
    before = project.to_dict()
    unsupported = LocalRuleBasedProvider().interpret("U-shaped round kitchen", project)
    proposal = build_proposal(project, unsupported, source="Local demo")
    assert not proposal.can_apply
    assert "straight and L-footprint" in proposal.warnings[0]
    remote = DesignIntent("Straight", (RequestedItem("fictional_robot_cabinet", 100, 200),
                                       RequestedItem("handle_bar", 200, 300)))
    proposal = build_proposal(project, remote, source="Mock AI", allow_reposition=False)
    assert not proposal.can_apply
    assert any("no matching catalogue" in warning for warning in proposal.warnings)
    assert any("manual cabinet assignment" in warning for warning in proposal.warnings)
    assert project.to_dict() == before


def test_remote_response_ignores_invented_dimensions_and_rejects_invalid_geometry():
    project = Project.empty()
    response = {"layout": "Straight", "items": [
        {"type_id": "base_2_door", "x": 3000, "y": 2700, "width": 5000},
        {"type_id": "base_3_drawer", "x": 100, "y": 2600, "orientation_degrees": 90},
        {"type_id": "base_2_door", "x": 200, "y": 2600, "finish": "Walnut"},
    ]}
    intent = parse_provider_response(response)
    proposal = build_proposal(project, intent, source="Mock AI", allow_reposition=False)
    assert len(proposal.items) == 1
    assert proposal.items[0].type_id == "base_2_door"
    assert proposal.items[0].width == 900  # Catalogue authority, not 5000.
    assert proposal.items[0].finish == "Walnut"
    assert any("custom dimensions ignored" in warning for warning in proposal.warnings)
    assert any("rotation 90" in warning for warning in proposal.warnings)
    assert any("no valid room position" in warning for warning in proposal.warnings)


def test_remote_position_conflicting_with_existing_door_is_rejected():
    project = Project.sample_kitchen()
    intent = DesignIntent("Straight", (RequestedItem("base_2_door", 0, 500),))
    proposal = build_proposal(project, intent, source="Mock service", mode="replace",
                              allow_reposition=False)
    assert not proposal.can_apply
    assert any("door D1" in warning for warning in proposal.warnings)
    assert len(project.cabinets) == 3


def test_mocked_http_provider_contract_and_unavailable_service(monkeypatch):
    project = Project.empty()
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"layout": "Straight", "items": [
                {"type_id": "base_2_door", "x": 100, "y": 2600},
            ]}).encode()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("kuchhe7.ai_design.urlopen", fake_urlopen)
    provider = HttpJsonDesignProvider("https://example.invalid/structured", "test-key")
    intent = provider.interpret("straight kitchen", project)
    assert intent.items[0].type_id == "base_2_door"
    assert captured["payload"]["room_mm"]["width"] == 3600
    assert "base_2_door" in captured["payload"]["catalogue_type_ids"]
    assert captured["timeout"] == 12

    def unavailable(*_args, **_kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr("kuchhe7.ai_design.urlopen", unavailable)
    with pytest.raises(RuntimeError, match="unavailable"):
        provider.interpret("straight kitchen", project)
    with pytest.raises(ValueError, match="HTTPS"):
        HttpJsonDesignProvider("http://public.example/api")
    with pytest.raises(ValueError, match="HTTPS"):
        HttpJsonDesignProvider("http://localhost.evil.example/api")


def test_remote_positions_require_both_integer_millimetre_coordinates():
    intent = parse_provider_response({"layout": "Straight", "items": [
        {"type_id": "base_2_door", "x": 100.5, "y": 2600},
        {"type_id": "base_2_door", "x": 100},
        {"type_id": "base_2_door", "x": 100, "y": 2600},
    ]})
    assert len(intent.items) == 1
    assert (intent.items[0].x, intent.items[0].y) == (100, 2600)
    assert len([warning for warning in intent.warnings if "invalid position" in warning]) == 2


def test_proposal_reject_apply_undo_redo_and_2d_3d_sync(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show_ai_design()
    before = deepcopy(window.project.to_dict())
    proposal = window.generate_design_proposal("compact straight kitchen", "replace")
    assert proposal is not None and proposal.can_apply
    assert window.ai_design_workspace.table.rowCount() == 4
    assert window.project.to_dict() == before
    window.reject_design_proposal()
    assert window.project.to_dict() == before
    window.generate_design_proposal("compact straight kitchen", "replace")
    assert window.apply_design_proposal()
    assert window._dirty
    assert len(window.project.cabinets) == 4
    assert len(window.plan_view._cabinet_items) == 4
    assert "C1-left-side" in window.view3d.plotter.actors
    window.select_cabinet("C2")
    window.width_spin.setValue(550)
    assert window.project.selected_cabinet.width == 550
    assert window.plan_view._cabinet_items["C2"].rect().width() == pytest.approx(550 * window.plan_view._scale)
    assert any(item.cabinet_id == "C2" and item.name == "Top panel" and item.length_mm == 514
               for item in generate_project_bom(window.project))
    reopened = load_project(save_project(window.project, tmp_path / "ai-kitchen.json"))
    assert [(item.cabinet_type_id, item.position_x, item.position_y) for item in reopened.cabinets] == [
        (item.cabinet_type_id, item.position_x, item.position_y) for item in window.project.cabinets
    ]
    window.undo_stack.undo()  # Undo the proposed layout as one command.
    assert window.project.to_dict() == before
    window.undo_stack.redo()
    assert len(window.project.cabinets) == 4
    assert window.project.cabinets[1].width == 600
    window.close()


def test_replace_existing_requires_confirmation_and_preserves_on_decline(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    before = window.project.to_dict()
    window.generate_design_proposal("compact straight kitchen", "replace")
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.No)
    assert not window.apply_design_proposal()
    assert window.project.to_dict() == before
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
    assert window.apply_design_proposal()
    assert len(window.project.cabinets) == 4
    window.undo_stack.undo()
    assert window.project.to_dict() == before
    window.close()


def test_add_mode_and_stale_proposal_cannot_overwrite_changes():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(start_empty=False)
    before_count = len(window.project.cabinets)
    proposal = window.generate_design_proposal("compact straight kitchen", "add")
    assert proposal and proposal.can_apply
    assert len(window.project.cabinets) == before_count
    assert window.apply_design_proposal()
    assert len(window.project.cabinets) > before_count
    window.undo_stack.undo()
    assert len(window.project.cabinets) == before_count
    window.generate_design_proposal("compact straight kitchen", "add")
    window.project.cabinets[0].material = "Walnut"
    assert not window.apply_design_proposal()
    assert window.pending_design_proposal is None
    window.close()


def test_props_remain_out_of_financial_and_manufacturing_outputs(tmp_path):
    project = Project.empty()
    intent = LocalRuleBasedProvider().interpret("straight kitchen with plant", project)
    proposal = build_proposal(project, intent, source="Local demo")
    after = proposal.after_project
    assert any(item.type_id == "plant_pot" for item in after.placed_products)
    without_prop = deepcopy(after)
    without_prop.placed_products.clear()
    assert generate_project_bom(after) == generate_project_bom(without_prop)
    assert len(eligible_panel_instances(after)) == len(eligible_panel_instances(without_prop))
    assert nest_project(after).eligible_count == nest_project(without_prop).eligible_count
    assert calculate_quotation(after).lines == calculate_quotation(without_prop).lines
    dxf = ezdxf.readfile(export_engineering_dxf(after, tmp_path / "panels.dxf", CNC_PROTOTYPE))
    assert len(dxf.modelspace().query('LWPOLYLINE[layer=="CNC_PANEL_OUTLINES"]')) == len(eligible_panel_instances(after))
    reopened = load_project(save_project(after, tmp_path / "props.json"))
    assert generate_project_bom(reopened) == generate_project_bom(without_prop)


def test_window_falls_back_to_labelled_local_demo_when_service_fails(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    class FailingProvider:
        name = "Unavailable remote"

        def interpret(self, *_args):
            raise RuntimeError("remote unavailable")

    monkeypatch.setattr("kuchhe7.ui.main_window.configured_provider", lambda: FailingProvider())
    proposal = window.generate_design_proposal("compact straight kitchen", "replace")
    assert proposal is not None
    assert proposal.source == LocalRuleBasedProvider.name
    assert "not AI" in window.ai_design_workspace.mode_label.text()
    assert any("remote unavailable" in warning for warning in proposal.warnings)
    assert len(window.project.cabinets) == 0
    window.close()
