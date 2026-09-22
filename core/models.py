"""鹊桥 V2 事件与实体的数据模型。

设计要点：鹊桥各服务端（原版/Spigot/Paper/Folia/Velocity/Forge/Fabric/NeoForge）
在同一事件的字段填充程度上差异很大（例如原版 Player 仅有 nickname，
Velocity 仅有 nickname/uuid/is_op），因此所有解析一律走 `.get()` 兜底，
缺失字段降级为空值而不抛异常。
"""

import re
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


# § 后跟一位格式/颜色代码（如 §a、§6、§r）。SLP 的 players.sample 名字在
# 部分服务端会被塞入这类彩色/广告文本（如 CubeCraft 的宣传链接），转发展示
# 前剥离成可读纯文本。玩家正常昵称不含 §，剥离安全。
_SECTION_RE = re.compile(r"§.")


def _strip_format_codes(value: str) -> str:
    """去掉 Minecraft 文本格式码（§ 后跟一位代码）与首尾空白。"""
    if not value:
        return ""
    return _SECTION_RE.sub("", value).strip()


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
    """成就详情。

    文本来源随鹊桥版本与服务端而异，**任何单一字段都可能为空**：
    - `0.4.1+`：`text` 已移除，文本只在 `translate.text`
    - `translate.text` 是「回退文本或原始消息」：未开启 `enable_translation`
      时鹊桥可能给出空壳 `{key, args, text: ""}`，此时连英文原文也取不到
    - `0.4.0` 及以前：文本在 `text`
    - 服务端差异：`Spigot` 仅含 `key`，部分 Forge 缺 `display.description`

    因此取出成就名必须走完整降级链，不能只认其中一两个字段。
    """

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
            # title/description 在 0.4.1+ 可能是 Translate 对象；
            # 该形态下 text 同样是「回退文本」，缺失时回落到 key（即翻译键本身）
            title=cls._translate_text(title),
            description=cls._translate_text(description),
            text=_as_str(data.get("text")),
            # 字段名以实测为准：鹊桥实际推送的是 `translation`（见原始 payload），
            # 文档中的 `translate` 作为兼容一并接受，两者取先有值者。
            translate=QueQiaoTranslate.from_dict(
                data.get("translation") or data.get("translate")
            ),
        )

    @staticmethod
    def _translate_text(value: object) -> str:
        """把 Display 的 title/description 取值，兼容纯字符串与 Translate 对象。

        Translate 对象的 `text` 缺失时回落到 `key`（翻译键），
        这样至少能显示 `advancements.husbandry.sweet_dreams.title`
        而不是空字符串 —— 有信息量好过没有。
        """
        if isinstance(value, dict):
            return _as_str(value.get("text")) or _as_str(value.get("key"))
        return _as_str(value)

    @property
    def display_text(self) -> str:
        """按可用性依次降级取出成就文本。

        顺序：`translate.text`（0.4.1+）→ `text`（0.4.0-）
        → `display.title`（部分服务端只填了显示名）→ 由 `key` 拼出的可读占位。

        前两条是协议正规定义；后两条是防御性兜底：`display.title` 在
        鹊桥未开启翻译、或服务端不填 `translate` 时仍可能有值，
        而 `key`（如 `minecraft:husbandry/sweet_dreams`）几乎总是存在，
        据此退化出成就标识远好于丢弃整条消息。

        返回空串表示三者皆无，由调用方决定最终文案。
        """
        if self.translate.text:
            return self.translate.text
        if self.text:
            return self.text
        if self.title:
            return self.title
        return ""

    @property
    def display_name(self) -> str:
        """成就的可读名称（不含玩家），用于兜底文案。

        与 `display_text` 的区别：这里只关心「成就叫什么」，
        因此取 `display.title` 优先于整句事件文本。
        """
        if self.title:
            return self.title
        if self.translate.text:
            return self.translate.text
        if self.text:
            return self.text
        return self.key


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
    """`get_status` 接口返回的服务器状态（鹊桥 >= v0.5.0）。

    `player_sample` 取自 SLP 的 `server_list_ping.players.sample`：每项
    `(name, uuid)`，name 已剥离 § 格式码。它免 RCON 即可得，但可能不全
    或被服务端伪造（原版端会截断、反 bot 插件会留空/塞假名）。
    """

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
    player_sample: list[tuple[str, str]] = field(default_factory=list)

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

        # SLP players.sample：在线玩家名+UUID 样本（免 RCON，但可能不全/伪造）
        player_sample: list[tuple[str, str]] = []
        sample_raw = players.get("sample")
        if isinstance(sample_raw, list):
            for item in sample_raw:
                if not isinstance(item, dict):
                    continue
                name = _strip_format_codes(_as_str(item.get("name")))
                if name:
                    player_sample.append((name, _as_str(item.get("id"))))

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
            player_sample=player_sample,
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

    @property
    def online_player_names(self) -> list[str]:
        """SLP players.sample 的在线玩家名（已剥离格式码，可能不全/被伪造）。"""
        return [name for name, _ in self.player_sample]


@dataclass
class PlayerListResult:
    """在线玩家查询结果：`fetch_player_list` 三层兜底的统一返回。

    source 取值：
    - ``"rcon"``：RCON ``list`` 指令，完整且权威（鹊桥 send_rcon / 直连 RCON）
    - ``"slp"``：鹊桥 ``get_status`` 的 SLP ``players.sample``，**免 RCON**，
      但可能不全或被服务端伪造
    - ``"count"``：sample 为空，仅拿到 ``online``/``max`` 人数
    - ``"none"``：两条通道都失败

    ``rcon_channel`` 仅在 ``source == "rcon"`` 时有意义，用于细分名单的实际
    取数通道（供渲染层标注「鹊桥RCON / 直连RCON」）：
    - ``"queqiao"``：经鹊桥 ``send_rcon_command`` 执行 ``list``
    - ``"direct"``：鹊桥通道不可用时回退到直连 RCON
    - ``""``：未指定（旧调用归一化 / 手动构造），渲染层按「不标注通道」处理
    """

    names: list[str] = field(default_factory=list)
    online: int = 0
    max: int = 0
    source: str = ""
    rcon_channel: str = ""
