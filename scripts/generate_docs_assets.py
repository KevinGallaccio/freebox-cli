"""Regenerate the README's visual assets — demo data only, never a real box.

- docs/logo.svg: the fbx mark, straight from `fbx.tui.brand`'s pixel grid.
- docs/screenshot-app.svg: the dashboard in the freebox-light default theme,
  rendered headless through the same respx harness as the test suite.

Run from the repo root: `uv run python scripts/generate_docs_assets.py`
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from fbx.tui import brand  # noqa: E402


def write_logo(out: Path) -> None:
    """One SVG rect per pixel — crisp, no font involved, transparent outside."""
    scale = 10
    rects = []
    colors = {"R": brand.FREE_RED, "W": "#F5F5F5"}
    for y in range(brand._H):
        for x in range(brand._W):
            color = brand._pixel(x, y)
            if color is None:
                continue
            rects.append(
                f'<rect x="{x * scale}" y="{y * scale}" width="{scale}" '
                f'height="{scale}" fill="{colors[color]}"/>'
            )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {brand._W * scale} {brand._H * scale}" '
        f'shape-rendering="crispEdges">\n'
        + "\n".join(rects)
        + "\n</svg>\n"
    )
    out.write_text(svg)
    print(f"wrote {out} ({len(rects)} pixels)")


async def write_screenshot(out: Path) -> None:
    import respx

    from fbx.core import credentials
    from fbx.tui.app import FbxApp
    from tests.helpers import authorize, mock_get, mock_login

    with tempfile.TemporaryDirectory() as tmp:
        # The same isolation as conftest.py, hand-rolled because this runs
        # outside pytest: never touch the real ~/.config/fbx.
        credentials.config_dir = lambda: Path(tmp)  # type: ignore[assignment]
        with respx.mock:
            authorize()
            mock_login()
            _mock_demo_box(mock_get)
            app = FbxApp(splash=False)
            async with app.run_test(size=(126, 42)) as pilot:
                for _ in range(80):
                    await pilot.pause(0.05)
                    from textual.widgets import Static

                    wifi = str(app.screen.query_one("#tile-wifi", Static).content)
                    if "5G" in wifi:
                        break
                await pilot.pause(0.3)
                out.write_text(app.export_screenshot())
    print(f"wrote {out}")


def _mock_demo_box(mock_get) -> None:
    """A healthy, fictional Ultra (TEST-NET addresses, demo names)."""
    mock_get(
        "connection/",
        {"state": "up", "media": "ftth", "ipv4": "192.0.2.1",
         "rate_down": 4_200_000, "rate_up": 1_100_000},
    )
    mock_get(
        "system/",
        {"firmware_version": "4.12.2", "uptime": "12 jours 4 heures 30 minutes",
         "model_info": {"pretty_name": "Freebox v9 (r1)"},
         "sensors": [{"name": "cpu", "value": 58}],
         "fans": [{"name": "fan0", "value": 2100}]},
    )
    mock_get(
        "wifi/ap/",
        [
            {"id": 10, "name": "5G", "status": {"state": "active", "primary_channel": 120},
             "config": {}},
            {"id": 11, "name": "6G", "status": {"state": "active", "primary_channel": 85},
             "config": {}},
            {"id": 12, "name": "2.4G", "status": {"state": "active", "primary_channel": 1},
             "config": {}},
            {"id": 13, "name": "5G1", "status": {"state": "active", "primary_channel": 48},
             "config": {}},
        ],
    )
    mock_get("wifi/wps/config/", {"enabled": False})
    mock_get(
        "lan/browser/pub/",
        [
            {"id": f"ether-02:00:00:00:00:{i:02x}", "active": True,
             "primary_name": name, "host_type": kind,
             "l2ident": {"id": f"02:00:00:00:00:{i:02x}", "type": "mac_address"},
             "l3connectivities": [
                 {"addr": f"192.0.2.{10 + i}", "af": "ipv4", "active": True,
                  "reachable": True}
             ],
             "last_activity": 1783944060}
            for i, (name, kind) in enumerate(
                [("portable-salon", "laptop"), ("télé-salon", "smart_tv"),
                 ("borne-hifi", "audio"), ("prise-bureau", "smartplug")]
            )
        ],
    )
    mock_get(
        "vm/",
        [{"id": 0, "name": "media", "status": "running"},
         {"id": 1, "name": "proxy", "status": "running"}],
    )
    mock_get(
        "storage/partition/",
        [{"id": 2, "label": "Freebox", "used_bytes": 620_000_000_000,
          "total_bytes": 984_300_000_000}],
    )
    mock_get("downloads/", [{"id": 1, "name": "debian-13.iso", "status": "done"}])
    mock_get("call/log/", [])


if __name__ == "__main__":
    docs = REPO / "docs"
    docs.mkdir(exist_ok=True)
    write_logo(docs / "logo.svg")
    asyncio.run(write_screenshot(docs / "screenshot-app.svg"))
