"""Presentation image capture and optional image-input provider contract.

Rendered images are detached from the project and never enter manufacturing data.
"""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
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


def configured_image_provider() -> ImageRenderProvider | None:
    endpoint = os.environ.get("KUCHE7_RENDER_ENDPOINT", "").strip()
    if not endpoint:
        return None
    return HttpJsonImageProvider(endpoint, os.environ.get("KUCHE7_RENDER_API_KEY", ""))
