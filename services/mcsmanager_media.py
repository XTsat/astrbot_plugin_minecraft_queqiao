"""MCSManager-backed E33Chat media storage."""

from __future__ import annotations

from urllib.parse import quote, urljoin, urlparse

from ..core.constants import E33CHAT_MEDIA_MAX_FILE_BYTES, E33CHAT_MEDIA_QUOTA_BYTES


class MCSManagerMediaError(RuntimeError):
    """Safe-to-log MCSManager failure without request URLs or credentials."""


def describe_mcsmanager_error(exc: Exception) -> str:
    if isinstance(exc, MCSManagerMediaError):
        return str(exc)
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        return f"{type(exc).__name__}: 缺少模块 {exc.name}"
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return f"{type(exc).__name__}: HTTP {status}"
    return type(exc).__name__


class MCSManagerMedia:
    def __init__(
        self,
        panel_url: str,
        api_key: str,
        daemon_id: str,
        instance_uuid: str,
        media_dir: str,
        daemon_url: str = "",
        timeout: float = 15,
    ) -> None:
        self.panel_url = panel_url.strip().rstrip("/") + "/"
        self.api_key = api_key.strip()
        self.daemon_id = daemon_id.strip()
        self.instance_uuid = instance_uuid.strip()
        self.media_dir = media_dir.strip().strip("/\\")
        self.daemon_url = daemon_url.strip().rstrip("/")
        self.timeout_seconds = timeout

    def _client_options(self):
        import aiohttp

        return aiohttp.ClientTimeout(total=self.timeout_seconds)

    def _validate(self) -> None:
        if not all((self.panel_url, self.api_key, self.daemon_id, self.instance_uuid, self.media_dir.strip("/"))):
            raise MCSManagerMediaError(
                "面板地址、API Key、Daemon ID、实例 UUID 和实例内媒体目录均须填写"
            )
        if urlparse(self.panel_url).scheme not in ("http", "https"):
            raise MCSManagerMediaError("面板地址必须以 http:// 或 https:// 开头")

    async def _ticket(
        self, endpoint: str, *, params: dict[str, str], method: str = "GET"
    ) -> dict:
        import aiohttp

        self._validate()
        query = {
            "daemonId": self.daemon_id,
            "uuid": self.instance_uuid,
            "apikey": self.api_key,
            **params,
        }
        async with aiohttp.ClientSession(timeout=self._client_options()) as session:
            async with session.request(
                method,
                urljoin(self.panel_url, endpoint),
                params=query,
                headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json; charset=utf-8"},
            ) as response:
                if not 200 <= response.status < 300:
                    raise MCSManagerMediaError(
                        f"面板接口 {endpoint} 返回 HTTP {response.status}"
                    )
                try:
                    payload = await response.json(content_type=None)
                except Exception as exc:
                    raise MCSManagerMediaError(
                        f"面板接口 {endpoint} 返回无效 JSON ({type(exc).__name__})"
                    ) from None
        if not isinstance(payload, dict):
            raise MCSManagerMediaError(
                f"面板接口 {endpoint} 返回 {type(payload).__name__}，预期为对象"
            )
        status = payload.get("status")
        if status != 200:
            raise MCSManagerMediaError(
                f"面板接口 {endpoint} 业务状态异常 ({status!r})"
            )
        if not isinstance(payload.get("data"), dict):
            raise MCSManagerMediaError(
                f"面板接口 {endpoint} 响应缺少对象格式的 data"
            )
        return payload["data"]

    def _transfer_url(self, ticket: dict, path: str) -> str:
        address = self.daemon_url or ticket.get("addr", "")
        if not isinstance(address, str):
            raise MCSManagerMediaError("面板未返回有效的 Daemon 地址")
        if not address:
            raise MCSManagerMediaError(
                "面板未返回 Daemon 地址；请填写 AstrBot 可访问的 Daemon 地址"
            )
        if not self.daemon_url:
            remote_mappings = ticket.get("remoteMappings", [])
            if remote_mappings is None:
                remote_mappings = []
            if isinstance(remote_mappings, list):
                panel = urlparse(self.panel_url)
                panel_addr = panel.netloc
                if panel.port is None and panel.scheme in ("http", "https"):
                    panel_addr += ":80" if panel.scheme == "http" else ":443"
                panel_prefix = panel.path.rstrip("/")
                for mapping in remote_mappings:
                    if not isinstance(mapping, dict):
                        raise MCSManagerMediaError(
                            "面板返回的 remoteMappings 条目格式无效"
                        )
                    source = mapping.get("from")
                    target = mapping.get("to")
                    if not isinstance(source, dict) or not isinstance(target, dict):
                        raise MCSManagerMediaError(
                            "面板返回的 remoteMappings 条目缺少 from/to 对象"
                        )
                    source_addr = source.get("addr")
                    source_prefix = source.get("prefix")
                    target_addr = target.get("addr")
                    target_prefix = target.get("prefix")
                    if not all(
                        isinstance(value, str)
                        for value in (
                            source_addr,
                            source_prefix,
                            target_addr,
                            target_prefix,
                        )
                    ) or not source_addr or not target_addr:
                        raise MCSManagerMediaError(
                            "面板返回的 remoteMappings 地址或前缀格式无效"
                        )
                    if (
                        source_addr.casefold() == panel_addr.casefold()
                        and source_prefix.rstrip("/") == panel_prefix
                    ):
                        address = target_addr + target_prefix
                        break
            elif isinstance(remote_mappings, dict):
                # Accept the legacy string map returned by older panel versions.
                for source, target in remote_mappings.items():
                    if not isinstance(source, str) or not isinstance(target, str):
                        raise MCSManagerMediaError(
                            "面板返回的 remoteMappings 条目格式无效"
                        )
                    if address.startswith(source):
                        address = target + address[len(source):]
                        break
            else:
                raise MCSManagerMediaError("面板返回的 remoteMappings 不是数组")
        if "://" not in address:
            panel_scheme = urlparse(self.panel_url).scheme
            address = f"{panel_scheme}://{address}"
        return urljoin(address.rstrip("/") + "/", path.lstrip("/"))

    async def upload(self, media_id: str, data: bytes) -> None:
        if not data or len(data) > E33CHAT_MEDIA_MAX_FILE_BYTES:
            raise ValueError("E33Chat 图片为空或超过单文件大小限制")
        await self._check_quota(len(data))
        ticket = await self._ticket(
            "api/files/upload",
            params={"upload_dir": self.media_dir},
            method="POST",
        )
        token = quote(str(ticket.get("password", "")), safe="")
        if not token:
            raise MCSManagerMediaError("面板未返回上传凭据")
        import aiohttp

        form = aiohttp.FormData()
        form.add_field("file", data, filename=media_id, content_type="application/octet-stream")
        async with aiohttp.ClientSession(timeout=self._client_options()) as session:
            async with session.post(self._transfer_url(ticket, f"upload/{token}"), data=form) as response:
                if not 200 <= response.status < 300:
                    raise MCSManagerMediaError(
                        f"Daemon 上传接口返回 HTTP {response.status}"
                    )
                body = await response.text()
        if body.strip().lower() not in ("", "ok"):
            raise MCSManagerMediaError("Daemon 上传接口返回非 OK 响应")

    async def _check_quota(self, incoming_bytes: int) -> None:
        used_bytes = 0
        page = 0
        while True:
            result = await self._ticket(
                "api/files/list",
                params={"target": self.media_dir, "page": str(page), "page_size": "100"},
            )
            items = result.get("items")
            if not isinstance(items, list):
                raise MCSManagerMediaError("面板文件列表响应缺少 items 数组")
            used_bytes += sum(
                int(item.get("size", 0))
                for item in items
                if isinstance(item, dict) and item.get("type") == 1
            )
            if used_bytes + incoming_bytes > E33CHAT_MEDIA_QUOTA_BYTES:
                raise MCSManagerMediaError(
                    f"E33Chat 媒体目录超过总配额 ({E33CHAT_MEDIA_QUOTA_BYTES} bytes)"
                )
            total = int(result.get("total", 0))
            if (page + 1) * 100 >= total or not items:
                return
            page += 1

    async def download(self, media_id: str) -> bytes:
        import aiohttp

        target = f"{self.media_dir}/{media_id}"
        ticket = await self._ticket(
            "api/files/download", params={"file_name": target}, method="POST"
        )
        token = quote(str(ticket.get("password", "")), safe="")
        if not token:
            raise MCSManagerMediaError("面板未返回下载凭据")
        async with aiohttp.ClientSession(timeout=self._client_options()) as session:
            async with session.get(
                # The passport binds the full instance-relative path above.
                # Daemon's /download/:key/:fileName route accepts only one
                # filename segment, so pass the basename here (not the path).
                self._transfer_url(ticket, f"download/{token}/{quote(media_id, safe='')}")
            ) as response:
                if response.status == 404:
                    raise MCSManagerMediaError(
                        "Daemon 下载接口未找到目标媒体文件 (HTTP 404)"
                    )
                if not 200 <= response.status < 300:
                    raise MCSManagerMediaError(
                        f"Daemon 下载接口返回 HTTP {response.status}"
                    )
                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    if len(data) + len(chunk) > E33CHAT_MEDIA_MAX_FILE_BYTES:
                        raise MCSManagerMediaError(
                            "E33Chat 媒体文件超过单文件大小限制"
                        )
                    data.extend(chunk)
        if not data:
            raise MCSManagerMediaError("Daemon 下载接口返回空文件")
        return bytes(data)
