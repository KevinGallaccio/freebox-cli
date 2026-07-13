"""The Freebox response envelope: `{success, result, error_code, msg}`.

Every Freebox API response — success or failure — is wrapped in this shape.
One place unwraps it, so auth, the client, and tests all agree on what a
success and a failure look like.
"""

from __future__ import annotations

from typing import Any

import httpx

from .errors import FbxAPIError, FbxHTTPError


def unwrap(resp: httpx.Response, *, method: str = "", path: str = "") -> Any:
    """Return the `result` field of a successful response, else raise.

    - Non-JSON body → `FbxHTTPError`.
    - `{"success": false, ...}` → `FbxAPIError` carrying `error_code`/`msg`.
    - `{"success": true, ...}` → the `result` value (or None if absent).

    A non-2xx HTTP status is NOT treated as fatal here: the Freebox returns a
    well-formed `success:false` envelope with a useful `error_code` alongside
    403s (e.g. `auth_required`), and the caller wants that code, not a bare
    status. Only a body we can't parse as the envelope raises `FbxHTTPError`.
    """
    try:
        body = resp.json()
    except ValueError as exc:
        raise FbxHTTPError(
            f"non-JSON response ({resp.status_code}) from {method} {path}"
        ) from exc

    if not isinstance(body, dict) or "success" not in body:
        raise FbxHTTPError(f"unexpected response shape from {method} {path}: {body!r}"[:200])

    if body.get("success"):
        return body.get("result")

    raise FbxAPIError(
        error_code=body.get("error_code", "unknown"),
        msg=body.get("msg"),
        method=method,
        path=path,
        status=resp.status_code,
    )


def call(
    http: httpx.Client,
    method: str,
    url: str,
    *,
    path: str = "",
    json: Any = None,
    params: dict | None = None,
    form: dict | None = None,
    files: Any = None,
) -> Any:
    """Send a request and return the unwrapped `result`, with typed errors only.

    Wraps every transport-level httpx failure (connect/read/timeout/protocol)
    into `FbxHTTPError` so no raw httpx exception ever escapes the core into the
    CLI. Envelope failures still surface as `FbxAPIError` from `unwrap`.

    Body encoding is mutually exclusive: `form` sends
    `application/x-www-form-urlencoded`, `files` sends `multipart/form-data`
    (both used by `POST /downloads/add`), otherwise `json` sends a JSON body.
    httpx rejects mixing `json=` with `data=`/`files=`, so we pick exactly one.
    """
    method = method.upper()
    label = path or url
    kwargs: dict[str, Any] = {"params": params}
    if files is not None:
        kwargs["files"] = files
        if form is not None:
            kwargs["data"] = form
    elif form is not None:
        kwargs["data"] = form
    else:
        kwargs["json"] = json
    try:
        resp = http.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise FbxHTTPError(f"could not reach the box ({method} {label}): {exc}") from exc
    return unwrap(resp, method=method, path=label)
