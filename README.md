# fbx — Freebox Ultra CLI

A modern command-line interface for the **Freebox Ultra** (Freebox OS):
connection status, LAN devices, DHCP, port forwarding, Wi-Fi, downloads,
VPN, telephony — and the undocumented **virtual machine manager** — plus an
MCP server so coding agents can drive the box.

> ⚠️ **Early development (v0.1.0).** Working today: discovery, authorization,
> `fbx system info`, and the `fbx api` raw-call escape hatch. More domains land
> phase by phase (see the roadmap).

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
- [ ] Phase 2 — all read-only domains, `--json` everywhere
- [ ] Phase 3 — write operations (port forwarding, DHCP, Wi-Fi, downloads)
- [ ] Phase 4 — VM lifecycle + serial console
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
