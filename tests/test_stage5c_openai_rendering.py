"""Mocked OpenAI image-edit adapter and desktop integration tests.

No test in this file sends a paid or external API request.
"""

import base64
import io
import json
import os
import time
from copy import deepcopy
from urllib.error import HTTPError, URLError

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from kuchhe7.bom import generate_project_bom
from kuchhe7.models import Project
from kuchhe7.nesting import nest_project
from kuchhe7.quotation import calculate_quotation
from kuchhe7.rendering import (OpenAIImageEditProvider, RenderRequest,
                               configured_image_provider, realistic_edit_prompt)
from kuchhe7.ui.main_window import MainWindow


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (16, 10), "#BDB2A5").save(output, format="PNG")
    return output.getvalue()


class _Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=None):
        return self.value


def test_openai_edit_uses_input_image_and_documented_fields(monkeypatch):
    seen = {}

    def fake_urlopen(http_request, timeout):
        seen.update(json.loads(http_request.data))
        assert http_request.full_url == "https://api.openai.com/v1/images/edits"
        assert http_request.get_header("Authorization") == "Bearer test-only-key"
        assert timeout == 17
        return _Response(json.dumps({"data": [{"b64_json": base64.b64encode(_png()).decode()}]}).encode())

    monkeypatch.setattr("kuchhe7.rendering.urlopen", fake_urlopen)
    provider = OpenAIImageEditProvider("test-only-key", model="gpt-image-2.5-flare",
                                       quality="high", timeout_seconds=17)
    result = provider.render(RenderRequest(_png(), "Neutral daylight", "Keep the walnut pantry"))
    assert result == _png()
    assert seen["model"] == "gpt-image-2.5-flare"
    assert seen["quality"] == "high"
    assert seen["size"] == "1536x1024"
    assert seen["output_format"] == "png"
    assert seen["n"] == 1
    assert seen["images"][0]["image_url"].startswith("data:image/png;base64,")
    assert base64.b64decode(seen["images"][0]["image_url"].split(",", 1)[1]) == _png()
    assert "cabinet" in seen["prompt"].lower() and "walnut pantry" in seen["prompt"]
    assert not any(key in seen for key in ("project", "bom", "quotation", "customer"))


@pytest.mark.parametrize("code,expected", [
    (401, "authentication"), (403, "authentication"),
    (429, "limit"), (500, "HTTP 500"),
])
def test_openai_http_failures_are_clear_without_key_leaks(monkeypatch, code, expected):
    def fake_urlopen(*_args, **_kwargs):
        raise HTTPError("https://api.openai.com/v1/images/edits", code, "Provider details", {}, None)

    monkeypatch.setattr("kuchhe7.rendering.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match=expected) as failure:
        OpenAIImageEditProvider("test-only-key").render(RenderRequest(_png(), "Neutral daylight"))
    assert "test-only-key" not in str(failure.value)


@pytest.mark.parametrize("failure,expected", [
    (TimeoutError(), "timed out"), (URLError(TimeoutError()), "timed out"),
    (URLError("offline"), "network connection"),
])
def test_openai_timeout_and_network_failures_allow_retry(monkeypatch, failure, expected):
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_kw: (_ for _ in ()).throw(failure))
    provider = OpenAIImageEditProvider("test-only-key")
    with pytest.raises(RuntimeError, match=expected):
        provider.render(RenderRequest(_png(), "Neutral daylight"))
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_kw: _Response(
        json.dumps({"data": [{"b64_json": base64.b64encode(_png()).decode()}]}).encode()
    ))
    assert provider.render(RenderRequest(_png(), "Neutral daylight")) == _png()


@pytest.mark.parametrize("raw", [b"not-json", b"{}", b'{"data":[]}',
                                 b'{"data":[{"b64_json":"garbage"}]}'])
def test_openai_rejects_invalid_image_responses(monkeypatch, raw):
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_kw: _Response(raw))
    with pytest.raises(RuntimeError, match="invalid or oversized PNG"):
        OpenAIImageEditProvider("test-only-key").render(RenderRequest(_png(), "Neutral daylight"))


def test_provider_configuration_requires_key_and_valid_model(monkeypatch):
    monkeypatch.delenv("KUCHE7_RENDER_ENDPOINT", raising=False)
    monkeypatch.setenv("KUCHE7_RENDER_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert configured_image_provider() is None
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("KUCHE7_OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst")
    monkeypatch.setenv("KUCHE7_OPENAI_IMAGE_QUALITY", "medium")
    provider = configured_image_provider()
    assert isinstance(provider, OpenAIImageEditProvider)
    assert provider.model == "gpt-image-2.5-sunburst"
    monkeypatch.setenv("KUCHE7_OPENAI_IMAGE_MODEL", "retired-model")
    with pytest.raises(ValueError, match="Unsupported OpenAI image-editing model"):
        configured_image_provider()


def test_openai_rejects_oversized_data_url_before_network(monkeypatch):
    monkeypatch.setattr("kuchhe7.rendering.MAX_OPENAI_DATA_URL_LENGTH", 10)
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_kw: pytest.fail("Network call was made"))
    with pytest.raises(ValueError, match="too large"):
        OpenAIImageEditProvider("test-only-key").render(RenderRequest(_png(), "Neutral daylight"))


def test_render_prompt_and_workspace_do_not_modify_design_or_manufacturing(monkeypatch):
    request = RenderRequest(_png(), "Luxury kitchen presentation", "Soft evening light")
    prompt = realistic_edit_prompt(request)
    assert "same camera viewpoint" in prompt
    assert "material colours" in prompt
    assert "Soft evening light" in prompt
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    monkeypatch.setattr("kuchhe7.ui.main_window.capture_view_png", lambda *_args: _png())
    monkeypatch.setenv("KUCHE7_RENDER_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.No)
    before = deepcopy(window.project.to_dict())
    bom = generate_project_bom(window.project)
    quote = calculate_quotation(window.project)
    nesting = nest_project(window.project)
    window.show_realistic_rendering()
    app.processEvents()
    assert window.realistic_render_workspace.capture()
    assert "Realistic Rendering" in window.statusBar().currentMessage()
    assert window.realistic_render_workspace.generate_button.isEnabled()
    assert not window.realistic_render_workspace.generate()  # User declines external upload.
    assert window.project.to_dict() == before
    assert generate_project_bom(window.project) == bom
    assert calculate_quotation(window.project) == quote
    assert nest_project(window.project) == nesting
    window.close()


def test_async_workspace_prevents_duplicates_and_can_retry_after_failure(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    monkeypatch.setattr("kuchhe7.ui.main_window.capture_view_png", lambda *_args: _png())
    monkeypatch.setattr(QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
    calls = []

    class FakeProvider:
        name = "Mock image edit"

        def render(self, request):
            calls.append(request)
            time.sleep(0.04)
            if len(calls) == 1:
                raise RuntimeError("Mock provider unavailable")
            return _png()

    provider = FakeProvider()
    monkeypatch.setattr("kuchhe7.ui.realistic_render_workspace.configured_image_provider", lambda: provider)
    before = deepcopy(window.project.to_dict())
    window.show_realistic_rendering()
    workspace = window.realistic_render_workspace

    def wait_for_worker():
        deadline = time.monotonic() + 4
        while workspace.render_in_progress and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        assert not workspace.render_in_progress

    assert workspace.generate()
    assert not workspace.generate()
    wait_for_worker()
    assert "Mock provider unavailable" in workspace.status_label.text()
    assert workspace.generate_button.isEnabled()
    assert workspace.generate()
    wait_for_worker()
    assert workspace.result_png == _png()
    assert "AI presentation image ready" in workspace.status_label.text()
    assert len(calls) == 2
    output = tmp_path / "ai-presentation.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_kw: (str(output), "PNG image (*.png)"))
    assert workspace.save_image()
    assert output.read_bytes() == _png()
    assert window.project.to_dict() == before
    window.close()
