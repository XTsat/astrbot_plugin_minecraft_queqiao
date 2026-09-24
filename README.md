<div align="center">
<h1>Minecraft 鹊桥互通</h1>
<p><strong>通过鹊桥模组连接 Minecraft 服务器，实现消息互通、图片互通、服务器管理与 AI 聊天</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-v0.5.5-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; 我的世界 &nbsp;&nbsp; 鹊桥 &nbsp;&nbsp; 消息互联 &nbsp;&nbsp; 图片互通 &nbsp;&nbsp; AI聊天</sub></p>
<p><strong>中文</strong> &nbsp;/&nbsp; <a href="README_en.md">English</a></p>
</div>

## 功能介绍

通过 [鹊桥（QueQiao）](https://github.com/17TheWord/QueQiao) 模组连接 Minecraft 服务器与 AstrBot，实现群服消息互通与服务器管理。

- **群服互通**：游戏内聊天与群消息双向转发
- **图片互通**：群消息图片转发进游戏（需玩家安装 [ChatImage](https://github.com/kitUIN/ChatImage) 模组渲染）；游戏内图片 / 链接自动下载后发回群
- **事件播报**：玩家进出 / 死亡 / 成就事件转发到指定会话（死亡与成就原版端与 Velocity 不支持）
- **服务器管理**：状态查询、在线玩家列表、远程指令执行
- **Web 仪表盘**：查看各服务器状态、性能监控（TPS / 延迟）与互通终端实时日志，支持快捷广播与指令执行
- **AI 聊天**：游戏内以 `ai` 前缀发言即可与 AI 对话，回复私聊给玩家
- **多服务器**：同时连接多台服务器，各自独立配置转发会话与开关
- **灵活连接**：正向连接（插件连鹊桥）或反向连接（鹊桥连插件，适合租赁服）

## 指令

| 命令 | 权限 | 说明 |
|------|------|------|
| `/mc help` | 全部 | 显示帮助信息与自定义指令列表 |
| `/mc status [编号\|地址]` | 全部 | 查看服务器状态（在线人数、延迟等） |
| `/mc list [编号\|地址]` | 全部 | 查看在线玩家列表 |
| `/mc player [编号] <玩家ID>` | 全部 | 查看玩家信息（依赖 RCON） |
| `/mc cmd [编号] <指令>` | 管理员 | 远程执行服务器指令，受黑白名单约束 |
| `/mc say [编号] <内容>` | 管理员 | 向游戏内广播消息 |
| `/mc bind <游戏ID>` | 全部 | 绑定你的游戏ID |
| `/mc unbind` | 全部 | 解除绑定 |
| `/mc servers` | 全部 | 查看已配置服务器与连接状态 |

多台服务器时在指令前加数字编号选择目标（如 `mc cmd 1 time set day` 定向第 1 台），仅一台服务器时可省略；`mc servers` 可查看各服务器编号。

`mc status` / `mc list` 支持**地址直连**：把参数换成 `host:port`（如 `mc status 127.0.0.1:25565`），插件直接以 Minecraft SLP 协议查询**任意**服务器（版本、在线人数、延迟、MOTD、玩家名），无需配置鹊桥；省略端口默认 `25565`。

### 自定义指令

`cmd.custom_cmd_list` 支持自定义快捷指令，格式：

```
触发词 <&参数&><<>>实际指令 {参数} {sender}
```

- `<<>>` 左侧为触发模板，右侧为实际执行的指令
- `{sender}` 替换为发送者**绑定的游戏 ID**
- `<&xxx&>` 为参数占位符，左右同名即按位置替换

示例：`tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>`——用户 A 绑定游戏 ID `Misaka` 后在群内发送 `tp 114 514 1919`，实际执行 `tp Misaka 114 514 1919`。

## 配置

### 服务器连接信息

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `target_sessions` | list | 空 | **目标会话**（必填）：MC 消息转发的会话 UMO 列表，决定 MC 与群的绑定关系，不填则群里收不到消息 |
| `server_name` | string | `Server` | **服务器名称**（唯一标识），必须与鹊桥 `config.yml` 的 `server_name` 一致；多台服务器时互不相同 |
| `display_name` | string | 空 | 服务器显示名称（可中文，如 `生存服`），仅影响展示；留空用 `display_name_default` |
| `display_name_default` | string | `MC` | 显示名称默认值：`display_name` 留空时 `{display_name}` 与状态查询显示的内容 |
| `ws_mode` | string | `forward` | `forward` 插件连鹊桥；`reverse` 插件开服务端等鹊桥连入 |
| `ws_url` | string | `ws://127.0.0.1:8080/minecraft/ws` | 正向连接地址，对应鹊桥 `websocket_server` |
| `reverse_host` | string | `0.0.0.0` | 反向监听地址 |
| `reverse_port` | int | `8080` | 反向监听端口 |
| `reverse_path` | string | `/minecraft/ws` | 反向监听路径 |
| `access_token` | string | 空 | 对应鹊桥 `access_token`，留空则免鉴权 |
| `client_origin` | string | `astrbot` | 作为 `x-client-origin` 发送，非必要勿改 |

</details>

### 消息转发配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `forward_chat_to_astrbot` | bool | `true` | 转发玩家聊天到指定会话 |
| `forward_chat_format` | string | `[{display_name}]{player}: {message}` | 聊天消息格式，支持 `{player}` `{message}` `{display_name}` |
| `forward_join_leave_to_astrbot` | bool | `false` | 转发玩家进出消息（自动附带服务器显示名称，多服同群可区分来源） |
| `forward_death_to_astrbot` | bool | `false` | 转发玩家死亡消息（原版/Velocity 不支持） |
| `forward_achievement_to_astrbot` | bool | `false` | 转发玩家成就消息（原版/Velocity 不支持） |
| `auto_forward_prefix` | string | 空 | 群消息以此开头才转发到游戏；留空 = 全部转发 |
| `broadcast_format` | string | `[{platform}]{sender}: {message}` | 转发到游戏内的格式，支持 `{platform}` `{sender}` `{message}` `{display_name}` `{server_name}` |
| `platform_names` | list | `["aiocqhttp=QQ"]` | 平台名称映射：`原始平台名=显示名`，如 `aiocqhttp=QQ` |
| `broadcast_color` | string | `white` | 转发消息颜色，支持 MC 颜色名或 `#RRGGBB` |
| `mark_option` | string | `emoji` | 转发成功提醒：`text` 回复 ✅ / `emoji` 贴表情 / `none` 不提醒 |
| `mark_emoji_id` | int | `124` | 回执表情 ID（QQ 表情 ID，默认 `124` = 👌） |
| `forward_image_to_mc` | bool | `false` | 群消息图片转发进游戏（需玩家安装 ChatImage 模组才渲染，否则显示 CICode 文本） |
| `chatimage_name` | string | `图片` | 图片在游戏聊天栏的显示名称 |
| `forward_image_from_mc` | bool | `false` | 游戏内图片（CICode / 链接）自动下载后作为图片发回群 |

> 目标会话可用 AstrBot 自带的 `/sid` 指令获取：在目标群聊/私聊发送 `/sid`，回复中的 `UMO` 就是要填的值（如 `aiocqhttp:GroupMessage:123456789`）。该列表同时决定：MC 消息转发到哪些会话、哪些会话的消息转发进 MC、以及该会话的 `mc` 指令归属哪台服务器。

> `mark_option: emoji` 会给触发转发的**原消息贴表情**（不额外发消息），所有 aiocqhttp 协议端（NapCat、Lagrange、LLOneBot 等）都支持，其他平台静默跳过。

`mark_emoji_id` 常用 QQ 表情 ID：

| 常量 | ID | 表情 |
|------|----|------|
| `EMOJI_OK_GESTURE` | `124` | 👌 |
| `EMOJI_THUMBS_UP` | `76` | 👍 |
| `EMOJI_LOVE` | `66` | ❤️ |
| `EMOJI_ROSE` | `63` | 🌹 |

</details>

### 图片转发到游戏内（ChatImage）

开启 `forward_image_to_mc` 后，群消息中的图片以携带 URL 的广播形式转发进游戏，由玩家客户端自行加载渲染：

```
[QQ]群友A: [[CICode,url=https://example.com/images/example.png,name=图片]]
```

- 需为安装了 [ChatImage](https://github.com/kitUIN/ChatImage) 模组（Fabric / Forge / NeoForge）的服务器开启，否则只显示 `[[CICode,...]]` 文本
- 图片 URL 必须对玩家客户端可达；若图片没有公开 URL（日志提示「图片均无可访问的公开 URL」），开启根级开关 `enable_image_upload` 并配置 `image_upload_services`（见下方）
- 配置了 `auto_forward_prefix` 时，只有带前缀的消息里的图片才会被转发（裸图片消息不带文本，不会命中前缀）

### 游戏内图片转发到外部会话

开启 `forward_image_from_mc` 后，游戏内聊天中的 ChatImage `[[CICode,url=...]]` 代码或图片链接会自动下载并作为图片发送到群：

- `http(s)://` 链接直接下载；`file://` 本地文件仅在 AstrBot 与游戏端同机时才能读取
- 下载失败（链接失效、本地文件不可见等）时保留原始代码/链接文本
- 单张图片上限 5 MB、下载超时 15 秒

#### 内置图片 HTTP 服务

部分协议端收到的图片只有 base64 / 本地文件，没有对外可访问的 URL。此时在 `image_upload_services` 添加**「内置图片HTTP服务」**条目（模板 `builtin_http`），插件会把图片转存到内置 HTTP 服务，广播成 `{base_url}/img/<token>` 供玩家加载。**前提是 AstrBot 有公网地址**；图片字节仅在内存缓存 30 分钟（上限 500 张）。

#### 通用图床

把无公开 URL 的图片自动上传到图床换取公网链接，再广播进游戏：

1. 打开根级开关 `enable_image_upload`
2. 按需调整 `image_upload_timeout`（图床上传超时，默认 30 秒）
3. 在 `image_upload_services` 添加图床条目：默认不加载任何图床，最上方为「自定义图床」（自由填写任意上传接口），其余为预配置模板（接口与响应方式已填好，按需补 token）

| 条目字段 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `enabled` | bool | `true` | 启用此图床条目 |
| `name` | string | 空 | 显示名称（仅日志/辨识用） |
| `upload_url` | string | 空 | 图床的**上传接口地址（完整 URL，非网站首页）** |
| `token` | string | 空 | API Token（作为 `Authorization: Bearer` 请求头并附带表单字段 `token`）；免 token 留空 |
| `response` | string | `text` | 响应解析：`text` = 响应正文即链接；`json` = 取 `url` 字段（无则取第一个 `http(s)://` 字段） |
| `file_field` | string | `file` | multipart 文件字段名（个别图床为 `image`、`fileToUpload` 等） |
| `headers` | string | 空 | 自定义请求头：一行一个 `名字: 值`（或 JSON 对象） |
| `form_fields` | string | 空 | 额外普通表单字段：一行一个 `名字: 值`（或 JSON 对象） |

预配置模板：

<details>
<summary>展开预配置模板表</summary>

| 模板 | 地区 | Token | 响应 | 大小/配额 | 说明 |
|------|------|-------|------|-----------|------|
| `catbox` | 海外 | 免 | `text` | ≤200MB/张 | 匿名直传 |
| `litterbox` | 海外 | 免 | `text` | ≤1GB/张 | catbox 临时分支，图片到期自动删除（`form_fields` 已预填 `time: 72h`） |
| `imglink` | 海外 | 免 | `json` | ≤25MB/张 | 匿名直传，服务端会重新编码图片 |
| `img402.dev` | 海外 | 免 | `json` | ≤10MB/张 | 文件字段为 `image`；≤1MB 永久保存、1–10MB 保留 30 天 |
| `pngurl` | 国内 | 免 | `json` | — | 原 pngcdn.cn 迁移而来 |
| `picui` | 国内 | 免 | `json` | — | Lsky 风格接口 |
| `anyapi` | 国内中转 | 免 | `json` | 建议 ≤10MB/文件 | anyapi 中转代理 |
| `xinyew` | 国内 | 免 | `json` | — | 360 图床 |
| `xunjinlu` | 国内 | 免 | `json` | — | 多接口聚合，按文件大小自动选上游 |
| `imgloc` | 国内 | 需 | `json` | 约 6MB/张 | 路过图床，需注册获取 token |
| `see` | 国内 | 需 | `json` | ≤5MB/张 | S.EE / sm.ms，文件字段为 `smfile` |
| `imgbb` | 海外 | 需 | `json` | ≤32MB/张 | 老牌 API，文件字段为 `image` |

</details>

- 多个启用条目按列表顺序**逐个尝试**，任一成功即广播进游戏；全部失败时按「图床名: 原因」汇总告警
- ⚠️ **隐私提醒**：群图片会被上传到图床，请按需开启

### 服务器显示名称与格式变量

`server_name` 是给鹊桥用的连接标识（不能用中文）；如需在群里更好辨认多台服务器，可另填 `display_name`（仅影响展示，可写中文）：

```jsonc
"server": {
  "server_name": "survival",       // 必须与鹊桥 config.yml 一致
  "display_name": "生存服",        // 仅用于展示
  "display_name_default": "MC"     // display_name 留空时的默认展示内容
}
```

格式串占位符：

| 占位符 | 可用位置 | 含义 |
|--------|----------|------|
| `{player}` | `forward_chat_format` | 玩家名称 |
| `{message}` | 两个格式串 | 消息内容 |
| `{display_name}` | 两个格式串 | 服务器显示名称；留空时用 `display_name_default`（默认 `MC`），两者都留空才输出空串 |
| `{platform}` | `broadcast_format` | 平台名（可经 `platform_names` 映射，如 `aiocqhttp` → `QQ`） |
| `{sender}` | `broadcast_format` | 发送者名 |
| `{server_name}` | `broadcast_format` | 服务器名称（始终有值） |

示例：`display_name` = `生存服`、格式 `[{display_name}] <{player}> {message}` → `[生存服] <Steve> 大家好`；什么都不填 → `[MC] <Steve> 大家好`。

> 进出消息、`mc status` / `mc list` 标题沿用同一条取值链（`display_name` → `display_name_default` → `server_name`）；连接握手与日志仍使用 `server_name`。

### AI 聊天配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_ai_chat` | bool | `true` | 启用游戏内 AI 对话（总开关） |
| `ai_chat_prefix` | string | `ai` | 触发前缀：游戏内以 `ai 你好` 发言即触发 AI，回复私聊给玩家；留空 = 不触发 |

两个前缀作用方向不同、互相独立，一条消息只会命中其中一个：

| 前缀 | 方向 | 作用 |
|------|------|------|
| `auto_forward_prefix` | 群 → MC | 群消息以此开头才转发到游戏 |
| `ai_chat_prefix` | 游戏内 → AI | 游戏内聊天以此开头才触发 AI，不再转发到群 |

> 前缀匹配做词边界判断：以字母/数字结尾的前缀要求后跟空格或直接结束，`ai` 不会误伤 `aim`、`airport`；字母不区分大小写。两个前缀**不要相互包含**，否则同一条消息的归属会产生歧义（启动时会告警）。`ai_chat_prefix` 留空不会导致所有聊天触发 AI。

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
| `rcon_enabled` | bool | `false` | 鹊桥未开 RCON 时，改由插件直连 RCON |
| `rcon_host` | string | `localhost` | RCON 地址 |
| `rcon_port` | int | `25575` | RCON 端口 |
| `rcon_password` | string | 空 | RCON 密码 |

> ⚠️ 旧版的 `rcon_fallback` 配置已废弃，请直接填写上方四个字段。

</details>

### 插件配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `true` | 启用插件 |
| `text2image` | bool | `true` | 服务器信息渲染为图片，失败自动回退文本 |

</details>

### 重连配置

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `reconnect_interval` | int | `5` | 重连间隔（秒），随失败次数递增，上限 60 秒 |
| `max_reconnect` | int | `0` | 最大重连次数，`0` 表示无限重连 |
| `low_frequency_threshold` | int | `30` | 连续失败**超过**该次数后进入低频重试（间隔固定为 `low_frequency_interval`）；`0` 关闭低频 |
| `low_frequency_interval` | int | `300` | 低频重试间隔（秒），默认 5 分钟 |

</details>

### 性能监控

TPS 与延迟监控**默认开启、无需配置**：后台定期采集并持久化，仪表盘「性能监控」面板展示趋势图与统计摘要，参数在面板「⚙ 设置」中调整（保存即时生效）。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 启用开关 | `on` | 关闭后停止采样 |
| 采集间隔 | `60` 秒 | 最小 `10` 秒 |
| 保留天数 | `7` 天 | 超期自动清理 |
| TPS 指令 | `auto` | 自动按服务端品牌选择（Forge → `forge tps`；Fabric/Quilt → `spark tps`；Bukkit 系 → `tps`），也可手动指定 |
| 延迟探测域名 | 留空 | 直连服务器的公网地址（可含端口，如 `mc.example.com:25565`），用于测玩家视角延迟；留空不采集延迟 |

- **TPS**：经 RCON 执行 TPS 指令解析，需服务端支持对应指令（原版端不支持，显示为不可用）
- **延迟**：直连服务器做 Minecraft SLP ping（不经鹊桥中转、无需 RCON），须在设置中填写公网探测地址；服务器关闭 SLP 或地址不可达时延迟显示不可用
- 采样按天分片存储于 `data_dir/monitor/`，重启不丢；`/mc status` 会附带最近采样值

## 部署与常见问题

### 安装

1. 将本插件放入 AstrBot 的 `data/plugins/` 目录，重启 AstrBot
2. 在 WebUI 插件配置中点击「添加 MC服务器」，填写**目标会话**（必填）
3. 确保 `server_name` 与鹊桥 `config.yml` 的 `server_name` 完全一致

> AstrBot 与 MC 装在同一台机器时，默认连接信息已与鹊桥默认端口对齐，通常无需改动，填好「目标会话」即可使用。

### 网络与地址（Docker / 同机部署）

`host` 填 `127.0.0.1` 还是 `0.0.0.0`，取决于 AstrBot 与 MC 是否在同一网络栈——判断依据只有一条：**鹊桥的监听地址能否被 AstrBot 直接访问到**。

| 场景 | 鹊桥 `websocket_server.host` | 插件 `ws_url` |
|------|------------------------------|---------------|
| 同机直装（同一网络栈） | `127.0.0.1`（默认） | `ws://127.0.0.1:8080/minecraft/ws` |
| 不同机器 | 该机器的可达地址（内网 IP 或 `0.0.0.0`） | `ws://<MC 服务器 IP>:8080/minecraft/ws` |
| AstrBot 在 Docker、MC 在宿主机（或反之） | `0.0.0.0` | 指向宿主机的可达地址 |
| 各自独立容器 | `0.0.0.0` | 指向 MC 容器的映射端口或容器名 |

> `0.0.0.0` 是**监听地址**（表示监听本机所有网卡），只能填在服务端一侧（鹊桥的 `websocket_server.host`、插件的 `reverse_host`）。`ws_url` 填「从 AstrBot 所在机器能访问到 MC 服务器」的地址。改了一侧，另一侧要同步改。

排查要点：

- 日志出现 `已连接鹊桥 (ws://...)` 才算成功，仅 TCP 可连通不代表握手通过
- 持续重连且无明确报错，多为鹊桥 `host` 仍为 `127.0.0.1`（容器内只绑 loopback，收不到 docker-proxy 转发的流量）
- 启动日志的 `WebSocket Server 在 <地址>:<端口> 启动...` 可确认实际监听地址

### 配置鹊桥

在 Minecraft 服务端安装 [鹊桥](https://modrinth.com/plugin/queqiao)，并按其[文档](https://github.com/17TheWord/queqiao-docs)配置 `config.yml`：

```yaml
server_name: "Server"        # 必须与插件配置的 server_name 一致
access_token: ""             # 对应插件配置的 access_token
websocket_server:
  enable: true               # 正向连接（插件连鹊桥）需开启
  host: "127.0.0.1"          # Docker 等跨网络栈部署见上方
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

### 依赖

- Python 3.10+
- AstrBot >= 4.10.4
- `websockets`（连接鹊桥必需）
- `aio-mc-rcon`（仅在启用直连 RCON 兜底时需要）

### 常见问题

**Q：连接不上，提示鉴权失败或 404？**

检查 `server_name` 是否与鹊桥完全一致（含大小写），以及 `access_token` 是否相同。

**Q：日志一直重连，是不是该把地址改成 `0.0.0.0`？**

`0.0.0.0` 是监听地址，填在鹊桥的 `websocket_server.host`。Docker 下 AstrBot 与 MC 不在同一网络栈时才需要改；同机直装通常无需修改。详见「网络与地址」。

**Q：`mc cmd` 没有输出？**

`mc cmd` 依赖 RCON：在鹊桥 `config.yml` 设置 `rcon.enable: true` 并填密码；无法开启鹊桥 RCON 时，可在插件配置启用「直连 RCON 兜底」。

**Q：`mc list` 不开 RCON 也能看到玩家名吗？**

可以。未开 RCON 时自动回退到在线查询（SLP `players.sample`），代价是名单可能不全（原版端截断、反 bot 插件留空或塞假名）；要 100% 完整名单仍需开 RCON。回报会标注取数方式。

**Q：死亡 / 成就 / 命令事件收不到？**

原版端与 Velocity 不支持这些事件，属上游限制。

**Q：成就消息只显示「🏆 达成成就」？**

成就文本随鹊桥版本与服务端而异，插件按 `translation.text → text → display.title → key` 降级取值。要显示中文成就名需在鹊桥侧开启翻译（`enable_translation: true` + `translate/zh_cn.json`），与插件无关。

**Q：租赁服无法开放端口？**

将 `ws_mode` 设为 `reverse`：插件监听端口等待鹊桥连入，并在鹊桥 `websocket_client.url_list` 填入插件地址。

**Q：游戏内聊天想既能和 AI 说话、又能同步到群？**

两个前缀各配一个即可（如互通前缀 `*`、AI 前缀 `ai`），注意不要让两者相互包含。

### 鸣谢

- [鹊桥 QueQiao](https://github.com/17TheWord/QueQiao) — 提供 Minecraft 服务端连接能力

### License

[AGPL-3.0](LICENSE)
