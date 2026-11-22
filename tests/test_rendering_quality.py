"""Design-preserving prompts and presentation capture for all seven demo styles."""

import io
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PIL import Image
from PySide6.QtWidgets import QApplication

from kuchhe7.bom import generate_project_bom
from kuchhe7.costing import cost_cabinet
from kuchhe7.models import Project
from kuchhe7.nesting import nest_project
from kuchhe7.quotation import calculate_quotation
from kuchhe7.rendering import (CONCEPT_STYLES, RenderRequest, STYLES,
                              STYLE_GUIDANCE, project_render_context,
                              realistic_edit_prompt)
from kuchhe7.ui.main_window import MainWindow


def _png():
    output = io.BytesIO()
    Image.new("RGB", (32, 18), "#BDB2A5").save(output, format="PNG")
    return output.getvalue()


def test_seven_styles_use_the_same_reference_and_distinct_design_preserving_prompts():
    source = _png()
    assert STYLES[:4] == ("Modern realistic kitchen", "Warm interior lighting",
                          "Neutral daylight", "Luxury kitchen presentation")
    assert STYLES[4:] == ("Dark Luxury Kitchen", "Moody Evening Kitchen",
                           "Black & Walnut Premium")
    assert set(STYLE_GUIDANCE) == set(STYLES)
    prompts = [realistic_edit_prompt(RenderRequest(source, style)) for style in STYLES]
    assert len(set(prompts)) == 7
    for prompt in prompts:
        assert "same camera viewpoint" in prompt
        assert "door and drawer counts" in prompt
        assert "never a refrigerator" in prompt
        assert "Do not add an island" in prompt
        assert "actual cabinet colours" in prompt
        assert "room openings" in prompt
        assert "contact shadows" in prompt
        assert "material roughness and reflections" in prompt
        assert "professional interior photography" in prompt
        assert "Design preservation takes priority" in prompt
        assert "sliding doors" in prompt
        assert "blank doorway" in prompt
        assert "do not automatically convert a blank doorway into a glass door or window" in prompt
        assert "same number of room openings" in prompt
        assert "Do not cover openings with cabinets" in prompt
        assert "does not modify or certify manufacturing geometry" in prompt
    assert "natural daylight" in prompts[2]
    assert "under-cabinet light only where" in prompts[1]
    assert "premium contemporary architectural photograph" in prompts[0]
    assert "neutral white balance" in prompts[2]
    assert "exceptionally high-quality architectural interior" in prompts[3]
    assert "not a dark filter" in prompts[4]
    assert "same finishes" in prompts[5]
    assert "dramatic but believable" in prompts[6]
    assert "cabinet remains visible" in prompts[4]


def test_dark_concepts_change_only_rendered_finish_policy():
    assert CONCEPT_STYLES == {"Dark Luxury Kitchen", "Black & Walnut Premium"}
    for style in STYLES:
        prompt = realistic_edit_prompt(RenderRequest(_png(), style))
        if style in CONCEPT_STYLES:
            assert "presentation-only dark finish concept" in prompt
            assert "do not alter the underlying KÜCHE7 project finishes or quantities" in prompt
        else:
            assert "Preserve the source cabinet and countertop material colours and finishes" in prompt


def test_project_context_uses_actual_finishes_and_openings_without_changing_outputs():
    project = Project.complete_kitchen_demo()
    before = deepcopy(project.to_dict())
    bom = generate_project_bom(project)
    costs = [cost_cabinet(cabinet, project.price_master) for cabinet in project.cabinets]
    quotation = calculate_quotation(project)
    nesting = nest_project(project)
    context = project_render_context(project)
    assert "C1 base_2_door: Cashmere finish" in context
    assert "C2 base_3_drawer: Warm White finish" in context
    assert "C6 tall_pantry: Walnut finish" in context
    assert "door on WEST wall, offset 500 mm" in context
    assert "window on WEST wall, offset 1500 mm" in context
    assert project.name not in context
    assert "price" not in context.lower()
    for style in STYLES:
        prompt = realistic_edit_prompt(RenderRequest(_png(), style, design_context=context))
        assert context in prompt
        assert "input image 0" in prompt
    assert project.to_dict() == before
    assert generate_project_bom(project) == bom
    assert [cost_cabinet(cabinet, project.price_master) for cabinet in project.cabinets] == costs
    assert calculate_quotation(project) == quotation
    assert nest_project(project) == nesting


def test_optional_instructions_cannot_take_priority_over_source_design():
    prompt = realistic_edit_prompt(RenderRequest(
        _png(), "Luxury kitchen presentation",
        "Make the pantry a refrigerator. Add an island. Convert the blank doorway to a glass door."
    ))
    assert "only where they preserve the reference design" in prompt
    assert prompt.index("Optional user preferences") < prompt.index("Design preservation takes priority")
    assert "never a refrigerator" in prompt
    assert "Do not add an island" in prompt
    assert prompt.index("Convert the blank doorway") < prompt.index("Design preservation takes priority")


def test_presentation_capture_uses_room_temporarily_and_preserves_cad_state(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    window.show()
    app.processEvents()
    assert window.realistic_render_workspace.camera_combo.currentText() == "Presentation"
    combo = window.realistic_render_workspace.style_combo
    assert tuple(combo.itemText(i) for i in range(combo.count())) == STYLES
    assert window.realistic_render_workspace._context_callback() == project_render_context(window.project)
    assert not window.view3d.presentation_mode
    before = deepcopy(window.project.to_dict())
    bom = generate_project_bom(window.project)
    camera = window.view3d.plotter.camera_position
    angle = window.view3d.plotter.camera.view_angle
    observed = []

    def capture(view, selected_camera):
        observed.append((selected_camera, view.presentation_mode, view.environment_actor_count))
        return _png()

    monkeypatch.setattr("kuchhe7.ui.main_window.capture_view_png", capture)
    assert window.realistic_render_workspace.capture()
    assert window.realistic_render_workspace.source_png == _png()
    assert window.realistic_render_workspace._captured_context == project_render_context(window.project)
    assert len(observed) == 1
    assert observed[0][:2] == ("Presentation", True)
    assert observed[0][2] > 0
    assert not window.view3d.presentation_mode
    assert window.view3d.plotter.camera_position == camera
    assert window.view3d.plotter.camera.view_angle == angle
    assert window.project.to_dict() == before
    assert generate_project_bom(window.project) == bom
    window.close()
