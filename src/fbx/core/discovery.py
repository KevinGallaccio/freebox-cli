"""Finding the box and reading its API version.

Two mechanisms, in order of preference:
1. mDNS (`_fbx-api._tcp`) — the method Free actually recommends; finds the box
   without assuming a hostname. Best-effort: needs the `zeroconf` extra and a
   network that passes multicast.
2. HTTP `GET /api_version` against `mafreebox.freebox.fr` (or a given host) —
   the reliable fallback, and how we read the version regardless.

The API version is always read from the box, never hardcoded (§3 of the brief).
"""

from __future__ import annotations

import logging

import httpx

from .errors import FbxDiscoveryError
from .models.discovery import ApiVersion

log = logging.getLogger("fbx.discovery")

DEFAULT_HOST = "mafreebox.freebox.fr"
MDNS_SERVICE = "_fbx-api._tcp.local."


def probe(
    host: str = DEFAULT_HOST,
    *,
    scheme: str = "http",
    port: int | None = None,
    timeout: float = 5.0,
    verify: object = True,
) -> ApiVersion:
    """Read `GET /api_version` from `host` and return the parsed version.

    `/api_version` lives at the web root, not under `/api/`, and needs no auth.
    """
    netloc = host if port is None else f"{host}:{port}"
    url = f"{scheme}://{netloc}/api_version"
    try:
        resp = httpx.get(url, timeout=timeout, verify=verify)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FbxDiscoveryError(f"could not read {url}: {exc}") from exc
    try:
        return ApiVersion.model_validate(data)
    except Exception as exc:  # pydantic ValidationError and friends
        raise FbxDiscoveryError(f"unexpected /api_version payload from {host}: {exc}") from exc


def discover_mdns(timeout: float = 3.0) -> list[dict]:
    """Browse for `_fbx-api._tcp` services on the LAN. Returns [] if none/unavailable.

    Each hit is a dict with at least `host`, `port`, and whatever TXT keys the
    box advertises (api_version, api_domain, uid, …). Never raises: mDNS is an
    optimization, and HTTP discovery is always available as the fallback.
    """
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        log.debug("zeroconf not installed; skipping mDNS discovery")
        return []

    found: list[dict] = []

    class _Listener(ServiceListener):
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name, timeout=int(timeout * 1000))
            if not info:
                return
            addresses = info.parsed_addresses() if hasattr(info, "parsed_addresses") else []
            props = {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in (info.properties or {}).items()
            }
            found.append(
                {
                    "name": name,
                    "host": addresses[0] if addresses else None,
                    "port": info.port,
                    **props,
                }
            )

        def update_service(self, *a: object) -> None:  # required by the interface
            pass

        def remove_service(self, *a: object) -> None:
            pass

    zc = None
    try:
        import time

        zc = Zeroconf()
        ServiceBrowser(zc, MDNS_SERVICE, _Listener())
        deadline = timeout
        step = 0.25
        waited = 0.0
        while waited < deadline and not found:
            time.sleep(step)
            waited += step
    except Exception as exc:  # noqa: BLE001 — mDNS is strictly best-effort
        log.debug("mDNS discovery failed: %s", exc)
    finally:
        if zc is not None:
            zc.close()
    return found
