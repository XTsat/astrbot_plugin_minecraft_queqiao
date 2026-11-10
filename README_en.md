<div align="center">
<h1>Minecraft Queqiao</h1>
<p><strong>Connect Minecraft servers to AstrBot via the QueQiao mod for message and image bridging, server management and AI chat</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-v0.7.2-blue"></p>
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
- **Web Dashboard**: view server status, performance monitoring (TPS / latency), the bridge terminal in real time and connection observability (reconnect count / phase / limit alert, API timeout count), with quick broadcast and command console
- **Image-bed panel**: a dedicated “🖼️ 图床” tab at the right end of the dashboard's server-tab bar to manage image transfer directly — the master switch, upload timeout, full add/edit/delete and reordering of image bed entries, the built-in HTTP service runtime state, and a one-click test upload that runs the whole chain with built-in probe images and colour-codes the result (green / yellow / red) by ChatImage compatibility
- **Manage servers from the panel**: create servers, enable / disable, edit connection settings and target sessions, or delete entries right from the dashboard; disabled servers stay visible as grey cards and can be enabled with one click — saving backs up the config and hot-reloads automatically
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

### Managing servers from the panel

The dashboard (plugin Pages) manages the servers in your config directly — no more hand-editing the config file:

- **Create a server**: click “＋ 新建服务器” in the section header or the placeholder card in the grid, then fill in the server name (must match `server_name` in QueQiao's `config.yml`), display name, transport and address, token and target sessions. Remaining fields are filled from the config template, so the entry is identical to one added in the WebUI
- **Enable / disable**: a disabled server **does not disappear** — it stays on the panel as a grey card with a dashed border; click the card or its “▶ 启用” button to enable it, and a running server can be paused with “⏸ 停用”
- **Edit / delete**: click a grey card to open the form and change the server name, display name, transport (forward / reverse) and address, token (leave empty to keep the current one) or target sessions (one per line), or delete the entry
- **Inactive entries stay visible**: an entry with an empty or duplicate server name is skipped by the main flow; it is shown as a grey “未生效” card so the problem is easy to spot
- Every save backs up the previous config to `data_dir/conf_backups/`, writes it atomically and **hot-reloads** (old connections are dropped and rebuilt from the new config); a failure never corrupts the in-memory config

### Dashboard image-bed panel

The dashboard has a dedicated “🖼️ 图床” (Image Bed) tab pinned at the right end of the server-tab bar (entering it hides the stat cards and the server-card area):

- **Master switch & timeout**: the root-level `enable_image_upload` (when off, no upload is attempted) and `image_upload_timeout` (upload timeout in seconds) are toggled / edited at the top of the panel and take effect on save
- **Full entry management**: each entry is a card showing its kind (built-in / third-party), enabled state, why it is (or is not) active (disabled entry / invalid URL / wrong response type are all spelled out), address and runtime state; “new” entries are created with the template defaults filled in, editing covers every field, and deletion asks for confirmation
- **Reorder entries**: the “⬆ 上移 / ⬇ 下移” (move up / move down) buttons on each card set the order in which image beds are tried; uploads walk the list from top to bottom, so the higher an entry sits the earlier it is tried, and the new order takes effect as soon as you save
- **Built-in HTTP service runtime**: `builtin_http` entries show a “running / not running” badge reflecting the real state (not started / stopped / failed to start)
- **🧪 Test upload**: with no parameters at all, a built-in PNG probe is pushed through the whole upload chain per entry and the hosted image is read back to verify its real format, with the result colour-coded — 🟢 **green = pass** (the produced format can be rendered by ChatImage), 🟡 **yellow = usable but limited** (the image bed re-encodes images to webp, which ChatImage cannot render, so the upload succeeds but nothing shows in game) and 🔴 **red = failed** (listed as “image-bed name: reason”) — configuration problems are identified in one click

Every save is **partial-effect** (only the image-transfer subsystem is rebuilt; no MC connection is touched). The image-transfer subsystem is also decoupled from the MC server config, so the image bed starts even when no server is configured at all.

### Dashboard feature-settings panel

Below the server cards and the performance-monitoring panel, the dashboard has a collapsible “⚙ 功能设置” (feature settings) panel that groups everything **not** monitoring-related; its collapsed state is remembered by the backend (and the panel is hidden in the “全部服务器” all-servers view):

- **AI chat** (per server): turn in-game AI chat on / off and set its trigger prefix. A chat message starting with the prefix goes to the AI only — the reply is sent to that player as a private message and the message is not forwarded to the group; an empty prefix disables AI triggering and leaves normal chat untouched. Saving writes the plugin config and takes effect immediately without rebuilding connections, so it is the same setting as `enable_ai_chat` / `ai_chat_prefix` in the WebUI
- **Message forwarding** (per server): toggles for chat / join-leave / death / achievement forwarding, the chat message format (`{player}` `{message}` `{display_name}` placeholders), the group→MC trigger prefix (empty = forward everything) and the target sessions (one UMO per line). These are the same settings as in the “Message-forwarding configuration” table; saving takes effect immediately without rebuilding connections
- **Connection notification** (per server): send a notice to the target sessions when the server connects or fails to connect, with independent switches for the two cases and templates supporting the `{display_name}` `{server_name}` placeholders; the failure notice only fires once the outage outlasts the disconnect quiet period, and only for the first failure of that outage. The same settings as in the “Server-connection notification” table; saving takes effect immediately without rebuilding connections
- **Terminal window** (per server): how many days of interop-terminal logs to load (0–30, default 2 = today plus yesterday, 0 = keep all shards). Stored at the top level of the config entry — the same setting as `terminal_days` in the WebUI; saving takes effect immediately without rebuilding connections
- Monitoring parameters themselves (enabled, sample interval, realtime rate, retention, TPS command, latency probe, default view) still live in the “⚙ 设置” dialog of the monitoring panel

### Top-right “⚙ 设置” global-settings dialog

The “⚙ 设置” button at the top right (next to the auto-refresh toggle) opens a dialog for preferences independent of any single server: the dashboard auto-refresh interval in seconds (10–3600, applied while the “自动刷新” toggle is on, takes effect immediately). Refreshing or reopening the page keeps the last opened server tab instead of returning to “全部服务器”.

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
| `forward_chat_to_astrbot` | bool | `true` | Relay all in-game chat to target sessions; when off, only chats matching `forward_chat_prefix` are relayed. Image forwarding ignores this text prefix |
| `forward_chat_prefix` | string | empty | Game → group trigger prefix; when full chat forwarding is off, only game chat starting with this prefix is relayed, with the prefix removed |
| `forward_chat_format` | string | `[{display_name}]{player}: {message}` | Chat format; supports `{player}` `{message}` `{display_name}` |
| `forward_join_leave_to_astrbot` | bool | `false` | Forward join/quit messages (server display name appended, so the source is clear when several servers share a group) |
| `forward_death_to_astrbot` | bool | `false` | Forward death messages (unsupported on Vanilla/Velocity) |
| `forward_achievement_to_astrbot` | bool | `false` | Forward achievement messages (unsupported on Vanilla/Velocity) |
| `auto_forward_prefix` | string | empty | Group text starting with it is relayed into the game; empty relays all. Enabled image forwarding ignores this prefix |
| `forward_bot_self_messages` | bool | `false` | **Relay the bot's own messages without stripping wake prefixes**: wake messages use their original pre-processing text, including the self-mention omitted from OneBot's text (a standalone `@bot` is relayed too); bot replies produced by AstrBot's message pipeline and bot self-messages observed by this plugin are relayed with the available group nickname. Images reuse `forward_image_to_mc` and the image-host settings; `[图片]` is only used when image forwarding is disabled or no reachable URL can be obtained. Faces are recorded as `[表情:id]`. No need to disable `ignore_bot_self_message`, and replies are not fed back into command handling. `auto_forward_prefix` still applies; this plugin's own group messages remain echo-suppressed |
| `broadcast_format` | string | `[{platform}]{sender}: {message}` | Format used when relaying into the game; supports `{platform}` `{sender}` `{message}` `{display_name}` `{server_name}` |
| `platform_names` | list | `["aiocqhttp=QQ"]` | Platform name mapping: `raw=display`, e.g. `aiocqhttp=QQ` |
| `broadcast_color` | string | `white` | Message color; MC color name or `#RRGGBB` |
| `mark_option` | string | `emoji` | Acknowledgement after a successful relay: `text` replies ✅ / `emoji` reacts to the original message / `none` silent |
| `mark_emoji_id` | int | `124` | Reaction emoji ID (QQ emoji ID; default `124` = 👌) |
| `forward_image_to_mc` | bool | `false` | Relay group images and enabled bot reply/self-message images into the game using the selected game image mode |
| `chatimage_name` | string | `图片` | In-game display name for the image |
| `forward_image_from_mc` | bool | `false` | Download in-game images according to the selected game image mode and send them as images; images ignore the game → group text prefix |
| `mc_image_mode` | string | `chatimage` | Bidirectional image route: `chatimage` preserves the existing behavior; `e33chat` writes group images to E33Chat media storage and reads game images from it, including E33Emote / ChatUpgrade tags |
| `e33chat_media_dir` | string | empty | Required for E33Chat mode: the actual E33Chat server media directory; the AstrBot process must have read and write access (mount a shared directory for remote servers) |

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

### Server-connection notification

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `notify_on_connect` | bool | `false` | Send a “server started” notice to the target sessions once the server connects; only sent when the server really started, so a brief connection hiccup no longer raises a false alarm (see below) |
| `notify_on_connect_format` | string | `[{display_name}] 🟢 服务器已启动` | Multiline notice template; supports the `{display_name}` and `{server_name}` placeholders; empty uses the default template |
| `notify_on_connect_fail` | bool | `false` | Send a “connection failed” notice to the target sessions when the first connection attempt fails or an established connection drops; the outage must last longer than the quiet period below, only the first failure of an outage is sent, and the next outage notifies again after a successful reconnect |
| `notify_on_connect_fail_format` | string | `[{display_name}] 🔴 服务器连接失败` | Multiline failure notice template; supports the `{display_name}` and `{server_name}` placeholders; empty uses the default template |
| `connect_fail_notify_delay` | int | `60` | Disconnect quiet period in seconds (`0`–`3600`): the failure notice is sent only when the outage outlasts it, and a reconnect within it stays silent; `0` notifies immediately |
| `slp_address` | string | empty | Server status probe address (e.g. `127.0.0.1:25565`; the port defaults to `25565`): while the bridge is down the plugin uses it to tell whether the server really stopped; empty falls back to outage length (a “server started” notice needs an outage longer than 30 seconds) |

</details>

With “server-connection notification” enabled, connecting that server sends a notice to its **target sessions**; nothing is sent at all when no target session is configured. Only `{display_name}` (server display name) and `{server_name}` (server name) are replaced — any other braces are kept verbatim.

A “server started” notice is only sent when the server really started. Network hiccups, server lag and plugin reloads no longer raise false alarms: when the “server status probe address” (`slp_address`) is filled in, the plugin probes that address while the bridge is down — a server that still answers only lost its bridge (nothing is sent), while an unreachable one is treated as a real restart. When it is left empty the outage length decides: reconnects after more than 30 seconds count as a start, while hiccups that heal within seconds stay silent.

With “connection-failure notification” enabled, a “connection failed” notice is sent both when the server has never been reachable and when an established connection drops; only the first message per outage (until the connection is re-established) is sent, so reconnect retries do not flood the chat. The notice also waits out the “disconnect quiet period” (`connect_fail_notify_delay`, 60 seconds by default): a reconnect within it sends nothing at all, and the notice only goes out when the outage outlasts it; set it to `0` to be told the moment the connection drops. In reverse mode the failure notice is only sent when an established connection drops.

### Quiet hours

When you would rather not have the group pinged by game activity overnight, give each server its own silent window (for example `23:00` – `08:00`). Inside the window only the message types you tick are muted.

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `quiet_hours_enabled` | bool | `false` | Enable the quiet window; off by default |
| `quiet_hours_start` | string | `23:00` | Start time (AstrBot local time, `HH:MM`); equal start and end means “not configured” |
| `quiet_hours_end` | string | `08:00` | End time (AstrBot local time, `HH:MM`); an end earlier than the start wraps past midnight |
| `quiet_hours_items` | list | death/achievement/connect/failure notices | Which types are muted (checkbox multi-select): `chat` game chat, `join_leave` player join/quit, `death` death messages, `achievement` achievements, `connect` connection notices, `connect_fail` failure notices |

</details>

- Both the dashboard's “功能设置 → 🌙 免打扰” panel and the AstrBot plugin config page let you toggle it, pick the window and tick the types; saving takes effect immediately without reconnecting

### Relaying images into the game

With `forward_image_to_mc` enabled, images in group messages and enabled bot pipeline/self-messages use the selected game image mode. **ChatImage and E33Chat are separate routes; choose one according to the mod installed on the server.** ChatImage is the URL route for the ChatImage mod. E33Chat uses server-hosted media IDs for the E33Chat mod.

ChatImage mode example:

```text
[QQ]UserA: [[CICode,url=https://example.com/images/example.png,name=Image]]
```

E33Chat mode example:

```text
[QQ]UserA: [[CICode,url=e33chat://media/0123456789abcdef0123456789abcdef,name=Image]]
```

- `chatimage` mode is for servers using the [ChatImage](https://github.com/kitUIN/ChatImage) mod; it sends image URLs reachable by players. If AstrBot has no reachable URL, configure `enable_image_upload` and `image_upload_services` (see below)
- `e33chat` mode is for servers using E33Chat and requires server media hosting (`media_enabled`). We recommend the MCSManager panel API described below. Game → group supports E33Chat media IDs, E33Emote, and ChatUpgrade image tags, as well as CICode image URLs
- Group → game and game → group still have separate `forward_image_to_mc` / `forward_image_from_mc` switches; the mode controls the image route for each enabled direction
- Images ignore `auto_forward_prefix`; with image forwarding enabled, bare image messages can be relayed. Any accompanying caption is relayed with the image

#### E33Chat media setup (recommended: MCSManager panel API)

Confirm that the server runs E33Chat and has `media_enabled` turned on. In the plugin Dashboard's “转发功能” settings, choose “游戏图片模式: E33Chat 服务端媒体”, then “媒体存储方式: MCSManager 面板 API”, and enter:

- Panel URL, API key, target Daemon ID, and instance UUID. Find these in MCSManager and the node/instance details. The API key has its owner's permissions; keep it private.
- Instance media directory. In the target instance's file manager, locate `e33chat-media` and enter its path relative to the instance root, for example `/world/serverconfig/e33chat-media`. Do not enter the Linux host's `/opt/...` absolute path.
- Daemon file-transfer address (advanced, optional). Usually leave this blank; the plugin uses the address returned by the MCSManager API. Only enter a Daemon address and port reachable from AstrBot if that returned address cannot be reached (for example, it is `localhost` or an incorrect private address). This is not the MCSManager panel URL.

The AstrBot host must be able to reach both the MCSManager panel and the Daemon transfer port. Save the settings and test image forwarding in both directions. The MCSManager API backend needs no mounted directory and does not use the local media-directory field.

**Alternative: local/shared directory.** Share or mount E33Chat's media directory somewhere AstrBot can access, select “本地/共享目录”, and enter that local path in “E33Chat 服务端媒体目录”. On Windows, use a UNC path such as `\\10.x.x.x\e33chat-media`; on Linux, use the mounted path such as `/mnt/e33chat-media`.

<details><summary>Detailed shared-directory instructions (optional)</summary>

1. Confirm the Minecraft server has an E33Chat version with server media hosting. The server setting `media_enabled` must be `true` (the default). `media_auto_clean` is also enabled by default and removes files older than 7 days; disabling it keeps files, but the 512 MiB total quota still applies.
2. In MCSM, select the correct instance, check `level-name` in `server.properties` (default `world`), then open `serverconfig/e33chat-media` under that world directory. E33Chat stores extensionless files named with 32 lowercase hexadecimal characters there. If the directory/files do not exist yet, send an image from the game client and refresh the file list. Do not enter the MCSM web address, the instance root, `serverconfig`, or the media directory's parent.
3. Locate the **media directory itself** on the MCSM host filesystem and share it over SMB/NFS on a private network. On a Windows MCSM host, enable Advanced Sharing on that folder, name the share `e33chat-media`, grant a dedicated account Change permission on the share and Modify permission on the Security tab, then restrict the SMB firewall rule to trusted clients. Do not expose SMB to the public internet. On a Linux MCSM host, export the actual directory with Samba/NFS and ensure both the share account and Minecraft server account can read and write it. Windows AstrBot can use a UNC path such as `\\10.x.x.x\e33chat-media`; Linux can mount it at `/mnt/e33chat-media`.
4. If AstrBot runs in Docker/a container, mount SMB/NFS on the container host first, then bind-mount that host directory into the container, for example at `/mnt/e33chat-media`. The plugin path must be the path visible inside the container, not the MCSM Linux path, host path, or Windows drive letter unless that path is actually mounted in the container.
5. As the same account/container that runs AstrBot, verify that the share can list ID files, read an existing image, and create then delete a temporary file. If AstrBot runs as a Windows service, check its “Log On” identity in `services.msc` and grant that identity share access; mapped drive letters may be invisible to the service. Seeing files in MCSM's web file manager does not prove AstrBot has filesystem access. Example paths are `\\10.0.0.2\e33chat-media` on Windows and `/mnt/e33chat-media` after a Linux mount.
6. Open the QueQiao plugin Dashboard in AstrBot, select the target Minecraft server, and expand image forwarding under “转发功能”. Set “游戏图片模式” to `E33Chat 服务端媒体` and enter the verified **directory path** in “E33Chat 服务端媒体目录” (`e33chat_media_dir`). Do not enter a filename, MCSM URL, or parent directory. Enable “外部 → MC 图片转发” and/or “MC → 外部 图片转发”, then save.
7. Test each enabled direction with an image under 8 MiB. A group image should render in game and create a new extensionless ID file in the share; an in-game image should arrive in the target group as an image component. If group → game fails, inspect AstrBot logs for directory write errors. If game → group fails, confirm the event contains a media ID/image tag and that its ID file remains in the shared directory.

If MCSM shows a Linux path while AstrBot runs on Windows, do not paste that host path as the local directory. Use a Windows UNC share path or a path mounted where AstrBot runs.

</details>

### Relaying in-game images to external sessions

With `forward_image_from_mc` enabled, in-game images are downloaded and sent to the group according to `mc_image_mode`. Images ignore `forward_chat_prefix`:

- `chatimage` (default): handles ChatImage `[[CICode,url=...]]` codes and reachable image links for the ChatImage mod
- `e33chat`: handles E33Chat `[[E33Emote,url=...]]`, `[[ChatUpgrade,url=...,type=image]]`, and server-hosted media IDs, while retaining CICode image URLs and existing image-link downloads
- `http(s)://` links are downloaded directly; `file://` local files are only readable when AstrBot runs on the same machine as the game
- E33Chat server media requires selecting E33Chat mode. With the MCSManager API backend, use the panel settings above; `e33chat_media_dir` is only needed for the local/shared-directory backend
- On download failure (dead link, invisible local file, etc.) the original code/link text is kept
- ChatImage / ordinary links are limited to 5 MB per image; E33Chat media is limited to 8 MiB; HTTP downloads time out after 15 seconds. E33Chat media shares the server's 512 MiB quota and auto-cleanup policy

#### Built-in image HTTP service

Some protocol clients deliver images only as base64 / local files with no externally reachable URL. Add a **"Built-in image HTTP service"** entry (template `builtin_http`) in `image_upload_services` — the plugin caches the image bytes in its built-in HTTP service and broadcasts `{base_url}/img/<token>` for player clients to load. **The prerequisite is that AstrBot has a publicly reachable address**; image bytes are cached in memory for 30 minutes (up to 500 entries). This service only stores bytes as-is and never re-encodes them, so whatever you send is what comes back (the image-bed test normally turns green). All of these entries can also be maintained directly in the dashboard's “🖼️ 图床” panel — no config file editing needed.

#### Generic image bed

Automatically upload images without a public URL to an image bed to get a publicly reachable link, then broadcast it into the game:

1. Turn on the root-level switch `enable_image_upload`
2. Adjust `image_upload_timeout` (upload timeout, default 30 s) as needed
3. Add image bed entries in `image_upload_services`: no bed is loaded by default — “new” lets you pick the **built-in HTTP service**, the **“Custom”** template (any upload endpoint), or a pre-configured template (endpoint and response mode pre-filled, just supply a token where needed)

> 💡 All three steps above can be done in the dashboard's “🖼️ 图床” panel: the master switch and timeout live at the top, entries are created / edited from templates with “new / edit”, and “🧪 Test upload” verifies the configuration right away.

| Entry field | Type | Default | Description |
|-------------|------|---------|-------------|
| `enabled` | bool | `true` | Enable this image bed entry |
| `name` | string | empty | Display name (logs/labels only) |
| `upload_url` | string | empty | **Full upload endpoint URL (not the site homepage)** |
| `token` | string | empty | API token (sent as `Authorization: Bearer <token>` header plus a `token` form field; imgbb is the exception and receives it as the `key` form field); leave empty for token-free beds |
| `response` | string | `text` | Response parsing: `text` = the response body is the link; `json` = the `url` field (falling back to the first `http(s)://` field) |
| `file_field` | string | `file` | Multipart file field name (`image` for img402 / imgbb, `smfile` for S.EE) |
| `headers` | string | empty | Custom request headers: one `Name: Value` per line (or a JSON object) |
| `form_fields` | string | empty | Extra plain form fields: one `Name: Value` per line (or a JSON object) |

Pre-configured templates:

<details>
<summary>Show pre-configured templates</summary>

| Template | Region | Token | Response | Size / quota | Notes |
|----------|--------|-------|----------|--------------|-------|
| `imglink` | overseas | no | `json` | ≤25MB per image | anonymous direct upload; the server re-encodes images and can be slow |
| `img402.dev` | overseas | no | `json` | ≤10MB per image | file field is `image`; ≤1MB stored permanently, 1–10MB for 30 days; behind Cloudflare, occasional timeouts |
| `pngurl` | domestic | no | `json` | — | successor of pngcdn.cn; guest uploads are rate-limited, register and supply a token for regular use |
| `anyapi` | domestic relay | no | `json` | suggested ≤10MB per file | anyapi relay proxy |
| `see` | domestic | yes | `json` | ≤5MB per image | S.EE / sm.ms; file field is `smfile`, put the key in the request header |
| `imgbb` | overseas | yes | `json` | ≤32MB per image | established API; file field is `image`, key submitted as the `key` form field |

</details>

- Only templates verified to work are kept: `catbox` / `litterbox` (requests blocked), `imgloc` (endpoint domain gone), `xinyew` / `xunjinlu` (blocked by a WAF) and `picui` (outputs webp only, which the game cannot display) were removed; if you still need them, use the `custom` template and fill in the endpoint yourself
- Uploads send the image's **real format** in the MIME type and filename suffix (png / jpg / webp …) so image beds do not reject it as a generic file
- Multiple enabled entries are **tried in list order** (use the “⬆ 上移 / ⬇ 下移” buttons in the panel to change which one comes first); the first success is broadcast into the game; when all fail, a warning aggregates each failure as `name: reason`
- ⚠️ **Privacy notice**: group images are uploaded to the image bed — enable only when needed
- ⚠️ **webp images may not show up**: rendering in game depends on ChatImage, which only supports png / jpg / jpeg / jfif / gif / ico / bmp and **does not support webp**. Images in chat are mostly png / jpg, but some image beds re-encode everything they host to webp; when the resulting link is webp the chat bar shows no picture (only the code text). “🧪 Test upload” sends a single PNG and reads the hosted image back to check its format: png / jpg and friends turn it green, while a product that became webp turns it yellow. A yellow result means the image bed re-encodes images to webp — switch to one that stores images as-is (such as `pngurl` or `img402.dev`)

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
| `{display_name}` | both formats, `notify_on_connect_format`, `notify_on_connect_fail_format` | Server display name; falls back to `display_name_default` (`MC`) when blank, renders empty only when both are cleared |
| `{platform}` | `broadcast_format` | Platform name (may be rewritten via `platform_names`, e.g. `aiocqhttp` → `QQ`) |
| `{sender}` | `broadcast_format` | Sender name |
| `{server_name}` | `broadcast_format`, `notify_on_connect_format`, `notify_on_connect_fail_format` | Server name (always populated) |

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
