"""Stage 5B persisted orientation and presentation-only image workflow."""

import base64
import io
import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import numpy as np
import pytest
from PIL import Image
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QGraphicsLineItem

from kuchhe7.ai_design import LocalRuleBasedProvider, build_proposal
from kuchhe7.bom import generate_project_bom
from kuchhe7.models import Cabinet, Project
from kuchhe7.nesting import nest_project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.quotation import calculate_quotation
from kuchhe7.rendering import (HttpJsonImageProvider, RenderRequest, capture_view_png,
                               save_png)
from kuchhe7.ui.main_window import MainWindow


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (12, 8), "#BDB2A5").save(output, format="PNG")
    return output.getvalue()


def test_rotated_footprint_collision_and_legacy_project(tmp_path):
    project = Project.empty()
    cabinet = Cabinet(cabinet_id="C1", width=900, depth=600, position_x=3000,
                      position_y=1400, orientation_degrees=270)
    project.add_cabinet(cabinet)
    assert (cabinet.footprint_width, cabinet.footprint_depth) == (600, 900)
    project.validate()
    with pytest.raises(ValueError, match="outside"):
        project.validate_cabinet_placement(Cabinet(cabinet_id="C2", width=900, depth=600,
                                                   position_x=3001, position_y=1400))
    path = tmp_path / "rotated.json"
    save_project(project, path)
    loaded = load_project(path)
    assert loaded.cabinets[0].orientation_degrees == 270
    data = loaded.to_dict()
    del data["cabinets"][0]["orientation_degrees"]
    data["cabinets"][0]["position_x"] = 0
    if data.get("cabinet"):
        data["cabinet"].pop("orientation_degrees", None)
    assert Project.from_dict(data).cabinets[0].orientation_degrees == 0


def test_l_proposal_rotates_actual_cabinet_without_changing_manufacturing():
    project = Project.empty()
    intent = LocalRuleBasedProvider().interpret("L-shaped Cashmere kitchen with plant", project)
    proposal = build_proposal(project, intent, source="Local demo")
    rotated = [item for item in proposal.after_project.cabinets if item.orientation_degrees == 270]
    assert len(rotated) == 1
    cabinet = rotated[0]
    assert cabinet.position_x + cabinet.footprint_width <= project.room.width
    assert cabinet.position_y + cabinet.footprint_depth <= project.room.depth
    before = deepcopy(proposal.after_project)
    before.placed_products.clear()
    assert generate_project_bom(before) == generate_project_bom(proposal.after_project)
    assert nest_project(before).eligible_panels == nest_project(proposal.after_project).eligible_panels
    assert calculate_quotation(before).total == calculate_quotation(proposal.after_project).total


def test_capture_camera_resolution_save_and_project_unchanged(monkeypatch, tmp_path):
    class Camera:
        view_angle = 30.0

    class Plotter:
        camera = Camera()
        camera_position = [(1, 2, 3), (0, 0, 0), (0, 0, 1)]
        calls = []

        def screenshot(self, **kwargs):
            self.calls.append(kwargs)
            return np.full((8, 12, 3), 180, dtype=np.uint8)

        def render(self):
            pass

    class View:
        plotter = Plotter()

        def view_front(self):
            self.plotter.camera_position = [(5, 5, 5), (0, 0, 0), (0, 0, 1)]

    view = View()
    before_camera = view.plotter.camera_position
    image = capture_view_png(view, "Front", (800, 600))
    assert view.plotter.calls[-1]["window_size"] == (800, 600)
    assert view.plotter.camera_position == before_camera
    target = tmp_path / "capture.png"
    save_png(image, target)
    assert Image.open(target).size == (12, 8)


def test_mocked_image_provider_sends_only_image_style_instructions(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"image_base64": base64.b64encode(_png()).decode()}).encode()

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data))
        assert timeout == 7
        return Response()

    monkeypatch.setattr("kuchhe7.rendering.urlopen", fake_urlopen)
    provider = HttpJsonImageProvider("https://example.invalid/render", timeout_seconds=7)
    result = provider.render(RenderRequest(_png(), "Neutral daylight", "Keep cabinet positions"))
    assert result == _png()
    assert set(captured) == {"image_base64", "style", "instructions", "output_format"}
    assert "project" not in captured
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(RuntimeError, match="Rendering service failed"):
        provider.render(RenderRequest(_png(), "Neutral daylight"))


def test_render_workspace_unavailable_without_provider_and_rotated_3d_actor(monkeypatch):
    monkeypatch.delenv("KUCHE7_RENDER_ENDPOINT", raising=False)
    monkeypatch.delenv("KUCHE7_RENDER_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    proposal = build_proposal(window.project,
                              LocalRuleBasedProvider().interpret("L-shaped Cashmere kitchen", window.project),
                              source="Local demo")
    window.project = proposal.after_project
    window.refresh_all(reset_camera=True)
    application.processEvents()
    rotated = next(item for item in window.project.cabinets if item.orientation_degrees == 270)
    actor = window.view3d.plotter.actors[f"{rotated.cabinet_id}-top"]
    assert actor.GetUserMatrix() is not None
    assert actor.GetBounds()[1] - actor.GetBounds()[0] == pytest.approx(rotated.depth)
    front_x = window.plan_view._ox + rotated.position_x * window.plan_view._scale
    front_y0 = window.plan_view._oy + rotated.position_y * window.plan_view._scale
    front_y1 = front_y0 + rotated.width * window.plan_view._scale
    assert any(
        isinstance(item, QGraphicsLineItem)
        and item.pen().color() == QColor("#0B5559")
        and item.line().x1() == pytest.approx(front_x)
        and item.line().x2() == pytest.approx(front_x)
        and sorted((item.line().y1(), item.line().y2())) == pytest.approx([front_y0, front_y1])
        for item in window.plan_view.scene().items()
    )
    before = deepcopy(window.project.to_dict())
    monkeypatch.setattr("kuchhe7.ui.main_window.capture_view_png", lambda *_args: _png())
    window.show_realistic_rendering()
    application.processEvents()
    assert window.workspace_tabs.currentWidget() is window.realistic_render_workspace
    assert not window.realistic_render_workspace.generate_button.isEnabled()
    assert window.project.to_dict() == before
    window.project.name = "Changed after capture"
    assert not window.realistic_render_workspace.generate()
    assert "Capture the current 3D scene again" in window.realistic_render_workspace.status_label.text()
    window.close()
