"""Stage 5A design proposals; interpretation never bypasses project validation.

The built-in provider is explicitly rule based. A configured HTTP provider may
translate prompts to the same small JSON contract, but geometry and catalogue
validation always run locally before a proposal can be applied.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .catalogue import FINISHES, create_catalogue_cabinet, get_catalogue_item
from .models import MAX_CABINETS, PlacedProduct, Project
from .product_libraries import APPLIANCES, PROPS, get_product


@dataclass(frozen=True)
class RequestedItem:
    type_id: str
    x: int | None = None
    y: int | None = None
    finish: str | None = None
    orientation_degrees: int = 0


@dataclass(frozen=True)
class DesignIntent:
    layout: str
    items: tuple[RequestedItem, ...]
    warnings: tuple[str, ...] = ()
    explanation: str = ""


@dataclass(frozen=True)
class ProposedItem:
    item_id: str
    type_id: str
    x: int
    y: int
    z: int
    width: int
    depth: int
    height: int
    finish: str
    orientation_degrees: int = 0


@dataclass
class DesignProposal:
    source: str
    mode: str
    intent: DesignIntent
    items: tuple[ProposedItem, ...]
    warnings: tuple[str, ...]
    after_project: Project
    base_fingerprint: str

    @property
    def can_apply(self) -> bool:
        return bool(self.items)


class DesignProvider(Protocol):
    name: str

    def interpret(self, prompt: str, project: Project) -> DesignIntent: ...


def project_fingerprint(project: Project) -> str:
    data = project.to_dict()
    data.pop("selected_cabinet_id", None)
    data.pop("selected_opening_id", None)
    return sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


class LocalRuleBasedProvider:
    name = "Local rule-based demonstration (not AI)"

    def interpret(self, prompt: str, project: Project) -> DesignIntent:
        text = prompt.strip().lower()
        if not text:
            return DesignIntent("unsupported", (), ("Enter a design request first.",))
        if re.search(r"\b(u[- ]?shaped|circular|round)\b", text):
            return DesignIntent("unsupported", (),
                                ("This demo supports straight and L-footprint layouts only.",))
        l_shape = bool(re.search(r"\bl[- ]?shaped\b|\bl shape\b|\bcorner kitchen\b", text))
        layout = "L footprint" if l_shape else "Straight run"
        warnings: list[str] = []
        if re.search(r"\b(rotate|rotated|90\s*degrees?|island)\b", text):
            warnings.append("Only 0, 90, 180 and 270 degree cabinet orientation is supported; island planning is unavailable.")
        if re.search(r"\b\d+(?:\.\d+)?\s*(?:mm|cm|metres?|meters?)\b", text):
            warnings.append("Requested custom measurements are not applied; catalogue dimensions are used.")
        if "hardware" in text or "hinge" in text or "runner" in text:
            warnings.append("Hardware must be assigned to a cabinet manually; no drilling is generated.")
        finish = next((value for value in FINISHES if value.lower() in text), None)
        width, depth = project.room.width, project.room.depth
        if l_shape:
            requests = [
                RequestedItem("corner_base", width - 900, depth - 900, finish),
                RequestedItem("base_2_door", 0, depth - 600, finish),
                RequestedItem("base_3_drawer", 900, depth - 600, finish),
                RequestedItem("sink_base", 1500, depth - 600, finish),
                RequestedItem("base_2_door", width - 600, depth - 1800, finish, 270),
                RequestedItem("wall_2_door", 0, depth - 350, finish),
            ]
        else:
            requests = [
                RequestedItem("base_2_door", 200, depth - 600, finish),
                RequestedItem("base_3_drawer", 1100, depth - 600, finish),
                RequestedItem("sink_base", 1700, depth - 600, finish),
                RequestedItem("wall_2_door", 200, depth - 350, finish),
            ]
        if "oven" in text:
            requests.append(RequestedItem("oven_freestanding", width - 700, 100))
        if "fridge" in text or "refrigerator" in text:
            requests.append(RequestedItem("fridge_tall", width - 800, 100))
        if "dishwasher" in text:
            requests.append(RequestedItem("dishwasher", width - 700, 900))
        if "plant" in text:
            requests.append(RequestedItem("plant_pot", 300, depth - 500))
        if "quartz" in text or "marble" in text:
            warnings.append("Requested surface material is unavailable; no surface specification was created.")
        return DesignIntent(layout, tuple(requests), tuple(warnings),
                            "Catalogue models and default dimensions were selected from the current room.")


class HttpJsonDesignProvider:
    """Adapter contract for a separately configured prompt-to-JSON service."""

    name = "Configured prompt-to-JSON service"

    def __init__(self, endpoint: str, api_key: str = "", timeout_seconds: float = 12) -> None:
        parsed = urlsplit(endpoint)
        if not (parsed.scheme == "https" or
                (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost"))):
            raise ValueError("AI endpoint must use HTTPS or local loopback HTTP.")
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def interpret(self, prompt: str, project: Project) -> DesignIntent:
        catalogue = [item.type_id for item in (*_all_cabinets(),)]
        catalogue.extend(item.type_id for item in _supported_products())
        payload = json.dumps({
            "prompt": prompt,
            "room_mm": {"width": project.room.width, "depth": project.room.depth,
                        "height": project.room.height},
            "openings": [vars(item) for item in project.room.openings],
            "catalogue_type_ids": catalogue,
            "instructions": "Return JSON with layout, items [{type_id,x,y,finish,orientation_degrees}], warnings. No invented dimensions or manufacturing rules.",
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(self.endpoint, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.load(response)
        except Exception as error:
            raise RuntimeError("Configured AI service is unavailable; no remote proposal was applied.") from error
        return parse_provider_response(data)


def _all_cabinets():
    from .catalogue import CATALOGUE, WARDROBE_CATALOGUE
    return (*CATALOGUE, *WARDROBE_CATALOGUE)


def _supported_products():
    from .product_libraries import PRODUCTS
    return tuple(item for item in PRODUCTS if item.library in (APPLIANCES, PROPS))


def parse_provider_response(data: object) -> DesignIntent:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("AI service response must contain an items array.")
    warnings = [str(item)[:200] for item in data.get("warnings", []) if isinstance(item, str)]
    requests: list[RequestedItem] = []

    def whole_mm(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("Position must be whole millimetres.")
        text = str(value)
        if not re.fullmatch(r"-?\d+", text):
            raise ValueError("Position must be whole millimetres.")
        return int(text)

    for entry in data["items"][:MAX_CABINETS + 8]:
        if not isinstance(entry, dict) or not isinstance(entry.get("type_id"), str):
            warnings.append("Ignored an item without a catalogue type ID.")
            continue
        if any(key in entry for key in ("width", "height", "depth", "board_thickness")):
            warnings.append(f"{entry['type_id']}: custom dimensions ignored; catalogue values are authoritative.")
        try:
            x, y = whole_mm(entry.get("x")), whole_mm(entry.get("y"))
            if (x is None) != (y is None):
                raise ValueError("Both X and Y are required for an explicit position.")
            orientation = int(entry.get("orientation_degrees", 0))
        except (TypeError, ValueError):
            warnings.append(f"{entry['type_id']}: invalid position or orientation ignored.")
            continue
        requests.append(RequestedItem(entry["type_id"], x, y, entry.get("finish"), orientation))
    if len(data["items"]) > MAX_CABINETS + 8:
        warnings.append("Additional service items were ignored to keep the proposal bounded.")
    return DesignIntent(str(data.get("layout", "Unspecified"))[:80], tuple(requests),
                        tuple(warnings), str(data.get("explanation", ""))[:300])


def configured_provider() -> DesignProvider:
    endpoint = os.environ.get("KUCHE7_AI_ENDPOINT", "").strip()
    if not endpoint:
        return LocalRuleBasedProvider()
    return HttpJsonDesignProvider(endpoint, os.environ.get("KUCHE7_AI_API_KEY", ""))


def _positions(project: Project, width: int, depth: int,
               preferred: tuple[int | None, int | None], allow_reposition: bool):
    seen = set()
    if preferred[0] is not None and preferred[1] is not None:
        seen.add(preferred)
        yield preferred
        if not allow_reposition:
            return
    for y in range(max(0, project.room.depth - depth), -1, -100):
        for x in range(0, max(0, project.room.width - width) + 1, 100):
            if (x, y) not in seen:
                yield x, y


def build_proposal(project: Project, intent: DesignIntent, *, source: str,
                   mode: str = "replace", allow_reposition: bool = True) -> DesignProposal:
    if mode not in ("add", "replace"):
        raise ValueError("Proposal mode must be add or replace.")
    project.validate()
    fingerprint = project_fingerprint(project)
    after = deepcopy(project)
    if mode == "replace":
        after.cabinets = []
        after.cabinet = None
        after.selected_cabinet_id = None
        after.placed_products = []
        after.hardware_assignments = []
        after.selected_opening_id = None
    warnings = list(intent.warnings)
    proposed: list[ProposedItem] = []
    first_cabinet_id = None
    for request in intent.items:
        if request.orientation_degrees not in (0, 90, 180, 270):
            warnings.append(f"{request.type_id}: unsupported orientation; item skipped.")
            continue
        try:
            item = get_catalogue_item(request.type_id)
        except ValueError:
            try:
                definition = get_product(request.type_id)
            except ValueError:
                warnings.append(f"{request.type_id}: no matching catalogue product; item skipped.")
                continue
            if definition.library not in (APPLIANCES, PROPS):
                warnings.append(f"{request.type_id}: hardware needs manual cabinet assignment; item skipped.")
                continue
            if request.orientation_degrees:
                warnings.append(f"{request.type_id}: product orientation is unavailable; item skipped.")
                continue
            item_id = after.next_product_id(definition.library)
            error = None
            for x, y in _positions(after, definition.width, definition.depth,
                                    (request.x, request.y), allow_reposition):
                candidate = PlacedProduct(item_id, request.type_id, x, y,
                                          definition.elevation_z, definition.width,
                                          definition.depth, definition.height)
                try:
                    after.validate_product_placement(candidate)
                    after.add_product(candidate)
                    if request.x is not None and request.y is not None and (x, y) != (request.x, request.y):
                        warnings.append(f"{request.type_id}: moved to valid X {x}, Y {y} mm.")
                    proposed.append(ProposedItem(item_id, request.type_id, x, y,
                                                 candidate.elevation_z, candidate.width,
                                                 candidate.depth, candidate.height, "Catalogue"))
                    break
                except ValueError as caught:
                    error = str(caught)
            else:
                warnings.append(f"{request.type_id}: no valid room position ({error or 'outside room'}).")
            continue
        if len(after.cabinets) >= MAX_CABINETS:
            warnings.append(f"{request.type_id}: {MAX_CABINETS}-cabinet demo limit reached.")
            continue
        cabinet_id = after.next_cabinet_id()
        cabinet = create_catalogue_cabinet(request.type_id, cabinet_id)
        cabinet.orientation_degrees = request.orientation_degrees
        if request.finish is not None:
            if request.finish in item.supported_finishes:
                cabinet.material = request.finish
            else:
                warnings.append(f"{request.type_id}: unsupported finish {request.finish!r}; using catalogue default.")
        error = None
        for x, y in _positions(after, cabinet.footprint_width, cabinet.footprint_depth,
                                (request.x, request.y), allow_reposition):
            cabinet.position_x, cabinet.position_y = x, y
            try:
                if cabinet.elevation_z + cabinet.height > after.room.height:
                    raise ValueError("Cabinet exceeds the room wall height.")
                after.validate_cabinet_placement(cabinet)
                after.add_cabinet(cabinet)
                if request.x is not None and request.y is not None and (x, y) != (request.x, request.y):
                    warnings.append(f"{request.type_id}: moved to valid X {x}, Y {y} mm.")
                first_cabinet_id = first_cabinet_id or cabinet_id
                proposed.append(ProposedItem(cabinet_id, request.type_id, x, y,
                                             cabinet.elevation_z, cabinet.width,
                                             cabinet.depth, cabinet.height, cabinet.material,
                                             cabinet.orientation_degrees))
                break
            except ValueError as caught:
                error = str(caught)
        else:
            warnings.append(f"{request.type_id}: no valid room position ({error or 'outside room'}).")
    if first_cabinet_id:
        after.select_cabinet(first_cabinet_id)
    after.validate()
    return DesignProposal(source, mode, intent, tuple(proposed), tuple(warnings), after, fingerprint)
