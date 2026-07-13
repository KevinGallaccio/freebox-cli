# Freebox OS API — reverse-engineering notes

> **The source of truth for `fbx`.** Everything the CLI, MCP server, and Skill
> know about the Freebox API is derived from what's written here.

## What this is

The Freebox OS web UI is a single-page app that talks to the exact REST +
WebSocket API this project wraps. These notes were produced by **watching the
UI drive that API** — instrumenting every `fetch`/`XHR`/`WebSocket` call the
page makes, then clicking through every section and bulk-fetching every
documented read-only endpoint. The captures live (scrubbed) in
[`recon/capture/`](../recon/capture/); the tooling is in [`recon/`](../recon/).

Where the public SDK and the box disagree, **the box wins** — that's the whole
reason this file exists.

## Observed on

| | |
|---|---|
| **Model** | Freebox Ultra — hardware `fbxgw9-r1`, `device_type` `FreeboxServer9,1` |
| **Firmware** | 4.12.2 |
| **API version** | **16.0** (`api_version` from `GET /api_version`) |
| **Date** | 2026-07-13 |
| **Base path** | `/api/v16/` — but the UI uses the undocumented alias `/api/latest/` everywhere, and it works |

Anything marked **[undocumented upstream]** exists on the box but is absent
from the public SDK at <https://dev.freebox.fr/sdk/os/>, which is frozen at API
4.0 (it still targets the 2013 Revolution, `FreeboxServer1,2`). Anything marked
**[UNSTABLE upstream]** is flagged unstable in the box's own docs and may change
between firmware releases — isolate it.

> ⚠️ **Firmware-versioned.** Every shape below was true on firmware 4.12.2 /
> API 16.0. The undocumented endpoints (VM, Home, LTE backup, VPN client) are
> the ones most likely to drift — re-verify against a fresh capture if the
> firmware has moved.

## The one-paragraph summary (what the public SDK doesn't have)

The public SDK is missing, and this document adds: the **entire Virtual
Machines API** (18 endpoints — list/create/modify/lifecycle, plus serial-console
and VNC WebSockets, plus async task-polled disk create/resize); the **Home
automation / camera** domain; **`connection/lte/backup`** (the Ultra's 4G/5G
failover); **`connection/ftth/`** with the SFP optical-module telemetry;
**`connection/full/`**; the **VPN client** (as opposed to server); the full
**Wi-Fi 6E/7 + WPA3 + GCMP-256** surface; the **`/api/latest/` path alias**; and
the **WebSocket event vocabulary** (`register` shape + the concrete push events,
including the `lan_host_` → `host_` prefix discrepancy documented below). It
also confirms a load-bearing behavioural fact: **the UI polls `/system/` and
`/connection/` about once a second rather than streaming them** — the
WebSocket carries only a handful of discrete events, which is what `fbx watch`
and `fbx top` should actually build on.

---

## Discovery, versioning, authentication & TLS

The Freebox OS API is a JSON-over-HTTP service. Every response is wrapped in `{"success": bool, ...}`; success payloads carry a `result` object (or the fields inline, as with `/api_version`), while failures carry `msg` and `error_code` (e.g. `{"success": false, "error_code": "notsupp"}` — a real captured failure). Bootstrapping a client is a three-step dance: discover the box, read `/api_version` to compute the base URL, then run the challenge/response login to get a session token.

### `GET /api_version`

Unauthenticated discovery endpoint served at the web root (`http://mafreebox.freebox.fr/api_version`), **not** under `/api/`. It is the one call you make before you know the API version. Real capture (`recon/capture/api_version.json`):

```json
{
  "box_model_name": "Freebox v9 (r1)",
  "api_base_url": "/api/",
  "https_port": 29491,
  "device_name": "Freebox Server",
  "https_available": true,
  "box_model": "fbxgw9-r1",
  "api_domain": "fake-1.fbxos.fr",
  "uid": "scrubbed-uid-1",
  "api_version": "16.0",
  "device_type": "FreeboxServer9,1"
}
```

Field notes:
- `api_version` `"16.0"` — take the **major** (`16`) to build the versioned prefix.
- `api_base_url` `"/api/"` — prefix for all versioned calls.
- **Base URL formula:** `{scheme}://{host}{api_base_url}v{major}/` → e.g. `http://mafreebox.freebox.fr/api/v16/`. Do not hardcode `v16`; derive it from `api_version` so the client tracks firmware upgrades.
- `device_type` `"FreeboxServer9,1"` / `box_model` `"fbxgw9-r1"` / `box_model_name` `"Freebox v9 (r1)"` — hardware identity (Freebox Ultra). Note the public SDK's `FreeboxServer1,2` is the 2013 Revolution; this is a different, undocumented generation.
- `api_domain` `"fake-1.fbxos.fr"` (a scrub placeholder) + `https_port` `29491` + `https_available` `true` — how to reach the box from **outside** the LAN over TLS (see TLS below).
- `uid` `"scrubbed-uid-1"` (scrub placeholder) — stable per-box identifier.

### `/api/latest/` alias **[undocumented upstream]**

The Freebox OS web UI issues all its calls against `/api/latest/…` rather than `/api/v16/…`. `latest` is an undocumented server-side alias that always resolves to the current major, so `/api/latest/system/` and `/api/v16/system/` return identical results. The captured WebSocket connects to `ws://mafreebox.freebox.fr/api/latest/ws/event/` (see `ws_frames.txt`), and captured `logo_url` fields are returned as `/api/latest/…` paths. Useful as a fallback, but for reproducible clients prefer the explicit `v{major}` computed from `/api_version` — `latest` silently shifts across firmware upgrades and is not in any published spec.

### Discovery via mDNS (recommended)

Rather than assuming `mafreebox.freebox.fr`, discover the box on the LAN via mDNS/Bonjour service type `_fbx-api._tcp`. The TXT record advertises the same fields as `/api_version` (api_version, api_domain, https_port, uid, device type), letting a client find the box, choose HTTP-vs-HTTPS, and compute the base URL without hardcoding a hostname. This is the robust path for `fbx` on networks where the default name doesn't resolve. (Recommendation; not part of the HTTP captures.)

### Authentication — challenge/response session flow

Standard Freebox app-token + HMAC-SHA1 challenge/response. The on-box docs list exactly five endpoints under **Login (5)** (`doc_inventory.txt`), versioned `v8` there but reachable under the computed `v16` prefix:

- **`POST /login/authorize/`** — one-time app registration. Body: `app_id`, `app_name`, `app_version`, `device_name`. Returns an `app_token` (store it forever) and a `track_id`. The box physically prompts the user to grant access on its LCD. *(Documented; not exercised in this session's captures.)*
- **`GET /login/authorize/{track_id}`** — poll registration status: `pending` → `granted` (or `denied`/`timeout`). Only needed once, at first pairing. *(Documented; not captured.)*
- **`GET /login/`** — session status + fresh `challenge`. Captured shape:
  ```json
  { "logged_in": true, "challenge": [ "…" ] }
  ```
  In the raw capture the `challenge` came back as an **array of obfuscated JS-expression strings** (self-decoding `eval(unescape(...))` fragments), not a plain string — treat it opaquely; the concatenated/evaluated result is the challenge to sign.
- **`POST /login/session/`** — open a session. Body: `app_id` and `password = HMAC-SHA1(app_token, challenge)`. Returns a `session_token` and the permissions map (below). *(Documented; not captured beyond `/login/perms/`.)*
- **`POST /login/logout/`** — close the session. *(Documented; not captured.)*

Per-request auth: send the session token in the **`X-Fbx-App-Auth`** header on every subsequent call. Session tokens expire; on an auth failure (Freebox returns HTTP 403 with an `auth_required`/`invalid_session`-class `error_code`), re-fetch `GET /login/` for a new challenge and re-open a session with the stored `app_token`. The `app_token` itself never changes — only the short-lived session token is refreshed. *(The exact 403 auth error was not captured this session; error-code strings like `notsupp`, `invalid_request`, `noent`, `service_down`, `internal_error` were.)*

### `GET /login/perms/` — session permissions map

The set of scopes granted to the app token; drives which domains a client may call. Captured (all `granted: true` on this box, French `desc` strings from the box):

```json
{
  "parental": {"granted": true, "desc": "Accès au contrôle parental"},
  "explorer": {"granted": true, "desc": "Accès aux fichiers de la Freebox"},
  "settings": {"granted": true, "desc": "Modification des réglages de la Freebox "},
  "home":     {"granted": true, "desc": "Gestion de l’alarme et maison connectée"},
  "vm":       {"granted": true, "desc": "Contrôle de la VM"},
  "downloader":{"granted": true,"desc": "Accès au gestionnaire de téléchargements"}
}
```

Full observed key set (14): `parental`, `tv`, `explorer`, `contacts`, `wdo` (device provisioning — "Provisionnement des équipements"), `camera`, `profile`, `player`, `settings`, `calls`, `home`, `pvr`, `vm`, `downloader`. Note `vm` (VM control) and `home` are present here but absent from the frozen public SDK — this box grants scopes the upstream docs never defined. A call into a domain whose scope is not `granted` fails with an auth/permission error even with a valid session token.

### TLS: local plain HTTP vs remote HTTPS

- **On the LAN**, the box is reached over plain **HTTP** at `http://mafreebox.freebox.fr/` (or its LAN IP). The captures in this session were taken this way. No certificate involved; the HMAC session still protects the API.
- **Remotely**, use **HTTPS** at `https://{api_domain}:{https_port}/` — from `/api_version`, `https://fake-1.fbxos.fr:29491/` (placeholder domain). The `api_domain` is a per-box name under `fbxos.fr` that resolves to the box's public IP; `https_available` gates whether this is on. (The same `api_domain`/`https_port`/`https_available` triple also appears in `/connection/config/`.)
- The remote certificate is signed by the **Freebox Root CA** (not a public/browser-trusted CA on older stacks). A client validating the remote endpoint should pin/trust the Freebox ECC + Freebox Root CA chain rather than relying on the system trust store. The same `/api_version` → compute-base-URL → login flow applies over HTTPS; only the scheme, host, and port change. (CA/pinning guidance is general platform knowledge, not from these captures.)

**Practical `fbx` bootstrap:** discover via `_fbx-api._tcp` (or fall back to `mafreebox.freebox.fr`) → `GET /api_version` → compute `/api/v{major}/` → one-time `POST /login/authorize/` (persist `app_token`) → per-run `GET /login/` + `POST /login/session/` (HMAC-SHA1) → send `X-Fbx-App-Auth` on all calls → check `/login/perms/` for the scopes your subcommands need.

---

## WebSocket event API (the push vocabulary)

The Freebox exposes exactly one WebSocket endpoint. It is the only push channel on the box; everything else is HTTP polling. The on-box docs (API v16) list it under the section **"WebSocket event API"** as a single entry, `GET /api/v8/ws/event` — note the docs advertise `v8` in the path but the live UI connects via the `/api/latest/` alias. The docs enumerate only the endpoint itself: the concrete event names and the `source`/`event` split documented below come from **captured traffic**, not the on-box reference. The `vm_state_changed` event in particular is **[undocumented upstream (public SDK)]** — the frozen public SDK has no Virtual Machines domain at all.

### `GET /api/latest/ws/event/` (WebSocket upgrade)

Open a WebSocket to receive server-pushed events. Observed connect URL:

```
ws://mafreebox.freebox.fr/api/latest/ws/event/
```

Authentication is the same session as the HTTP API — the `X-Fbx-App-Auth` session token must already be established (via `login/session`); the socket rides the authenticated session.

**Subscribe (client → server).** One `register` frame per event class. The client sent one event name per frame (observed: three separate frames rather than one array of three):

```json
{"action":"register","events":["lan_host_l3addr_reachable"]}
{"action":"register","events":["lan_host_l3addr_unreachable"]}
{"action":"register","events":["vm_state_changed"]}
```

`events` is an array, so multiple names in one frame is plausible, but the captured client registered them one at a time.

**Ack (server → client).** Each `register` is acknowledged with a bare success frame — no echo of which event was registered, so acks are positional / not individually correlatable:

```json
{"success":true,"action":"register"}
```

### Notification frame shape (server → client)

Pushed events arrive as `action:"notification"` frames. The envelope (captured key order: `success`, `result`, `source`, `event`, `action` — order is not significant in JSON):

```json
{
  "success": true,
  "result": { ... },
  "source": "lan",
  "event":  "host_l3addr_reachable",
  "action": "notification"
}
```

- `action` — always `"notification"` for pushed events.
- `success` — `true`.
- `source` — the subsystem namespace (observed: `"lan"`).
- `event` — the event name **without the subsystem prefix** (see the gotcha below).
- `result` — the event payload; its schema depends on the event.

### The `lan_host_` prefix / `source` gotcha (real, verified)

There is an asymmetry between what you **register** and what you **receive**:

| You register (client → server) | You receive (server → client) |
|---|---|
| `"lan_host_l3addr_reachable"` | `"source":"lan"` + `"event":"host_l3addr_reachable"` |
| `"lan_host_l3addr_unreachable"` | `"source":"lan"` + `"event":"host_l3addr_unreachable"` |

The registration name is the **fully-qualified** `lan_host_l3addr_reachable`, but the incoming notification splits that into `source:"lan"` and `event:"host_l3addr_reachable"` — the `lan_` prefix is stripped off `event` and reappears as `source`. A naive client that string-matches the incoming `event` field against the string it registered will never match. Match on `source + "_" + event`, or strip/normalize before comparing.

### Concrete events observed

#### `host_l3addr_reachable` / `host_l3addr_unreachable` (source `lan`)

Fired when a LAN host's L3 (IP) reachability flips. Registered as `lan_host_l3addr_reachable` / `lan_host_l3addr_unreachable`. The `result` is a **full LAN host object** — the same shape returned by `GET /lan/browser/{interface}/{hostid}/` — not a small delta. Trimmed to the informative fields:

```json
{
  "success": true,
  "source": "lan",
  "event": "host_l3addr_reachable",
  "action": "notification",
  "result": {
    "id": "ether-02:00:00:00:00:14",
    "primary_name": "host-37",
    "host_type": "laptop",
    "vendor_name": "Apple, Inc.",
    "active": true,
    "reachable": true,
    "last_activity": 1783944060,
    "last_time_reachable": 1783944060,
    "l2ident": { "id": "02:00:00:00:00:14", "type": "mac_address" },
    "l3connectivities": [
      { "addr": "192.168.1.182", "af": "ipv4", "active": true, "reachable": true,  "last_activity": 1783944059 },
      { "addr": "2001:db8::36",  "af": "ipv6", "active": true, "reachable": false, "last_activity": 1783944060 }
    ],
    "access_point": {
      "connectivity_type": "wifi",
      "wifi_information": { "band": "6g", "ssid": "<ssid>", "bssid": "02:00:00:00:00:10",
                            "standard": "ax", "signal": -79, "phy_rx_rate": 4083, "phy_tx_rate": 8646 }
    }
  }
}
```

Notes for consumers:
- The event distinguishes **host-level** reachability (`result.reachable`) from **per-address** reachability inside `result.l3connectivities[].reachable`. In the captured `..._unreachable` frames the host object still had `"reachable": true` at top level while an individual IPv6 `l3connectivities` entry went `reachable:false` — so the event name reflects an *address* transition, and you must read `l3connectivities` to know *which* address flipped, not the top-level flag.
- Because the whole host object (including `access_point.wifi_information` with live RSSI/PHY rates) is delivered on every reachability flip, this event doubles as a cheap "host came/went on wifi" signal.
- `wifi_information.signal` is dBm RSSI; `phy_rx_rate`/`phy_tx_rate` are Mbps PHY rates.

#### `vm_state_changed` (VM subsystem)

Registered as `vm_state_changed`. Fired when a Virtual Machine changes power state. **[undocumented upstream (public SDK)]** — the public SDK has no Virtual Machines domain at all. **No `vm_state_changed` notification frame was captured this session** (the box's VMs did not change state during the capture window), so only the registration is confirmed from real traffic; the payload shape is not documented here to avoid inventing fields. Expect `source` to be the VM namespace and `result` to carry the VM id and its new `status` (consistent with the `vm/` REST domain), but treat that as unverified until a live frame is captured.

### What this means for `fbx watch` / `fbx top`

- **Presence / arrivals-departures (`fbx watch` for devices): use the WebSocket.** `lan_host_l3addr_reachable` / `_unreachable` are genuine push events and carry the full host object, so a device-presence watcher needs no polling — register both and react to frames. Remember the prefix gotcha when routing frames.
- **Throughput / system stats (`fbx top`): you cannot use the WebSocket.** There is **no** push event for connection throughput, system temps, or CPU/uptime. The Freebox OS web UI itself does **not** stream these — it **polls** `GET /connection/` and `GET /system/` at roughly 1 Hz. Any `fbx top` must do the same: poll `/connection/` (for `rate_down`/`rate_up`/`bytes_down`/`bytes_up`) and `/system/` (sensors) on a ~1 s timer. The WebSocket will not help here.
- **VM state (`fbx watch` for VMs): register `vm_state_changed`,** but be prepared to fall back to polling `GET /vm/` since the notification payload is unverified from this capture.
- **Registration is per-event and additive**; the ack does not tell you which event it acknowledged, so track your own ordering or ignore the acks and just handle notifications.

### Cross-reference: on-box docs vs. capture

- On-box docs (v16) list the endpoint as `GET /api/v8/ws/event` under **"WebSocket event API"** (1 entry). The live path used is `/api/latest/ws/event/`.
- The docs do **not** enumerate the concrete event names or the `source`/`event` split — the three registerable events (`lan_host_l3addr_reachable`, `lan_host_l3addr_unreachable`, `vm_state_changed`) and the prefix-stripping behavior documented above come from **captured traffic**, not from the on-box reference.
- Do not confuse this with the separate **"Notification" (8)** docs section (`/notif/targets`, `/register`, `/send`) — that is the *push-notification-to-mobile-device* subsystem (FCM-style target registration; the captured `GET /notif/targets` returns Iliad `api.scw.iliad.fr/notifications/...` target URLs), unrelated to this in-session WebSocket event stream.

---

## System & connection (status, FTTH/SFP, LTE backup)

The status dashboard is built almost entirely from these read-only endpoints. The Freebox OS web UI **polls `GET /system/` and `GET /connection/` roughly once per second** (not WebSocket-pushed), so a `fbx watch`/`fbx top` should do the same: short-interval GET polling, not a WS subscription. (The captured WebSocket registrations are only `lan_host_l3addr_reachable`, `lan_host_l3addr_unreachable`, and `vm_state_changed` — none of them system/connection telemetry.) Graph curves (throughput, temperature) come from `POST /rrd/`.

Unless noted, all paths are relative to `/api/latest/` (or `/api/v16/`). Every endpoint below returned HTTP `200` (some carry a `success:false` error envelope in the body — see the individual notes).

### `GET /system/`
Rich box identity, hardware model flags, live sensors/fans, and uptime. This is the single most useful status call and the one the UI polls every ~1s.
- `firmware_version` (e.g. `"4.12.2"`), `mac`, `serial`, `board_name` (`"fbxgw9r"`)
- `model_info` — capability flags and naming: `name` (`"fbxgw9-r1"`), `pretty_name` (`"Freebox v9 (r1)"`), `net_operator`, `wifi_type` (`"2d4_5g_5g_6g"`), `wifi_country`, `has_vm`, `has_wop`, `has_lan_sfp`, `has_standby`, `has_eco_wifi`, `has_status_led`, `supported_languages[]`, `default_language`
- `sensors[]` — each `{id, name, value}` in °C: `temp_cpu0..temp_cpu3`, `temp_t1`
- `fans[]` — each `{id, name, value}` in RPM: `fan0_speed`
- `uptime` (localized string) and `uptime_val` (seconds, e.g. `81231`)
- `disk_status` (`"active"`), `user_storage_powered`, `user_main_storage`, `box_authenticated`, `usb3_enable`

```json
{ "mac":"<mac>","board_name":"fbxgw9r","firmware_version":"4.12.2","serial":"<serial>",
  "model_info":{"name":"fbxgw9-r1","pretty_name":"Freebox v9 (r1)","wifi_type":"2d4_5g_5g_6g","has_vm":true,"has_lan_sfp":true},
  "sensors":[{"id":"temp_cpu1","name":"Température CPU 1","value":59}],
  "fans":[{"id":"fan0_speed","name":"Ventilateur 1","value":630}],
  "uptime_val":81231,"disk_status":"active" }
```

### `GET /connection/`
Current WAN state and live throughput counters. Polled ~1s alongside `/system/`. Note both `/connection` and `/connection/` (trailing slash) return the same shape.
- `state` (`"up"`), `media` (`"ftth"`), `type` (`"ethernet"`)
- `rate_down` / `rate_up` — **instantaneous bytes/sec** (e.g. `176626` / `543876`)
- `bandwidth_down` / `bandwidth_up` — negotiated link capacity in bits/sec (`8000000000` = 8 Gbit/s on this Ultra)
- `bytes_down` / `bytes_up` — cumulative counters
- `ipv4`, `ipv6`, `ipv4_port_range` (`[16384, 32767]`)

### `GET /connection/full/` **[undocumented upstream]**
Superset of `/connection/` with the `ftth` and `xdsl` sub-objects inlined — one call to render the whole connection panel. Not present in the public SDK (nor in the on-box v16 endpoint list).
- All fields from `/connection/`, plus:
- `ftth{}` — same fields as `GET /connection/ftth/` below
- `xdsl{}` — here just `{"status":"disabled"}` (fiber box)

### `GET /connection/config/`
WAN/remote-access configuration (the "Mode réseau"/remote-access panel).
- `remote_access` (bool), `api_remote_access`, `remote_access_ip`, `remote_access_port`, `remote_access_min_port`/`remote_access_max_port`, `api_domain` (`"<id>.fbxos.fr"`)
- `https_available`, `https_port`, `is_secure_pass`, `allow_token_request`
- `adblock`, `adblock_not_set`, `wol`, `ping`, `sip_alg` (`"direct_media"`), `disable_guest`
- Docs list a `PUT /connection/config/` counterpart (not captured).

### `GET /connection/ipv6/config/`
IPv6 enablement plus delegated prefixes handed to the LAN.
- `ipv6_enabled` (bool), `ipv6ll` (link-local), `ipv6_firewall`, `ipv6_prefix_firewall`
- `delegations[]` — each `{prefix:"2001:db8::x/64", next_hop:""}` (8 delegated /64s observed)
- Docs list a `PUT /connection/ipv6/config/` counterpart (not captured).

### `GET /connection/ftth/` **[undocumented upstream]**
FTTH/SFP optical-module status. Key for a fiber health readout. Absent from the public SDK (present in the on-box v16 docs).
- `link` (bool, optical link up), `link_type` (`"pon"`), `has_sfp`, `sfp_present`, `sfp_alim_ok`
- `sfp_model` (`"LTF7219-BC+1"`), `sfp_vendor` (`"Hisense"`), `sfp_serial`
- `sfp_pwr_rx` / `sfp_pwr_tx` — optical power. Observed `-1838` / `642`; these are **hundredths of a dBm** (i.e. RX ≈ −18.38 dBm, TX ≈ +6.42 dBm)
- `sfp_has_power_report`, `sfp_has_signal`

```json
{ "link":true,"link_type":"pon","has_sfp":true,"sfp_present":true,
  "sfp_model":"LTF7219-BC+1","sfp_vendor":"Hisense","sfp_serial":"<serial>",
  "sfp_pwr_rx":-1838,"sfp_pwr_tx":642,"sfp_alim_ok":true }
```

### `GET /connection/xdsl/`
xDSL line status. On this FTTH box the service is not running:
- Returns a Freebox API error envelope (still HTTP `200`): `{"success":false,"error_code":"service_down","msg":"…Ce service n'est pas disponible actuellement"}`. Callers must check `success`, not the HTTP status.

### `GET /connection/aggregation`
Link-aggregation (4G/xDSL bonding) status.
- No 4G module present here → error envelope (HTTP `200`): `{"success":false,"error_code":"noent","msg":"Aucun module 4G détecté"}`
- Docs list a `PUT /connection/aggregation` counterpart (not captured).

### `GET /connection/lte/backup` **[undocumented upstream, Ultra 4G/5G backup]**
Cellular WAN-backup state (the Ultra's internal LTE modem). Not in the public SDK, and not in the on-box v16 endpoint list either (the docs list only the per-modem `GET /connection/lte/{id}`). Returned `200` even with no SIM.
- `enabled` (bool), top-level `state` (`"not_detected"`), `fsm_state` (`"wait_neighboor"`), `antenna` (`"internal"`), `has_external_antennas`
- `sim{}` — `present` (false here), `pin_locked`, `puk_locked`, `pin_remaining`, `puk_remaining`, `imsi`, `iccid`
- `network{}` — `pdn_up`, `has_ipv4`/`has_ipv6`, `ipv4`/`ipv6` and netmasks/DNS (all empty/zero with no SIM)
- `radio{}` — `associated`, `ue_active`, `attach_status`, `plmn`, `signal_level`, and `bands[]` each with `{band, bandwidth, rsrp, rsrq, rssi, pci, enabled}`

### `GET /connection/logs/`
WAN link/connection up-down event history (small array of `{type, state, date, …}`; `type:"link"` carries `bw_up`/`bw_down`/`link`, `type:"conn"` carries `conn`). Not requested in the task but captured alongside; useful for an outage timeline.

### `POST /rrd/`
The graph data source for all time-series curves (throughput, temperatures, switch rates). This is a **POST with a JSON body** selecting the database and fields — not a GET.
- Request body: `{"db":"<name>","precision":<step_sec>,"date_start":<epoch>,"date_end":<epoch>,"fields":[…]}`
  - Observed `db:"temp"` with `fields:["fan0_speed","temp_cpu0..3","temp_t1"]`. Other DBs (`net`, `switch`, …) exist per the docs but were not captured.
- Response: `{date_start, date_end, data:[ {time:<epoch>, <field>:<value>, …}, … ]}`, one sample per `precision` interval.
- **Value scaling:** temps/fan in the RRD are ×10 vs the live `/system/` sensors (RRD `temp_cpu0:590`, `fan0_speed:6630` correspond to 59 °C and 663 RPM). Scale accordingly when plotting.

```json
// request
{"db":"temp","precision":10,"date_start":1783941720,"date_end":1783941950,
 "fields":["fan0_speed","temp_cpu0","temp_cpu1","temp_cpu2","temp_cpu3","temp_t1"]}
// response
{"date_start":1783941600,"date_end":1783941942,
 "data":[{"time":1783941600,"temp_cpu0":590,"temp_cpu1":598,"fan0_speed":6630,"temp_t1":602}]}
```

### `GET /rrd/`
The GET form exists but requires DB selection; called bare it returns an error envelope (HTTP `200`): `{"success":false,"msg":"invalid_db"}`. Use `POST /rrd/` with a body instead.

### Related: `GET /sfp/status` (LAN SFP, distinct from WAN FTTH SFP)
Status of the **LAN-side** SFP cage (`has_lan_sfp` in `/system/`), separate from the WAN optical module in `/connection/ftth/`. Empty cage here.
- `{"type":"p2p_1g","present":false,"link":false,"supported":false,"power_good":true,"eeprom_valid":false}`
- Docs (SFP section) also list `PUT /sfp/config` (not captured).

### Notes / gaps vs. docs
- **Documented on-box (API v16) but not captured:** `PUT /connection/config/`, `PUT /connection/ipv6/config/`, `PUT /connection/aggregation`, `GET /connection/lte/{id}`, the DDNS endpoints (`GET /connection/ddns/{provider}/status/`, `GET/PUT /connection/ddns/{provider}/`), `POST /system/reboot/`, `POST /system/shutdown/`, `PUT /sfp/config`.
- **Public-SDK gap:** the public SDK (frozen at API 4.0) has no `/connection/full/`, no LTE backup, and no SFP section — the endpoints marked `[undocumented upstream]` are real v16 endpoints absent from dev.freebox.fr.

---

## LAN, network devices & DHCP

The LAN device browser is the richest read-only surface on the box and the natural backbone for `fbx devices` / `fbx net`. Most fields here are **[undocumented upstream (public SDK)]** — the frozen 4.0 SDK documents `lan/config`, `lan/browser`, `dhcp`, `dhcpv6`, `freeplug` and `lan/wol`, but at a far shallower schema than API v16 actually returns (no `access_point`, `network_control`, `model`, `l2ident`, `last_time_reachable`, etc.). The on-box docs (v16, `doc_inventory`) do list these paths; treat the field lists below — captured off firmware 4.12.2 / API 16.0 — as the real contract.

All examples use scrubbed placeholder values (`02:00:00:00:00:0x` MACs, `192.168.1.x` / `2001:db8::x` addresses, `host-N` / `person-N` names).

### `GET /lan/config/`
The Freebox's own LAN identity and router/bridge mode.
```json
{
  "name_dns": "freebox-server",
  "name": "Freebox Server",
  "name_mdns": "Freebox-Server",
  "mode": "router",
  "name_netbios": "host-3",
  "ip": "192.168.1.254"
}
```
- `mode`: `"router"` here; docs describe a bridge mode too. In bridge mode the DHCP server and device browser go dark, which matters for any CLI that assumes a populated device list.
- `PUT /lan/config/` exists in docs (not captured) to change name/mode.

### `GET /lan/browser/interfaces/`
Lists the L2 interfaces the browser scans, with a live host count.
```json
[
  { "name": "pub", "host_count": 127 },
  { "name": "wifiguest", "host_count": 0 }
]
```
- `pub` is the main LAN; `wifiguest` is the guest Wi-Fi segment. Use the `name` value as the `{interface}` path segment for the browser and WoL endpoints.

### `GET /lan/browser/pub/`
The device list — the single most important endpoint in this section. Returns an array of host objects. This is what the UI's "Réseau / Appareils connectés" view renders. (Docs generalize this as `GET /lan/browser/{interface}/`; `pub` is the concrete interface captured. Per-host `GET`/`PUT /lan/browser/{interface}/{hostid}/` also exist in docs but weren't captured — `PUT` is how you rename a device or set its type.)

Full host object key set observed (union across hosts; some keys — e.g. `network_control`, `model` — are absent on some hosts): `l2ident`, `active`, `persistent`, `names`, `vendor_name`, `host_type`, `domain_name`, `info`, `l3connectivities`, `id`, `last_time_reachable`, `primary_name_manual`, `network_control`, `interface`, `default_name`, `first_activity`, `reachable`, `last_activity`, `primary_name`, `access_point`, `model`.

Abbreviated real example (host `02:00:00:00:00:0a`, exactly as captured):
```json
{
  "l2ident": { "id": "02:00:00:00:00:0a", "type": "mac_address" },
  "active": true,
  "persistent": true,
  "names": [ { "name": "host-20", "source": "dhcp" } ],
  "vendor_name": "SAMJIN Co., Ltd.",
  "host_type": "other",
  "domain_name": "host-21",
  "info": { "dhcp": { "Host Name": "host-20" } },
  "id": "ether-02:00:00:00:00:0a",
  "interface": "pub",
  "default_name": "host-20",
  "primary_name": "host-22",
  "primary_name_manual": true,
  "first_activity": 1719762509,
  "last_activity": 1783941970,
  "last_time_reachable": 1783941970,
  "reachable": true,
  "l3connectivities": [
    { "addr": "192.168.1.75", "af": "ipv4", "active": true, "reachable": true,
      "last_activity": 1783941970, "last_time_reachable": 1783941970 }
  ],
  "model": "fbx8am",
  "access_point": { "connectivity_type": "wifi", "…": "…" }
}
```
(This host has no `network_control` key; other hosts do — see below.)

Field-by-field:
- **`id`** — stable device key of the form `"ether-<mac>"` (e.g. `ether-02:00:00:00:00:0a`). This is the `{hostid}` for per-host GET/PUT. Prefer it over raw MAC.
- **`l2ident`** — `{ "id": "<mac>", "type": "mac_address" }`. `type` is `mac_address` for everything observed.
- **`active`** — device currently seen on the link. **`reachable`** — responds to L3 probing. These can differ.
- **`persistent`** — box remembers this host across reboots / when offline (statically leased or manually kept devices are persistent).
- **`names[]`** — `{ name, source }` pairs; `source` values observed: `dhcp`, `mdns`, `mdns_srv`, `netbios`, `upnp` (multiple names per host common). **`primary_name`** is the resolved display name, **`default_name`** the fallback, **`primary_name_manual`** true if the user renamed it via PUT.
- **`vendor_name`** — OUI vendor lookup from the MAC (e.g. `"Apple, Inc."`, `"SAMJIN Co., Ltd."`, `"Microsoft Corporation"`); empty string when unknown.
- **`host_type`** — device class (`workstation`, `laptop`, `smartphone`, `television`, `other`, …; full enum via `/lan/browser/types/`).
- **`domain_name`** — the box-assigned local domain label.
- **`model`** — internal Freebox device model tag for Freebox-family gear. Values observed: `"fbx8am"`, `"fbxwmr"`; absent (`null`/missing) on third-party devices.
- **`first_activity` / `last_activity` / `last_time_reachable`** — Unix epoch seconds.
- **`info`** — free-form maps keyed by discovery protocol. Observed sub-keys: `dhcp` (e.g. `{"Host Name": "...", "Vendor Class Identifier": "udhcp 1.29.3"}`), `mdns` (e.g. `{"Service: spotify-connect": "192.168.1.6:81 (tcp)"}`), `upnp` (`friendlyName`, `modelName`, `manufacturer`, …). Contents are device-dependent strings — treat as opaque display data, not a stable schema.
- **`network_control`** — present on some hosts (absent on others). Parental-control binding: `{ "current_mode": "allowed", "profile_id": 1, "name": "person-7" }`. Only `current_mode: "allowed"` was observed in this capture; docs define additional modes (blocked/controlled) that a CLI should tolerate. `profile_id`/`name` link to a Parental Control profile.

**`l3connectivities[]`** — per-address reachability, one entry per IPv4/IPv6 address:
```json
{
  "addr": "192.168.1.141",
  "af": "ipv4",
  "active": false,
  "reachable": false,
  "last_activity": 1733072354,
  "last_time_reachable": 1733072354
}
```
- `af` ∈ `ipv4` / `ipv6`. A host typically has one IPv4 plus several IPv6 (link-local `fe80::*` and global `2001:db8::*`). Pick the `ipv4` entry (or the reachable global IPv6) for a "current IP" display.

**`access_point`** — how the device attaches to the network. `connectivity_type` is `ethernet` or `wifi`, with a matching sub-object. Common top-level fields observed: `mac` (AP MAC), `type` (e.g. `"gateway"`), `uid`, and `rx_bytes`/`tx_bytes`/`rx_rate`/`tx_rate` counters.

Wi-Fi client (`connectivity_type: "wifi"`), captured verbatim:
```json
{
  "connectivity_type": "wifi",
  "type": "gateway",
  "mac": "02:00:00:00:00:04",
  "uid": "scrubbed-uid-1",
  "rx_bytes": 856235, "tx_bytes": 589615, "rx_rate": 0, "tx_rate": 0,
  "wifi_information": {
    "band": "2d4g",
    "ssid": "scrubbed-ssid-1",
    "bssid": "02:00:00:00:00:0b",
    "standard": "n",
    "signal": -34,
    "phy_rx_rate": 722,
    "phy_tx_rate": 722,
    "sess_duration": 81267
  }
}
```
- `band` (`2d4g` and `6g` observed; `standard` seen as `n` and `ax`), `signal` in dBm, `phy_rx_rate`/`phy_tx_rate` in Mbit/s, `sess_duration` seconds. This is the data `fbx wifi`/`fbx devices --wifi` would surface.

Ethernet client (`connectivity_type: "ethernet"`):
```json
{
  "connectivity_type": "ethernet",
  "mac": "02:00:00:00:00:04",
  "type": "gateway",
  "uid": "scrubbed-uid-1",
  "ethernet_information": { "speed": 1000, "duplex": "full", "max_port_speed": 1000, "link": "up" }
}
```

### `GET /lan/browser/types/`
Reference list mapping `host_type` values to display names, categories, and icon paths. Static-ish; fetch once and cache.
```json
[
  { "type": "workstation", "name": "Ordinateur",  "category": "personal_device", "icon": "/resources/images/lan/ic_device_computer.png" },
  { "type": "laptop",      "name": "Laptop",       "category": "personal_device", "icon": "/resources/images/lan/ic_device_laptop.png" },
  { "type": "smartphone",  "name": "Smartphone",   "category": "personal_device", "icon": "/resources/images/lan/ic_device_phone.png" },
  { "type": "television",  "name": "Télévision",   "category": "multimedia",      "icon": "/resources/images/lan/ic_device_television.png" }
]
```
- Full `type` enum observed (19 entries): `workstation`, `laptop`, `smartphone`, `tablet`, `printer`, `vg_console`, `television`, `nas`, `ip_camera`, `networking_device`, `multimedia_device`, `ip_phone`, `other`, `car`, `watch`, `light`, `outlet`, `appliances`, `thermostat`.
- `category` values observed: `personal_device`, `multimedia`, `network`, `home`, `other`. `name` is localized (French here, per the box `lang=fra`).

### `GET /lan/routes`
Purpose per docs: list static LAN routes. **[UNSTABLE / effectively empty]** — capture returned only an envelope with **no `result` key**:
```json
{ "success": true }
```
No routes were configured on this box, so the shape of a populated result is unknown from captures. `PUT /lan/routes/` exists in docs to manage them. A CLI should treat a missing `result` as "no routes," not an error.

### `GET /dhcp/config/`
DHCP server configuration.
```json
{
  "enabled": true,
  "sticky_assign": true,
  "netmask": "255.255.255.0",
  "ip_range_start": "192.168.1.2",
  "ip_range_end": "192.168.1.200",
  "gateway": "192.168.1.254",
  "dns": ["192.168.1.24", "", "", "", "", ""],
  "always_broadcast": false,
  "boot_server": "", "boot_file": "",
  "ignore_out_of_range_hint": false,
  "options": {}
}
```
- `sticky_assign`: reuse the same IP for a returning MAC. `dns[]` is a fixed-length array of 6 slots (empty strings for unused). `PUT /dhcp/config/` (docs) writes these.

### `GET /dhcp/static_lease/`
Configured static (reserved) leases — array. Each entry carries the reservation plus a full embedded `host` object (same schema as the browser).
```json
{
  "id": "02:00:00:00:00:01",
  "mac": "02:00:00:00:00:01",
  "hostname": "host-7",
  "ip": "192.168.1.24",
  "comment": "",
  "options": {},
  "host": { "l2ident": {…}, "active": false, "persistent": true, "host_type": "workstation",
            "l3connectivities": [ { "addr": "192.168.1.24", "af": "ipv4", … } ], … }
}
```
- `id` == the MAC (used as `{id}` for `GET/PUT /dhcp/static_lease/{id}`, `DELETE`, and `POST /dhcp/static_lease/` to create). Top-level `ip`/`hostname`/`comment` describe the reservation; `comment` is a user note. `host` embeds the last-known device object.

### `GET /dhcp/dynamic_lease/`
Currently active DHCP leases — array. Top-level lease fields (each also embeds a full `host` object):
```json
{
  "mac": "02:00:00:00:00:05",
  "ip": "192.168.1.6",
  "hostname": "host-10",
  "assign_time": 1783897654,
  "refresh_time": 1783940855,
  "lease_remaining": 40408,
  "is_static": false
}
```
- `ip`, `mac`, `hostname` are the quick-glance fields. `assign_time`/`refresh_time` are epoch seconds; `lease_remaining` is seconds until expiry. Both `is_static:false` and `is_static:true` appear in this capture — a static reservation shows here as `is_static:true` once its device is active. This is the endpoint for `fbx dhcp leases`.

### `GET /dhcpv6/config/`
IPv6 DHCP config. On this box it was disabled, so the response is minimal:
```json
{ "enabled": false, "use_custom_dns": false, "dns": {} }
```
- When enabled, expect `dns` to populate. `PUT /dhcpv6/config/` (docs) writes it. Note `dns` here is an object/map, unlike the fixed 6-slot array in v4 DHCP config.

### `POST /lan/wol/{interface}/` — Wake-on-LAN **[not captured]**
Documented (doc inventory line 56, `POST /api/v8/lan/wol/{interface}/`) but not exercised in this session. Per the API it sends a magic packet to wake a host; body carries the target `mac` (and optionally a `password`). `{interface}` is a browser interface name such as `pub`. Flagged here for completeness so `fbx wol <mac>` implementers know where it lives.

### `GET /freeplug/`
Powerline (CPL) adapter topology. **[UNSTABLE / empty on this hardware]** — the Freebox Ultra has no Freeplug/CPL network, and the capture returned only:
```json
{ "success": true }
```
No `result` was present. On a box with Freeplugs, docs list per-network/adapter groupings, with per-adapter detail at `GET /freeplug/{id}/` and `POST /freeplug/{id}/reset/` (neither captured). A CLI should render "no Freeplug network" when `result` is absent rather than treating the bare `{"success":true}` as an error.

---

**Notes for `fbx` implementers:**
- The web UI reaches all of these via the `/api/latest/` alias (e.g. `/api/latest/lan/browser/pub/`); `/api/v16/…` is equivalent.
- **LAN reachability IS pushed over WebSocket.** The UI polls the *full* `GET /lan/browser/pub/` list on an interval, but individual host reachability transitions arrive as WS push events. The client registers `lan_host_l3addr_reachable` and `lan_host_l3addr_unreachable` (`{"action":"register","events":[…]}`), and the box replies with `action:"notification"` frames carrying `source:"lan"`, `event:"host_l3addr_reachable"`/`"host_l3addr_unreachable"` and a **full host object** in `result` (same schema as the browser, `access_point`/`l3connectivities` included). So `fbx devices --watch` can subscribe to these events for live up/down instead of only polling; use a periodic full `GET` to reconcile the complete list.
- Two endpoints in this section returned a bare `{"success":true}` envelope with **no `result`** (`/lan/routes`, `/freeplug/`), and `dhcpv6/config` was minimal — all reflecting unconfigured/unsupported features on this specific box rather than a stable empty-result schema. Don't hardcode these shapes.

---

## Wi-Fi (Wi-Fi 7 / WPA3 era)

The Freebox Ultra (fbxgw9-r1) exposes a Wi-Fi 7 (802.11be) radio stack with **four PHYs**: 2.4 GHz, two 5 GHz radios, and a **6 GHz** radio — plus **WPA3** and **GCMP-256** encryption fields. None of this exists in the public SDK (frozen at API 4.0 / Revolution): there is no 6 GHz band value, no WPA3, no EHT/MLO, and no `custom_keys` guest-Wi-Fi surface upstream. Treat the whole domain as **[undocumented upstream (public SDK)]**; the on-box v16 docs are the reference. The base `/wifi/*` paths are served at `v9`, with newer additions at `v10` (`state`), `v13` (`temp_disable`), `v14` (`custom_keys/config`, `bss/{id}/mlo/*`), and `v16` (`steering`).

All 14 GET endpoints below were **captured** (status 200). PUT/POST/DELETE mutators and the per-`{id}` sub-resources are **inventory-only** (documented, not captured) and are listed at the end.

### `GET /wifi/config/`
Global Wi-Fi service state.
```json
{ "enabled": true, "power_saving": false, "mac_filter_state": "disabled" }
```
- `mac_filter_state`: `disabled` | (whitelist/blacklist when active).

### `GET /wifi/state/`
Radio detection map — enumerates the PHYs and which band each is on. This is where the 6 GHz radio shows up. Served at v10.
```json
{
 "state": "enabled",
 "power_saving_capability": "supported",
 "expected_phys": [
  { "band": "2d4g", "phy_id": 0,  "detected": true },
  { "band": "5g",   "phy_id": 1,  "detected": true },
  { "band": "5g",   "phy_id": 10, "detected": true },
  { "band": "6g",   "phy_id": 11, "detected": true }
 ]
}
```
- Band values: `2d4g`, `5g`, `6g`. Two independent `5g` PHYs (ids 1 and 10).

### `GET /wifi/ap/`
Access points — **one entry per radio/PHY** (4 total on the Ultra). Each carries a large `capabilities` block plus `config` and `status`.

Observed APs (`config.band` / `channel_width` / `dfs_enabled`):
- id `0` — `2d4g`, width `20`, dfs `false`
- id `1` — `5g`, width `80`, dfs `false`
- id `10` — `5g`, width `160`, dfs `true`
- id `11` — `6g`, width **`320`**, dfs `true`  ← 320 MHz = Wi-Fi 7

`config` keys: `enabled`, `ht`, `eht`, `he`, `primary_channel`, `secondary_channel`, `channel_width`, `band`, `dfs_enabled`. Note the distinct **`eht`** (Wi-Fi 7) and **`he`** (Wi-Fi 6) config sub-objects, e.g. for the 6 GHz AP:
```json
"eht": { "enabled": true, "su_beamformer": true, "su_beamformee": true, "mu_beamformer": true },
"he":  { "enabled": true, "su_beamformee": true, "twt_responder": true, "su_beamformer": true, "twt_required": false, "mu_beamformer": true }
```
`status` (runtime, from the 6 GHz AP):
```json
{ "state": "active", "primary_channel": 85, "secondary_channel": 0,
  "channel_width": "320", "dfs_disabled": false, "dfs_cac_remaining_time": 0 }
```
- Each AP's `capabilities` block enumerates **four bands** — `6g`, `5g`, `2d4g`, and an empty `60g` — and the feature flags are **per-radio**. On the 2.4/5 GHz radios (ap `0`, `1`) the `6g` sub-block reads `eht_supported: false`; on the high-5 GHz and 6 GHz radios (ap `10`, `11`) the `6g` sub-block reads `eht_supported: true` with `eht_320: true`. The `5g` sub-block reports `eht_supported: true`, `he_supported: true`, `he_160: true`, `vht_160: true` throughout. Capabilities are verbose (60+ boolean flags per band) — filter to the `*_supported`, `eht_320`, `he_160`, `vht_160` flags for anything useful.

### `GET /wifi/bss/`
SSID / BSS configuration — the security-relevant endpoint. One entry per broadcast BSS, each with the effective `config` plus `bss_params` / `shared_bss_params` variants and a `status`.
```json
{
 "status": { "state": "active", "band": "6G", "sta_count": 3,
             "authorized_sta_count": 3, "is_main_bss": false,
             "custom_key_ssid": "scrubbed-ssid-2", "partners": [] },
 "config": {
   "enabled": true,
   "ssid": "scrubbed-ssid-1",
   "encryption": "wpa3_psk_ccmp",
   "key": "SCRUBBED_KEY",
   "hide_ssid": false,
   "eapol_version": 2,
   "gcmp256": false,
   "wps_enabled": true,
   "wps_uuid": "8cdf46ed-...-020000000016",
   "use_default_config": true
 },
 "id": "02:00:00:00:00:10", "phy_id": 11,
 "use_shared_params": true, "disable_wep": true
}
```
- `encryption` observed values: **`wpa3_psk_ccmp`** (6 GHz BSS) and `wpa2_psk_ccmp` (5 GHz). `gcmp256` is a boolean toggle (false here, but the field exists — GCMP-256 cipher, not in public SDK).
- `key` is the PSK (scrubbed). `hide_ssid`, `eapol_version` (2), `wps_enabled`/`wps_uuid` per BSS.
- `status.band` uses upper-case (`6G`/`5G`) here vs lower-case (`6g`/`5g`) in `/wifi/state/` and `/wifi/ap/` — inconsistent casing, worth normalizing in the CLI. **[UNSTABLE upstream]**
- `status.custom_key_ssid` links the BSS to the guest-Wi-Fi SSID (see `custom_keys` below). `partners` is for MLO/multi-link pairing.

### `GET /wifi/steering/config/`
Band steering level (served at v16).
```json
{ "steering_level": 1 }
```

### `GET /wifi/planning/`
Scheduled on/off planning (time-based Wi-Fi disable).
```json
{ "use_planning": false, "resolution": 48, "mapping": ["on","on", ...] }
```
- `resolution` 48 = half-hour slots/day; `mapping` is the on/off grid.

### `GET /wifi/mac_filter/`
MAC access-control list. Empty here → capture shows a bare `{ "success": true }` (no populated result list).
```json
{ "success": true }
```

### `GET /wifi/wps/config/`
WPS enable state.
```json
{ "enabled": true }
```

### `GET /wifi/wps/sessions/`
Active WPS pairing sessions. None active → bare success.
```json
{ "success": true }
```

### `GET /wifi/custom_keys/config/`
Guest Wi-Fi ("custom key") SSID configuration (v14).
```json
{ "ssid": "scrubbed-ssid-2", "ssid_read_only": false,
  "hide_ssid": false, "encryption": "wpa2_psk_ccmp" }
```
- This `ssid` is the `custom_key_ssid` referenced from `/wifi/bss/`.

### `GET /wifi/custom_key/`
Guest-Wi-Fi temporary access keys (list). None present → bare success.
```json
{ "success": true }
```

### `GET /wifi/diag`
Wi-Fi health diagnostics — arrays of issues per AP/BSS.
```json
{ "aps": [],
  "bsss": [ { "severity": "minor", "bssid": "02:00:00:00:00:06", "code": "network_security" }, ... ] }
```
- `code: "network_security"` (minor) flagged on the WPA2 BSSs — the box nudges toward WPA3.

### `GET /wifi/default`
Factory-default AP/BSS parameters (used to reset). Mirrors `/wifi/ap/` config shape with `aps[].params` (incl. `band`, `channel_width` `"320"` for 6g, `eht`/`he` blocks) and `ap_id`.

### `GET /wifi/temp_disable`
Temporary Wi-Fi disable countdown (v13).
```json
{ "remaining": 0 }
```
- `remaining` in seconds; 0 = not temporarily disabled.

### Inventory-only (documented v16, not captured)
Mutators and sub-resources present in the on-box docs but not exercised in this capture:
- **Config mutators:** `PUT /wifi/config/`, `POST /wifi/config/reset/`, `PUT /wifi/steering/config/`, `PUT /wifi/planning/`, `PUT /wifi/wps/config/`, `PUT /wifi/custom_keys/config/`.
- **Per-AP:** `GET/PUT /wifi/ap/{id}`, `GET /wifi/ap/{id}/allowed_channel_comb`, `.../stations/` + `.../stations/{mac}` (associated clients), `.../channel_survey_history/{timestamp}`, `.../neighbors/` + `POST .../neighbors/scan`, `.../channel_usage/`, `POST .../restart`, `GET /wifi/ap/{id}/default`.
- **Per-BSS:** `GET/PUT /wifi/bss/{id}`, `GET /wifi/bss/{id}/default`, and the **Wi-Fi 7 MLO** endpoints `GET /wifi/bss/{id}/mlo/allowed_comb` + `GET /wifi/bss/{id}/mlo/config` (v14) — multi-link operation, wholly absent upstream. (Only GET forms are documented; no MLO PUT appears in the v16 inventory.)
- **MAC filter:** `GET/PUT/DELETE /wifi/mac_filter/{filter_id}`, `POST /wifi/mac_filter/`.
- **WPS:** `POST /wifi/wps/start/`, `DELETE /wifi/wps/sessions/`.
- **Guest keys:** `GET/DELETE /wifi/custom_key/{key_id}`, `POST /wifi/custom_key/`.
- **Diag:** `POST /wifi/diag`, `GET/POST /wifi/ap/{id}/diag`, `GET/POST /wifi/bss/{id}/diag`.
- **Temp disable:** `POST /wifi/temp_disable`.

---

## Port forwarding, DMZ, firewall & UPnP IGD

This domain corresponds to the public SDK's "Port Forwarding" / "Incoming Ports" / "UPnP IGD" areas (long-standing features, not among the domains the frozen SDK omits). All bodies below are from the real capture (API 16.0, path prefix `/api/latest/`). Every response is wrapped in the standard `{"success":true,"result":…}` envelope.

### `GET /fw/redir/`
Static (user-defined) port-forwarding rules. **On this box the result was empty**, so the response was literally `{"success":true}` with **no `result` field at all** (not `result: []`) — clients must treat a missing `result` as "zero rules".

```json
{ "success": true }
```

Because no rules were configured, the per-rule field schema was **not observed** in this capture and is not reproduced here (the sources contain no rule body to ground it). Full CRUD exists in the on-box docs (API v16): `GET /fw/redir/`, `POST /fw/redir/`, `GET /fw/redir/{redir_id}`, `PUT /fw/redir/{redir_id}`, `DELETE /fw/redir/{redir_id}`.

### `GET /fw/dmz/`
DMZ target host. Disabled here.

```json
{ "enabled": false, "ip": "" }
```
- `enabled` — whether a DMZ host is set
- `ip` — LAN IPv4 that receives all unsolicited inbound traffic (empty when disabled)

Writable via `PUT /fw/dmz/` (per docs; not captured).

### `GET /fw/incoming/`
Incoming-port policy for the box's **own built-in services** (FTP, BitTorrent, HTTP/HTTPS remote admin, VPN servers). This is a fixed list keyed by service `id`, not user rules. `result` is an array; each entry looks like:

```json
{ "id": "http", "type": "tcp", "enabled": true, "active": true,
  "in_port": 21252, "min_port": 16384, "max_port": 32767,
  "readonly": false, "netns": "init" }
```
- `id` — service key. All observed: `ftp`, `ftp_pasv`, `bittorrent-main`, `bittorrent-dht`, `http`, `https`, `openvpn_routed`, `openvpn_bridge`, `pptp`, `ipsec_ike`, `ipsec_nat`, `wireguard`
- `type` — `tcp` / `udp` / `tcp_udp`
- `enabled` — service allowed inbound; `active` — service currently listening/running
- `in_port` — the actual WAN port in effect; `min_port`/`max_port` — allowed range (`16384`–`32767` on all entries here) when the port is user-configurable
- `readonly` — `true` for fixed-port protocols: `pptp` (`in_port` 1723), `ipsec_ike` (500), `ipsec_nat` (4500); their `in_port` cannot be changed
- `netns` — network namespace (always `"init"` here)

Editable per entry via `GET /fw/incoming/{port_id}` / `PUT /fw/incoming/{port_id}` (per docs).

### `GET /upnpigd/config/`
UPnP IGD (automatic port mapping) service state.

```json
{ "enabled": true, "version": 1 }
```
- `enabled` — whether apps on the LAN may request their own port mappings
- `version` — IGD protocol version advertised (`1` here)

Writable via `PUT /upnpigd/config/` (per docs; not captured).

### `GET /upnpigd/redir/`
Dynamic redirects **created by LAN clients via UPnP** (distinct from the static `/fw/redir/` rules). `result` is an array; each entry carries the rule fields plus a fully expanded `host` object (same shape as `/lan/browser` hosts).

Rule-level fields (host object omitted):
```json
{
  "id": "0.0.0.0-26476-tcp",
  "enabled": true,
  "proto": "tcp",
  "desc": "Plex Media Server",
  "ext_src_ip": "0.0.0.0",
  "ext_port": 26476,
  "int_ip": "192.168.1.49",
  "int_port": 32400,
  "remaining": 0
}
```
- `id` — synthetic key `{ext_src_ip}-{ext_port}-{proto}`
- `proto` — `tcp` / `udp`
- `desc` — description supplied by the requesting app (here `"Plex Media Server"`)
- `ext_src_ip` — allowed external source (`0.0.0.0` = any)
- `ext_port` → `int_ip`:`int_port` — the WAN-to-LAN mapping (`int_ip` shown is a scrub placeholder in the `192.168.1.x` range)
- `remaining` — lease seconds left (`0` = no expiry / permanent lease)
- `host` — nested full LAN-host object (`l2ident`, `names[]`, `vendor_name`, `host_type`, `l3connectivities[]`, `access_point`, `interface`, …) identifying the device that owns the mapping

Individual mappings can be torn down via `DELETE /upnpigd/redir/{id}` (per docs). No POST/PUT — these are created by clients, not the API.

### `GET /domain/config/`
DDNS / custom-domain config backing the "Nom de domaine" (remote-access hostname) feature. **[undocumented upstream]** — the frozen public SDK (API 4.0) has no `domain` section (nor does it appear in this box's on-box v16 endpoint inventory).

```json
{
  "default_domain": "",
  "root_domains": ["freeboxos.fr"],
  "api_domain": "fake-1.fbxos.fr"
}
```
- `default_domain` — user-selected custom domain (empty = none configured)
- `root_domains` — Free-provided root domains available for a free subdomain (`freeboxos.fr`)
- `api_domain` — the box's auto-assigned `*.fbxos.fr` hostname used for authenticated remote API access (value scrubbed to `fake-1.fbxos.fr`)

### Not captured (exist in on-box docs, API v16)
- `PUT /fw/dmz/`, `POST /fw/redir/`, `GET /fw/redir/{redir_id}`, `PUT /fw/redir/{redir_id}`, `DELETE /fw/redir/{redir_id}`
- `GET /fw/incoming/{port_id}`, `PUT /fw/incoming/{port_id}`
- `PUT /upnpigd/config/`, `DELETE /upnpigd/redir/{id}`

All write operations were skipped (read-only capture session); their request schemas were not verified against this box.

---

## Downloads (torrent/NZB/HTTP)

The download manager drives BitTorrent, NNTP/NZB (Usenet), and plain HTTP transfers. All read-only endpoints below were captured live; the write verbs (add/pause/resume/remove/config) are listed from the on-box docs inventory (API v16, shown there as `/api/v8/…`) but were **not** exercised this session. Unlike most domains in this document, Downloads **is** documented in the frozen 4.0 public SDK at dev.freebox.fr — so it is *not* "undocumented upstream". However, the v16 surface is richer than the public SDK: the `news` (NZB/Usenet) config block, the blocklist `sources`, and the RSS/feeds item endpoints go beyond what the 4.0 SDK describes, so treat those specific bits as **[UNSTABLE upstream]**.

**Path encoding:** every filesystem path (`download_dir`, `watch_dir`, file `path`/`filepath`) is **base64-encoded**. E.g. `L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0x` decodes to `/Freebox/scrubbed/file-1` (a scrub placeholder). Decode before display; re-encode when submitting paths in a config PUT.

### `GET /downloads/`
List all download tasks. Returns a JSON array (one object per task).

Per-task fields (from the actual capture):
- `id` (int), `name`, `type` — observed only `http`; other values `bt` / `nzb` per docs
- `status` — observed `error`; other states per stats counters: `downloading`, `seeding`, `queued`, `checking`, `extracting`, `repairing`, `stopping`, `stopped`, `done`
- `size` (bytes), `rx_bytes` / `tx_bytes` (transferred), `rx_rate` / `tx_rate` (bytes/s), `rx_pct` / `tx_pct` (per-10000, so `10000` = 100%)
- `eta` (seconds), `queue_pos`, `io_priority` (`normal`), `stop_ratio`
- `download_dir` — base64 path
- `error` — `none` when no task-level error (note: a task can be `status:"error"` while its `error` field is `"none"`; the real cause shows per-file, see below)
- `created_ts` (unix), `info_hash` / `piece_length` (BitTorrent-only; empty/`0` for http), `archive_password`

```json
{
  "id": 1, "type": "http", "status": "error",
  "name": "file-1", "size": 425860000,
  "rx_bytes": 0, "tx_bytes": 0, "rx_rate": 0, "tx_rate": 0,
  "rx_pct": 0, "tx_pct": 10000, "eta": 0, "queue_pos": 1,
  "io_priority": "normal", "stop_ratio": 0, "archive_password": "",
  "download_dir": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0x",
  "info_hash": "", "piece_length": 0, "created_ts": 1726316875, "error": "none"
}
```

(Values above are scrub placeholders — the path decodes to `/Freebox/scrubbed/file-1`.)

### `GET /downloads/{id}/files`
List files inside a task. Returns an array. (Docs inventory names the path parameter `{task_id}`.)

- `id` (`"<task>-<n>"`, e.g. `"1-1"`), `task_id`, `name`
- `path` / `filepath` — base64 paths (`filepath` is the full target)
- `size` (bytes), `rx` (received bytes), `status`, `priority`
- `mimetype` (e.g. `application/x-qemu-disk`)
- `error` — here `http_4xx` (the real reason the parent task shows `status:"error"`)

```json
{ "id": "1-1", "task_id": "1", "name": "file-1",
  "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS03",
  "filepath": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS04",
  "mimetype": "application/x-qemu-disk",
  "size": 425869312, "rx": 0, "status": "error",
  "priority": "normal", "error": "http_4xx" }
```

### `GET /downloads/{id}/log/`
Per-task log text. Captured as an empty string (`""`) — the `result` is a plain string, not an object.

### `GET /downloads/stats`
Aggregate manager status — the endpoint for a `fbx top`/dashboard.

- Task counters: `nb_tasks`, `nb_tasks_active`, `nb_tasks_downloading`, `nb_tasks_seeding`, `nb_tasks_queued`, `nb_tasks_stopped`, `nb_tasks_stopping`, `nb_tasks_checking`, `nb_tasks_extracting`, `nb_tasks_repairing`, `nb_tasks_done`, `nb_tasks_error`
- Throughput: `rx_rate` / `tx_rate`, plus `throttling_rate` (`{rx_rate, tx_rate}`), `throttling_mode` (`normal`), `throttling_is_scheduled`
- `nb_peer`, `conn_ready`
- `dht_stats`: `enabled`, `enabled_ipv6`, `node_count`, `node_count_ipv6`
- Blocklist: `blocklist_hits`, `blocklist_entries`
- RSS: `nb_rss`, `nb_rss_items_unread`
- `nzb_config_status`: `{ status: "not_checked", error: "none" }`

```json
{ "nb_tasks": 2, "nb_tasks_error": 2, "nb_tasks_active": 0,
  "rx_rate": 0, "tx_rate": 0, "throttling_mode": "normal",
  "throttling_rate": { "rx_rate": 0, "tx_rate": 0 }, "throttling_is_scheduled": false,
  "dht_stats": { "enabled": false, "node_count": 0, "enabled_ipv6": false, "node_count_ipv6": 0 },
  "nb_peer": 0, "conn_ready": true, "nb_rss": 0, "nb_rss_items_unread": 0,
  "nzb_config_status": { "status": "not_checked", "error": "none" } }
```

### `GET /downloads/config/`
Global download-manager configuration.

- `download_dir`, `watch_dir` — base64 paths; `use_watch_dir` (bool) toggles the watch folder
- `max_downloading_tasks` (5), `dns1` / `dns2` (empty when default)
- `bt` (BitTorrent): `enable_dht`, `dht_port`, `main_port`, `min_port`/`max_port`, `max_peers`, `enable_pex`, `stop_ratio`, `announce_timeout`, `crypto_support` (`allowed`)
- `news` (NZB/Usenet) **[UNSTABLE upstream]**: `server` (`news.free.fr`), `port` (119), `ssl`, `nthreads`, `user`/`password`, `auto_extract`, `auto_repair`, `lazy_par2`, `erase_tmp`, `file_naming` (`auto`)
- `feed` (RSS defaults): `max_items` (120), `fetch_interval` (60)
- `throttling`: named profiles `normal` and `slow`, each `{ rx_rate, tx_rate }`, plus a `schedule` array of **168 entries** (24 h × 7 days — one per hour of the week), each the profile name to apply that hour (all `"normal"` in capture — verified length 168, single unique value)
- `blocklist`: `{ sources: {} }` (empty in capture)

```json
{ "download_dir": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0y",
  "watch_dir": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0z", "use_watch_dir": true,
  "max_downloading_tasks": 5, "dns1": "", "dns2": "",
  "bt": { "enable_dht": true, "dht_port": 30588, "main_port": 20921,
          "min_port": 16384, "max_port": 32767, "max_peers": 50,
          "enable_pex": true, "stop_ratio": 150, "announce_timeout": 30, "crypto_support": "allowed" },
  "news": { "server": "news.free.fr", "port": 119, "ssl": false, "nthreads": 4,
            "auto_extract": true, "auto_repair": true, "lazy_par2": true, "erase_tmp": true, "file_naming": "auto" },
  "feed": { "max_items": 120, "fetch_interval": 60 },
  "throttling": { "normal": { "rx_rate": 0, "tx_rate": 0 },
                  "slow": { "rx_rate": 512000, "tx_rate": 42000 },
                  "schedule": [ "normal", "... 168 entries ..." ] },
  "blocklist": { "sources": {} } }
```

### `GET /downloads/feeds/`
RSS/news feed list. Captured envelope was `{ "success": true }` with **no `result` key at all** — i.e. no feeds configured (`nb_rss: 0` in stats corroborates). With feeds present this would return an array of feed objects.

---

### Write / mutation verbs — from on-box docs inventory (NOT captured)
Documented in the box's v16 inventory (listed there under the `/api/v8/` prefix) but not exercised this session, so field shapes are unverified:

- `POST /downloads/add` — add a task (appears twice in the inventory: two forms — URL-based, and file/magnet upload)
- `PUT /downloads/{id}` — pause/resume/change priority or `io_priority` (set `status`)
- `DELETE /downloads/{id}` — remove task (keep files)
- `DELETE /downloads/{id}/erase` — remove task **and** erase downloaded files
- `PUT /downloads/{task_id}/files/{file_id}` — set per-file priority
- BitTorrent tracker/peer/piece introspection: `GET /downloads/{task_id}/trackers`, `POST /downloads/{task_id}/trackers`, `PUT`/`DELETE .../trackers/{announce}`; `GET /downloads/{task_id}/peers`; `GET /downloads/{task_id}/pieces`
- Blocklist: `GET /downloads/{task_id}/blacklist`, `DELETE .../blacklist/empty`, `POST /downloads/blacklist`, `DELETE /downloads/blacklist/{host}`
- Feeds: `GET /downloads/feeds/{id}`, `POST /downloads/feeds/`, `PUT`/`DELETE /downloads/feeds/{id}`, `POST /downloads/feeds/{id}/fetch`, `POST /downloads/feeds/fetch`, `GET /downloads/feeds/{feed_id}/items/`, `PUT .../items/{item_id}`, `POST .../items/{item_id}/download`, `POST .../items/mark_all_as_read`
- Config: `PUT /downloads/config/` and `PUT /downloads/throttling` — update config / switch throttling profile

Note: the on-box inventory uses the path segment `blacklist` (not "blocklist") for the per-task and global block-list endpoints. Unlike the read endpoints above, these were verified only against the on-box endpoint list — treat request/response shapes as **[UNSTABLE upstream]** until captured.

---

## Filesystem, storage & sharing

The Freebox exposes its attached storage (internal SSD / USB disks) through a filesystem API, a set of file-operation tasks, public share links, and the classic file-sharing daemons (Samba/AFP/FTP/TFTP). All of these are wrapped in the standard `{"success": true, "result": …}` envelope; the snippets below show the unwrapped `result`. Every path in this domain is **base64-encoded** (see below).

Coverage note: the filesystem, share_link, storage, and netshare domains **do exist in the public SDK (API 4.0)**, but the on-box v16 docs are the accurate reference (e.g. `has_basic_raid_support: false` on this fbxgw9-r1 — RAID is present in the API but not supported by this hardware).

### Base64 path encoding

Every `{path}` segment in `/fs/ls/{path}`, and the `path` field returned inside directory entries / partitions, is the **absolute filesystem path, base64-encoded** (standard base64 alphabet, with `=` padding, as observed — not the URL-safe variant). To browse a directory you take its absolute path, base64-encode it, and append it to `/fs/ls/`.

Verified decodings from the capture:

| Encoded (`path`) | Decodes to |
|---|---|
| `Lw==` | `/` (filesystem root; also the TFTP `root`) |
| `L0ZyZWVib3gvc2NydWJiZWQvZmlsZS00` | `/Freebox/scrubbed/file-4` |
| `L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0xNg==` | `/Freebox/scrubbed/file-16` |

The `path` returned in each entry is what you feed back into the next `/fs/ls/` call to descend — you never construct paths client-side by string concatenation; you follow the `path` token the box gives you.

### `GET /fs/ls/{b64path}`

List the contents of a directory. The `{b64path}` is the base64 of the absolute path (omit it — `GET /fs/ls/` with an empty trailing segment — and the box lists a default root, which in the capture returned the top-level `Freebox` entry).

Query params (per on-box docs; not visible in these captures): `countSubFolder`, `removeHidden`, `onlyFolder`.

Response is `{"entries": [ … ]}`. Each entry (from a real listing of `/Freebox/scrubbed/file-10`):

```json
{
  "type": "dir",
  "name": "Vidéos",
  "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0xNQ==",
  "index": 4,
  "size": 4096,
  "modification": 1770024546,
  "mimetype": "inode/directory",
  "hidden": false,
  "link": false,
  "foldercount": 4,
  "filecount": 0
}
```

- `type` — `"dir"` or `"file"`.
- `size` — bytes (dirs report the inode size, `4096`).
- `modification` — Unix epoch seconds.
- `mimetype` — `inode/directory` for folders; a real MIME type for files.
- `foldercount` / `filecount` — child counts (populated for directories).
- `hidden`, `link` — booleans; note the `removeHidden` param filters these out server-side.
- An empty directory returns `{"entries": []}`.

### `GET /fs/tasks/`

List active/queued file-operation tasks (copy/move/rm/archive/extract/hash, etc.). At capture time none were running, so the box returned an empty result:

```json
{ "success": true }
```

Per the on-box docs (v15+) the full set of file operations lives under `/fs/`: `POST /fs/mv/`, `/fs/cp/`, `/fs/rm/`, `/fs/cat/`, `/fs/archive/`, `/fs/extract/`, `/fs/repair/`, `/fs/hash/`, `/fs/mkdir/`, `/fs/rename/`, plus `GET /fs/info/{path}` / `POST /fs/info`, `GET/DELETE/PUT /fs/tasks/{id}` and `GET /fs/tasks/{id}/hash`. **[not captured]** — only the empty task list was observed.

### `GET /share_link/`

List public share links (each maps a filesystem path to a token-based public URL, optionally with an expiry). No share links existed at capture time, so:

```json
{ "success": true }
```

Per docs, links are managed with `POST /share_link/` (create), `GET/DELETE /share_link/{token}`. **[entry fields not captured — none configured]**

---

## Storage (disks, partitions, RAID, power)

### `GET /storage/disk/`

Enumerate physical disks and their partitions. Returns an array of disks. From the real capture (one USB disk):

```json
[
  {
    "id": 1000,
    "type": "usb",
    "connector": 0,
    "state": "enabled",
    "table_type": "gpt",
    "total_bytes": 1000000000000,
    "temp": 0,
    "spinning": false,
    "idle": true,
    "idle_duration": 0,
    "active_duration": 0,
    "read_requests": 847962,
    "write_requests": 553288,
    "read_error_requests": 0,
    "write_error_requests": 0,
    "model": "",
    "firmware": "",
    "serial": "",
    "partitions": [ … ]
  }
]
```

- `id` — disk id (referenced by `/storage/disk/{id}`, `/format/`, `fsadvice`).
- `type` — `"usb"` (also `"internal"`/`"sata"` on other hardware).
- `state` — `"enabled"`; `table_type` — partition table (`"gpt"`).
- `total_bytes` — capacity. `temp` — °C (0 here, USB disk reports none).
- `spinning` / `idle` / `idle_duration` / `active_duration` — power/activity state (ties into `/storage/config/` spindown).
- `read_requests` / `write_requests` (+ `_error_` counters) — lifetime I/O counters.
- `model` / `firmware` / `serial` — empty strings on this scrubbed/USB disk.
- `partitions[]` — inline array, same shape as `/storage/partition/` below.

### `GET /storage/partition/`

Flat list of all partitions across disks. From capture:

```json
[
  {
    "id": 1001,
    "disk_id": 1000,
    "label": "Freebox",
    "fstype": "ext4",
    "state": "mounted",
    "internal": false,
    "total_bytes": 984260000000,
    "used_bytes": 626210000000,
    "free_bytes": 358030000000,
    "fsck_result": "no_run_yet",
    "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS00"
  }
]
```

- `id` / `disk_id` — partition id and its parent disk.
- `label` — volume label (this is `user_main_storage: "Freebox"` in `/system/`).
- `fstype` — `"ext4"`; `state` — `"mounted"`.
- `total_bytes` / `used_bytes` / `free_bytes` — space accounting.
- `fsck_result` — `"no_run_yet"` (checked via `PUT /storage/partition/{id}/check/`).
- `path` — base64 of the mount path (`/Freebox/scrubbed/file-4`) — feed to `/fs/ls/` to browse the volume.

### `GET /storage/config/`

Global storage power-management config:

```json
{
  "external_pm_enabled": true,
  "external_pm_idle_before_spindown": 10
}
```

- `external_pm_enabled` — spin down external disks when idle.
- `external_pm_idle_before_spindown` — idle minutes before spindown.

### `GET /storage/raid/` **[UNSTABLE upstream]**

List RAID arrays. This hardware reports `has_basic_raid_support: false` (from `/system/` `model_info`) and has no arrays, so the box returns an empty result:

```json
{ "success": true }
```

Treat RAID as **[UNSTABLE upstream]** — the on-box docs list a large RAID surface (`GET/POST/DELETE /storage/raid/`, `PUT /storage/raid/{id}`, `POST /storage/raid/{id}/forcestart`, `PUT /storage/raid/{id}/members`, `DELETE /storage/raid/{id}/members/faulty`, `POST /storage/raid/{id}/members/addspares`) that is **not exercisable on fbxgw9-r1**; do not rely on its shape. **[array fields not captured — no RAID on this box]**

---

## Network file sharing (Samba, AFP, FTP, TFTP)

### `GET /netshare/samba/`

SMB/CIFS server config:

```json
{
  "workgroup": "WORKGROUP",
  "file_share_enabled": true,
  "print_share_enabled": true,
  "smbv2_enabled": true,
  "logon_enabled": false,
  "logon_user": "freebox",
  "logon_password": ""
}
```

- `file_share_enabled` / `print_share_enabled` — file vs printer sharing toggles.
- `smbv2_enabled` — SMBv2 on.
- `logon_enabled` — whether authenticated (vs guest) access is required; `logon_user`/`logon_password` hold the credential (password blanked in read responses).

### `GET /netshare/afp/`

Apple Filing Protocol server config:

```json
{
  "enabled": true,
  "guest_allow": true,
  "server_type": "airport",
  "login_name": "freebox",
  "login_password": ""
}
```

- `enabled` — AFP on; `guest_allow` — allow guest access.
- `server_type` — `"airport"` (advertises as an AirPort-style server).
- `login_name` / `login_password` — credential (password blanked on read).

### `GET /ftp/config/`

FTP server config (disabled here):

```json
{
  "enabled": false,
  "allow_remote_access": false,
  "allow_anonymous": false,
  "allow_anonymous_write": false,
  "username": "freebox",
  "password": "SCRUBBED_PASSWORD",
  "weak_password": true,
  "remote_domain": "203.0.113.1",
  "port_ctrl": 28013,
  "port_data": 32600,
  "min_port": 16384,
  "max_port": 32767
}
```

(`password` and `remote_domain` above are scrub placeholders, not real values.)

- `enabled` / `allow_remote_access` — local vs WAN-reachable FTP.
- `allow_anonymous` / `allow_anonymous_write` — anonymous access controls.
- `username` / `password` — the FTP account; `weak_password: true` flags a weak credential.
- `remote_domain` — WAN address for remote access (`203.0.113.1` is scrubbed).
- `port_ctrl` / `port_data` and the `min_port`/`max_port` passive range — port config (the control port `28013` corresponds to the `ftp` entry in `/fw/incoming/`).

### `GET /tftp/config/`

TFTP server config:

```json
{
  "enabled": false,
  "root": "Lw=="
}
```

- `enabled` — off.
- `root` — base64 of the served directory; `Lw==` decodes to `/` (same encoding as `/fs/ls/`).

---

### Mutating endpoints in this domain — documented but not captured

All captures here are `GET` (status 200). The on-box docs expose the corresponding writes, none of which were exercised this session (all **[not captured]**): `PUT /netshare/samba/`, `PUT /netshare/afp/`, `PUT /ftp/config/`, `PUT /tftp/config/`, `PUT /storage/config/`, `PUT /storage/disk/{id}` (+ `/format/`), `PUT /storage/partition/{id}` (+ `/check/`), the full `/fs/` operation set, and `POST/DELETE /share_link/`.

---

## Virtual Machines (flagship — undocumented upstream)

**[undocumented upstream]** — The entire `/vm/` API is absent from the public SDK (dev.freebox.fr/sdk/os/, frozen at API 4.0 / 2013 Revolution hardware). Everything here comes from the on-box docs (API v16, listed under `/api/v8/vm/…`) and from live captures off the Freebox Ultra (fbxgw9-r1, firmware 4.12.2). The Ultra runs an ARM64 (aarch64) hypervisor — inferred from the distro image URLs below, which are all `arm64`/`aarch64` builds.

We captured this domain **read-only**: `GET /vm/`, `GET /vm/info/`, `GET /vm/distros/`, plus the WebSocket `vm_state_changed` registration. All 8 lifecycle/mutation endpoints, both consoles, and all 5 disk endpoints are documented from the on-box reference but **not yet exercised** — their request/response shapes remain to be verified in Phase 4.

### `GET /vm/`
List all configured virtual machines. Returns an array; each element is a full VM config object.

```json
{
  "id": 0,
  "name": "host-17",
  "status": "running",
  "os": "debian",
  "vcpus": 1,
  "memory": 1536,
  "disk_path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS01",
  "disk_type": "qcow2",
  "cd_path": "",
  "mac": "02:00:00:00:00:09",
  "enable_screen": false,
  "bind_usb_ports": "",
  "enable_cloudinit": true,
  "cloudinit_hostname": "host-17",
  "cloudinit_userdata": "SCRUBBED_CLOUDINIT_USERDATA"
}
```

Field notes (all observed):
- `id` — integer, stable per-VM; used in every `/vm/{id}` path.
- `status` — observed values `running` and `stopped` (a second VM in the capture was stopped). Other lifecycle states (`starting`, `stopping`, etc.) are presumably pushed via the WebSocket event below.
- `memory` — RAM in **MB** (captured VMs: 1536 and 256).
- `vcpus` — integer vCPU count.
- `disk_path` — **base64-encoded** filesystem path (decodes to `/Freebox/scrubbed/…`), same encoding used across the Freebox filesystem API. `disk_type` was `qcow2` on both captured VMs.
- `cd_path` — base64 path to an install ISO/CD image; empty string when none attached (both captured VMs).
- `mac` — auto-assigned NIC MAC in the `02:00:00:…` locally-administered range.
- `enable_screen` — boolean; when true a VNC framebuffer is exposed (see `/vm/{id}/vnc`).
- `bind_usb_ports` — string list of passed-through USB ports (empty = none); valid port names come from `/vm/info/`.
- `enable_cloudinit` / `cloudinit_hostname` / `cloudinit_userdata` — cloud-init config. **`cloudinit_userdata` is SENSITIVE**: it is the raw cloud-init YAML (`#cloud-config`) and typically contains SSH authorized keys, user passwords/hashes, and provisioning scripts. It was scrubbed to `SCRUBBED_CLOUDINIT_USERDATA` in our capture, and any tooling should treat it as a secret (redact in logs, never echo).

### `GET /vm/{id}`
Fetch a single VM by id. Same object shape as one element of `GET /vm/`. **Not captured** (only the list endpoint was called); the endpoint is present in the on-box inventory.

### `GET /vm/info/`
Host hypervisor capabilities and current resource usage — the numbers you need to validate a create/modify request before submitting it.

```json
{
  "total_cpus": 2,
  "used_cpus": 1,
  "total_memory": 2048,
  "used_memory": 1536,
  "usb_used": false,
  "usb_ports": ["usb-external-type-a"],
  "sata_used": false,
  "sata_ports": {}
}
```

- `total_cpus` / `total_memory` — hard ceiling for VM allocation on this box (Ultra: 2 vCPUs, 2048 MB total). `used_*` are the sums currently committed to running VMs.
- `usb_ports` — array of bindable USB port identifiers (feeds a VM's `bind_usb_ports`); `usb_used` flags whether one is already claimed.
- `sata_ports` — object (empty on this hardware), with `sata_used` flag; present for models exposing SATA passthrough.

### `GET /vm/distros/`
The Free-curated catalog of installable cloud images, so users never hand-type a download URL. Array of image descriptors.

```json
{
  "name": "Ubuntu 24.04 LTS (Noble)",
  "os": "ubuntu",
  "url": "http://ftp.free.fr/.private/ubuntu-cloud/releases/noble/release/ubuntu-24.04-server-cloudimg-arm64.img",
  "hash": "http://ftp.free.fr/.private/ubuntu-cloud/releases/noble/release/SHA256SUMS"
}
```

- Fields observed: `name`, `os`, `url`, `hash`. **No `icon` field was present** in either the digest or the raw capture — it is not returned by API 16.0 on this firmware. Do not document an icon field as observed.
- `url` — direct image download (all `arm64`/`aarch64`, matching the Ultra's architecture). Mirrored via `ftp.free.fr` where possible, else upstream (`cloud.debian.org`, `dl-cdn.alpinelinux.org`, `cloud.centos.org`, `images.jeedom.com`).
- `hash` — **a URL to a checksums file** (e.g. `SHA256SUMS` / `SHA512SUMS` / a `CHECKSUM` or `.sha256`/`.sha512` file), not a literal digest. Consumers must fetch it and match the image filename. One entry (CentOS 8.4) omits `hash` entirely — treat the field as optional.
- 9 images captured: Ubuntu 24.04 / 23.10, Debian 12 / sid, Fedora 40, openSUSE Leap 15.6 JeOS, Alpine 3.20, CentOS 8.4, and Jeedom (home-automation appliance, `os: jeedom`).

### Lifecycle endpoints (documented, not captured)
All from the on-box inventory (`/api/v8/vm/…`); request/response shapes **remain to be exercised (Phase 4)**.

- `POST /vm/` — **[undocumented upstream]** create a VM. Body is expected to be a VM config object (subset of the `GET /vm/` shape: `name`, `os`, `vcpus`, `memory`, `disk_path`, `disk_type`, `cd_path`, `enable_screen`, `bind_usb_ports`, `enable_cloudinit`, `cloudinit_hostname`, `cloudinit_userdata`). Validate `vcpus`/`memory` against `/vm/info/` first.
- `PUT /vm/{id}` — modify an existing VM's config (same fields).
- `DELETE /vm/{id}` — remove a VM definition. (Disk image files are managed separately via the disk endpoints below.)
- `POST /vm/{id}/start` — power on.
- `POST /vm/{id}/powerbutton` — ACPI soft power button (graceful guest shutdown; guest must honor ACPI).
- `POST /vm/{id}/stop` — force stop (hard power-off).
- `POST /vm/{id}/restart` — restart.

### Consoles (documented, not captured)
- `GET /vm/{id}/console` — **[undocumented upstream]** serial console, expected to be a WebSocket upgrade streaming the guest's serial tty (byte-level, bidirectional).
- `GET /vm/{id}/vnc` — VNC framebuffer, expected to be a WebSocket upgrade (only meaningful when `enable_screen: true`). A browser noVNC-style client would connect here for graphical access.

Both are distinct from the event bus at `/ws/event/`.

### Disk management — expected async, task-polled (documented, not captured)
Disk operations appear to be **long-running and task-based**: the create/resize calls are expected to return a task id you poll until completion, rather than blocking on the request.

- `POST /vm/disk/info` — inspect a disk image (body expected to carry the base64 `disk_path`).
- `POST /vm/disk/create` — create a new disk image.
- `POST /vm/disk/resize` — grow/shrink a disk image.
- `GET /vm/disk/task/{id}` — **poll** an in-flight disk task for progress/status.
- `DELETE /vm/disk/task/{id}` — cancel/clear a disk task.

Practical note: a full "install a distro" flow is likely multi-step — pick an image from `/vm/distros/`, download it, `POST /vm/disk/create` (or resize) and poll `/vm/disk/task/{id}` to completion, then `POST /vm/` referencing the resulting `disk_path`, then `POST /vm/{id}/start`. (Exact request/response shapes not yet verified.)

### WebSocket: `vm_state_changed`
VM lifecycle transitions are **pushed** over the event bus at `ws://mafreebox.freebox.fr/api/latest/ws/event/`. The client subscribes with:

```json
{"action":"register","events":["vm_state_changed"]}
```

and the box acknowledges:

```json
{"success":true,"action":"register"}
```

Both the register frame and its `success` ack were captured (the same session also registered `lan_host_l3addr_reachable` / `lan_host_l3addr_unreachable`). **No actual `vm_state_changed` notification body was captured** in this read-only session (no VM changed state during the window), so the notification payload shape is not yet documented from live data — expect it to carry at least the VM `id` and new `status`, to be confirmed in Phase 4. This is the correct mechanism for a `fbx watch`/`fbx top`-style live VM status display: subscribe here rather than polling `/vm/`, since (unlike `/system/` and `/connection/`, which the UI polls ~1 Hz) VM state genuinely arrives as push events.

---

## VPN, parental control, telephony, home, player, PVR, AirMedia

This section covers the "consumer feature" domains. A recurring theme: several of these (VPN client, Home automation, cameras) are **absent from the public SDK (frozen at API 4.0)** and are documented only in the on-box docs (v16). Others require a permission scope that is **not granted by default** and must be ticked by hand in the Freebox OS UI (Settings → this app's authorization) — where that bites, captures returned `404`/error even though the endpoint exists.

### VPN server (marked **[UNSTABLE upstream]**)

The box runs several VPN server backends simultaneously; each has an independent `state`.

#### `GET /vpn/`
Lists the configured VPN servers and their live connection counts.
```json
[
 { "type": "pptp",      "name": "pptp",           "state": "stopped", "connection_count": 0, "auth_connection_count": 0 },
 { "type": "openvpn",   "name": "openvpn_routed", "state": "stopped", "connection_count": 0, "auth_connection_count": 0 },
 { "type": "ipsec",     "name": "ipsec",          "state": "stopped", "connection_count": 0, "auth_connection_count": 0 },
 { "type": "openvpn",   "name": "openvpn_bridge", "state": "stopped", "connection_count": 0, "auth_connection_count": 0 },
 { "type": "wireguard", "name": "wireguard",      "state": "stopped", "connection_count": 0, "auth_connection_count": 0 }
]
```
- Note the **five** server backends incl. `wireguard` — the frozen public SDK predates this list.

#### `GET /vpn/ip_pool/`
Address pool handed to VPN clients.
- `ip_start`, `ip_end` (`192.168.27.65` → `192.168.27.95`), `reservations: []`.

#### `GET /vpn/user/`
Configured VPN users. Empty here — returns only `{ "success": true }` (the list would ride under the envelope's `result`, which was empty).

#### `GET /vpn/connection/`
Active VPN connections. None here — `{ "success": true }`.

- Docs-only, not captured: `GET /vpn/{vpn_id}/config/`, `PUT /vpn/openvpn_routed/config/`, `DELETE /vpn/connection/{id}`, `GET /vpn/download_config/{server_name}/{login}/{fmt}` (downloads a client profile).

### VPN client **[undocumented upstream]**

The Freebox-as-VPN-client feature. Absent from the public SDK; on-box docs only.

#### `GET /vpn_client/status`
- `{ "enabled": false }` — whether the box is currently tunneling its own traffic out through a client VPN.

#### `GET /vpn_client/config/`
- Configured client profiles. Empty here → `{ "success": true }`. Per-profile config lives at `GET /vpn_client/config/{id}` (docs).

#### `GET /vpn_client/log`
- Plain-text log as a JSON string. Empty here → `""`.

### Parental / network control

Gated by the `parental` permission (granted by default in these captures). The list endpoint returns the **full LAN host inventory** grouped by profile, so it is heavy — each host carries `l2ident`, `names[]`, `vendor_name`, `host_type`, and a full `l3connectivities[]` array.

#### `GET /network_control`  (alias `GET /network_control/`)
One object per profile; `override_mode` is the temporary override on top of the schedule.
```json
[{
  "override_mode": "allowed",
  "profile_id": 1,
  "cdayranges": [],
  "hosts": [{
     "id": "ether-02:00:00:00:00:21",
     "primary_name": "host-46",
     "host_type": "laptop",
     "network_control": { "current_mode": "allowed", "profile_id": 1, "name": "person-7" },
     "l3connectivities": [ /* … per-address reachability … */ ]
  }]
}]
```
- Key per-host field: `network_control.current_mode` (`allowed` / …) and `profile_id`. `cdayranges` holds the weekly schedule (empty here).

#### `GET /network_control/{id}/rules`
- Per-profile time rules. Empty here → `{ "success": true }`. Full CRUD in docs (`PUT`/`DELETE .../rules/{rule_id}`). Note the docs list a typo endpoint `POST /network_controlr/{profile_id}/rules/` (extra `r`) — treat as `network_control`.

#### `GET /network_control/migrate`
- One-shot migration status: `{ "default_mode_migrated": true }`.

#### `GET /profile`
The parental profiles (the "who" that network_control references).
```json
[{ "id": 1, "name": "person-7", "icon": "/resources/images/profile/profile_03.png" }]
```
- Fields: `id`, `name`, `icon`. CRUD in docs (`POST`/`PUT`/`DELETE /profile/{id}`).

### Telephony / calls

Gated by the `calls` permission.

#### `GET /call/account`
- `{ "phone_number": "+3310000008" }` — the box's own landline number (scrubbed placeholder).

#### `GET /call/log/`
Call history, newest first.
```json
{ "id": 10, "datetime": 1777904840, "type": "missed",
  "number": "+3310000001", "name": "person-1",
  "contact_id": 0, "duration": 29, "new": true }
```
- All captured entries were `type: "missed"` (docs/other clients also emit `accepted` / `outgoing`). `duration` in seconds. `contact_id` is `0` when the number isn't in the address book. `new: true` = unacknowledged. Mutations in docs: `DELETE /call/log/{id}`, `POST /call/log/delete_all/`, `POST /call/log/mark_all_as_read/`.

#### `GET /call/voicemail/`
- **Returned an error body** (HTTP 200, `success: false`): `{ "success": false, "error_code": "internal_error" }` (no voicemail service provisioned on this line). Docs also define `/call/voicemail/{id}`, `.../audio_file`.

### Address book (contacts / groups)

Gated by the `contacts` permission.

#### `GET /contact/`
- Empty address book here → envelope `{ "success": true }` (no `result` array). Docs: full CRUD plus sub-collections `GET /contact/{contact_id}/[numbers|addresses|urls|emails]/` and the top-level `[number|address|url|email]` object endpoints.

#### `GET /contact/count`
- Bare integer `0` (note: not wrapped in an object).

#### `GET /group/`
- Contact groups: `{ "total": 0, "success": true }`. (Captured; the on-box doc inventory has no `/group` CRUD endpoints listed.)

### Home automation & cameras **[undocumented upstream]**

Absent from the public SDK. **The `home` and `camera` permission scopes are NOT granted by default** — in the `/authorization/` capture both `home` and `camera` were `false` for the installed apps. With the scope ungranted, every endpoint below returned **`404` `invalid_request`** despite existing:

#### `GET /home/adapters` — **404** `invalid_request` (scope not granted)
#### `GET /home/nodes` — **404** `invalid_request`
#### `GET /home/tileset/all` — **404** `invalid_request`
#### `GET /camera/` — **404** `invalid_request`

- To exercise these, the user must grant the alarm/home-automation and camera scopes by hand in the app's authorization page, then re-request. Docs define the fuller tree: `/home/adapters/{id}`, `/home/pairing/{adapter_id}`, `/home/nodes/{id}`, `/home/endpoints/{node_id}/{endpoint_id}`, `/home/tileset/{node_id}`, `/camera/{id}`.

### Player devices

#### `GET /player`
Lists paired Freebox Players.
```json
[{ "mac": "02:00:00:00:00:0c", "device_name": "Freebox Player POP",
   "device_model": "fbx8am", "stb_type": "stb_v8",
   "reachable": true, "api_available": false,
   "last_time_reachable": 1783943627,
   "lan_gids": ["ether-02:00:00:00:00:0c", "ether-02:00:00:00:00:22"] }]
```
- Note `api_available: false` here — the per-player control API (`GET /player/{id}/api/v6/status/`, `POST .../control/mediactrl/`, `GET|PUT .../control/volume/`, `POST .../control/open`) is only reachable when the player exposes it; those sub-endpoints were not capturable. `stb_type: stb_v8` = the POP generation.

### PVR (recording)

Gated by the `pvr` permission (granted by default here).

#### `GET /pvr/config/`
- `{ "margin_before": 0, "auto_ack": false, "margin_after": 0 }` — recording padding (seconds) and auto-acknowledge.

#### `GET /pvr/quota/`
- `{ "quota_exceeded": true, "needed_tresh": 8, "cur_tresh": 0 }` — recording-space threshold state.

#### `GET /pvr/media/`
Per-storage recording capacity, with estimated recordable time by stream type.
```json
[{ "media": "Freebox", "free_bytes": 358030000000, "total_bytes": 984260000000,
   "record_time": { "dvb": { "sd": 437048, "hd": 317853, "3d": 317853 },
                    "iptv": { "ld": 1398554, "sd": 998967, "hd": 460050, "3d": 460050 } } }]
```

#### `GET /pvr/programmed/`
- Scheduled recordings — none here → `{ "success": true }`.

#### `GET /pvr/finished/`
- Completed recordings — none here → `{ "success": true }`. Docs: per-item `GET/PUT/DELETE /pvr/{programmed|finished}/{id}`, `POST /pvr/programmed/`.

### AirMedia (AirPlay / cast)

#### `GET /airmedia/config/`
- `{ "enabled": true, "password": "" }` — global AirMedia receiver toggle and optional passcode.

#### `GET /airmedia/receivers/`
Discoverable receivers (Players) and their capabilities.
```json
[{ "name": "host-1", "password_protected": false,
   "capabilities": { "photo": false, "screen": false, "audio": true, "video": false } },
 { "name": "host-2", "password_protected": false,
   "capabilities": { "photo": false, "screen": true, "audio": true, "video": true } }]
```
- Docs also define `POST /airmedia/receviers/{receiver_name}/` (note upstream's `receviers` typo) to push media to a receiver.

### Access management / permissions model

#### `GET /authorization/`
The authoritative list of third-party apps that hold a token, each with its **granted permission scopes**. This is the master cross-reference for every permission gate mentioned above.
```json
[{
  "id": 1, "app_id": "fr.freebox.framework", "app_name": "Freebox Connect",
  "device_name": "iPhone", "app_version": "3238",
  "req_ip": "192.168.1.94", "req_date": 1711455980, "last_session": 1770580548,
  "token_validity": "granted",
  "permissions": {
    "parental": true, "downloader": true, "explorer": true, "tv": true, "wdo": true,
    "camera": false, "profile": true, "player": true, "settings": true,
    "calls": true, "home": false, "pvr": true, "vm": true, "contacts": true }
}]
```
- The permission keys map 1:1 to the domains above. Observed: `camera` and `home` are **`false`** for both installed app tokens — confirming why the Home/camera endpoints 404'd. `token_validity` is `granted`.
- Complementary endpoint (captured): `GET /login/perms/` returns the **current session's** granted scopes with human labels, e.g. `"camera": { "granted": true, "desc": "Accès aux caméras" }`. (This session had camera granted, unlike the stored app tokens.) The captured v16 Login-section doc inventory (`POST /login/authorize/`, `GET /login/authorize/{track_id}`, `GET /login/`, `POST /login/session/`, `POST /login/logout/`) lists no per-app revocation endpoint — do that from the Freebox OS UI.

### Misc system/config surfaces

Small single-shot config endpoints relevant to a CLI's "info"/"settings" surface:

- **`GET /update/`** — firmware update state: `{ "state": "up_to_date" }`.
- **`GET /standby/status`** — box standby planning: `{ "use_planning": false, "planning_mode": "wifi_off", "available_planning_modes": ["wifi_off", "suspend"], "next_change": 0 }`.
- **`GET /sfp/status`** — SFP cage (distinct from the FTTH SFP under `/connection/ftth/`): `{ "type": "p2p_1g", "present": false, "link": false, "supported": false, "power_good": true, "eeprom_valid": false }`. No module in the generic cage here.
- **`GET /lang/`** — UI language: `{ "lang": "fra", "avalaible": ["fra","eng","ita"] }` (note upstream's `avalaible` misspelling — do not "correct" it in client code).
- **`GET /lcd/config/`** — front-panel LCD: `{ "hide_status_led": false, "hide_wifi_key": false, "brightness": 100, "orientation": 0, "orientation_forced": false }`.
- **`GET /ledstrip/status`** — **`{ "success": false, "error_code": "notsupp" }`** (HTTP 200) on this hardware (fbxgw9-r1 has no addressable LED strip). Endpoint exists in v16 docs (also `PUT /ledstrip/planning`) but this model returns `notsupp`.
- **`GET /upnpav/config/`** — DLNA media server toggle: `{ "enabled": true }`.
- **`GET /notif/targets`** (alias `/notif/targets/`) — registered push-notification targets (mobile apps). Each: `type` (`firebase`), `name`, `id`, `subscriptions` (e.g. `["box_state"]`), `api_url`, `message_type`, `last_use`. This is the registry behind box → phone push (separate from the WebSocket event channel).
- **`GET /switch/status/`** — physical switch ports (captured; per-port stats live under `/switch/port/{id}/stats`).

### Docs-only endpoints in these domains not captured this session
Worth listing for completeness (exist in v16 on-box docs, not exercised): VPN `PUT /vpn/openvpn_routed/config/` and `GET /vpn/download_config/...`; VPN-client CRUD (`POST/PUT/DELETE /vpn_client/config/{id}`); all Home pairing/endpoint mutations; player control sub-API (`mediactrl`/`volume`/`open`); PVR per-item CRUD; contact CRUD (plus its `number`/`address`/`url`/`email` sub-objects); `POST /airmedia/receviers/{receiver_name}/`.

---

## Appendix — capture coverage

These notes are backed by scrubbed captures in [`recon/capture/`](../recon/capture/).
118 distinct endpoints were exercised (10 clicked-through sections plus a
bulk-GET of every documented read-only endpoint). Endpoints listed above with
no captured body are drawn from the box's on-box docs
([`recon/doc_inventory.json`](../recon/doc_inventory.json), 343 endpoints) and
are marked where their request/response shape still needs to be exercised —
chiefly the VM mutation and disk-task endpoints (Phase 4) and the write verbs
across every domain (Phase 3).

| Capture | Section |
|---|---|
| `api_version.json` | discovery |
| `etat-freebox.json` | system, connection, FTTH/SFP, LTE backup, RRD |
| `lan-devices.json` | LAN browser, DHCP |
| `downloads.json` | downloads |
| `fs.json` | filesystem, storage, share links |
| `settings-access.json` | bulk config sweep + access management / authorizations |
| `bulk-harvest.json` | every documented read-only GET (86/92 returned 200) |
| `calls-contacts-profiles-pvr.json` | telephony, contacts, parental profiles, PVR |
| `vm-readonly.json` | VM list/info/distros + the register frames |
| `ws-events.json` | WebSocket notification samples |

**Methods, path shapes, and field names above are grounded in those captures
or in the on-box docs.** Where the two disagree, the capture wins and is
marked. Run `python3 recon/summarize.py recon/capture/*.json` for the raw
endpoint list per file.

