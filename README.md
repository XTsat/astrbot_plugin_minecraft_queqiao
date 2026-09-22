<div align="center">
<h1>Minecraft 鹊桥互通</h1>
<p><strong>通过鹊桥模组连接 Minecraft 服务器，实现消息互通、图片互通、服务器管理与 AI 聊天</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-v0.3.3-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; 我的世界 &nbsp;&nbsp; 鹊桥 &nbsp;&nbsp; 消息互联 &nbsp;&nbsp; 图片互通 &nbsp;&nbsp; AI聊天</sub></p>
<p><strong>中文</strong> &nbsp;/&nbsp; <a href="README_en.md">English</a></p>
</div>

## 功能介绍

通过 [鹊桥（QueQiao）](https://github.com/17TheWord/QueQiao) 模组连接 Minecraft 服务器与 AstrBot，实现群服消息互通与服务器管理。连接层使用鹊桥 V2 协议。

- **群服互通**：Minecraft 玩家聊天与其他平台消息双向转发
- **图片转发**：双向图片互通——群消息图片可转发进游戏（由 [ChatImage](https://github.com/kitUIN/ChatImage) 模组渲染）；游戏内聊天图片（CICode 代码 / 图片链接）可自动下载后发回群
- **事件播报**：玩家加入 / 离开 / 死亡 / 成就事件转发到指定会话
- **服务器管理**：服务器状态查询、在线玩家列表、远程指令执行
- **AI 聊天**：游戏内以独立前缀发言（如 `ai 你好`）即可与 AI 对话，回复私聊给玩家，不影响正常互通
- **多服务器**：同时连接多台服务器，各服务器独立配置转发会话与开关
- **灵活连接**：支持正向连接（插件连鹊桥）与反向连接（鹊桥连插件，适合租赁服）

> 鹊桥**未提供玩家详情查询接口**，`mc player` 依赖 RCON 实现。

## 指令

| 命令 | 权限 | 说明 |
|------|------|------|
| `/mc help` | 全部 | 显示帮助信息与自定义指令列表 |
| `/mc status` | 全部 | 查看服务器状态（含在线人数；服务器返回名单时也显示玩家名） |
| `/mc list` | 全部 | 查看在线玩家列表（优先 RCON，未开 RCON 时用在线查询兜底） |
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

假设用户 A 绑定了游戏 ID `Misaka`，在群内发送 `tp 114 514 1919`，实际执行 `tp Misaka 114 514 1919`。

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
| `platform_names` | list | `["aiocqhttp=QQ"]` | **平台名称映射**：把 `{platform}` 的原始平台名替换为自定义展示名，每项格式 `原始平台名=显示名`。默认自带示例 `aiocqhttp=QQ`（开箱即用）；未命中的平台保持原名，删空则不改写 |
| `broadcast_color` | string | `white` | 转发消息颜色，支持 MC 颜色名或 `#RRGGBB` |
| `mark_option` | string | `emoji` | 转发成功后的提醒方式：`text` 回复 ✅ 文本 / `emoji` 给原消息贴表情 / `none` 不提醒 |
| `mark_emoji_id` | int | `124` | **回执表情 ID**（仅 `mark_option=emoji` 时生效）。默认 `124` 为 👌，已核实的可用 ID 见下表 |
| `forward_image_to_mc` | bool | `false` | **转发图片到游戏内**：群消息里的图片自动转发到 MC。**需要游戏端安装 [ChatImage](https://github.com/kitUIN/ChatImage) 模组**才会渲染成图片，否则显示为 `[[CICode,...]]` 文本。图片以携带 URL 的广播形式发送，玩家客户端自行加载，需保证图片 URL 对玩家客户端可达（QQ 图片 CDN 通常可直接访问） |
| `chatimage_name` | string | `图片` | **游戏内图片显示名称**：ChatImage 在聊天栏显示图片时使用的名称（CICode 的 `name` 参数） |
| `forward_image_from_mc` | bool | `false` | **转发游戏内图片到外部会话**：识别游戏内聊天里的 ChatImage `[[CICode,url=...]]` 代码或直接贴出的图片链接，自动下载后作为图片消息发送。下载失败（如 `file://` 本地文件不在本机）时保留原始文本 |

> `target_sessions`（目标会话）位于服务器列表项**最上方**的「启用此服务器」下方，详见上一节的表格。UMO 可通过 **AstrBot 自带的 `/sid` 指令**获取：在目标群聊/私聊里发送 `/sid`，回复中的 `UMO` 就是要填的值，格式如`aiocqhttp:GroupMessage:123456789`。该列表同时决定三件事：**MC 消息转发到哪些外部会话**、**哪些外部会话的消息会转发进 MC**，以及**该会话里的 `mc` 指令归属哪台服务器**。

> **回执表情**：`mark_option: emoji` 会给触发转发的**原消息贴一个表情**（不额外发消息）。**所有 aiocqhttp 协议端都支持**（如 NapCat、Lagrange、LLOneBot 等）；其他平台会静默跳过，不会报错。

`mark_emoji_id` 填 **QQ 表情 ID**。以下为推荐的几个 Emoji 响应 ID：

| 常量 | ID | 表情 |
|------|----|------|
| `EMOJI_OK_GESTURE` | `124` | 👌 |
| `EMOJI_THUMBS_UP` | `76` | 👍 |
| `EMOJI_LOVE` | `66` | ❤️ |
| `EMOJI_ROSE` | `63` | 🌹 |

</details>

### 图片转发到游戏内（ChatImage 联动）

群聊里发图片，玩家想在游戏里直接看到？开启 **`forward_image_to_mc`**即可把外部会话消息中的图片自动转发进游戏。游戏端需要安装[ChatImage](https://github.com/kitUIN/ChatImage) 模组（支持 Fabric / Forge / NeoForge），它会把聊天栏里识别到的图片直接渲染出来：

```
[QQ]群友A: [[CICode,url=https://example.com/images/example.png,name=图片]]
```

- **默认关闭**：未安装 ChatImage 的服务器开启后只会看到 `[[CICode,...]]` 文本，因此请只为装了模组的服务器开启
- **URL 可达性**：图片以携带 URL 的广播形式发送，由**玩家自己的客户端**去下载，所以图片 URL 必须对玩家客户端可达。若没有公开 URL（日志提示「图片均无可访问的公开 URL」），开启根级开关 **`enable_image_upload`**，并在 **`image_upload_services`** 列表里添加**「内置图片HTTP服务」**或**第三方图床**条目接管，见下方
- **转发前缀仍然生效**：`auto_forward_prefix` 配置了前缀时，只有带前缀的消息里的图片才会被转发（裸图片消息不带文本，不会命中前缀，因此不会被转发）
- **显示名称**：`chatimage_name` 控制图片在聊天栏显示的名称，默认「图片」

### 游戏内图片转发到外部会话

玩家在游戏里贴图（ChatImage 的 `[[CICode,url=...]]` 代码，或直接在聊天里发图片链接），想在群里直接看到图片而不是一长串代码/链接？开启每台服务器的 **`forward_image_from_mc`**：

```
[MC]Steve: [[CICode,url=file:///D:/profile/Downloads/example.jpg]]
[MC]Steve: https://example.com/images/example.png
```

开启后，`http(s)://` 链接会**自动下载并作为图片发送到群**；`file://` 本地链接仅在AstrBot 与游戏端同机时才能下载，否则保留原文。原始代码/链接从文本中移除，其余文字照常转发：

- **支持两种来源**：`http(s)://` 图片链接直接下载；`file://` 本地文件只在**AstrBot 与游戏端同机（或文件对 AstrBot 可见）** 时才能读到，否则跳过
- **下载失败不丢信息**：某个图片下载失败（链接失效、`file://` 文件不在本机等）时，保留原始代码/链接文本，不会静默消失
- **大小与超时**：单张图片上限 5 MB、下载超时 15 秒，超限/超时的图片跳过
- **默认关闭**：开启后图片会被下载再发送，请按需开启

#### 内置图片 HTTP 服务（需要公网地址）

部分协议端（某些 onebot 客户端）收到的图片只有 base64 / 本地文件，没有对外可访问的URL。此时在 **`image_upload_services`** 里添加**「内置图片HTTP服务」**条目（模板 `builtin_http`），插件会把图片字节转存到内置 HTTP 服务，广播成`{base_url}/img/<token>` 让玩家客户端直接加载：

> 内置条目图片不经过任何第三方。**前提是 AstrBot 有公网地址**

> 图片字节仅在插件内存中缓存 30 分钟（上限 500 张，超时/超量自动清理），过期后游戏内图片链接失效，属正常现象。

#### 通用图床方案

把无公开 URL 的图片**自动上传到图床**，换取公网可访问的链接再广播进游戏。

1. 打开 **`enable_image_upload`**
2. 按需调整根级配置 **`image_upload_timeout`**（图床上传超时，默认 `30` 秒）：单个条目超时即视为该条目失败并自动切换列表里的下一个；超时的失败原因会明确写出「上传超时（N 秒）」，便于判断是调大超时还是换更快的图床。非正数按 1 秒计、无法解析的值回落默认 30 秒
3. 在 **`image_upload_services`** 里点「添加条目」选择图床：**默认不加载任何图床**，最上方是**「自定义图床」**（自由填写任意图床的上传接口），其余为预配置模板（接口地址与响应方式已填好，按需补 token 即可）。添加多个图床时按**列表顺序逐个尝试**，前一个失败会自动切换到下一个。模板**只展示自己需要的字段**：基础字段所有模板都有：

| 条目字段 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `enabled` | bool | `true` | 启用此图床条目 |
| `name` | string | 空 | 显示名称（仅日志/辨识用，留空用地址主机名） |
| `upload_url` | string | 空 | **图床的上传接口地址（完整 URL，不是网站首页）**，如 `https://img402.dev/api/free`、自建兰空图床的 `http://IP:7791/api/v1/upload` |
| `token` | string | 空 | 需要鉴权的图床填 API Token（作为 `Authorization: Bearer` 请求头并附带表单字段 `token` 发送）；免 token 的留空 |
| `response` | string | `text` | 响应解析方式：`text` = 响应正文就是图片链接（catbox 等）；`json` = 取 JSON 响应中键名为 `url` 的字段（无则取第一个形如 `http(s)://` 的字段，imgloc、兰空、sm.ms、pngurl、imglink 等） |
| `file_field` | string | `file` | （仅部分模板）multipart 表单里**文件字段的名称**：绝大多数图床是 `file`，个别是 `image`（如 img402.dev）或 `fileToUpload`（catbox 系），插件按此字段名发送 |
| `headers` | string | 空 | （仅部分模板）**自定义请求头**：一行一个 `名字: 值`（或 JSON 对象，如 `{"X-Api-Key":"abc"}`）；pngurl / picui 已预填必需的 `Accept: application/json`，自定义模板按需自填，其余留空 |
| `form_fields` | string | 空 | （仅部分模板）**额外的普通表单字段**：一行一个 `名字: 值`（或 JSON 对象，如 `{"time":"72h"}`）；litterbox 必填 `time` 指定保留时长，漏填服务端返回 500 |

**上传协议**：`POST <upload_url>` + multipart 文件字段按条目 `file_field`（默认 `file`；catbox.moe 与 litterbox.catbox.moe 自动特殊兼容：附带`reqtype=fileupload` + 字段 `fileToUpload`）；填了 `token` 则同时带`Authorization: Bearer <token>` 请求头与表单字段 `token`；条目配置了`headers` 则一并携带；配置了 `form_fields` 的额外字段一并作为 multipart表单发送。

- 预配置模板说明：

  <details>
  <summary>展开预配置模板表</summary>

  | 模板 | 地区 | Token | 响应 | 大小/配额 | 说明 |
  |------|------|-------|------|-----------|------|
  | `catbox` | 海外 | 免 | `text` | ≤200MB/张 | 匿名直传，依赖海外网络可达性 |
  | `litterbox` | 海外 | 免 | `text` | ≤1GB/张 | catbox 的临时分支，图片到期自动删除（`form_fields` 已预填 `time: 72h`，可改成 1h/12h/24h/72h） |
  | `imglink` | 海外 | 免 | `json` | ≤25MB/张 | 匿名直传无 30 分钟 1 次的限流；服务端会重新编码图片，不适合存档 |
  | `img402.dev` | 海外 | 免 | `json` | ≤10MB/张 | 文件字段为 `image`；≤1MB 永久保存、1–10MB 保留 30 天 |
  | `pngurl` | 国内 | 免 | `json` | — | 原 pngcdn.cn 迁移而来；访客免 token 直传 |
  | `picui` | 国内 | 免 | `json` | — | Lsky 风格接口，游客直传可用 |
  | `anyapi` | 国内中转 | 免 | `json` | 建议 ≤10MB/文件 | anyapi 中转代理 |
  | `xinyew` | 国内 | 免 | `json` | — | 360 图床，360 CDN 存储 |
  | `xunjinlu` | 国内 | 免 | `json` | — | 多接口自适应聚合，按文件大小自动选上游（≤5MB 随机接口、5–20MB 稳定接口、>20MB 拒绝） |
  | `imgloc` | 国内 | 需 | `json` | 约 6MB/张 | 路过图床，需在 imgloc.com 注册后到「API 设置」获取 token |
  | `see` | 国内 | 需 | `json` | ≤5MB/张 | S.EE / sm.ms，文件字段为 `smfile`；需在 s.ee 注册拿 API key（用户页 → 工具 → API 密钥令牌） |
  | `imgbb` | 海外 | 需 | `json` | ≤32MB/张 | 老牌 API ，文件字段为 `image`；key 在 https://api.imgbb.com/ 免费注册 |

  </details>
- **自由接入自己的图床**：选「自定义图床」模板，如自建兰空图床填`http://ip:7791/api/v1/upload` + `response=json` + token；任何「直接返回链接」的接口填 text 即可；字段名特殊的图床（如非 `file`）填 `file_field`，需要额外请求头的填 `headers`，还需要额外普通表单字段的填 `form_fields`
- 多个启用条目按列表顺序**逐个尝试**，任一成功即广播进游戏；全部失败时，转发跳过的警告会按「图床名: 具体原因」汇总列出（如`图床上传失败: catbox: Server disconnected；img402: HTTP 429 ...`）
- 上传成功会广播 `[[CICode,url=https://图床域名/...,name=图片]]`，失败则跳过并告警
- ⚠️ **隐私提醒**：群图片会被上传到图床，请按需开启；不要发不适合外传的内容

### 服务器显示名称与格式变量

<details>
<summary>展开配置表</summary>

`server_id` 是给鹊桥用的**连接标识**（受 `x-self-name` 约束，不能用中文）；如果想让多台服务器在群里更好辨认，可以另外填写 **`server_name`（服务器显示名称）**，它只影响展示，可以随意写中文：

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
| `{platform}` | `broadcast_format` | 平台名（群消息来源平台）；可经 **`platform_names`** 映射为自定义名称（如 `aiocqhttp` → `QQ`），未命中原样保留 |
| `{sender}` | `broadcast_format` | 发送者名 |
| `{server_id}` | `broadcast_format` | 服务器原始 ID（**始终有值**，需要精确标识时用） |

示例（多服同群时标明来源）：

| 配置项 | 值 | 实际效果 |
|--------|-----|--------------|
| `server_name` = `生存服`、格式 `[{server}] <{player}> {message}` | — | `[生存服] <Steve> 大家好` |
| 什么都不填、格式 `[{server}] <{player}> {message}` | — | `[MC] <Steve> 大家好`（默认值 `MC`） |
| 默认值改成 `本服`、格式 `[{server}]{player}: {message}` | — | `[本服]Steve: 大家好` |

`{platform}` 还可以通过 **`platform_names`** 映射成顺眼的名字——原始平台 ID（如 `aiocqhttp`、`qq_official`）往往又长又不好看，放进游戏里占地方。该项**默认自带示例 `aiocqhttp=QQ`**：什么都不配，aiocqhttp 在游戏内也会显示为 `QQ`；不需要改写的平台可以删掉示例项：

| 配置项 | 实际效果 |
|--------|-----------|
| `platform_names` = `aiocqhttp=QQ`、格式 `[{platform}]{sender}: {message}` | `[QQ]群友A: 你好` |
| 同一份映射再添 `telegram=电报`、`discord=DC` | 这些平台的消息也显示为映射名；未命中的平台保持原名 |

> 映射是**每台服务器独立**配置的（在「消息转发配置」分组里），不同服可以有不同的叫法；匹配忽略大小写（平台 ID 均为小写，手误大小写也能命中）；条目写法`原始平台名=显示名`，写错的条目（无 `=`、空键、空值）会被自动忽略；把整个列表删空则关闭改写，恢复显示原始平台名。

> **留空行为**：`server_name` 留空时用「显示名称默认值」（默认 `MC`，即什么都不填就是 `[MC]<玩家名>` 效果）。想让 `{server}` 输出**空字符串**（无前缀），需要把 `server_name_default` 也显式清空——此时格式串里的字面量方括号仍在（`[{server}]<{player}>` 会得到 `[]<Steve> 大家好`），干净效果就不要写方括号。想让前缀永远有值，请改用 `{server_id}`。

> 不写 `{server}` 的旧格式串完全不受影响，无需迁移。

`/mc status` 与 `/mc list` 的标题沿用同一条取值链（`server_name` → 默认值 → `server_id`），多服排障时不用再对着英文 ID 猜是哪台；连接握手与日志仍使用 `server_id`。

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

游戏内一条消息的处理顺序是：命中 `ai_chat_prefix` → 交给 AI（回复私聊给该玩家）；否则按普通聊天转发到群。

以默认配置为例（互通前缀留空 = 全部转发、AI `ai`）：

| 游戏内发言 | 结果 |
|------------|------|
| `ai 帮我算道题` | 交给 AI，私聊回复 |
| `AI 你好` | 交给 AI（前缀不区分大小写） |
| `大家好` | 转发到群 |
| `aim 很高` / `airport 到了` | 转发到群（**不**误触发 AI） |

> **前缀匹配规则**：以字母或数字结尾的前缀要求后面跟空格或直接结束，因此 `ai` 不会误伤 `aim`、`airport` 这类同词头发言；字母部分不区分大小写。以符号结尾的前缀（如 `*`、`!`）按字面匹配，无需空格。

> ⚠️ 两个前缀**不要相互包含**（例如都填 `*`，或一个为另一个的前缀），否则同一条消息的归属会产生歧义。插件会在启动时检测并输出告警日志。

> `ai_chat_prefix` 留空**不会**导致所有聊天都触发 AI——那样会把全部聊天投给 LLM，既产生噪声也消耗额度。留空即表示关闭 AI 触发，普通互通不受影响。

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
| `rcon_enabled` | bool | `false` | 鹊桥未开 RCON 时，改由插件直连 RCON |
| `rcon_host` | string | `localhost` | RCON 地址 |
| `rcon_port` | int | `25575` | RCON 端口 |
| `rcon_password` | string | 空 | RCON 密码 |

> ⚠️ 从旧版升级：此前 RCON 配置在 `rcon_fallback` 对象内（WebUI 无法编辑）。新版本中请直接在上方四个字段填写；旧 `rcon_fallback` 值在配置保存前仍生效，首次保存后以新字段为准。

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
| `low_frequency_threshold` | int | `30` | **进入低频重试的失败次数**：连续重连失败**超过**该次数后，间隔不再随失败次数递增，改为固定等待 `low_frequency_interval` 秒。默认 `30`（前 30 次正常退避，第 31 次起进入低频）；配 `0` 关闭低频，始终按退避重连 |
| `low_frequency_interval` | int | `300` | **低频重试间隔（秒）**：进入低频后的固定等待时间，默认 `300`（5 分钟）；可配更大值实现更安静的重试（长期断线时不高频打扰） |

</details>

## 部署与常见问题

### 安装

1. 将本插件放入 AstrBot 的 `data/plugins/` 目录，重启 AstrBot
2. 在 WebUI 插件配置中点击「添加 MC服务器」，**填写「目标会话」（必填）**
3. 确保 `server_id` 与鹊桥 `config.yml` 的 `server_name` 完全一致

> **默认配置即可直连本机双端**：AstrBot 与 MC 装在同一台机器时，连接信息（`ws_url` → `ws://127.0.0.1:8080/minecraft/ws`）与鹊桥默认端口已经对齐，**通常无需改动**，只要填好「目标会话」就能用。跨机器、Docker 等场景见下一节。

### 网络与地址（Docker / 同机部署）

`host` 该填 `127.0.0.1` 还是 `0.0.0.0`，**取决于 AstrBot 与 MC 是否在同一网络栈**，与操作系统无关。判断依据只有一条：**鹊桥的监听地址能不能被 AstrBot 直接访问到**。

| 场景 | 鹊桥 `websocket_server.host` | 插件 `ws_url` |
|------|------------------------------|---------------|
| Windows / Linux **同机直装**（两者同一网络栈） | `127.0.0.1`（默认，无需改） | `ws://127.0.0.1:8080/minecraft/ws` |
| AstrBot 与 MC 在**不同机器** | 该机器的可达地址（内网 IP 或 `0.0.0.0`） | `ws://<MC 服务器 IP>:8080/minecraft/ws` |
| AstrBot 在 Docker、MC 在宿主机，或反之 | **`0.0.0.0`** | 指向宿主机的可达地址 |
| AstrBot 与 MC 各自独立容器 | **`0.0.0.0`** | 指向 MC 容器的映射端口或容器名 |

> 上表中的 `127.0.0.1`、`8080`、`/minecraft/ws` 均为**默认值，都可修改**：地址按实际部署填写（见下表说明），端口对应鹊桥 `websocket_server.port`，反向模式下则对应插件的 `reverse_port`。**改了一侧，另一侧要同步改。**

> **填 `ws_url` 的原则：填「从 AstrBot 所在机器能访问到 MC 服务器」的那个地址。**同机部署就填 `127.0.0.1`；AstrBot 与 MC 不在同一台机器时，**填 MC 服务器的实际 IP**（如 `ws://192.168.1.10:8080/minecraft/ws`），不能填 `127.0.0.1` ——那在 AstrBot 上指的是 AstrBot 自己。

> **`0.0.0.0` 是「监听地址」，表示监听本机所有网卡，只能填在服务端一侧**（鹊桥的 `websocket_server.host`、插件的 `reverse_host`）。

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
- 若日志**持续重连**且无明确报错，多为 `host` 仍为 `127.0.0.1`——此时端口映射虽在宿主机监听，但容器内的鹊桥只绑在容器自己的 loopback，收不到 docker-proxy 转发的流量，连接会被立即重置
- 启动日志中的 `WebSocket Server 在 <地址>:<端口> 启动...` 可直接确认实际监听地址

### 配置鹊桥

在 Minecraft 服务端安装 [鹊桥](https://modrinth.com/plugin/queqiao) 插件/模组，并按其[文档](https://github.com/17TheWord/queqiao-docs)配置 `config.yml`：

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

> 成就名的可用性还取决于服务端：`Spigot` 的成就事件**仅包含 `key`**，`Forge 1.7.10` 缺 `display.description`。插件按`translation.text → text → display.title → key` 降级取值，因此成就名或标识总能显示出来；要显示中文需在鹊桥侧开启翻译，见「常见问题」。

### 依赖

- Python 3.10+
- AstrBot >= 4.10.4
- `websockets`（连接鹊桥必需）
- `aio-mc-rcon`（仅在启用直连 RCON 兜底时需要，缺失时其余功能不受影响）

### 常见问题

**Q：连接不上，日志提示鉴权失败或 404？**

检查 `server_id` 是否与鹊桥 `server_name` 完全一致（含大小写），以及 `access_token` 是否与鹊桥配置相同。

**Q：日志一直重连、连不上鹊桥，是不是该把地址改成 `0.0.0.0`？** 

`0.0.0.0` 是监听地址，填鹊桥的 `websocket_server.host`。Docker 下若 AstrBot 与 MC不在同一网络栈，需改为 `0.0.0.0`；Windows / Linux 同机直装则通常无需修改。详见「网络与地址」一节。

**Q：`mc cmd` 没有输出？**

`mc cmd` 依赖 RCON。请在鹊桥 `config.yml` 中设置 `rcon.enable: true` 并填写密码；若无法开启鹊桥 RCON，可在插件配置中启用「直连 RCON 兜底」并填写服务器 RCON 信息。

**Q：`mc list` 不想开 RCON 也能看到玩家名吗？**

可以。`mc list` 现在优先用 RCON `list`（完整权威），未开 RCON 时自动回退到鹊桥 `get_status` 的在线查询（SLP `players.sample`）——和你用 motd 查询站看到的一样，无需 RCON。代价是 SLP 名单可能不全（原版端会截断、反 bot 插件会留空或塞假名）；只拿到人数时也会显示「在线 N/M 人」。要 100% 完整名单仍需开 RCON。

**Q：死亡 / 成就 / 命令事件收不到？** 

**原版端与 Velocity 不支持**这些事件，这是上游限制。

**Q：成就消息只显示「🏆 达成成就」，或干脆不显示？**

成就文本在鹊桥侧的字段名与可用性都随版本、服务端而异。**注意实测推送的字段是`translation`，与鹊桥文档所写的 `translate` 不一致**，插件两者都接受。

插件按四级降级取值：`translation.text` → `text` → `display.title` → `key`。通常至少能显示 `Hot Stuff` 这类成就名或成就标识；全部缺失时才退化为`🏆 <玩家> 达成了成就`，不会再出现整条消息丢失。

若成就名想显示为中文，需在鹊桥侧开启翻译（**与插件无关**）：`config.yml` 设 `enable_translation: true`，并在鹊桥目录下建 `translate/`文件夹、放入 `zh_cn.json`（可从客户端 jar 提取）。详见[鹊桥翻译文档](https://github.com/17TheWord/queqiao-docs/blob/main/docs/config/translate.md)。

**Q：群里出现的消息带花括号，如 `{"text":"Hello"}？**

非原版服务端的 `raw_message` 是文本组件格式，插件已做剥离；若仍出现，请提交 Issue 并附上服务端类型与版本。

**Q：租赁服无法开放端口怎么办？**

将 `ws_mode` 设为 `reverse`，插件会监听端口等待鹊桥主动连入，并在鹊桥 `websocket_client.url_list` 中填入插件地址。

**Q：为什么 `mc player` 提示依赖 RCON？**

鹊桥未提供玩家详情查询接口，本项目只能通过 RCON `data get entity` 获取，属于能力降级，详见「功能介绍」末尾说明。

**Q：游戏内聊天想既能和 AI 说话、又能同步到群，怎么设？**

两个前缀作用方向不同且互相独立，各配一个即可，例如互通前缀 `*`、AI 前缀 `ai`。普通聊天走互通、`ai 你好` 走 AI。注意不要让两者相互包含。

### 鸣谢

- [鹊桥 QueQiao](https://github.com/17TheWord/QueQiao) — 提供 Minecraft 服务端连接能力

### License

[AGPL-3.0](LICENSE)
