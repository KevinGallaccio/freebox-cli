"""Persistent credential store: the per-box `app_token`, keyed by profile.

The app token is the long-lived secret earned once via the button-press
authorization. It is stored in `~/.config/fbx/credentials.json` at mode 0600
(owner read/write only). Session tokens are ephemeral and never persisted.

Multiple boxes are supported through named profiles (`--profile`); "default"
is used when none is given.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

_APP = "fbx"


@dataclass
class Credential:
    """What we persist per profile after a successful authorization."""

    app_id: str
    app_token: str
    # Identity of the box these belong to, captured at login so we can warn if
    # the box on the network later looks different.
    box_uid: str | None = None
    box_model: str | None = None
    api_domain: str | None = None
    # How to reach it, so routine commands skip rediscovery.
    host: str = "mafreebox.freebox.fr"
    https_port: int | None = None


def config_dir() -> Path:
    """`~/.config/fbx`, honoring `$XDG_CONFIG_HOME`.

    We use the XDG location on every platform (including macOS) rather than
    `~/Library/Application Support`, because CLI users expect `~/.config` and a
    predictable path is easier to document, back up, and `--profile` against.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / _APP


def credentials_path() -> Path:
    return config_dir() / "credentials.json"


def _read_all() -> dict:
    path = credentials_path()
    if not path.exists():
        return {"version": 1, "profiles": {}}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "profiles": {}}
    data.setdefault("profiles", {})
    return data


def _write_all(data: dict) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with 0600 from the start; never widen an existing file.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
    finally:
        # Defensively re-assert 0600 in case the file pre-existed with wider bits.
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def load(profile: str = "default") -> Credential | None:
    """Return the stored credential for `profile`, or None if not authorized."""
    entry = _read_all()["profiles"].get(profile)
    if not entry:
        return None
    known = {f for f in Credential.__dataclass_fields__}
    return Credential(**{k: v for k, v in entry.items() if k in known})


def save(cred: Credential, profile: str = "default") -> None:
    data = _read_all()
    data["profiles"][profile] = asdict(cred)
    _write_all(data)


def delete(profile: str = "default") -> bool:
    """Remove a profile's credential. Returns True if something was removed."""
    data = _read_all()
    if profile in data["profiles"]:
        del data["profiles"][profile]
        _write_all(data)
        return True
    return False


def list_profiles() -> list[str]:
    return sorted(_read_all()["profiles"])
