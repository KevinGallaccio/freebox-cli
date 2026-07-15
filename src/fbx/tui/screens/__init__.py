"""The domain registry — one entry per screen; drives dashboard navigation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from textual.screen import Screen

from .system import SystemScreen


@dataclass(frozen=True)
class Domain:
    key: str
    title: str
    blurb: str  # one-liner shown in the dashboard menu
    factory: Callable[[], Screen]


# Order is the dashboard menu order. Grows as Phase 6 screens land.
DOMAINS: dict[str, Domain] = {
    d.key: d
    for d in (
        Domain("system", "System", "firmware, sensors, reboot", SystemScreen),
    )
}
