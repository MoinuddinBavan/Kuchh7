"""Presentation image capture and optional image-input provider contract.

Rendered images are detached from the project and never enter manufacturing data.
"""

from __future__ import annotations

import base64
import io
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image


STYLES = (
    "Modern realistic kitchen",
    "Warm interior lighting",
    "Neutral daylight",
    "Luxury kitchen presentation",
)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
OPENAI_IMAGE_EDIT_URL = "https://api.openai.com/v1/images/edits"
OPENAI_IMAGE_MODELS = ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2.6-sunburst", "gpt-image-2.6-flare")
OPENAI_IMAGE_QUALITIES = ("low", "medium", "high")
OPENAI_IMAGE_SIZES = ("1024x1024", "1536x1024", "1024x1536")
MAX_OPENAI_DATA_URL_LENGTH = 20_971_520
MAX_PROVIDER_RESPONSE_BYTES = 30 * 1024 * 1024


@dataclass(frozen=True)
class RenderRequest:
    source_png: bytes
    style: str
    instructions: str = ""

    def validate(self) -> None:
        validate_png(self.source_png)
        if self.style not in STYLES:
            raise ValueError("Choose a supported presentation style.")
        if len(self.instructions) > 1000:
            raise ValueError("Presentation instructions must be 1,000 characters or less.")


class ImageRenderProvider(Protocol):
    name: str

    def render(self, request: RenderRequest) -> bytes: ...


def validate_png(data: bytes) -> None:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("PNG image is empty or exceeds the 20 MB demo limit.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG":
                raise ValueError("Provider image must be PNG.")
            if image.width > 4096 or image.height > 4096 or image.width * image.height > 16_000_000:
                raise ValueError("PNG dimensions exceed the presentation image limit.")
            image.verify()
    except (OSError, SyntaxError) as error:
        raise ValueError("Invalid PNG image.") from error


def capture_view_png(view, camera: str = "Current", resolution: tuple[int, int] = (1600, 900)) -> bytes:
    """Capture the existing PyVista scene; camera changes are restored afterward."""
    if camera not in ("Current", "Front", "Isometric", "Presentation"):
        raise ValueError("Unknown camera view.")
    width, height = resolution
    if not 320 <= width <= 4096 or not 240 <= height <= 4096:
        raise ValueError("Capture resolution is outside the supported range.")
    plotter = view.plotter
    previous_position = plotter.camera_position
    previous_angle = plotter.camera.view_angle
    try:
        if camera == "Front":
            view.view_front()
        elif camera == "Isometric":
            view.view_isometric()
        elif camera == "Presentation":
            view.view_presentation()
        pixels = plotter.screenshot(return_img=True, window_size=(width, height))
        if pixels is None:
            raise RuntimeError("The 3D viewport did not return an image.")
        output = io.BytesIO()
        Image.fromarray(pixels).convert("RGB").save(output, format="PNG")
        return output.getvalue()
    finally:
        plotter.camera_position = previous_position
        plotter.camera.view_angle = previous_angle
        plotter.render()


def save_png(data: bytes, path: str | Path) -> None:
    validate_png(data)
    Path(path).write_bytes(data)


class HttpJsonImageProvider:
    """Optional approved service adapter: POST PNG base64, receive PNG base64.

    The service must support image input and return JSON {image_base64: ...}.
    No project JSON, dimensions, names or credentials are sent in the payload.
    """

    name = "Configured image provider"

    def __init__(self, endpoint: str, api_key: str = "", timeout_seconds: float = 90) -> None:
        parsed = urlsplit(endpoint)
        if not (parsed.scheme == "https" or
                (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))):
            raise ValueError("Rendering endpoint must use HTTPS or local loopback HTTP.")
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def render(self, request: RenderRequest) -> bytes:
        request.validate()
        payload = json.dumps({
            "image_base64": base64.b64encode(request.source_png).decode("ascii"),
            "style": request.style,
            "instructions": request.instructions,
            "output_format": "png",
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with urlopen(Request(self.endpoint, data=payload, headers=headers, method="POST"),
                         timeout=self.timeout_seconds) as response:
                result = json.load(response)
            image_data = base64.b64decode(result["image_base64"], validate=True)
            validate_png(image_data)
            return image_data
        except Exception as error:
            raise RuntimeError("Rendering service failed or returned an invalid PNG image.") from error


def realistic_edit_prompt(request: RenderRequest) -> str:
    """Presentation guidance; the image remains the sole design reference."""
    request.validate()
    prompt = (
        "Edit the supplied 3D kitchen design image into a photorealistic client presentation. "
        "Use the input image as the composition and layout reference. Keep the same camera viewpoint, "
        "visible cabinet count and arrangement, approximate cabinet proportions, wall openings, "
        "appliances, sink, countertop, decorative props and selected material colours. "
        "Do not add, remove, move or resize furniture or change the room layout. "
        "Improve only realistic material texture, lighting and interior atmosphere. "
        "Avoid labels, dimension marks and invented products. "
        f"Presentation style: {request.style}."
    )
    if request.instructions:
        prompt += f" Additional visual instructions: {request.instructions.strip()}"
    return prompt


class OpenAIImageEditProvider:
    """OpenAI Images API edit adapter using the captured PNG as image input.

    Uses the documented JSON image_url data-URI request and GPT Image base64
    response. This class does not know about Project, BOM or manufacturing data.
    """

    def __init__(self, api_key: str, *, model: str = "gpt-image-2.5-sunburst",
                 quality: str = "medium", size: str = "1536x1024",
                 timeout_seconds: float = 90) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is not configured.")
        if model not in OPENAI_IMAGE_MODELS:
            raise ValueError("Unsupported OpenAI image-editing model.")
        if quality not in OPENAI_IMAGE_QUALITIES:
            raise ValueError("Unsupported OpenAI image quality.")
        if size not in OPENAI_IMAGE_SIZES:
            raise ValueError("Unsupported OpenAI image size.")
        if timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be positive.")
        self.api_key = api_key.strip()
        self.model = model
        self.quality = quality
        self.size = size
        self.timeout_seconds = timeout_seconds
        self.name = f"OpenAI image edit ({model}, {quality})"

    def render(self, request: RenderRequest) -> bytes:
        request.validate()
        image_url = "data:image/png;base64," + base64.b64encode(request.source_png).decode("ascii")
        if len(image_url) > MAX_OPENAI_DATA_URL_LENGTH:
            raise ValueError("3D capture is too large for the OpenAI image-edit input. Use a smaller capture.")
        payload = json.dumps({
            "model": self.model,
            "images": [{"image_url": image_url}],
            "prompt": realistic_edit_prompt(request),
            "quality": self.quality,
            "size": self.size,
            "output_format": "png",
            "n": 1,
        }).encode("utf-8")
        http_request = Request(
            OPENAI_IMAGE_EDIT_URL, data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
            if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
                raise ValueError("OpenAI response exceeds the presentation image limit.")
            result = json.loads(raw)
            encoded = result["data"][0]["b64_json"]
            image_data = base64.b64decode(encoded, validate=True)
            validate_png(image_data)
            return image_data
        except HTTPError as error:
            if error.code in (401, 403):
                raise RuntimeError("OpenAI authentication or model access failed. Check the configured API key and permissions.") from error
            if error.code == 429:
                raise RuntimeError("OpenAI rate or usage limit reached. Retry later or check usage controls.") from error
            raise RuntimeError(f"OpenAI image edit failed (HTTP {error.code}).") from error
        except (TimeoutError, socket.timeout) as error:
            raise RuntimeError("OpenAI image edit timed out. Retry the request.") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise RuntimeError("OpenAI image edit timed out. Retry the request.") from error
            raise RuntimeError("OpenAI network connection failed. Check connectivity and retry.") from error
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise RuntimeError("OpenAI returned an invalid or oversized PNG image response.") from error


def configured_image_provider() -> ImageRenderProvider | None:
    choice = os.environ.get("KUCHE7_RENDER_PROVIDER", "").strip().lower()
    if choice not in ("", "openai", "custom"):
        raise ValueError("KUCHE7_RENDER_PROVIDER must be openai or custom.")
    endpoint = os.environ.get("KUCHE7_RENDER_ENDPOINT", "").strip()
    if choice == "custom" or (not choice and endpoint):
        return HttpJsonImageProvider(endpoint, os.environ.get("KUCHE7_RENDER_API_KEY", "")) if endpoint else None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAIImageEditProvider(
        api_key,
        model=os.environ.get("KUCHE7_OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst").strip(),
        quality=os.environ.get("KUCHE7_OPENAI_IMAGE_QUALITY", "medium").strip(),
        size=os.environ.get("KUCHE7_OPENAI_IMAGE_SIZE", "1536x1024").strip(),
    )
