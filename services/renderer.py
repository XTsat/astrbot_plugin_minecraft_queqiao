"""服务器信息图片渲染。

渲染失败时必须回退为文本（配置项 text2image 的语义），因此这里不引入
额外绘图依赖，直接复用 AstrBot 的 t2i 能力；不可用时由调用方回退文本。
"""

from astrbot.api import logger

from ..core.constants import PLUGIN_NAME
from ..core.models import ServerStatus


class InfoRenderer:
    """把服务器状态渲染为图片。"""

    def __init__(self, text2image_enabled: bool = True) -> None:
        self.enabled = text2image_enabled

    @staticmethod
    def format_status(server_id: str, status: ServerStatus | None) -> str:
        """状态文本（渲染失败或未启用渲染时的输出）。"""
        if status is None:
            return f"❌ 服务器 {server_id} 状态获取失败（需鹊桥 v0.5.0+ 且已连接）"

        lines = [
            f"📊 服务器状态：{server_id}",
            f"类型：{status.server_type or '未知'}",
            f"版本：{status.server_version or '未知'}",
            f"在线：{status.players_text}",
        ]
        if status.description:
            lines.append(f"描述：{status.description}")
        if status.memory_total:
            lines.append(f"内存：{status.memory_usage_text}")
        if status.cpu_cores:
            lines.append(f"CPU 核心：{status.cpu_cores}（负载 {status.system_load:.2f}）")
        return "\n".join(lines)

    async def render_status(self, server_id: str, status: ServerStatus | None) -> str:
        """渲染状态图。

        当前实现返回文本（图片渲染为后续增强项），保持调用方接口稳定，
        使「渲染失败自动回退文本」的配置语义始终成立。
        """
        if not self.enabled:
            return self.format_status(server_id, status)

        try:
            return self.format_status(server_id, status)
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}][{server_id}] 状态渲染失败，回退文本: {exc}")
            return self.format_status(server_id, None)

    @staticmethod
    def format_player_list(server_id: str, players: list[str] | None) -> str:
        """在线玩家列表文本。"""
        if players is None:
            return (
                f"❌ 无法获取服务器 {server_id} 的玩家列表\n"
                f"请确认：鹊桥已开启 RCON，或在配置中启用直连 RCON 兜底"
            )
        if not players:
            return f"👥 服务器 {server_id} 当前没有玩家在线"
        return f"👥 服务器 {server_id} 在线 {len(players)} 人：\n" + "、".join(players)
