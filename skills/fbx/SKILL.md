---
name: fbx
description: Drive a Freebox (Ultra) — connection, LAN, DHCP, port forwarding, Wi-Fi, files, downloads, calls, contacts, and VMs — through the fbx MCP tools or CLI. Use whenever the user asks about their Freebox, their home network behind one, or the VMs it hosts.
---

# Driving a Freebox with fbx

`fbx` mirrors Freebox OS: everything the web UI can do, from tools/commands.
Prefer the MCP tools (`fbx_*`) when the fbx MCP server is connected; otherwise
use the CLI (`fbx … --json`). Both are thin adapters over the same core — same
behavior, same shapes.

## Preconditions

- The machine must already be **paired**: `fbx auth status` tells you. Pairing
  (`fbx auth login`) is a one-time HUMAN step — it blocks until someone presses
  the ▶ button on the box's front panel. **Never run it yourself**; if not
  paired, ask the user to run it at a terminal.
- Some permissions (notably `settings` and `home`) can only be granted by hand
  in Freebox OS → Paramètres → Gestion des accès → Applications → fbx. A
  `missing the X permission` error means the user has to tick a box there.

## The contract

- CLI: stdout is data, stderr is messages. `--json` prints the **whole**
  upstream result object — always use it when parsing. Exit codes: 2 auth,
  3 not paired, 4 missing permission, 5 box unreachable.
- MCP: results are the box's raw JSON; errors come back as tool errors with
  the reason and the fix.

## Rules that prevent real damage

1. **Discover ids live, never assume or reuse them.** Wi-Fi AP ids shift
   across firmware/reboots (acting on a stale id can disable the wrong radio),
   VM/host/redirection/lease ids are box-specific, and Wi-Fi MAC-filter ids
   are `<mac>-<type>`, not the bare MAC. List first (`fbx_wifi_aps`,
   `fbx_vm_list`, `fbx_lan_devices`, …), then act.
2. **Config writes are read-modify-write.** `*_config_set` / `*_set` tools
   take partial objects: read the current config, send ONLY the fields you
   mean to change. Never reconstruct a whole config from assumptions.
3. **Destructive tools need explicit user confirmation first** — they are
   annotated (`destructiveHint`) and their descriptions say so: reboot /
   shutdown, Wi-Fi off (global or temp), deleting files/leases/rules/VMs,
   erasing downloads. In the CLI these prompt; agents must pass `--yes` and
   should only after the user has agreed.
4. **Wi-Fi writes can cut the connection you're using.** Disabling Wi-Fi or a
   band may drop the very machine running fbx (prefer `fbx_wifi_temp_disable`
   with `keep`, and warn the user). SSID/key are usually shared across all
   bands (`use_shared_params`): one BSS write changes every band, and 6 GHz
   requires WPA3 — don't downgrade security band-by-band.
5. **The user's box config may be deliberate.** A pinned channel, a disabled
   feature, an odd DNS: ask before "fixing" anything you didn't change.

## Domain notes

- **Files**: paths are plain absolute strings (`/Freebox/…`); fbx handles the
  API's base64. `mv`/`cp`/`rm` run as box-side tasks — MCP tools wait by
  default and report `done`/`pending`/failed honestly; `rm` is permanent (no
  trash).
- **VMs** (Freebox Ultra: aarch64 hypervisor): create disk → create VM →
  start. Disk ops are tasks too. `fbx_vm_exec` sends one command line to the
  guest's **serial console** and returns raw tty output (echo + output + next
  prompt, no exit code) — it needs a shell on the guest's serial tty (autologin
  getty on `ttyAMA0` for the stock images). `fbx vm console` is the
  interactive version (Ctrl-] detaches). Prefer `fbx_vm_shutdown` (ACPI) over
  `fbx_vm_stop` (plug-pull).
- **Port forwarding**: some boxes reject WAN ports outside an allowed range
  (`port_outside_range`) — treat "the box refused" as a real answer, not a bug.
- **Downloads**: `add` accepts URLs/magnets; `erase` deletes the files too.

## The escape hatch

No dedicated tool for an endpoint yet? `fbx_api_request` (or `fbx api GET
path/`) makes a raw authenticated call to anything in the Freebox API. The
box's own current reference is at `http://mafreebox.freebox.fr/doc` (public,
unauthenticated, firmware-accurate). Double-check method/path/body there
before any raw write, and treat raw POST/PUT/DELETE like destructive tools:
confirm with the user.

## Quick reference

```sh
fbx auth status                     # paired? which box?
fbx --json system info              # firmware, uptime, temps
fbx --json connection status        # WAN state + public IPs
fbx --json lan devices              # who's on the network
fbx --json wifi ap                  # radios (ids are ephemeral!)
fbx --json vm list                  # VMs
fbx vm exec 1 "uptime"              # run a command in a guest
fbx api GET dhcp/config/            # raw escape hatch
```
