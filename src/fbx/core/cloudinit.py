"""Best-effort peek into cloud-init userdata for guest login hints.

Not a YAML parser (no YAML dependency): a line scanner for the few
`#cloud-config` keys that carry guest credentials. Display-only — the
console never types these into a guest tty.
"""

from __future__ import annotations

import re

# `password: x` / `plain_text_passwd: x` / `passwd: x`, possibly a list item.
_PASSWORD_KEY = re.compile(
    r"^\s*-?\s*(?:password|plain_text_passwd|passwd)\s*:\s*(\S.*?)\s*$"
)
# `- name: alice` — remembered so a following password gets its username.
_NAME_KEY = re.compile(r"^\s*-?\s*name\s*:\s*(\S+)\s*$")
# A raw `user:pass` line inside a chpasswd list (block scalar or YAML list).
_CHPASSWD_PAIR = re.compile(r"^\s*-?\s*([A-Za-z_][\w-]*):([^\s:]+)\s*$")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def find_credentials(userdata: str) -> list[tuple[str, str]]:
    """`(label, secret)` pairs found in a cloud-config document.

    Labels are usernames when the document names one (a preceding `name:`,
    or chpasswd `user:pass` pairs), otherwise the generic "password".
    """
    found: list[tuple[str, str]] = []
    in_chpasswd = False
    chpasswd_indent = 0
    last_name: str | None = None
    for raw in userdata.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if in_chpasswd and indent <= chpasswd_indent:
            in_chpasswd = False
        if re.match(r"^\s*chpasswd\s*:\s*$", line):
            in_chpasswd = True
            chpasswd_indent = indent
            continue
        if name := _NAME_KEY.match(line):
            last_name = _unquote(name.group(1))
            continue
        if password := _PASSWORD_KEY.match(line):
            found.append((last_name or "password", _unquote(password.group(1))))
            continue
        # The bare `user:pass` shape means something only inside chpasswd.
        if in_chpasswd and not re.match(r"^\s*(list|users|expire)\s*:", line):
            if pair := _CHPASSWD_PAIR.match(line):
                found.append((pair.group(1), _unquote(pair.group(2))))
    return found
