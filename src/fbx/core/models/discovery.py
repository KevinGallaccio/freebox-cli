"""Models for the discovery step (`GET /api_version` and mDNS)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ApiVersion(BaseModel):
    """The unauthenticated `GET /api_version` payload.

    Observed on a Freebox Ultra (firmware 4.12.2): api_version "16.0". The
    public SDK still claims 4.0 — always trust this, never hardcode.
    """

    model_config = {"extra": "allow"}

    api_version: str
    api_base_url: str = "/api/"
    device_name: str | None = None
    device_type: str | None = None
    box_model: str | None = None
    box_model_name: str | None = None
    uid: str | None = None
    api_domain: str | None = None
    https_available: bool = False
    https_port: int | None = Field(default=None)

    @property
    def major(self) -> int:
        """Major API version, e.g. 16 from "16.0"."""
        return int(self.api_version.split(".", 1)[0])

    def base_path(self) -> str:
        """The versioned API path prefix, e.g. `/api/v16/`.

        Derived from the box, never hardcoded, so the client follows firmware
        upgrades automatically.
        """
        base = self.api_base_url if self.api_base_url.endswith("/") else self.api_base_url + "/"
        return f"{base}v{self.major}/"

    def base_url(self, host: str, *, scheme: str = "http", port: int | None = None) -> str:
        """Full base URL for API calls against `host`."""
        netloc = host if port is None else f"{host}:{port}"
        return f"{scheme}://{netloc}{self.base_path()}"
