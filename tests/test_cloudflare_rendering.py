"""Cloudflare image-edit adapter tests; all network responses are mocked."""

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
from kuchhe7.rendering import (CloudflareImageEditProvider, RenderRequest,
                               configured_image_provider)
from scripts.compare_cloudflare_models import COMPARISON_PROMPT, main as compare_models
from kuchhe7.ui.main_window import MainWindow


ACCOUNT = "a" * 32  # Synthetic account ID, never a usable credential.


def _png(size=(32, 18)):
    output = io.BytesIO()
    Image.new("RGB", size, "#BDB2A5").save(output, format="PNG")
    return output.getvalue()


class _Response:
    def __init__(self, data, content_type="application/json"):
        self.data = data
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit):
        return self.data[:limit]


def test_cloudflare_uses_reference_image_multipart_and_normalizes_result(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["content_type"] = request.get_header("Content-type")
        seen["body"] = request.data
        assert timeout == 17
        return _Response(json.dumps({"success": True, "result": {
            "image": base64.b64encode(_png()).decode()
        }}).encode())

    monkeypatch.setattr("kuchhe7.rendering.urlopen", fake_urlopen)
    result = CloudflareImageEditProvider(ACCOUNT, "test-only-token", timeout_seconds=17).render(
        RenderRequest(_png((1600, 900)), "Neutral daylight", "Keep the walnut pantry")
    )
    assert result == _png()
    assert seen["url"].endswith("/ai/run/@cf/black-forest-labs/flux-2-klein-4b")
    assert seen["authorization"] == "Bearer test-only-token"
    assert seen["content_type"].startswith("multipart/form-data; boundary=")
    assert b'name="input_image_0"' in seen["body"]
    assert b'name="prompt"' in seen["body"]
    assert b"Keep the walnut pantry" in seen["body"]
    assert b'name="width"\r\n\r\n1536' in seen["body"]
    assert b'name="height"\r\n\r\n864' in seen["body"]
    reference = seen["body"].split(b"Content-Type: image/png\r\n\r\n", 1)[1].split(b"\r\n--kuche7-", 1)[0]
    with Image.open(io.BytesIO(reference)) as image:
        assert image.format == "PNG"
        assert image.size == (500, 281)
    assert b"test-only-token" not in seen["body"]


def test_cloudflare_accepts_binary_image_and_returns_png(monkeypatch):
    jpeg = io.BytesIO()
    Image.new("RGB", (20, 12), "#694B39").save(jpeg, format="JPEG")
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: _Response(
        jpeg.getvalue(), "image/jpeg"))
    result = CloudflareImageEditProvider(ACCOUNT, "test-only-token").render(
        RenderRequest(_png(), "Neutral daylight"))
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "PNG" and image.size == (20, 12)


@pytest.mark.parametrize("model,has_steps", [
    ("@cf/black-forest-labs/flux-2-klein-4b", False),
    ("@cf/black-forest-labs/flux-2-dev", True),
    ("@cf/black-forest-labs/flux-2-klein-9b", False),
])
def test_cloudflare_model_comparison_uses_same_reference_and_supported_fields(
        monkeypatch, model, has_steps):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = request.data
        return _Response(json.dumps({"result": {"image": base64.b64encode(_png()).decode()}}).encode())

    monkeypatch.setattr("kuchhe7.rendering.urlopen", fake_urlopen)
    provider = CloudflareImageEditProvider(ACCOUNT, "test-only-token", model=model,
                                           comparison_prompt=COMPARISON_PROMPT)
    provider.render(RenderRequest(_png((1600, 900)), "Luxury kitchen presentation"))
    assert seen["url"].endswith("/ai/run/" + model)
    assert b'name="width"\r\n\r\n1536' in seen["body"]
    assert b'name="height"\r\n\r\n864' in seen["body"]
    assert (b'name="steps"\r\n\r\n25' in seen["body"]) == has_steps
    assert COMPARISON_PROMPT.encode() in seen["body"]
    reference = seen["body"].split(b"Content-Type: image/png\r\n\r\n", 1)[1].split(
        b"\r\n--kuche7-", 1)[0]
    with Image.open(io.BytesIO(reference)) as image:
        assert image.size == (500, 281)  # Strictly below the 512x512 reference limit.


def test_comparison_script_dry_run_never_calls_provider(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source.png"
    source.write_bytes(_png((1600, 900)))
    monkeypatch.setattr(CloudflareImageEditProvider, "render", lambda *_a: pytest.fail("network call"))
    output_dir = tmp_path / "results"
    assert compare_models(["--source", str(source), "--output-dir", str(output_dir)]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert not output_dir.exists()
    with pytest.raises(SystemExit):
        compare_models(["--source", str(source), "--output-dir", str(output_dir), "--execute"])
    assert not output_dir.exists()


def test_cloudflare_internal_model_configuration_preserves_klein_fallback(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-only-token")
    monkeypatch.delenv("KUCHE7_CLOUDFLARE_IMAGE_MODEL", raising=False)
    assert configured_image_provider("cloudflare").model.endswith("flux-2-klein-4b")
    monkeypatch.setenv("KUCHE7_CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-dev")
    assert configured_image_provider("cloudflare").model.endswith("flux-2-dev")
    monkeypatch.setenv("KUCHE7_CLOUDFLARE_IMAGE_MODEL", "unsupported")
    with pytest.raises(ValueError, match="Unsupported Cloudflare"):
        configured_image_provider("cloudflare")


@pytest.mark.parametrize("failure, expected", [
    (HTTPError("https://example.invalid", 401, "private", {}, None), "authentication"),
    (HTTPError("https://example.invalid", 429, "private", {}, None), "limit"),
    (TimeoutError(), "timed out"),
    (URLError("offline"), "network connection"),
])
def test_cloudflare_failures_do_not_expose_token(monkeypatch, failure, expected):
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: (_ for _ in ()).throw(failure))
    with pytest.raises(RuntimeError, match=expected) as error:
        CloudflareImageEditProvider(ACCOUNT, "test-only-token").render(
            RenderRequest(_png(), "Neutral daylight"))
    assert "test-only-token" not in str(error.value)


@pytest.mark.parametrize("raw", [b"{}", b"not-json", b'{"result":{"image":"garbage"}}',
                                 b'{"success":false,"errors":["private"]}'])
def test_cloudflare_rejects_invalid_response(monkeypatch, raw):
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: _Response(raw))
    with pytest.raises(RuntimeError, match="invalid or oversized"):
        CloudflareImageEditProvider(ACCOUNT, "test-only-token").render(
            RenderRequest(_png(), "Neutral daylight"))


def test_cloudflare_configuration_and_sample_workspace(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    assert configured_image_provider("cloudflare") is None
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-only-token")
    assert isinstance(configured_image_provider("cloudflare"), CloudflareImageEditProvider)
    monkeypatch.setattr("kuchhe7.ui.main_window.capture_view_png", lambda *_a: _png())
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("kuchhe7.rendering.urlopen", lambda *_a, **_k: _Response(json.dumps({
        "result": {"image": base64.b64encode(_png()).decode()}
    }).encode()))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.project = Project.complete_kitchen_demo()
    window.refresh_all(reset_camera=True)
    before = deepcopy(window.project.to_dict())
    bom = generate_project_bom(window.project)
    quote = calculate_quotation(window.project)
    nesting = nest_project(window.project)
    window.show_realistic_rendering()
    workspace = window.realistic_render_workspace
    workspace.provider_combo.setCurrentIndex(workspace.provider_combo.findData("cloudflare"))
    assert workspace.capture()
    assert workspace.generate()
    deadline = time.monotonic() + 5
    while workspace.render_in_progress and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert workspace.source_png == _png()
    assert workspace.result_png == _png()
    assert not workspace.before_label.pixmap().isNull()
    assert not workspace.after_label.pixmap().isNull()
    assert window.project.to_dict() == before
    assert generate_project_bom(window.project) == bom
    assert calculate_quotation(window.project) == quote
    assert nest_project(window.project) == nesting
    window.close()
