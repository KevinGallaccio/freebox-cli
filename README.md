# fbx — Freebox Ultra CLI & app

Full control of the **Freebox Ultra** (Freebox OS) from the terminal:
an **interactive app** you open with a bare `fbx`, a complete scriptable
CLI, and an MCP server so coding agents can drive the box — connection,
LAN, DHCP, port forwarding, Wi-Fi, downloads, files, telephony, and the
undocumented **virtual machine manager**.

**Unofficial.** This project is not affiliated with Free or the Iliad group.

## Install

With [Homebrew](https://brew.sh), or from [PyPI](https://pypi.org/project/fbx/)
with [`uv`](https://astral.sh/uv) / `pipx`, on a machine on the same LAN as
your Freebox:

```sh
brew install kevingallaccio/tap/fbx
# or
uv tool install fbx        # or: pipx install fbx
```

One-off runs work without installing anything: `uvx fbx system info`.

## The app

Type `fbx` and you're in: a dashboard of the whole box — live WAN
throughput, radios, devices, VMs, storage, downloads, phone — plus
**suggestions** pointing at things worth doing (WPS left on, finished
downloads to clean up, a stopped VM, unnamed devices…). Navigate into any
domain, act, and quit with `q`. Anything destructive asks first.

![The fbx app: dashboard with live tiles and suggestions](docs/screenshot-app.svg)

Inside the app: a live `top`-style view (1 s throughput sparklines,
temperatures, per-client Wi-Fi signal), a **terminal-in-terminal file
shell** (`/Freebox > ls`, `cd`, `mkdir`, `mv`, `cp`, `rm`, `share`), and a
full VM screen that attaches the **serial console** right in place
(Ctrl-] detaches, you're back in the app).

The app is one of three faces over the same core — the CLI below and the
MCP server stay byte-for-byte scriptable; `fbx` with no arguments only
opens the app on a real terminal (piped, it prints help exactly like
before).

## Getting started

Authorize this machine with your box — a one-time step that needs a physical
button press:

```sh
fbx auth login
```

`fbx` registers with the box, then asks you to **press ▶ (the right arrow) on
the front display of your Freebox** to grant access. The resulting token is
saved at `~/.config/fbx/credentials.json` (mode 0600); sessions renew
automatically after that.

```sh
fbx auth status          # are we authorized, and for which box?
fbx auth permissions     # what can this app do?
fbx system info          # firmware, model, uptime, temperatures, fans
```

## Reading the box

Every domain gets a noun command with Rich tables (and `--json` for scripts):

```sh
fbx connection status    # WAN state, addresses, live throughput
fbx connection ftth      # optical link + SFP power (fiber health)
fbx connection ipv6      # delegated prefixes
fbx connection logs      # WAN up/down history
fbx lan devices          # who's on the network (--all for inactive too)
fbx lan interfaces       # browsable interfaces (pub, wifiguest, …)
fbx dhcp leases          # active leases
fbx dhcp static          # static reservations
fbx fw redirs            # port-forwarding rules
fbx fw dmz               # DMZ host
fbx fw incoming          # built-in services' incoming ports
fbx fw upnp              # UPnP IGD state (+ upnp-redirs for client mappings)
fbx wifi status          # radios (2.4/5/5/6 GHz on the Ultra)
fbx wifi ap              # per-radio channel/width/state
fbx wifi bss             # SSIDs + security (keys only via --json)
fbx wifi stations        # associated clients, signal, rates
fbx wifi mac-filter      # MAC access-control list
fbx wifi neighbors 10    # channel survey: what AP 10 hears (--scan refreshes)
fbx wifi key             # print the Wi-Fi passphrase (pipe to pbcopy)
fbx downloads list       # download tasks
fbx downloads stats      # manager counters
fbx storage disks        # physical disks
fbx storage partitions   # space usage
fbx fs ls /Freebox       # browse files on the box
fbx calls list           # landline call log
fbx contacts list        # address book
```

## Controlling the box

Every domain has mutating commands too. Writes print a friendly confirmation on
stderr and the box's response object on stdout (`--json`-clean); genuinely
irreversible actions prompt for confirmation, bypassable with `--yes`:

```sh
# DHCP reservations + Wake-on-LAN
fbx dhcp static-add 02:00:00:00:00:99 192.168.1.222 -c "printer"
fbx dhcp static-rm  02:00:00:00:00:99
fbx wol 02:00:00:00:00:0a

# Port forwarding / DMZ / UPnP
fbx fw redir-add 192.168.1.42 8080 --wan-port 8080 --comment web
fbx fw redir-rm 3
fbx fw dmz-set 192.168.1.50        # …or dmz-off
fbx fw upnp-set --disabled

# Wi-Fi (disabling Wi-Fi globally asks first — you may be on it)
fbx wifi bss-set 02:00:00:00:00:10 --ssid "Home" --key "s3cret…"
fbx wifi mac-filter-add 02:00:00:00:00:99 --type blacklist
fbx wifi config-set --disabled          # prompts unless --yes

# Downloads
fbx downloads add "magnet:?xt=urn:btih:…"
fbx downloads pause 3 && fbx downloads resume 3
fbx downloads erase 3                    # removes files → prompts

# Files (mv/cp/rm are task-based and polled to completion)
fbx fs mkdir /Freebox/Téléchargements new
fbx fs cp /Freebox/a --to /Freebox/b
fbx fs rm /Freebox/old --yes
fbx fs share /Freebox/movie.mkv --days 7

# LAN / connection / system / address book
fbx lan rename ether-02:00:00:00:00:0a "Living Room TV"
fbx connection config-set --no-ping
fbx system reboot                        # prompts unless --yes
fbx contacts add "Sandy Kilo" --first Sandy --last Kilo
```

## Virtual machines

The Freebox Ultra runs an aarch64 hypervisor. `fbx vm` drives the whole
lifecycle — including a **serial console over WebSocket**, the way `virsh
console` attaches to a guest tty:

```sh
fbx vm list                              # every VM + status, vCPU, RAM
fbx vm info                              # hypervisor capacity / free headroom
fbx vm distros                           # Free's catalog of cloud images

# create a disk, then a VM, then boot it
fbx vm disk-create /Freebox/VMs/web.qcow2 8G
fbx vm create --name web --disk /Freebox/VMs/web.qcow2 \
    --memory 512 --vcpus 1 --cloudinit-file cloud-init.yaml
fbx vm start 2
fbx vm console 2                         # attach the serial console (Ctrl-] detaches)

fbx vm shutdown 2                         # graceful ACPI power-off
fbx vm stop 2                            # hard power-off (prompts)
fbx vm rm 2                              # delete the definition (prompts; disk file kept)

# one-shot command on the serial console (needs a shell on the guest tty)
fbx vm exec 2 "uptime"

fbx vm userdata 2                        # print the raw cloud-init userdata
```

The serial console needs the bundled `websockets` dependency; paths for
`--disk`/`--cd` are absolute (`/Freebox/…`), and `cloudinit_userdata` (which
holds SSH keys and passwords) is shown only via `--json`, never in a table.

## MCP server — let a coding agent drive the box

`fbx mcp serve` exposes the whole surface (107 tools across 13 toolsets:
system, connection, lan, dhcp, fw, wifi, downloads, files, calls, contacts,
storage, vm, raw) as an [MCP](https://modelcontextprotocol.io) server over
stdio. Same core as the CLI, so behavior is identical; destructive operations
carry MCP annotations so agents know to ask before rebooting your network.

Two agent-specific defaults (each overridable per call): secret fields —
cloud-init userdata, Wi-Fi keys — are **masked** unless the agent passes
`include_secrets: true` (humans use `fbx vm userdata` / `fbx wifi key`), and
`fbx_lan_devices` returns currently-reachable devices unless `all: true`
(the full history runs to hundreds of KB on a lived-in LAN).

**Claude Code — the plugin (recommended).** One install gets the MCP server
*and* the fbx skill (usage guardrails for the agent). In Claude Code:

```
/plugin marketplace add KevinGallaccio/fbx
/plugin install fbx@fbx
```

The plugin launches the server via `uvx` **from the plugin's own copy of the
code**, so updating the plugin updates the server — nothing else to refresh:

```
/plugin marketplace update fbx
```

It needs [`uv`](https://astral.sh/uv) on your PATH, and your box must already
be paired (`fbx auth login`, one physical button press).

**Any MCP client (Claude Desktop, Cursor, Zed, …).** Install fbx with the
`mcp` extra and point your client at `fbx mcp serve`:

```sh
uv tool install 'fbx[mcp]'
fbx mcp install        # prints the exact wiring for common clients
```

```json
{ "mcpServers": { "fbx": { "command": "fbx", "args": ["mcp", "serve"] } } }
```

**Dial the surface to taste.** Everything is exposed by default — the
operator decides, not the tool:

```sh
fbx mcp serve --read-only              # no writes at all
fbx mcp serve --toolsets vm,wifi       # only these domains
fbx mcp serve --exclude raw            # drop the raw API escape hatch
fbx mcp tools                          # preview what a filter set exposes
```

## The `--json` contract

Every command that emits data supports `--json`, and it prints the **whole**
upstream result object — nothing lossy. Data goes to stdout; all messages,
spinners, and errors go to stderr, so pipes stay clean:

```sh
fbx --json system info | jq '.firmware_version'
fbx api GET connection/ | jq '{state, media, rate_down}'
```

### `fbx api` — the escape hatch

Make a raw authenticated call to any endpoint. Handy wherever a typed command
doesn't exist yet, and for exploring the API. Paths can be pasted straight from
the docs (a leading `/api/latest/` or `/api/v16/` is stripped):

```sh
fbx api GET system/
fbx api GET vm/
fbx api POST vm/1/start
fbx api PUT wifi/config/ --data '{"enabled": true}'
```

## Roadmap

- [x] Phase 0 — API reconnaissance on a real Freebox Ultra (kept private)
- [x] Phase 1 — discovery, auth, `fbx system info`, `fbx api` (**v0.1.0**)
- [x] Phase 2 — all read-only domains, `--json` everywhere (**v0.2.0**)
- [x] Phase 3 — write operations across every domain (**v0.3.0**)
- [x] Phase 4 — VM lifecycle + serial console (**v0.4.0**)
- [x] Phase 5 — MCP server + Claude Code plugin & skill (**v0.5.0**)
- [x] Phase 6 — PyPI + Homebrew tap + the interactive app (**v0.6.0**)

## Development

No install needed to hack on the repo — the `./fbx` shim bootstraps `uv` and
runs the CLI straight from the source tree:

```sh
git clone https://github.com/KevinGallaccio/fbx
cd fbx
./fbx --version

uv sync                 # install deps + dev tools
uv run pytest           # the test suite runs fully offline (respx-mocked box)
uv run ruff check src tests
```

No Freebox required to hack on `fbx`: the tests mock the box, so contributors
without one can work on the whole thing.

---

## Français

`fbx` pilote la **Freebox Ultra** (Freebox OS) depuis le terminal : une
**application interactive** (tapez `fbx` : tableau de bord, suggestions,
navigation dans tous les domaines), une CLI scriptable complète — état de
la connexion, appareils du réseau local, DHCP, redirections de ports,
Wi-Fi, téléchargements, fichiers, téléphonie, et le gestionnaire de
**machines virtuelles** (API non documentée) — ainsi qu'un serveur MCP
pour les agents de code.

### Démarrage

```sh
brew install kevingallaccio/tap/fbx   # ou : uv tool install fbx
fbx auth login       # autorisation unique — appuyez sur ▶ sur la Freebox
fbx                  # l'application interactive
fbx system info      # état de la box
fbx --json api GET connection/ | jq
```

Pour les agents : `fbx mcp serve` (serveur MCP), ou dans Claude Code
`/plugin marketplace add KevinGallaccio/fbx` puis `/plugin install fbx@fbx`.

**Non officiel.** Ce projet n'est pas affilié à Free ni au groupe Iliad.
