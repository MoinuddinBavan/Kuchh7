"""Local company Price Setup, copied explicitly into new projects.

Projects retain their own saved price-master snapshot for portability. Existing
projects are never silently repriced when the company setup changes.
"""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .price_master import (PriceMaster, load_price_master, save_price_master,
                           validate_company_price_setup)
from .pricing_refresh import approved_company_master, latest_effective_date, master_revision


def company_price_setup_path() -> Path:
    override = os.environ.get("KUCHE7_PRICE_SETUP_PATH")
    if override:
        return Path(override).expanduser()
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not root:
        raise OSError("No writable application data directory is available for Price Setup.")
    return Path(root) / "company-price-master.json"


def load_company_price_setup(path: str | Path | None = None) -> PriceMaster:
    source = Path(path) if path is not None else company_price_setup_path()
    return load_price_master(source) if source.is_file() else PriceMaster()


def save_company_price_setup(master: PriceMaster, path: str | Path | None = None) -> Path:
    validate_company_price_setup(master)
    return save_price_master(master, path or company_price_setup_path())


def apply_company_setup_to_new_project(project, master: PriceMaster) -> None:
    """Explicitly seed a new project; never mutate the company setup object."""
    approved = approved_company_master(master)
    project.price_master = deepcopy(approved)
    currencies = {row.currency for row in approved.records}
    currencies.update(row.currency for row in approved.catalogue_rules)
    if len(currencies) == 1:
        project.quotation.currency = next(iter(currencies))
    project.pricing_revision = {
        "source": "company_price_setup",
        "revision": master_revision(approved),
        "latest_effective_date": latest_effective_date(approved),
        "applied_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
