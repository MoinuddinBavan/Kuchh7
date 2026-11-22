"""Presentation image capture and optional image-input provider contract.

Rendered images are detached from the project and never enter manufacturing data.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

if TYPE_CHECKING:
    from .models import Project


STYLES = (
    "Modern realistic kitchen",
    "Warm interior lighting",
    "Neutral daylight",
    "Luxury kitchen presentation",
    "Dark Luxury Kitchen",
    "Moody Evening Kitchen",
    "Black & Walnut Premium",
)
CONCEPT_STYLES = frozenset(("Dark Luxury Kitchen", "Black & Walnut Premium"))
STYLE_GUIDANCE = {
    "Modern realistic kitchen": (
        "Modern realistic kitchen: produce a premium contemporary architectural photograph of this "
        "same kitchen. Render clean modern finishes with fine, physically believable matte texture, "
        "crisp cabinet joinery and detailed door and drawer surfaces. Balance daylight with gentle "
        "ambient illumination; use natural contact shadows, restrained reflections and an understated "
        "neutral colour balance. Keep existing wood and stone character rather than replacing finishes."
    ),
    "Warm interior lighting": (
        "Warm interior lighting: make a photorealistic, welcoming architectural photograph of this "
        "same kitchen. Layer sophisticated warm ambient and practical lighting with soft daylight; "
        "suggest subtle under-cabinet light only where it could naturally illuminate the existing "
        "worktop, without adding fixtures or changing cabinetry. Show smooth light falloff, soft shadow "
        "gradients, believable material reflections and rich but restrained wood grain. Keep the "
        "original cabinet colours identifiable without an orange cast."
    ),
    "Neutral daylight": (
        "Neutral daylight: create an exceptionally realistic architectural photograph of this same "
        "kitchen in soft natural daylight from the openings visible in the reference. Use accurate "
        "material colours, neutral white balance and balanced exposure without blown highlights or "
        "crushed shadows. Reveal believable cabinet and countertop surface textures, gentle "
        "reflections, natural contact shadows and clean room surfaces."
    ),
    "Luxury kitchen presentation": (
        "Luxury kitchen presentation: create an exceptionally high-quality architectural interior "
        "photograph of this same kitchen. Give the existing finishes premium yet faithful microtexture, "
        "realistic wood grain and precise cabinet joinery. Blend refined natural and discreet practical "
        "light, sophisticated shadow detail and controlled reflections on stone and metal. Use balanced "
        "exposure, rich but accurate contrast and professional interior photography composition while "
        "retaining the reference viewpoint."
    ),
    "Dark Luxury Kitchen": (
        "Dark Luxury Kitchen: present the existing cabinetry as a high-end dark interior concept, "
        "with physically believable deep charcoal cabinet surfaces, premium dark walnut on existing "
        "wood elements and refined dark stone where stone is visible. Reveal realistic wood grain, "
        "panel joinery and individual door and drawer fronts with controlled grazing light. Use "
        "sophisticated layered ambient lighting, soft contact shadows and subtle rough reflections. "
        "Balance exposure so every cabinet remains visible and dimensional; create real dark "
        "materials and light interaction, not a dark filter."
    ),
    "Moody Evening Kitchen": (
        "Moody Evening Kitchen: photograph the same finishes in a welcoming evening atmosphere. "
        "Preserve the source cabinet colours while replacing daylight ambience with soft warm "
        "practical illumination and tasteful under-cabinet glow where it naturally lights an existing "
        "worktop, without adding visible fixtures. Show realistic light falloff, rich natural shadow "
        "gradients, believable reflections and detailed wood texture. Keep cabinet fronts legible and "
        "the scene warmly exposed rather than excessively dark."
    ),
    "Black & Walnut Premium": (
        "Black & Walnut Premium: create a dramatic but believable modern interior concept using "
        "black accents, natural dark walnut on existing wood cabinetry and refined stone detail on "
        "existing surfaces. Show tactile grain, realistic material roughness, crisp cabinet fronts "
        "and handles, and deep spatial contrast. Use precise architectural light with warm highlights "
        "and restrained reflections so the cabinetry stays clear, richly textured and naturally "
        "coloured rather than uniformly black or artificially tinted."
    ),
}
MASTER_RENDER_PROMPT = (
    "Transform the provided KÜCHE7 3D kitchen reference image into a professional photorealistic "
    "architectural visualization. Treat input image 0 as the primary design reference.\n\n"
    "DESIGN PRESERVATION: Preserve cabinet count, cabinet types, positions, proportions, door "
    "configurations, door and drawer counts, shelves, tall pantry cabinets, countertops, sink locations "
    "and visible hardware. Preserve the same camera viewpoint and framing and the original spatial "
    "arrangement. Do not add, delete, move or replace cabinets. A tall storage pantry is never a "
    "refrigerator. Do not add an island.\n\n"
    "MATERIAL PRESERVATION: Read the actual cabinet colours, wood finishes and countertop materials "
    "from the source. Preserve their light/dark contrast and material identity as closely as possible "
    "unless the selected dark concept explicitly allows presentation-only finish exploration.\n\n"
    "ROOM AND OPENING PRESERVATION: Preserve all visible doors, windows, sliding doors, open doorways "
    "and architectural wall openings. Keep the same number of room openings, their original locations, "
    "approximate dimensions, proportions and relationships to nearby walls and cabinets. Do not cover "
    "openings with cabinets, appliances, decorative objects or invented structural elements. If a "
    "window looks pale or washed out, add believable framing, glass reflections and daylight without "
    "changing its geometry. If a doorway looks white or blank, retain its opening and clarify its "
    "existing edges; do not automatically convert a blank doorway into a glass door or window. If "
    "an opening type is unclear, preserve the visible shape rather than inventing a new type. Never "
    "create additional doors, windows or wall openings.\n\n"
    "PHOTOREALISM: Improve physically believable materials, wood grain, surface roughness, cabinet "
    "joinery, natural contact shadows and shadow gradients, material roughness and reflections, wall "
    "finish, floor appearance and professional interior photography exposure. Keep cabinet fronts, "
    "drawers, doors and handles clear. Avoid artificial lighting, excessive brightness, flat or "
    "plastic-looking surfaces, unrealistic gloss and exaggerated shadows. Photograph the same "
    "kitchen rather than redesigning it. This image is for visual presentation only; it does not "
    "modify or certify manufacturing geometry."
)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
OPENAI_IMAGE_EDIT_URL = "https://api.openai.com/v1/images/edits"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_IMAGE_MODELS = ("gemini-nano-banana-2.1", "gemini-3.1-flash-image")
CLOUDFLARE_IMAGE_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
CLOUDFLARE_IMAGE_MODELS = (
    CLOUDFLARE_IMAGE_MODEL,
    "@cf/black-forest-labs/flux-2-dev",
    "@cf/black-forest-labs/flux-2-klein-9b",
)
CLOUDFLARE_DEV_STEPS = 25
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
    design_context: str = ""

    def validate(self) -> None:
        validate_png(self.source_png)
        if self.style not in STYLES:
            raise ValueError("Choose a supported presentation style.")
        if len(self.instructions) > 1000:
            raise ValueError("Presentation instructions must be 1,000 characters or less.")
        if len(self.design_context) > 4000:
            raise ValueError("Rendering design context exceeds the demo limit.")


def project_render_context(project: Project) -> str:
    """Read-only, compact design facts; excludes names, prices and manufacturing data."""
    def label(value: object) -> str:
        return re.sub(r"[^A-Za-z0-9 &_-]", "", str(value))[:48].strip()

    room = project.room
    cabinets = "; ".join(
        f"{label(item.cabinet_id)} {label(item.cabinet_type_id)}: {label(item.material)} finish, "
        f"{item.width}x{item.height}x{item.depth} mm, "
        f"position x={item.position_x}, y={item.position_y}, z={item.elevation_z} mm, "
        f"{item.door_count} doors, {item.drawer_count} drawers"
        for item in project.cabinets
    ) or "none"
    openings = "; ".join(
        f"{label(item.kind)} on {label(item.wall_id)} wall, offset {item.offset} mm, "
        f"{item.width}x{item.height} mm, elevation {item.elevation} mm"
        for item in room.openings
    ) or "none recorded"
    return (
        f"PROJECT DESIGN FACTS (use only to clarify what is visible in input image 0; do not add "
        f"unseen objects): room {room.width}x{room.depth}x{room.height} mm. "
        f"Cabinets: {cabinets}. Room openings: {openings}."
    )


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
    finish_policy = (
        "This is a presentation-only dark finish concept: the rendered surfaces may explore darker "
        "charcoal, black, walnut or stone tones, but keep the same material roles and do not alter the "
        "underlying KÜCHE7 project finishes or quantities. "
        if request.style in CONCEPT_STYLES else
        "Preserve the source cabinet and countertop material colours and finishes; change atmosphere "
        "and surface realism, not the selected finishes. "
    )
    prompt = f"{MASTER_RENDER_PROMPT}\n\n{finish_policy}"
    if request.design_context.strip():
        prompt += f"\n{request.design_context.strip()}"
    prompt += f"\nSTYLE DIRECTION: {STYLE_GUIDANCE[request.style]}"
    if request.instructions.strip():
        prompt += (" Optional user preferences apply only to presentation and lighting, and only where "
                   f"they preserve the reference design: {request.instructions.strip()}")
    prompt += ("\nDesign preservation takes priority over style or optional instructions; keep the "
               "reference layout, architectural openings, cabinet fronts and camera perspective, "
               "and follow the finish policy above.")
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


class GeminiImageEditProvider:
    """Gemini Interactions image edit; only the captured PNG and prompt leave the app."""

    def __init__(self, api_key: str, *, model: str = "gemini-nano-banana-2.1",
                 timeout_seconds: float = 90) -> None:
        if not api_key.strip():
            raise ValueError("Gemini API key is not configured.")
        if model not in GEMINI_IMAGE_MODELS:
            raise ValueError("Unsupported Gemini image-editing model.")
        if timeout_seconds <= 0:
            raise ValueError("Gemini timeout must be positive.")
        self.api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.name = f"Gemini image edit ({model})"

    def render(self, request: RenderRequest) -> bytes:
        request.validate()
        payload = json.dumps({
            "model": self.model,
            "input": [
                {"type": "text", "text": realistic_edit_prompt(request)},
                {"type": "image", "mime_type": "image/png",
                 "data": base64.b64encode(request.source_png).decode("ascii")},
            ],
        }).encode("utf-8")
        http_request = Request(
            GEMINI_INTERACTIONS_URL, data=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key,
                     "Api-Revision": "2026-05-20"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
            if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
                raise ValueError("Gemini response exceeds the presentation image limit.")
            result = json.loads(raw)
            interaction = result.get("interaction", result)
            output = interaction.get("output_image") or interaction.get("outputImage")
            if not output:
                for step in interaction.get("steps", []):
                    if step.get("type") == "model_output":
                        output = next((item for item in step.get("content", [])
                                       if item.get("type") == "image"), None)
                        if output:
                            break
            image_data = base64.b64decode(output["data"], validate=True)
            if len(image_data) > MAX_IMAGE_BYTES:
                raise ValueError("Gemini image exceeds the presentation image limit.")
            with Image.open(io.BytesIO(image_data)) as image:
                if image.format not in ("PNG", "JPEG", "WEBP"):
                    raise ValueError("Unsupported Gemini image format.")
                if image.width > 4096 or image.height > 4096 or image.width * image.height > 16_000_000:
                    raise ValueError("Gemini image dimensions exceed the presentation image limit.")
                png = io.BytesIO()
                image.convert("RGB").save(png, format="PNG")
            image_data = png.getvalue()
            validate_png(image_data)
            return image_data
        except HTTPError as error:
            if error.code in (401, 403):
                raise RuntimeError("Gemini authentication or model access failed. Check the API key and permissions.") from error
            if error.code == 429:
                raise RuntimeError("Gemini rate or usage limit reached. Retry later or check usage controls.") from error
            raise RuntimeError(f"Gemini image edit failed (HTTP {error.code}).") from error
        except (TimeoutError, socket.timeout) as error:
            raise RuntimeError("Gemini image edit timed out. Retry the request.") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise RuntimeError("Gemini image edit timed out. Retry the request.") from error
            raise RuntimeError("Gemini network connection failed. Check connectivity and retry.") from error
        except (ValueError, KeyError, IndexError, TypeError, OSError, AttributeError) as error:
            raise RuntimeError("Gemini returned an invalid or oversized image response.") from error


class CloudflareImageEditProvider:
    """Workers AI FLUX.2 image edit using one reduced 3D PNG reference."""

    def __init__(self, account_id: str, api_token: str, *,
                 model: str = CLOUDFLARE_IMAGE_MODEL,
                 timeout_seconds: float = 120,
                 comparison_prompt: str | None = None) -> None:
        if not re.fullmatch(r"[A-Fa-f0-9]{32}", account_id.strip()):
            raise ValueError("Cloudflare account ID must be a 32-character hexadecimal value.")
        if not api_token.strip():
            raise ValueError("Cloudflare API token is not configured.")
        if model not in CLOUDFLARE_IMAGE_MODELS:
            raise ValueError("Unsupported Cloudflare image-editing model.")
        if timeout_seconds <= 0:
            raise ValueError("Cloudflare timeout must be positive.")
        if comparison_prompt is not None and not comparison_prompt.strip():
            raise ValueError("Comparison prompt must not be empty.")
        self.account_id = account_id.strip()
        self.api_token = api_token.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.comparison_prompt = comparison_prompt
        self.name = f"Cloudflare Workers AI ({model.rsplit('/', 1)[-1]})"

    def render(self, request: RenderRequest) -> bytes:
        request.validate()
        with Image.open(io.BytesIO(request.source_png)) as image:
            reference = ImageOps.contain(image.convert("RGB"), (500, 500), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            reference.save(output, format="PNG")
        reference_png = output.getvalue()
        boundary = f"kuche7-{uuid.uuid4().hex}"
        body = bytearray()
        fields = [("prompt", self.comparison_prompt or realistic_edit_prompt(request)),
                  ("width", "1536"), ("height", "864")]
        if self.model == "@cf/black-forest-labs/flux-2-dev":
            fields.append(("steps", str(CLOUDFLARE_DEV_STEPS)))
        for name, value in fields:
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode())
            body.extend(value.encode("utf-8"))
            body.extend(b"\r\n")
        body.extend((f"--{boundary}\r\nContent-Disposition: form-data; name=\"input_image_0\"; "
                     "filename=\"kitchen-reference.png\"\r\nContent-Type: image/png\r\n\r\n").encode())
        body.extend(reference_png)
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        endpoint = (f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
                    f"/ai/run/{self.model}")
        http_request = Request(endpoint, data=bytes(body), headers={
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }, method="POST")
        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                content_type = response.headers.get("Content-Type", "").lower()
            if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
                raise ValueError("Cloudflare response exceeds the presentation image limit.")
            if content_type.startswith("image/"):
                image_data = raw
            else:
                result = json.loads(raw)
                if result.get("success") is False:
                    raise ValueError("Cloudflare returned no generated image.")
                encoded = result["result"]["image"]
                if encoded.startswith("data:image/"):
                    encoded = encoded.split(",", 1)[1]
                image_data = base64.b64decode(encoded, validate=True)
            if len(image_data) > MAX_IMAGE_BYTES:
                raise ValueError("Cloudflare image exceeds the presentation image limit.")
            with Image.open(io.BytesIO(image_data)) as image:
                if image.format not in ("PNG", "JPEG", "WEBP"):
                    raise ValueError("Unsupported Cloudflare image format.")
                if image.width > 4096 or image.height > 4096 or image.width * image.height > 16_000_000:
                    raise ValueError("Cloudflare image dimensions exceed the presentation image limit.")
                output = io.BytesIO()
                image.convert("RGB").save(output, format="PNG")
            image_data = output.getvalue()
            validate_png(image_data)
            return image_data
        except HTTPError as error:
            if error.code in (401, 403):
                raise RuntimeError("Cloudflare authentication or model access failed. Check the token and permissions.") from error
            if error.code == 429:
                raise RuntimeError("Cloudflare rate or usage limit reached. Retry later or check usage controls.") from error
            raise RuntimeError(f"Cloudflare image edit failed (HTTP {error.code}).") from error
        except (TimeoutError, socket.timeout) as error:
            raise RuntimeError("Cloudflare image edit timed out. Retry the request.") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise RuntimeError("Cloudflare image edit timed out. Retry the request.") from error
            raise RuntimeError("Cloudflare network connection failed. Check connectivity and retry.") from error
        except (ValueError, KeyError, IndexError, TypeError, OSError, AttributeError) as error:
            raise RuntimeError("Cloudflare returned an invalid or oversized image response.") from error


def configured_image_provider(choice: str | None = None) -> ImageRenderProvider | None:
    choice = (choice if choice is not None else os.environ.get("KUCHE7_RENDER_PROVIDER", "")).strip().lower()
    if choice not in ("", "openai", "gemini", "cloudflare", "custom"):
        raise ValueError("KUCHE7_RENDER_PROVIDER must be openai, gemini, cloudflare or custom.")
    endpoint = os.environ.get("KUCHE7_RENDER_ENDPOINT", "").strip()
    if choice == "custom" or (not choice and endpoint):
        return HttpJsonImageProvider(endpoint, os.environ.get("KUCHE7_RENDER_API_KEY", "")) if endpoint else None
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if choice == "gemini" or (not choice and gemini_key and not os.environ.get("OPENAI_API_KEY", "").strip()):
        return GeminiImageEditProvider(
            gemini_key,
            model=os.environ.get("KUCHE7_GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1").strip(),
        ) if gemini_key else None
    if choice == "cloudflare" or (not choice and not os.environ.get("OPENAI_API_KEY", "").strip()):
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        model = os.environ.get("KUCHE7_CLOUDFLARE_IMAGE_MODEL", CLOUDFLARE_IMAGE_MODEL).strip()
        return CloudflareImageEditProvider(account_id, api_token, model=model) if account_id and api_token else None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAIImageEditProvider(
        api_key,
        model=os.environ.get("KUCHE7_OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst").strip(),
        quality=os.environ.get("KUCHE7_OPENAI_IMAGE_QUALITY", "medium").strip(),
        size=os.environ.get("KUCHE7_OPENAI_IMAGE_SIZE", "1536x1024").strip(),
    )
