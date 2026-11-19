"""Local, revisioned cabinet library; construction still uses existing demo templates."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .catalogue import (CATALOGUE, FINISHES, WARDROBE_CATALOGUE, CatalogueItem,
                        catalogue_item_from_dict, register_custom_items, set_company_custom_items)


BASE_TEMPLATES = {item.type_id: item for item in (*CATALOGUE, *WARDROBE_CATALOGUE)}


def custom_catalogue_path() -> Path:
    override = os.environ.get("KUCHE7_CABINET_LIBRARY_PATH")
    if override:
        return Path(override).expanduser()
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not root:
        raise OSError("No writable application data directory is available for the cabinet library.")
    return Path(root) / "custom-cabinet-library.json"


def validate_custom_item(item: CatalogueItem) -> None:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{2,31}", item.product_id):
        raise ValueError("Product ID needs 3–32 letters, digits, underscores or hyphens, starting with a letter.")
    if item.type_id != f"custom_{item.product_id.lower()}__v{item.revision}" or item.revision < 1:
        raise ValueError("Custom cabinet revision ID is invalid.")
    if not item.name.strip():
        raise ValueError("Cabinet name is required.")
    if item.template_id not in BASE_TEMPLATES:
        raise ValueError("Choose an existing supported construction template.")
    template = BASE_TEMPLATES[item.template_id]
    if item.category != template.category or item.front_style != template.front_style:
        raise ValueError("Category and front style must match the selected construction template.")
    for value, lower, upper, label in (
        (item.width, item.min_width, item.max_width, "Width"),
        (item.height, item.min_height, item.max_height, "Height"),
        (item.depth, item.min_depth, item.max_depth, "Depth"),
    ):
        if not (lower <= value <= upper) or lower <= 0 or upper <= 0:
            raise ValueError(f"{label} default must be inside its positive supported range.")
    if item.min_width < 300 or item.max_width > 3000 or item.min_height < 300 or item.max_height > 3000 or item.min_depth < 200 or item.max_depth > 1200:
        raise ValueError("Custom limits must stay within the existing demo engineering ranges.")
    if not 10 <= item.board_thickness <= 50 or item.min_width <= 2 * item.board_thickness or item.min_height <= 2 * item.board_thickness:
        raise ValueError("Board thickness is outside the supported demo geometry.")
    if item.default_finish not in FINISHES or item.default_finish not in item.supported_finishes:
        raise ValueError("Choose a supported default finish.")
    if not 0 <= item.door_count <= 6 or not 0 <= item.drawer_count <= 8 or not 0 <= item.shelf_count <= 10:
        raise ValueError("Door, drawer or shelf count is outside existing demo limits.")
    if item.front_style == "drawers" and item.door_count:
        raise ValueError("Drawer construction template does not support doors.")
    if item.front_style != "drawers" and item.drawer_count:
        raise ValueError("This construction template does not support drawers.")
    if item.front_style == "open" and item.door_count:
        raise ValueError("Open-shelf construction template does not support doors.")
    if item.hardware_defaults and set(item.hardware_defaults) != {"handle_bar"}:
        raise ValueError("Only optional bar-handle assignments are supported in custom templates.")
    if any(not isinstance(qty, int) or qty < 1 or qty > 20 for qty in item.hardware_defaults.values()):
        raise ValueError("Handle quantity must be between 1 and 20.")


def create_custom_revision(items: list[CatalogueItem], *, product_id: str, name: str,
                           template_id: str, width: int, height: int, depth: int,
                           board_thickness: int, door_count: int, drawer_count: int,
                           shelf_count: int, default_finish: str,
                           min_width: int, max_width: int, min_height: int, max_height: int,
                           min_depth: int, max_depth: int, handle_quantity: int = 0) -> CatalogueItem:
    if template_id not in BASE_TEMPLATES:
        raise ValueError("Unknown construction template.")
    existing = [item for item in items if item.product_id.casefold() == product_id.casefold()]
    if existing and any(item.product_id != product_id for item in existing):
        raise ValueError("Product ID differs only by letter case from an existing product.")
    revision = max((item.revision for item in existing), default=0) + 1
    template = BASE_TEMPLATES[template_id]
    item = replace(template, type_id=f"custom_{product_id.lower()}__v{revision}",
                   product_id=product_id, revision=revision, name=name.strip(),
                   template_id=template_id, width=width, height=height, depth=depth,
                   board_thickness=board_thickness, door_count=door_count,
                   drawer_count=drawer_count, shelf_count=shelf_count,
                   default_finish=default_finish, min_width=min_width, max_width=max_width,
                   min_height=min_height, max_height=max_height,
                   min_depth=min_depth, max_depth=max_depth,
                   hardware_defaults={"handle_bar": handle_quantity} if handle_quantity else {})
    validate_custom_item(item)
    return item


def load_custom_catalogue(path: str | Path | None = None) -> list[CatalogueItem]:
    source = Path(path) if path is not None else custom_catalogue_path()
    if not source.is_file():
        set_company_custom_items([])
        return []
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("items"), list):
        raise ValueError("Custom cabinet library has an unsupported format.")
    items = [catalogue_item_from_dict(row) for row in data["items"]]
    if len({item.type_id for item in items}) != len(items):
        raise ValueError("Custom cabinet revision IDs must be unique.")
    for item in items:
        validate_custom_item(item)
    set_company_custom_items(items)
    return items


def save_custom_catalogue(items: list[CatalogueItem], path: str | Path | None = None) -> Path:
    destination = Path(path) if path is not None else custom_catalogue_path()
    if len({item.type_id for item in items}) != len(items):
        raise ValueError("Custom cabinet revision IDs must be unique.")
    for item in items:
        validate_custom_item(item)
    register_custom_items(items)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps({"schema_version": 1,
                                     "items": [asdict(item) for item in items]}, indent=2), encoding="utf-8")
    os.replace(temporary, destination)
    set_company_custom_items(items)
    return destination
