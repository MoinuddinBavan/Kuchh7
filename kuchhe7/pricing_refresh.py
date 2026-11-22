"""Reviewed, atomic company-price refresh for an existing project draft."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .price_master import PriceMaster, validate_company_price_setup
from .quotation import calculate_quotation


def master_revision(master: PriceMaster) -> str:
    encoded = json.dumps(master.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def approved_company_master(master: PriceMaster) -> PriceMaster:
    """Copy approved records only; draft company entries cannot price a project."""
    validate_company_price_setup(master)
    return PriceMaster(
        records=deepcopy([row for row in master.records if row.status == "approved"]),
        catalogue_rules=deepcopy([row for row in master.catalogue_rules if row.status == "approved"]),
    )


def latest_effective_date(master: PriceMaster) -> str:
    return max((row.effective_date for row in (*master.records, *master.catalogue_rules)), default="")


@dataclass(frozen=True)
class PriceChange:
    kind: str
    record_id: str
    change: str
    old_value: str
    new_value: str
    old_effective: str
    new_effective: str


@dataclass(frozen=True)
class PriceRefreshPreview:
    changes: tuple[PriceChange, ...]
    old_revision: str
    source_revision: str
    latest_effective_date: str
    old_currency: str
    proposed_currency: str
    old_draft_total: str
    proposed_draft_total: str
    old_incomplete: bool
    proposed_incomplete: bool
    manual_exception_ids: tuple[str, ...]
    proposed_master: PriceMaster


def _rate_value(row) -> str:
    detail = f", band {row.thickness_mm} x {row.band_width_mm} mm" if row.category == "Edge banding" else ""
    return f"{row.rate} {row.currency}/{row.unit} ({row.match_key}{detail})"


def _rule_value(row) -> str:
    value = (f"{row.fixed_price} {row.currency} for {row.width_mm}x{row.height_mm}x{row.depth_mm} mm"
             if row.mode == "fixed" else
             f"{row.markup_percent or row.gross_margin_percent}% {'markup' if row.markup_percent else 'margin'} {row.currency}")
    return (f"{value} ({row.type_id}, {row.material or 'any finish'}; "
            f"basis {row.cost_basis}; material waste {row.material_wastage_percent or 'none'}%; "
            f"edge waste {row.edge_wastage_percent or 'none'}%; overhead {row.overhead_percent or 'none'}%)")


def _diff_rows(kind: str, old_rows, new_rows, id_field: str, formatter) -> list[PriceChange]:
    old = {getattr(row, id_field): row for row in old_rows}
    new = {getattr(row, id_field): row for row in new_rows}
    changes = []
    for record_id in sorted(old.keys() | new.keys()):
        before, after = old.get(record_id), new.get(record_id)
        if before is not None and after is not None and asdict(before) == asdict(after):
            continue
        change = "Added" if before is None else "Missing from company" if after is None else "Changed"
        changes.append(PriceChange(
            kind, record_id, change, formatter(before) if before else "—",
            formatter(after) if after else "—", before.effective_date if before else "",
            after.effective_date if after else ""))
    return changes


def preview_company_price_refresh(project, company_master: PriceMaster) -> PriceRefreshPreview:
    """Compare without mutating project, issued snapshot or company setup."""
    proposed = approved_company_master(company_master)
    currencies = {row.currency for row in (*proposed.records, *proposed.catalogue_rules)}
    if len(currencies) > 1:
        raise ValueError("Company pricing has incompatible currencies.")
    proposed_currency = next(iter(currencies), project.quotation.currency)
    if project.quotation.currency and proposed_currency and project.quotation.currency != proposed_currency:
        raise ValueError(f"Project quotation uses {project.quotation.currency}; company prices use {proposed_currency}. Resolve currency before refresh.")
    changes = _diff_rows("Rate", project.price_master.records, proposed.records, "record_id", _rate_value)
    changes += _diff_rows("Catalogue rule", project.price_master.catalogue_rules,
                          proposed.catalogue_rules, "rule_id", _rule_value)
    old_summary = calculate_quotation(project)
    candidate = deepcopy(project)
    candidate.price_master = deepcopy(proposed)
    if not candidate.quotation.currency:
        candidate.quotation.currency = proposed_currency
    candidate.validate()
    new_summary = calculate_quotation(candidate)
    exceptions = set(project.quotation.unit_prices) | set(project.quotation.pricing_rules)
    return PriceRefreshPreview(
        tuple(changes), master_revision(project.price_master), master_revision(proposed),
        latest_effective_date(proposed), project.quotation.currency, proposed_currency,
        str(old_summary.total), str(new_summary.total),
        bool(old_summary.unpriced_ids or old_summary.incomplete_reasons),
        bool(new_summary.unpriced_ids or new_summary.incomplete_reasons),
        tuple(sorted(exceptions)), proposed)


def apply_company_price_refresh(project, preview: PriceRefreshPreview) -> None:
    """Commit the reviewed candidate only if the source project has not changed."""
    if master_revision(project.price_master) != preview.old_revision:
        raise ValueError("Project prices changed after this preview. Review the refresh again.")
    if master_revision(preview.proposed_master) != preview.source_revision:
        raise ValueError("Proposed company prices changed after this preview. Review again.")
    candidate = deepcopy(project)
    candidate.price_master = deepcopy(preview.proposed_master)
    if not candidate.quotation.currency:
        candidate.quotation.currency = preview.proposed_currency
    candidate.pricing_revision = {
        "source": "company_price_setup",
        "revision": preview.source_revision,
        "latest_effective_date": preview.latest_effective_date,
        "applied_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    candidate.validate()
    project.price_master = candidate.price_master
    project.quotation.currency = candidate.quotation.currency
    project.pricing_revision = candidate.pricing_revision
