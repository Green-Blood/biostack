"""Range tiers (deficient ... toxic) exactly as a lab printed them, stored per marker and report."""
from sqlmodel import Session, select

from db.models import LabReport, MarkerTier
from services.lab_rows import TierBand
from services.markers import units_compatible

TIER_ORDER = ("deficient", "insufficient", "normal", "high", "toxic")


def replace_report_tiers(session: Session, report_id: int, marker_key: str, unit: str, bands: list[TierBand]) -> None:
    """Replace the tiers one report holds for one marker (no commit)."""
    for old in session.exec(select(MarkerTier).where(MarkerTier.report_id == report_id, MarkerTier.marker_key == marker_key)):
        session.delete(old)
    for band in bands:
        session.add(MarkerTier(marker_key=marker_key, tier=band.tier, min_value=band.min, max_value=band.max,
                               unit=unit, label=band.label, report_id=report_id, source="pdf"))


def _as_dict(tier: MarkerTier) -> dict:
    return {"tier": tier.tier, "min": tier.min_value, "max": tier.max_value, "label": tier.label,
            "unit": tier.unit, "report_id": tier.report_id}


def tiers_for_unit(tiers: list[dict], unit: str | None) -> list[dict]:
    """The tiers printed in a unit compatible with `unit`; tiers in another unit say nothing about this value."""
    return [t for t in tiers if units_compatible(t.get("unit") or "", unit or "")]


def latest_tiers(session: Session) -> dict[str, list[dict]]:
    """marker_key -> tiers of the most recent report that has any, ordered deficient to toxic."""
    rows = session.exec(select(MarkerTier, LabReport).where(MarkerTier.report_id == LabReport.id)).all()
    newest: dict[str, tuple] = {}
    for tier, report in rows:
        stamp = (report.test_date, report.id)
        if tier.marker_key not in newest or stamp > newest[tier.marker_key]:
            newest[tier.marker_key] = stamp
    out: dict[str, list[dict]] = {}
    for tier, report in rows:
        if (report.test_date, report.id) == newest[tier.marker_key]:
            out.setdefault(tier.marker_key, []).append(tier)
    return {key: [_as_dict(t) for t in sorted(items, key=lambda t: (TIER_ORDER.index(t.tier) if t.tier in TIER_ORDER else 9, t.min_value or 0))]
            for key, items in out.items()}
