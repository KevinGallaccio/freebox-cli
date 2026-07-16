#!/usr/bin/env python3
"""Build the Claude Desktop extension bundle (freebox-cli.mcpb).

Claude Desktop's plain-chat surface only sees *connector* MCP servers, not
Claude-Code plugins — an .mcpb extension is the one-click way for users to get
the fbx tools in chat. The bundle is deliberately thin: a manifest whose
mcp_config launches `uvx --from freebox-cli[mcp]==<this version> fbx mcp
serve`. Pinning the exact version makes uv's environment cache deterministic
(the v0.5.2 lesson: an unpinned spec is resolved once and cached forever), so
shipping a new bundle IS the update. The only prerequisite on the user's
machine is uv itself.

Usage:
    uv run scripts/build_mcpb.py [--out dist/freebox-cli.mcpb]
    uv run scripts/build_mcpb.py --print-manifest   # for tests/debugging
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

from fbx import __version__


def manifest(version: str) -> dict:
    return {
        # 0.2, not the spec's latest: Claude Desktop validates installs against
        # its embedded schemas, and 0.2 is the newest shape its whole schema
        # family accepts (verified against the app bundle after a "0.4"
        # manifest was rejected with `Invalid manifest: server: Required`).
        "manifest_version": "0.2",
        "name": "freebox-cli",
        # ASCII-only, no spaces: hosts derive MCP server/tool identifiers from
        # this, and tool names are limited to [a-zA-Z0-9_-] — a pretty name
        # like "fbx — Freebox" produced tools chat-side registries dropped.
        "display_name": "freebox-cli",
        "version": version,
        "description": (
            "Drive a Freebox (Ultra) from Claude: connection, LAN, DHCP, port "
            "forwarding, Wi-Fi, files, downloads, and VMs — with guided "
            "pairing (a button press on the box). Requires uv "
            "(https://docs.astral.sh/uv)."
        ),
        "author": {"name": "Kevin Gallaccio", "url": "https://github.com/KevinGallaccio"},
        "homepage": "https://github.com/KevinGallaccio/freebox-cli",
        "license": "MIT",
        "keywords": ["freebox", "freebox-ultra", "router", "homelab", "mcp"],
        "server": {
            "type": "binary",
            # Required by every schema version; informational here — the host
            # executes mcp_config, and the "binary" we point at is uvx itself.
            "entry_point": "uvx",
            "mcp_config": {
                "command": "uvx",
                "args": [
                    "--from",
                    f"freebox-cli[mcp]=={version}",
                    "fbx",
                    "mcp",
                    "serve",
                ],
            },
        },
        "compatibility": {"platforms": ["darwin", "linux", "win32"]},
    }


def build(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(manifest(__version__), indent=2, ensure_ascii=False) + "\n",
        )
    print(f"wrote {out} (freebox-cli {__version__})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("dist/freebox-cli.mcpb"))
    parser.add_argument(
        "--print-manifest", action="store_true", help="dump the manifest JSON and exit"
    )
    args = parser.parse_args()
    if args.print_manifest:
        json.dump(manifest(__version__), sys.stdout, indent=2, ensure_ascii=False)
        print()
        return
    build(args.out)


if __name__ == "__main__":
    main()
