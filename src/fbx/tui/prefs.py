"""App preferences: `~/.config/fbx/app.toml` — theme and per-screen choices.

Prefs are cosmetic state, not secrets: the file is world-readable, but writes
stay atomic (the credential store's recipe) so a crash never leaves a torn
file. A missing or corrupt file just means defaults; a failed write must
never take the app down.
"""

from __future__ import annotations

import contextlib
import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from ..core import credentials


def prefs_path() -> Path:
    # Resolved through `credentials.config_dir` at call time, so the test
    # suite's config-dir isolation fixture covers prefs too.
    return credentials.config_dir() / "app.toml"


class Prefs:
    """The loaded prefs document, dotted-path access, persisted on set."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data or {}

    @classmethod
    def load(cls) -> Prefs:
        try:
            with open(prefs_path(), "rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        return cls(data)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        if node.get(parts[-1]) == value:
            return
        node[parts[-1]] = value
        self._save()

    def _save(self) -> None:
        path = prefs_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_TRUNC, 0o644)
            try:
                with os.fdopen(fd, "wb") as fh:
                    tomli_w.dump(self._data, fh)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
        except OSError:
            pass
