import datetime as dt

from sqlmodel import Session, select

from db.models import Biomarker, DateReview, LabReport, MedicalRecord


def effective_dates(session: Session) -> dict[int, tuple[dt.date | None, bool]]:
    """record_id -> (date to use, still_suspect). A confirmed date from the owner wins."""
    reviews = {r.record_id: r for r in session.exec(select(DateReview))}
    out = {}
    for rec in session.exec(select(MedicalRecord)):
        rv = reviews.get(rec.id)
        if rv is not None:
            out[rec.id] = (rv.confirmed_date or rec.record_date, False)
        else:
            out[rec.id] = (rec.record_date, rec.date_suspect)
    return out


def biomarker_rows(session: Session, marker_key: str | None = None):
    """(Biomarker, effective_date, date_suspect) for every biomarker, oldest first."""
    eff = effective_dates(session)
    q = select(Biomarker, LabReport).where(Biomarker.report_id == LabReport.id)
    if marker_key:
        q = q.where(Biomarker.marker_key == marker_key)
    out = []
    for bm, rep in session.exec(q):
        date, suspect = rep.test_date, False
        # A PDF's own printed date is the sample date; only results without one borrow their record's date.
        if rep.source != "pdf" and rep.record_id and rep.record_id in eff:
            rdate, suspect = eff[rep.record_id]
            date = rdate or rep.test_date
        out.append((bm, date, suspect))
    out.sort(key=lambda t: t[1])
    return out
