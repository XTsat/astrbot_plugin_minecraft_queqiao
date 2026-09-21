<div align="center">

<h1>Minecraft Queqiao</h1>

<p><strong>Connect Minecraft servers to AstrBot via the QueQiao mod for message bridging, server management and AI chat</strong></p>

<p><sub>Minecraft &nbsp;&nbsp; Chat Bridge &nbsp;&nbsp; QueQiao &nbsp;&nbsp; AI Chat</sub></p>

<p><a href="README.md">中文</a> &nbsp;/&nbsp; <strong>English</strong></p>

</div>

## Features

Connects Minecraft servers to AstrBot through the
[QueQiao](https://github.com/17TheWord/QueQiao) mod. The configuration layout follows
[astrbot_plugin_minecraft_adapter](https://github.com/railgun19457/astrbot_plugin_minecraft_adapter),
while the transport layer uses the QueQiao V2 protocol.

- **Chat bridge**: two-way forwarding between Minecraft chat and other platforms
- **Event broadcast**: player join / quit / death / achievement events forwarded to sessions
- **Server management**: status queries, online player list, remote command execution
- **AI chat**: talk to the AI in-game with its own prefix (`ai hello`); replies are sent privately and normal bridging is unaffected
- **Multiple servers**: connect several servers, each with independent forwarding settings
- **Flexible transport**: forward mode (plugin dials QueQiao) or reverse mode (QueQiao dials plugin, ideal for rented servers)

> Compared with the adapter, this plugin additionally supports death and achievement events
> plus Title and ActionBar pushes. However, QueQiao exposes **no player-detail query API**,
> so `mc player` relies on RCON.

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

When a session is bound to several servers, a numbered list is shown; reply with a
number to pick the target server.

### Custom commands

The `cmd.custom_cmd_list` option defines shortcuts using this syntax:

```
trigger <&param&><<>>actual command {param} {sender}
```

- Everything left of `<<>>` is the trigger template, right of it is the command to run
- `{sender}` is replaced with the sender's **bound game ID**
- `<&xxx&>` are positional placeholders, substituted by matching names on both sides

Example: `tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>`

If user A has bound the game ID `Misaka` and sends `tp 114 514 1919` in the group,
the server actually runs `tp Misaka 114 514 1919`.

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
| `reconnect_interval` | int | `5` | Reconnect delay in seconds, growing up to 60s |
| `max_reconnect` | int | `0` | Max reconnect attempts; `0` means unlimited |

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

> Obtain a session UMO with AstrBot's `sid` command; the form is
> `aiocqhttp:GroupMessage:123456789`.

> **Reaction emoji**: `mark_option: emoji` adds a reaction to the **original message**
> that triggered the relay (no extra message is sent). **Every aiocqhttp protocol
> implementation supports it** (such as NapCat, Lagrange or LLOneBot); other platforms
> are skipped silently instead of failing.

`mark_emoji_id` takes a **QQ emoji ID** — note that this is neither a Unicode code point
nor an OneBot standard index (e.g. ✅ has no QQ emoji ID). The built-in Emoji response
constants of this plugin, all verified by testing:

| Constant | ID | Emoji |
|----------|----|-------|
| `EMOJI_OK_GESTURE` | `124` | 👌 |
| `EMOJI_THUMBS_UP` | `76` | 👍 |
| `EMOJI_LOVE` | `66` | ❤️ |
| `EMOJI_ROSE` | `63` | 🌹 |

</details>

### Server display name and format placeholders

<details>
<summary>Show options</summary>

`server_id` is the **connection identity** used by QueQiao (bound to `x-self-name`, so it
cannot be Chinese). To make multiple servers easier to tell apart in a group, set
**`server_name` (display name)** as well — it only affects presentation and may be Chinese:

```jsonc
"server": {
  "server_id": "survival",       // must match QueQiao's config.yml server_name; don't change
  "server_name": "生存服",        // display only, may be Chinese
  "server_name_default": "MC"    // shown when server_name is blank; defaults to MC
}
```

Both format strings accept `{server}`, which resolves through the chain
**`server_name` → `server_name_default` (default `MC`) → empty string**:

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

`{platform}` can also be rewritten into something nicer via **`platform_names`** — raw
platform IDs (such as `aiocqhttp`, `qq_official`) are often long and ugly inside the game.
This option **ships with a default `aiocqhttp=QQ` entry**: with no configuration at all,
`aiocqhttp` already renders as `QQ` in-game. Delete the entry if you do not want the rewrite:

| Setting | Result |
|---------|--------|
| `platform_names` = `aiocqhttp=QQ`, format `[{platform}]{sender}: {message}` | `[QQ]群友A: 你好` |
| same mapping plus `telegram=电报`, `discord=DC` | those platforms also show the mapped name; unmapped platforms keep their original name |

> The mapping is configured **per server** (in the "Message forwarding" section), so
> different servers may use different names. Matching is case-insensitive (platform IDs are
> lowercase, so a case typo still hits). Entries take the form `raw=display`; malformed
> entries (no `=`, empty key, empty value) are silently ignored; clearing the whole list
> disables the rewrite and restores the original platform name.

> **Empty behaviour**: when `server_name` is blank, the **display-name default**
> (`MC`) is used — leaving everything untouched yields `[MC]<player>`. To make `{server}`
> render an **empty string** (no prefix), clear `server_name_default` as well; literal
> brackets in the format string remain (`[{server}]<{player}> {message}` then yields
> `[]<Steve> 大家好`; drop the brackets for a clean look). Use `{server_id}` if you
> always want a value.

> Existing format strings without `{server}` keep working unchanged.

`/mc status` and `/mc list` label the server through the same chain
(`server_name` → default → `server_id`), so multi-server setups are easier to read;
the handshake and logs keep using `server_id`.

</details>

### AI chat

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable_ai_chat` | bool | `true` | Master switch for in-game AI chat |
| `ai_chat_prefix` | string | `ai` | **Trigger prefix**, e.g. `ai hello`. Empty disables the AI trigger |

> The trigger is **in-game chat** (`ai hello`), available on all server types (including
> Vanilla / Velocity).

#### How the two prefixes relate (important)

They act in different directions and are configured independently, but **a given message
matches only one of them**:

| Prefix | Direction | Effect |
|--------|-----------|--------|
| `auto_forward_prefix` | group → MC | Group messages starting with it are relayed into the game |
| `ai_chat_prefix` | in-game → AI | In-game chat starting with it triggers the AI and is **not** relayed to the group |

An in-game message is handled in this order: if it matches `ai_chat_prefix` it goes to the
AI (the reply is sent privately to that player); otherwise it is relayed to the group as a
normal chat message.

With the defaults (bridging prefix empty = relay all, AI `ai`):

| In-game message | Result |
|-----------------|--------|
| `ai do some math` | Goes to the AI, replied privately |
| `AI hello` | Goes to the AI (prefix is case-insensitive) |
| `hello everyone` | Relayed to the group |
| `aim high` / `airport` | Relayed to the group (**no** false AI trigger) |

> **Matching rules**: a prefix ending in a letter or digit must be followed by a space or
> the end of the message, so `ai` will not misfire on words like `aim` or `airport`; letter
> matching is case-insensitive. Prefixes ending in a symbol (`*`, `!`) match literally and
> need no separator.

> ⚠️ Do not let the two prefixes contain one another (for example both set to `*`, or one
> being a prefix of the other), otherwise the routing of a message becomes ambiguous. The
> plugin detects this at startup and logs a warning.

> Leaving `ai_chat_prefix` empty does **not** make every message trigger the AI — doing so
> would feed all chat into the LLM, adding noise and cost. Empty simply disables the AI
> trigger; normal bridging is unaffected.

> A trigger with no content (e.g. just `ai`) sends no request to the LLM, avoiding pointless
> usage.

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
| `rcon_fallback.enabled` | bool | `false` | Connect to RCON directly when QueQiao's RCON is unavailable |
| `rcon_fallback.host` | string | `localhost` | RCON host |
| `rcon_fallback.port` | int | `25575` | RCON port |
| `rcon_fallback.password` | string | empty | RCON password |

</details>

### Plugin options

<details>
<summary>Show options</summary>

| Option | Type | Default | Description |
|--------|------|--------|-------------|
| `enabled` | bool | `true` | Enable the plugin |
| `text2image` | bool | `true` | Render server info as an image, falling back to text |

</details>

## Deployment and FAQ

### Installation

1. Place this plugin under AstrBot's `data/plugins/` directory and restart AstrBot
2. In the WebUI plugin config, click "Add MC server" and **fill in "Target sessions" (required)**
3. Make sure `server_id` exactly matches QueQiao's `server_name`

> **The defaults work out of the box for a same-machine setup**: when AstrBot and MC run
> on one machine, the connection settings (`ws_url` →
> `ws://127.0.0.1:8080/minecraft/ws`) already line up with QueQiao's default port, so
> **nothing needs changing** — just set "Target sessions" and you are done. For
> cross-machine or Docker setups, see the next section.

### Networking and addresses (Docker / same-machine setups)

Whether `host` should be `127.0.0.1` or `0.0.0.0` **depends on whether AstrBot and MC
share a network stack** — not on the operating system. There is exactly one criterion:
**can AstrBot reach the address QueQiao is listening on?**

| Scenario | QueQiao `websocket_server.host` | Plugin `ws_url` |
|----------|--------------------------------|-----------------|
| Windows / Linux, **both installed directly on one machine** (same network stack) | `127.0.0.1` (default, no change needed) | `ws://127.0.0.1:8080/minecraft/ws` |
| AstrBot and MC on **different machines** | that machine's reachable address (LAN IP or `0.0.0.0`) | `ws://<MC server IP>:8080/minecraft/ws` |
| AstrBot in Docker, MC on the host (or vice versa) | **`0.0.0.0`** | the host's reachable address |
| AstrBot and MC in separate containers | **`0.0.0.0`** | the MC container's published port or container name |

> In the table above, `127.0.0.1`, `8080` and `/minecraft/ws` are all **defaults and can be
> changed**: use whatever address fits your deployment (see the notes below), and set the
> port to match QueQiao's `websocket_server.port` — or the plugin's `reverse_port` in
> reverse mode. **Change one side and you must change the other to match.**

> **How to fill in `ws_url`: use the address at which the MC server is reachable
> *from the machine running AstrBot*.** On the same machine, use `127.0.0.1`. When
> AstrBot and MC are on different machines, **use the MC server's actual IP** (e.g.
> `ws://192.168.1.10:8080/minecraft/ws`) — `127.0.0.1` will not work there, because on
> AstrBot it means AstrBot itself.

> **`0.0.0.0` is a *listen* address meaning "all interfaces", and belongs only on the
> server side** (QueQiao's `websocket_server.host`, the plugin's `reverse_host`).

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

- Success is logged as `已连接鹊桥 (ws://...)` ("connected to QueQiao"); a reachable TCP
  port alone does not mean the handshake succeeded
- If the log shows **continuous reconnects** with no explicit error, `host` is usually
  still `127.0.0.1`: the published port listens on the host, but QueQiao inside the
  container is bound only to the container's own loopback, so it never receives the
  docker-proxy traffic and the connection is reset immediately
- The startup line `WebSocket Server 在 <address>:<port> 启动...` tells you the actual
  address QueQiao bound to

### Configuring QueQiao

Install the [QueQiao](https://modrinth.com/plugin/queqiao) plugin/mod on your Minecraft
server and configure `config.yml` as described in its
[documentation](https://github.com/17TheWord/queqiao-docs):

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

> Achievement name availability also depends on the server: on `Spigot` the achievement
> event contains **only `key`**, and `Forge 1.7.10` lacks `display.description`.
> The plugin falls back through `translation.text → text → display.title → key`,
> so a name or identifier always shows; enable translation on the QueQiao side for
> localized names — see the FAQ.

### Dependencies

- Python 3.10+
- AstrBot >= 4.10.4
- `websockets` (required to connect to QueQiao)
- `aio-mc-rcon` (only needed for the direct RCON fallback)

### FAQ

**Q: Connection fails with an auth error or 404?**
Verify that `server_id` matches QueQiao's `server_name` exactly, including case, and that
`access_token` is identical on both sides.

**Q: The plugin keeps reconnecting. Should I change the address to `0.0.0.0`?**
`0.0.0.0` is a listen address, set on QueQiao's `websocket_server.host`. Under Docker, if
AstrBot and MC are not on the same network stack, change it to `0.0.0.0`; for a
Windows / Linux same-machine install no change is normally needed. See "Networking and
addresses" above, and the MC server IP note there when the two are on different machines.

**Q: `mc cmd` and `mc list` return nothing?**
Both depend on RCON. Set `rcon.enable: true` with a password in QueQiao's `config.yml`, or
enable the plugin's "direct RCON fallback" and fill in the server's RCON details.

**Q: Why am I not receiving death, achievement or command events?**
These events are **unsupported on Vanilla and Velocity** servers; this is an
upstream limitation.

**Q: Achievement messages only show "🏆 达成成就", or do not appear at all?**
The achievement field name and its availability vary by QueQiao version and server type.
**Note that the field actually pushed is `translation`, contradicting the `translate` name
used in QueQiao's docs**; the plugin accepts both.

The plugin falls back in four steps:
`translation.text` → `text` → `display.title` → `key`.
It normally shows at least the achievement name (e.g. `Hot Stuff`) or an identifier, and
only degrades to `🏆 <player> 达成了成就` when everything is missing — a message is no
longer dropped entirely.

Why the player name can be absent: with translation enabled, `translation.text` is a full
sentence that already embeds the player name (`X has made the advancement [Y]`). With
translation disabled it falls back to `display.title`, which contains **only the
achievement name** — so the plugin now prepends the player name itself, de-duplicating
when the sentence already contains it.

To get localized achievement names you must enable translation **on the QueQiao side**
(this is not a plugin setting): set `enable_translation: true` in `config.yml`, create a
`translate/` folder next to it, and drop in `zh_cn.json` / `en_us.json` (extractable from
the client jar). See the
[QueQiao translation docs](https://github.com/17TheWord/queqiao-docs/blob/main/docs/config/translate.md).
With translation disabled, `translation.text` may be an empty shell, in which case
`display.title` covers it.

**Q: Messages in chat contain braces like `{"text":"Hello"}`?**
On non-Vanilla servers `raw_message` is a text-component string. The plugin strips it; if
you still see braces, please open an issue with your server type and version.

**Q: My rented server cannot open a port.**
Set `ws_mode` to `reverse`. The plugin then listens and waits for QueQiao to connect;
point QueQiao's `websocket_client.url_list` at the plugin.

**Q: Why does `mc player` say it needs RCON?**
QueQiao offers no player-detail API, so this plugin falls back to RCON
`data get entity`. This is a known capability trade-off.

**Q: How do I let in-game chat both reach the AI and sync to the group?**
The two prefixes act independently in different directions — just set both, e.g.
`*` for bridging and `ai` for the AI. Normal chat is bridged while `ai hello` goes to the
AI. Take care not to let one prefix contain the other.

### Credits

- [QueQiao](https://github.com/17TheWord/QueQiao) — Minecraft server connectivity
- [astrbot_plugin_minecraft_adapter](https://github.com/railgun19457/astrbot_plugin_minecraft_adapter) — configuration reference
- [astrbot_plugin_mcqq](https://github.com/kterna/astrbot_plugin_mcqq) — reverse WebSocket approach

### License

[AGPL-3.0](LICENSE)
