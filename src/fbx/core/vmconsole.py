"""The VM serial console — a raw byte pump over a WebSocket.

`GET /vm/{id}/console` upgrades to a WebSocket that streams the guest's serial
tty, byte-for-byte, in both directions (undocumented upstream; verified against
the box). This module attaches the local terminal to it: stdin → WS, WS →
stdout, with the local tty in raw mode so control keys reach the guest. A single
escape key (Ctrl-] by default, like telnet) detaches cleanly without touching
the guest.

Auth rides the same session as the HTTP API — the WebSocket handshake carries
the `X-Fbx-App-Auth` session token as a header. POSIX only (needs `termios`);
Windows raises a clear error.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from .errors import FbxError

# Ctrl-] (telnet's escape) — the local detach key; never forwarded to the guest.
DETACH_KEY = 0x1D


class FbxConsoleError(FbxError):
    """The serial console could not be attached (connection or platform error)."""


def serial_console_url(base_url: str, vm_id: int) -> str:
    """The ws:// URL for a VM's serial console, from the HTTP API base URL.

    `http://host/api/v16/` → `ws://host/api/v16/vm/{id}/console`. HTTPS maps to
    wss.
    """
    root = base_url if base_url.endswith("/") else base_url + "/"
    if root.startswith("https://"):
        root = "wss://" + root[len("https://"):]
    elif root.startswith("http://"):
        root = "ws://" + root[len("http://"):]
    return f"{root}vm/{vm_id}/console"


def vnc_url(base_url: str, vm_id: int) -> str:
    """The ws:// URL for a VM's VNC framebuffer (needs `enable_screen`)."""
    return serial_console_url(base_url, vm_id).replace(f"vm/{vm_id}/console", f"vm/{vm_id}/vnc")


async def _pump(url: str, token: str, detach: int) -> None:
    # Imported lazily so the dependency is only needed when the console is used.
    from websockets.asyncio.client import connect

    async with connect(url, additional_headers={"X-Fbx-App-Auth": token}) as ws:

        async def ws_to_stdout() -> None:
            async for message in ws:
                data = message.encode() if isinstance(message, str) else message
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()

        async def stdin_to_ws() -> None:
            import os

            loop = asyncio.get_running_loop()
            fd = sys.stdin.fileno()
            queue: asyncio.Queue[bytes] = asyncio.Queue()

            def on_readable() -> None:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    chunk = b""
                queue.put_nowait(chunk)

            loop.add_reader(fd, on_readable)
            try:
                while True:
                    chunk = await queue.get()
                    if not chunk:  # EOF on stdin
                        return
                    if detach in chunk:
                        head = chunk[: chunk.index(detach)]
                        if head:
                            await ws.send(head)
                        return
                    await ws.send(chunk)
            finally:
                loop.remove_reader(fd)

        reader = asyncio.create_task(ws_to_stdout())
        writer = asyncio.create_task(stdin_to_ws())
        done, pending = await asyncio.wait(
            {reader, writer}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc


def run_console(base_url: str, token: str, vm_id: int, *, detach: int = DETACH_KEY) -> None:
    """Attach the local terminal to a VM's serial console until detach/EOF.

    Puts stdin in raw mode (if it's a tty) so control keys reach the guest, and
    always restores it. Raises `FbxConsoleError` on an unsupported platform or a
    connection failure.
    """
    try:
        import termios
        import tty
    except ImportError as exc:  # pragma: no cover — Windows
        raise FbxConsoleError(
            "the serial console requires a POSIX terminal (termios); "
            "not supported on this platform."
        ) from exc

    url = serial_console_url(base_url, vm_id)
    fd = sys.stdin.fileno()
    is_tty = sys.stdin.isatty()
    saved = termios.tcgetattr(fd) if is_tty else None
    if is_tty:
        tty.setraw(fd)
    try:
        asyncio.run(_pump(url, token, detach))
    except FbxError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any WS/transport failure cleanly
        raise FbxConsoleError(f"serial console failed: {exc}") from exc
    finally:
        if saved is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def console_runner(client: Any, vm_id: int, *, detach: int = DETACH_KEY) -> None:
    """Attach using an authenticated client (needs its session token + base URL).

    Requires the `vm` permission; the client must already hold a session."""
    client.require_permission("vm")
    client.ensure_session()
    run_console(client.base_url, client.session_token, vm_id, detach=detach)
