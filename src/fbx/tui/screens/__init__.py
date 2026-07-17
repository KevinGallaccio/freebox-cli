"""The domain registry — one entry per screen; drives dashboard navigation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from textual.screen import Screen

from .calls import CallsScreen
from .connection import ConnectionScreen
from .contacts import ContactsScreen
from .dhcp import DhcpScreen
from .downloads import DownloadsScreen
from .fs import FsScreen
from .fw import FwScreen
from .lan import LanScreen
from .storage import StorageScreen
from .system import SystemScreen
from .top import TopScreen
from .vm import VmScreen
from .wifi import WifiScreen


@dataclass(frozen=True)
class Domain:
    key: str
    title: str
    blurb: str  # one-liner shown in the dashboard menu
    factory: Callable[[], Screen]


# Order is the dashboard menu order. Menu entries show the title alone;
# the blurb appears in the description box under the menu as the cursor
# moves, so it can afford a full sentence's worth of words.
DOMAINS: dict[str, Domain] = {
    d.key: d
    for d in (
        Domain("top", "Activity", "live throughput and sensors", TopScreen),
        Domain("connection", "Connection", "WAN, fiber, IPv6, logs", ConnectionScreen),
        Domain("wifi", "Wi-Fi", "radios, networks, clients", WifiScreen),
        Domain("lan", "Devices", "who's on the network", LanScreen),
        Domain("dhcp", "DHCP", "leases and reservations", DhcpScreen),
        Domain("fw", "Port forwarding", "rules, DMZ, UPnP", FwScreen),
        Domain("downloads", "Downloads", "the download manager", DownloadsScreen),
        Domain("fs", "Files", "browse the box's disks", FsScreen),
        Domain("storage", "Storage", "disks and partitions", StorageScreen),
        Domain("vm", "Virtual machines", "lifecycle, console, exec", VmScreen),
        Domain("calls", "Phone", "call log", CallsScreen),
        Domain("contacts", "Contacts", "address book", ContactsScreen),
        Domain("system", "System", "firmware, sensors, reboot", SystemScreen),
    )
}
