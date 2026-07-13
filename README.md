# fbx — Freebox Ultra CLI

A modern command-line interface for the **Freebox Ultra** (Freebox OS):
connection status, LAN devices, DHCP, port forwarding, Wi-Fi, downloads,
VPN, telephony — and the undocumented **virtual machine manager** — plus an
MCP server so coding agents can drive the box.

> ⚠️ **Early development (v0.4.0).** Working today: discovery, authorization,
> the read-only view of every major domain, full write control across DHCP,
> port forwarding/DMZ/UPnP, Wi-Fi, downloads, filesystem, connection, system,
> calls and contacts — **and the virtual-machine manager**, including a
> `fbx vm console` serial console over WebSocket. The MCP server lands next
> (see the roadmap).

**Unofficial.** This project is not affiliated with Free or the Iliad group.

## Install (from the repo)

You need [`uv`](https://astral.sh/uv) and a machine on the same LAN as your
Freebox. The repo ships a `./fbx` shim that bootstraps everything:

```sh
git clone https://github.com/KevinGallaccio/fbx
cd fbx
./fbx --version
```

`uv` fetches the right Python and dependencies on first run; it's instant
after that. (Homebrew, prebuilt binaries, and PyPI come in Phase 6.)

## Getting started

Authorize this machine with your box — a one-time step that needs a physical
button press:

```sh
./fbx auth login
```

`fbx` registers with the box, then asks you to **press ▶ (the right arrow) on
the front display of your Freebox** to grant access. The resulting token is
saved at `~/.config/fbx/credentials.json` (mode 0600); sessions renew
automatically after that.

```sh
./fbx auth status          # are we authorized, and for which box?
./fbx auth permissions     # what can this app do?
./fbx system info          # firmware, model, uptime, temperatures, fans
```

## Reading the box

Every domain gets a noun command with Rich tables (and `--json` for scripts):

```sh
./fbx connection status    # WAN state, addresses, live throughput
./fbx connection ftth      # optical link + SFP power (fiber health)
./fbx connection ipv6      # delegated prefixes
./fbx connection logs      # WAN up/down history
./fbx lan devices          # who's on the network (--all for inactive too)
./fbx lan interfaces       # browsable interfaces (pub, wifiguest, …)
./fbx dhcp leases          # active leases
./fbx dhcp static          # static reservations
./fbx fw redirs            # port-forwarding rules
./fbx fw dmz               # DMZ host
./fbx fw incoming          # built-in services' incoming ports
./fbx fw upnp              # UPnP IGD state (+ upnp-redirs for client mappings)
./fbx wifi status          # radios (2.4/5/5/6 GHz on the Ultra)
./fbx wifi ap              # per-radio channel/width/state
./fbx wifi bss             # SSIDs + security (keys only via --json)
./fbx wifi stations        # associated clients, signal, rates
./fbx wifi mac-filter      # MAC access-control list
./fbx downloads list       # download tasks
./fbx downloads stats      # manager counters
./fbx storage disks        # physical disks
./fbx storage partitions   # space usage
./fbx fs ls /Freebox       # browse files on the box
./fbx calls list           # landline call log
./fbx contacts list        # address book
```

## Controlling the box

Every domain has mutating commands too. Writes print a friendly confirmation on
stderr and the box's response object on stdout (`--json`-clean); genuinely
irreversible actions prompt for confirmation, bypassable with `--yes`:

```sh
# DHCP reservations + Wake-on-LAN
./fbx dhcp static-add 02:00:00:00:00:99 192.168.1.222 -c "printer"
./fbx dhcp static-rm  02:00:00:00:00:99
./fbx wol 02:00:00:00:00:0a

# Port forwarding / DMZ / UPnP
./fbx fw redir-add 192.168.1.42 8080 --wan-port 8080 --comment web
./fbx fw redir-rm 3
./fbx fw dmz-set 192.168.1.50        # …or dmz-off
./fbx fw upnp-set --disabled

# Wi-Fi (disabling Wi-Fi globally asks first — you may be on it)
./fbx wifi bss-set 02:00:00:00:00:10 --ssid "Home" --key "s3cret…"
./fbx wifi mac-filter-add 02:00:00:00:00:99 --type blacklist
./fbx wifi config-set --disabled          # prompts unless --yes

# Downloads
./fbx downloads add "magnet:?xt=urn:btih:…"
./fbx downloads pause 3 && ./fbx downloads resume 3
./fbx downloads erase 3                    # removes files → prompts

# Files (mv/cp/rm are task-based and polled to completion)
./fbx fs mkdir /Freebox/Téléchargements new
./fbx fs cp /Freebox/a --to /Freebox/b
./fbx fs rm /Freebox/old --yes
./fbx fs share /Freebox/movie.mkv --days 7

# LAN / connection / system / address book
./fbx lan rename ether-02:00:00:00:00:0a "Living Room TV"
./fbx connection config-set --no-ping
./fbx system reboot                        # prompts unless --yes
./fbx contacts add "Sandy Kilo" --first Sandy --last Kilo
```

## Virtual machines

The Freebox Ultra runs an aarch64 hypervisor. `fbx vm` drives the whole
lifecycle — including a **serial console over WebSocket**, the way `virsh
console` attaches to a guest tty:

```sh
./fbx vm list                              # every VM + status, vCPU, RAM
./fbx vm info                              # hypervisor capacity / free headroom
./fbx vm distros                           # Free's catalog of cloud images

# create a disk, then a VM, then boot it
./fbx vm disk-create /Freebox/VMs/web.qcow2 8G
./fbx vm create --name web --disk /Freebox/VMs/web.qcow2 \
    --memory 512 --vcpus 1 --cloudinit-file cloud-init.yaml
./fbx vm start 2
./fbx vm console 2                         # attach the serial console (Ctrl-] detaches)

./fbx vm shutdown 2                         # graceful ACPI power-off
./fbx vm stop 2                            # hard power-off (prompts)
./fbx vm rm 2                              # delete the definition (prompts; disk file kept)
```

The serial console needs the bundled `websockets` dependency; paths for
`--disk`/`--cd` are absolute (`/Freebox/…`), and `cloudinit_userdata` (which
holds SSH keys and passwords) is shown only via `--json`, never in a table.

## The `--json` contract

Every command that emits data supports `--json`, and it prints the **whole**
upstream result object — nothing lossy. Data goes to stdout; all messages,
spinners, and errors go to stderr, so pipes stay clean:

```sh
./fbx --json system info | jq '.firmware_version'
./fbx api GET connection/ | jq '{state, media, rate_down}'
```

### `fbx api` — the escape hatch

Make a raw authenticated call to any endpoint. Handy wherever a typed command
doesn't exist yet, and for exploring the API. Paths can be pasted straight from
the docs (a leading `/api/latest/` or `/api/v16/` is stripped):

```sh
./fbx api GET system/
./fbx api GET vm/
./fbx api POST vm/1/start
./fbx api PUT wifi/config/ --data '{"enabled": true}'
```

## Roadmap

- [x] Phase 0 — API reconnaissance on a real Freebox Ultra (kept private)
- [x] Phase 1 — discovery, auth, `fbx system info`, `fbx api` (**v0.1.0**)
- [x] Phase 2 — all read-only domains, `--json` everywhere (**v0.2.0**)
- [x] Phase 3 — write operations across every domain (**v0.3.0**)
- [x] Phase 4 — VM lifecycle + serial console (**v0.4.0**)
- [ ] Phase 5 — MCP server + Claude Skill
- [ ] Phase 6 — splash, `fbx top`, Homebrew tap, PyPI

## Development

```sh
uv sync                 # install deps + dev tools
uv run pytest           # the test suite runs fully offline (respx-mocked box)
uv run ruff check src/  # lint
```

No Freebox required to hack on `fbx`: the tests mock the box, so contributors
without one can work on the whole thing.

---

## Français

`fbx` est une interface en ligne de commande pour la **Freebox Ultra**
(Freebox OS) : état de la connexion, appareils du réseau local, DHCP,
redirections de ports, Wi-Fi, téléchargements, VPN, téléphonie — et le
gestionnaire de **machines virtuelles** (API non documentée) — ainsi qu'un
serveur MCP pour les agents de code.

### Démarrage

```sh
./fbx auth login       # autorisation unique — appuyez sur ▶ sur la Freebox
./fbx system info      # état de la box
./fbx --json api GET connection/ | jq
```

**Non officiel.** Ce projet n'est pas affilié à Free ni au groupe Iliad.
