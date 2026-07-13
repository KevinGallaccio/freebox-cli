#!/usr/bin/env python3
"""Extract a machine-readable endpoint inventory from the mirrored on-box docs.

Input:  recon/raw/onbox-doc/index.html  (gitignored mirror, see mirror_doc.py)
Output: recon/doc_inventory.json        (committed: factual method+path list)

The inventory drives the Phase 0 browser sweep (checklist of what to exercise)
and the coverage diff: endpoints the Freebox OS UI calls that are absent here
are undocumented even on-box; endpoints here that the public dev.freebox.fr
docs lack are undocumented upstream.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RECON_DIR = Path(__file__).resolve().parent
SRC = RECON_DIR / "raw" / "onbox-doc" / "index.html"
DST = RECON_DIR / "doc_inventory.json"

H4_RE = re.compile(r'<h4[^>]*>(.*?)</h4>', re.S)
DL_RE = re.compile(
    r'<dl class="(get|post|put|delete)">\s*<dt id="([^"]*)">(.*?)</dt>', re.S
)
CODE_RE = re.compile(r'<code[^>]*>(.*?)</code>', re.S)


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).replace("¶", "").strip()


def main() -> int:
    html = SRC.read_text(encoding="utf-8", errors="replace")

    # Build (position, section title) markers from h4 headings.
    sections = [(m.start(), clean(m.group(1))) for m in H4_RE.finditer(html)]

    def section_at(pos: int) -> str:
        cur = "?"
        for start, title in sections:
            if start > pos:
                break
            cur = title
        return cur

    endpoints = []
    for m in DL_RE.finditer(html):
        method, anchor, dt = m.group(1).upper(), m.group(2), m.group(3)
        codes = [clean(c) for c in CODE_RE.findall(dt)]
        # First <code> is "GET ", the second is the path.
        path = codes[1] if len(codes) > 1 else clean(dt).replace(method, "", 1).strip()
        endpoints.append({
            "method": method,
            "path": path,
            "section": section_at(m.start()),
            "anchor": anchor,
        })

    inventory = {
        "source": "on-box docs http://mafreebox.freebox.fr/doc/index.html",
        "api_version": "16.0",
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
    }
    DST.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n")

    by_section: dict[str, int] = {}
    for e in endpoints:
        by_section[e["section"]] = by_section.get(e["section"], 0) + 1
    for s, n in sorted(by_section.items(), key=lambda kv: -kv[1]):
        print(f"{n:4d}  {s}", file=sys.stderr)
    print(f"total {len(endpoints)} -> {DST}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
