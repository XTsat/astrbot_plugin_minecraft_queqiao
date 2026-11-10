"""MCSManager-backed E33Chat media storage."""

from __future__ import annotations

from urllib.parse import quote, urljoin, urlparse

from core.constants import E33CHAT_MEDIA_MAX_FILE_BYTES, E33CHAT_MEDIA_QUOTA_BYTES


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
        self.media_dir = "/" + media_dir.strip().strip("/")
        self.daemon_url = daemon_url.strip().rstrip("/")
        self.timeout_seconds = timeout

    def _client_options(self):
        import aiohttp

        return aiohttp.ClientTimeout(total=self.timeout_seconds)

    def _validate(self) -> None:
        if not all((self.panel_url, self.api_key, self.daemon_id, self.instance_uuid, self.media_dir.strip("/"))):
            raise ValueError("MCSManager 面板地址、API Key、Daemon ID、实例 UUID 和媒体目录均须填写")
        if urlparse(self.panel_url).scheme not in ("http", "https"):
            raise ValueError("MCSManager 面板地址必须以 http:// 或 https:// 开头")

    async def _ticket(self, endpoint: str, *, params: dict[str, str]) -> dict:
        import aiohttp

        self._validate()
        query = {
            "daemonId": self.daemon_id,
            "uuid": self.instance_uuid,
            "apikey": self.api_key,
            **params,
        }
        async with aiohttp.ClientSession(timeout=self._client_options()) as session:
            async with session.get(
                urljoin(self.panel_url, endpoint),
                params=query,
                headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json; charset=utf-8"},
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        if payload.get("status") != 200 or not isinstance(payload.get("data"), dict):
            raise RuntimeError(f"MCSManager API 返回错误状态: {payload.get('status')}")
        return payload["data"]

    def _transfer_url(self, ticket: dict, path: str) -> str:
        address = self.daemon_url or ticket.get("addr", "")
        if not address:
            raise RuntimeError("MCSManager 未返回 Daemon 地址，请配置 Daemon 地址覆盖")
        if "://" not in address:
            panel_scheme = urlparse(self.panel_url).scheme
            address = f"{panel_scheme}://{address}"
        for source, target in (ticket.get("remoteMappings") or {}).items():
            if address.startswith(source):
                address = target + address[len(source):]
                break
        return urljoin(address.rstrip("/") + "/", path)

    async def upload(self, media_id: str, data: bytes) -> None:
        if not data or len(data) > E33CHAT_MEDIA_MAX_FILE_BYTES:
            raise ValueError("E33Chat 图片为空或超过单文件大小限制")
        await self._check_quota(len(data))
        ticket = await self._ticket(
            "api/files/upload",
            params={"upload_dir": self.media_dir},
        )
        token = quote(str(ticket.get("password", "")), safe="")
        if not token:
            raise RuntimeError("MCSManager 未返回上传凭据")
        import aiohttp

        form = aiohttp.FormData()
        form.add_field("file", data, filename=media_id, content_type="application/octet-stream")
        async with aiohttp.ClientSession(timeout=self._client_options()) as session:
            async with session.post(self._transfer_url(ticket, f"upload/{token}"), data=form) as response:
                response.raise_for_status()
                body = await response.text()
        if body.strip().lower() not in ("", "ok"):
            raise RuntimeError(f"MCSManager Daemon 上传失败: {body[:200]}")

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
                raise RuntimeError("MCSManager 文件列表响应格式无效")
            used_bytes += sum(
                int(item.get("size", 0))
                for item in items
                if isinstance(item, dict) and item.get("type") == 1
            )
            if used_bytes + incoming_bytes > E33CHAT_MEDIA_QUOTA_BYTES:
                raise ValueError(
                    f"E33Chat 媒体目录超过总配额 ({E33CHAT_MEDIA_QUOTA_BYTES} bytes)"
                )
            total = int(result.get("total", 0))
            if (page + 1) * 100 >= total or not items:
                return
            page += 1

    async def download(self, media_id: str) -> bytes | None:
        import aiohttp

        target = f"{self.media_dir}/{media_id}"
        ticket = await self._ticket(
            "api/files/download", params={"file_name": target}
        )
        token = quote(str(ticket.get("password", "")), safe="")
        if not token:
            raise RuntimeError("MCSManager 未返回下载凭据")
        async with aiohttp.ClientSession(timeout=self._client_options()) as session:
            async with session.get(
                self._transfer_url(ticket, f"download/{token}/{quote(target.lstrip('/'), safe='/')}")
            ) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                data = await response.content.read(E33CHAT_MEDIA_MAX_FILE_BYTES + 1)
        if not data or len(data) > E33CHAT_MEDIA_MAX_FILE_BYTES:
            return None
        return data
