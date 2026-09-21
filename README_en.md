<div align="center">
<h1>Minecraft Queqiao</h1>
<p><strong>Connect Minecraft servers to AstrBot via the QueQiao mod for message bridging, server management and AI chat</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-v0.3.1-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; QueQiao &nbsp;&nbsp; Message Bridge &nbsp;&nbsp; AI Chat</sub></p>
<p><a href="README.md">中文</a> &nbsp;/&nbsp; <strong>English</strong></p>
</div>

## Features

Connects Minecraft servers to AstrBot through the [QueQiao](https://github.com/17TheWord/QueQiao) mod, bridging group chat with in-game chat and providing server management. The transport layer uses the QueQiao V2 protocol.

- **Chat bridge**: two-way forwarding between Minecraft chat and other platforms
- **Image forwarding**: two-way image bridging — images from the group can be relayed into the game (rendered by the [ChatImage](https://github.com/kitUIN/ChatImage) mod), and in-game chat images (CICode / image links) can be downloaded and sent back to the group
- **Event broadcast**: player join / quit / death / achievement events forwarded to sessions
- **Server management**: status queries, online player list, remote command execution
- **AI chat**: talk to the AI in-game with its own prefix (`ai hello`); replies are sent privately and normal bridging is unaffected
- **Multiple servers**: connect several servers, each with independent forwarding settings
- **Flexible transport**: forward mode (plugin dials QueQiao) or reverse mode (QueQiao dials plugin, ideal for rented servers)

> QueQiao exposes **no player-detail query API**, so `mc player` relies on RCON.

## Commands

| Command | Permission | Description |
|---------|------------|-------------|
| `/mc help` | Everyone | Show help and custom command list |
| `/mc status` | Everyone | Show server status |
| `/mc list` | Everyone | Show online players |
| `/mc player <id>` | Everyone | Show player info (requires RCON) |
| `/mc cmd <command>` | Admin | Execute a server command, filtered by the allow/deny list |
| `/mc say <text>` | Admin | Broadcast a message in-game |
| `/mc bind <game_id>` | Everyone | Bind your game ID |
| `/mc unbind` | Everyone | Remove the binding |
| `/mc servers` | Everyone | List configured servers and connection state |

When a session is bound to several servers, a numbered list is shown; reply with a number to pick the target server.

### Custom commands

The `cmd.custom_cmd_list` option defines shortcuts using this syntax:

```
trigger <&param&><<>>actual command {param} {sender}
```

- Everything left of `<<>>` is the trigger template, right of it is the command to run
- `{sender}` is replaced with the sender's **bound game ID**
- `<&xxx&>` are positional placeholders, substituted by matching names on both sides

Example: `tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>`

If user A has bound the game ID `Misaka` and sends `tp 114 514 1919` in the group, the server actually runs `tp Misaka 114 514 1919`.

## Configuration

### Connection

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `target_sessions` | list | empty | **Target sessions**, shown at the very top of the list entry, right below "Enable this server". Session UMO list for MC messages; **defines the MC ↔ chat binding** — when empty the plugin connects but the group receives nothing |
| `server_id` | string | `Server` | Unique server ID, **must match QueQiao's `server_name`** |
| `server_name` | string | empty | **Display name** of the server, may be Chinese (e.g. `生存服`). When empty, the **display-name default** below is used. Display only, does not affect the connection |
| `server_name_default` | string | `MC` | **Display-name default**: what `{server}` and status output show when `server_name` is blank — with nothing filled in you get `[MC]<player>`. Clear it to render an empty string (no prefix) |
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
| `forward_chat_format` | string | `[{server}]{player}: {message}` | Chat format; `{player}` name, `{message}` content, `{server}` **server display name** (falls back to the default `MC` when unset) |
| `forward_join_leave_to_astrbot` | bool | `false` | Forward join/quit messages |
| `forward_death_to_astrbot` | bool | `false` | Forward death messages (unsupported on Vanilla/Velocity) |
| `forward_achievement_to_astrbot` | bool | `false` | Forward achievement messages (unsupported on Vanilla/Velocity) |
| `auto_forward_prefix` | string | empty | **Prefix for relaying group messages into MC**; empty relays all (only takes effect for bound target sessions) |
| `broadcast_format` | string | `[{platform}]{sender}: {message}` | Format used when relaying into the game; `{server}` display name (falls back to the default `MC` when unset), `{server_id}` raw server ID (always populated) |
| `platform_names` | list | `["aiocqhttp=QQ"]` | **Platform name mapping**: replace the raw platform name behind `{platform}` with a custom display name, one entry per line in the form `raw=display`. Ships with a default `aiocqhttp=QQ` entry (works out of the box); unmapped platforms keep their original name, clearing the list disables the rewrite |
| `broadcast_color` | string | `white` | Message color; MC color name or `#RRGGBB` |
| `mark_option` | string | `emoji` | Acknowledgement after a successful relay: `text` replies ✅ / `emoji` reacts to the original message / `none` silent |
| `mark_emoji_id` | int | `124` | **Reaction emoji ID** (only when `mark_option=emoji`). Default `124` is 👌; see the table below for verified IDs |
| `forward_image_to_mc` | bool | `false` | **Relay images into the game**: images in external messages are forwarded to MC automatically. **Requires the [ChatImage](https://github.com/kitUIN/ChatImage) mod on the game client** to render them — otherwise the `[[CICode,...]]` text is shown literally. Images are broadcast as messages carrying a URL that each player's client downloads, so the URL must be reachable from player clients (QQ image CDN URLs usually are) |
| `chatimage_name` | string | `图片` | **In-game image display name**: the name ChatImage shows in the chat bar for the image (the `name` argument of the CICode) |
| `forward_image_from_mc` | bool | `false` | **Relay in-game images to external sessions**: recognises ChatImage `[[CICode,url=...]]` codes or image links pasted in game chat, downloads them and sends them as image messages. On download failure (e.g. a `file://` local file not on this machine) the original text is kept |

> Get a session's UMO with **AstrBot's built-in `/sid` command**: send `/sid` in the target group/DM, and the `UMO` field in the reply is the value to fill in here; it looks like `aiocqhttp:GroupMessage:123456789`. This list drives three things at once: **which external sessions receive MC messages**, **which external sessions' messages are relayed into MC**, and **which server the `mc` commands issued in that session belong to**.

> **Reaction emoji**: `mark_option: emoji` adds a reaction to the **original message** that triggered the relay (no extra message is sent). **Every aiocqhttp protocol implementation supports it** (such as NapCat, Lagrange or LLOneBot); other platforms are skipped silently instead of failing.

`mark_emoji_id` takes a **QQ emoji ID** — note that this is neither a Unicode code point nor an OneBot standard index (e.g. ✅ has no QQ emoji ID). The built-in Emoji response constants of this plugin, all verified by testing:

| Constant | ID | Emoji |
|----------|----|-------|
| `EMOJI_OK_GESTURE` | `124` | 👌 |
| `EMOJI_THUMBS_UP` | `76` | 👍 |
| `EMOJI_LOVE` | `66` | ❤️ |
| `EMOJI_ROSE` | `63` | 🌹 |

</details>

### Relaying images into the game (ChatImage)

Want players to see images posted in the group right inside the game? Enable **`forward_image_to_mc`** per server to automatically relay images from external sessions into the game. The game client needs the [ChatImage](https://github.com/kitUIN/ChatImage) mod (Fabric / Forge / NeoForge), which renders recognised images straight into the chat bar:

```
[QQ]UserA: [[CICode,url=https://gchat.qpic.cn/...,name=图片]]
```

- **Off by default**: on servers without ChatImage, enabling it only shows `[[CICode,...]]` text, so only enable it where the mod is installed
- **URL reachability**: images are broadcast as a message carrying a URL that **each player's own client** downloads, so the URL must be reachable from the players' machines. QQ image CDN URLs (e.g. `gchat.qpic.cn`) are usually directly accessible; when the protocol side does not provide a public URL (the log says "图片均无可访问的公开 URL"), turn on the root-level **`enable_image_upload`** and add a **"Built-in image HTTP service"** entry (local fallback) or a **third-party image bed** entry in the **`image_upload_services`** list — see the two options below, or configure AstrBot's `callback_api_base` to use its file service
- **The relay prefix still applies**: when `auto_forward_prefix` is set, only images in messages that carry the prefix are relayed (a bare image message has no text, does not match the prefix, and is therefore not relayed)
- **Display name**: `chatimage_name` controls the name shown for the image in the chat bar; default `图片`

### Relaying in-game images to external sessions

Players paste images in the game (ChatImage's `[[CICode,url=...]]` codes, or image links typed straight into chat) and you want to see the actual image in the group instead of a long code/link? Enable **`forward_image_from_mc`** per server:

```
[MC]Steve: [[CICode,url=file:///D:/profile/Downloads/example.jpg]]
[MC]Steve: https://example.com/images/example.png
```

With it enabled, `http(s)://` links are **downloaded and sent to the group as images**; `file://` local links are only downloadable when AstrBot runs on the same machine as the game (otherwise the original text is kept). The original code/link is removed from the text; the rest is still relayed:

- **Two sources**: `http(s)://` links are downloaded directly; `file://` local files are only readable when **AstrBot runs on the same machine as the game side (or the file is otherwise visible to AstrBot)**, otherwise they are skipped
- **Failed downloads are not lost**: when an image fails to download (dead link, a `file://` file not on this machine, etc.), the original code/link text is kept
- **Size & timeout**: 5 MB per image, 15 s download timeout; oversized/timed-out images are skipped
- **Off by default**: enabling it downloads and re-sends images, so turn it on only where you want it

#### Built-in image HTTP service (fallback when no public URL)

Some protocol clients deliver images only as base64 / local files with no externally reachable URL. Add a **"Built-in image HTTP service"** entry (template `builtin_http`) in **`image_upload_services`** — the plugin then caches the image bytes in its built-in HTTP service and broadcasts `{base_url}/img/<token>` for player clients to load directly:

> Built-in entries do not go through any third party. **The prerequisite is that AstrBot has a publicly reachable address**

> Image bytes are cached in plugin memory for 30 minutes (up to 500 entries, expired/overflow entries are cleaned automatically); after expiry the in-game link stops working, which is expected.

#### Generic image bed (when there is no public URL and AstrBot cannot be reached by players)

Automatically **upload images without a public URL to an image bed** to get a publicly reachable link, then broadcast it into the game. As long as AstrBot can reach the internet and players can reach the internet, no direct connection to AstrBot is required:

1. Turn on the root-level switch **`enable_image_upload`** — built-in HTTP and third-party beds share this single switch and this single list, and can be mixed freely (**built-in first**)
2. Adjust **`image_upload_timeout`** (root-level, default `30` seconds) as needed: when one entry times out it is treated as a failure and the next entry in the list is tried; a timeout is reported explicitly as "上传超时（N 秒）" / "upload timed out (N s)" so you can decide between raising the timeout and switching to a faster bed. Non-positive values are clamped to 1 second and unparseable values fall back to the 30-second default
3. Add image beds in **`image_upload_services`** using the same "add entry" style as mc_servers. **No bed is loaded by default**: when adding an entry you pick a template — **"Custom" (自定义图床) is at the top** for freely filling in any bed's upload endpoint, followed by the pre-configured templates (endpoint and response mode pre-filled, just supply a token where needed — see the table below for all 12). In the picker and in the table below, **token-free templates come first and token-requiring ones at the bottom**. Each template **only shows the fields it needs**: the base fields are on every template:

| Entry field | Type | Default | Description |
|-------------|------|---------|-------------|
| `enabled` | bool | `true` | Enable this image bed entry |
| `name` | string | empty | Display name (logs/labels only; defaults to the address host) |
| `upload_url` | string | empty | **Full upload endpoint URL (not the site homepage)**, e.g. `https://img402.dev/api/free`, or Lsky Pro's `http://IP:7791/api/v1/upload` |
| `token` | string | empty | API token for beds that require auth (sent as `Authorization: Bearer <token>` header plus a form field `token`); leave empty for token-free beds |
| `response` | string | `text` | Response parsing: `text` = the response body itself is the image link (catbox, ...); `json` = the field named `url` in the JSON response (falling back to the first field shaped like `http(s)://`; imgloc, Lsky, sm.ms, pngurl, imglink, ...) |
| `file_field` | string | `file` | (some templates) **Multipart file field name**: most beds use `file`, a few use `image` (img402.dev) or `fileToUpload` (catbox family); the plugin sends the file under this field name |
| `headers` | string | empty | (some templates) **Custom request headers**: one `Name: Value` per line (or a JSON object like `{"X-Api-Key":"abc"}`); pngurl / picui pre-fill the required `Accept: application/json`, leave empty otherwise |
| `form_fields` | string | empty | (some templates) **Extra plain form fields**: one `Name: Value` per line (or a JSON object like `{"time":"72h"}`); litterbox requires `time` to set the retention period, and returns 500 without it |

**Upload protocol**: `POST <upload_url>` with a multipart file field named per the entry's `file_field` (default `file`; catbox.moe and litterbox.catbox.moe get an automatic compatibility shim: adds `reqtype=fileupload` + field `fileToUpload`); when `token` is set, both the `Authorization: Bearer <token>` header and a `token` form field are sent; any entry `headers` configured are sent as-is; any `form_fields` configured are sent as extra multipart fields.

- Pre-configured templates:

  <details>
  <summary>Show pre-configured templates</summary>

  | Template | Region | Token | Response | Size / quota | Notes |
  |----------|--------|-------|----------|--------------|-------|
  | `catbox` | overseas | no | `text` | ≤200MB per image | anonymous direct upload; depends on overseas network reachability |
  | `litterbox` | overseas | no | `text` | ≤1GB per image | catbox's temporary branch; images expire automatically (`form_fields` pre-filled with `time: 72h`; change it to 1h/12h/24h/72h); the upload endpoint is `/resources/internals/api.php` — the `/api/upload.php` path found in many blog posts already returns 404; measured upload time 1.6–3.1s |
  | `imglink` | overseas | no | `json` | ≤25MB per image | anonymous direct upload with no one-upload-per-30-minutes throttle; the server re-encodes the image, not suitable for archiving |
  | `img402.dev` | overseas | no | `json` | ≤10MB per image | file field is `image`; ≤1MB stored permanently, 1–10MB for 30 days; limited global daily quota (HTTP 429 means the cap is reached) |
  | `pngurl` | domestic | no | `json` | — | successor of pngcdn.cn; guest upload works without a token (the site admin may close guest uploads — register for a permanent token then); the template pre-fills the required `Accept: application/json` header |
  | `picui` | domestic | no | `json` | — | Lsky-style endpoint, guest upload works |
  | `anyapi` | domestic relay | no | `json` | suggested ≤10MB per file | anyapi relay proxy |
  | `xinyew` | domestic | no | `json` | — | 360 image bed, stored on 360 CDN; very small images may be rejected upstream |
  | `xunjinlu` | domestic | no | `json` | — | multi-endpoint aggregator that picks an upstream by file size (≤5MB random, 5–20MB stable, >20MB rejected) |
  | `imgloc` | domestic | yes | `json` | ~6MB per image | 路过图床; register at imgloc.com and get the API token from the "API settings" page; the domestic-first choice |
  | `see` | domestic | yes | `json` | ≤5MB per image | S.EE / sm.ms; file field is `smfile`; sm.ms has migrated to S.EE — the old `sm.ms/api/v2` endpoint returns a 308 redirect and no longer works; register at s.ee for an API key (User → Tools → API Keys), the template pre-fills the `Authorization: ` header prefix so you just paste the key |
  | `imgbb` | overseas | yes | `json` | ≤32MB per image | established API; file field is `image`; key registered for free at https://api.imgbb.com/ |

  </details>
- **Freely plug in your own image bed**: pick the Custom template, e.g. a self-hosted Lsky Pro with `upload_url=http://NAS:7791/api/v1/upload` + `response=json` + token; any endpoint that returns the link directly works with `response=text`; set `file_field` if the bed uses a non-`file` field, `headers` if it needs extra request headers, and `form_fields` if it needs extra plain form fields
- Multiple enabled entries are **tried in list order**; the first success is broadcast into the game; when all fail, the relay-skip warning aggregates each failure as `图床上传失败: catbox: Server disconnected；img402: HTTP 429 ...`
- On success the image is broadcast as `[[CICode,url=https://bed-domain/...,name=图片]]`; on failure it is skipped with a warning
- ⚠️ **Privacy notice**: group images are uploaded to the image bed — enable only when needed and avoid posting content that must not leave your chat

### Server display name and format placeholders

<details>
<summary>Show options</summary>

`server_id` is the **connection identity** used by QueQiao (bound to `x-self-name`, so it cannot be Chinese). To make multiple servers easier to tell apart in a group, set **`server_name` (display name)** as well — it only affects presentation and may be Chinese:

```jsonc
"server": {
  "server_id": "survival",       // must match QueQiao's config.yml server_name; don't change
  "server_name": "生存服",        // display only, may be Chinese
  "server_name_default": "MC"    // shown when server_name is blank; defaults to MC
}
```

Both format strings accept `{server}`, which resolves through the chain **`server_name` → `server_name_default` (default `MC`) → empty string**:

| Placeholder | Available in | Meaning |
|-------------|--------------|---------|
| `{player}` | `forward_chat_format` | Player name |
| `{message}` | both formats | Message content (rich text and color codes already stripped for MC → external) |
| `{server}` | both formats | **Server display name**; falls back to the **display-name default** (`MC`) when `server_name` is blank; renders empty only when both are cleared |
| `{platform}` | `broadcast_format` | Platform name; may be rewritten via **`platform_names`** to a custom display name (e.g. `aiocqhttp` → `QQ`); unmapped names are kept as-is |
| `{sender}` | `broadcast_format` | Sender name |
| `{server_id}` | `broadcast_format` | Raw server ID (**always populated**, when you need the exact identifier) |

Example (labelling the source when several servers share a group):

| Setting | Format | Result |
|---------|--------|--------|
| `server_name` = `生存服` | `[{server}] <{player}> {message}` | `[生存服] <Steve> 大家好` |
| nothing filled in | `[{server}] <{player}> {message}` | `[MC] <Steve> 大家好` (default `MC`) |
| default changed to `本服` | `[{server}]{player}: {message}` | `[本服]Steve: 大家好` |

`{platform}` can also be rewritten into something nicer via **`platform_names`** — raw platform IDs (such as `aiocqhttp`, `qq_official`) are often long and ugly inside the game. This option **ships with a default `aiocqhttp=QQ` entry**: with no configuration at all, `aiocqhttp` already renders as `QQ` in-game. Delete the entry if you do not want the rewrite:

| Setting | Result |
|---------|--------|
| `platform_names` = `aiocqhttp=QQ`, format `[{platform}]{sender}: {message}` | `[QQ]群友A: 你好` |
| same mapping plus `telegram=电报`, `discord=DC` | those platforms also show the mapped name; unmapped platforms keep their original name |

> The mapping is configured **per server** (in the "Message forwarding" section), so different servers may use different names. Matching is case-insensitive (platform IDs are lowercase, so a case typo still hits). Entries take the form `raw=display`; malformed entries (no `=`, empty key, empty value) are silently ignored; clearing the whole list disables the rewrite and restores the original platform name.

> **Empty behaviour**: when `server_name` is blank, the **display-name default** (`MC`) is used — leaving everything untouched yields `[MC]<player>`. To make `{server}` render an **empty string** (no prefix), clear `server_name_default` as well; literal brackets in the format string remain (`[{server}]<{player}> {message}` then yields `[]<Steve> 大家好`; drop the brackets for a clean look). Use `{server_id}` if you always want a value.

> Existing format strings without `{server}` keep working unchanged.

`/mc status` and `/mc list` label the server through the same chain (`server_name` → default → `server_id`), so multi-server setups are easier to read; the handshake and logs keep using `server_id`.

</details>

### AI chat

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable_ai_chat` | bool | `true` | Master switch for in-game AI chat |
| `ai_chat_prefix` | string | `ai` | **Trigger prefix**, e.g. `ai hello`. Empty disables the AI trigger |

> The trigger is **in-game chat** (`ai hello`), available on all server types (including Vanilla / Velocity).

#### How the two prefixes relate (important)

They act in different directions and are configured independently, but **a given message matches only one of them**:

| Prefix | Direction | Effect |
|--------|-----------|--------|
| `auto_forward_prefix` | group → MC | Group messages starting with it are relayed into the game |
| `ai_chat_prefix` | in-game → AI | In-game chat starting with it triggers the AI and is **not** relayed to the group |

An in-game message is handled in this order: if it matches `ai_chat_prefix` it goes to the AI (the reply is sent privately to that player); otherwise it is relayed to the group as a normal chat message.

With the defaults (bridging prefix empty = relay all, AI `ai`):

| In-game message | Result |
|-----------------|--------|
| `ai do some math` | Goes to the AI, replied privately |
| `AI hello` | Goes to the AI (prefix is case-insensitive) |
| `hello everyone` | Relayed to the group |
| `aim high` / `airport` | Relayed to the group (**no** false AI trigger) |

> **Matching rules**: a prefix ending in a letter or digit must be followed by a space or the end of the message, so `ai` will not misfire on words like `aim` or `airport`; letter matching is case-insensitive. Prefixes ending in a symbol (`*`, `!`) match literally and need no separator.

> ⚠️ Do not let the two prefixes contain one another (for example both set to `*`, or one being a prefix of the other), otherwise the routing of a message becomes ambiguous. The plugin detects this at startup and logs a warning.

> Leaving `ai_chat_prefix` empty does **not** make every message trigger the AI — doing so would feed all chat into the LLM, adding noise and cost. Empty simply disables the AI trigger; normal bridging is unaffected.

> A trigger with no content (e.g. just `ai`) sends no request to the LLM, avoiding pointless usage.

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

> ⚠️ Upgrading from an older version: RCON settings used to live in a nested `rcon_fallback` object (not editable in the WebUI). In the new version fill in the four fields above instead; the old `rcon_fallback` values remain effective until the config is first saved.

</details>

### Plugin options

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|--------|-------------|
| `enabled` | bool | `true` | Enable the plugin |
| `text2image` | bool | `true` | Render server info as an image, falling back to text |

</details>

### Reconnect

> Matching the WebUI layout, reconnect options live in their own group at the very bottom of each server entry.

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `reconnect_interval` | int | `5` | Reconnect delay in seconds, growing with each failed attempt, capped at 60s |
| `max_reconnect` | int | `0` | Max reconnect attempts; `0` means unlimited |
| `low_frequency_threshold` | int | `30` | **Failures after which low-frequency retries kick in**: once consecutive reconnect failures **exceed** this count, the delay stops growing and stays fixed at `low_frequency_interval`. Default `30` (normal backoff for the first 30, low-frequency from attempt 31 on); set `0` to disable low-frequency mode and always use backoff |
| `low_frequency_interval` | int | `300` | **Low-frequency retry delay (s)**: fixed wait once low-frequency mode is active. Default `300` (5 minutes); larger values give quieter retries (no busy polling during long outages) |

</details>

## Deployment and FAQ

### Installation

1. Place this plugin under AstrBot's `data/plugins/` directory and restart AstrBot
2. In the WebUI plugin config, click "Add MC server" and **fill in "Target sessions" (required)**
3. Make sure `server_id` exactly matches QueQiao's `server_name`

> **The defaults work out of the box for a same-machine setup**: when AstrBot and MC run on one machine, the connection settings (`ws_url` → `ws://127.0.0.1:8080/minecraft/ws`) already line up with QueQiao's default port, so **nothing needs changing** — just set "Target sessions" and you are done. For cross-machine or Docker setups, see the next section.

### Networking and addresses (Docker / same-machine setups)

Whether `host` should be `127.0.0.1` or `0.0.0.0` **depends on whether AstrBot and MC share a network stack** — not on the operating system. There is exactly one criterion: **can AstrBot reach the address QueQiao is listening on?**

| Scenario | QueQiao `websocket_server.host` | Plugin `ws_url` |
|----------|--------------------------------|-----------------|
| Windows / Linux, **both installed directly on one machine** (same network stack) | `127.0.0.1` (default, no change needed) | `ws://127.0.0.1:8080/minecraft/ws` |
| AstrBot and MC on **different machines** | that machine's reachable address (LAN IP or `0.0.0.0`) | `ws://<MC server IP>:8080/minecraft/ws` |
| AstrBot in Docker, MC on the host (or vice versa) | **`0.0.0.0`** | the host's reachable address |
| AstrBot and MC in separate containers | **`0.0.0.0`** | the MC container's published port or container name |

> In the table above, `127.0.0.1`, `8080` and `/minecraft/ws` are all **defaults and can be changed**: use whatever address fits your deployment (see the notes below), and set the port to match QueQiao's `websocket_server.port` — or the plugin's `reverse_port` in reverse mode. **Change one side and you must change the other to match.**

> **How to fill in `ws_url`: use the address at which the MC server is reachable *from the machine running AstrBot*.** On the same machine, use `127.0.0.1`. When AstrBot and MC are on different machines, **use the MC server's actual IP** (e.g. `ws://192.168.1.10:8080/minecraft/ws`) — `127.0.0.1` will not work there, because on AstrBot it means AstrBot itself.

> **`0.0.0.0` is a *listen* address meaning "all interfaces", and belongs only on the server side** (QueQiao's `websocket_server.host`, the plugin's `reverse_host`).

**Docker example** (AstrBot on the host network, MC inside a bridge container):

```yaml
# QueQiao config.yml inside the MC container — must listen on all interfaces,
# otherwise traffic from outside the container never arrives
websocket_server:
  host: "0.0.0.0"            # can be narrowed to a specific interface if needed
  port: 8080                 # default port, changeable (must match the ws_url below)
```

```
# AstrBot plugin config — AstrBot is on the host network, i.e. the host itself,
# so connect to the local machine via 127.0.0.1
ws_url: "ws://127.0.0.1:8080/minecraft/ws"   # port must match the port above
```

Troubleshooting notes:

- Success is logged as `已连接鹊桥 (ws://...)` ("connected to QueQiao"); a reachable TCP port alone does not mean the handshake succeeded
- If the log shows **continuous reconnects** with no explicit error, `host` is usually still `127.0.0.1`: the published port listens on the host, but QueQiao inside the container is bound only to the container's own loopback, so it never receives the docker-proxy traffic and the connection is reset immediately
- The startup line `WebSocket Server 在 <address>:<port> 启动...` tells you the actual address QueQiao bound to

### Configuring QueQiao

Install the [QueQiao](https://modrinth.com/plugin/queqiao) plugin/mod on your Minecraft server and configure `config.yml` as described in its [documentation](https://github.com/17TheWord/queqiao-docs):

```yaml
server_name: "Server"        # must match the plugin's server_id
access_token: ""             # matches the plugin's access_token
websocket_server:
  enable: true               # required for forward mode
  host: "127.0.0.1"          # for Docker and cross-network setups see "Networking and addresses" above
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

> Achievement name availability also depends on the server: on `Spigot` the achievement event contains **only `key`**, and `Forge 1.7.10` lacks `display.description`. The plugin falls back through `translation.text → text → display.title → key`, so a name or identifier always shows; enable translation on the QueQiao side for localized names — see the FAQ.

### Dependencies

- Python 3.10+
- AstrBot >= 4.10.4
- `websockets` (required to connect to QueQiao)
- `aio-mc-rcon` (only needed for the direct RCON fallback)

### FAQ

**Q: Connection fails with an auth error or 404?** Verify that `server_id` matches QueQiao's `server_name` exactly, including case, and that `access_token` is identical on both sides.

**Q: The plugin keeps reconnecting. Should I change the address to `0.0.0.0`?** `0.0.0.0` is a listen address, set on QueQiao's `websocket_server.host`. Under Docker, if AstrBot and MC are not on the same network stack, change it to `0.0.0.0`; for a Windows / Linux same-machine install no change is normally needed. See "Networking and addresses" above, and the MC server IP note there when the two are on different machines.

**Q: `mc cmd` and `mc list` return nothing?** Both depend on RCON. Set `rcon.enable: true` with a password in QueQiao's `config.yml`, or enable the plugin's "direct RCON fallback" and fill in the server's RCON details.

**Q: Why am I not receiving death, achievement or command events?** These events are **unsupported on Vanilla and Velocity** servers; this is an upstream limitation.

**Q: Achievement messages only show "🏆 达成成就", or do not appear at all?** The achievement field name and its availability vary by QueQiao version and server type. **Note that the field actually pushed is `translation`, contradicting the `translate` name used in QueQiao's docs**; the plugin accepts both.

The plugin falls back in four steps: `translation.text` → `text` → `display.title` → `key`. It normally shows at least the achievement name (e.g. `Hot Stuff`) or an identifier, and only degrades to `🏆 <player> 达成了成就` when everything is missing — a message is no longer dropped entirely.

To get localized achievement names you must enable translation **on the QueQiao side** (this is not a plugin setting): set `enable_translation: true` in `config.yml`, create a `translate/` folder next to it, and drop in `zh_cn.json` (extractable from the client jar). See the [QueQiao translation docs](https://github.com/17TheWord/queqiao-docs/blob/main/docs/config/translate.md). With translation disabled, `translation.text` may be an empty shell, in which case `display.title` covers it.

**Q: Messages in chat contain braces like `{"text":"Hello"}`?** On non-Vanilla servers `raw_message` is a text-component string. The plugin strips it; if you still see braces, please open an issue with your server type and version.

**Q: My rented server cannot open a port.** Set `ws_mode` to `reverse`. The plugin then listens and waits for QueQiao to connect; point QueQiao's `websocket_client.url_list` at the plugin.

**Q: Why does `mc player` say it needs RCON?** QueQiao offers no player-detail API, so this plugin can only obtain it through RCON `data get entity`. This is a known capability trade-off — see the note at the end of "Features".

**Q: How do I let in-game chat both reach the AI and sync to the group?** The two prefixes act independently in different directions — just set both, e.g. `*` for bridging and `ai` for the AI. Normal chat is bridged while `ai hello` goes to the AI. Take care not to let one prefix contain the other.

### Credits

- [QueQiao](https://github.com/17TheWord/QueQiao) — Minecraft server connectivity

### License

[AGPL-3.0](LICENSE)
