"""App language: English msgids, a hand-written French catalog, no gettext.

The app has exactly two languages (issue #5): English — the source strings —
and French, the box's mother tongue. That rules the machinery: no .po/.mo
pipeline, no plural-forms grammar, just a dict keyed by the English string
as written in the source. A missing entry falls back to English, so a typo
can never crash a render — but the test suite's drift-guards keep the
catalog and the source in lockstep both ways.

Translation happens at *render* time (`compose`, `refresh_data`, `notify`),
never at import time. The one place that can't: `BINDINGS` descriptions,
frozen into the class when Python evaluates the class body. Textual gives
every DOMNode instance its own copy of the bindings map, so
`translate_bindings(node)` rewrites the descriptions per instance — and a
language switch simply rebuilds the screens (`FbxApp.set_language`), which
re-runs every render-time `_()` and re-translates every new instance.

French terminology follows Freebox OS's own UI (Kevin's rule: the app must
speak the same French as the box) — « Redirections de ports », « baux
statiques », « Journal d'appels », « Actualiser », octets not bytes.
"""

from __future__ import annotations

import dataclasses
import os
from typing import TYPE_CHECKING

from .locale_fr import CATALOG as _FR

if TYPE_CHECKING:
    from textual.dom import DOMNode

# Codes are what `app.lang` persists; names are shown untranslated in the
# language chooser — you must be able to find your way back from a language
# you can't read.
LANGUAGES = {"en": "English", "fr": "Français"}

_lang = "en"


def lang() -> str:
    return _lang


def set_lang(code: str) -> None:
    """Activate a language; unknown codes fall back to English."""
    global _lang
    _lang = code if code in LANGUAGES else "en"


def detect_lang() -> str:
    """The POSIX locale's verdict, for first runs (no `app.lang` saved yet).

    Same precedence as gettext: LANGUAGE > LC_ALL > LC_MESSAGES > LANG.
    Only the language part matters — fr_FR, fr_BE, fr_CA all get French.
    """
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return "fr" if value.split(":")[0].lower().startswith("fr") else "en"
    return "en"


def _(msgid: str) -> str:
    """The English source string, translated into the active language."""
    if _lang == "en":
        return msgid
    return _FR.get(msgid, msgid)


def _p(context: str, msgid: str) -> str:
    """Context-scoped lookup for short, collision-prone strings.

    Box statuses ("up", "missed", "running") and one-word labels collide as
    plain msgids; the catalog keys them "context|msgid". Values straight off
    the wire pass through untranslated when unknown — a new firmware status
    must render raw, not crash.
    """
    if _lang == "en":
        return msgid
    return _FR.get(f"{context}|{msgid}", msgid)


def _n(singular: str, plural: str, n: int) -> str:
    """Two-form plural, per-language rule (French: 0 takes the singular)."""
    if _lang == "fr":
        return _(singular) if n <= 1 else _(plural)
    return singular if n == 1 else plural


def translate_bindings(node: DOMNode) -> None:
    """Rewrite this instance's binding descriptions in the active language.

    Class-level `BINDINGS` keep their English descriptions (they're the
    msgids); each instance gets translated copies here. Textual's
    `DOMNode.__init__` gives the instance a shallow copy of the class map —
    fresh dict, shared Binding lists — so this replaces the lists rather
    than mutating them, and the class stays untouched. Re-runnable: always
    translates from the class originals, so a language switch only needs
    new instances (screens are rebuilt) or a re-call (the App itself).
    """
    originals = type(node)._merged_bindings
    if not originals:
        return
    node._bindings.key_to_bindings = {
        key: [
            dataclasses.replace(b, description=_(b.description))
            if b.description
            else b
            for b in bindings
        ]
        for key, bindings in originals.key_to_bindings.items()
    }
