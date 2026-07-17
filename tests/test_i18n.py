"""App language: catalog drift-guards, locale detection, binding translation.

The drift-guards are the point (same culture as the MCP registry guards):
the catalog and the source can only move together. One direction proves
every wrapped string has a French entry; the other proves every entry is
still used by the source — a renamed English msgid fails both ways.
"""

from __future__ import annotations

import ast
from pathlib import Path

import fbx.tui
from fbx.tui import fmt, i18n
from fbx.tui.locale_fr import CATALOG

TUI_DIR = Path(fbx.tui.__file__).parent


def _scan_sources() -> tuple[set[str], set[tuple[str, str | None]], set[str]]:
    """(msgids wrapped for translation, _p contexts, every string constant)."""
    wrapped: set[str] = set()
    contexts: set[tuple[str, str | None]] = set()
    constants: set[str] = set()

    for path in TUI_DIR.rglob("*.py"):
        if path.name == "locale_fr.py":
            # The catalog must not vouch for itself: its keys are string
            # literals too, and counting them as "used" would blind the
            # stale-entry guard below.
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                constants.add(node.value)
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            args = node.args
            if name == "_" and args and isinstance(args[0], ast.Constant):
                wrapped.add(args[0].value)
            elif name == "_n":
                wrapped.update(
                    a.value for a in args[:2] if isinstance(a, ast.Constant)
                )
            elif name == "_p" and args and isinstance(args[0], ast.Constant):
                value = args[1].value if (
                    len(args) > 1 and isinstance(args[1], ast.Constant)
                ) else None
                contexts.add((args[0].value, value))
            elif name == "Binding":
                desc = args[2].value if (
                    len(args) > 2 and isinstance(args[2], ast.Constant)
                ) else None
                for kw in node.keywords:
                    if kw.arg == "description" and isinstance(kw.value, ast.Constant):
                        desc = kw.value.value
                if desc:
                    wrapped.add(desc)
            elif name == "Domain" and len(args) >= 3:
                # title + blurb render through _() in the dashboard menu.
                wrapped.update(
                    a.value for a in args[1:3] if isinstance(a, ast.Constant)
                )
    return wrapped, contexts, constants


# ---------------------------------------------------------------------------
# drift-guards


def test_every_wrapped_string_has_a_catalog_entry():
    wrapped, _contexts, _constants = _scan_sources()
    missing = sorted(m for m in wrapped if m not in CATALOG)
    assert not missing, f"strings without a French entry: {missing!r}"


def test_every_catalog_entry_is_still_used():
    wrapped, contexts, constants = _scan_sources()
    known_contexts = {ctx for ctx, _value in contexts}
    stale = []
    for key in CATALOG:
        ctx, sep, _value = key.partition("|")
        if sep and ctx in known_contexts:
            continue  # wire-value map; values come off the box, not the source
        if key not in wrapped and key not in constants:
            stale.append(key)
    assert not stale, f"catalog entries no source string uses: {stale!r}"


def test_placeholders_survive_translation():
    # A French string that loses (or invents) a {field} would KeyError at
    # .format time — in production, mid-render. Compare field sets instead.
    import string

    formatter = string.Formatter()

    def fields(s: str) -> set[str]:
        return {name for _, name, _, _ in formatter.parse(s) if name}

    broken = {
        key: (sorted(fields(key)), sorted(fields(value)))
        for key, value in CATALOG.items()
        if "|" not in key and fields(key) != fields(value)
    }
    assert not broken, f"placeholder mismatch (en vs fr): {broken!r}"


def test_french_typography_uses_no_break_spaces():
    # Freebox OS's own catalog puts U+00A0 before ?!;:% and inside « » —
    # a plain space there is a regression someone's editor slipped in.
    offenders = {
        key: value
        for key, value in CATALOG.items()
        if any(f" {mark}" in value for mark in "?!;:%»") or "« " in value
    }
    assert not offenders, f"plain space around French punctuation: {offenders!r}"


# ---------------------------------------------------------------------------
# the machinery


def test_unknown_msgid_falls_back_to_english():
    i18n.set_lang("fr")
    assert i18n._("totally unknown msgid") == "totally unknown msgid"
    assert i18n._p("state", "weird_new_state") == "weird_new_state"


def test_set_lang_rejects_unknown_codes():
    i18n.set_lang("de")
    assert i18n.lang() == "en"


def test_plural_rule_french_zero_is_singular():
    singular, plural = "{n} entry in {path}", "{n} entries in {path}"
    i18n.set_lang("en")
    assert i18n._n(singular, plural, 0) == plural
    assert i18n._n(singular, plural, 1) == singular
    i18n.set_lang("fr")
    assert i18n._n(singular, plural, 0) == CATALOG[singular]
    assert i18n._n(singular, plural, 1) == CATALOG[singular]
    assert i18n._n(singular, plural, 2) == CATALOG[plural]


def test_detect_lang_reads_posix_precedence(monkeypatch):
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    assert i18n.detect_lang() == "en"
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.detect_lang() == "fr"
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")  # outranks LANG
    assert i18n.detect_lang() == "en"
    monkeypatch.setenv("LANGUAGE", "fr:en")  # outranks everything
    assert i18n.detect_lang() == "fr"


def test_bindings_translate_per_instance_not_per_class():
    from fbx.tui.screens.system import SystemScreen

    i18n.set_lang("fr")
    french = SystemScreen()
    descriptions = {
        b.description
        for bindings in french._bindings.key_to_bindings.values()
        for b in bindings
    }
    assert {"Redémarrer", "Éteindre", "Retour"} <= descriptions

    # The class map keeps the English msgids: a later English instance (or a
    # language switch back) must not inherit the French copies.
    class_descriptions = {
        b.description
        for bindings in SystemScreen._merged_bindings.key_to_bindings.values()
        for b in bindings
    }
    assert "Reboot" in class_descriptions and "Redémarrer" not in class_descriptions

    i18n.set_lang("en")
    english = SystemScreen()
    descriptions = {
        b.description
        for bindings in english._bindings.key_to_bindings.values()
        for b in bindings
    }
    assert "Reboot" in descriptions and "Redémarrer" not in descriptions


# ---------------------------------------------------------------------------
# locale-aware formatting


def test_fmt_english_defers_to_cli_fmt():
    from fbx.cli import fmt as cli_fmt

    for value in (0, 999, 1234567, None, "junk"):
        assert fmt.human_bytes(value) == cli_fmt.human_bytes(value)
        assert fmt.human_rate(value) == cli_fmt.human_rate(value)
    assert fmt.duration(200000) == cli_fmt.duration(200000)
    assert fmt.epoch(1783944060) == cli_fmt.epoch(1783944060)
    assert fmt.onoff(True) == "on" and fmt.yesno(False) == "no"


def test_fmt_french_octets_commas_and_dates():
    i18n.set_lang("fr")
    assert fmt.human_bytes(1234567) == "1,2 Mo"
    assert fmt.human_bytes(532) == "532 o"
    assert fmt.human_rate(2500000) == "2,5 Mo/s"
    assert fmt.human_bits(8_000_000_000) == "8 Gbit/s"
    assert fmt.duration(200000) == "2j 7h"  # days are jours
    assert fmt.duration(90) == "1m 30s"  # h/m/s read the same
    assert fmt.epoch(1783944060).startswith("13/07/2026")  # DD/MM/YYYY
    assert fmt.centi_dbm(-1838) == "-18,38 dBm"
    assert fmt.onoff(True) == "activé" and fmt.onoff(False) == "désactivé"
    assert fmt.yesno(True) == "oui" and fmt.yesno(None) == ""
