"""内置图片 HTTP 服务：把无公开 URL 的图片转成玩家客户端可访问的链接。

场景：部分协议端（如某些 onebot 客户端）收到的图片只有 base64 / 本地文件，
没有对外可访问的 URL。而 ChatImage 需要玩家**自己的客户端**去下载图片，
因此必须有一个玩家可达的地址。

本服务把图片字节缓存在插件内，提供 `GET /img/<token>` 端点，配合
`builtin_http` 图床条目的 `base_url`（玩家可达地址前缀，如
`http://公网IP:8765`）生成 `{base_url}/img/<token>` 广播进游戏。

约束：
- 玩家可达性由 `base_url` 决定，不能填 127.0.0.1（除非玩家与服务同机）
- aiohttp 是 AstrBot 运行时的既有依赖，这里惰性 import，避免离线自检依赖它
- 服务实例由上层（`BuiltinHttpUploader`）管理生命周期，通常只启动一个
"""

import contextlib
import time
import uuid
from typing import Any

from astrbot.api import logger

from ..core.constants import IMAGE_HOST_MAX_IMAGES, IMAGE_HOST_TTL, PLUGIN_NAME


def guess_image_content_type(data: bytes) -> str:
    """按文件魔数猜测图片 MIME，供 HTTP 响应使用；无法识别回退 octet-stream。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return "application/octet-stream"


class ImageHost:
    """图片字节缓存 + HTTP 对外服务。

    - `register(data)`：登记一张图片并返回 `{base_url}/img/<token>`
    - `start(host, port)` / `stop()`：aiohttp 服务生命周期
    - 仅当 `base_url` 非空（`enabled`）时才登记；未启用时 resolve 走其它兜底
    """

    def __init__(self) -> None:
        self.base_url = ""
        self._images: dict[str, tuple[float, bytes]] = {}
        self._runner: Any = None
        self._site: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    async def start(self, host: str, port: int) -> None:
        """启动 HTTP 监听。aiohttp 为 AstrBot 运行时既有依赖，惰性导入。"""
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/img/{token}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()
        logger.info(
            f"[{PLUGIN_NAME}] 图片 HTTP 服务已启动: http://{host}:{port}/img/<token> "
            f"（对外地址: {self.base_url}）"
        )

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            if self._site is not None:
                await self._site.stop()
        with contextlib.suppress(Exception):
            if self._runner is not None:
                await self._runner.cleanup()
        self._site = None
        self._runner = None
        self._images.clear()

    def register(self, data: bytes) -> str | None:
        """登记一张图片，返回对外访问 URL；未启用或数据为空返回 None。"""
        if not self.enabled or not data:
            return None
        self._gc()
        token = uuid.uuid4().hex
        self._images[token] = (time.time(), data)
        return f"{self.base_url}/img/{token}"

    def _gc(self) -> None:
        """条目超过上限时清理过期项，防止长期运行内存膨胀。"""
        if len(self._images) < IMAGE_HOST_MAX_IMAGES:
            return
        now = time.time()
        expired = [
            token
            for token, (stamp, _) in self._images.items()
            if now - stamp > IMAGE_HOST_TTL
        ]
        for token in expired:
            self._images.pop(token, None)

    async def _handle(self, request: Any) -> Any:
        from aiohttp import web

        token = request.match_info.get("token", "")
        entry = self._images.get(token)
        if entry is None:
            return web.Response(status=404)
        stamp, data = entry
        if time.time() - stamp > IMAGE_HOST_TTL:
            self._images.pop(token, None)
            return web.Response(status=404)
        return web.Response(body=data, content_type=guess_image_content_type(data))