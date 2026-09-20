"""服务器配置模型：把 `_conf_schema.json` 中 mc_servers 的每个模板项解析为 dataclass。

WebUI 配置值可能以字符串形式抵达（例如模板列表的输入框），因此这里统一做
防御式类型收敛，非法值一律回退默认值，避免个别字段写错导致整台服务器不可用。
"""

import json
from dataclasses import dataclass, field

from .constants import (
    DEFAULT_BROADCAST_FORMAT,
    DEFAULT_CHAT_FORMAT,
    DEFAULT_CLIENT_ORIGIN,
    DEFAULT_RECONNECT_INTERVAL,
    DEFAULT_REVERSE_HOST,
    DEFAULT_REVERSE_PORT,
    DEFAULT_REVERSE_PATH,
    DEFAULT_WS_URL,
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


@dataclass
class ServerConfig:
    """单台 MC 服务器的完整配置（对应 conf 中一个模板项）。"""

    # ---- 基础 ----
    enabled: bool = True
    server_id: str = ""

    # ---- 鹊桥连接 ----
    ws_mode: str = WS_MODE_FORWARD
    ws_url: str = DEFAULT_WS_URL
    reverse_host: str = DEFAULT_REVERSE_HOST
    reverse_port: int = DEFAULT_REVERSE_PORT
    reverse_path: str = DEFAULT_REVERSE_PATH
    access_token: str = ""
    client_origin: str = DEFAULT_CLIENT_ORIGIN
    reconnect_interval: int = DEFAULT_RECONNECT_INTERVAL
    max_reconnect: int = 0

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
    auto_forward_prefix: str = "*"
    broadcast_format: str = DEFAULT_BROADCAST_FORMAT
    broadcast_color: str = "white"
    mark_option: str = "emoji"

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

        ws_mode = _to_str(server.get("ws_mode"), WS_MODE_FORWARD).strip().lower()
        if ws_mode not in VALID_WS_MODES:
            ws_mode = WS_MODE_FORWARD

        mark_option = _to_str(message.get("mark_option"), "emoji").strip().lower()
        if mark_option not in VALID_MARK_OPTIONS:
            mark_option = "emoji"

        list_mode = _to_str(cmd.get("cmd_white_black_list"), "white").strip().lower()
        if list_mode not in VALID_LIST_MODES:
            list_mode = "white"

        server_id = _to_str(server.get("server_id"), "").strip()

        return cls(
            enabled=_to_bool(data.get("enabled"), True),
            server_id=server_id,
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
                1, _to_int(server.get("reconnect_interval"), DEFAULT_RECONNECT_INTERVAL)
            ),
            max_reconnect=max(0, _to_int(server.get("max_reconnect"), 0)),
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
            target_sessions=_to_list(message.get("target_sessions"), []),
            auto_forward_prefix=_to_str(message.get("auto_forward_prefix"), "*"),
            broadcast_format=_to_str(
                message.get("broadcast_format"), DEFAULT_BROADCAST_FORMAT
            )
            or DEFAULT_BROADCAST_FORMAT,
            broadcast_color=_to_str(message.get("broadcast_color"), "white") or "white",
            mark_option=mark_option,
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
