"""直连 RCON 客户端（兜底通道）。

当鹊桥未开启 RCON 时，本模块提供一条独立的 RCON 通道，用于执行远程指令与
查询在线玩家。依赖 `aio-mc-rcon`，采用惰性 import：未安装时插件其余功能不受影响。
"""

import asyncio
import contextlib

from astrbot.api import logger

from .constants import PLUGIN_NAME
from .models_config import ServerConfig

try:  # 惰性降级：缺失依赖时仅关闭兜底通道
    import aiomcrcon

    _RCON_AVAILABLE = True
except ImportError:  # pragma: no cover - 取决于运行环境
    aiomcrcon = None  # type: ignore[assignment]
    _RCON_AVAILABLE = False


class RconClient:
    """单台服务器的 RCON 连接，带串行化的自动重连。"""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.server_name = config.server_name
        self._client: object | None = None
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        """是否具备启用条件（配置开启 + 依赖可用 + 密码已填）。"""
        if not self.config.rcon_fallback_enabled:
            return False
        if not self.config.rcon_password:
            logger.warning(
                f"[{PLUGIN_NAME}][{self.server_name}] 已启用 RCON 兜底但未配置密码，跳过"
            )
            return False
        if not _RCON_AVAILABLE:
            logger.warning(
                f"[{PLUGIN_NAME}][{self.server_name}] 已启用 RCON 兜底但未安装 "
                f"aio-mc-rcon，请执行 pip install aio-mc-rcon"
            )
            return False
        return True

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """建立 RCON 连接（幂等）。"""
        if not self.enabled:
            return False
        if self._connected and self._client is not None:
            return True

        async with self._lock:
            if self._connected and self._client is not None:
                return True
            try:
                client = aiomcrcon.Client(
                    self.config.rcon_host,
                    self.config.rcon_port,
                    self.config.rcon_password,
                )
                await client.connect()
            except Exception as exc:
                logger.error(
                    f"[{PLUGIN_NAME}][{self.server_name}] RCON 连接失败 "
                    f"({self.config.rcon_host}:{self.config.rcon_port}): {exc}"
                )
                self._client = None
                self._connected = False
                return False

            self._client = client
            self._connected = True
            logger.info(
                f"[{PLUGIN_NAME}][{self.server_name}] RCON 已连接 "
                f"{self.config.rcon_host}:{self.config.rcon_port}"
            )
            return True

    async def execute(self, command: str) -> str | None:
        """执行指令并返回输出；失败返回 None（失败后自动断开以便下次重连）。"""
        if not self.enabled:
            return None

        if not await self.connect():
            return None

        client = self._client
        if client is None:
            return None

        try:
            async with self._lock:
                response = await client.send_cmd(command)
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}][{self.server_name}] RCON 执行失败: {exc}")
            await self.close()
            return None

        # aiomcrcon 返回 (response, request_id)
        if isinstance(response, tuple) and response:
            return str(response[0])
        return str(response) if response is not None else ""

    async def close(self) -> None:
        """关闭连接。"""
        client = self._client
        self._client = None
        self._connected = False
        if client is None:
            return
        with contextlib.suppress(Exception):
            await client.close()

    @staticmethod
    def parse_player_list(output: str | None) -> list[str]:
        """从 `list` 指令输出中解析玩家名列表。

        兼容形如：`There are 2 of a max of 20 players online: Alice, Bob`
        """
        if not output or ":" not in output:
            return []
        _, _, names = output.partition(":")
        return [name.strip() for name in names.split(",") if name.strip()]
