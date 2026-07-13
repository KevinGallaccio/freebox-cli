"""Token redaction for logs. Wired in on day one, not after the first leak.

Freebox secrets (`app_token`, `session_token`, the `X-Fbx-App-Auth` header,
login `password`/`challenge`) must never reach a log sink — not in a
`--verbose` dump a user pastes into an issue, not anywhere. This module owns
the single definition of "what a secret looks like" and a logging filter that
scrubs it from every record.
"""

from __future__ import annotations

import logging
import re

# Keys whose values are secret wherever they appear (JSON bodies, dict reprs,
# header dumps). Matched case-insensitively against `key: value`, `key=value`,
# and `"key": "value"` shapes.
SECRET_KEYS = (
    "app_token",
    "session_token",
    "password",
    "challenge",
    "x-fbx-app-auth",
)

REDACTED = "«redacted»"

# "app_token": "abc"   |   app_token=abc   |   X-Fbx-App-Auth: abc
_PATTERNS = [
    re.compile(
        r'(?i)(["\']?' + re.escape(key) + r'["\']?\s*[:=]\s*)(["\']?)([^"\'\s,}&]+)(\2)'
    )
    for key in SECRET_KEYS
]


def redact(text: str) -> str:
    """Replace any secret-looking `key: value` pair in `text` with a marker."""
    for pat in _PATTERNS:
        text = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(4)}", text)
    return text


class RedactingFilter(logging.Filter):
    """A logging filter that scrubs secrets from every record's message.

    Attach to any handler that could emit request/response detail. It rewrites
    the formatted message and stringifies args defensively, so neither the
    format string nor its interpolated values can carry a token through.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install(logger: logging.Logger) -> None:
    """Idempotently attach the redacting filter to a logger."""
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
