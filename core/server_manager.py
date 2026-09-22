"""服务器实例管理：把配置、鹊桥连接与 RCON 兜底聚合为可直接使用的运行时对象。"""

import asyncio
import time

from astrbot.api import logger

from .constants import PLUGIN_NAME
from .models import PlayerListResult, ServerStatus
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
        self.server_name = config.server_name
        self.online_players: set[str] = set()
        # 鹊桥 RCON（send_rcon_command）可用性：None=未确认，True=曾成功，
        # False=鹊桥明确报错/未开启 RCON。仅 WS 连接成功不代表鹊桥 RCON 可用，
        # 必须由真实指令执行结果确认（鹊桥侧未开启 RCON 时 send_rcon_command 报错）。
        self.queqiao_rcon_ok: bool | None = None
        # 本次连接建立时刻（None = 未连接），供仪表盘展示单服务器在线时长
        self.connected_at: float | None = None

        async def _wrapped_on_event(event) -> None:
            if hasattr(event, "is_join") and event.is_join:
                if getattr(event, "player_name", ""):
                    self.online_players.add(event.player_name)
            elif hasattr(event, "is_quit") and event.is_quit:
                if getattr(event, "player_name", ""):
                    self.online_players.discard(event.player_name)
            if on_event:
                res = on_event(event)
                if asyncio.iscoroutine(res):
                    await res

        async def _wrapped_on_connect() -> None:
            # 重连后 RCON 可用性未知，重新由指令执行结果确认
            self.queqiao_rcon_ok = None
            self.connected_at = time.time()
            if on_connect:
                res = on_connect()
                if asyncio.iscoroutine(res):
                    await res

        async def _wrapped_on_disconnect(reason: str) -> None:
            # 连接断开后鹊桥 RCON 必然不可用
            self.queqiao_rcon_ok = False
            self.connected_at = None
            if on_disconnect:
                res = on_disconnect(reason)
                if asyncio.iscoroutine(res):
                    await res

        self.client = QueQiaoClient(
            config,
            on_event=_wrapped_on_event,
            on_connect=_wrapped_on_connect,
            on_disconnect=_wrapped_on_disconnect,
        )
        self.rcon = RconClient(config)
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self.client.connected

    @property
    def connected_seconds(self) -> int:
        """本次连接已持续的秒数；未连接（或尚未握手成功）返回 0。"""
        if not self.connected or self.connected_at is None:
            return 0
        return max(0, int(time.time() - self.connected_at))

    def start(self) -> None:
        """启动连接任务并统一处理未捕获异常。"""
        if self._task and not self._task.done():
            return
        try:
            self._task = asyncio.create_task(self.client.start())
        except RuntimeError as exc:
            logger.error(f"[{PLUGIN_NAME}][{self.server_name}] 无法启动连接任务: {exc}")
            return
        self._task.add_done_callback(self._on_task_done)

    def _on_task_done(self, task: asyncio.Task) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.error(f"[{PLUGIN_NAME}][{self.server_name}] 连接任务异常退出: {exc}")

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

    async def get_status_model(self) -> ServerStatus | None:
        """获取服务器状态模型；未连接/失败返回 None（需鹊桥 >= v0.5.0）。

        把 `client.get_status()` 的原始 dict 包成 `ServerStatus`，供
        `handle_status` 与 `fetch_player_list`（SLP sample 兜底）共用。
        """
        raw = await self.client.get_status()
        return ServerStatus.from_dict(raw) if raw else None

    async def execute_command(self, command: str) -> str | None:
        """执行服务器指令，返回输出；两条通道都失败返回 None。

        鹊桥超时 = 结果未知（指令可能已执行），此时**不走** RCON 兜底，
        避免同一条指令被执行两遍；仅确定失败（未连接 / 明确报错）才兜底。

        本方法是 ``execute_command_with_channel`` 的薄包装，丢弃通道信息；
        需要区分「鹊桥RCON / 直连RCON」时直接调 ``execute_command_with_channel``。
        """
        output, _ = await self.execute_command_with_channel(command)
        return output

    async def execute_command_with_channel(
        self, command: str
    ) -> tuple[str | None, str]:
        """执行服务器指令，返回 ``(output, channel)``；两条通道都失败返回 ``(None, "")``。

        鹊桥超时 = 结果未知（指令可能已执行），此时**不走** RCON 兜底，
        避免同一条指令被执行两遍；仅确定失败（未连接 / 明确报错）才兜底。

        ``channel`` 取值（供渲染层标注实际取数通道）：
        - ``"queqiao"``：经鹊桥 ``send_rcon_command`` 执行成功
        - ``"direct"``：鹊桥通道不可用时回退到直连 RCON 执行成功
        - ``""``：未执行（未连接且未配直连 RCON）/ 鹊桥超时 / 全失败
        """
        if self.client.connected:
            try:
                output = await self.client.send_rcon_command(command)
            except QueQiaoTimeout:
                logger.warning(
                    f"[{PLUGIN_NAME}][{self.server_name}] 鹊桥执行指令响应超时"
                    "（指令可能已执行，不再走 RCON 兜底，避免重复执行）"
                )
                return None, ""
            if output is not None:
                # 鹊桥成功响应（有无输出均视为通道可用）
                self.queqiao_rcon_ok = True
                return output, "queqiao"
            # 鹊桥明确报错（未开启 RCON / 指令被拒）：标记通道不可用
            self.queqiao_rcon_ok = False

        if self.rcon.enabled:
            logger.info(
                f"[{PLUGIN_NAME}][{self.server_name}] 鹊桥通道不可用，回退直连 RCON"
            )
            output = await self.rcon.execute(command)
            if output is not None:
                return output, "direct"

        return None, ""

    async def fetch_player_list(self) -> PlayerListResult:
        """获取在线玩家，三层兜底（RCON list → SLP sample → 人数）：

        1. RCON ``list``（完整权威）：鹊桥 send_rcon_command → 直连 RCON
        2. 鹊桥 ``get_status`` 的 SLP ``players.sample``（**免 RCON**，
           可能不全/被服务端伪造）
        3. sample 为空时退回 ``online``/``max`` 人数
        4. 都失败 → ``source="none"``

        鹊桥执行 ``list`` 超时属「结果未知」：指令可能已执行，故不再走直连
        RCON 重发（同一条指令会执行两遍）；此时降级到 SLP sample 属**不同
        查询**（SLP ping），不构成重发，符合「超时 ≠ 失败，禁止重发」约定。
        """
        # ① RCON list（完整权威）：鹊桥 send_rcon_command → 直连 RCON 兜底
        #    记录实际通道（queqiao / direct），供渲染层标注取数方式
        output, channel = await self.execute_command_with_channel("list")
        if output is not None:
            parsed_names = RconClient.parse_player_list(output)
            self.online_players = set(parsed_names)
            return PlayerListResult(
                names=parsed_names,
                source="rcon",
                rcon_channel=channel,
            )

        # ② 鹊桥 get_status 的 SLP sample（免 RCON）
        status = await self.get_status_model()
        if status is not None:
            names = status.online_player_names
            if names:
                self.online_players.update(names)
                return PlayerListResult(
                    names=names,
                    online=status.online_players,
                    max=status.max_players,
                    source="slp",
                )
            # ②.5 若 SLP sample 未返回玩家名，但事件追踪缓存有记录
            if self.online_players:
                return PlayerListResult(
                    names=sorted(self.online_players),
                    online=max(len(self.online_players), status.online_players),
                    max=status.max_players,
                    source="event_cache",
                )
            # ③ sample 空且无缓存，退回人数
            return PlayerListResult(
                online=status.online_players,
                max=status.max_players,
                source="count",
            )

        # ④ 若 get_status 也失败，但事件追踪缓存有玩家
        if self.online_players:
            return PlayerListResult(
                names=sorted(self.online_players),
                online=len(self.online_players),
                source="event_cache",
            )

        # ⑤ 全失败
        return PlayerListResult(source="none")


class ServerManager:
    """多服务器实例的注册与生命周期管理。"""

    def __init__(self) -> None:
        self._servers: dict[str, ServerInstance] = {}

    def __contains__(self, server_name: str) -> bool:
        return server_name in self._servers

    def get(self, server_name: str) -> ServerInstance | None:
        return self._servers.get(server_name)

    def all(self) -> list[ServerInstance]:
        return list(self._servers.values())

    @property
    def server_names(self) -> list[str]:
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
        self._servers[config.server_name] = instance
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
