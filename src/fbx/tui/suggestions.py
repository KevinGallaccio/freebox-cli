"""Contextual suggestions for the dashboard.

Each rule looks at the latest snapshot and proposes a next action a
low-technicality user might not know to look for. Rules must be safe to show
on any box: point at genuine hygiene or unfinished business, never at taste.

GUARDRAIL (load-bearing): no rule may second-guess radio configuration —
channel pinning, Wi-Fi generation (he/eht) toggles, band enable/disable.
Radio settings are deliberate operator choices; on the reference box, 2.4 GHz
is intentionally pinned to channel 1 with Wi-Fi 6/7 off so ESP8266-era IoT
gear can associate. A "fix your Wi-Fi" suggestion would be wrong exactly when
it matters most.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Suggestion:
    text: str
    domain: str  # registry key of the screen that handles it


def suggest(snap: dict) -> list[Suggestion]:
    """Derive suggestions from a dashboard snapshot (missing keys are fine)."""
    out: list[Suggestion] = []

    conn = snap.get("connection") or {}
    if conn and conn.get("state") != "up":
        out.append(Suggestion("WAN is not up — inspect the connection logs", "connection"))

    wps = snap.get("wps") or {}
    if wps.get("enabled"):
        out.append(
            Suggestion(
                "Wi-Fi WPS is enabled — a known attack surface; consider disabling it", "wifi"
            )
        )

    tasks = snap.get("downloads") or []
    done = sum(1 for t in tasks if t.get("status") == "done")
    if done:
        out.append(Suggestion(f"{done} finished download(s) — clean up the list", "downloads"))
    errored = sum(1 for t in tasks if t.get("status") == "error")
    if errored:
        out.append(Suggestion(f"{errored} download(s) in error — inspect them", "downloads"))

    for v in snap.get("vms") or []:
        if v.get("status") == "stopped":
            name = v.get("name") or f"#{v.get('id')}"
            out.append(Suggestion(f"VM '{name}' is stopped — start it?", "vm"))

    for p in snap.get("partitions") or []:
        used, total = p.get("used_bytes"), p.get("total_bytes")
        if used and total and used / total > 0.9:
            label = p.get("label") or p.get("path") or f"#{p.get('id')}"
            pct = round(100 * used / total)
            out.append(Suggestion(f"Partition '{label}' is {pct}% full — free up space", "storage"))

    missed = sum(1 for c in snap.get("calls") or [] if c.get("new") and c.get("type") == "missed")
    if missed:
        out.append(Suggestion(f"{missed} new missed call(s) — review the log", "calls"))

    unnamed = sum(
        1 for h in snap.get("lan_devices") or [] if h.get("active") and not h.get("primary_name")
    )
    if unnamed:
        out.append(
            Suggestion(f"{unnamed} active device(s) without a name — label them", "lan")
        )

    return out
