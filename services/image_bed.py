"""图片转存条目：把无公开 URL 的图片换成玩家可访问的 URL。

`image_upload_services` 是「添加条目」式的条目列表，条目有两类：

- `BuiltinHttpUploader`（`builtin_http` 模板）：把图片字节登记到插件内的
  HTTP 服务，返回 `{base_url}/img/<token>`。不依赖外网与第三方，要求
  玩家客户端能连到 AstrBot 所在机器；
- `ImageBedUploader`（第三方图床模板）：把图片上传到公网图床换取链接，
  只要 AstrBot 能出网、玩家能上公网即可，适合「玩家与 AstrBot 不在同一
  网络」的部署。

两类条目共享同一接口（`upload(data) -> (url, 失败原因)`），可混排在同一
列表里按顺序逐个尝试，前一个失败自动切换下一个。

第三方图床**不限定服务商名单**：图床条目里填上传接口地址 + 响应解析方式
即可接入任意图床。统一的上传协议：
- `POST <upload_url>`，multipart 表单，文件字段名为 `file`
  （catbox.moe 自带上传接口特殊兼容：自动附加 `reqtype=fileupload` 并使用
  `fileToUpload` 字段名）；
- 若条目填了 `token`，同时携带 `Authorization: Bearer <token>` 请求头
  与表单字段 `token`（imgloc / 兰空等按各自习惯读取其一）；
- 若条目配了 `form_fields`，额外字段一并作为 multipart 表单发送
  （litterbox 必填 `time=72h` 指定保留时长，不带则服务端返回 500）；
- 响应解析由条目 `response` 决定：`text` = 响应正文就是图片链接
  （catbox 等）；`json` = 优先取键名为 `url` 的字段，否则按字段顺序取
  第一个形如 `http(s)://` 的字符串（imgloc / 兰空 / sm.ms / pngurl 等）。

注意隐私与稳定性：第三方图床会把群图片上传到外部服务，请按需开启。
总开关在根级配置 `enable_image_upload`；条目自身的 `enabled` 可单独关闭。
"""

import json
import uuid
from urllib.parse import urlparse

from astrbot.api import logger

from ..core.constants import (
    DEFAULT_IMAGE_HTTP_HOST,
    DEFAULT_IMAGE_HTTP_PORT,
    DEFAULT_IMAGE_UPLOAD_TIMEOUT,
    PLUGIN_NAME,
)
from .image_host import ImageHost

# 第三方图床单次上传超时（秒）的默认值；实际取值由根级配置
# `image_upload_timeout` 决定，构造条目时注入
UPLOAD_TIMEOUT = DEFAULT_IMAGE_UPLOAD_TIMEOUT

# response 支持的可取值
VALID_RESPONSE_KINDS = ("text", "json")


def _short(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _parse_key_value_lines(raw: str) -> dict | None:
    """解析「键: 值」形式的字符串配置为 dict；非法/空返回 None。

    支持两种写法：
    - 每行一个 `名字: 值`（如 `Accept: application/json`、`time: 72h`）；
    - 整个值以 `{` 开头则按 JSON 对象解析（如 `{"X-Api-Key": "abc"}`）。
    值为空的条目会被忽略，避免发出 `Authorization: ` 这种空值键。
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(obj, dict):
            return None
        result: dict = {}
        for key, value in obj.items():
            key = str(key).strip()
            if key and str(value).strip():
                result[key] = str(value).strip()
        return result or None
    result = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key and value.strip():
            result[key] = value.strip()
    return result or None


def parse_headers(raw: str) -> dict | None:
    """把条目自定义请求头配置解析为 dict；非法/空返回 None。

    支持两种写法：
    - 每行一个 `名字: 值`（如 `Accept: application/json`）；
    - 整个值以 `{` 开头则按 JSON 对象解析（如 `{"X-Api-Key": "abc"}`）。
    值为空的条目会被忽略，避免发出 `Authorization: ` 这种空值请求头。
    """
    return _parse_key_value_lines(raw)


def parse_form_fields(raw: str) -> dict | None:
    """把条目自定义表单字段配置解析为 dict；非法/空返回 None。

    用于图床要求的额外 multipart 字段（litterbox 必填 `time=72h`，
    不带该字段服务端直接返回 500）。格式与 `headers` 一致：
    一行一个 `名字: 值`，或 JSON 对象。
    """
    return _parse_key_value_lines(raw)


def _iter_url_strings(node, _depth: int = 0):
    """按文档顺序遍历 JSON，产出 `(键名, 字符串值)`。

    深度超过 16 层截断，避免异常嵌套把调用方拖死。
    """
    if _depth > 16:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                yield str(key), value
            else:
                yield from _iter_url_strings(value, _depth + 1)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str):
                yield "", item
            else:
                yield from _iter_url_strings(item, _depth + 1)


def _try_load_json(text: str):
    """解析 JSON；兼容带前后缀垃圾的响应（如 PHP 警告后接 JSON）。

    先整体 json.loads；失败则从第一个 `{` 起逐个位置 raw_decode，
    忽略前导垃圾与尾随内容（部分图床响应前会有 `}` 或 `?>` 等输出）。
    """
    try:
        return json.loads(text)
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    idx = 0
    while True:
        i = text.find("{", idx)
        if i < 0:
            return None
        try:
            payload, _ = decoder.raw_decode(text, i)
            return payload
        except ValueError:
            idx = i + 1


def extract_json_url(text: str) -> str | None:
    """从 JSON 响应中提取图片链接。

    图床普遍把图片地址放在键名为 `url` 的字段里（sm.ms / img402 / pngurl 等），
    优先取它；否则按字段顺序取第一个形如 http(s):// 的字符串。
    必须按文档顺序遍历（不能用栈弹出）：pngurl 的响应在 `url` 之后还有
    `thumbnail_url` 与 `delete_url`，逆序遍历会误取到删除接口的地址。
    """
    payload = _try_load_json(text)
    if payload is None:
        return None
    for key, value in _iter_url_strings(payload):
        if key == "url" and value.strip().startswith(("http://", "https://")):
            return value.strip()
    for _key, value in _iter_url_strings(payload):
        candidate = value.strip()
        if candidate.startswith(("http://", "https://")):
            return candidate
    return None


class BuiltinHttpUploader:
    """内置图片 HTTP 服务条目（`builtin_http` 模板）。

    与第三方图床条目共享同一接口，但**不向外上传**：图片字节登记到插件内
    的 `ImageHost`，返回 `{base_url}/img/<token>` 由玩家客户端直接加载。
    适合玩家能直连 AstrBot 所在机器（同机或有公网地址）的部署。

    与第三方图床的差别在于需要占用本机端口，因此额外提供 `start()` /
    `stop()` 生命周期，由插件层在初始化时启动、卸载时停止；`is_builtin`
    供分组识别并批量管理生命周期。

    注意：`base_url` 是**玩家客户端访问**该服务的地址前缀，不是监听地址。
    留空（或不是 http(s) 地址）视为未启用，条目不参与上传。
    """

    is_builtin = True

    DEFAULT_NAME = "内置图片HTTP服务"

    def __init__(
        self,
        host: str = DEFAULT_IMAGE_HTTP_HOST,
        port: int = DEFAULT_IMAGE_HTTP_PORT,
        base_url: str = "",
        name: str = "",
    ) -> None:
        self.host = (host or "").strip() or DEFAULT_IMAGE_HTTP_HOST
        self.port = max(1, int(port) if str(port).strip().isdigit() else DEFAULT_IMAGE_HTTP_PORT)
        self.base_url = (base_url or "").strip().rstrip("/")
        self.name = (name or "").strip()
        self._host = ImageHost()
        self._host.base_url = self.base_url
        self._started = False

    @property
    def enabled(self) -> bool:
        """`base_url` 为合法 http(s) 前缀才算启用（监听地址不影响判定）。"""
        return self.base_url.startswith(("http://", "https://"))

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        try:
            netloc = urlparse(self.base_url).netloc
        except ValueError:
            netloc = ""
        return f"{self.DEFAULT_NAME}({netloc})" if netloc else self.DEFAULT_NAME

    async def start(self) -> None:
        """启动本机 HTTP 监听；失败时回滚 base_url，避免误报服务可用。

        回滚会把 `enabled` 一并置 False，让本条目彻底退出上传链，
        而不是每次都报「登记失败」刷日志。
        """
        if not self.enabled:
            return
        try:
            await self._host.start(self.host, self.port)
            self._started = True
        except Exception:
            self._host.base_url = ""
            self.base_url = ""
            raise

    async def stop(self) -> None:
        await self._host.stop()
        self._started = False

    async def upload(self, data: bytes) -> tuple[str | None, str]:
        """登记图片字节，返回 `(内置服务 URL, 失败原因)`。

        与其它图床条目语义一致：拿到 URL 时失败原因为空；返回 None 时
        由分组继续尝试下一个条目。
        """
        if not self.enabled or not data:
            return None, "未启用或图片数据为空"
        if not self._started:
            return None, "监听未启动"
        url = self._host.register(data)
        if url:
            return url, ""
        return None, "登记失败"


class ImageBedUploader:
    """通用图床上传条目：任意上传接口地址 + 响应解析方式。"""

    is_builtin = False

    def __init__(
        self,
        upload_url: str = "",
        token: str = "",
        response: str = "text",
        name: str = "",
        file_field: str = "file",
        headers: str = "",
        form_fields: str = "",
        timeout: int = UPLOAD_TIMEOUT,
    ) -> None:
        self.upload_url = (upload_url or "").strip()
        self.token = (token or "").strip()
        self.response = (response or "text").strip().lower()
        self.name = (name or "").strip()
        self.file_field = (file_field or "file").strip() or "file"
        self.headers = parse_headers(headers)
        self.form_fields = parse_form_fields(form_fields)
        # 上传超时（秒）：非正数视为非法，回落默认值（WebUI 可能存成字符串）
        try:
            seconds = int(float(str(timeout).strip()))
        except (TypeError, ValueError):
            seconds = UPLOAD_TIMEOUT
        self.timeout = max(1, seconds)

    @property
    def enabled(self) -> bool:
        return (
            self.upload_url.startswith(("http://", "https://"))
            and self.response in VALID_RESPONSE_KINDS
        )

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        try:
            netloc = urlparse(self.upload_url).netloc
        except ValueError:
            netloc = ""
        return netloc or self.upload_url

    async def upload(self, data: bytes) -> tuple[str | None, str]:
        """上传图片字节，返回 `(公开URL, 失败原因)`；失败时 URL 为 None。

        失败原因用于汇聚进转发跳过的排障日志；同时也会单独打一条 WARN。
        """
        if not self.enabled or not data:
            return None, "未启用或图片数据为空"
        try:
            import aiohttp  # AstrBot 运行时既有依赖，惰性导入

            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                return await self._upload(session, data), ""
        except Exception as exc:
            # 超时是最常见的一类失败，单独说清「超时多少秒」方便用户决定
            # 是调大 image_upload_timeout 还是换一个更快的图床
            reason = f"上传超时（{self.timeout} 秒）" if isinstance(
                exc, TimeoutError
            ) else str(exc)
            logger.warning(
                f"[{PLUGIN_NAME}] 图床 {self.display_name} 上传失败: {reason}"
            )
            return None, reason

    async def _upload(self, session, data: bytes) -> str:
        import aiohttp

        form = aiohttp.FormData()
        is_catbox = "catbox.moe" in self.upload_url
        # catbox 系特殊兼容（字段名 fileToUpload + reqtype）；其余图床按
        # 条目配置的 file_field 发送（绝大多数是 file，img402 是 image）
        file_field = "fileToUpload" if is_catbox else self.file_field
        form.add_field(file_field, data, filename=self._filename())
        if is_catbox:
            form.add_field("reqtype", "fileupload")
        # 额外 multipart 字段（litterbox 必填 time=72h 指定保留时长）
        for key, value in (self.form_fields or {}).items():
            form.add_field(key, value)
        headers = dict(self.headers) if self.headers else None
        if self.token:
            headers = headers or {}
            headers["Authorization"] = f"Bearer {self.token}"
            form.add_field("token", self.token)
        async with session.post(
            self.upload_url, data=form, headers=headers
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {_short(text)}")
        if self.response == "json":
            url = extract_json_url(text)
            if not url:
                raise RuntimeError(f"JSON 响应中未找到图片链接: {_short(text)}")
            return url
        url = text.strip()
        if not url.startswith("http"):
            raise RuntimeError(f"响应中未返回图片链接: {_short(text)}")
        return url

    @staticmethod
    def _filename() -> str:
        return f"astrbot_{uuid.uuid4().hex}.png"


class ImageBedUploaderGroup:
    """多个图片转存条目的集合：按配置顺序逐个尝试，任一成功即返回 URL。

    与 mc_servers 的「添加条目」样式对应：根级配置 `image_upload_services`
    是一个条目列表，每个条目是 `BuiltinHttpUploader` 或 `ImageBedUploader`；
    总开关在插件层（`enable_image_upload`），条目自身的 `enabled` 可单独关闭。
    """

    def __init__(self) -> None:
        self.uploaders: list[ImageBedUploader | BuiltinHttpUploader] = []

    @property
    def enabled(self) -> bool:
        return any(uploader.enabled for uploader in self.uploaders)

    @property
    def service_names(self) -> str:
        names = [uploader.display_name for uploader in self.uploaders if uploader.enabled]
        return ", ".join(names) or "空"

    @property
    def status_text(self) -> str:
        """排障日志用的一句话状态：内置服务 / 第三方图床 各自是否启用与名称。

        转发的图片拿不到可访问 URL 时，日志需要一眼看出「兜底到底开了没」，
        因此把两类条目分开列（同名条目混在一起看不出是哪类出了问题）。
        """

        def _fmt(prefix: str, names: list[str]) -> str:
            joined = ", ".join(names)
            return f"{prefix}={'开' if names else '关'}({joined or '空'})"

        builtin = [
            u.display_name
            for u in self.uploaders
            if getattr(u, "is_builtin", False) and u.enabled
        ]
        beds = [
            u.display_name
            for u in self.uploaders
            if not getattr(u, "is_builtin", False) and u.enabled
        ]
        return "；".join([_fmt("内置服务", builtin), _fmt("图床", beds)])

    def builtin_uploaders(self) -> list[BuiltinHttpUploader]:
        """取出所有内置 HTTP 条目（需要管理监听生命周期）。"""
        return [u for u in self.uploaders if getattr(u, "is_builtin", False)]

    async def start_builtin(self) -> int:
        """启动全部内置 HTTP 条目的监听，返回成功启动的条目数。

        单条失败只记日志，不影响其它条目与插件整体初始化；失败条目会回滚
        `base_url`（`enabled` 变 False），从而不再参与上传。
        """
        started = 0
        for uploader in self.builtin_uploaders():
            try:
                await uploader.start()
                started += 1
            except Exception as exc:
                logger.error(
                    f"[{PLUGIN_NAME}] 内置图片 HTTP 服务 {uploader.display_name} "
                    f"监听 {uploader.host}:{uploader.port} 启动失败: {exc}"
                )
        return started

    async def stop_builtin(self) -> None:
        """停止全部内置 HTTP 条目（幂等，可重复调用）。"""
        for uploader in self.builtin_uploaders():
            await uploader.stop()

    async def upload(self, data: bytes) -> tuple[str | None, str]:
        """按条目顺序逐个上传，返回 `(URL, 失败原因)`。

        URL 为 None 时，失败原因按「条目名: 具体原因」汇总，供转发跳过警告展示。
        """
        failures: list[str] = []
        for uploader in self.uploaders:
            if not uploader.enabled:
                continue
            url, error = await uploader.upload(data)
            if url:
                return url, ""
            failures.append(f"{uploader.display_name}: {error}")
        return None, "；".join(failures) or "无可用图床条目"