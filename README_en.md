<div align="center">
<h1>Minecraft Queqiao</h1>
<p><strong>Connect Minecraft servers to AstrBot via the QueQiao mod for message and image bridging, server management and AI chat</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-v0.5.4-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; QueQiao &nbsp;&nbsp; Message Bridge &nbsp;&nbsp; Image Bridge &nbsp;&nbsp; AI Chat</sub></p>
<p><a href="README.md">中文</a> &nbsp;/&nbsp; <strong>English</strong></p>
</div>

## Features

Connects Minecraft servers to AstrBot through the [QueQiao](https://github.com/17TheWord/QueQiao) mod, bridging group chat with in-game chat and providing server management.

- **Chat bridge**: two-way forwarding between in-game chat and group messages
- **Image forwarding**: group images relayed into the game (players need the [ChatImage](https://github.com/kitUIN/ChatImage) mod installed to render them); in-game images / links are downloaded and sent back to the group
- **Event broadcast**: player join / quit / death / achievement events forwarded to sessions (death & achievements unsupported on Vanilla/Velocity)
- **Server management**: status queries, online player list, remote command execution
- **Web Dashboard**: view server status, performance monitoring (TPS / latency) and the bridge terminal in real time, with quick broadcast and command console
- **AI chat**: talk to the AI in-game with the `ai` prefix; replies are sent privately to the player
- **Multiple servers**: connect several servers, each with independent forwarding settings
- **Flexible transport**: forward mode (plugin dials QueQiao) or reverse mode (QueQiao dials plugin, ideal for rented servers)

## Commands

| Command | Permission | Description |
|---------|------------|-------------|
| `/mc help` | Everyone | Show help and custom command list |
| `/mc status [number\|address]` | Everyone | Show server status (online count, latency, etc.) |
| `/mc list [number\|address]` | Everyone | Show online player list |
| `/mc player [number] <id>` | Everyone | Show player info (requires RCON) |
| `/mc cmd [number] <command>` | Admin | Execute a server command, filtered by the allow/deny list |
| `/mc say [number] <text>` | Admin | Broadcast a message in-game |
| `/mc bind <game_id>` | Everyone | Bind your game ID |
| `/mc unbind` | Everyone | Remove the binding |
| `/mc servers` | Everyone | List configured servers and connection state |

When several servers are configured, prefix the command with a number to pick the target (e.g. `mc cmd 1 time set day` targets the first server); with one server it can be omitted. Run `mc servers` to see each server's number.

`mc status` / `mc list` also support **direct address query**: pass a `host:port` instead (e.g. `mc status 127.0.0.1:25565`) and the plugin queries **any** server directly over the Minecraft SLP protocol (version, online count, latency, MOTD, player names) with no QueQiao or config needed. When the port is omitted it defaults to `25565`.

### Custom commands

The `cmd.custom_cmd_list` option defines shortcuts using this syntax:

```
trigger <&param&><<>>actual command {param} {sender}
```

- Everything left of `<<>>` is the trigger template, right of it is the command to run
- `{sender}` is replaced with the sender's **bound game ID**
- `<&xxx&>` are positional placeholders, substituted by matching names on both sides

Example: `tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>` — if user A has bound the game ID `Misaka` and sends `tp 114 514 1919` in the group, the server actually runs `tp Misaka 114 514 1919`.

## Configuration

### Connection

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `target_sessions` | list | empty | **Target sessions** (required): session UMO list for MC messages; defines the MC ↔ chat binding — when empty the group receives nothing |
| `server_name` | string | `Server` | **Server name** (unique identifier), must match QueQiao's `server_name`; must differ across servers |
| `display_name` | string | empty | Display name (may be Chinese, e.g. `生存服`), display only; falls back to `display_name_default` when blank |
| `display_name_default` | string | `MC` | Display-name default: what `{display_name}` and status output show when `display_name` is blank |
| `ws_mode` | string | `forward` | `forward`: plugin dials QueQiao; `reverse`: plugin listens for QueQiao |
| `ws_url` | string | `ws://127.0.0.1:8080/minecraft/ws` | Forward-mode URL, matches QueQiao `websocket_server` |
| `reverse_host` | string | `0.0.0.0` | Reverse-mode listen address |
| `reverse_port` | int | `8080` | Reverse-mode listen port |
| `reverse_path` | string | `/minecraft/ws` | Reverse-mode listen path |
| `access_token` | string | empty | Matches QueQiao `access_token`; empty disables auth |
| `client_origin` | string | `astrbot` | Sent as `x-client-origin`; leave unchanged unless needed |

</details>

### Message forwarding

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `forward_chat_to_astrbot` | bool | `true` | Forward player chat to target sessions |
| `forward_chat_format` | string | `[{display_name}]{player}: {message}` | Chat format; supports `{player}` `{message}` `{display_name}` |
| `forward_join_leave_to_astrbot` | bool | `false` | Forward join/quit messages (server display name appended, so the source is clear when several servers share a group) |
| `forward_death_to_astrbot` | bool | `false` | Forward death messages (unsupported on Vanilla/Velocity) |
| `forward_achievement_to_astrbot` | bool | `false` | Forward achievement messages (unsupported on Vanilla/Velocity) |
| `auto_forward_prefix` | string | empty | Group messages starting with it are relayed into the game; empty relays all |
| `broadcast_format` | string | `[{platform}]{sender}: {message}` | Format used when relaying into the game; supports `{platform}` `{sender}` `{message}` `{display_name}` `{server_name}` |
| `platform_names` | list | `["aiocqhttp=QQ"]` | Platform name mapping: `raw=display`, e.g. `aiocqhttp=QQ` |
| `broadcast_color` | string | `white` | Message color; MC color name or `#RRGGBB` |
| `mark_option` | string | `emoji` | Acknowledgement after a successful relay: `text` replies ✅ / `emoji` reacts to the original message / `none` silent |
| `mark_emoji_id` | int | `124` | Reaction emoji ID (QQ emoji ID; default `124` = 👌) |
| `forward_image_to_mc` | bool | `false` | Relay group images into the game (requires ChatImage on the client to render; otherwise the CICode text is shown) |
| `chatimage_name` | string | `图片` | In-game display name for the image |
| `forward_image_from_mc` | bool | `false` | In-game images (CICode / links) downloaded and sent back as images |

> Get a session's UMO with **AstrBot's built-in `/sid` command**: send `/sid` in the target group/DM, and the `UMO` field in the reply is the value to fill in (e.g. `aiocqhttp:GroupMessage:123456789`). This list drives three things at once: which sessions receive MC messages, which sessions' messages are relayed into MC, and which server the `mc` commands issued in that session belong to.

> `mark_option: emoji` adds a reaction to the **original message** that triggered the relay (no extra message is sent); every aiocqhttp protocol implementation (NapCat, Lagrange, LLOneBot, etc.) supports it, other platforms are skipped silently.

Common `mark_emoji_id` values:

| Constant | ID | Emoji |
|----------|----|-------|
| `EMOJI_OK_GESTURE` | `124` | 👌 |
| `EMOJI_THUMBS_UP` | `76` | 👍 |
| `EMOJI_LOVE` | `66` | ❤️ |
| `EMOJI_ROSE` | `63` | 🌹 |

</details>

### Relaying images into the game (ChatImage)

With `forward_image_to_mc` enabled, images in group messages are broadcast as messages carrying a URL, which each player's client downloads and renders:

```
[QQ]UserA: [[CICode,url=https://example.com/images/example.png,name=图片]]
```

- Only enable it on servers where players have the [ChatImage](https://github.com/kitUIN/ChatImage) mod (Fabric / Forge / NeoForge) installed — otherwise only the `[[CICode,...]]` text is shown
- The image URL must be reachable from player clients; when an image has no public URL (the log says "图片均无可访问的公开 URL"), turn on the root-level `enable_image_upload` and configure `image_upload_services` (see below)
- When `auto_forward_prefix` is set, only images in messages carrying the prefix are relayed (a bare image message has no text and never matches the prefix)

### Relaying in-game images to external sessions

With `forward_image_from_mc` enabled, ChatImage `[[CICode,url=...]]` codes or image links in game chat are downloaded and sent to the group as images:

- `http(s)://` links are downloaded directly; `file://` local files are only readable when AstrBot runs on the same machine as the game
- On download failure (dead link, invisible local file, etc.) the original code/link text is kept
- 5 MB per image, 15 s download timeout

#### Built-in image HTTP service

Some protocol clients deliver images only as base64 / local files with no externally reachable URL. Add a **"Built-in image HTTP service"** entry (template `builtin_http`) in `image_upload_services` — the plugin caches the image bytes in its built-in HTTP service and broadcasts `{base_url}/img/<token>` for player clients to load. **The prerequisite is that AstrBot has a publicly reachable address**; image bytes are cached in memory for 30 minutes (up to 500 entries).

#### Generic image bed

Automatically upload images without a public URL to an image bed to get a publicly reachable link, then broadcast it into the game:

1. Turn on the root-level switch `enable_image_upload`
2. Adjust `image_upload_timeout` (upload timeout, default 30 s) as needed
3. Add image bed entries in `image_upload_services`: no bed is loaded by default — the **"Custom"** template at the top accepts any upload endpoint, the rest are pre-configured templates (endpoint and response mode pre-filled, just supply a token where needed)

| Entry field | Type | Default | Description |
|-------------|------|---------|-------------|
| `enabled` | bool | `true` | Enable this image bed entry |
| `name` | string | empty | Display name (logs/labels only) |
| `upload_url` | string | empty | **Full upload endpoint URL (not the site homepage)** |
| `token` | string | empty | API token (sent as `Authorization: Bearer <token>` header plus a `token` form field); leave empty for token-free beds |
| `response` | string | `text` | Response parsing: `text` = the response body is the link; `json` = the `url` field (falling back to the first `http(s)://` field) |
| `file_field` | string | `file` | Multipart file field name (a few beds use `image`, `fileToUpload`, etc.) |
| `headers` | string | empty | Custom request headers: one `Name: Value` per line (or a JSON object) |
| `form_fields` | string | empty | Extra plain form fields: one `Name: Value` per line (or a JSON object) |

Pre-configured templates:

<details>
<summary>Show pre-configured templates</summary>

| Template | Region | Token | Response | Size / quota | Notes |
|----------|--------|-------|----------|--------------|-------|
| `catbox` | overseas | no | `text` | ≤200MB per image | anonymous direct upload |
| `litterbox` | overseas | no | `text` | ≤1GB per image | catbox's temporary branch; images expire automatically (`form_fields` pre-filled with `time: 72h`) |
| `imglink` | overseas | no | `json` | ≤25MB per image | anonymous direct upload; the server re-encodes images |
| `img402.dev` | overseas | no | `json` | ≤10MB per image | file field is `image`; ≤1MB stored permanently, 1–10MB for 30 days |
| `pngurl` | domestic | no | `json` | — | successor of pngcdn.cn |
| `picui` | domestic | no | `json` | — | Lsky-style endpoint |
| `anyapi` | domestic relay | no | `json` | suggested ≤10MB per file | anyapi relay proxy |
| `xinyew` | domestic | no | `json` | — | 360 image bed |
| `xunjinlu` | domestic | no | `json` | — | multi-endpoint aggregator that picks an upstream by file size |
| `imgloc` | domestic | yes | `json` | ~6MB per image | 路过图床; register for a token |
| `see` | domestic | yes | `json` | ≤5MB per image | S.EE / sm.ms; file field is `smfile` |
| `imgbb` | overseas | yes | `json` | ≤32MB per image | established API; file field is `image` |

</details>

- Multiple enabled entries are **tried in list order**; the first success is broadcast into the game; when all fail, a warning aggregates each failure as `name: reason`
- ⚠️ **Privacy notice**: group images are uploaded to the image bed — enable only when needed

### Server display name and format placeholders

`server_name` is the **connection identity** used by QueQiao (cannot be Chinese). To make multiple servers easier to tell apart in a group, set `display_name` (display only, may be Chinese):

```jsonc
"server": {
  "server_name": "survival",       // must match QueQiao's config.yml
  "display_name": "生存服",        // display only
  "display_name_default": "MC"     // shown when display_name is blank
}
```

Format placeholders:

| Placeholder | Available in | Meaning |
|-------------|--------------|---------|
| `{player}` | `forward_chat_format` | Player name |
| `{message}` | both formats | Message content |
| `{display_name}` | both formats | Server display name; falls back to `display_name_default` (`MC`) when blank, renders empty only when both are cleared |
| `{platform}` | `broadcast_format` | Platform name (may be rewritten via `platform_names`, e.g. `aiocqhttp` → `QQ`) |
| `{sender}` | `broadcast_format` | Sender name |
| `{server_name}` | `broadcast_format` | Server name (always populated) |

Example: `display_name` = `生存服`, format `[{display_name}] <{player}> {message}` → `[生存服] <Steve> 大家好`; with nothing filled in → `[MC] <Steve> 大家好`.

> Join/quit pushes, `mc status` and `mc list` titles use the same chain (`display_name` → `display_name_default` → `server_name`); the handshake and logs keep using `server_name`.

### AI chat

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable_ai_chat` | bool | `true` | Master switch for in-game AI chat |
| `ai_chat_prefix` | string | `ai` | Trigger prefix: in-game chat like `ai hello` goes to the AI, replied privately; empty disables the trigger |

The two prefixes act in different directions and are configured independently; a given message matches only one of them:

| Prefix | Direction | Effect |
|--------|-----------|--------|
| `auto_forward_prefix` | group → MC | Group messages starting with it are relayed into the game |
| `ai_chat_prefix` | in-game → AI | In-game chat starting with it triggers the AI and is **not** relayed to the group |

> Matching does word-boundary checks: a prefix ending in a letter/digit must be followed by a space or the end of the message, so `ai` will not misfire on `aim`/`airport`; letter matching is case-insensitive. Do not let the two prefixes contain one another, or a message's routing becomes ambiguous (a startup warning is logged). Leaving `ai_chat_prefix` empty does **not** make every message trigger the AI.

</details>

### Commands

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable remote command execution |
| `cmd_white_black_list` | string | `white` | `white`: only listed; `black`: all but listed; `none`: unrestricted |
| `cmd_list` | list | `["say","list","weather","time"]` | Command names without the leading `/` |
| `bind_enable` | bool | `true` | Enable account ↔ game ID binding |
| `custom_cmd_list` | list | empty | Custom command mappings, see above |
| `rcon_enabled` | bool | `false` | Connect to RCON directly when QueQiao's RCON is unavailable |
| `rcon_host` | string | `localhost` | RCON host |
| `rcon_port` | int | `25575` | RCON port |
| `rcon_password` | string | empty | RCON password |

> ⚠️ The old `rcon_fallback` config is deprecated — fill in the four fields above instead.

</details>

### Plugin options

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable the plugin |
| `text2image` | bool | `true` | Render server info as an image, falling back to text |

</details>

### Reconnect

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `reconnect_interval` | int | `5` | Reconnect delay in seconds, growing with each failed attempt, capped at 60s |
| `max_reconnect` | int | `0` | Max reconnect attempts; `0` means unlimited |
| `low_frequency_threshold` | int | `30` | Once consecutive failures **exceed** this count, retries switch to a fixed `low_frequency_interval`; `0` disables low-frequency mode |
| `low_frequency_interval` | int | `300` | Low-frequency retry delay (s), default 5 minutes |

</details>

### Performance Monitoring

TPS and latency monitoring are **enabled by default, zero-config**: a background task periodically samples and persists the data; the dashboard's "Performance Monitoring" panel shows trend charts and summaries, with parameters adjusted in the panel's "⚙ Settings" (taking effect immediately on save).

| Parameter | Default | Description |
|-----------|---------|-------------|
| Enable switch | `on` | Stops sampling when off |
| Sample interval | `60` s | Minimum `10` s |
| Retention | `7` days | Older samples pruned automatically |
| TPS command | `auto` | Auto-picks by server brand (Forge → `forge tps`; Fabric/Quilt → `spark tps`; Bukkit forks → `tps`); may be pinned manually |
| Latency domain | empty | Public address of the MC server (may include a port, e.g. `mc.example.com:25565`) for player-perspective latency; empty disables latency probing |

- **TPS**: parsed from a TPS command executed over RCON — the server must support the command (Vanilla reports it as unavailable)
- **Latency**: direct-connect Minecraft SLP ping (no QueQiao relay, no RCON) — a public probe address must be filled in Settings; servers with SLP disabled or unreachable addresses report latency as unavailable
- Samples are stored per-day under `data_dir/monitor/` and survive restarts; `/mc status` also shows the latest samples

## Deployment and FAQ

### Installation

1. Place this plugin under AstrBot's `data/plugins/` directory and restart AstrBot
2. In the WebUI plugin config, click "Add MC server" and **fill in "Target sessions" (required)**
3. Make sure `server_name` exactly matches QueQiao's `server_name`

> When AstrBot and MC run on one machine, the default connection settings already line up with QueQiao's default port — nothing needs changing, just set "Target sessions".

### Networking and addresses (Docker / same-machine setups)

Whether `host` should be `127.0.0.1` or `0.0.0.0` depends on whether AstrBot and MC share a network stack — the only criterion is: **can AstrBot reach the address QueQiao is listening on?**

| Scenario | QueQiao `websocket_server.host` | Plugin `ws_url` |
|----------|--------------------------------|-----------------|
| Same machine (same network stack) | `127.0.0.1` (default) | `ws://127.0.0.1:8080/minecraft/ws` |
| Different machines | that machine's reachable address (LAN IP or `0.0.0.0`) | `ws://<MC server IP>:8080/minecraft/ws` |
| AstrBot in Docker, MC on the host (or vice versa) | `0.0.0.0` | the host's reachable address |
| Separate containers | `0.0.0.0` | the MC container's published port or container name |

> `0.0.0.0` is a **listen** address (all interfaces) and belongs only on the server side (QueQiao's `websocket_server.host`, the plugin's `reverse_host`). Fill `ws_url` with the address at which the MC server is reachable *from the machine running AstrBot*. Change one side and you must change the other to match.

Troubleshooting notes:

- Success is logged as `已连接鹊桥 (ws://...)`; a reachable TCP port alone does not mean the handshake succeeded
- Continuous reconnects with no explicit error usually mean QueQiao's `host` is still `127.0.0.1` (bound only to the container's loopback, so it never receives docker-proxy traffic)
- The startup line `WebSocket Server 在 <address>:<port> 启动...` tells you the actual bound address

### Configuring QueQiao

Install the [QueQiao](https://modrinth.com/plugin/queqiao) plugin/mod on your Minecraft server and configure `config.yml` as described in its [documentation](https://github.com/17TheWord/queqiao-docs):

```yaml
server_name: "Server"        # must match the plugin's server_name
access_token: ""             # matches the plugin's access_token
websocket_server:
  enable: true               # required for forward mode
  host: "127.0.0.1"          # for Docker and cross-network setups see above
  port: 8080
websocket_client:
  enable: false              # required for reverse mode; fill in url_list
  url_list: ["ws://127.0.0.1:8080/minecraft/ws"]
rcon:
  enable: true               # required by mc cmd and mc list
  port: 25575
  password: "your_password"
subscribe_event:             # enable the events you need
  player_chat: true
  player_join: true
  player_quit: true
  player_death: true
  player_advancement: true
```

### Compatibility

| Capability | Minimum QueQiao version |
|------------|-------------------------|
| API V2 (broadcast / private message / title / action bar / RCON) | v0.2.11 |
| Event V2 | v0.3.0 |
| Translate model for death and achievement text | v0.4.1 |
| Server status via `mc status` | v0.5.0 |

### Dependencies

- Python 3.10+
- AstrBot >= 4.10.4
- `websockets` (required to connect to QueQiao)
- `aio-mc-rcon` (only needed for the direct RCON fallback)

### FAQ

**Q: Connection fails with an auth error or 404?** Verify that `server_name` matches QueQiao's exactly, including case, and that `access_token` is identical on both sides.

**Q: The plugin keeps reconnecting. Should I change the address to `0.0.0.0`?** `0.0.0.0` is a listen address, set on QueQiao's `websocket_server.host`. Under Docker with separate network stacks it needs changing; for a same-machine install no change is normally needed. See "Networking and addresses".

**Q: `mc cmd` returns nothing?** `mc cmd` depends on RCON: set `rcon.enable: true` with a password in QueQiao's `config.yml`, or enable the plugin's "direct RCON fallback".

**Q: Can `mc list` show player names without enabling RCON?** Yes — it falls back to the online query (SLP `players.sample`) when RCON is off; the list may be incomplete (Vanilla truncates it, anti-bot plugins may leave it empty or stuff it with fake names). For a 100% complete list you still need RCON. The output labels the source used.

**Q: Why am I not receiving death, achievement or command events?** These events are **unsupported on Vanilla and Velocity** servers; an upstream limitation.

**Q: Achievement messages only show "🏆 达成成就"?** Achievement text varies by QueQiao version and server type; the plugin falls back through `translation.text → text → display.title → key`. For localized names, enable translation on the QueQiao side (`enable_translation: true` + `translate/zh_cn.json`) — it is not a plugin setting.

**Q: My rented server cannot open a port.** Set `ws_mode` to `reverse`: the plugin listens and waits for QueQiao to connect; point QueQiao's `websocket_client.url_list` at the plugin.

**Q: How do I let in-game chat both reach the AI and sync to the group?** Set both prefixes, e.g. `*` for bridging and `ai` for the AI. Take care not to let one prefix contain the other.

### Credits

- [QueQiao](https://github.com/17TheWord/QueQiao) — Minecraft server connectivity

### License

[AGPL-3.0](LICENSE)
