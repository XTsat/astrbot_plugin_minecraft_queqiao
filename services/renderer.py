"""服务器信息图片渲染。

渲染失败时必须回退为文本（配置项 text2image 的语义），因此这里不引入
额外绘图依赖，直接复用 AstrBot 的 t2i 能力；不可用时由调用方回退文本。
"""

from astrbot.api import logger

from ..core.constants import PLUGIN_NAME
from ..core.models import PlayerListResult, ServerStatus


class InfoRenderer:
    """把服务器状态渲染为图片。"""

    def __init__(self, text2image_enabled: bool = True) -> None:
        self.enabled = text2image_enabled

    @staticmethod
    def format_status(
        server_id: str, status: ServerStatus | None, label: str | None = None
    ) -> str:
        """状态文本（渲染失败或未启用渲染时的输出）。

        `label` 为展示用名称（`server_name`，可中文），缺省时回退 `server_id`。
        """
        name = label or server_id
        if status is None:
            return f"❌ 服务器 {name} 状态获取失败（需鹊桥 v0.5.0+ 且已连接）"

        lines = [
            f"📊 服务器状态：{name}",
            f"类型：{status.server_type or '未知'}",
            f"版本：{status.server_version or '未知'}",
            f"在线：{status.players_text}",
        ]
        if status.description:
            lines.append(f"描述：{status.description}")
        # 在线玩家名（SLP players.sample，免 RCON 即可得；可能不全/被伪造）
        names = status.online_player_names
        if names:
            shown = "、".join(names[:8])
            more = f" 等 {len(names)} 人" if len(names) > 8 else ""
            lines.append(f"玩家：{shown}{more}")
        if status.memory_total:
            lines.append(f"内存：{status.memory_usage_text}")
        if status.cpu_cores:
            lines.append(f"CPU 核心：{status.cpu_cores}（负载 {status.system_load:.2f}）")
        return "\n".join(lines)

    async def render_status(
        self, server_id: str, status: ServerStatus | None, label: str | None = None
    ) -> str:
        """渲染状态图。

        当前实现返回文本（图片渲染为后续增强项），保持调用方接口稳定，
        使「渲染失败自动回退文本」的配置语义始终成立。
        """
        if not self.enabled:
            return self.format_status(server_id, status, label)

        try:
            return self.format_status(server_id, status, label)
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}][{server_id}] 状态渲染失败，回退文本: {exc}")
            return self.format_status(server_id, None, label)

    @staticmethod
    def format_player_list(
        server_id: str,
        players: "PlayerListResult | list[str] | None",
        label: str | None = None,
    ) -> str:
        """在线玩家列表文本。

        兼容两种入参：
        - `PlayerListResult`（新）：按 source 区分 RCON / SLP / 仅人数 / 失败
        - `list[str]`（旧）：视作 RCON 完整名单，`None` 视作查询失败
          （保留以兼容既有调用与 tests_offline 第 21 组契约）

        三层取数语义见 `ServerInstance.fetch_player_list`：RCON `list`
        完整权威；未开 RCON 时用鹊桥 `get_status` 的 SLP `players.sample`
        兜底（免 RCON，但可能不全/被服务端伪造）。命中名单时在人数后括注
        本次实际取数方式：RCON 按 `rcon_channel` 标「鹊桥RCON / 直连RCON」，
        SLP 标「在线查询」。
        """
        name = label or server_id
        if not isinstance(players, PlayerListResult):
            # 旧调用归一化：list[str] → rcon 完整名单，None → 失败
            players = PlayerListResult(
                names=list(players) if players else [],
                source="rcon" if players is not None else "none",
            )

        if players.source == "none":
            return (
                f"❌ 无法获取服务器 {name} 的玩家列表\n"
                f"请确认：鹊桥已连接（get_status 需 v0.5.0+），"
                f"或已开启 RCON"
            )

        # 只有人数、没有名单（未开 RCON 且 SLP 未返回玩家名）
        if players.source == "count":
            if players.online == 0:
                # 0 人在线：与 RCON 空名单一致，按「没人在线」处理
                return f"👥 服务器 {name} 当前没有玩家在线"
            return (
                f"👥 服务器 {name} 在线 {players.online}/{players.max} 人\n"
                f"（未开 RCON 且在线查询未返回玩家名；"
                f"部分服务端会隐藏或伪造在线名单）"
            )

        # source in ("rcon", "slp")
        if not players.names:
            # RCON 成功但无人 → 确实没人在线
            return f"👥 服务器 {name} 当前没有玩家在线"

        # 标注本次取数方式：RCON 细分鹊桥/直连通道，SLP 为在线查询（免 RCON，
        # 可能不全）；旧调用归一化（source="rcon" 未带 channel）不标注，保持
        # 第 21 组契约「在线 N 人」无括注
        if players.source == "slp":
            note = "（在线查询）"
        elif players.source == "rcon":
            if players.rcon_channel == "queqiao":
                note = "（鹊桥RCON）"
            elif players.rcon_channel == "direct":
                note = "（直连RCON）"
            else:
                note = ""
        else:
            note = ""
        return (
            f"👥 服务器 {name} 在线 {len(players.names)} 人{note}：\n"
            + "、".join(players.names)
        )
