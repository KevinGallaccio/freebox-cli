"""Discovery + version computation."""

from __future__ import annotations

import httpx
import pytest
import respx

from fbx.core import discovery
from fbx.core.errors import FbxDiscoveryError
from fbx.core.models.discovery import ApiVersion

API_VERSION_BODY = {
    "box_model_name": "Freebox v9 (r1)",
    "api_base_url": "/api/",
    "https_port": 29491,
    "device_name": "Freebox Server",
    "https_available": True,
    "box_model": "fbxgw9-r1",
    "api_domain": "abcd1234.fbxos.fr",
    "uid": "deadbeef",
    "api_version": "16.0",
    "device_type": "FreeboxServer9,1",
}


@respx.mock
def test_probe_parses_api_version():
    respx.get("http://mafreebox.freebox.fr/api_version").mock(
        return_value=httpx.Response(200, json=API_VERSION_BODY)
    )
    ver = discovery.probe()
    assert ver.api_version == "16.0"
    assert ver.major == 16
    assert ver.box_model == "fbxgw9-r1"


def test_base_path_is_derived_not_hardcoded():
    assert ApiVersion(api_version="16.0").base_path() == "/api/v16/"
    # Follows a firmware bump automatically.
    assert ApiVersion(api_version="17.3").base_path() == "/api/v17/"


def test_base_url_local_http():
    ver = ApiVersion(api_version="16.0")
    assert ver.base_url("mafreebox.freebox.fr") == "http://mafreebox.freebox.fr/api/v16/"


@respx.mock
def test_probe_unreachable_raises_discovery_error():
    respx.get("http://mafreebox.freebox.fr/api_version").mock(
        side_effect=httpx.ConnectError("no route")
    )
    with pytest.raises(FbxDiscoveryError):
        discovery.probe()


@respx.mock
def test_probe_garbage_body_raises_discovery_error():
    respx.get("http://mafreebox.freebox.fr/api_version").mock(
        return_value=httpx.Response(200, json={"nope": True})
    )
    with pytest.raises(FbxDiscoveryError):
        discovery.probe()
