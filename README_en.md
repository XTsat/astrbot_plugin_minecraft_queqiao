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

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `server_id` | string | `Server` | Unique server ID, **must match QueQiao's `server_name`** |
| `ws_mode` | string | `forward` | `forward`: plugin dials QueQiao; `reverse`: plugin listens for QueQiao |
| `ws_url` | string | `ws://127.0.0.1:8080/minecraft/ws` | Forward-mode URL, matches QueQiao `websocket_server` |
| `reverse_host` | string | `0.0.0.0` | Reverse-mode listen address |
| `reverse_port` | int | `8080` | Reverse-mode listen port |
| `reverse_path` | string | `/minecraft/ws` | Reverse-mode listen path |
| `access_token` | string | empty | Matches QueQiao `access_token`; empty disables auth |
| `client_origin` | string | `astrbot` | Sent as `x-client-origin`; leave unchanged unless needed |
| `reconnect_interval` | int | `5` | Reconnect delay in seconds, growing up to 60s |
| `max_reconnect` | int | `0` | Max reconnect attempts; `0` means unlimited |

### Message forwarding

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `forward_chat_to_astrbot` | bool | `true` | Forward player chat to target sessions |
| `forward_chat_format` | string | `<{player}> {message}` | Chat format; `{player}` name, `{message}` content |
| `forward_join_leave_to_astrbot` | bool | `false` | Forward join/quit messages |
| `forward_death_to_astrbot` | bool | `false` | Forward death messages (unsupported on Vanilla/Velocity) |
| `forward_achievement_to_astrbot` | bool | `false` | Forward achievement messages (unsupported on Vanilla/Velocity) |
| `target_sessions` | list | empty | Target session UMO list; **defines the MC ↔ chat binding** |
| `auto_forward_prefix` | string | `*` | **Prefix for relaying group messages into MC**; empty relays all |
| `broadcast_format` | string | `[{platform}] {sender}: {message}` | Format used when relaying into the game |
| `broadcast_color` | string | `white` | Message color; MC color name or `#RRGGBB` |
| `mark_option` | string | `emoji` | Relay acknowledgement: `text` / `emoji` / `none` |

> Obtain a session UMO with AstrBot's `sid` command; the form is
> `aiocqhttp:GroupMessage:123456789`.

### AI chat

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

With the defaults (bridging `*`, AI `ai`):

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

### Commands

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

### Miscellaneous

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable the plugin |
| `text2image` | bool | `true` | Render server info as an image, falling back to text |

## Other

### Installation

1. Place this plugin under AstrBot's `data/plugins/` directory and restart AstrBot
2. In the WebUI plugin config, click "Add MC server" and fill in the connection details
3. Make sure `server_id` exactly matches QueQiao's `server_name`

### Configuring QueQiao

Install the [QueQiao](https://modrinth.com/plugin/queqiao) plugin/mod on your Minecraft
server and configure `config.yml` as described in its
[documentation](https://github.com/17TheWord/queqiao-docs):

```yaml
server_name: "Server"        # must match the plugin's server_id
access_token: ""             # matches the plugin's access_token
websocket_server:
  enable: true               # required for forward mode
  host: "127.0.0.1"
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

**Q: Connection fails with an auth error or 404?**
Verify that `server_id` matches QueQiao's `server_name` exactly, including case, and that
`access_token` is identical on both sides.

**Q: `mc cmd` and `mc list` return nothing?**
Both depend on RCON. Set `rcon.enable: true` with a password in QueQiao's `config.yml`, or
enable the plugin's "direct RCON fallback" and fill in the server's RCON details.

**Q: Why am I not receiving death, achievement or command events?**
These events are **unsupported on Vanilla and Velocity** servers; this is an
upstream limitation.

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
