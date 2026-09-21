"""服务器配置模型：把 `_conf_schema.json` 中 mc_servers 的每个模板项解析为 dataclass。

WebUI 配置值可能以字符串形式抵达（例如模板列表的输入框），因此这里统一做
防御式类型收敛，非法值一律回退默认值，避免个别字段写错导致整台服务器不可用。
"""

import json
from dataclasses import dataclass, field

from .constants import (
    DEFAULT_BROADCAST_FORMAT,
    DEFAULT_CHAT_FORMAT,
    DEFAULT_CHATIMAGE_NAME,
    DEFAULT_CLIENT_ORIGIN,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_LOW_FREQUENCY_INTERVAL,
    DEFAULT_LOW_FREQUENCY_THRESHOLD,
    DEFAULT_PLATFORM_NAMES,
    DEFAULT_RECONNECT_INTERVAL,
    DEFAULT_REVERSE_HOST,
    DEFAULT_REVERSE_PORT,
    DEFAULT_REVERSE_PATH,
    DEFAULT_WS_URL,
    EMOJI_OK_GESTURE,
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
    server_id: str = "Server"
    server_name: str = ""
    # server_name 留空时 {server} 与状态查询展示的默认内容；
    # 显式清空（WebUI 里删成空串）才输出空串，用于配置无前缀展示
    server_name_default: str = DEFAULT_DISPLAY_NAME

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
    ai_chat_prefix: str = "ai"
    text2image: bool = True

    # ---- 消息转发 ----
    forward_chat_to_astrbot: bool = True
    forward_chat_format: str = DEFAULT_CHAT_FORMAT
    forward_join_leave_to_astrbot: bool = False
    forward_death_to_astrbot: bool = False
    forward_achievement_to_astrbot: bool = False
    target_sessions: list[str] = field(default_factory=list)
    # 默认留空 = 全部转发；仅对已绑定 target_sessions 的会话生效，故默认放开是安全的
    auto_forward_prefix: str = ""
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

    @property
    def server_label(self) -> str:
        """消息格式 `{server}` 的取值：**显示名称 → 显示名称默认值**。

        - 填了 `server_name`：原样使用（可中文，如 `生存服`）
        - `server_name` 留空：使用 `server_name_default`（默认 `MC`，
          即什么都不填时 `{server}` 显示 `MC`）
        - 两者**都**显式留空：才输出空串——唯一的无前缀途径，
          供 `[{server}]<{player}> {message}` 这类格式在未命名时隐藏前缀

        注意：这是**展示**语义，与连接握手用的 `server_id` 无关。
        """
        return self.server_name or self.server_name_default

    @property
    def display_name(self) -> str:
        """带兜底的展示名称，用于状态/列表等孤立文案。

        与 `server_label` 共用同一条取值链，额外兜底 `server_id` /「未知」：
        孤立文案（如「服务器状态：」）必须给出一个非空标识，
        否则会变成没有主语的半句话。
        """
        return self.server_label or self.server_id or "未知"

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
        """互通前缀与 AI 前缀是否冲突（互相包含即视为冲突）。

        两个前缀作用在不同方向，但都必须能唯一判定消息归属：
        - 群→MC 的互通前缀：外部会话消息以此开头才转发到游戏
        - AI 前缀：游戏内聊天以此开头才触发 AI

        若两者互相包含（例如同为 `*`，或一个是另一个的前缀），
        同一条游戏内消息可能同时命中两个语义，因此在读取时告警。
        """
        if not self.auto_forward_prefix or not self.ai_chat_prefix:
            return False
        return (
            self.auto_forward_prefix.startswith(self.ai_chat_prefix)
            or self.ai_chat_prefix.startswith(self.auto_forward_prefix)
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
            "x-self-name": self.server_id,
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

        # server_id 缺省回落 conf 模板默认值 Server；显式留空仍触发 main 层跳过告警
        server_id = _to_str(server.get("server_id"), "Server").strip()

        # 目标会话现位于模板项顶层（紧随「启用此服务器」，避免被折叠的消息转发分组
        # 藏住）；同时兼容早期写在 message 子对象内的配置，防止旧配置失效。
        target_sessions = _to_list(data.get("target_sessions"), [])
        if not target_sessions:
            target_sessions = _to_list(message.get("target_sessions"), [])

        return cls(
            enabled=_to_bool(data.get("enabled"), True),
            server_id=server_id,
            server_name=_to_str(server.get("server_name"), "").strip(),
            # 键缺失（旧配置/WebUI 默认注入）→ 默认 MC；显式清空 → 空串（无前缀）。
            # _to_str(None, 默认) 得默认值，_to_str("", 默认) 保持空串，二者可区分
            server_name_default=_to_str(
                server.get("server_name_default"), DEFAULT_DISPLAY_NAME
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
            ai_chat_prefix=_to_str(data.get("ai_chat_prefix"), "ai"),
            text2image=_to_bool(data.get("text2image"), True),
            forward_chat_to_astrbot=_to_bool(message.get("forward_chat_to_astrbot"), True),
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
            target_sessions=target_sessions,
            auto_forward_prefix=_to_str(message.get("auto_forward_prefix"), ""),
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
            rcon_fallback_enabled=_to_bool(rcon.get("enabled"), False),
            rcon_host=_to_str(rcon.get("host"), "localhost").strip() or "localhost",
            rcon_port=max(1, _to_int(rcon.get("port"), 25575)),
            rcon_password=_to_str(rcon.get("password"), ""),
        )
