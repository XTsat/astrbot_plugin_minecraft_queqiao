"""服务器实例管理：把配置、鹊桥连接与 RCON 兜底聚合为可直接使用的运行时对象。"""

import asyncio

from astrbot.api import logger

from .constants import PLUGIN_NAME
from .models_config import ServerConfig
from .queqiao_client import QueQiaoClient, QueQiaoTimeout
from .rcon_client import RconClient


class ServerInstance:
    """一台 MC 服务器的运行时聚合对象。"""

    def __init__(
        self,
        config: ServerConfig,
        on_event=None,
        on_connect=None,
        on_disconnect=None,
    ) -> None:
        self.config = config
        self.server_id = config.server_id
        self.client = QueQiaoClient(
            config,
            on_event=on_event,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
        )
        self.rcon = RconClient(config)
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self.client.connected

    def start(self) -> None:
        """启动连接任务并统一处理未捕获异常。"""
        if self._task and not self._task.done():
            return
        try:
            self._task = asyncio.create_task(self.client.start())
        except RuntimeError as exc:
            logger.error(f"[{PLUGIN_NAME}][{self.server_id}] 无法启动连接任务: {exc}")
            return
        self._task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.error(f"[{PLUGIN_NAME}][{self.server_id}] 连接任务异常退出: {exc}")

    async def stop(self) -> None:
        """停止连接与 RCON。"""
        await self.client.stop()
        await self.rcon.close()

        task = self._task
        self._task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # ---- 指令执行：鹊桥优先，RCON 兜底 ----

    async def execute_command(self, command: str) -> str | None:
        """执行服务器指令，返回输出；两条通道都失败返回 None。

        鹊桥超时 = 结果未知（指令可能已执行），此时**不走** RCON 兜底，
        避免同一条指令被执行两遍；仅确定失败（未连接 / 明确报错）才兜底。
        """
        if self.client.connected:
            try:
                output = await self.client.send_rcon_command(command)
            except QueQiaoTimeout:
                logger.warning(
                    f"[{PLUGIN_NAME}][{self.server_id}] 鹊桥执行指令响应超时"
                    "（指令可能已执行，不再走 RCON 兜底，避免重复执行）"
                )
                return None
            if output is not None:
                return output

        if self.rcon.enabled:
            logger.info(
                f"[{PLUGIN_NAME}][{self.server_id}] 鹊桥通道不可用，回退直连 RCON"
            )
            return await self.rcon.execute(command)

        return None

    async def fetch_player_list(self) -> list[str] | None:
        """获取在线玩家名列表；失败返回 None（与「空列表」区分）。"""
        output = await self.execute_command("list")
        if output is None:
            return None
        return RconClient.parse_player_list(output)


class ServerManager:
    """多服务器实例的注册与生命周期管理。"""

    def __init__(self) -> None:
        self._servers: dict[str, ServerInstance] = {}

    def __contains__(self, server_id: str) -> bool:
        return server_id in self._servers

    def get(self, server_id: str) -> ServerInstance | None:
        return self._servers.get(server_id)

    def all(self) -> list[ServerInstance]:
        return list(self._servers.values())

    @property
    def server_ids(self) -> list[str]:
        return list(self._servers.keys())

    def add(
        self,
        config: ServerConfig,
        on_event=None,
        on_connect=None,
        on_disconnect=None,
    ) -> ServerInstance:
        instance = ServerInstance(
            config,
            on_event=on_event,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
        )
        self._servers[config.server_id] = instance
        return instance

    async def start_all(self) -> None:
        for instance in self._servers.values():
            instance.start()

    async def stop_all(self) -> None:
        await asyncio.gather(
            *(instance.stop() for instance in self._servers.values()),
            return_exceptions=True,
        )
        self._servers.clear()
