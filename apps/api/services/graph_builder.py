"""Shapes cached correlations into a node and edge graph for the UI.

Node kinds: symptom (a drop or symptom: HRV, deep sleep, worst symptom), trigger (behaviour or environment),
protector (a supplement), biomarker (a latest lab result outside its range; shown without edges because labs
are too sparse to correlate). An edge runs from predictor to target; `strength` is |r|, `lagged` marks any lag,
`phrase` and `effect` say in plain words what the link means, and `n_days` and `p_value` say how much data backs it.
"""

from sqlmodel import Session

from services.context_builder import latest_out_of_range
from services.correlation_phrases import describe
from services.correlation_store import AnalysisReport, load_correlations, load_report
from services.daily_series import variable_for
from services.i18n import msg, translate_text


def lag_label(lag_hours: int, lang: str = "en") -> str:
    return msg(lang, "graph.lag_hours", hours=lag_hours) if lag_hours else msg(lang, "graph.lag_same_day")


def _notes(report: AnalysisReport | None, has_edges: bool, lang: str) -> list[str]:
    if has_edges:
        return []
    if report is None:
        return [msg(lang, "graph.not_run")]
    if not report.targets:
        return [msg(lang, "graph.no_targets")]
    notes = [msg(lang, "graph.note_target", label=variable_for(t.target, lang).label, reason=translate_text(lang, t.reason))
             for t in report.targets if t.status == "insufficient_data"]
    return notes or [msg(lang, "graph.no_link")]


def build_graph(session: Session, lang: str = "en") -> dict:
    correlations = load_correlations(session)
    nodes: dict[str, dict] = {}
    edges = []
    for c in correlations:
        phrase, effect = describe(c.trigger_key, c.target_metric, c.correlation_score, c.lag_hours, lang)
        for key in (c.trigger_key, c.target_metric):
            variable = variable_for(key, lang)
            nodes[key] = {"id": key, "label": variable.label, "kind": variable.kind, "detail": ""}
        edges.append({
            "id": f"{c.trigger_key}->{c.target_metric}", "source": c.trigger_key, "target": c.target_metric,
            "r": round(c.correlation_score, 3), "strength": round(abs(c.correlation_score), 3), "lag_hours": c.lag_hours,
            "lag_label": lag_label(c.lag_hours, lang), "lagged": c.lag_hours > 0, "p_value": c.p_value, "n_days": c.n_days,
            "phrase": phrase, "effect": effect,
        })
    for marker, stored in zip(latest_out_of_range(session, lang), latest_out_of_range(session)):
        low, high = marker["ref_min"], marker["ref_max"]
        nodes[f"biomarker:{stored['name']}"] = {  # the id does not change with the language
            "id": f"biomarker:{stored['name']}", "label": marker["name"], "kind": "biomarker",
            "detail": msg(lang, "graph.range", value=f"{marker['value']:g}", unit=marker["unit"], low=f"{low:g}", high=f"{high:g}")
            if low is not None and high is not None else f"{marker['value']:g} {marker['unit']}",
        }
    return {"nodes": list(nodes.values()), "edges": edges, "notes": _notes(load_report(session), bool(edges), lang)}
