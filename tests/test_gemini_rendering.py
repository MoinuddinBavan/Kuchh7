"""Gemini image-edit integration tests; all provider responses are mocked."""

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
from PySide6.QtWidgets import QApplication, QMessageBox

from kuchhe7.bom import generate_project_bom
from kuchhe7.models import Project
from kuchhe7.nesting import nest_project
from kuchhe7.quotation import calculate_quotation
from kuchhe7.rendering import GeminiImageEditProvider, RenderRequest, configured_image_provider
from kuchhe7.ui.main_window import MainWindow
from kuchhe7.ui.realistic_render_workspace import RealisticRenderWorkspace


def _image(fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (24, 16), "#BDB2A5").save(output, format=fmt)
    return output.getvalue()


class _Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        return self.data[:limit]


def test_gemini_submits_actual_capture_and_displays_returned_png(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["body"] = json.loads(request.data)
        seen["url"] = request.full_url
        seen["key"] = request.get_header("X-goog-api-key")
        seen["revision"] = request.get_header("Api-revision")
        assert timeout == 21
        return _Response(json.dumps({"output_image": {"data": base64.b64encode(_image()).decode()}}).encode())

    monkeypatch.setattr("kuchhe7.rendering.urlopen", fake_urlopen)
    result = GeminiImageEditProvider("test-only-key", timeout_seconds=21).render(
        RenderRequest(_image(), "Neutral daylight", "Keep the Cashmere base cabinet")
    )
    assert result == _image()
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert seen["key"] == "test-only-key"
    assert seen["revision"] == "2026-05-20"
    assert seen["body"]["model"] == "gemini-nano-banana-2.1"
    assert base64.b64decode(seen["body"]["input"][1]["data"]) == _image()
    assert seen["body"]["input"][1]["mime_type"] == "image/png"
    assert "Cashmere base cabinet" in seen["body"]["input"][0]["text"]
    assert not any(name in seen["body"] for name in ("project", "bom", "quotation", "customer"))


def test_gemini_accepts_image_step_and_converts_jpeg_for_preview(monkeypatch):
    response = {"interaction": {"steps": [{"type": "model_output", "content": [
        {"type": "text", "text": "Done"},
        {"type": "image", "data": base64.b64encode(_image("JPEG")).decode()},
    ]}]}}
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: _Response(json.dumps(response).encode()))
    result = GeminiImageEditProvider("test-only-key").render(RenderRequest(_image(), "Neutral daylight"))
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "PNG"
        assert image.size == (24, 16)


@pytest.mark.parametrize("failure, expected", [
    (HTTPError("https://example.invalid", 401, "private", {}, None), "authentication"),
    (HTTPError("https://example.invalid", 429, "private", {}, None), "limit"),
    (TimeoutError(), "timed out"),
    (URLError("offline"), "network connection"),
])
def test_gemini_failures_are_clear_and_do_not_expose_key(monkeypatch, failure, expected):
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: (_ for _ in ()).throw(failure))
    with pytest.raises(RuntimeError, match=expected) as error:
        GeminiImageEditProvider("test-only-key").render(RenderRequest(_image(), "Neutral daylight"))
    assert "test-only-key" not in str(error.value)


@pytest.mark.parametrize("response", [b"{}", b"not-json", b'{"output_image":{"data":"garbage"}}'])
def test_gemini_rejects_missing_or_invalid_image(monkeypatch, response):
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: _Response(response))
    with pytest.raises(RuntimeError, match="invalid or oversized"):
        GeminiImageEditProvider("test-only-key").render(RenderRequest(_image(), "Neutral daylight"))


def test_provider_selection_and_capture_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("KUCHE7_RENDER_ENDPOINT", raising=False)
    monkeypatch.delenv("KUCHE7_RENDER_PROVIDER", raising=False)
    assert configured_image_provider("gemini") is None
    assert configured_image_provider("openai") is None
    app = QApplication.instance() or QApplication([])
    workspace = RealisticRenderWorkspace(None, capture_callback=lambda _camera: _image())
    workspace.provider_combo.setCurrentIndex(1)
    assert workspace.capture()
    assert not workspace.generate_button.isEnabled()
    assert workspace.source_png == _image()
    assert workspace.result_png is None
    workspace.close()
    app.processEvents()

    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    assert isinstance(configured_image_provider("gemini"), GeminiImageEditProvider)
    assert isinstance(configured_image_provider(), GeminiImageEditProvider)
    monkeypatch.setenv("KUCHE7_GEMINI_IMAGE_MODEL", "retired-model")
    with pytest.raises(ValueError, match="Unsupported Gemini"):
        configured_image_provider("gemini")


def test_sample_kitchen_gemini_result_reaches_before_after_preview(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    monkeypatch.delenv("KUCHE7_GEMINI_IMAGE_MODEL", raising=False)
    monkeypatch.setattr("kuchhe7.ui.main_window.capture_view_png", lambda *_a: _image())
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: _Response(json.dumps({
        "output_image": {"data": base64.b64encode(_image()).decode()}
    }).encode()))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    project_before = deepcopy(window.project.to_dict())
    bom_before = generate_project_bom(window.project)
    quotation_before = calculate_quotation(window.project)
    nesting_before = nest_project(window.project)
    window.show_realistic_rendering()
    workspace = window.realistic_render_workspace
    workspace.provider_combo.setCurrentIndex(1)
    assert workspace.capture()
    assert workspace.generate()
    deadline = time.monotonic() + 5
    while workspace.render_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert workspace.source_png == _image()
    assert workspace.result_png == _image()
    assert not workspace.before_label.pixmap().isNull()
    assert not workspace.after_label.pixmap().isNull()
    assert window.project.to_dict() == project_before
    assert generate_project_bom(window.project) == bom_before
    assert calculate_quotation(window.project) == quotation_before
    assert nest_project(window.project) == nesting_before
    window.close()
