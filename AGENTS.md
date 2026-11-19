# AGENTS.md — astrbot_plugin_minecraft_queqiao（Minecraft 鹊桥互通）

> 本文件是任何 AI 编码代理（agent）进入本项目时的**必读**工作说明书。
> 它约定插件的架构、代码规范、文档维护规则。任何对代码、配置、行为的改动，都必须同时遵守本文档的规则。
>
> 项目：`astrbot_plugin_minecraft_queqiao`（Minecraft 鹊桥互通，AstrBot 插件，Python）
>
> **来源**：本文件基于 [XTsat/agent-templates](https://github.com/XTsat/agent-templates) 的 `templates/astrbot-plugin/AGENTS.md`，最新版见该仓库 `main` 分支；已回填本项目的插件名、命令前缀、目录结构与特有约定。
> 用户说「更新 AGENTS」时按此流程：① 拉取来源模板最新版 → ② 与本地逐节比对 → ③ 合并（保留本项目已回填的内容）→ ④ 展示 diff 与改动清单，等用户确认后再落盘。**禁止整文件覆盖**。
>
> 与模板的已回填差异：采用分层多文件架构（`core/` + `services/` + `handlers/`，非单文件）；日志使用二级前缀 `[{PLUGIN_NAME}][{server_name}]`；WebUI 页面在 `pages/dashboard/`（原生 JS）；另含模板未覆盖的项目专题——鹊桥协议与连接层（6.4）、指令通道超时语义（6.5）、AI 触发（6.6）、前端持久化（5.5）。

---

## 1. 项目概览

`astrbot_plugin_minecraft_queqiao` 是 AstrBot 插件（要求 AstrBot >= 4.10.4）：通过[鹊桥（QueQiao）](https://github.com/17TheWord/QueQiao) 模组连接 Minecraft 服务器，实现群服消息互通、图片互通、服务器管理与 AI 聊天。

- 配置结构**参照** [astrbot_plugin_minecraft_adapter](https://github.com/railgun19457/astrbot_plugin_minecraft_adapter)
- 连接方式**替换**为鹊桥 V2 协议（WebSocket + `echo` 请求响应关联）
- 协议文档：https://github.com/17TheWord/queqiao-docs
- 核心能力：
  - **消息互通**：游戏 ↔ 外部会话双向转发，回环抑制、富文本剥离；回复 Bot 转发的游戏消息时自动反解玩家名并前置 `@`
  - **图片互通**：外部图片经 ChatImage / 内置 HTTP / 第三方图床进入游戏；游戏内图片与链接下载后发回外部会话
  - **服务器管理**：多服务器、状态与在线玩家、远程指令、广播；直连 SLP / RCON 兜底
  - **AI 聊天**：游戏内聊天前缀触发 LLM，回复私聊给玩家
  - **WebUI 仪表盘**：服务器配置、互通终端、性能监控、图床与面板偏好
- 最小依赖：AstrBot 运行时 + `websockets`（必需）+ `aio-mc-rcon` / `aiohttp`（惰性，缺失不影响其余功能）

### 1.1 与 adapter 的关键差异（改动前必须理解）

| 维度 | adapter | 本项目 |
|---|---|---|
| 传输协议 | 自家 MC 插件私有协议（`CONNECTION_ACK`/`CHAT_REQUEST` 等） | 鹊桥 V2（`{api,data,echo}` + 事件 `post_type`） |
| 连接寻址 | `host` + `port` + URL 上的 `token` | `server_name`≡鹊桥 `server_name`，走 `x-self-name` Header |
| 鉴权 | URL query token | `Authorization: Bearer <access_token>` Header |
| 连接方向 | 仅正向 | 正向 + 反向（`ws_mode`） |
| AI 聊天触发 | 私有 `CHAT_REQUEST` 事件 | 聊天前缀触发（`ai_chat_prefix`，无斜杠指令） |
| 玩家详情 | REST 接口 | **无对应接口**，降级为 RCON `data get` |
| 状态查询 | REST | `get_status`（需鹊桥 ≥ v0.5.0） |

### 1.2 核心文件清单

| 文件 | 必选 | 职责 |
|------|------|------|
| `main.py` | ✅ | 插件入口：`Star` 子类注册、命令组、生命周期、事件编排（`_on_queqiao_event`） |
| `core/constants.py` | ✅ | 协议标识、API/事件名、默认值、重连参数（依赖链最底层） |
| `core/models.py` | ✅ | 鹊桥事件与实体模型（防御式 `from_dict`） |
| `core/models_config.py` | ✅ | `ServerConfig`（对齐 `_conf_schema.json` 的服务器字段） |
| `core/queqiao_client.py` | ✅ | WS 客户端：正向/反向、握手、`echo` 关联、重连 |
| `core/rcon_client.py` | ✅ | 直连 RCON 兜底（惰性 import `aiomcrcon`） |
| `core/server_manager.py` | ✅ | 多服务器实例与指令执行（鹊桥优先 / RCON 兜底） |
| `handlers/commands.py` | ✅ | 命令业务逻辑、自定义指令、多服务器选择 |
| `services/` | ✅ | 绑定、转发、图床、渲染、翻译、日志、监控、指标、Web API 等服务 |
| `pages/dashboard/` | ✅ | WebUI 仪表盘（原生 HTML/CSS/JS，无框架） |
| `translations/` | ✅ | 本地翻译数据（死亡/成就/实体，随插件分发） |
| `_conf_schema.json` | ✅ | WebUI 配置 Schema（**真实扁平结构**） |
| `metadata.yaml` | ✅ | 插件元数据（name/display_name/version/desc/author/repo/tags/platform） |
| `README.md` / `README_en.md` | ✅ | 中文/英文文档（中文为权威源） |
| `CHANGELOG.md` | ✅ | 变更日志（分组式） |
| `tests_offline.py` | ✅ | 离线逻辑自检（桩替代 astrbot/websockets） |
| `LICENSE` | ✅ | 许可证 |
| `logo.png` | ✅ | 插件图标 |
| `requirements.txt` | 可选 | 运行时依赖（当前仅 websockets / aio-mc-rcon / aiohttp） |

---

## 2. 目录结构与架构

### 2.1 项目结构

```
astrbot_plugin_minecraft_queqiao/
├── main.py                 # 插件入口：注册、命令组、生命周期、事件编排
├── core/                   # 核心层：配置模型 + 协议模型 + 连接管理
│   ├── constants.py        #   常量（协议标识/默认值/重连参数）—— 零内部依赖
│   ├── models.py           #   鹊桥事件与实体模型（防御式 from_dict）
│   ├── models_config.py    #   ServerConfig（对齐 _conf_schema.json）
│   ├── queqiao_client.py   #   WS 客户端：正/反向、握手、echo 关联、重连
│   ├── rcon_client.py      #   直连 RCON 兜底（惰性 import aiomcrcon）
│   └── server_manager.py   #   多服务器实例与指令执行（鹊桥优先/RCON 兜底）
├── services/               # 服务层
│   ├── binding.py          #   账号↔游戏ID 绑定（原子写）
│   ├── message_bridge.py   #   双向转发 + 回环抑制 + 富文本剥离
│   ├── image_host.py       #   内置图片 HTTP 服务（/img/<token>）
│   ├── image_bed.py        #   图片转存条目（内置 HTTP + 第三方图床统一接口）
│   ├── renderer.py         #   状态/玩家列表图片渲染（不可用时回退文本）
│   ├── translator.py       #   本地翻译（翻译键 / 英文 → 中文）
│   ├── panel_prefs.py      #   面板偏好落盘（panel_prefs.json，替代 localStorage）
│   ├── terminal_log.py     #   互通终端日志按天分片持久化
│   ├── metrics.py          #   运行指标 + 事件环形队列 + SSE 发布
│   ├── monitor.py          #   TPS / 延迟采样、聚合与落盘
│   ├── slp_ping.py         #   Minecraft SLP 直连延迟测量（零第三方依赖）
│   ├── host_mem.py         #   宿主机物理内存读取与鹊桥口径修正
│   └── web_api.py          #   面板后端 API（HTTP + SSE）与配置/偏好读写
├── handlers/
│   └── commands.py         #   命令业务逻辑 + 自定义指令 + 多服务器选择
├── pages/dashboard/        #   WebUI 仪表盘（原生 JS/CSS，无框架）
├── translations/           #   本地翻译数据（死亡/成就/实体，随插件分发）
├── tests_offline.py        # 离线逻辑自检（桩替代 astrbot/websockets）
├── metadata.yaml / _conf_schema.json / README.md / README_en.md / CHANGELOG.md / LICENSE
```

### 2.2 架构风格：分层多文件

本项目**固定采用分层多文件风格**（模板 §2.2），依赖方向严格单向：

```
main.py → handlers / services → core
core/constants.py 位于最底层，零内部依赖，不得 import 本插件其它模块
```

- `core/`：核心业务层，只做协议、配置模型、连接与服务器实例，不接触 WebUI 与命令展示
- `services/`：可复用的服务（绑定、转发、图床、渲染、翻译、日志、监控、指标、Web API），可 import `core`，禁止 import `main`
- `handlers/`：命令业务逻辑与多服务器选择，可 import `core` / `services`，禁止 import `main`
- `main.py`：编排层，持有各服务实例、注册命令与事件，不实现具体业务细节

新增代码归位：

- 新常量 / 协议名 / 事件名 → `core/constants.py`，**禁止在业务代码里硬编码事件名或 API 名字符串**
- 新配置项 → `_conf_schema.json` + `core/models_config.py`
- 新工具 / 服务 → `services/`；新命令业务 → `handlers/commands.py` 或 `main.py` 命令组

### 2.3 核心数据流

```
鹊桥 WS 事件 → QueQiaoClient 分发 → main._on_queqiao_event
  → 聊天（PlayerChatEvent）：_resolve_ai_question 命中 ai_chat_prefix → 交给 LLM → 私聊回复
                             否则 MessageBridge 转发到已绑定的 target_sessions
  → 进出 / 死亡 / 成就（notice）：翻译与格式渲染 → 转发 + 终端记录
  → 指令事件（PlayerCommandEvent）：放行进互通流程，不进入 AI 分支

外部消息（@filter.event_message_type(ALL) → on_message）
  → 自定义指令匹配 → 已绑定群转发到游戏（图片转 ChatImage 代码）
  → 回环抑制窗口内不重复转发
```

### 2.4 WebUI 页面与后端 API

- 页面：`pages/dashboard/`（`index.html` + `app.js` + `config-view.js` + `style.css`），原生 JS，无构建步骤
- 后端：`services/web_api.py` 的 `WebApiController.register_routes()` 通过 `context.register_web_api()` 注册路由，提供 JSON 接口与 SSE 实时事件流
- 依赖注入：`main.py` 构造 `WebApiController` 时传入 server_manager / binding / image_bed / metrics / terminal_logs / monitor / panel_prefs 等实例
- 改接口契约时**同时改前端与后端**，并同步 `tests_offline.py` 中对应的路由断言

---

## 3. 技术栈与依赖

- **Python 3.10+**（AstrBot 4.x 最低要求），现代联合类型写法（`dict | None`、`list[dict]`）
- **AstrBot API**：`astrbot.api.star`（register, Star, Context, StarTools）、`astrbot.api.event`（filter, AstrMessageEvent, MessageChain）、`astrbot.api`（logger, AstrBotConfig）、`astrbot.api.message_components`（Plain / Image / Reply）、`astrbot.api.web`（Web API 响应）、`astrbot.core.star.filter.command`（GreedyStr）
- **依赖管理**：`requirements.txt` 声明。`websockets>=12.0` 为鹊桥连接必需；`aio-mc-rcon>=3.2.0`（直连 RCON 兜底）与 `aiohttp>=3.11.18`（内置图片 HTTP 服务）**一律惰性 import**，缺失时相关功能降级，不影响其余功能
- **禁止引入**：不引入与原功能无关的依赖；非必要不新增 `requirements.txt` 声明

### 3.1 鹊桥版本门槛（写进文档时必须如实标注）

| 能力 | 最低鹊桥版本 |
|---|---|
| API V2（broadcast/私聊/title/actionbar/rcon） | v0.2.11 |
| 事件 V2 | v0.3.0 |
| `Translate` 模型（死亡/成就文本） | v0.4.1 |
| `get_status` | v0.5.0 |

### 3.2 服务端差异（解析必须容忍）

- 原版端 `Player` 仅 `nickname`；Velocity 仅 `nickname`/`uuid`/`is_op`
- Spigot/Paper/Folia 无 `max_health`；Folia 可能缺 `address`
- **死亡 / 成就 / 命令事件在原版端与 Velocity 完全不支持**
- `raw_message` 在非原版端可能是 JSON 文本组件 → 转发前必须 `component_to_text()` 剥离

---

## 4. 核心代码规范

### 4.1 插件骨架

```python
import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from .core.constants import PLUGIN_DATA_DIR, PLUGIN_NAME
from .core.server_manager import ServerManager

DEFAULT_TIMEOUT = 30

@register(PLUGIN_NAME, "XTsat", "插件描述", "vX.Y.Z", "https://github.com/XTsat/astrbot_plugin_minecraft_queqiao")
class MinecraftQueQiaoPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        data_dir = Path(StarTools.get_data_dir(PLUGIN_DATA_DIR))
        data_dir.mkdir(parents=True, exist_ok=True)
        # 初始化各服务（server_manager / binding / bridge / web_api ...）

    @filter.command_group("mc")
    def mc_group(self) -> None:
        """Minecraft 服务器管理命令"""
        pass

    @mc_group.command("status")
    async def cmd_status(self, event: AstrMessageEvent, target: str = ""):
        """查看服务器状态（可指定数字编号或 host:port 地址直连查询）"""
        yield event.plain_result("结果")
```

> `@register` 的版本号只是注册信息，**不是版本源**：插件版本以 `metadata.yaml` 的 `version` 为准（见 7.1）。日常提交不动它与 README 徽章；准备发布时才按 7.1 一次性同步到同一版本号。

### 4.2 命名约定

| 元素 | 约定 |
|------|------|
| 模块级常量 | `UPPER_SNAKE`（`DEFAULT_TIMEOUT`、`PLUGIN_DATA_DIR`） |
| 私有方法 | `_` 前缀 + `snake_case`（`_resolve_ai_question`、`_on_queqiao_event`） |
| Web API 方法 | `api_` 前缀 |
| 命令方法 | `cmd_` 前缀 |
| 业务处理方法 | `handle_` 前缀（`handle_status`、`handle_bind`） |
| 类名 | `PascalCase`（`MinecraftQueQiaoPlugin`、`ServerManager`） |
| 文件名 | `snake_case`（`queqiao_client.py`、`models_config.py`） |

### 4.3 类型与语法

- Python 3.10+ 现代联合类型写法（`dict | None`、`list[dict]`、`tuple[str, str]`）
- 函数签名**必须完整类型注解**（参数 + 返回类型）；用 `yield` 返回结果的命令/事件处理方法标注为 `AsyncGenerator[MessageEventResult, None]`
- 禁止 `Any` 作为类型注解（调用方签名强制要求时除外）
- 禁止 `# type: ignore`（无理由的类型作弊）

### 4.4 注释规范

- 注释规范见第 7 章 [7.3 注释规范](#73-注释规范)

### 4.5 日志

- 统一 `logger.info/warning/error`，**必须带二级前缀** `[{PLUGIN_NAME}][{server_name}]`，如 `[astrbot_plugin_minecraft_queqiao][生存服] 连接成功`
- 错误信息带 emoji 前缀（如 `❌`、`⚠️`）
- 精确捕获异常类型（`asyncio.TimeoutError`、`OSError`），禁止空 `except: pass`（除非注释说明理由）
- 异常分类记录：ValueError = 非法参数，OSError = 文件/IO 错误，各自记录，单条失败不影响其它服务器/规则

### 4.6 错误处理与防御性编程

- 面对不规范的输入必须优雅 fallback（配置值可能是字符串、事件字段可能缺失）
- 外部 IO（文件、WS、HTTP、LLM）必须 try/except 并记录日志，**不允许静默吞异常**
- 配置值防御式校验：`max(1, _to_int(...))`、`(TypeError, ValueError)` → 默认值
- 降级链路清晰：鹊桥 → 直连 RCON → 可操作提示；渲染 → 文本；翻译未命中 → 原文

### 4.7 并发

- 异步方法使用 `async/await`，**禁止阻塞事件循环**
- 批量/后台任务用 `asyncio.create_task` 并保留任务句柄，`terminate()` 中统一取消
- 采样、清理等周期任务用 `asyncio.sleep` 循环，退出时取消，避免僵尸任务
- 文件/网络重活避免阻塞主循环（AstrBot 的 t2i 等能力本身异步）

### 4.8 回复消息

- 统一 `yield event.plain_result(...)`
- 用户可读输出用中文 + emoji 图标风格（`❌` 错误、`✅` 成功）
- 多服务器场景的提示必须带编号列表，便于用户选择目标

### 4.9 权限控制

- 管理类命令加 `@filter.permission_type(filter.PermissionType.ADMIN)`（如 `/mc cmd`、`/mc say`）

### 4.10 AstrBot API 导入路径（写错会导致插件加载失败）

**不要凭记忆猜导入路径**，以下均已对照真实 AstrBot 源码核实：

| 符号 | 正确来源 | 备注 |
|---|---|---|
| `AstrBotConfig` | `astrbot.api` | |
| `logger` | `astrbot.api` | 会按调用方模块自动路由到插件专属 logger |
| `AstrMessageEvent` | `astrbot.api.event` | |
| `filter` | `astrbot.api.event` | 是**子包**，不是 `__init__` 里的名字，但可导入 |
| `MessageChain` | `astrbot.api.event` | |
| `Context` | **`astrbot.api.star`** | ⚠️ **`astrbot.api` 没有它** |
| `Star` / `StarTools` / `register` | `astrbot.api.star` | |
| `GreedyStr` | `astrbot.core.star.filter.command` | |
| `Plain` / `Image` / `Reply` | `astrbot.api.message_components` | |
| `error_response` / `json_response` / `stream_response` | `astrbot.api.web` | Web API 响应工具 |

> 已知踩坑：曾写成 `from astrbot.api import Context`，导致
> `cannot import name 'Context' from 'astrbot.api'` 插件加载失败。
>
> `tests_offline.py` 的桩**必须忠实反映真实 API**（尤其 `astrbot.api` 不得提供
> `Context`），否则桩会掩盖此类错误——第 16 组断言专门守卫这一点。
>
> 另注：`LLMResponse.completion_text` 已被官方标记「过时，推荐 `result_chain`」，
> 目前仍可用；若未来移除需改 `_ask_llm()`。
>
> 核实方式：真实 AstrBot 源码在 `/vol2/@appdata/deepseek.harness/home/astrbot/astrbot/`，
> 兄弟插件在 `/vol2/@appdata/deepseek.harness/home/astrbot_plugin/`。

---

## 5. 配置与数据文件

### 5.1 配置 Schema（_conf_schema.json）

- 本项目 Schema 是**真实扁平结构**（不是模板示意里的 `schemaVersion/fields`）
- 顶层键：`enabled`（总开关）、`mc_servers`（`template_list` 服务器条目）、`image_upload`（图片转存分组：`enabled` 总开关 / `timeout` 上传超时 / `services` 图床条目 `template_list`）；旧的根级 `enable_image_upload` / `image_upload_timeout` / `image_upload_services` 仅作为隐藏的迁移来源保留（`invisible: true`），读取一律走 `core.models_config.image_upload_settings()`
- 新增配置项 → **先在 `_conf_schema.json` 补 schema**（type/hint/default/options），再在代码中实现读写；`hint` 用中文，作为文档里的「中文名」
- 多服务器配置一律落在 `mc_servers` 条目内，不要新增平级「服务器名」字段
- 配置项在文档（README 配置表、CHANGELOG）中引用时，**中文名在前、英文 key 在后**：统一写成「中文名（`key`）」形式，例如「超时时间（`image_upload.timeout`）」；中文名取自 `_conf_schema.json` 的 `hint` 字段，`key` 用反引号包裹

### 5.2 新增配置项流程

1. 改 `_conf_schema.json`（真实扁平结构）
2. 改 `core/models_config.py` 的 `ServerConfig` 字段 + `from_dict()` 兜底解析
3. 在业务代码读取时保持防御式（WebUI 值可能是字符串）
4. 更新 `README.md` 与 `README_en.md` 的配置表
5. 面板可改的字段需同时处理「保存即生效」路径（`SOFT_CONFIG_KEYS` 软更新 + `/config/server/update`），避免要求重启

### 5.3 配置读取与默认值

- 配置持久化：`self.config[...]` 读写 → `self.config.save_config()` 保存
- 服务器字段解析集中在 `ServerConfig.from_dict()`，缺字段回落到 `_conf_schema.json` 的默认值
- 读取时防御式转换：布尔/整数用 `_to_bool` / `_to_int`，非法输入回落默认值
- `forward_chat_prefix`（游戏 → 群）与 `ai_chat_prefix`（游戏 → AI）互相包含时 `ServerConfig.prefixes_conflict` 为真，启动时告警：两者竞争同一条游戏聊天

### 5.4 运行时数据与持久化

数据目录：`StarTools.get_data_dir("astrbot_plugin_minecraft_queqiao")`

| 路径 | 内容 |
|---|---|
| `bindings.json` | 外部账号 ↔ 游戏 ID 绑定 |
| `panel_prefs.json` | 面板偏好（`active_tab` / `auto_refresh` / `auto_refresh_interval` / `settings_collapsed`） |
| `terminal_logs/YYYY-MM-DD.json` | 互通终端日志（按天分片，默认保留 30 天，每服环形 300 条） |
| `monitor/<server>/YYYY-MM-DD.jsonl` | TPS / 延迟采样（按天分片） |
| `monitor/settings.json` | 监控设置（实时频率、保留期等） |

写入要求：`encoding="utf-8"` + `ensure_ascii=False`；原子写入（先写 `.tmp` 再 `replace`）；写操作持锁（`asyncio.Lock` 或线程锁）；旧版单文件（如 `terminal_logs.json`）启动时迁移并备份 `.bak`。

### 5.5 前端页面持久化约束（改 pages/ 前必读）

AstrBot 插件页面运行在**沙箱 iframe**（`dashboard/src/views/PluginPagePage.vue`：
`sandbox="allow-scripts allow-forms allow-downloads"`，**没有 `allow-same-origin`**）。
这种沙箱下访问 `localStorage` / `sessionStorage` / `document.cookie` 会**直接抛
SecurityError**，不是返回空——任何「try/catch 包一下就能用」的假设都无效
（实测：tab 记忆写不进也读不出，静默回退默认值）。

因此：

- **前端任何需要「跨刷新 / 跨设备保持」的状态，权威值一律走后端落盘**
  （本项目用 `panel_prefs.json` + `/panel/prefs` API，见
  `services/web_api.py::set_panel_prefs`：白名单字段、钳制校验、合并原子落盘）
- 已按此模式落盘的偏好：`active_tab`（当前服务器视图）、`auto_refresh`
  （自动刷新开关）、`auto_refresh_interval`（间隔秒数）、
  `settings_collapsed`（功能设置面板折叠）
- 例外：`terminal_days`（互通终端加载天数）早期也走 panel_prefs，后迁为
  **每台服务器独立配置**（conf 条目顶层 + `SOFT_CONFIG_KEYS` 软更新 +
  `/config/server/update`），前端按当前服务器读取；`set_panel_prefs` 仍保留
  该字段仅作旧客户端兼容，前端不再写入
- 浏览器存储最多作「启动缓存」：访问必须 try/catch，加载后以异步拉回的后端
  值为准覆盖；**不得**把用户可见状态只存在浏览器
- 新增需持久化的前端状态时：先在后端 `set_panel_prefs` 加白名单字段（含
  类型/长度校验与钳制），再在前端异步写 + 异步恢复；不要在 iframe 里依赖
  任何本地存储

---

## 6. 指令注册、事件与消息链路

### 6.1 指令注册模式

```python
@filter.command_group("mc")            # 指令前缀 /mc
def mc_group(self) -> None:
    pass

@mc_group.command("sub")               # 子命令 /mc sub
@filter.permission_type(filter.PermissionType.ADMIN)
async def cmd_sub(
    self, event: AstrMessageEvent
) -> AsyncGenerator[MessageEventResult, None]:
    yield event.plain_result("结果")
```

### 6.2 命令清单

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

- 多服务器时命令可带数字编号（`/mc status 2`）；仅一台时可省略，多台未指定时返回带编号列表的提示
- `/mc status`、`/mc list` 支持直接传 `host:port` 走 SLP 直连查询（不依赖鹊桥）
- 命令表新增/删除时同步更新 `README.md` 与本表

### 6.3 事件监听与消息转发

- 外部消息统一由 `@filter.event_message_type(filter.EventMessageType.ALL)` 的 `on_message` 处理：
  - **不要用 `is_at_or_wake_command` 短路**：QQ 回复/转发 Bot 消息时客户端会自动附带 @Bot，若在此 return，这类回复永远无法转发到游戏；空消息（无文本无图片）由方法内统一过滤
  - 先匹配自定义指令；未命中则转发到该会话绑定的 `target_sessions`
  - 图片随消息一起转发：外部图片转 ChatImage 代码（需玩家安装 [ChatImage](https://github.com/kitUIN/ChatImage) 模组），无公开 URL 的图片走内置 HTTP / 图床条目
- 回复 Bot 转发的游戏消息时，转发进游戏的内容自动反解原玩家名并前置 `@`：
  - 按 `forward_chat_format` 正向反解（默认 `[{display_name}]{player}: {message}`），优先匹配服务器 `display_name`
  - 非游戏消息、非法玩家名、空引用文本一律不加 `@`
- 免打扰时段（`quiet_hours_*`）是**发送侧门禁**：`MessageBridge.forward_event()` 与
  `main._notify_server_online` / `_notify_server_fail` 只在「发出去」这一步拦截，事件本身
  照常写 metrics 与 terminal_logs（静音 ≠ 丢事件）。判断统一走
  `ServerConfig.quiet_suppresses(item)`（`core/models_config.py`），项目 key 用
  `core/constants.py` 的 `QUIET_ITEM_*`，禁止在业务代码里硬编码字符串
- 鹊桥事件由 `QueQiaoClient` 分发到 `main._on_queqiao_event`，再按 `post_type` / 事件名分流（见 6.4）

### 6.4 鹊桥协议与连接层（改动连接层前必读）

#### 6.4.1 握手 Header

| Header | 必填 | 说明 |
|---|---|---|
| `x-self-name` | ✅ | 取 `server_name`，**必须与鹊桥 config.yml 的 `server_name` 一致** |
| `Authorization` | 选填 | `Bearer <access_token>`，token 为空时不发送 |
| `x-client-origin` | 建议 | 取 `client_origin`（默认 `astrbot`），用于防重复连接与自环 |

#### 6.4.2 请求 / 响应

```json
// 请求
{"api": "broadcast", "data": {"message": [{"text": "hi", "color": "white"}]}, "echo": "<uuid>"}
// 响应
{"code": 200, "api": "broadcast", "post_type": "response", "status": "SUCCESS", "echo": "<uuid>"}
```

- **`call_api()` 必须在发送前登记 waiter**，否则鹊桥的快响应会因找不到 `echo` 被丢弃
- 消息内容一律是 **Minecraft 文本组件**（V2 不再手动解析 JSON）
- `post_type` 为 `message` 或 `notice` 时按事件处理；`response` 走 `echo` 关联
- 事件名 / API 名常量集中在 `core/constants.py`，**禁止在业务代码里硬编码字符串**

#### 6.4.3 连接层约束

- 反向模式下**同端口多服务器共享一个 WS Server**（`SharedReverseServer`），按 `x-self-name` 路由；不要每台服务器各起一个 listener
- 致命错误不重试：关闭码 `{1003,1008,1010}`、HTTP `{401,403,404}`
- 重连等待 `min(reconnect_interval × retries, 60)`；连续失败超过阈值后进入低频静默重试（默认 300 秒，阈值 0 表示关闭低频）
- 连接断开时必须 `_fail_pending()`，否则调用方永久挂起
- 「连接结束」必须在**所有路径**上被识别：正向模式对端发 close frame 时 `async for`
  是正常结束、不抛异常，也要走 `_on_lost`（否则 `_connected` 假活、未决请求挂到超时、
  下一次握手失败还会被记成误导性的断开原因）；反向模式收尾统一走
  `_finish_reverse_connection()`，被新连接替换掉的旧连接直接返回，既不误报断开也不
  清掉新连接的未决请求
- 断线通知**必须**经「断连静默期」（`connect_fail_notify_delay`）过滤：`_on_lost` 只调
  `_schedule_fail_notice()`，期间连回由 `_on_established()` 取消计时。禁止在重连循环里
  直接 `await` 失败回调（慢的会话发送会推迟重连），也**不得**在静默期内或连回时补发
  「已恢复」消息（连回即完全静默）

### 6.5 指令通道与「超时 ≠ 失败」

`ServerInstance.execute_command()` 的优先级：**鹊桥 `send_rcon_command` → 直连 RCON 兜底**。
两条通道都不可用时返回 `None`（调用方据此给出可操作的提示，而非静默失败）。

**超时 ≠ 失败**（改回执/兜底逻辑前必读）：鹊桥 WS 发送成功但 `API_TIMEOUT`
内无响应时抛 `QueQiaoTimeout`——请求大概率已投递执行，只是响应慢/丢失。
此时**禁止**换通道重发（消息/指令会重复两遍，实测发生过 AI 回复发两遍）：

- 私聊回复（`send_private_message`）与 RCON（`send_rcon_command`）超时向上抛，
  由调用方放弃本次发送，不得自动兜底重发
- 展示类（broadcast / title / actionbar）超时在封装层按已投递处理返回 True
- 仅「确定失败」（未连接 / 鹊桥明确报错）才允许走兜底通道

### 6.6 AI 触发与三个前缀（不可混淆）

游戏内 AI **仅由聊天前缀触发**（`PlayerChatEvent` + `ai_chat_prefix`，默认 `#`），全端可用。

> **明确不做斜杠触发**：本插件运行在 AstrBot 侧，无法向 Minecraft 注册真实指令。
> 且斜杠输入在游戏内属于**指令**而非聊天：Fabric 侧 `onChatMessage` 直接
> `if (message.startsWith("/")) return;`，Spigot 侧走 `PlayerCommandPreprocessEvent`
> 而不进 `AsyncPlayerChatEvent`。因此 `/ai 你好` **既不会触发 AI，也不会转发到群**
> ——它压根不会进入聊天事件。玩家只会看到原版 `Unknown command` 报错。
> 不要再引入 `ai_command_*` 配置或 `PlayerCommandEvent` 触发路径；
> 若确实需要原生指令，应由服务端侧插件提供。

前缀语义：

**三个方向各有一个开关 + 一个前缀**：开关是总闸（关闭即整条链路静音、不看前缀），
前缀只负责筛消息。schema 上成对落在 `prefix` 分组，运行时映射到扁平属性。

配置页只保留**一个**多选框 `prefix.enabled_directions`（`type: "list"` +
`render_type: "checkbox"`），勾选值即启用的方向；运行时仍读三个独立布尔，
由 `PREFIX_DIRECTION_FLAGS` 双向翻译。**同一开关不得在配置里出现两处**。

| 多选框选项 | 运行时属性 | 方向 | 默认 |
|---|---|---|---|
| `group_to_game` | `enable_relay_to_mc` | 群 → MC | 勾选 |
| `game_to_group` | `forward_chat_to_astrbot` | 游戏内 → 群 | 勾选 |
| `game_to_ai` | `enable_ai_chat` | 游戏内 → AI | 勾选 |

| 配置项 | 方向 | 默认值 | 语义 |
|---|---|---|---|
| `auto_forward_prefix` | 群 → MC | 留空 | 群消息以此开头才转发到游戏；留空 = 全部转发（仅对已绑定 `target_sessions` 的群生效）；已开启的图片转发不受此前缀限制 |
| `forward_chat_prefix` | 游戏内 → 群 | 留空 | 游戏聊天以此开头才转发到群，转发时去掉前缀；留空 = 全部转发；图片转发不受此前缀限制 |
| `ai_chat_prefix` | 游戏内 → AI | `#` | 游戏内聊天以此开头才触发 AI；留空 = 全部触发（所有聊天都交给 AI，不再转发到群） |

**三个前缀统一遵循「留空 = 全部命中」**：`prefix_matches("", text)` 恒为真，
各调用方不得再自行维护空值分支（`should_relay` 曾单独写 `if not prefix: return True`，
已收敛到 `prefix_matches`）。默认 AI 前缀是 `#`：符号结尾无需空格，
`#你好` 直接命中。

不变式（改事件编排时必须保持）：

- 游戏内一条消息**只命中一条路径**：先调 `_resolve_ai_question()`，返回非 None 即交给 LLM 并 return，不再转发
- `ai_chat_prefix` 留空 = 全部触发，此时**不告警**「前缀冲突」以外的歧义（转发方向被 AI 吞掉是用户显式选择）；`prefixes_conflict` 在 AI 前缀留空时为真，启动告警提示群消息会变少
- **总开关优先于前缀**：`enable_relay_to_mc` / `forward_chat_to_astrbot` / `enable_ai_chat`
  任一为假即整条链路静音，前缀配置一律不再参与判断（此前 `forward_chat_to_astrbot`
  曾是「全量转发」开关、会绕过前缀，统一成总闸后不再绕过）
- **面板保存必须写回 `payload.prefix`**：面板把三个前缀放在 `prefix` 分组提交，
  后端漏读会表现为「保存后又被旧值覆盖」，改动 `update_config_server` 时不可回归
- 两个前缀互相包含时 `ServerConfig.prefixes_conflict` 为真，启动时告警
- 指令事件（`PlayerCommandEvent`）**不得**进入 AI 分支，应放行给互通流程
- 触发后内容为空（`ai`）不得向 LLM 发请求
- 前缀匹配一律走 `core/constants.py` 的 `prefix_matches()` / `strip_prefix()`，
  **禁止直接用 `str.startswith`**：短前缀（`ai`）必须做词边界判断，
  否则 `aim`、`airport` 会被误判；纯字母前缀忽略大小写

### 6.7 自定义指令

- 自定义指令来自每台服务器配置的 `custom_cmd_list`（schema 的「自定义指令映射」），在 `on_message` 中先于转发匹配
- 指令执行走 6.5 的指令通道语义（超时不得重发）
- 新增/修改自定义指令相关配置时同步更新 README 的「指令配置」章节

---

## 7. 文档维护规范（强制，不可省略）

> 本项目的**硬性要求**：任何改动在合并前，必须同步维护 `README.md` / `README_en.md` 与 `CHANGELOG.md`。未同步文档 = 任务未完成。

### 7.1 CHANGELOG 维护

#### 流程

- 日常改动先记在 `## [Unreleased]` 段（顶部固定）。**发版时**再把内容移动到带版本号的新段。
- **先记后合**：记录阶段同一工作周期内的改动各自独立记入 `[Unreleased]`（同一功能的多处调整也先各记一条，避免遗漏）；提交或发版前的整理阶段统一过一遍 `[Unreleased]`，把描述同一件事的多条合并成一条，不相关改动保持独立（判断标准：用户会不会把它当成同一件事，细则见下方「写作视角」）。
- **发版日期**：版本段日期 `(YYYY-MM-DD)` 填**当前日期**（以发版当天的系统时间为准，例如 `2026-09-22`）。

#### 格式

统一使用 **分组式**（与 scaffold 的 `CHANGELOG.md.template` 一致）：按分类用 `###` 子标题分组，条目用「标题 + 冒号 + 说明」，**仅重点条目/重点内容才加粗**：

```markdown
# Changelog

## [Unreleased]

> 一句话总结这个版本（可选）

### 新增
- 功能 A：说明
- **功能 B**：说明

### 修复
- 问题 C：说明

## v0.3.0 (2026-07-06)

> 一句话总结这个版本（可选）

### 新增
- 功能 D：说明
```

分组子标题分类：`新增` / `修复` / `变更` / `移除` / `性能`（只保留本次有内容的分类，无内容的分类不写空标题）

**加粗规则**：条目默认不加粗；写 changelog 时先识别本次改动中的**重点改动**（核心新功能、重要修复、破坏性变更等），只对重点改动用 `**加粗**` 标题强调，其余条目一律不加粗。

**版本总结**：版本标题（`## [Unreleased]` / `## vX.Y.Z (YYYY-MM-DD)`）与分类子标题之间，可加一行 `> 引用` 形式的一句话总结（概括该版本/该批改动的主旨），可选，不强制。

#### 写作视角（面向用户）

CHANGELOG 的读者是**插件使用者**（服务器管理员、群成员），不是开发者。条目只写「用户能感知到的变化」，不写内部实现：

- **写用户视角的结果**：用户能做什么、会看到什么、行为/默认值/配置有什么不同。
- **禁止内部实现细节**：类名/函数名、方法拆分、数据结构、算法、缓存与并发策略、日志埋点、依赖升级、重构过程，一律不写。
- **禁止出现代码标识符与文件路径**（如 `_on_queqiao_event`、`services/monitor.py`）；用户直接接触的**命令名**、**配置项 key** 除外。
- **无用户感知的改动不记入 CHANGELOG**：纯内部重构、格式化、注释与测试调整等，写了用户也读不懂、也用不上。
- **只写相对上一版的变化**：每条回答「这个版本和用户手上的版本比，变了什么」，只讲差异；不复述仍然有效的旧功能，不写「继续优化」「体验更好」这类没有信息量的空话。
- **同一个变化合并成一条**：同一功能的多处调整、跨多个提交的同一件事，在提交或发版前的整理阶段合并为一条；同一内容不要在不同分类或不同版本段里重复出现。
- **一句话说清改了什么**：按「做了什么 + 用户得到什么」写完，不加背景、动机与实现过程，也不用复杂形容；用户扫一眼就能对上自己关心的功能。
- 判断标准：使用者读完一条，能决定「要不要升级、升级后有什么不同」。

正反例：

```markdown
### 新增
- ✅ 转发图片到游戏内（`forward_image_to_mc`）：开启后图片以地图画形式发送
- ❌ 新增 `_rebuild_media_component` 并重构消息构造链路，改用 dataclass 缓存节点

### 修复
- ✅ 修复超时后不再重试、消息被静默丢弃的问题
- ❌ 修复 `as_completed` 回调未捕获 `asyncio.TimeoutError` 导致的 `finally` 泄漏
```

#### 版本号（准备发布时才确认）

- **日常开发不碰版本号**：只往 `[Unreleased]` 追加条目，`metadata.yaml` 的 `version` 保持原值；每个功能、每个修复各自是一次独立提交，提交里不带版本号变更，也不改辅助位置的版本字样。
- **准备发布时才确认并递增一次**：一次发版汇总了多个独立的功能/修复提交，等合并到指定版本、把 `[Unreleased]` 内容移入 `## vX.Y.Z (YYYY-MM-DD)` 的同一次操作里，才确认版本号（SemVer 见 8.2）、写进下方的**唯一版本源文件**、把辅助位置同步成同一个版本号并打 `git tag vX.Y.Z`。**不能每改一点就递增**——否则版本号会随提交次数突进，与实际发布节奏脱节。
- **唯一版本源**：`metadata.yaml` 的 `version` 字段（`vX.Y.Z` 格式，AstrBot 读取的插件版本）。需要「插件版本」时一律以它为准。

| 版本源文件 | 位置 |
|------|------|
| `metadata.yaml` | `version` 字段（`vX.Y.Z` 格式） |

下列位置属于**辅助信息，不是版本源**，不决定版本号（需要「插件版本」时以 `metadata.yaml` 为准）：`main.py` 中 `@register` 传入的版本号、`README.md` / `README_en.md` 的版本徽章与正文版本字样。**日常提交不动它们；准备发布时必须逐个同步到同一个新版本号**，不得残留旧版本号或自相矛盾的版本字样。也不要新增此类重复版本号——需要展示版本时从 `metadata.yaml` 读取，不手写。

#### 多会话并行开发

**⚠️ 更新 `CHANGELOG.md` 前必须先读取当前文件内容**，识别并保留其他会话已写入的既有条目（含 `[Unreleased]` 下未提交的功能），只追加自己的条目，**严禁整文件覆盖或删除他人记录**。

### 7.2 README 维护

#### 7.2.1 写作视角（面向用户）

README 的读者是**插件使用者**（服务器管理员、群成员），不是开发者。只写用户能直接用到的东西：

- **该写的**：能做什么（能力清单）、怎么装、怎么配（配置表）、怎么用（指令表与示例）、出问题怎么办（常见问题、前置条件与限制）。
- **不该写的**：实现原理与设计理念、架构分层与模块划分、算法与数据结构、内部调用流程、类名/函数名/文件路径、性能优化手段、依赖内部实现。
- **代码只贴用户要用的最小片段**：安装命令、配置项、指令示例；不贴内部实现代码。
- **技术细节翻译成用户语言**：不写「用 `asyncio.Semaphore` 限制并发」，写「同时处理的任务数量上限（`max_concurrency`），超出后排队」。
- 判断标准：使用者只读 README，就能独立完成安装 → 配置 → 使用 → 排障。

正反例：

```markdown
- ✅ 支持把图片以地图画形式转发到游戏内（需在配置中开启）
- ❌ 图片经 `_rebuild_media_component` 转为 dataclass 节点，再由 worker 渲染为地图画
```

#### 7.2.2 头部表头格式

本项目维护 **两个** README（中文 `README.md` + 英文 `README_en.md`），**中文版为权威版本（源）**，任何修改先落中文版、再同步到英文版（方向规则见 7.2.5）。表头格式如下（**元素间不留空行**）：

**中文版（`README.md`）：**

```html
<div align="center">
<h1>Minecraft 鹊桥互通</h1>
<p><strong>通过鹊桥模组连接 Minecraft 服务器，实现消息互通、图片互通、服务器管理与 AI 聊天</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-vX.Y.Z-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; 我的世界 &nbsp;&nbsp; 鹊桥 &nbsp;&nbsp; 消息互联 &nbsp;&nbsp; 图片互通 &nbsp;&nbsp; AI聊天</sub></p>
<p><strong>中文</strong> &nbsp;/&nbsp; <a href="README_en.md">English</a></p>
</div>
```

**英文版（`README_en.md`）：**

```html
<div align="center">
<h1>Minecraft Queqiao</h1>
<p><strong>Connect Minecraft servers to AstrBot via the QueQiao mod for message and image bridging, server management and AI chat</strong></p>
<p><img alt="version" src="https://img.shields.io/badge/version-vX.Y.Z-blue"></p>
<p><sub>Minecraft &nbsp;&nbsp; QueQiao &nbsp;&nbsp; Message Bridge &nbsp;&nbsp; Image Bridge &nbsp;&nbsp; AI Chat</sub></p>
<p><a href="README.md">中文</a> &nbsp;/&nbsp; <strong>English</strong></p>
</div>
```

命名规则：

- **中文版 h1**：取 `metadata.yaml` 的 `display_name`（Minecraft 鹊桥互通）
- **英文版 h1**：取插件名 `astrbot_plugin_xxx` 的 `xxx` 拆分后首字母大写；本项目沿用现有标题 `Minecraft Queqiao`（Queqiao 视为专名，不再拆分）
- **desc**：中文版用 `metadata.yaml` 的 `desc`；英文版做地道翻译
- **标签（tags）**：取自 `metadata.yaml` 的 `tags`（中文标签用 `&nbsp;&nbsp;` 分隔；英文版用英文标签）
- **版本徽章**：本项目在 desc 与 tags 之间保留 version badge，发版时同步更新

#### 7.2.3 README 四大结构

README 正文严格按以下 4 大板块组织，但不强制使用 `##` 标题层级，可灵活组合：

| 板块 | 内容 | 说明 |
|------|------|------|
| **一、功能/介绍** | 功能介绍、特性列表、用户使用场景、截图/演示 | 独立板块 |
| **二、指令** | 命令表格（命令、权限、说明）、使用示例 | 独立板块 |
| **三、配置** | 配置项表格（配置项、类型、默认值、说明）、`_conf_schema.json` 说明 | 独立板块 |
| **四、其它** | 安装、快速开始、运行环境与依赖要求、贡献指南、常见问题、许可证、鸣谢等 | 剩余所有内容放这里 |

注意点：

- 板块 4 是兜底区域，不强制子标题顺序，但**安装/快速开始**建议放在最前。
- **板块一/板块四只写用户视角**：写「运行环境与依赖要求」而非框架选型理由、架构分层、模块职责；实现原理一律不进 README（写作视角见 7.2.1）。
- 更新后通读一遍 README，确保与新行为一致（示例：默认值、超时说明、数据目录等）。

#### 7.2.4 何时必须更新 README

| 改动类型 | 必须更新的板块 |
|----------|--------------|
| 功能新增/删除 | 一、功能/介绍 |
| 使用方式/命令变化 | 二、指令 |
| 配置项变化 | 三、配置 |
| 依赖/版本要求变化 | 四、其它（安装/依赖部分） |
| 已知问题/行为变化 | 四、其它（常见问题部分） |

**何时不需要更新 README：**

- 纯内部重构（行为完全不变）、样式调整、bug 修复（除非修复改变了用户可见行为）

#### 7.2.5 双语文档同步

- 中文版用 `README.md`，英文版用 `README_en.md`。
- **中文为主（单向同步）**：中文版是**权威版本（源）**，英文版跟随中文版。所有改动**先落中文版，再从中文同步到英文版**；**禁止反向**——不得先改英文版再回填中文，不得用英文版覆盖中文版。
- 章节结构必须保持一致，新增章节两个文件都要加。
- 中文版使用自然中文，英文版使用地道英文，**禁止**逐字机翻、禁止留下半翻译的句子。
- 头部的语言切换链接互相指向对方文件。
- 修改时逐条 diff，确保无内容遗漏或错位。

#### 7.2.6 格式与多会话约束

- **禁止无意义的换行**：HTML 头部区块内元素间不留空行；正文长句不要人为软换行（一段文字保持一行，由 Markdown 自动折行显示）；空行只用于分隔标题、表格、列表、代码块等结构性区块。
- **多会话并行修改**：更新 `README.md` / `README_en.md` 前必须先读取当前文件内容，识别并保留其他会话已写入的既有内容，只追加/修改自己的部分，**严禁整文件覆盖或删除他人记录**。

### 7.3 注释规范

- **注释只写 non-obvious reason**：解释「为什么这么做」，而不是「做了什么」（代码本身应自文档化）
  - 坏：`# 设置超时时间为30秒`（代码已写 `timeout = 30`）
  - 好：`# 30秒超时，因为上游API的SLA承诺P99为25秒`
- **禁止残留 intermediate attempts**：不保留被注释掉的旧代码、TODO 但未完成的方案、调试输出
- 方法级 docstring 用中文说明用途/参数/返回（仅对 `_` 开头私有方法可省略，如果用途足够明显）
- 代码分区用 `# ---- 分区名 ----` 分隔条

### 7.4 PR 描述规范

- **PR 描述只写最终行为**：描述最终完成了什么，而不是过程中尝试了什么
- 禁止提及：尝试过的方案、被否定的设计、从未合入的中间状态
- 只写 diff 里看不出来的取舍理由（如「选用方案A因为性能比B高20%」）

---

## 8. 提交与发布流程

### 8.1 提交规范

- 提交信息遵循 **Conventional Commits**：`<type>(<scope>): <中文短句式 subject>`（如 `feat: 开放颜色配置项`、`fix: 失败发送通知补重试`、`docs: 补充配置说明`）
- **禁止**将未完成的功能、多轮迭代的中间状态、被废弃的方案写进提交信息
- **提交前必须先向用户展示，等用户确认后再执行 commit**，展示内容缺一不可：
  - 待提交文件清单
  - 改动概要（如 `git diff --stat`）
  - **提交标题，尽量给 2–3 个候选**（同一改动的不同侧重点：做了什么 / 为什么改 / 是否带 scope），逐条注明侧重供用户挑选并标出推荐项；确实只有一种合理写法时才只给一个
  - 用户选定标题（或自拟）后才 commit；涉及推送时另附提交 hash、提交信息、目标分支与改动概要
- 推荐顺序：完成功能代码 → 跑通验证 → 更新 CHANGELOG 与 README → 提交
- 文档更新与代码改动**在同一提交中完成**（不单独拆「补文档」提交）
- 只有用户明确要求时才 commit / push
- **授权一次性，不延续**（「上一轮说过推送」≠ 本轮可以提交）：
  - 用户的确认**只对当次动作生效**；下一次改动必须重新展示改动内容与提交标题，重新确认
  - 展示后改动内容又变了（用户提了新要求、你又改了文件，哪怕只改一行），**原确认立即失效**，必须重新展示并再次确认
  - 下列情形**都不算授权**：上一轮 / 上一个任务 / 上一个会话说过「提交」「推送」；会话恢复（resume / fork）后继承的历史授权；用户对功能或代码表示满意；用户正在讨论其它需求；用户未回复
  - 授权范围逐项独立：确认 commit ≠ 授权 push；确认推送某分支 ≠ 授权后续继续提交或推送；确认一个提交 ≠ 授权 `--amend` 或追加提交
  - 执行前自检：能指出用户**本轮**对**本次改动**的明确同意原话；指不出来就先问，不要执行

### 8.2 版本号规范

- 采用 **SemVer**：新功能 → `minor` 递增；bug 修复/小改进 → `patch` 递增
- **只在准备发布时递增**（规则见 7.1）：单个功能/修复提交不碰版本号；一次发版汇总多个独立提交、合并到指定版本时才确认版本号，改 `metadata.yaml` 的 `version`，并把 `@register`、README 徽章等辅助位置同步到同一版本号——逐次递增会让版本号突进
- 发版一致性：`metadata.yaml` version = CHANGELOG 新版本段号 = `git tag vX.Y.Z`，tag 推送同样需用户确认

### 8.3 测试与验证

- 改动纯逻辑后运行 `python3 tests_offline.py`（55 组断言，覆盖配置解析、事件模型、转发/回声抑制、自定义指令、绑定持久化、AI 触发方式与前缀互斥语义、端到端事件流、main 导入、AstrBot 导入路径校验、显示名称与格式默认值、conf 模板↔代码默认值一致性守卫、API 超时语义「未知 ≠ 失败，禁止重发」、图床与内置图片 HTTP、SLP ping 与监控采样、面板偏好与终端日志、本地翻译、回复游戏消息反解玩家名）
- 语法自检：`python3 -m py_compile main.py core/*.py services/*.py handlers/*.py` 无语法错误（本项目是包结构，`import main` 相对导入不可用）
- 格式检查：`python -m ruff format .`（如果项目历史有 ruff 提交）
- 命令有新增/删除时：同步更新 `README.md` 命令表与本文件 6.2 节

---

## 9. 最终检查清单（每次任务完成前）

- [ ] 架构：所选风格与既有代码一致；新代码放在 `core/` / `services/` / `handlers/` 的正确层
- [ ] 注释：只写 non-obvious reason，无残留中间状态、无被注释掉的旧代码
- [ ] 类型：新增/修改函数完整类型注解，禁止 `Any` 与 `# type: ignore`
- [ ] 日志：`logger.info/warning/error` 带 `[{PLUGIN_NAME}][{server_name}]` 前缀，异常分类记录，无空 `except: pass`
- [ ] 事件/API：名称走 `core/constants.py` 常量，未硬编码
- [ ] 连接层改动：已考虑反向模式共享 Server 与 `echo` 关联时序
- [ ] CHANGELOG：`[Unreleased]` 已追加分组式条目，**只写相对上一版的变化**、同一变化已合并为一条（无重复条目），条目面向用户（无内部实现细节、无复杂形容即可看懂），保留了他人的既有记录
- [ ] README：涉及用户可见变更时已同步更新（中英双语、四大板块），且面向用户书写（无实现原理与内部细节）
- [ ] 版本号：日常任务不递增；仅发版任务改 `metadata.yaml` 的 `version`（与 CHANGELOG 新版本段、tag 一致），并把 `@register`、README 徽章等辅助位置同步到同一版本号
- [ ] 配置：新增配置项已在 `_conf_schema.json` 与 `core/models_config.py` 同步，文档写成「中文名（`key`）」
- [ ] 命令：新增/修改命令已同步 `README.md` 命令表与本文件 6.2 表
- [ ] 提交信息：Conventional Commits 格式（`type: 中文短句式`），只描述最终行为
- [ ] 提交前展示：已给出待提交文件清单、`git diff --stat`、2–3 个候选提交标题（逐条注明侧重并标出推荐项），并取得用户对本次改动的明确确认（一次性授权，未沿用上一轮）
- [ ] 本地测试：`python3 tests_offline.py` 通过

---

## 附录：已知设计细节与注意点

- 翻译优先级：原始翻译键 → 原版英文精确表（`en_zh.json`）→ 死亡英文模板匹配（`death_en_templates.json`）→ 原文兜底；全部未命中不报错
- 本地翻译开关关闭时保持鹊桥原文；开启时死亡/成就消息同样经本地翻译
- 终端日志按天分片（`terminal_logs/YYYY-MM-DD.json`），默认保留 30 天；旧版单文件启动时迁移并备份 `.bak`；仅仪表盘「清屏」删除对应服务器记录
- `metrics.py` 是运行期统计（重启清零），`terminal_log.py` 才负责跨会话持久化——两者不要混用
- 面板偏好（`panel_prefs.json`）是权威源；`terminal_days` 已迁为每服独立配置，前端不再写入面板偏好
- 图床两类条目共用 `upload(data) -> (url, 失败原因)`：`builtin_http` 需玩家客户端可达 `base_url`；第三方图床需 AstrBot 能出网
- `host_mem.py`：同机部署（MemTotal 匹配 ±5%）用 `/proc/meminfo` 的 MemAvailable 修正鹊桥口径；跨机部署物理内存字段清零，只保留 JVM 堆内存
- `slp_ping.py`：直连服务器做状态协议握手测 RTT，与玩家客户端口径一致，不经鹊桥
- `monitor.py`：TPS 数据源默认 `auto`，按 SLP 识别服务端品牌选择 `tps` / `spark tps` / `forge tps`；延迟走 SLP 直连
- 回环抑制：外部 → MC 转发的内容在抑制窗口内从 MC 回传时不再转发，避免回声刷屏
