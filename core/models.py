"""鹊桥 V2 事件与实体的数据模型。

设计要点：鹊桥各服务端（原版/Spigot/Paper/Folia/Velocity/Forge/Fabric/NeoForge）
在同一事件的字段填充程度上差异很大（例如原版 Player 仅有 nickname，
Velocity 仅有 nickname/uuid/is_op），因此所有解析一律走 `.get()` 兜底，
缺失字段降级为空值而不抛异常。
"""

from dataclasses import dataclass, field

from .constants import (
    EVENT_ACHIEVEMENT,
    EVENT_CHAT,
    EVENT_COMMAND,
    EVENT_DEATH,
    EVENT_JOIN,
    EVENT_QUIT,
)


def _as_str(value: object) -> str:
    """把任意 JSON 值安全转为字符串，None 转空串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _as_float(value: object, default: float = 0.0) -> float:
    """安全转 float，失败返回默认值。"""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _as_int(value: object, default: int = 0) -> int:
    """安全转 int，失败返回默认值。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _as_bool(value: object, default: bool = False) -> bool:
    """安全转 bool，兼容字符串形式的布尔值。"""
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


@dataclass
class QueQiaoPlayer:
    """鹊桥 Player 模型。

    字段可用性依服务端而异，缺失时保持默认值：
    - 原版端：仅 nickname
    - Velocity：仅 nickname / uuid / is_op
    - Spigot / Paper / Folia：无 max_health（Folia 可能缺 address）
    """

    nickname: str = ""
    uuid: str = ""
    is_op: bool = False
    address: str = ""
    health: float = 0.0
    max_health: float = 0.0
    experience_level: int = 0
    experience_progress: float = 0.0
    total_experience: int = 0
    walk_speed: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def from_dict(cls, data: object) -> "QueQiaoPlayer":
        if not isinstance(data, dict):
            return cls()
        return cls(
            nickname=_as_str(data.get("nickname")),
            uuid=_as_str(data.get("uuid")),
            is_op=_as_bool(data.get("is_op")),
            address=_as_str(data.get("address")),
            health=_as_float(data.get("health")),
            max_health=_as_float(data.get("max_health")),
            experience_level=_as_int(data.get("experience_level")),
            experience_progress=_as_float(data.get("experience_progress")),
            total_experience=_as_int(data.get("total_experience")),
            walk_speed=_as_float(data.get("walk_speed")),
            x=_as_float(data.get("x")),
            y=_as_float(data.get("y")),
            z=_as_float(data.get("z")),
        )

    @property
    def display_name(self) -> str:
        """用于展示的名称，nickname 缺失时退化为 uuid。"""
        return self.nickname or self.uuid


@dataclass
class QueQiaoTranslate:
    """鹊桥 Translate 模型（鹊桥 >= v0.4.1，用于死亡与成就文本国际化）。"""

    key: str = ""
    args: list[str] = field(default_factory=list)
    text: str = ""

    @classmethod
    def from_dict(cls, data: object) -> "QueQiaoTranslate":
        # 兼容 0.4.0 及以前：该位置直接是纯文本字符串
        if isinstance(data, str):
            return cls(text=data)
        if not isinstance(data, dict):
            return cls()
        raw_args = data.get("args")
        args = [_as_str(item) for item in raw_args] if isinstance(raw_args, list) else []
        return cls(
            key=_as_str(data.get("key")),
            args=args,
            text=_as_str(data.get("text")),
        )


@dataclass
class QueQiaoAchievement:
    """成就详情。0.4.1+ 文本在 translate.text，0.4.0 及以前在 text。"""

    key: str = ""
    frame: str = ""
    title: str = ""
    description: str = ""
    text: str = ""
    translate: QueQiaoTranslate = field(default_factory=QueQiaoTranslate)

    @classmethod
    def from_dict(cls, data: object) -> "QueQiaoAchievement":
        if not isinstance(data, dict):
            return cls()
        display = data.get("display")
        display = display if isinstance(display, dict) else {}
        title = display.get("title")
        description = display.get("description")
        return cls(
            key=_as_str(data.get("key")),
            frame=_as_str(display.get("frame")),
            # title/description 在 0.4.1+ 可能是 Translate 对象
            title=title.get("text", "") if isinstance(title, dict) else _as_str(title),
            description=(
                description.get("text", "")
                if isinstance(description, dict)
                else _as_str(description)
            ),
            text=_as_str(data.get("text")),
            translate=QueQiaoTranslate.from_dict(data.get("translate")),
        )

    @property
    def display_text(self) -> str:
        """优先取 0.4.1+ 的 translate.text，回退旧版 text。"""
        return self.translate.text or self.text


@dataclass
class QueQiaoEvent:
    """鹊桥 V2 事件。

    公共字段：timestamp / post_type / event_name / server_name /
    server_version / server_type / sub_type / message_id
    """

    event_name: str = ""
    post_type: str = ""
    sub_type: str = ""
    server_name: str = ""
    server_version: str = ""
    server_type: str = ""
    message_id: str = ""
    timestamp: int = 0
    player: QueQiaoPlayer = field(default_factory=QueQiaoPlayer)
    message: str = ""
    raw_message: str = ""
    command: str = ""
    death: QueQiaoTranslate = field(default_factory=QueQiaoTranslate)
    achievement: QueQiaoAchievement = field(default_factory=QueQiaoAchievement)

    @classmethod
    def from_dict(cls, data: dict) -> "QueQiaoEvent":
        return cls(
            event_name=_as_str(data.get("event_name")),
            post_type=_as_str(data.get("post_type")),
            sub_type=_as_str(data.get("sub_type")),
            server_name=_as_str(data.get("server_name")),
            server_version=_as_str(data.get("server_version")),
            server_type=_as_str(data.get("server_type")),
            message_id=_as_str(data.get("message_id")),
            timestamp=_as_int(data.get("timestamp")),
            player=QueQiaoPlayer.from_dict(data.get("player")),
            message=_as_str(data.get("message")),
            raw_message=_as_str(data.get("raw_message")),
            command=_as_str(data.get("command")),
            death=QueQiaoTranslate.from_dict(data.get("death")),
            achievement=QueQiaoAchievement.from_dict(data.get("achievement")),
        )

    @property
    def is_chat(self) -> bool:
        return self.event_name == EVENT_CHAT

    @property
    def is_command(self) -> bool:
        return self.event_name == EVENT_COMMAND

    @property
    def is_join(self) -> bool:
        return self.event_name == EVENT_JOIN

    @property
    def is_quit(self) -> bool:
        return self.event_name == EVENT_QUIT

    @property
    def is_death(self) -> bool:
        return self.event_name == EVENT_DEATH

    @property
    def is_achievement(self) -> bool:
        return self.event_name == EVENT_ACHIEVEMENT

    @property
    def player_name(self) -> str:
        return self.player.display_name


@dataclass
class ServerStatus:
    """`get_status` 接口返回的服务器状态（鹊桥 >= v0.5.0）。"""

    server_type: str = ""
    server_version: str = ""
    online_players: int = 0
    max_players: int = 0
    description: str = ""
    favicon: str = ""
    host: str = ""
    port: int = 0
    cpu_cores: int = 0
    system_load: float = 0.0
    memory_total: int = 0
    memory_used: int = 0
    memory_percentage: float = 0.0

    @classmethod
    def from_dict(cls, data: object) -> "ServerStatus":
        if not isinstance(data, dict):
            return cls()

        ping = data.get("server_list_ping")
        ping = ping if isinstance(ping, dict) else {}
        players = ping.get("players")
        players = players if isinstance(players, dict) else {}
        version = ping.get("version")
        version = version if isinstance(version, dict) else {}
        cpu = data.get("cpu_information")
        cpu = cpu if isinstance(cpu, dict) else {}
        memory = data.get("memory_information")
        memory = memory if isinstance(memory, dict) else {}
        physical = memory.get("physical_memory")
        physical = physical if isinstance(physical, dict) else {}

        return cls(
            server_type=_as_str(data.get("server_type")),
            server_version=_as_str(data.get("server_version"))
            or _as_str(version.get("name")),
            online_players=_as_int(players.get("online")),
            max_players=_as_int(players.get("max")),
            description=_as_str(ping.get("description")),
            favicon=_as_str(ping.get("favicon")),
            host=_as_str(ping.get("host")),
            port=_as_int(ping.get("port")),
            cpu_cores=_as_int(cpu.get("cpu_cores")),
            system_load=_as_float(cpu.get("system_load")),
            memory_total=_as_int(physical.get("total")),
            memory_used=_as_int(physical.get("used")),
            memory_percentage=_as_float(physical.get("percentage")),
        )

    @property
    def memory_usage_text(self) -> str:
        """人类可读的内存占用描述。"""
        if not self.memory_total:
            return "未知"

        def _to_mb(size: int) -> str:
            return f"{size / 1024 / 1024:.1f}MB"

        return (
            f"{_to_mb(self.memory_used)} / {_to_mb(self.memory_total)}"
            f" ({self.memory_percentage:.1f}%)"
        )

    @property
    def players_text(self) -> str:
        return f"{self.online_players}/{self.max_players}"
