"""`cli.fmt`, in the app's language — units and dates, not just words.

Matching Freebox OS's French takes more than translated labels: the box
displays octets (« 1,2 Mo »), decimal commas, and DD/MM/YYYY dates. The CLI
and its JSON stay English, so this shim wraps `cli.fmt` for the app only:
in English every helper defers verbatim; in French the locale-sensitive
ones re-format. Screens import this module wherever they used `cli.fmt`.

Deliberately untouched in French: `human_bits` units (French Freebox
marketing says « 8 Gbit/s » too — only the decimal comma changes) and the
h/m/s duration letters (compact and unambiguous in a table; only d → j).
"""

from __future__ import annotations

from datetime import datetime

from ..cli import fmt as _en
from ..cli.fmt import is_num, safe  # locale-neutral, re-exported as-is
from .i18n import lang

__all__ = [
    "centi_dbm",
    "duration",
    "epoch",
    "human_bits",
    "human_bytes",
    "human_rate",
    "is_num",
    "onoff",
    "safe",
    "yesno",
]

_UNITS_FR = ["o", "Ko", "Mo", "Go", "To", "Po"]


def _fr_num(value: float, digits: int = 1) -> str:
    """French decimal: one comma, trailing zeros dropped ('1,2', '8')."""
    return f"{value:.{digits}f}".rstrip("0").rstrip(".").replace(".", ",")


def human_bytes(n: object) -> str:
    """1234567 → '1.2 MB', or « 1,2 Mo » — octets, the box's French unit."""
    if lang() != "fr":
        return _en.human_bytes(n)
    if not is_num(n):
        return ""
    value = float(n)
    for unit in _UNITS_FR:
        if abs(value) < 1000 or unit == _UNITS_FR[-1]:
            if unit == "o":
                return f"{int(value)} o"
            return f"{_fr_num(value)} {unit}"
        value /= 1000
    return ""  # pragma: no cover — loop always returns


def human_rate(n: object) -> str:
    s = human_bytes(n)
    return f"{s}/s" if s else ""


def human_bits(n: object) -> str:
    if lang() != "fr":
        return _en.human_bits(n)
    # Same units as English (bit/s is bit/s in French); only the comma.
    return _en.human_bits(n).replace(".", ",")


def epoch(ts: object) -> str:
    """Local time, in the locale's date order (French: DD/MM/YYYY)."""
    if lang() != "fr":
        return _en.epoch(ts)
    if not is_num(ts) or ts <= 0:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


def duration(secs: object) -> str:
    if lang() != "fr":
        return _en.duration(secs)
    # '3d 2h' → '3j 2h'. The English form always pairs the day count with an
    # hour part, so 'd ' appears exactly once; h/m/s read the same in French.
    return _en.duration(secs).replace("d ", "j ")


def centi_dbm(v: object) -> str:
    if lang() != "fr":
        return _en.centi_dbm(v)
    return _en.centi_dbm(v).replace(".", ",")


def yesno(v: object) -> str:
    if lang() != "fr":
        return _en.yesno(v)
    if v is None:
        return ""
    return "oui" if v else "non"


def onoff(v: object) -> str:
    if lang() != "fr":
        return _en.onoff(v)
    if v is None:
        return ""
    # Freebox OS toggles read « Activé / Désactivé ».
    return "activé" if v else "désactivé"
