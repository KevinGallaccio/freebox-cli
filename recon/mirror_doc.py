#!/usr/bin/env python3
"""Mirror the on-box API docs (http://mafreebox.freebox.fr/doc/) into recon/raw/.

The Freebox serves its own, firmware-current Sphinx documentation at
/doc/index.html with no authentication. That HTML is Free's material: it is
mirrored into the gitignored recon/raw/onbox-doc/ as a local reference for
writing docs/api-notes.md, and is never committed.

Usage: python3 recon/mirror_doc.py
"""

from __future__ import annotations

import re
import sys
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

BASE = "http://mafreebox.freebox.fr/doc/"
OUT = Path(__file__).resolve().parent / "raw" / "onbox-doc"

HREF_RE = re.compile(r"""(?:href|src)=["']([^"'#]+)["']""", re.I)


def fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001 — a 404'd asset should not kill the mirror
        print(f"  !! {url}: {e}", file=sys.stderr)
        return None


def main() -> int:
    queue: deque[str] = deque([BASE + "index.html"])
    seen: set[str] = set(queue)
    pages = 0

    while queue:
        url = queue.popleft()
        rel = urllib.parse.unquote(url[len(BASE):]) or "index.html"
        dst = OUT / rel
        if not str(dst.resolve()).startswith(str(OUT.resolve())):
            print(f"  skip path escape: {rel}", file=sys.stderr)
            continue

        body = fetch(url)
        if body is None:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(body)
        pages += 1

        if dst.suffix in (".html", ".htm", ".js", ".css"):
            text = body.decode("utf-8", errors="replace")
            for link in HREF_RE.findall(text):
                if "[" in link or "{" in link:  # template examples in the docs
                    continue
                try:
                    nxt = urllib.parse.urljoin(url, link)
                except ValueError:
                    continue
                nxt = nxt.split("#", 1)[0].split("?", 1)[0]
                if nxt.startswith(BASE) and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)

    print(f"mirrored {pages} files -> {OUT}", file=sys.stderr)
    return 0 if pages else 1


if __name__ == "__main__":
    sys.exit(main())
