# fbx — Freebox Ultra CLI

A modern command-line interface for the **Freebox Ultra** (Freebox OS):
connection status, LAN devices, DHCP, port forwarding, Wi-Fi, downloads,
VPN, telephony — and the undocumented **virtual machine manager** — plus an
MCP server so coding agents can drive the box.

> ⚠️ **Early development.** Nothing to install yet. Phase 0 (API
> reconnaissance) is complete — see [`docs/api-notes.md`](docs/api-notes.md),
> the reverse-engineered Freebox OS API spec this project is built against.

**Unofficial.** This project is not affiliated with Free or the Iliad group.

## Roadmap

- [x] Phase 0 — API recon on a real Freebox Ultra → [`docs/api-notes.md`](docs/api-notes.md)
- [ ] Phase 1 — discovery, auth, `fbx system info`, `fbx api` (v0.1.0)
- [ ] Phase 2 — all read-only domains, `--json` everywhere
- [ ] Phase 3 — write operations (port forwarding, DHCP, Wi-Fi, downloads)
- [ ] Phase 4 — VM lifecycle + serial console
- [ ] Phase 5 — MCP server + Claude Skill
- [ ] Phase 6 — splash, `fbx top`, Homebrew tap, PyPI

---

## Français

`fbx` est une interface en ligne de commande pour la **Freebox Ultra**
(Freebox OS) : état de la connexion, appareils du réseau local, DHCP,
redirections de ports, Wi-Fi, téléchargements, VPN, téléphonie — et le
gestionnaire de **machines virtuelles** (API non documentée) — ainsi qu'un
serveur MCP pour les agents de code.

> ⚠️ **En cours de développement.** Rien à installer pour le moment.

**Non officiel.** Ce projet n'est pas affilié à Free ni au groupe Iliad.
