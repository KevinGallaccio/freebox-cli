"""Freebox filesystem-path encoding.

Every filesystem path the API returns or accepts (`/fs/ls/{path}`, download
`download_dir`, storage partition `path`, VM `disk_path`, …) is the absolute
path **base64-encoded** — standard alphabet with `=` padding, not the URL-safe
variant. Encode before building a URL; decode before showing a human.
"""

from __future__ import annotations

import base64
import binascii


def encode(path: str) -> str:
    """Absolute filesystem path → the base64 token the API expects."""
    return base64.b64encode(path.encode()).decode("ascii")


def decode(token: str) -> str:
    """Base64 path token → the absolute path, or the token itself if it
    doesn't decode cleanly (never raise over a display value)."""
    try:
        raw = base64.b64decode(token, validate=True)
        text = raw.decode()
    except (binascii.Error, ValueError):
        return token
    # Freebox path tokens always decode to an absolute path; anything else is
    # probably a plain string that merely looked like base64.
    return text if text.startswith("/") else token


def decode_lenient(token: object) -> str:
    """`decode` without the absolute-path guard, for VM disk/cd tokens.

    The box stores those relative (`Freebox/VMs/x.qcow2`) as often as
    absolute, so the guard would bounce legitimate values. Empty → ""."""
    if not token:
        return ""
    try:
        return base64.b64decode(str(token), validate=True).decode()
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return str(token)
