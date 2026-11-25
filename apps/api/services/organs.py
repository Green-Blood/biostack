"""The organ catalog for scan history: which organs and parameters we track, their units, and headline values.
Units are both storage and display units; the extractor converts printed units to these."""
from dataclasses import dataclass
from typing import Literal

from services.i18n import msg


SIDES = ("", "left", "right")  # "" when a parameter has no sides
ORIGINS = ("rule", "ai", "manual")


@dataclass(frozen=True)
class Param:
    key: str
    kind: Literal["numeric", "text"]
    unit: str
    sides: bool = False
    chart: bool = False


@dataclass(frozen=True)
class Organ:
    key: str
    aliases: tuple[str, ...]
    params: tuple[Param, ...]
    headline: tuple[str, str]  # (param_key, side); side "" when the param has no sides
    related_markers: tuple[str, ...] = ()


def _n(key: str, unit: str, sides: bool = False, chart: bool = False) -> Param:
    return Param(key, "numeric", unit, sides, chart)


def _t(key: str) -> Param:
    return Param(key, "text", "")


ORGANS: dict[str, Organ] = {o.key: o for o in (
    Organ("thyroid", ("thyroid", "щитовидн"), (
        _n("volume_total", "cm³", chart=True), _n("volume_lobe", "cm³", sides=True, chart=True),
        _n("length_mm", "mm", sides=True), _n("width_mm", "mm", sides=True), _n("thickness_mm", "mm", sides=True),
        _n("isthmus_mm", "mm"), _n("nodule_count", "count"), _n("nodule_max_mm", "mm", chart=True),
        _n("tirads", "score", chart=True), _t("echogenicity"), _t("vascularity"),
    ), ("volume_total", ""), ("tsh", "free_t4", "free_t3", "anti_tpo")),
    Organ("liver", ("liver", "печен"), (
        _n("lobe_size_cm", "cm", sides=True, chart=True), _t("echotexture"),
    ), ("lobe_size_cm", "right")),
    Organ("gallbladder", ("gallbladder", "желчн"), (
        _n("length_cm", "cm"), _n("width_cm", "cm"), _n("wall_thickness_mm", "mm", chart=True),
    ), ("wall_thickness_mm", "")),
    Organ("pancreas", ("pancrea", "поджелудочн"), (
        _n("head_cm", "cm", chart=True), _n("body_cm", "cm"), _n("tail_cm", "cm"),
    ), ("head_cm", "")),
    Organ("spleen", ("spleen", "селезен"), (
        _n("length_cm", "cm", chart=True),
    ), ("length_cm", "")),
    Organ("kidneys", ("kidney", "renal", "почк", "почек"), (
        _n("length_cm", "cm", sides=True, chart=True), _n("width_cm", "cm", sides=True),
        _n("parenchyma_mm", "mm", sides=True),
    ), ("length_cm", "right")),
    Organ("bladder", ("bladder", "мочев"), (
        _n("volume_ml", "ml", chart=True), _n("wall_thickness_mm", "mm"), _n("residual_urine_ml", "ml", chart=True),
    ), ("volume_ml", "")),
    Organ("prostate", ("prostat", "предстательн"), (
        _n("volume_cm3", "cm³", chart=True), _n("length_mm", "mm"), _n("width_mm", "mm"), _n("thickness_mm", "mm"),
    ), ("volume_cm3", "")),
)}


def get_param(organ_key: str, param_key: str) -> Param | None:
    organ = ORGANS.get(organ_key)
    return next((p for p in organ.params if p.key == param_key), None) if organ else None


def organs_in(text: str) -> list[str]:
    """Organ keys in order of first mention (case-insensitive substring of any alias)."""
    low = text.lower().replace("ё", "е")
    found = []
    for organ in ORGANS.values():
        positions = [i for a in organ.aliases if (i := low.find(a)) >= 0]
        if positions:
            found.append((min(positions), organ.key))
    return [key for _, key in sorted(found)]


def organ_name(key: str, lang: str) -> str:
    return msg(lang, f"organ.{key}")


def param_name(param_key: str, lang: str) -> str:
    return msg(lang, f"param.{param_key}")
