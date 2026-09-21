<div align="center">

<h1>Minecraft鹊桥互通</h1>

<p><strong>通过鹊桥模组连接 Minecraft 服务器，实现消息互通、服务器管理与 AI 聊天</strong></p>

<p><sub>Minecraft &nbsp;&nbsp; 群服互通 &nbsp;&nbsp; 鹊桥 &nbsp;&nbsp; AI聊天</sub></p>

<p><strong>中文</strong> &nbsp;/&nbsp; <a href="README_en.md">English</a></p>

</div>

## 功能介绍

通过 [鹊桥（QueQiao）](https://github.com/17TheWord/QueQiao) 模组连接 Minecraft 服务器与 AstrBot，
实现群服消息互通与服务器管理。配置结构参照
[astrbot_plugin_minecraft_adapter](https://github.com/railgun19457/astrbot_plugin_minecraft_adapter)，
连接层使用鹊桥 V2 协议。

- **群服互通**：Minecraft 玩家聊天与其他平台消息双向转发
- **事件播报**：玩家加入 / 离开 / 死亡 / 成就事件转发到指定会话
- **服务器管理**：服务器状态查询、在线玩家列表、远程指令执行
- **AI 聊天**：游戏内以独立前缀发言（如 `ai 你好`）即可与 AI 对话，回复私聊给玩家，不影响正常互通
- **多服务器**：同时连接多台服务器，各服务器独立配置转发会话与开关
- **灵活连接**：支持正向连接（插件连鹊桥）与反向连接（鹊桥连插件，适合租赁服）

> 相比 adapter，本项目额外支持死亡与成就事件、Title 与 ActionBar 推送；
> 但鹊桥**未提供玩家详情查询接口**，`mc player` 依赖 RCON 实现。

## 指令

| 命令 | 权限 | 说明 |
|------|------|------|
| `/mc help` | 全部 | 显示帮助信息与自定义指令列表 |
| `/mc status` | 全部 | 查看服务器状态 |
| `/mc list` | 全部 | 查看在线玩家列表 |
| `/mc player <玩家ID>` | 全部 | 查看玩家信息（依赖 RCON） |
| `/mc cmd <指令>` | 管理员 | 远程执行服务器指令，受黑白名单约束 |
| `/mc say <内容>` | 管理员 | 向游戏内广播消息 |
| `/mc bind <游戏ID>` | 全部 | 绑定你的游戏ID |
| `/mc unbind` | 全部 | 解除绑定 |
| `/mc servers` | 全部 | 查看已配置服务器与连接状态 |

当前会话关联多台服务器时，会显示服务器列表，回复编号选择目标服务器。

### 自定义指令

配置项 `cmd.custom_cmd_list` 支持自定义快捷指令，格式：

```
触发词 <&参数&><<>>实际指令 {参数} {sender}
```

- `<<>>` 左侧为触发模板，右侧为实际执行的指令
- `{sender}` 会替换为发送者**绑定的游戏 ID**
- `<&xxx&>` 为自定义参数占位符，左右同名即按位置替换

示例：`tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>`

假设用户 A 绑定了游戏 ID `Misaka`，在群内发送 `tp 114 514 1919`，
实际执行 `tp Misaka 114 514 1919`。

## 配置

### 服务器连接信息

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `target_sessions` | list | 空 | **目标会话**，位于列表项最上方「启用此服务器」下方。MC 消息转发到的会话 UMO 列表，**此项决定 MC 与群聊的绑定关系**，不填则插件能连上但群里收不到消息 |
| `server_id` | string | `Server` | 服务器唯一标识，**必须与鹊桥 `config.yml` 的 `server_name` 一致** |
| `server_name` | string | 空 | **服务器显示名称**，可写中文（如 `生存服`）。留空时用下方「显示名称默认值」；仅影响展示，不影响连接 |
| `server_name_default` | string | `MC` | **显示名称默认值**：`server_name` 留空时 `{server}` 与状态查询显示的内容，什么都不填即显示 `[MC]<玩家名>`。改成留空则输出空串（无前缀效果） |
| `ws_mode` | string | `forward` | `forward` 插件连鹊桥；`reverse` 插件开服务端等鹊桥连入 |
| `ws_url` | string | `ws://127.0.0.1:8080/minecraft/ws` | 正向连接地址，对应鹊桥 `websocket_server`（IP 与端口按实际部署填写） |
| `reverse_host` | string | `0.0.0.0` | 反向监听地址 |
| `reverse_port` | int | `8080` | 反向监听端口 |
| `reverse_path` | string | `/minecraft/ws` | 反向监听路径 |
| `access_token` | string | 空 | 对应鹊桥 `access_token`，留空则免鉴权 |
| `client_origin` | string | `astrbot` | 作为 `x-client-origin` 发送，非必要勿改 |
| `reconnect_interval` | int | `5` | 重连间隔（秒），随失败次数递增，上限 60 秒 |
| `max_reconnect` | int | `0` | 最大重连次数，`0` 表示无限重连 |

</details>

### 消息转发配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `forward_chat_to_astrbot` | bool | `true` | 转发玩家聊天到指定会话 |
| `forward_chat_format` | string | `[{server}]{player}: {message}` | 聊天消息格式，`{player}` 玩家名，`{message}` 内容，`{server}` **服务器显示名称**（可中文，留空用默认值 `MC`） |
| `forward_join_leave_to_astrbot` | bool | `false` | 转发玩家进出消息 |
| `forward_death_to_astrbot` | bool | `false` | 转发玩家死亡消息（原版/Velocity 不支持） |
| `forward_achievement_to_astrbot` | bool | `false` | 转发玩家成就消息（原版/Velocity 不支持） |
| `auto_forward_prefix` | string | 空 | **群消息转发到 MC 的前缀**，留空则全部转发（仅对已绑定目标会话的群生效） |
| `broadcast_format` | string | `[{platform}]{sender}: {message}` | 转发到游戏内的格式，`{server}` 显示名称（留空用默认值 `MC`）、`{server_id}` 服务器 ID（始终有值） |
| `broadcast_color` | string | `white` | 转发消息颜色，支持 MC 颜色名或 `#RRGGBB` |
| `mark_option` | string | `emoji` | 转发成功后的提醒方式：`text` 回复 ✅ 文本 / `emoji` 给原消息贴表情 / `none` 不提醒 |
| `mark_emoji_id` | int | `124` | **回执表情 ID**（仅 `mark_option=emoji` 时生效）。默认 `124` 为 👌，已核实的可用 ID 见下表 |

> `target_sessions`（目标会话）位于服务器列表项**最上方**的「启用此服务器」下方，
> 详见上一节的表格。其 UMO 可通过 AstrBot 的 `sid` 指令获取，格式如
> `aiocqhttp:GroupMessage:123456789`。

> **回执表情**：`mark_option: emoji` 会给触发转发的**原消息贴一个表情**（不额外发消息）。
> **所有 aiocqhttp 协议端都支持**（如 NapCat、Lagrange、LLOneBot 等）；
> 其他平台会静默跳过，不会报错。

`mark_emoji_id` 填 **QQ 表情 ID**。以下为推荐的几个 Emoji 响应 ID：

| 常量 | ID | 表情 |
|------|----|------|
| `EMOJI_OK_GESTURE` | `124` | 👌 |
| `EMOJI_THUMBS_UP` | `76` | 👍 |
| `EMOJI_LOVE` | `66` | ❤️ |
| `EMOJI_ROSE` | `63` | 🌹 |

</details>

### 服务器显示名称与格式变量

<details>
<summary>展开配置表</summary>

`server_id` 是给鹊桥用的**连接标识**（受 `x-self-name` 约束，不能用中文）；
如果想让多台服务器在群里更好辨认，可以另外填写 **`server_name`（服务器显示名称）**，
它只影响展示，可以随意写中文：

```jsonc
"server": {
  "server_id": "survival",       // 必须与鹊桥 config.yml 的 server_name 一致，别改
  "server_name": "生存服",        // 仅用于展示，可写中文
  "server_name_default": "MC"    // server_name 留空时的默认展示内容，默认 MC
}
```

两个格式串都支持 `{server}`，取值链为 **`server_name` → `server_name_default`（默认 `MC`）→ 空串**：

| 占位符 | 可用位置 | 含义 |
|--------|----------|------|
| `{player}` | `forward_chat_format` | 玩家名称 |
| `{message}` | 两个格式串 | 消息内容（MC → 外部时已剥离富文本与颜色代码） |
| `{server}` | 两个格式串 | **服务器显示名称**；`server_name` 留空时用**显示名称默认值**（默认 `MC`），两者都留空才输出空串 |
| `{platform}` | `broadcast_format` | 平台名（群消息来源平台） |
| `{sender}` | `broadcast_format` | 发送者名 |
| `{server_id}` | `broadcast_format` | 服务器原始 ID（**始终有值**，需要精确标识时用） |

示例（多服同群时标明来源）：

| 配置项 | 值 | 实际效果 |
|--------|-----|--------------|
| `server_name` = `生存服`、格式 `[{server}] <{player}> {message}` | — | `[生存服] <Steve> 大家好` |
| 什么都不填、格式 `[{server}] <{player}> {message}` | — | `[MC] <Steve> 大家好`（默认值 `MC`） |
| 默认值改成 `本服`、格式 `[{server}]{player}: {message}` | — | `[本服]Steve: 大家好` |

> **留空行为**：`server_name` 留空时用「显示名称默认值」（默认 `MC`，即什么都不填
> 就是 `[MC]<玩家名>` 效果）。想让 `{server}` 输出**空字符串**（无前缀），
> 需要把 `server_name_default` 也显式清空——此时格式串里的字面量方括号仍在
> （`[{server}]<{player}>` 会得到 `[]<Steve> 大家好`），干净效果就不要写方括号。
> 想让前缀永远有值，请改用 `{server_id}`。

> 不写 `{server}` 的旧格式串完全不受影响，无需迁移。

`/mc status` 与 `/mc list` 的标题沿用同一条取值链（`server_name` → 默认值 → `server_id`），
多服排障时不用再对着英文 ID 猜是哪台；连接握手与日志仍使用 `server_id`。

</details>

### AI 聊天配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_ai_chat` | bool | `true` | 启用游戏内 AI 对话（总开关） |
| `ai_chat_prefix` | string | `ai` | **触发前缀**，例如发送 `ai 你好`。留空表示不启用 AI 触发 |

> 触发方式是**游戏内聊天**（`ai 你好`），全服务端可用（含原版 / Velocity）。

#### 两个前缀的关系（重要）

两个前缀作用方向不同、互相独立，**但一条消息只会命中其中一个**：

| 前缀 | 方向 | 作用 |
|------|------|------|
| `auto_forward_prefix` | 群 → MC | 群消息以此开头才转发到游戏 |
| `ai_chat_prefix` | 游戏内 → AI | 游戏内聊天以此开头才触发 AI，**不再转发到群** |

游戏内一条消息的处理顺序是：命中 `ai_chat_prefix` → 交给 AI（回复私聊给该玩家）；
否则按普通聊天转发到群。

以默认配置为例（互通前缀留空 = 全部转发、AI `ai`）：

| 游戏内发言 | 结果 |
|------------|------|
| `ai 帮我算道题` | 交给 AI，私聊回复 |
| `AI 你好` | 交给 AI（前缀不区分大小写） |
| `大家好` | 转发到群 |
| `aim 很高` / `airport 到了` | 转发到群（**不**误触发 AI） |

> **前缀匹配规则**：以字母或数字结尾的前缀要求后面跟空格或直接结束，
> 因此 `ai` 不会误伤 `aim`、`airport` 这类同词头发言；字母部分不区分大小写。
> 以符号结尾的前缀（如 `*`、`!`）按字面匹配，无需空格。

> ⚠️ 两个前缀**不要相互包含**（例如都填 `*`，或一个为另一个的前缀），
> 否则同一条消息的归属会产生歧义。插件会在启动时检测并输出告警日志。

> `ai_chat_prefix` 留空**不会**导致所有聊天都触发 AI——那样会把全部聊天投给 LLM，
> 既产生噪声也消耗额度。留空即表示关闭 AI 触发，普通互通不受影响。

> 触发后内容为空（例如只发 `ai`）不会向 LLM 发请求，避免无意义消耗。

</details>

### 指令配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `true` | 启用远程指令执行 |
| `cmd_white_black_list` | string | `white` | `white` 仅允许名单内；`black` 禁止名单内；`none` 不限制 |
| `cmd_list` | list | `["say","list","weather","time"]` | 指令名单（填指令名，不带 `/`） |
| `bind_enable` | bool | `true` | 启用账号与游戏 ID 绑定 |
| `custom_cmd_list` | list | 空 | 自定义指令映射，语法见上文 |
| `rcon_fallback.enabled` | bool | `false` | 鹊桥未开 RCON 时，改由插件直连 RCON |
| `rcon_fallback.host` | string | `localhost` | RCON 地址 |
| `rcon_fallback.port` | int | `25575` | RCON 端口 |
| `rcon_fallback.password` | string | 空 | RCON 密码 |

</details>

### 插件配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `true` | 启用插件 |
| `text2image` | bool | `true` | 服务器信息渲染为图片，失败自动回退文本 |

</details>

## 部署与常见问题

### 安装

1. 将本插件放入 AstrBot 的 `data/plugins/` 目录，重启 AstrBot
2. 在 WebUI 插件配置中点击「添加 MC服务器」，**填写「目标会话」（必填）**
3. 确保 `server_id` 与鹊桥 `config.yml` 的 `server_name` 完全一致

> **默认配置即可直连本机双端**：AstrBot 与 MC 装在同一台机器时，
> 连接信息（`ws_url` → `ws://127.0.0.1:8080/minecraft/ws`）与鹊桥默认端口
> 已经对齐，**通常无需改动**，只要填好「目标会话」就能用。
> 跨机器、Docker 等场景见下一节。

### 网络与地址（Docker / 同机部署）

`host` 该填 `127.0.0.1` 还是 `0.0.0.0`，**取决于 AstrBot 与 MC 是否在同一网络栈**，
与操作系统无关。判断依据只有一条：**鹊桥的监听地址能不能被 AstrBot 直接访问到**。

| 场景 | 鹊桥 `websocket_server.host` | 插件 `ws_url` |
|------|------------------------------|---------------|
| Windows / Linux **同机直装**（两者同一网络栈） | `127.0.0.1`（默认，无需改） | `ws://127.0.0.1:8080/minecraft/ws` |
| AstrBot 与 MC 在**不同机器** | 该机器的可达地址（内网 IP 或 `0.0.0.0`） | `ws://<MC 服务器 IP>:8080/minecraft/ws` |
| AstrBot 在 Docker、MC 在宿主机，或反之 | **`0.0.0.0`** | 指向宿主机的可达地址 |
| AstrBot 与 MC 各自独立容器 | **`0.0.0.0`** | 指向 MC 容器的映射端口或容器名 |

> 上表中的 `127.0.0.1`、`8080`、`/minecraft/ws` 均为**默认值，都可修改**：
> 地址按实际部署填写（见下表说明），端口对应鹊桥 `websocket_server.port`，
> 反向模式下则对应插件的 `reverse_port`。**改了一侧，另一侧要同步改。**

> **填 `ws_url` 的原则：填「从 AstrBot 所在机器能访问到 MC 服务器」的那个地址。**
> 同机部署就填 `127.0.0.1`；AstrBot 与 MC 不在同一台机器时，**填 MC 服务器的
> 实际 IP**（如 `ws://192.168.1.10:8080/minecraft/ws`），不能填 `127.0.0.1`
> ——那在 AstrBot 上指的是 AstrBot 自己。

> **`0.0.0.0` 是「监听地址」，表示监听本机所有网卡，只能填在服务端一侧**
> （鹊桥的 `websocket_server.host`、插件的 `reverse_host`）。

**Docker 场景示例**（AstrBot 使用 host 网络、MC 在 bridge 容器内）：

```yaml
# MC 容器内 鹊桥 config.yml —— 必须监听所有网卡，否则容器外连不进来
websocket_server:
  host: "0.0.0.0"            # 可按需改为具体网卡地址
  port: 8080                 # 默认端口，可修改（需与下方 ws_url 一致）
```

```
# AstrBot 插件配置 —— AstrBot 在 host 网络即宿主机自身，连本机用 127.0.0.1
ws_url: "ws://127.0.0.1:8080/minecraft/ws"   # 端口需与上方 port 一致
```

排查要点：

- 插件日志出现 `已连接鹊桥 (ws://...)` 才算成功，仅 TCP 可连通不代表握手通过
- 若日志**持续重连**且无明确报错，多为 `host` 仍为 `127.0.0.1`——
  此时端口映射虽在宿主机监听，但容器内的鹊桥只绑在容器自己的 loopback，
  收不到 docker-proxy 转发的流量，连接会被立即重置
- 启动日志中的 `WebSocket Server 在 <地址>:<端口> 启动...` 可直接确认实际监听地址

### 配置鹊桥

在 Minecraft 服务端安装 [鹊桥](https://modrinth.com/plugin/queqiao) 插件/模组，
并按其[文档](https://github.com/17TheWord/queqiao-docs)配置 `config.yml`：

```yaml
server_name: "Server"        # 必须与插件配置的 server_id 一致
access_token: ""             # 对应插件配置的 access_token
websocket_server:
  enable: true               # 正向连接（插件连鹊桥）需开启
  host: "127.0.0.1"          # Docker 等跨网络栈部署见上方「网络与地址」
  port: 8080
websocket_client:
  enable: false              # 反向连接（鹊桥连插件）需开启并填写 url_list
  url_list: ["ws://127.0.0.1:8080/minecraft/ws"]
rcon:
  enable: true               # mc cmd / mc list 依赖此项
  port: 25575
  password: "your_password"
subscribe_event:             # 按需开启事件订阅
  player_chat: true
  player_join: true
  player_quit: true
  player_death: true
  player_advancement: true
```

### 版本兼容

| 能力 | 最低鹊桥版本 |
|------|--------------|
| API V2（广播 / 私聊 / 标题 / ActionBar / RCON） | v0.2.11 |
| 事件 V2 | v0.3.0 |
| 死亡与成就文本国际化（Translate） | v0.4.1 |
| 服务器状态查询 `mc status` | v0.5.0 |

> 成就名的可用性还取决于服务端：`Spigot` 的成就事件**仅包含 `key`**，
> `Forge 1.7.10` 缺 `display.description`。插件按
> `translation.text → text → display.title → key` 降级取值，
> 因此成就名或标识总能显示出来；要显示中文需在鹊桥侧开启翻译，见「常见问题」。

### 依赖

- Python 3.10+
- AstrBot >= 4.10.4
- `websockets`（连接鹊桥必需）
- `aio-mc-rcon`（仅在启用直连 RCON 兜底时需要，缺失时其余功能不受影响）

### 常见问题

**Q：连接不上，日志提示鉴权失败或 404？**
检查 `server_id` 是否与鹊桥 `server_name` 完全一致（含大小写），
以及 `access_token` 是否与鹊桥配置相同。

**Q：日志一直重连、连不上鹊桥，是不是该把地址改成 `0.0.0.0`？**
`0.0.0.0` 是监听地址，填鹊桥的 `websocket_server.host`。Docker 下若 AstrBot 与 MC
不在同一网络栈，需改为 `0.0.0.0`；Windows / Linux 同机直装则通常无需修改。
详见「网络与地址」一节。

**Q：`mc cmd` 和 `mc list` 没有输出？**
这两项依赖 RCON。请在鹊桥 `config.yml` 中设置 `rcon.enable: true` 并填写密码；
若无法开启鹊桥 RCON，可在插件配置中启用「直连 RCON 兜底」并填写服务器 RCON 信息。

**Q：死亡 / 成就 / 命令事件收不到？**
**原版端与 Velocity 不支持**这些事件，这是上游限制。

**Q：成就消息只显示「🏆 达成成就」，或干脆不显示？**
成就文本在鹊桥侧的字段名与可用性都随版本、服务端而异。**注意实测推送的字段是
`translation`，与鹊桥文档所写的 `translate` 不一致**，插件两者都接受。

插件按四级降级取值：
`translation.text` → `text` → `display.title` → `key`。
通常至少能显示 `Hot Stuff` 这类成就名或成就标识；全部缺失时才退化为
`🏆 <玩家> 达成了成就`，不会再出现整条消息丢失。

若连成就名也想显示为中文，需在鹊桥侧开启翻译（**与插件无关**）：
`config.yml` 设 `enable_translation: true`，并在鹊桥目录下建 `translate/`
文件夹、放入 `zh_cn.json`（可从客户端 jar 提取）。详见
[鹊桥翻译文档](https://github.com/17TheWord/queqiao-docs/blob/main/docs/config/translate.md)。
未开启翻译时 `translation.text` 可能是空壳，届时由 `display.title` 兜住。

**Q：群里出现的消息带花括号，如 `{"text":"Hello"}？**
非原版服务端的 `raw_message` 是文本组件格式，插件已做剥离；
若仍出现，请提交 Issue 并附上服务端类型与版本。

**Q：租赁服无法开放端口怎么办？**
将 `ws_mode` 设为 `reverse`，插件会监听端口等待鹊桥主动连入，
并在鹊桥 `websocket_client.url_list` 中填入插件地址。

**Q：为什么 `mc player` 提示依赖 RCON？**
鹊桥未提供玩家详情查询接口，本项目只能通过 RCON `data get entity` 获取，
属于能力降级，详见「功能介绍」末尾说明。

**Q：游戏内聊天想既能和 AI 说话、又能同步到群，怎么设？**
两个前缀作用方向不同且互相独立，各配一个即可，例如
互通前缀 `*`、AI 前缀 `ai`。普通聊天走互通、`ai 你好` 走 AI。
注意不要让两者相互包含。

### 鸣谢

- [鹊桥 QueQiao](https://github.com/17TheWord/QueQiao) — 提供 Minecraft 服务端连接能力
- [astrbot_plugin_minecraft_adapter](https://github.com/railgun19457/astrbot_plugin_minecraft_adapter) — 配置结构参照
- [astrbot_plugin_mcqq](https://github.com/kterna/astrbot_plugin_mcqq) — 反向 WebSocket 方案参考

### License

[AGPL-3.0](LICENSE)
