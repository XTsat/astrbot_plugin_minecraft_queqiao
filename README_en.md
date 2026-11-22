<div align="center">
<img src="logo.png" alt="Minecraft Queqiao" width="160" />
<h1>Minecraft Queqiao</h1>
<p><strong>Connect Minecraft servers to AstrBot via the QueQiao mod for message and image bridging, server management and AI chat</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-v0.9.1-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; QueQiao &nbsp;&nbsp; Message Bridge &nbsp;&nbsp; Image Bridge &nbsp;&nbsp; AI Chat</sub></p>
<p><a href="README.md">中文</a> &nbsp;/&nbsp; <strong>English</strong></p>
</div>

## Features

Connects Minecraft servers to AstrBot through the [QueQiao](https://github.com/17TheWord/QueQiao) mod, bridging group chat with in-game chat and providing server management.

- **Chat bridge**: two-way forwarding between in-game chat and group messages; replying to a game message forwarded by the bot automatically prepends `@原玩家名` (the original player name) in-game, so everyone sees who replied
- **Image forwarding**: group images relayed into the game (players need the [ChatImage](https://github.com/kitUIN/ChatImage) mod installed to render them); in-game images / links are downloaded and sent back to the group
- **Event broadcast**: player join / quit / death / achievement events forwarded to sessions (death & achievements unsupported on Vanilla/Velocity)
- **Quiet hours**: give each server a silent window (e.g. `23:00`–`08:00`) that mutes the game message types and connection notices you pick, so nothing pings the group overnight
- **Server management**: status queries, online player list, remote command execution
- **Web dashboard**: configure servers, check status and performance (TPS / latency), read the bridge terminal and manage image beds right in the panel — no config-file editing needed (see “What the dashboard can do”)
- **AI chat**: talk to the AI in-game with the `#` prefix and get replies privately; it remembers the conversation (scoped per server, per target group or per player), and `#new` / `#reset` work like AstrBot's own commands
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

### Full config editor (“📝 配置” at the top right)

The standalone config page is folded into the dashboard: click “📝 配置” to switch the page into a full config view where every field (MC servers, image transfer, forwarding and sessions) can be edited from the plugin config template, or switch to JSON mode to edit it directly. “💾 保存并重载” backs up first, writes atomically and hot-reloads, then refreshes the monitoring panel; “📊 返回监控” returns to monitoring.

### What the dashboard can do

The dashboard (plugin Pages) handles almost all day-to-day work — no more hand-editing the config file:

**Server entries**: click “＋ 新建服务器” and fill in the server name (must match `server_name` in QueQiao's `config.yml`), display name, transport and address, token and target sessions; the remaining fields are filled from the config template. Disabled servers stay on the panel as grey cards — click one to enable it, and a running server can be paused. An entry with an empty or duplicate server name is skipped and shown as a grey “未生效” card so the problem is easy to spot. Every save backs up the previous config first, then writes it and hot-reloads (old connections are dropped and rebuilt).

**🖼️ Image-bed tab** (right end of the server-tab bar; entering it hides the stat cards and server cards): the master switch and upload timeout sit at the top; each image bed is a card you can create, edit or delete (deletion asks for confirmation), with “⬆ 上移 / ⬇ 下移” setting the order in which beds are tried from top to bottom. `builtin_http` entries also show a running / not-running badge. “🧪 测试上传” pushes a built-in PNG probe through the whole chain and reads the hosted image back to verify its real format: 🟢 pass (ChatImage can render it), 🟡 usable but limited (the bed re-encoded to webp, so it uploads but shows nothing in game), 🔴 failed (listed as “image-bed name: reason”). Saving only rebuilds the image-transfer subsystem, never MC connections, and it works even with no server configured.

**⚙ Feature-settings drawer** (right side; its collapsed state is remembered by the backend across devices, and it is hidden in the all-servers view): everything not monitoring-related — trigger prefixes (one checkbox row enables the three directions; an empty prefix matches everything), message forwarding (per-event toggles, chat format, group→MC prefix and target sessions), connection notifications (independent switches and templates), and how many days of terminal logs to load. Saving writes the plugin config and takes effect immediately without rebuilding connections; these are the same settings as the config tables below. Monitoring parameters themselves still live in the “⚙ 设置” dialog of the monitoring panel.

### Auto-refresh interval

The seconds box right of the “自动刷新” toggle is editable in place — type a value, then blur or press Enter to apply (10–3600 s), no dialog needed. While the toggle is on, the dashboard reloads at that interval. It is a global preference, independent of any single server. Refreshing or reopening the page keeps the last opened server tab instead of returning to “全部服务器”.

### Connection

Set these two first; the rest can stay at their defaults:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Target sessions | list | empty | **Required.** Session UMO list for MC messages; defines the MC ↔ chat binding — when empty the group receives nothing |
| Server name | string | `Server` | **Required.** Unique identifier, must match QueQiao's `server_name`; must differ across servers |

<details>
<summary>Other connection options (9 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Server display name | string | empty | Display name (may be Chinese, e.g. `生存服`), display only; falls back to `display_name_default` when blank |
| Default display name | string | `MC` | Display-name default: what `{display_name}` and status output show when `display_name` is blank |
| Transport mode | string | `forward` | `forward`: plugin dials QueQiao; `reverse`: plugin listens for QueQiao |
| QueQiao WebSocket URL | string | `ws://127.0.0.1:8080/minecraft/ws` | Forward-mode URL, matches QueQiao `websocket_server` |
| Reverse listen address | string | `0.0.0.0` | Reverse-mode listen address |
| Reverse listen port | int | `8080` | Reverse-mode listen port |
| Reverse listen path | string | `/minecraft/ws` | Reverse-mode listen path |
| Auth token | string | empty | Matches QueQiao `access_token`; empty disables auth |
| Client origin tag | string | `astrbot` | Sent as `x-client-origin`; leave unchanged unless needed |

</details>

### Message forwarding

<details>
<summary>Message forwarding (20 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Relay all in-game chat | bool | `true` | Relay all in-game chat to target sessions; when off, only chat matching `forward_chat_prefix` is relayed (an empty prefix still relays everything), image forwarding ignores the text prefix |
| Game → group trigger prefix | string | empty | Game → group trigger prefix: only chat starting with it is relayed to the group (prefix removed); empty relays everything |
| Chat message format | string | `[{display_name}]{player}: {message}` | Chat format; supports `{player}` `{message}` `{display_name}` |
| Forward join/leave | bool | `false` | Forward join/quit messages (server display name appended, so the source is clear when several servers share a group) |
| Forward deaths | bool | `false` | Forward death messages (unsupported on Vanilla/Velocity) |
| Forward achievements | bool | `false` | Forward achievement messages (unsupported on Vanilla/Velocity) |
| Local translation | bool | `false` | Translate death / achievement text to Chinese using the plugin's bundled data — no server-side translation needed |
| Group → MC trigger prefix | string | empty | Group messages starting with it are relayed into the game; empty relays all |
| Forward the bot's own messages | bool | `false` | Relay the bot's own messages without stripping wake prefixes: wake messages use their original text (including the `@bot` OneBot omits), and bot self-messages in groups are relayed too. Images reuse `forward_image_to_mc`; `[图片]` is used when no reachable image URL exists, faces are recorded as `[表情:id]` |
| External → MC message format | string | `[{platform}]{sender}: {message}` | Format used when relaying into the game; supports `{platform}` `{sender}` `{message}` `{display_name}` `{server_name}` |
| Platform name mapping | list | `["aiocqhttp=QQ"]` | Platform name mapping: `raw=display`, e.g. `aiocqhttp=QQ` |
| Relayed message colour | string | `white` | Message color; MC color name or `#RRGGBB` |
| Delivery acknowledgement | string | `emoji` | Acknowledgement after a successful relay: `text` replies ✅ / `emoji` reacts to the original message / `none` silent |
| Reaction emoji ID | int | `124` | QQ emoji ID; `124` = 👌 (other common ones: `76` 👍, `66` ❤️, `63` 🌹) |
| Forward images into the game | bool | `false` | Relay group images and enabled bot reply/self-message images into the game (requires ChatImage on the client to render; otherwise the CICode text is shown) |
| In-game image label | string | `图片` | In-game display name for the image |
| Forward in-game images out | bool | `false` | In-game images (CICode / links) downloaded and sent back as images |
| In-game image mode | string | `chatimage` | Game image mode: `chatimage` only understands ChatImage codes and links; `e33chat` additionally understands E33Chat image tags and server media |
| E33Chat media cache dir | string | empty | E33Chat server image cache directory; only needed in `e33chat` mode when relaying server-media images, and AstrBot must be able to read the path directly |
| E33Chat image max edge | int | `320` | Max edge length (px) for group images sent into the game in E33Chat mode; larger images are scaled down |

> Get a session's UMO with **AstrBot's built-in `/sid` command**: send `/sid` in the target group/DM, and the `UMO` field in the reply is the value to fill in (e.g. `aiocqhttp:GroupMessage:123456789`). This list drives three things at once: which sessions receive MC messages, which sessions' messages are relayed into MC, and which server the `mc` commands issued in that session belong to.

> `mark_option: emoji` adds a reaction to the **original message** that triggered the relay (no extra message is sent); every aiocqhttp protocol implementation (NapCat, Lagrange, LLOneBot, etc.) supports it, other platforms are skipped silently.

</details>

### Server-connection notification

<details>
<summary>Server-connection notification (6 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Notify on connect | bool | `false` | Send a “server started” notice to the target sessions once the server connects; only sent when the server really started, so a brief connection hiccup no longer raises a false alarm (see below) |
| Connect notice format | string | `[{display_name}] 🟢 服务器已启动` | Multiline notice template; supports the `{display_name}` and `{server_name}` placeholders; empty uses the default template |
| Notify on connect failure | bool | `false` | Send a “connection failed” notice to the target sessions when the first connection attempt fails or an established connection drops; the outage must last longer than the quiet period below, only the first failure of an outage is sent, and the next outage notifies again after a successful reconnect |
| Connect-failure notice format | string | `[{display_name}] 🔴 服务器连接失败` | Multiline failure notice template; supports the `{display_name}` and `{server_name}` placeholders; empty uses the default template |
| Disconnect quiet period (s) | int | `60` | Disconnect quiet period in seconds (`0`–`3600`): the failure notice is sent only when the outage outlasts it, and a reconnect within it stays silent; `0` notifies immediately |
| Server status probe address | string | empty | Server status probe address (e.g. `127.0.0.1:25565`; the port defaults to `25565`): while the bridge is down the plugin uses it to tell whether the server really stopped; empty falls back to outage length (a “server started” notice needs an outage longer than 30 seconds) |

</details>

Both notice types go only to that server's **target sessions**; nothing is sent when no target session is configured. Only `{display_name}` (server display name) and `{server_name}` (server name) are replaced — any other braces are kept verbatim. An empty template falls back to the default wording.

**Connect notice (“server started”)**

A “server started” notice is sent when the server connects — but **only when it really restarted**. Network hiccups, server lag and plugin reloads should not make you think the server rebooted. How it decides:

- **With a “server status probe address”**: while the bridge is down the plugin probes that address. If the server still answers, only the WebSocket died (no notice); if it does not answer, the server really stopped and the notice goes out once it recovers. This is the most accurate way — fill it in if you can.
- **Without a probe address**: only the outage length is available. A reconnect after more than **30 seconds** counts as a restart and sends the notice; hiccups that heal within seconds stay silent.

**Connect-failure notice**

Covers two cases: the server was never reachable (it is down), and an established connection dropped. To avoid flooding the chat, **only the first message per outage** (from disconnect until a successful reconnect) is sent; retries do not repeat it. Once the connection is re-established, the next outage notifies again.

The notice also waits out the “disconnect quiet period” (60 seconds by default): a reconnect within it sends nothing at all, and the notice only goes out when the outage outlasts it. Set it to `0` to be told the moment the connection drops. In reverse mode the failure notice is only sent when an **established** connection drops (waiting for QueQiao to dial in does not count).

> You can enable either one or both. To hear only about servers that actually went down, enable “connect-failure notice”; add the connect notice as well if you also want to know when they come back.

### Quiet hours

When you would rather not have the group pinged by game activity overnight, give each server its own silent window (for example `23:00` – `08:00`). Inside the window only the message types you tick are muted.

<details>
<summary>Quiet hours (4 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Enable quiet hours | bool | `false` | Enable the quiet window; off by default |
| Quiet hours start | string | `23:00` | Start time (AstrBot local time, `HH:MM`); equal start and end means “not configured” |
| Quiet hours end | string | `08:00` | End time (AstrBot local time, `HH:MM`); an end earlier than the start wraps past midnight |
| Muted event types | list | death/achievement/connect/failure notices | Which types are muted (checkbox multi-select): `chat` game chat, `join_leave` player join/quit, `death` death messages, `achievement` achievements, `connect` connection notices, `connect_fail` failure notices |

</details>

- Both the dashboard's “功能设置 → 🌙 免打扰” panel and the AstrBot plugin config page let you toggle it, pick the window and tick the types; saving takes effect immediately without reconnecting

### Relaying images into the game (ChatImage)

With `forward_image_to_mc` enabled, images in group messages and enabled bot pipeline/self-messages are broadcast as messages carrying a URL, which each player's client downloads and renders:

```
[QQ]UserA: [[CICode,url=https://example.com/images/example.png,name=图片]]
```

- Only enable it on servers where players have the [ChatImage](https://github.com/kitUIN/ChatImage) mod (Fabric / Forge / NeoForge) installed — otherwise only the `[[CICode,...]]` text is shown
- The image URL must be reachable from player clients; when an image has no public URL (the log says "图片均无可访问的公开 URL"), turn on `image_upload.enabled` and configure `image_upload.services` (see below)
- When `auto_forward_prefix` is set, only images in messages carrying the prefix are relayed (a bare image message has no text and never matches the prefix)

### Relaying in-game images to external sessions

With `forward_image_from_mc` enabled, ChatImage `[[CICode,url=...]]` codes or image links in game chat are downloaded and sent to the group as images:

- `http(s)://` links are downloaded directly; `file://` local files are only readable when AstrBot runs on the same machine as the game
- On download failure (dead link, invisible local file, etc.) the original code/link text is kept
- 5 MB per image, 15 s download timeout

#### E33Chat support

E33Chat is a separate chat mod ([NereaFantasia/E33Chat](https://github.com/NereaFantasia/E33Chat)) that represents images with tags in chat. Setting the game image mode (`mc_image_mode`) to `e33chat` makes the plugin understand these tags:

| Tag | Meaning |
|---|---|
| `[[E33Emote,url=...]]` | E33Chat's own emote / image tag |
| `[[ChatUpgrade,url=...,type=image]]` | Third-party rich-message tag (ignored when `type` is not image) |
| `e33chat://media/<32 hex chars>` | Image hosted by the E33Chat server |

- **Game → group**: all of the above are recognised, downloaded and sent to the group; `http(s)` links are downloaded directly
- **Group → game**: the image is written into the E33Chat server media directory and sent into the game as `[[CICode,url=e33chat://media/<ID>]]` (CICode is understood by every E33Chat version)
- **Server media directory** (`e33chat_media_dir`): E33Chat server media has **no HTTP endpoint** — the image sits on the server's disk, so AstrBot must be able to read that directory directly (a plain path when co-located; a shared mount when on separate machines). When left **empty**, only third-party image-bed links work, and server-media images are skipped with a single log hint
- **Prefer not to set up a shared directory?** Turn off server media hosting in the E33Chat client and it falls back to a third-party host (uguu.se by default), emitting a public link the plugin can read with no extra configuration
- E33Chat renders images at their native pixel size, so group images are scaled to a 320px longest edge by default (`e33chat_image_max_edge`, adjustable 64–2048) to avoid filling the chat panel

> Older E33Chat (≤2.3.9) does not render images itself — they are still displayed by ChatImage, so keep the default `chatimage` mode there.

#### Built-in image HTTP service

Some protocol clients deliver images only as base64 / local files with no externally reachable URL. Add a **"Built-in image HTTP service"** entry (template `builtin_http`) in `image_upload.services` — the plugin caches the image bytes in its built-in HTTP service and broadcasts `{base_url}/img/<token>` for player clients to load. **The prerequisite is that AstrBot has a publicly reachable address** that player clients can reach. The entry can be maintained from the dashboard's “🖼️ 图床” panel — no config file editing needed.

#### Generic image bed

Automatically upload images without a public URL to an image bed to get a publicly reachable link, then broadcast it into the game.

In the dashboard's “🖼️ 图床” panel: turn the master switch on and adjust the upload timeout at the top; when creating an entry you can pick the **built-in HTTP service**, the **“Custom”** template (any upload endpoint), or a pre-configured template (endpoint and response mode pre-filled, just supply a token where needed); “🧪 Test upload” verifies the configuration right away. No image bed entry is loaded by default.

| Entry field | Type | Default | Description |
|-------------|------|---------|-------------|
| Enable | bool | `true` | Enable this image bed entry |
| Display name (optional) | string | empty | Display name (logs/labels only) |
| Upload endpoint URL | string | empty | **Full upload endpoint URL (not the site homepage)** |
| Auth token (optional) | string | empty | API token (sent as `Authorization: Bearer <token>` header plus a `token` form field; imgbb is the exception and receives it as the `key` form field); leave empty for token-free beds |
| Response parsing | string | `text` | Response parsing: `text` = the response body is the link; `json` = the `url` field (falling back to the first `http(s)://` field) |
| Upload file field | string | `file` | Multipart file field name (`image` for img402 / imgbb, `smfile` for S.EE) |
| Custom request headers | string | empty | Custom request headers: one `Name: Value` per line (or a JSON object) |
| Extra form fields | string | empty | Extra plain form fields: one `Name: Value` per line (or a JSON object) |

Pre-configured templates:

<details>
<summary>Pre-configured image-bed templates (6 items)</summary>

| Template | Region | Token | Response | Size / quota | Notes |
|----------|--------|-------|----------|--------------|-------|
| imglink | overseas | no | `json` | ≤25MB per image | anonymous direct upload; the server re-encodes images and can be slow |
| img402.dev | overseas | no | `json` | ≤10MB per image | file field is `image`; ≤1MB stored permanently, 1–10MB for 30 days; behind Cloudflare, occasional timeouts |
| pngurl | domestic | no | `json` | — | successor of pngcdn.cn; guest uploads are rate-limited, register and supply a token for regular use |
| anyapi | domestic relay | no | `json` | suggested ≤10MB per file | anyapi relay proxy |
| see | domestic | yes | `json` | ≤5MB per image | S.EE / sm.ms; file field is `smfile`, put the key in the request header |
| imgbb | overseas | yes | `json` | ≤32MB per image | established API; file field is `image`, key submitted as the `key` form field |

</details>

- The table lists only templates verified to work; for any other image bed, use the `custom` template and fill in the endpoint yourself
- Multiple enabled entries are **tried in list order** (use the “⬆ 上移 / ⬇ 下移” buttons in the panel to change which one comes first); the first success is broadcast into the game; when all fail, a warning aggregates each failure as `name: reason`
- ⚠️ **Privacy notice**: group images are uploaded to the image bed — enable only when needed
- ⚠️ **webp images may not show up**: rendering in game depends on ChatImage, which only supports png / jpg / jpeg / jfif / gif / ico / bmp and **does not support webp**. Images in chat are mostly png / jpg, but some image beds re-encode everything they host to webp; when the resulting link is webp the chat bar shows no picture (only the code text). “🧪 Test upload” sends a single PNG and reads the hosted image back to check its format: png / jpg and friends turn it green, while a product that became webp turns it yellow. A yellow result means the image bed re-encodes images to webp — switch to one that stores images as-is (such as `pngurl` or `img402.dev`)
- “🧪 Test upload” results are colour-coded: 🟢 **green** = pass (the produced format can be rendered by ChatImage), 🟡 **yellow** = usable but limited (the bed re-encoded to webp, so it uploads but nothing shows in game), 🔴 **red** = failed (listed as “image-bed name: reason”) — configuration problems are identified in one step

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

<details>
<summary>Placeholder reference (6 items)</summary>

| Placeholder | Available in | Meaning |
|-------------|--------------|---------|
| `{player}` | `forward_chat_format` | Player name |
| `{message}` | both formats | Message content |
| `{display_name}` | both formats, `notify_on_connect_format`, `notify_on_connect_fail_format` | Server display name; falls back to `display_name_default` (`MC`) when blank, renders empty only when both are cleared |
| `{platform}` | `broadcast_format` | Platform name (may be rewritten via `platform_names`, e.g. `aiocqhttp` → `QQ`) |
| `{sender}` | `broadcast_format` | Sender name |
| `{server_name}` | `broadcast_format`, `notify_on_connect_format`, `notify_on_connect_fail_format` | Server name (always populated) |

</details>

Example: `display_name` = `生存服`, format `[{display_name}] <{player}> {message}` → `[生存服] <Steve> 大家好`; with nothing filled in → `[MC] <Steve> 大家好`.

> Join/quit pushes, `mc status` and `mc list` titles use the same chain (`display_name` → `display_name_default` → `server_name`); the handshake and logs keep using `server_name`.

### AI chat

<details>
<summary>AI chat (11 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Enable in-game AI | bool | `true` | Master switch for in-game AI chat |
| Game → AI trigger prefix | string | `#` | Game → AI trigger prefix: in-game chat like `#hello` goes to the AI, replied privately; empty triggers on everything (all in-game chat goes to the AI) |
| AI context scope | string | `server` | Where the AI keeps its context: `server` one per server (independent) / `group` shared with the target group (so `/new` in that group resets the in-game chat too) / `player` one per player (no cross-talk on a shared server) |
| AI context turns | int | `20` | How many turns to remember (one question + one answer is a turn); `0` = unlimited. Larger is more coherent but costs more tokens per request |
| New-conversation word | string | `new` | New-conversation word: an in-game message that, after the AI prefix, equals this word exactly starts a new conversation (same as `/new`); empty = disabled |
| Clear-history word | string | `reset` | Clear-history word: an in-game message that, after the AI prefix, equals this word exactly clears the current history (same as `/reset`); empty = disabled |
| AI persona | string | empty | AI persona: pick one of the existing AstrBot personas and the in-game AI uses its prompt; empty = follow the session's persona settings |

> **In-game AI now remembers context.** `ai_session_mode` decides which session the history lives on. `server` (the default) keeps every server separate and unaffected by `/new` in a group; `group` shares one history with the target group, so sending `/new` there also starts a fresh in-game conversation; `player` keeps one history per player so people on the same server do not bleed into each other. The default reset words are `#new` (start a new conversation) and `#reset` (clear the current history), matching AstrBot's own commands; Both words are configured independently and can be anything (e.g. `newchat`); they only appear in the plugin config page, not in the dashboard drawer.

> **Heads-up on “isolated sessions”**: if AstrBot's platform setting **unique_session** is on, group messages get a per-member session id (`{sender}_{group}`) that no longer matches the group UMO you put in Target Sessions. The `group` mode still reads and writes the UMO you configured rather than one per member; use `player` mode for per-player isolation, or turn unique_session off.

The three prefixes act in different directions and are configured independently; a given in-game message matches only one of them:

Each direction has one switch and one prefix: **the switch is the master gate, the prefix only filters messages**. With the switch off the whole direction is silenced and the prefix has no effect no matter how wide it is.

| Setting | Direction | Effect |
|---------|-----------|--------|
| Enabled directions | all three | Checkbox group: only ticked directions are active; unticking one silences that whole direction. The config page and the dashboard share this single switch |

| Prefix | Direction | Effect |
|--------|-----------|--------|
| Group → game switch | group → game | Group messages starting with it are relayed into the game; empty = all are relayed |
| Game → group switch | game → group | Only in-game chat starting with it is relayed to the group (prefix removed); empty = everything is relayed; image forwarding ignores this prefix |
| Game → AI switch | game → AI | In-game chat starting with it triggers the AI and is **not** relayed to the group; empty = everything triggers (all in-game chat goes to the AI) |

> All three prefixes share one rule: **empty means "match everything"** (no threshold is applied in that direction). Matching does word-boundary checks: a prefix ending in a letter/digit must be followed by a space or the end of the message, so `ai` will not misfire on `aim`/`airport`; letter matching is case-insensitive. Do not let `forward_chat_prefix` and `ai_chat_prefix` contain one another, or a message's routing becomes ambiguous (a startup warning is logged). Leaving `ai_chat_prefix` empty means every in-game message triggers the AI, so nothing is forwarded to the group.

</details>

### Commands

<details>
<summary>Commands (9 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Enable | bool | `true` | Enable remote command execution |
| Command list mode | string | `white` | `white`: only listed; `black`: all but listed; `none`: unrestricted |
| Allowed commands | list | `["say","list","weather","time"]` | Command names without the leading `/` |
| Enable account binding | bool | `true` | Enable account ↔ game ID binding |
| Custom command mappings | list | empty | Custom command mappings, see above |
| Enable direct RCON fallback | bool | `false` | Connect to RCON directly when QueQiao's RCON is unavailable |
| RCON host | string | `localhost` | RCON host |
| RCON port | int | `25575` | RCON port |
| RCON password | string | empty | RCON password |

> ⚠️ The old `rcon_fallback` config is deprecated — fill in the four fields above instead.

</details>

### Plugin options

<details>
<summary>Plugin options (2 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Enable | bool | `true` | Enable the plugin |
| Render server info as image | bool | `true` | Render server info as an image, falling back to text |

</details>

### Reconnect

<details>
<summary>Reconnect (4 items)</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Reconnect interval (s) | int | `5` | Reconnect delay in seconds, growing with each failed attempt, capped at 60s |
| Max reconnect attempts | int | `0` | Max reconnect attempts; `0` means unlimited |
| Low-frequency retry threshold | int | `30` | Once consecutive failures **exceed** this count, retries switch to a fixed `low_frequency_interval`; `0` disables low-frequency mode |
| Low-frequency retry interval | int | `300` | Low-frequency retry delay (s), default 5 minutes |

</details>

### Performance Monitoring

TPS and latency monitoring are **enabled by default, zero-config**: a background task periodically samples and persists the data; the dashboard's "Performance Monitoring" panel shows trend charts and summaries, with parameters adjusted in the panel's "⚙ Settings" (taking effect immediately on save).

<details>
<summary>Monitoring parameters (5 items)</summary>

| Parameter | Default | Description |
|-----------|---------|-------------|
| Enable switch | `on` | Stops sampling when off |
| Sample interval | `60` s | Minimum `10` s |
| Retention | `7` days | Older samples pruned automatically |
| TPS command | `auto` | Auto-picks by server type (Forge → `forge tps`; NeoForge → `neoforge tps`, falling back to `forge tps`; Fabric/Quilt → `spark tps`; Paper/Spigot → `tps`). If the type cannot be identified, common commands are tried in order and the first working one is remembered; it may also be pinned manually |
| Latency domain | empty | Public address of the MC server (may include a port, e.g. `mc.example.com:25565`) for player-perspective latency; empty disables latency probing |

</details>

- **TPS**: parsed from a TPS command executed over RCON — the server must support the command (Vanilla reports it as unavailable); Forge/NeoForge output a single average TPS, so the panel shows one value (Bukkit forks / Spark still show the 1m/5m/15m windows)
- **Latency**: direct-connect Minecraft SLP ping (no QueQiao relay, no RCON) — a public probe address must be filled in Settings; servers with SLP disabled or unreachable addresses report latency as unavailable
- Samples are persisted per day and survive restarts; `/mc status` also shows the latest samples

## Deployment and FAQ

### Prerequisites

- **Minecraft server**: install the [QueQiao mod](https://github.com/17TheWord/QueQiao) first — this plugin only covers the AstrBot side, so nothing connects without it
- **AstrBot**: just install this plugin; its dependencies are installed automatically

Then click "+ New server" in the dashboard. **Target sessions** is required, and `server_name` must match QueQiao's `server_name`. When AstrBot and MC run on one machine the connection settings already line up with QueQiao's default port, so nothing else needs changing.

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
# These must line up with this plugin's own settings
server_name: "Server"        # must match the plugin's "Server name"
access_token: ""             # matches the plugin's "Auth token"; empty disables auth

websocket_server:            # forward mode (plugin dials QueQiao)
  enable: true
  host: "127.0.0.1"          # for Docker and cross-network setups see above
  port: 8080

rcon:
  enable: true               # false by default upstream; mc cmd / mc list need it
  password: "your_password"  # must match rcon.password in server.properties

subscribe_event:             # enable the events you need; off means no event
  player_chat: true
  player_join: true
  player_quit: true
  player_death: true
  player_command: true
  player_advancement: true
```

For reverse mode use `websocket_client` instead (`enable: true` plus the plugin's address in `url_list`) and turn `websocket_server` off. Leave the remaining fields (`debug`, `message_prefix`, `enable_translation`, `ignored_commands`, …) at their defaults — see the [QueQiao docs](https://queqiao-docs.pages.dev/config/) for the full reference.

### Compatibility

<details>
<summary>Minimum QueQiao version (4 items)</summary>

| Capability | Minimum QueQiao version |
|------------|-------------------------|
| API V2 (broadcast / private message / title / action bar / RCON) | v0.2.11 |
| Event V2 | v0.3.0 |
| Translate model for death and achievement text | v0.4.1 |
| Server status via `mc status` | v0.5.0 |

</details>

### FAQ

**Q: Connection fails with an auth error or 404?** Verify that `server_name` matches QueQiao's exactly, including case, and that `access_token` is identical on both sides.

**Q: `mc cmd` returns nothing?** It depends on RCON: set `rcon.enable: true` with a password in QueQiao's `config.yml`, or enable the plugin's "direct RCON fallback".

**Q: Can `mc list` show player names without enabling RCON?** Yes — it falls back to the online query (SLP `players.sample`) when RCON is off; the list may be incomplete (Vanilla truncates it, anti-bot plugins may leave it empty or stuff it with fake names). For a complete list you still need RCON; the output labels the source used.

**Q: Achievement messages only show "🏆 达成成就"?** Turn on the plugin's own "本地翻译" option (`enable_local_translation`): it ships its own translation data under `translations/` and resolves the Chinese name by trying the achievement key, then the exact English name, then the original text — **no server-side translation needed**. Only when it is off does the plugin fall back to whatever the server sent, which on Vanilla may be just the achievement key.

### Credits

- [QueQiao](https://github.com/17TheWord/QueQiao) — Minecraft server connectivity
