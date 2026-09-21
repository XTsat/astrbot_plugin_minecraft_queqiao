"""鹊桥 WebSocket 客户端。

支持两种连接方式（对应鹊桥文档的「正向 / 反向 Websocket」）：
- forward：本插件作为 Client 主动连接鹊桥的 WebSocket Server
- reverse：本插件作为 Server，等待鹊桥作为 Client 连入（租赁服场景）

职责边界：本模块只负责「连上、鉴权、收发 JSON、请求-响应关联、重连」，
不解析业务事件（交给调用方的 on_event 回调）。
"""

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote_plus

import websockets
from astrbot.api import logger

from .constants import (
    API_ACTIONBAR,
    API_BROADCAST,
    API_GET_STATUS,
    API_PRIVATE_MSG,
    API_RCON,
    API_TITLE,
    API_TIMEOUT,
    FATAL_CLOSE_CODES,
    FATAL_HTTP_STATUS,
    HEADER_AUTHORIZATION,
    HEADER_CLIENT_ORIGIN,
    HEADER_SELF_NAME,
    MAX_RECONNECT_WAIT,
    PING_INTERVAL,
    PING_TIMEOUT,
    PLUGIN_NAME,
    POST_TYPE_MESSAGE,
    POST_TYPE_NOTICE,
    POST_TYPE_RESPONSE,
    RESPONSE_SUCCESS,
)
from .models import QueQiaoEvent
from .models_config import ServerConfig

# 反向模式下按 (host, port) 共享同一个 WS Server，避免同端口多服务器互相抢占
_SHARED_SERVERS: dict[tuple[str, int], "SharedReverseServer"] = {}
_SHARED_LOCK = asyncio.Lock()


class QueQiaoTimeout(Exception):
    """API 请求已发出但超时未收到鹊桥响应（投递结果未知）。

    与「确定失败」不同：WebSocket 发送已成功，鹊桥大概率已收到并执行了请求，
    只是响应慢或响应丢失。因此调用方**不得**据此断定失败并原样重发——
    否则消息/指令会在游戏内重复执行（实测出现过 AI 回复发两遍）。

    - 展示类调用（broadcast / title / actionbar）：在封装层按「已投递」处理，
      吞掉本异常并返回 True
    - 需要精确决策的调用（私聊回复 / RCON 指令）：向上抛出，由调用方
      决定是否换通道（通常不换，避免重复）
    """

    def __init__(self, api: str, timeout: float) -> None:
        self.api = api
        self.timeout = timeout
        super().__init__(f"API {api} 响应超时(>{timeout:g}s)，投递结果未知")


def _get_header(headers: Any, name: str) -> str | None:
    """兼容不同 websockets 版本的 Header 读取（大小写不敏感）。"""
    if headers is None:
        return None
    with contextlib.suppress(Exception):
        value = headers.get(name)
        if value is not None:
            return str(value)
    with contextlib.suppress(Exception):
        value = headers.get(name.lower())
        if value is not None:
            return str(value)
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return str(value)
    return None


class SharedReverseServer:
    """可被多台服务器共用的反向 WebSocket 服务端，按 x-self-name 路由到对应客户端。"""

    def __init__(self, host: str, port: int, path: str) -> None:
        self.host = host
        self.port = port
        self.path = path if path.startswith("/") else f"/{path}"
        self.clients: dict[str, "QueQiaoClient"] = {}
        self._server: Any = None
        self._running = False

    @property
    def is_empty(self) -> bool:
        return not self.clients

    def register(self, server_id: str, client: "QueQiaoClient") -> None:
        self.clients[server_id] = client

    def unregister(self, server_id: str) -> None:
        self.clients.pop(server_id, None)

    async def start(self) -> None:
        if self._running:
            return
        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
            process_request=self._process_request,
            ping_interval=PING_INTERVAL,
            ping_timeout=PING_TIMEOUT,
        )
        self._running = True
        logger.info(
            f"[{PLUGIN_NAME}] 反向 WebSocket 服务端已启动: "
            f"ws://{self.host}:{self.port}{self.path}"
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), timeout=5)
            self._server = None
        logger.info(f"[{PLUGIN_NAME}] 反向 WebSocket 服务端已停止: {self.host}:{self.port}")

    async def _process_request(self, connection: Any, request: Any) -> Any:
        """握手阶段校验路径、来源标识与鉴权。返回 None 表示放行。"""
        path = getattr(request, "path", None) or getattr(connection, "path", "") or ""
        if "?" in path:
            path = path.split("?", 1)[0]

        if path != self.path:
            logger.warning(f"[{PLUGIN_NAME}] 反向 WS 路径不匹配: 期望 {self.path}, 实际 {path}")
            return connection.respond(404, "Invalid path")

        headers = getattr(request, "headers", None)
        self_name_raw = _get_header(headers, HEADER_SELF_NAME)
        if not self_name_raw:
            logger.warning(f"[{PLUGIN_NAME}] 反向 WS 缺少 x-self-name Header")
            return connection.respond(400, "Missing X-Self-Name Header")

        server_id = unquote_plus(self_name_raw)

        # 拒绝来自插件自身的回环连接，避免自己连自己造成消息风暴
        origin = _get_header(headers, HEADER_CLIENT_ORIGIN) or ""
        if origin.lower() == "astrbot":
            logger.warning(f"[{PLUGIN_NAME}] 反向 WS 拒绝 x-client-origin=astrbot 的连接")
            return connection.respond(403, "X-Client-Origin cannot be astrbot")

        client = self.clients.get(server_id)
        if client is None:
            logger.warning(
                f"[{PLUGIN_NAME}] 反向 WS 未知 server_id={server_id}，"
                f"已注册: {list(self.clients.keys())}"
            )
            return connection.respond(404, f"Unknown server_id: {server_id}")

        expected = client.config.access_token
        if expected:
            auth = _get_header(headers, HEADER_AUTHORIZATION) or ""
            token = auth[7:] if auth.startswith("Bearer ") else auth
            if token != expected:
                logger.warning(f"[{PLUGIN_NAME}] 反向 WS 鉴权失败: server_id={server_id}")
                return connection.respond(401, "Invalid access token")

        return None

    async def _handle_connection(self, websocket: Any) -> None:
        headers = getattr(websocket, "request_headers", None)
        if headers is None and hasattr(websocket, "request"):
            headers = getattr(websocket.request, "headers", None)

        server_id = unquote_plus(_get_header(headers, HEADER_SELF_NAME) or "")
        client = self.clients.get(server_id)
        if client is None:
            logger.warning(f"[{PLUGIN_NAME}] 反向 WS 连接后找不到客户端: {server_id}")
            await websocket.close(1008, "Unknown server")
            return

        logger.info(f"[{PLUGIN_NAME}] 反向 WS 鹊桥已连入: server_id={server_id}")
        await client.attach_reverse_connection(websocket)


class QueQiaoClient:
    """单台 MC 服务器的鹊桥连接。

    对外提供：
    - start() / stop()：连接生命周期（含自动重连）
    - call_api()：发请求并等待 echo 匹配的响应
    - 三个回调：on_event / on_connect / on_disconnect
    """

    def __init__(
        self,
        config: ServerConfig,
        on_event: Callable[[QueQiaoEvent], Awaitable[None]] | None = None,
        on_connect: Callable[[], Awaitable[None]] | None = None,
        on_disconnect: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self.server_id = config.server_id
        self.on_event = on_event
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

        self._ws: Any = None
        self._connected = False
        self._running = False
        self._closing = False
        self._retries = 0
        self._send_lock = asyncio.Lock()
        self._shared_server: SharedReverseServer | None = None
        self._client_gone = asyncio.Event()

        # echo -> Future，用于把 API 响应投递给等待者
        self._pending: dict[str, asyncio.Future] = {}

    # ---- 状态 ----

    @property
    def connected(self) -> bool:
        return self._connected

    # ---- 生命周期 ----

    async def start(self) -> None:
        """启动连接并在断开后按退避策略重连，直到 stop() 被调用。"""
        self._running = True
        self._closing = False

        if self.config.is_reverse:
            await self._run_reverse()
        else:
            await self._run_forward()

    async def stop(self) -> None:
        """关闭连接并停止重连。"""
        self._running = False
        self._closing = True
        self._connected = False
        self._client_gone.set()

        if self._shared_server is not None:
            await self._detach_shared_server()

        ws = self._ws
        self._ws = None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()

        self._fail_pending("连接已关闭")

    async def _run_forward(self) -> None:
        """正向模式：作为 Client 连接鹊桥的 WS Server。"""
        while self._running:
            try:
                async with websockets.connect(
                    self.config.ws_url,
                    additional_headers=self.config.forward_headers,
                    ping_interval=PING_INTERVAL,
                    ping_timeout=PING_TIMEOUT,
                    proxy=None,
                ) as websocket:
                    await self._on_established(websocket)
                    async for message in websocket:
                        await self._dispatch(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._on_lost(exc)
                if not self._should_retry(exc):
                    break
                await self._backoff()

        self._connected = False
        self._ws = None

    async def _run_reverse(self) -> None:
        """反向模式：作为 Server 等待鹊桥连入，连接由 SharedReverseServer 交付。"""
        await self._attach_shared_server()
        # 阻塞直到 stop() 被调用；期间连接建立/断开由回调驱动
        with contextlib.suppress(asyncio.CancelledError):
            await self._client_gone.wait()

    async def attach_reverse_connection(self, websocket: Any) -> None:
        """反向模式：接住 SharedReverseServer 交付的连接。"""
        old = self._ws
        if old is not None and old is not websocket:
            with contextlib.suppress(Exception):
                await old.close(1000, "Replaced by new connection")

        self._ws = websocket
        self._client_gone.clear()
        await self._on_established(websocket)

        try:
            async for message in websocket:
                await self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}][{self.server_id}] 反向 WS 连接异常: {exc}")
        finally:
            if self._ws is websocket:
                self._ws = None
                if self._connected:
                    self._connected = False
                    if self.on_disconnect:
                        with contextlib.suppress(Exception):
                            await self.on_disconnect("鹊桥连接已断开")
            self._fail_pending("连接已断开")
            self._client_gone.set()

    async def _on_established(self, websocket: Any) -> None:
        self._ws = websocket
        self._connected = True
        self._retries = 0
        logger.info(
            f"[{PLUGIN_NAME}][{self.server_id}] 已连接鹊桥 "
            f"({'反向' if self.config.is_reverse else self.config.ws_url})"
        )
        if self.on_connect:
            with contextlib.suppress(Exception):
                await self.on_connect()

    async def _on_lost(self, exc: Exception) -> None:
        was_connected = self._connected
        self._connected = False
        if was_connected and self.on_disconnect:
            with contextlib.suppress(Exception):
                await self.on_disconnect(str(exc))
        self._fail_pending("连接已断开")

    def _should_retry(self, exc: Exception) -> bool:
        """判断异常是否值得重试（鉴权失败等致命错误不重试）。"""
        if not self._running:
            return False

        if isinstance(exc, websockets.exceptions.ConnectionClosed):
            return exc.code not in FATAL_CLOSE_CODES

        invalid_status = getattr(websockets.exceptions, "InvalidStatus", None) or getattr(
            websockets.exceptions, "InvalidStatusCode", None
        )
        if invalid_status is not None and isinstance(exc, invalid_status):
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            return status not in FATAL_HTTP_STATUS

        if self.config.max_reconnect and self._retries >= self.config.max_reconnect:
            logger.error(
                f"[{PLUGIN_NAME}][{self.server_id}] 重连次数已达上限 "
                f"({self.config.max_reconnect})，停止重连"
            )
            return False

        return True

    @staticmethod
    def _reconnect_wait(retries: int, config: ServerConfig) -> tuple[int, str]:
        """计算第 `retries` 次重连失败后的等待秒数与阶段名。

        两段式退避：
        - 退避段（前 `low_frequency_threshold` 次）：按
          `reconnect_interval × 次数` 线性递增，上限 `MAX_RECONNECT_WAIT` 秒；
        - 低频段（超过阈值后）：固定等待 `low_frequency_interval` 秒，
          避免长期断线时仍高频打扰；
        - `low_frequency_threshold` 配 0 表示关闭低频，始终按退避段计算。
        """
        threshold = config.low_frequency_threshold
        if threshold > 0 and retries > threshold:
            return config.low_frequency_interval, "低频"
        return min(config.reconnect_interval * retries, MAX_RECONNECT_WAIT), "退避"

    async def _backoff(self) -> None:
        self._retries += 1
        if self.config.max_reconnect and self._retries > self.config.max_reconnect:
            self._running = False
            return
        wait, stage = self._reconnect_wait(self._retries, self.config)
        logger.warning(
            f"[{PLUGIN_NAME}][{self.server_id}] {stage}重试：{wait} 秒后重连 "
            f"(第 {self._retries} 次)"
        )
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(wait)

    # ---- 反向模式的共享服务端 ----

    async def _attach_shared_server(self) -> None:
        key = (self.config.reverse_host, self.config.reverse_port)
        async with _SHARED_LOCK:
            shared = _SHARED_SERVERS.get(key)
            if shared is None:
                shared = SharedReverseServer(
                    self.config.reverse_host,
                    self.config.reverse_port,
                    self.config.normalized_path,
                )
                _SHARED_SERVERS[key] = shared
            elif shared.path != self.config.normalized_path:
                logger.warning(
                    f"[{PLUGIN_NAME}] 端口 {self.config.reverse_port} 已使用 path="
                    f"{shared.path}，服务器 {self.server_id} 的 path="
                    f"{self.config.normalized_path} 将被忽略"
                )
            shared.register(self.server_id, self)
            self._shared_server = shared
            try:
                await shared.start()
            except OSError as exc:
                shared.unregister(self.server_id)
                _SHARED_SERVERS.pop(key, None)
                self._shared_server = None
                logger.error(
                    f"[{PLUGIN_NAME}][{self.server_id}] 反向 WS 服务端启动失败 "
                    f"({self.config.reverse_host}:{self.config.reverse_port}): {exc}"
                )
                self._running = False
                raise

    async def _detach_shared_server(self) -> None:
        shared = self._shared_server
        if shared is None:
            return
        async with _SHARED_LOCK:
            shared.unregister(self.server_id)
            if shared.is_empty:
                key = (shared.host, shared.port)
                if _SHARED_SERVERS.get(key) is shared:
                    _SHARED_SERVERS.pop(key, None)
                await shared.stop()
            self._shared_server = None

    # ---- 消息收发 ----

    async def _dispatch(self, raw: str | bytes) -> None:
        """接收入口：先尝试投递给 API 等待者，其余作为事件解析。"""
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                logger.error(f"[{PLUGIN_NAME}][{self.server_id}] 收到无法解码的消息")
                return

        try:
            data = json.loads(raw)
        except ValueError:
            logger.error(f"[{PLUGIN_NAME}][{self.server_id}] 无法解析 JSON: {raw[:200]}")
            return

        if not isinstance(data, dict):
            return

        if self._resolve_pending(data):
            return

        post_type = data.get("post_type")
        if post_type in (POST_TYPE_MESSAGE, POST_TYPE_NOTICE):
            event = QueQiaoEvent.from_dict(data)
            if self.on_event:
                try:
                    await self.on_event(event)
                except Exception as exc:
                    logger.error(
                        f"[{PLUGIN_NAME}][{self.server_id}] 事件处理异常 "
                        f"({event.event_name}): {exc}"
                    )
        elif post_type != POST_TYPE_RESPONSE:
            logger.debug(f"[{PLUGIN_NAME}][{self.server_id}] 忽略未知消息: {raw[:200]}")

    def _resolve_pending(self, data: dict) -> bool:
        """把 API 响应投递给等待中的 Future。

        返回 True 表示该消息已被消费，不再当作事件处理。
        """
        if not self._pending or data.get("post_type") != POST_TYPE_RESPONSE:
            return False

        echo = data.get("echo")
        future = self._pending.pop(echo, None) if echo else None
        if future is None:
            return False

        if not future.done():
            future.set_result(data)
        return True

    def _fail_pending(self, reason: str) -> None:
        """连接断开时清理所有等待者，避免调用方永久挂起。"""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError(reason))
        self._pending.clear()

    async def _send(self, payload: dict) -> bool:
        ws = self._ws
        if ws is None or not self._connected:
            logger.warning(f"[{PLUGIN_NAME}][{self.server_id}] 发送失败：连接未建立")
            return False
        try:
            async with self._send_lock:
                await ws.send(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}][{self.server_id}] 发送异常: {exc}")
            return False

    async def call_api(
        self, api: str, data: dict | None = None, timeout: float = API_TIMEOUT
    ) -> dict | None:
        """调用鹊桥 API 并等待响应。

        必须在发送前登记等待者，否则鹊桥的快速响应会因找不到 echo 而被丢弃。
        """
        if not self._connected:
            return None

        echo = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[echo] = future

        payload: dict[str, Any] = {"api": api, "echo": echo}
        if data:
            payload["data"] = data

        try:
            if not await self._send(payload):
                self._pending.pop(echo, None)
                return None
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(echo, None)
            logger.warning(
                f"[{PLUGIN_NAME}][{self.server_id}] API {api} 响应超时"
                "（请求可能已投递，勿据此重发）"
            )
            raise QueQiaoTimeout(api, timeout) from None
        except ConnectionError as exc:
            logger.warning(f"[{PLUGIN_NAME}][{self.server_id}] API {api} 失败: {exc}")
            return None

    # ---- 业务接口封装 ----

    async def broadcast(self, text: str, color: str = "white") -> bool:
        """广播文本到服务器内所有玩家。

        响应超时按「已投递」处理返回 True：广播属展示类消息，WS 发送成功后
        鹊桥大概率已执行；若按失败返回 False，上层重发/重试会让玩家看到两遍。
        """
        component: dict[str, Any] = {"text": text}
        if color:
            component["color"] = color
        try:
            result = await self.call_api(API_BROADCAST, {"message": [component]})
        except QueQiaoTimeout:
            return True
        return self._is_success(result)

    async def send_private_message(
        self, text: str, uuid_str: str = "", nickname: str = "", color: str = "white"
    ) -> bool:
        """私聊指定玩家（uuid 优先，缺失时用 nickname）。

        响应超时向上抛 `QueQiaoTimeout`：私聊可能已送达游戏内，调用方
        不得在超时后改用广播重发（玩家会收到两份回复），应直接放弃本次发送。
        """
        if not uuid_str and not nickname:
            return False
        component: dict[str, Any] = {"text": text}
        if color:
            component["color"] = color
        result = await self.call_api(
            API_PRIVATE_MSG,
            {
                "uuid": uuid_str or None,
                "nickname": nickname or None,
                "message": [component],
            },
        )
        return self._is_success(result)

    async def send_title(
        self, title: str, subtitle: str = "", fade_in: int = 20, stay: int = 70, fade_out: int = 20
    ) -> bool:
        """推送标题。响应超时按「已投递」处理（展示类消息，禁止重发）。"""
        if not title and not subtitle:
            return False
        data: dict[str, Any] = {
            "fade_in": fade_in,
            "stay": stay,
            "fade_out": fade_out,
        }
        if title:
            data["title"] = {"text": title}
        if subtitle:
            data["subtitle"] = {"text": subtitle}
        try:
            result = await self.call_api(API_TITLE, data)
        except QueQiaoTimeout:
            return True
        return self._is_success(result)

    async def send_actionbar(self, text: str) -> bool:
        """推送状态栏消息。响应超时按「已投递」处理（展示类消息，禁止重发）。"""
        try:
            result = await self.call_api(API_ACTIONBAR, {"message": [{"text": text}]})
        except QueQiaoTimeout:
            return True
        return self._is_success(result)

    async def send_rcon_command(self, command: str, timeout: float = API_TIMEOUT) -> str | None:
        """通过鹊桥执行 RCON 指令，返回命令输出；失败返回 None。

        响应超时向上抛 `QueQiaoTimeout`：指令可能已在服务器执行，
        调用方不得换直连 RCON 重发（同一条指令会执行两遍）。
        """
        result = await self.call_api(API_RCON, {"command": command}, timeout=timeout)
        if not self._is_success(result):
            return None
        payload = result.get("data") if result else None
        if payload is None:
            return ""
        return payload if isinstance(payload, str) else str(payload)

    async def get_status(self) -> dict | None:
        """获取服务器状态（需要鹊桥 >= v0.5.0）；超时/失败返回 None。"""
        try:
            result = await self.call_api(API_GET_STATUS, None)
        except QueQiaoTimeout:
            return None
        if not self._is_success(result):
            return None
        payload = result.get("data")
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _is_success(result: dict | None) -> bool:
        if not result:
            return False
        return result.get("status") == RESPONSE_SUCCESS or result.get("code") == 200
