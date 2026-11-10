<div align="center">
<h1>Minecraft 鹊桥互通</h1>
<p><strong>通过鹊桥模组连接 Minecraft 服务器，实现消息互通、图片互通、服务器管理与 AI 聊天</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-v0.7.2-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; 我的世界 &nbsp;&nbsp; 鹊桥 &nbsp;&nbsp; 消息互联 &nbsp;&nbsp; 图片互通 &nbsp;&nbsp; AI聊天</sub></p>
<p><strong>中文</strong> &nbsp;/&nbsp; <a href="README_en.md">English</a></p>
</div>

## 功能介绍

通过 [鹊桥（QueQiao）](https://github.com/17TheWord/QueQiao) 模组连接 Minecraft 服务器与 AstrBot，实现群服消息互通与服务器管理。

- **群服互通**：游戏内聊天与群消息双向转发；回复 Bot 转发的游戏消息时，转发进游戏的内容自动附 `@原玩家名`，游戏内一目了然是谁在群里回复
- **图片互通**：群消息图片转发进游戏（需玩家安装 [ChatImage](https://github.com/kitUIN/ChatImage) 模组渲染）；游戏内图片 / 链接自动下载后发回群
- **事件播报**：玩家进出 / 死亡 / 成就事件转发到指定会话（死亡与成就原版端与 Velocity 不支持）
- **连通通知**：服务器连通 / 连接失败后向目标会话发送提示，文案可自定义
- **免打扰时段**：按服务器设置安静时段（如 `23:00` 至 `08:00`），时段内按类型静音游戏消息与连通通知，夜里不刷群
- **服务器管理**：状态查询、在线玩家列表、远程指令执行
- **Web 仪表盘**：查看各服务器状态、性能监控（TPS / 延迟）、互通终端实时日志与连接观测（重连次数 / 阶段 / 上限告警、API 超时计数），支持快捷广播与指令执行
- **图床面板**：仪表盘顶部「🖼️ 图床」独立标签，直接管理图片转存——总开关、上传超时、图床条目增删改与顺序调整、内置 HTTP 服务运行态，内置探针图一键验证完整上传链并按 ChatImage 兼容性给出绿/黄/红三色结论
- **面板直接管理服务器**：仪表盘里即可新建服务器、启用 / 停用、改连接信息与目标会话、删除条目；未启用的服务器以灰色卡片保留在面板上，点进去一键启用，保存自动备份并热重载生效
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

### 完整配置编辑（仪表盘右上角「📝 配置」）

独立配置页已并入仪表盘：点右上角「📝 配置」在页面内切换出完整配置视图，按插件配置模板可视化编辑全部字段（含 MC 服务器、图片转存、转发与会话等），也可切到 JSON 模式直编辑；「💾 保存并重载」先备份再原子落盘并热重载，保存后自动刷新监控面板。返回监控点「📊 返回监控」。

### 面板直接管理服务器

仪表盘（插件 Pages 页面）里可以直接管理配置中的服务器条目，不必再改配置文件：

- **新建服务器**：点右上角「＋ 新建服务器」或卡片区的「＋ 新建服务器」占位卡，填服务器名称（与鹊桥 `config.yml` 一致）、显示名、连接方式与地址、Token、目标会话即可。其余字段按配置模板自动补齐，与在 WebUI 里新增的条目结构完全一致
- **启用 / 停用**：未启用的服务器**不会消失**，而是以灰色卡片（虚线边框）留在面板上，点卡片或卡片上的「▶ 启用」即可启用；运行中的服务器也可一键「⏸ 停用」
- **编辑 / 删除**：点灰色卡片打开配置弹窗，可改服务器名、显示名、连接方式（正向 / 反向）与地址、Token（留空 = 不修改）、目标会话（每行一个），或直接删除条目
- **未生效条目可见**：服务器名为空或与其它条目重名时，该条目会被主流程跳过；这类条目同样以灰色「未生效」卡片显示，便于定位问题
- 每次保存都会先把原配置备份到 `data_dir/conf_backups/`，再原子落盘并**热重载**（断开旧连接按新配置重建），失败不会污染内存中的配置

### 仪表盘图床面板

仪表盘顶部服务器标签栏最右侧新增「🖼️ 图床」独立标签，把图片转存能力做成可独立操作的面板（进入后顶部统计卡与服务器卡片区隐藏）：

- **总开关与超时**：根级 `enable_image_upload`（关闭后不再尝试上传）与 `image_upload_timeout`（上传超时，秒）在面板顶部直接切换 / 修改，保存即生效
- **条目完整增删改**：每个图床条目一张卡片，展示类型（内置 / 第三方）、启用状态、生效原因（未启用 / 地址不合法 / 响应类型错误都会标出）、地址与运行态；「新建」按配置模板补齐默认值，编辑可改全部字段，删除需二次确认
- **顺序调整**：每张卡片上有「⬆ 上移 / ⬇ 下移」按钮，可直接调整图床尝试顺序；上传时按列表**从上到下**依次尝试，越靠前越优先，保存后立即生效
- **内置 HTTP 服务运行态**：`builtin_http` 条目单独展示「运行中 / 未运行」徽标（未启动 / 已停止 / 启动失败都会如实反映）
- **🧪 测试上传**：不填任何参数，用内置 PNG 探针图按条目顺序跑一遍完整上传链，并回读图床返回的图片核对真实格式，结果按三色标注——🟢 **绿灯 = 通过**（产物格式 ChatImage 能显示）、🟡 **黄灯 = 可用但受限**（图床把图片转成了 webp 这类 ChatImage 显示不出来的格式，传得上去但游戏里看不到）、🔴 **红灯 = 失败**（按「图床名: 原因」列出），一步定位配置问题

保存全部走**局部生效**（只重建图片转存子系统，不重连任何 MC 服务器）；且图床子系统与 MC 服务器配置解耦——一台服务器都没配时图床也能独立启动。

### 仪表盘功能设置面板

仪表盘在「服务器实例状态」与「性能监控」下方还有一个可折叠的「⚙ 功能设置」面板，把**不属于监控**的开关集中在这里（折叠状态由后端记住，换设备/刷新后保持；在「全部服务器」视图下自动隐藏）：

- **AI 对话**（每台服务器独立）：启用 / 停用游戏内 AI 对话，以及触发前缀。前缀命中时该条聊天只走 AI、回复私聊给玩家，不再转发到群；留空 = 不触发 AI，普通聊天不受影响。保存后写入插件配置并即时生效（不重建连接），与 WebUI 里的 `enable_ai_chat` / `ai_chat_prefix` 是同一份配置
- **消息转发**（每台服务器独立）：聊天 / 进出 / 死亡 / 成就转发开关、聊天消息格式（`{player}` `{message}` `{display_name}` 占位符）、群 → MC 触发前缀（留空 = 全部转发）与目标会话（每行一个 UMO）。与「消息转发配置」配置表是同一份配置，保存后即时生效（不重建连接）
- **连接通知**（每台服务器独立）：服务器连通 / 连接失败后向目标会话发送通知，分别独立开关，通知文案格式均可用 `{display_name}` `{server_name}` 占位符；失败通知需断线持续超过「断连静默期」才发（期间连回不打扰），同一轮故障只发第一条。与「服务器连通通知」配置表是同一份配置，保存后即时生效（不重建连接）
- **互通终端**（每台服务器独立）：终端日志加载天数（0～30，默认 2 = 今天 + 昨天，0 = 全部保留分片）。保存在插件配置条目顶层（与 WebUI 里的 `terminal_days` 是同一份配置），保存后即时生效（不重建连接）
- 性能监控自身参数（启用、采集间隔、实时采集频率、数据保留、TPS 指令、延迟探测、默认展示）仍在监控面板右上角「⚙ 设置」弹窗里维护

### 右上角「⚙ 设置」总设置弹窗

仪表盘右上角（自动刷新开关右侧）的「⚙ 设置」打开总设置弹窗，维护**与具体服务器无关**的全局偏好：自动刷新间隔（10～3600 秒，勾选顶部「自动刷新」后生效，保存即生效）。刷新 / 重新打开页面时，仪表盘停留在上一次打开的服务器标签，不再回到「全部服务器」。

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
| `forward_chat_to_astrbot` | bool | `true` | 全量转发游戏聊天到指定会话；关闭后仅转发命中 `forward_chat_prefix` 的聊天，图片转发不受此前缀限制 |
| `forward_chat_prefix` | string | 空 | 游戏 → 群触发前缀；全量转发关闭后，只有以此前缀开头的游戏聊天才转发，转发时去掉前缀 |
| `forward_chat_format` | string | `[{display_name}]{player}: {message}` | 聊天消息格式，支持 `{player}` `{message}` `{display_name}` |
| `forward_join_leave_to_astrbot` | bool | `false` | 转发玩家进出消息（自动附带服务器显示名称，多服同群可区分来源） |
| `forward_death_to_astrbot` | bool | `false` | 转发玩家死亡消息（原版/Velocity 不支持） |
| `forward_achievement_to_astrbot` | bool | `false` | 转发玩家成就消息（原版/Velocity 不支持） |
| `auto_forward_prefix` | string | 空 | 群文本以此开头才转发到游戏；留空 = 全部转发；已开启的图片转发不受此前缀限制 |
| `forward_bot_self_messages` | bool | `false` | **转发机器人自己的消息，不剥离唤醒词**：开启后，唤醒消息按处理前原文转发（包括 OneBot 从文本中省略的 `@机器人`，单独 `@机器人` 也会转发）；同时转发消息管道回复和本插件监听到的机器人自身群消息（存在其他 aiocqhttp 适配器时按分段旁路转发，整条回复不再重复补发；仅有单个 aiocqhttp 适配器、无法旁路监听时，回退为转发整条回复），并使用可用的机器人群昵称；图片复用 `forward_image_to_mc` 和图床配置；只有未开启图片转发或图床无法提供可访问 URL 时才降级为 `[图片]` 占位，表情以 `[表情:id]` 记录；无需关闭 `ignore_bot_self_message`，也不会再次进入指令处理；仍受 `auto_forward_prefix` 过滤；本插件发群消息仍会回声抑制 |
| `broadcast_format` | string | `[{platform}]{sender}: {message}` | 转发到游戏内的格式，支持 `{platform}` `{sender}` `{message}` `{display_name}` `{server_name}` |
| `platform_names` | list | `["aiocqhttp=QQ"]` | 平台名称映射：`原始平台名=显示名`，如 `aiocqhttp=QQ` |
| `broadcast_color` | string | `white` | 转发消息颜色，支持 MC 颜色名或 `#RRGGBB` |
| `mark_option` | string | `emoji` | 转发成功提醒：`text` 回复 ✅ / `emoji` 贴表情 / `none` 不提醒 |
| `mark_emoji_id` | int | `124` | 回执表情 ID（QQ 表情 ID，默认 `124` = 👌） |
| `forward_image_to_mc` | bool | `false` | 群消息和已开启转发的 Bot 回复/自身群消息图片转发进游戏；使用所选「游戏图片模式」对应的链路 |
| `chatimage_name` | string | `图片` | 图片在游戏聊天栏的显示名称 |
| `forward_image_from_mc` | bool | `false` | 按「游戏图片模式」将游戏内图片下载后作为图片发回群；图片不受游戏 → 群触发前缀限制 |
| `mc_image_mode` | string | `chatimage` | 双向图片链路：`chatimage` 保留原行为；`e33chat` 时群图片写入 E33Chat 媒体目录，游戏图片从该目录读取并识别 E33Emote / ChatUpgrade 标记 |
| `e33chat_media_dir` | string | 空 | E33Chat 模式必填：E33Chat 服务端实际使用的媒体目录；AstrBot 运行账户必须可读写，远程服务器需挂载共享目录 |

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

### 服务器连通通知

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `notify_on_connect` | bool | `false` | 服务器连通后向目标会话发送「服务器已启动」通知；只在服务器真的启动过时发送，连接抖动不会误报（见下方说明） |
| `notify_on_connect_format` | string | `[{display_name}] 🟢 服务器已启动` | 通知文案，支持多行输入与 `{display_name}` `{server_name}` 占位符；留空用默认文案 |
| `notify_on_connect_fail` | bool | `false` | 初次连不上、已连接后断线时向目标会话发送「服务器连接失败」通知；断线需持续超过「断连静默期」仍未恢复才发送，同一轮故障只发第一条，重新连上后下一轮故障重新通知 |
| `notify_on_connect_fail_format` | string | `[{display_name}] 🔴 服务器连接失败` | 失败通知文案，支持多行输入与 `{display_name}` `{server_name}` 占位符；留空用默认文案 |
| `connect_fail_notify_delay` | int | `60` | 断连静默期（秒，0 到 3600）：断线超过该时长仍未恢复才发失败通知，期间连回则完全不通知；`0` = 立即通知 |
| `slp_address` | string | 空 | 服务器状态探测地址（如 `127.0.0.1:25565`，可省略端口，默认 `25565`）：断线期间插件用它判断服务器是否真的停了；留空则按断线时长判断（超过 30 秒才发启动通知） |

</details>

开启「服务器连通通知」后，该服务器连通时会向它的**目标会话**发送一条通知；未配置目标会话时不发送。模板里只有 `{display_name}`（服务器显示名称）与 `{server_name}`（服务器名称）会被替换，其余花括号原样保留。

「服务器已启动」只在服务器真的启动过时才发送。网络抖动、服务端卡顿或插件重载后重新连上时不会再误报：如果填了「服务器状态探测地址」（`slp_address`），插件会在断线期间直接探测该地址——服务器仍在响应说明只是连接断了（不发通知），连不上才认为是真重启；没填则按断线时长判断，超过 30 秒的重连才算「服务器已启动」，几秒就自愈的抖动保持安静。

开启「连接失败通知」后，服务器初次连不上或已连接后断线时会发送「服务器连接失败」通知，覆盖上述两种情况；同一次故障（直到重新连上）只发送第一条，不会随重连次数刷屏。断线后还会先等过「断连静默期」（`connect_fail_notify_delay`，默认 60 秒）：期间连回则一条都不发，超过静默期仍未恢复才通知，设为 `0` 则断线立即通知。反向模式下失败通知只在已建立的连接断开时发送。

### 免打扰（安静时段）

夜里不想被游戏消息刷群时，可以给每台服务器单独设一个安静时段（例如 `23:00` 至 `08:00`），时段内只静音你勾选的消息类型。

<details>
<summary>展开配置表</summary>

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `quiet_hours_enabled` | bool | `false` | 启用免打扰时段；默认关闭 |
| `quiet_hours_start` | string | `23:00` | 开始时间（AstrBot 本地时间 `HH:MM`）；与结束时间相同视为未配置 |
| `quiet_hours_end` | string | `08:00` | 结束时间（AstrBot 本地时间 `HH:MM`）；早于开始时间表示跨零点 |
| `quiet_hours_items` | list | 死亡/成就/连通/失败通知 | 时段内静音哪些类型（多选框）：`chat` 游戏聊天、`join_leave` 玩家进出、`death` 死亡消息、`achievement` 成就消息、`connect` 连通通知、`connect_fail` 连接失败通知 |

</details>

### 图片转发到游戏内

开启 `forward_image_to_mc` 后，群消息以及已开启机器人自身转发的管道回复/自身群消息中的图片，会按「游戏图片模式」转发进游戏。**ChatImage 和 E33Chat 是两条不同链路，按服务端安装的模组任选其一即可**：ChatImage 模式为 ChatImage 模组准备，通过图片 URL 转发；E33Chat 模式为 E33Chat 模组准备，通过服务端媒体 ID 转发。

ChatImage 模式示例：

```text
[QQ]群友A: [[CICode,url=https://example.com/images/example.png,name=图片]]
```

E33Chat 模式示例：

```text
[QQ]群友A: [[CICode,url=e33chat://media/0123456789abcdef0123456789abcdef,name=图片]]
```

- `chatimage` 模式用于安装了 [ChatImage](https://github.com/kitUIN/ChatImage) 的服务端；AstrBot 转发可访问的图片 URL，没有可访问 URL 时可配置 `enable_image_upload` 与 `image_upload_services`
- `e33chat` 模式用于安装了 E33Chat 的服务端，需要开启服务端媒体托管（`media_enabled`）。推荐使用下方的 MCSManager 面板 API，让 AstrBot 通过面板读写服务端媒体；游戏→群可读取 E33Chat 媒体 ID、`E33Emote` 与 `ChatUpgrade` 图片标记，并继续支持 CICode 图片 URL
- 群 → 游戏与游戏 → 群仍分别受 `forward_image_to_mc` / `forward_image_from_mc` 控制；模式选择决定开启方向使用哪条图片链路
- 图片不受 `auto_forward_prefix` 限制；启用图片转发后，裸图片消息也可转发。附带的文字会随图片一起转发

#### E33Chat 媒体配置（推荐：MCSManager 面板 API）

先确认服务端安装的是 E33Chat，并开启 `media_enabled`。然后在插件 Dashboard 的「转发功能」中选择「游戏图片模式：E33Chat 服务端媒体」，再选择「媒体存储方式：MCSManager 面板 API」，填写：

- 面板地址、API Key、目标节点 Daemon ID、实例 UUID：可在 MCSManager 面板和节点/实例详情中找到。API Key 使用面板用户权限，请妥善保管。
- 实例内媒体目录：在目标实例的文件管理器中找到 E33Chat 的 `e33chat-media` 目录，填写从实例根目录开始的路径，例如 `/world/serverconfig/e33chat-media`。不要填 Linux 主机上的 `/opt/...` 绝对路径。
- Daemon 文件传输地址（高级，可选）：通常留空，插件会使用 MCSManager API 返回的地址。只有 AstrBot 无法访问该地址（例如返回 `localhost` 或错误的内网地址）时，才填写 AstrBot 可访问的 Daemon 地址和端口。这里填写的不是面板地址。

AstrBot 所在主机需要能访问 MCSManager 面板和 Daemon 文件传输端口。保存后分别测试群→游戏、游戏→群图片转发。MCSManager API 模式不需要挂载目录，也不需要填写上面的本地媒体目录。

**备选：本地/共享目录。** 将 E33Chat 的媒体目录共享或挂载到 AstrBot 可访问的位置，在「媒体存储方式」选择「本地/共享目录」，然后把该位置填入「E33Chat 服务端媒体目录」。Windows 可填写 UNC 路径（如 `\\10.x.x.x\e33chat-media`）；Linux 可填写已挂载路径（如 `/mnt/e33chat-media`）。

### 游戏内图片转发到外部会话

开启 `forward_image_from_mc` 后，游戏内图片会按 `mc_image_mode` 选择的方式下载并作为图片发送到群，且不受 `forward_chat_prefix` 限制：

- `chatimage`（默认）：处理 ChatImage `[[CICode,url=...]]` 代码与可访问图片链接，供 ChatImage 模组显示
- `e33chat`：处理 E33Chat `[[E33Emote,url=...]]`、`[[ChatUpgrade,url=...,type=image]]` 标记和服务端托管媒体 ID，同时保留 CICode 图片 URL 与原有图片链接下载
- `http(s)://` 链接直接下载；`file://` 本地文件仅在 AstrBot 与游戏端同机时才能读取
- E33Chat 服务端媒体需选择 E33Chat 模式；使用 MCSManager API 后端时按上方填写面板配置，本地/共享目录后端才需要 `e33chat_media_dir`
- 下载失败（链接失效、本地文件不可见等）时保留原始代码/链接文本
- ChatImage / 普通链接单张图片上限 5 MB；E33Chat 媒体上限 8 MiB；HTTP 下载超时 15 秒。E33Chat 服务端媒体目录共用服务端的 512 MiB 配额与自动清理策略

#### 内置图片 HTTP 服务

部分协议端收到的图片只有 base64 / 本地文件，没有对外可访问的 URL。此时在 `image_upload_services` 添加**「内置图片HTTP服务」**条目（模板 `builtin_http`），插件会把图片转存到内置 HTTP 服务，广播成 `{base_url}/img/<token>` 供玩家加载。**前提是 AstrBot 有公网地址**；图片字节仅在内存缓存 30 分钟（上限 500 张）。该服务只做原样转存、不做转码，传什么存什么（图床检测里回读到的就是原样字节，一般亮绿灯）。以上条目均可在仪表盘「🖼️ 图床」面板里直接维护，无需改配置文件。

#### 通用图床

把无公开 URL 的图片自动上传到图床换取公网链接，再广播进游戏：

1. 打开根级开关 `enable_image_upload`
2. 按需调整 `image_upload_timeout`（图床上传超时，默认 30 秒）
3. 在 `image_upload_services` 添加图床条目：默认不加载任何图床；「新建」可选「内置图片HTTP服务」「自定义图床」（自由填写任意上传接口）或预配置模板（接口与响应方式已填好，按需补 token）

> 💡 以上三步都能在仪表盘「🖼️ 图床」面板里完成：总开关与超时在面板顶部，条目用「新建 / 编辑」按模板填写，「🧪 测试上传」可直接验证配置是否生效。

| 条目字段 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `enabled` | bool | `true` | 启用此图床条目 |
| `name` | string | 空 | 显示名称（仅日志/辨识用） |
| `upload_url` | string | 空 | 图床的**上传接口地址（完整 URL，非网站首页）** |
| `token` | string | 空 | API Token（默认作为 `Authorization: Bearer` 请求头并附带表单字段 `token`；imgbb 例外，以表单字段 `key` 提交）；免 token 留空 |
| `response` | string | `text` | 响应解析：`text` = 响应正文即链接；`json` = 取 `url` 字段（无则取第一个 `http(s)://` 字段） |
| `file_field` | string | `file` | multipart 文件字段名（img402 / imgbb 为 `image`，S.EE 为 `smfile`） |
| `headers` | string | 空 | 自定义请求头：一行一个 `名字: 值`（或 JSON 对象） |
| `form_fields` | string | 空 | 额外普通表单字段：一行一个 `名字: 值`（或 JSON 对象） |

预配置模板：

<details>
<summary>展开预配置模板表</summary>

| 模板 | 地区 | Token | 响应 | 大小/配额 | 说明 |
|------|------|-------|------|-----------|------|
| `imglink` | 海外 | 免 | `json` | ≤25MB/张 | 匿名直传，服务端会重新编码图片；偶尔较慢 |
| `img402.dev` | 海外 | 免 | `json` | ≤10MB/张 | 文件字段为 `image`；≤1MB 永久保存、1–10MB 保留 30 天；走 Cloudflare，偶发超时 |
| `pngurl` | 国内 | 免 | `json` | — | 原 pngcdn.cn 迁移而来；访客有频率限制，长期使用建议注册填 token |
| `anyapi` | 国内中转 | 免 | `json` | 建议 ≤10MB/文件 | anyapi 中转代理 |
| `see` | 国内 | 需 | `json` | ≤5MB/张 | S.EE / sm.ms，文件字段为 `smfile`，key 直接填在请求头 |
| `imgbb` | 海外 | 需 | `json` | ≤32MB/张 | 老牌 API，文件字段为 `image`，key 以表单字段 `key` 提交 |

</details>

- 只保留实测能连通的模板：`catbox` / `litterbox`（请求被拦截）、`imgloc`（接口域名已失效）、`xinyew` / `xunjinlu`（被 WAF 拦截）、`picui`（只输出 webp，游戏里显示不出来）等模板已移除；确有需要仍可用 `custom` 模板自行填写接口地址
- 上传时按图片**真实格式**携带 MIME 与文件名后缀（png / jpg / webp 等），避免图床把图片当成普通文件拒收
- 多个启用条目按列表顺序**逐个尝试**（可在面板用「⬆ 上移 / ⬇ 下移」调整优先顺序），任一成功即广播进游戏；全部失败时按「图床名: 原因」汇总告警
- ⚠️ **隐私提醒**：群图片会被上传到图床，请按需开启
- ⚠️ **webp 图片可能显示不出来**：游戏端渲染依赖 ChatImage，而 ChatImage 只认 png / jpg / jpeg / jfif / gif / ico / bmp，**不支持 webp**。群里的图片以 png / jpg 为主，但有些图床会把上传的图片统一重新编码成 webp，拿到的链接是 webp 时游戏聊天栏就显示不出图片（只留一行代码文本）。「🧪 测试上传」只传一张 PNG 并把产物读回来核对格式：产物是 png / jpg 等则亮绿灯，产物被转成 webp 则亮黄灯。看到黄灯说明该图床会把图片转成 webp，可换一个原样转存的图床（如 `pngurl`、`img402.dev`）

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
| `{display_name}` | 两个格式串、`notify_on_connect_format`、`notify_on_connect_fail_format` | 服务器显示名称；留空时用 `display_name_default`（默认 `MC`），两者都留空才输出空串 |
| `{platform}` | `broadcast_format` | 平台名（可经 `platform_names` 映射，如 `aiocqhttp` → `QQ`） |
| `{sender}` | `broadcast_format` | 发送者名 |
| `{server_name}` | `broadcast_format`、`notify_on_connect_format`、`notify_on_connect_fail_format` | 服务器名称（始终有值） |

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
