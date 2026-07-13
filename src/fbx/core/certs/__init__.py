"""TLS trust for reaching the box.

- **Locally** the box is plain HTTP (`http://mafreebox.freebox.fr`) — no
  certificate involved; `verify` is irrelevant to httpx for http URLs.
- **Remotely** the box is HTTPS on `{api_domain}:{https_port}`, served by the
  **Freebox Root CA**, which is not in any system trust store. Bundle that PEM
  here and point httpx at it. We deliberately expose no `--insecure` flag.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

CA_BUNDLE = Path(__file__).with_name("freebox_root_ca.pem")


def ca_bundle_path() -> str | None:
    """Path to the bundled Freebox Root CA PEM, or None if not present yet."""
    return str(CA_BUNDLE) if CA_BUNDLE.exists() else None


def default_verify(*, scheme: str) -> Any:
    """The `verify=` value to hand httpx for a connection of `scheme`.

    http → `True` (ignored for http). https → the bundled CA if we have it,
    otherwise fall back to system trust (which will fail against the Freebox
    CA — a clear TLS error is better than a silent `--insecure`).
    """
    if scheme != "https":
        return True
    bundle = ca_bundle_path()
    return bundle if bundle is not None else True
