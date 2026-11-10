"""服务器配置模型：把 `_conf_schema.json` 中 mc_servers 的每个模板项解析为 dataclass。

WebUI 配置值可能以字符串形式抵达（例如模板列表的输入框），因此这里统一做
防御式类型收敛，非法值一律回退默认值，避免个别字段写错导致整台服务器不可用。
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from .constants import (
    DEFAULT_BROADCAST_FORMAT,
    DEFAULT_CHAT_FORMAT,
    DEFAULT_CHATIMAGE_NAME,
    CONNECT_FAIL_NOTIFY_DELAY_MAX,
    CONNECT_FAIL_NOTIFY_DELAY_MIN,
    DEFAULT_CLIENT_ORIGIN,
    DEFAULT_CONNECT_FAIL_NOTIFY_DELAY,
    DEFAULT_CONNECT_FAIL_NOTIFY_FORMAT,
    DEFAULT_CONNECT_NOTIFY_FORMAT,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_LOW_FREQUENCY_INTERVAL,
    DEFAULT_LOW_FREQUENCY_THRESHOLD,
    DEFAULT_MONITOR_INTERVAL,
    DEFAULT_MONITOR_RETENTION_DAYS,
    DEFAULT_MONITOR_TPS_COMMAND,
    DEFAULT_PLATFORM_NAMES,
    DEFAULT_QUIET_HOURS_ENABLED,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_ITEMS,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_RECONNECT_INTERVAL,
    DEFAULT_REVERSE_HOST,
    DEFAULT_REVERSE_PORT,
    DEFAULT_REVERSE_PATH,
    DEFAULT_TERMINAL_DAYS,
    DEFAULT_WS_URL,
    EMOJI_OK_GESTURE,
    MONITOR_MIN_INTERVAL,
    QUIET_HOURS_ITEM_KEYS,
    QUIET_HOURS_TIME_PATTERN,
)

WS_MODE_FORWARD = "forward"
WS_MODE_REVERSE = "reverse"

VALID_WS_MODES = (WS_MODE_FORWARD, WS_MODE_REVERSE)
VALID_MARK_OPTIONS = ("text", "emoji", "none")
VALID_LIST_MODES = ("white", "black", "none")


def _to_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _to_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "y", "on"):
            return True
        if lowered in ("0", "false", "no", "n", "off"):
            return False
    return default


def _to_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(float(stripped))
            except ValueError:
                return default
    return default


def _to_int_clamped(value: object, default: int, lo: int, hi: int) -> int:
    """整数解析 + 区间钳制（0~30 之类的天数）。非法值回退默认。"""
    return max(lo, min(hi, _to_int(value, default)))


def _to_list(value: object, default: list[str]) -> list[str]:
    """兼容列表、JSON 字符串、逗号分隔字符串三种形态。"""
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [_to_str(item) for item in value]
    if isinstance(value, tuple):
        return [_to_str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return list(default)
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return [_to_str(item) for item in parsed]
        parts = [part.strip() for part in stripped.split(",") if part.strip()]
        return parts if parts else list(default)
    return list(default)


def _to_quiet_items(value: object) -> list[str]:
    """解析免打扰项目：只保留已知 key，按 QUIET_HOURS_ITEMS 的固定顺序输出。

    未知 key（手写配置写错、前端旧版本残留）一律丢弃；显式清空列表
    表示「什么都不静音」，与未配置（回落默认全选）区分开。
    """
    raw = _to_list(value, DEFAULT_QUIET_HOURS_ITEMS)
    selected = {item.strip() for item in raw if item.strip()}
    return [key for key in QUIET_HOURS_ITEM_KEYS if key in selected]


def _as_object(value: object) -> dict:
    """把配置子节点收敛为 dict，非法形态返回空 dict。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return {}
            if isinstance(parsed, dict):
                return parsed
    return {}


def _to_platform_map(value: object) -> dict[str, str]:
    """把「平台名称映射」配置收敛为 {原始平台名: 显示名}。

    条目格式 `原始平台名=显示名`（如 `aiocqhttp=QQ`），兼容列表、
    JSON 对象字符串、逗号分隔字符串三种形态（复用 _to_list），
    另兼容 dict 形态（WebUI 误存对象时）。无分隔符或键/值为空的条目
    一律忽略，避免个别写错把整个映射弄坏；重复键取最后一条。
    """
    if isinstance(value, dict):
        raw = list(value.items())
    elif isinstance(value, str) and _as_object(value):
        raw = list(_as_object(value).items())
    else:
        raw = []
        for entry in _to_list(value, []):
            key, _, val = entry.partition("=")
            raw.append((key, val))

    mapping: dict[str, str] = {}
    for key, val in raw:
        k = _to_str(key).strip()
        v = _to_str(val).strip()
        if k and v:
            mapping[k] = v
    return mapping


@dataclass
class ServerConfig:
    """单台 MC 服务器的完整配置（对应 conf 中一个模板项）。"""

    # ---- 基础 ----
    enabled: bool = True
    # 与 conf 模板默认值一致；显式填空串仍会被 main 层跳过并告警
    server_name: str = "Server"
    display_name: str = ""
    # display_name 留空时 {display_name} 与状态查询展示的默认内容；
    # 显式清空（WebUI 里删成空串）才输出空串，用于配置无前缀展示
    display_name_default: str = DEFAULT_DISPLAY_NAME

    # ---- 鹊桥连接 ----
    ws_mode: str = WS_MODE_FORWARD
    ws_url: str = DEFAULT_WS_URL
    reverse_host: str = DEFAULT_REVERSE_HOST
    reverse_port: int = DEFAULT_REVERSE_PORT
    reverse_path: str = DEFAULT_REVERSE_PATH
    access_token: str = ""
    client_origin: str = DEFAULT_CLIENT_ORIGIN

    # ---- 重连（对应模板项底部的 reconnect 分组） ----
    reconnect_interval: int = DEFAULT_RECONNECT_INTERVAL
    max_reconnect: int = 0
    # 连续重连失败超过该次数后进入低频重试：间隔固定为 low_frequency_interval，
    # 不再随失败次数递增（避免长期断线时高频打扰）；配 0 关闭低频，始终按退避
    low_frequency_threshold: int = DEFAULT_LOW_FREQUENCY_THRESHOLD
    low_frequency_interval: int = DEFAULT_LOW_FREQUENCY_INTERVAL

    # ---- 功能开关 ----
    enable_ai_chat: bool = True
    ai_persona_id: str = ""
    ai_chat_prefix: str = "ai"
    text2image: bool = True
    # 互通终端加载最近几天的日志分片（0=全部保留分片），每台服务器独立
    terminal_days: int = DEFAULT_TERMINAL_DAYS
    # 服务器连通通知：连接建立（含断线重连、插件热重载）时向目标会话
    # 发送「服务器已启动」；默认关闭，避免升级后打扰已有配置
    notify_on_connect: bool = False
    notify_on_connect_format: str = DEFAULT_CONNECT_NOTIFY_FORMAT
    # 连接失败通知：初次连不上与已连接后断线都算，同一轮故障（直到重新
    # 连上）只发第一条，避免重试期间刷屏
    notify_on_connect_fail: bool = False
    notify_on_connect_fail_format: str = DEFAULT_CONNECT_FAIL_NOTIFY_FORMAT
    # 断连静默期（秒）：断线持续超过该时长仍未恢复才发失败通知；期间连回
    # 则完全静默（不发失败、也不发恢复）。0 = 断线立即通知
    connect_fail_notify_delay: int = DEFAULT_CONNECT_FAIL_NOTIFY_DELAY
    # 服务器状态探测地址 host[:port]：连通通知据此判断「服务器真的启动过」还是
    # 「只是鹊桥断了」。留空则退回按断线时长判断（≥30 秒才算启动）
    slp_address: str = ""
    # 免打扰（安静时段）：时段内静音 quiet_hours_items 里勾选的消息类型，
    # 只影响「发到外部会话」这一步——终端日志与指标照常记录，不会丢事件
    quiet_hours_enabled: bool = DEFAULT_QUIET_HOURS_ENABLED
    quiet_hours_start: str = DEFAULT_QUIET_HOURS_START
    quiet_hours_end: str = DEFAULT_QUIET_HOURS_END
    quiet_hours_items: list[str] = field(
        default_factory=lambda: list(DEFAULT_QUIET_HOURS_ITEMS)
    )

    # ---- 消息转发 ----
    forward_chat_to_astrbot: bool = True
    forward_chat_prefix: str = ""
    forward_chat_format: str = DEFAULT_CHAT_FORMAT
    forward_join_leave_to_astrbot: bool = False
    forward_death_to_astrbot: bool = False
    forward_achievement_to_astrbot: bool = False
    # 本地翻译：给上面两个转发（死亡/成就）做翻译——开启后鹊桥传来的
    # 英文 / 翻译键在插件侧直接转成中文，不依赖服务端鹊桥 enable_translation
    # （无需重启服务端，翻译库内置在插件 translations/ 目录）
    enable_local_translation: bool = False
    target_sessions: list[str] = field(default_factory=list)
    # 默认留空 = 全部转发；仅对已绑定 target_sessions 的会话生效，故默认放开是安全的
    auto_forward_prefix: str = ""
    # E33Chat 服务端媒体目录；仅当 AstrBot 可读取该目录时才能转发 e33chat://media 图片
    e33chat_media_dir: str = ""
    # 游戏 → 外部图片来源：默认保留 ChatImage / 图片链接处理，E33Chat 模式额外读取服务端媒体目录
    mc_image_mode: str = "chatimage"
    # 同时保留唤醒消息原文并转发机器人自己的群消息；插件自身发出的消息仍由回声标记拦截
    forward_bot_self_messages: bool = False
    broadcast_format: str = DEFAULT_BROADCAST_FORMAT
    # 平台名称映射：{platform} 占位符按此把原始平台名替换为自定义展示名。
    # 默认自带 aiocqhttp=QQ 示例（开箱即用）；配置里删空该项则不改写
    platform_names: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_PLATFORM_NAMES)
    )
    broadcast_color: str = "white"
    mark_option: str = "emoji"
    mark_emoji_id: int = EMOJI_OK_GESTURE
    # 外部会话消息中的图片转发到游戏内（依赖游戏端 ChatImage 模组渲染）
    forward_image_to_mc: bool = False
    # ChatImage 代码中 name 参数的取值（图片在聊天栏的显示名）
    chatimage_name: str = DEFAULT_CHATIMAGE_NAME
    # 游戏内聊天消息中的图片（ChatImage CICode 代码 / 图片链接）下载后作为图片转发到外部
    forward_image_from_mc: bool = False

    # ---- 远程指令 ----
    cmd_enabled: bool = True
    cmd_white_black_list: str = "white"
    cmd_list: list[str] = field(default_factory=lambda: ["say", "list", "weather", "time"])
    bind_enable: bool = True
    custom_cmd_list: list[str] = field(default_factory=list)

    # ---- 直连 RCON 兜底 ----
    rcon_fallback_enabled: bool = False
    rcon_host: str = "localhost"
    rcon_port: int = 25575
    rcon_password: str = ""

    # ---- 性能监控（TPS / 延迟，长时间采样分析） ----
    # 默认开启、参数内置（间隔 60s / 保留 7 天 / tps 指令），不占用 WebUI
    # 配置项（性能监控只在仪表盘展示）。如需关闭或调整，可手动在 AstrBot
    # 配置 JSON 的服务器条目下写 monitor 分组（enabled/interval/
    # retention_days/tps_command）；未填时全部回落默认值。
    # TPS 经 RCON 执行 tps_command 获取；延迟为鹊桥 get_status API 往返耗时。
    monitor_enabled: bool = True
    monitor_interval: int = DEFAULT_MONITOR_INTERVAL
    monitor_retention_days: int = DEFAULT_MONITOR_RETENTION_DAYS
    monitor_tps_command: str = DEFAULT_MONITOR_TPS_COMMAND

    @property
    def server_label(self) -> str:
        """消息格式 `{display_name}` 的取值：**显示名称 → 显示名称默认值**。

        - 填了 `display_name`：原样使用（可中文，如 `生存服`）
        - `display_name` 留空：使用 `display_name_default`（默认 `MC`，
          即什么都不填时 `{display_name}` 显示 `MC`）
        - 两者**都**显式留空：才输出空串——唯一的无前缀途径，
          供 `[{display_name}]<{player}> {message}` 这类格式在未命名时隐藏前缀

        注意：这是**展示**语义，与连接握手用的 `server_name` 无关。
        """
        return self.display_name or self.display_name_default

    @property
    def display_label(self) -> str:
        """带兜底的展示名称，用于状态/列表等孤立文案。

        与 `server_label` 共用同一条取值链，额外兜底 `server_name` /「未知」：
        孤立文案（如「服务器状态：」）必须给出一个非空标识，
        否则会变成没有主语的半句话。
        """
        return self.server_label or self.server_name or "未知"

    def _render_notice(self, template: str) -> str:
        """替换通知文案里的 `{display_name}` / `{server_name}` 占位符。

        只做字符串替换、不用 `str.format`：用户文案里的 `{` / `}`（颜文字、
        JSON 片段等）会让 format 抛 ValueError，而这段代码跑在连接回调里，
        异常会导致整条通知发不出去。其余花括号原样保留。
        """
        text = template.strip().replace("{display_name}", self.server_label)
        return text.replace("{server_name}", self.server_name).strip()

    def render_connect_notice(self) -> str:
        """渲染「服务器已启动」通知文案（模板留空时回落默认文案）。"""
        return (
            self._render_notice(self.notify_on_connect_format)
            or DEFAULT_CONNECT_NOTIFY_FORMAT
        )

    def render_connect_fail_notice(self) -> str:
        """渲染「服务器连接失败」通知文案（模板留空时回落默认文案）。"""
        return (
            self._render_notice(self.notify_on_connect_fail_format)
            or DEFAULT_CONNECT_FAIL_NOTIFY_FORMAT
        )

    @staticmethod
    def parse_hhmm(value: str) -> int | None:
        """把 `HH:MM` 解析为当天分钟数；非法格式返回 None。"""
        match = re.match(QUIET_HOURS_TIME_PATTERN, (value or "").strip())
        if match is None:
            return None
        return int(match.group(1)) * 60 + int(match.group(2))

    def quiet_window(self) -> tuple[int, int] | None:
        """免打扰时段的 (起, 止) 分钟数；未启用或首尾相同/非法时返回 None。"""
        if not self.quiet_hours_enabled:
            return None
        start = self.parse_hhmm(self.quiet_hours_start)
        end = self.parse_hhmm(self.quiet_hours_end)
        if start is None or end is None or start == end:
            return None
        return start, end

    def is_quiet_now(self, now: datetime | None = None) -> bool:
        """当前（AstrBot 进程本地时间）是否处于免打扰时段，支持 23:00~08:00 这类跨零点区间。"""
        window = self.quiet_window()
        if window is None:
            return False
        moment = now or datetime.now()
        minutes = moment.hour * 60 + moment.minute
        start, end = window
        if start < end:
            return start <= minutes < end
        return minutes >= start or minutes < end

    def quiet_suppresses(self, item: str, now: datetime | None = None) -> bool:
        """该消息类型此刻是否应被免打扰静音（未勾选的项目不受时段影响）。"""
        if item not in self.quiet_hours_items:
            return False
        return self.is_quiet_now(now)

    def platform_display_name(self, platform: str) -> str:
        """把原始平台名按用户映射转换为游戏内展示名；未命中时原样返回。

        `{platform}` 占位符专用：平台 ID（如 `aiocqhttp`）又长又不好看，
        用户可配置 `aiocqhttp=QQ` 之类的映射让转发到游戏的内容更友好。
        精确匹配优先，其次忽略大小写匹配（平台 ID 均为小写，
        用户条目大小写手误时仍生效）。未配置映射或未命中时不做任何改写。
        """
        if not platform or not self.platform_names:
            return platform
        name = self.platform_names.get(platform)
        if name is not None:
            return name
        lowered = platform.lower()
        for key, value in self.platform_names.items():
            if key.lower() == lowered:
                return value
        return platform

    @property
    def is_reverse(self) -> bool:
        """是否使用反向连接（本插件作为 WS Server）。"""
        return self.ws_mode == WS_MODE_REVERSE

    @property
    def prefixes_conflict(self) -> bool:
        """游戏→群前缀与 AI 前缀互相包含时可能竞争同一条游戏聊天。"""
        return bool(
            self.forward_chat_prefix
            and self.ai_chat_prefix
            and (
                self.forward_chat_prefix.startswith(self.ai_chat_prefix)
                or self.ai_chat_prefix.startswith(self.forward_chat_prefix)
            )
        )

    @property
    def normalized_path(self) -> str:
        """反向监听路径，确保以 / 开头。"""
        path = self.reverse_path or DEFAULT_REVERSE_PATH
        return path if path.startswith("/") else f"/{path}"

    @property
    def forward_headers(self) -> dict[str, str]:
        """正向连接所需握手 Header；token 为空时不发送 Authorization。"""
        headers = {
            "x-self-name": self.server_name,
            "x-client-origin": self.client_origin or DEFAULT_CLIENT_ORIGIN,
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def is_command_allowed(self, command: str) -> bool:
        """按黑白名单判断指令是否放行。

        取指令的第一个词作为指令名（兼容 `gamemode creative` 这类带参形式），
        并忽略开头的 `/`。
        """
        mode = self.cmd_white_black_list
        if mode == "none":
            return True

        name = command.strip().lstrip("/").split(" ", 1)[0].lower()
        if not name:
            return False

        allowed = {item.strip().lstrip("/").lower() for item in self.cmd_list if item.strip()}
        if mode == "black":
            return name not in allowed
        return name in allowed

    @classmethod
    def from_dict(cls, data: dict) -> "ServerConfig":
        """从 conf 模板项解析配置。

        兼容两种层级：模板项直接带 `server`/`message`/`cmd` 子对象；
        缺失时使用默认值。
        """
        if not isinstance(data, dict):
            return cls()

        server = _as_object(data.get("server"))
        message = _as_object(data.get("message"))
        cmd = _as_object(data.get("cmd"))
        rcon = _as_object(cmd.get("rcon_fallback"))
        # 重连项现位于模板项底部独立的 reconnect 分组；
        # 兼容旧版写在 server 子对象内的配置，防止旧配置失效（新分组优先）
        reconnect = _as_object(data.get("reconnect")) or server
        # 性能监控参数不在 WebUI schema 中（只在仪表盘展示）；仍兼容配置 JSON
        # 手动写入 monitor 分组（关闭/调参），未填时用代码默认值
        monitor = _as_object(data.get("monitor"))

        ws_mode = _to_str(server.get("ws_mode"), WS_MODE_FORWARD).strip().lower()
        if ws_mode not in VALID_WS_MODES:
            ws_mode = WS_MODE_FORWARD

        mark_option = _to_str(message.get("mark_option"), "emoji").strip().lower()
        if mark_option not in VALID_MARK_OPTIONS:
            mark_option = "emoji"

        # 自定义回执表情 ID（默认 👌 = EMOJI_OK_GESTURE）；
        # 留空或非法时回落默认值，避免把非表情 ID 发给协议端
        mark_emoji_id = _to_int(message.get("mark_emoji_id"), EMOJI_OK_GESTURE)

        list_mode = _to_str(cmd.get("cmd_white_black_list"), "white").strip().lower()
        if list_mode not in VALID_LIST_MODES:
            list_mode = "white"

        # server_name 缺省回落 conf 模板默认值 Server；显式留空仍触发 main 层跳过告警
        server_name = _to_str(server.get("server_name"), "Server").strip()

        # 目标会话现位于模板项顶层（紧随「启用此服务器」，避免被折叠的消息转发分组
        # 藏住）；同时兼容早期写在 message 子对象内的配置，防止旧配置失效。
        target_sessions = _to_list(data.get("target_sessions"), [])
        if not target_sessions:
            target_sessions = _to_list(message.get("target_sessions"), [])

        return cls(
            enabled=_to_bool(data.get("enabled"), True),
            server_name=server_name,
            display_name=_to_str(server.get("display_name"), "").strip(),
            # 键缺失（旧配置/WebUI 默认注入）→ 默认 MC；显式清空 → 空串（无前缀）。
            # _to_str(None, 默认) 得默认值，_to_str("", 默认) 保持空串，二者可区分
            display_name_default=_to_str(
                server.get("display_name_default"), DEFAULT_DISPLAY_NAME
            ).strip(),
            ws_mode=ws_mode,
            ws_url=_to_str(server.get("ws_url"), DEFAULT_WS_URL).strip() or DEFAULT_WS_URL,
            reverse_host=_to_str(server.get("reverse_host"), DEFAULT_REVERSE_HOST).strip()
            or DEFAULT_REVERSE_HOST,
            reverse_port=max(1, _to_int(server.get("reverse_port"), DEFAULT_REVERSE_PORT)),
            reverse_path=_to_str(server.get("reverse_path"), DEFAULT_REVERSE_PATH).strip()
            or DEFAULT_REVERSE_PATH,
            access_token=_to_str(server.get("access_token"), ""),
            client_origin=_to_str(server.get("client_origin"), DEFAULT_CLIENT_ORIGIN).strip()
            or DEFAULT_CLIENT_ORIGIN,
            reconnect_interval=max(
                1, _to_int(reconnect.get("reconnect_interval"), DEFAULT_RECONNECT_INTERVAL)
            ),
            max_reconnect=max(0, _to_int(reconnect.get("max_reconnect"), 0)),
            low_frequency_threshold=max(
                0,
                _to_int(
                    reconnect.get("low_frequency_threshold"),
                    DEFAULT_LOW_FREQUENCY_THRESHOLD,
                ),
            ),
            low_frequency_interval=max(
                1,
                _to_int(
                    reconnect.get("low_frequency_interval"),
                    DEFAULT_LOW_FREQUENCY_INTERVAL,
                ),
            ),
            enable_ai_chat=_to_bool(data.get("enable_ai_chat"), True),
            ai_persona_id=_to_str(data.get("ai_persona_id"), ""),
            ai_chat_prefix=_to_str(data.get("ai_chat_prefix"), "ai"),
            text2image=_to_bool(data.get("text2image"), True),
            terminal_days=_to_int_clamped(
                data.get("terminal_days"), DEFAULT_TERMINAL_DAYS, 0, 30
            ),
            notify_on_connect=_to_bool(data.get("notify_on_connect"), False),
            # 模板留空回落默认文案（显式清空 = 用默认，不发送空消息）
            notify_on_connect_format=_to_str(
                data.get("notify_on_connect_format"), DEFAULT_CONNECT_NOTIFY_FORMAT
            ).strip()
            or DEFAULT_CONNECT_NOTIFY_FORMAT,
            notify_on_connect_fail=_to_bool(
                data.get("notify_on_connect_fail"), False
            ),
            notify_on_connect_fail_format=_to_str(
                data.get("notify_on_connect_fail_format"),
                DEFAULT_CONNECT_FAIL_NOTIFY_FORMAT,
            ).strip()
            or DEFAULT_CONNECT_FAIL_NOTIFY_FORMAT,
            connect_fail_notify_delay=_to_int_clamped(
                data.get("connect_fail_notify_delay"),
                DEFAULT_CONNECT_FAIL_NOTIFY_DELAY,
                CONNECT_FAIL_NOTIFY_DELAY_MIN,
                CONNECT_FAIL_NOTIFY_DELAY_MAX,
            ),
            slp_address=_to_str(data.get("slp_address"), "").strip(),
            quiet_hours_enabled=_to_bool(data.get("quiet_hours_enabled"), False),
            quiet_hours_start=_to_str(
                data.get("quiet_hours_start"), DEFAULT_QUIET_HOURS_START
            ).strip()
            or DEFAULT_QUIET_HOURS_START,
            quiet_hours_end=_to_str(
                data.get("quiet_hours_end"), DEFAULT_QUIET_HOURS_END
            ).strip()
            or DEFAULT_QUIET_HOURS_END,
            quiet_hours_items=_to_quiet_items(data.get("quiet_hours_items")),
            forward_chat_to_astrbot=_to_bool(message.get("forward_chat_to_astrbot"), True),
            forward_chat_prefix=_to_str(message.get("forward_chat_prefix"), "").strip(),
            forward_chat_format=_to_str(
                message.get("forward_chat_format"), DEFAULT_CHAT_FORMAT
            )
            or DEFAULT_CHAT_FORMAT,
            forward_join_leave_to_astrbot=_to_bool(
                message.get("forward_join_leave_to_astrbot"), False
            ),
            forward_death_to_astrbot=_to_bool(
                message.get("forward_death_to_astrbot"), False
            ),
            forward_achievement_to_astrbot=_to_bool(
                message.get("forward_achievement_to_astrbot"), False
            ),
            enable_local_translation=_to_bool(
                message.get("enable_local_translation"), False
            ),
            target_sessions=target_sessions,
            auto_forward_prefix=_to_str(message.get("auto_forward_prefix"), ""),
            e33chat_media_dir=_to_str(message.get("e33chat_media_dir"), "").strip(),
            mc_image_mode=(
                "e33chat"
                if _to_str(message.get("mc_image_mode"), "chatimage").strip().lower()
                == "e33chat"
                else "chatimage"
            ),
            forward_bot_self_messages=_to_bool(
                message.get("forward_bot_self_messages"),
                _to_bool(message.get("preserve_wake_prefix"), False),
            ),
            broadcast_format=_to_str(
                message.get("broadcast_format"), DEFAULT_BROADCAST_FORMAT
            )
            or DEFAULT_BROADCAST_FORMAT,
            platform_names=(
                # 配置里没有该键（旧配置/未动过）→ 默认自带 aiocqhttp=QQ 示例；
                # 显式给了（包括删空的空列表）→ 按解析结果，删空即不改写
                _to_platform_map(message["platform_names"])
                if "platform_names" in message
                else dict(DEFAULT_PLATFORM_NAMES)
            ),
            broadcast_color=_to_str(message.get("broadcast_color"), "white") or "white",
            mark_option=mark_option,
            mark_emoji_id=mark_emoji_id,
            forward_image_to_mc=_to_bool(message.get("forward_image_to_mc"), False),
            chatimage_name=_to_str(
                message.get("chatimage_name"), DEFAULT_CHATIMAGE_NAME
            ).strip()
            or DEFAULT_CHATIMAGE_NAME,
            forward_image_from_mc=_to_bool(message.get("forward_image_from_mc"), False),
            cmd_enabled=_to_bool(cmd.get("enabled"), True),
            cmd_white_black_list=list_mode,
            cmd_list=_to_list(
                cmd.get("cmd_list"), ["say", "list", "weather", "time"]
            ),
            bind_enable=_to_bool(cmd.get("bind_enable"), True),
            custom_cmd_list=_to_list(cmd.get("custom_cmd_list"), []),
            # 直连 RCON 兜底：扁平字段优先（cmd.rcon_enabled 等，AstrBot WebUI
            # 只渲染一层 object 嵌套，二级 object 无法显示）；兼容旧版
            # cmd.rcon_fallback 对象结构，防止旧配置失效
            rcon_fallback_enabled=_to_bool(
                cmd.get("rcon_enabled", rcon.get("enabled")), False
            ),
            rcon_host=(
                _to_str(cmd.get("rcon_host", rcon.get("host")), "localhost").strip()
                or "localhost"
            ),
            rcon_port=max(
                1, _to_int(cmd.get("rcon_port", rcon.get("port")), 25575)
            ),
            rcon_password=_to_str(
                cmd.get("rcon_password", rcon.get("password")), ""
            ),
            # 性能监控：默认开启（仅仪表盘展示，不占 WebUI 配置项）；配置 JSON
            # 手动写 monitor 分组可关闭/调参。间隔与保留天数做下限防御，
            # 避免误配造成采集风暴或立即清空历史
            monitor_enabled=_to_bool(monitor.get("enabled"), True),
            monitor_interval=max(
                MONITOR_MIN_INTERVAL,
                _to_int(monitor.get("interval"), DEFAULT_MONITOR_INTERVAL),
            ),
            monitor_retention_days=max(
                1, _to_int(monitor.get("retention_days"), DEFAULT_MONITOR_RETENTION_DAYS)
            ),
            monitor_tps_command=(
                _to_str(monitor.get("tps_command"), DEFAULT_MONITOR_TPS_COMMAND).strip()
                or DEFAULT_MONITOR_TPS_COMMAND
            ),
        )
