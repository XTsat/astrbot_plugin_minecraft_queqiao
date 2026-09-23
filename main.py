"""astrbot_plugin_minecraft_queqiao — AstrBot 插件

通过鹊桥模组连接 Minecraft 服务器，实现群服消息互通、服务器管理与 AI 聊天。
配置结构参照 astrbot_plugin_minecraft_adapter，连接层改用鹊桥 V2 协议。
"""

import asyncio
import contextlib
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.star.filter.command import GreedyStr

from .core.constants import (
    DEFAULT_IMAGE_HTTP_HOST,
    DEFAULT_IMAGE_HTTP_PORT,
    DEFAULT_IMAGE_UPLOAD_TIMEOUT,
    PLUGIN_DATA_DIR,
    PLUGIN_NAME,
    prefix_matches,
    strip_prefix,
)
from .core.models import QueQiaoEvent
from .core.models_config import ServerConfig, _to_bool, _to_int, _to_str
from .core.queqiao_client import QueQiaoTimeout
from .core.server_manager import ServerManager
from .handlers.commands import CommandHandler, parse_direct_address
from .services.binding import BindingService
from .services.image_bed import (
    BuiltinHttpUploader,
    ImageBedUploader,
    ImageBedUploaderGroup,
)
from .services.message_bridge import (
    MessageBridge,
    build_chatimage_code,
    resolve_image_url,
)
from .services.metrics import MetricsCollector
from .services.monitor import MonitorCollector
from .services.panel_prefs import PanelPrefsStore
from .services.renderer import InfoRenderer
from .services.terminal_log import TerminalLogStore
from .services.web_api import WebApiController

DEFAULT_TIMEOUT = 30

# 图床条目模板 key（AstrBot 会在每个条目上写入 __template_key 持久化）
TEMPLATE_KEY_BUILTIN_HTTP = "builtin_http"


@register(
    PLUGIN_NAME,
    "XTsat",
    "通过鹊桥模组连接 Minecraft 服务器，实现消息互通、服务器管理与 AI 聊天",
    "v0.3.4",
    "https://github.com/XTsat/astrbot_plugin_minecraft_queqiao",
)
class MinecraftQueQiaoPlugin(Star):
    """Minecraft 鹊桥互通主插件类。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config

        data_dir = Path(StarTools.get_data_dir(PLUGIN_DATA_DIR))
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir = data_dir

        self.server_manager = ServerManager()
        self.binding_service = BindingService(data_dir)
        self.message_bridge = MessageBridge(context)
        self.renderer = InfoRenderer()
        self.image_bed = ImageBedUploaderGroup()
        self.metrics = MetricsCollector()
        self.terminal_logs = TerminalLogStore(data_dir)
        self.monitor = MonitorCollector(data_dir, self.server_manager)
        self.panel_prefs = PanelPrefsStore(data_dir)
        self.command_handler = CommandHandler(
            self.server_manager, self.binding_service, self.renderer
        )
        self.command_handler.attach_bridge(self.message_bridge)
        self.command_handler.attach_monitor(self.monitor)

        self._configs: dict[str, ServerConfig] = {}
        self.web_api = WebApiController(
            context,
            self.server_manager,
            self.binding_service,
            self.image_bed,
            self.metrics,
            self._configs,
            self.terminal_logs,
            self.monitor,
            self.panel_prefs,
        )
        self.web_api.register_routes()
        self._init_task: asyncio.Task | None = None

    # ---- 生命周期 ----

    async def initialize(self) -> None:
        """加载配置并启动所有服务器连接（由 AstrBot 在加载插件后调用）。"""
        if not self.config.get("enabled", True):
            logger.info(f"[{PLUGIN_NAME}] 插件已禁用")
            return

        self.binding_service.load()
        self.terminal_logs.load()
        logger.info(
            f"[{PLUGIN_NAME}] 终端日志目录: {self._data_dir / 'terminal_logs'}"
        )

        raw_servers = self.config.get("mc_servers", []) or []
        if not isinstance(raw_servers, list) or not raw_servers:
            logger.warning(f"[{PLUGIN_NAME}] 未配置任何服务器")
            return

        any_text2image = False
        for entry in raw_servers:
            if not isinstance(entry, dict) or not entry.get("enabled", True):
                continue

            config = ServerConfig.from_dict(entry)
            if not config.server_name:
                logger.warning(f"[{PLUGIN_NAME}] 跳过 server_name 为空的服务器配置")
                continue
            if config.server_name in self._configs:
                logger.warning(
                    f"[{PLUGIN_NAME}] server_name 重复，后者被忽略: {config.server_name}"
                )
                await self._notify_duplicate_server(config)
                continue

            self._configs[config.server_name] = config
            self.message_bridge.register_server(config)
            self.server_manager.add(
                config,
                on_event=self._make_event_handler(config.server_name),
                on_connect=self._make_connect_handler(config.server_name),
                on_disconnect=self._make_disconnect_handler(config.server_name),
            )

            if config.custom_cmd_list:
                self.command_handler.register_custom_commands(
                    config.server_name, config.custom_cmd_list
                )

            any_text2image = any_text2image or config.text2image
            logger.info(
                f"[{PLUGIN_NAME}] 已配置服务器: {config.server_name} "
                f"({'反向' if config.is_reverse else '正向'})"
            )
            self._warn_prefix_conflict(config)

        self.renderer.enabled = any_text2image

        if not self._configs:
            logger.warning(f"[{PLUGIN_NAME}] 没有可用的服务器配置")
            return

        await self._setup_image_services()
        await self.server_manager.start_all()
        # 性能监控（TPS/延迟）采集任务：仅对启用了监控的服务器启动
        self.monitor.start(self._configs)
        logger.info(
            f"[{PLUGIN_NAME}] 插件已初始化，共 {len(self._configs)} 台服务器"
        )

    async def terminate(self) -> None:
        """插件卸载时清理所有连接。"""
        logger.info(f"[{PLUGIN_NAME}] 正在关闭...")

        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._init_task

        await self.image_bed.stop_builtin()
        await self.server_manager.stop_all()
        await self.monitor.stop()
        logger.info(f"[{PLUGIN_NAME}] 已关闭")

    async def _setup_image_services(self) -> None:
        """按根级配置构建图片转存条目并启动内置 HTTP 监听。

        `enable_image_upload` 是总开关；`image_upload_services` 是与
        mc_servers 同款的条目列表，内置图片 HTTP 服务与其它第三方图床
        混排在同一列表里，按列表顺序逐个尝试（内置条目通常放前面）。
        内置条目需要占用本机端口，构建后统一调用 `start_builtin()` 启动。
        """
        self.image_bed.uploaders = []
        if not _to_bool(self.config.get("enable_image_upload"), False):
            return

        entries = self.config.get("image_upload_services") or []
        if isinstance(entries, dict):  # 防御：误存成单项对象
            entries = [entries]
        # 上传超时是全局根级配置，逐个注入第三方图床条目；非正数回落默认值
        upload_timeout = max(
            1,
            _to_int(
                self.config.get("image_upload_timeout"),
                DEFAULT_IMAGE_UPLOAD_TIMEOUT,
            ),
        )
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not _to_bool(entry.get("enabled"), True):
                continue

            if self._is_builtin_entry(entry):
                uploader = BuiltinHttpUploader(
                    host=_to_str(entry.get("host"), DEFAULT_IMAGE_HTTP_HOST),
                    port=_to_int(entry.get("port"), DEFAULT_IMAGE_HTTP_PORT),
                    base_url=_to_str(entry.get("base_url"), ""),
                    name=_to_str(entry.get("name"), ""),
                )
                if not uploader.enabled:
                    logger.warning(
                        f"[{PLUGIN_NAME}] 内置图片 HTTP 服务条目 "
                        f"{uploader.display_name}: base_url 为空或不是 "
                        "http(s) 地址，服务不会启动。请填写玩家客户端可访问的"
                        "地址前缀，如 http://公网IP:8765（不能用 127.0.0.1，"
                        "除非玩家与服务同机）"
                    )
                    continue
                self.image_bed.uploaders.append(uploader)
                continue

            uploader = ImageBedUploader(
                upload_url=_to_str(entry.get("upload_url"), ""),
                token=_to_str(entry.get("token"), ""),
                response=_to_str(entry.get("response"), "text"),
                name=_to_str(entry.get("name"), ""),
                file_field=_to_str(entry.get("file_field"), "file"),
                headers=_to_str(entry.get("headers"), ""),
                form_fields=_to_str(entry.get("form_fields"), ""),
                timeout=upload_timeout,
            )
            if not uploader.enabled:
                logger.warning(
                    f"[{PLUGIN_NAME}] 图床条目 {uploader.display_name or '未命名'}: "
                    f"upload_url 需为 http(s):// 开头且 response 为 text/json，"
                    "已忽略"
                )
                continue
            self.image_bed.uploaders.append(uploader)

        await self.image_bed.start_builtin()
        if self.image_bed.enabled:
            logger.info(
                f"[{PLUGIN_NAME}] 图片转存服务已启用: {self.image_bed.service_names}"
            )

    @staticmethod
    def _is_builtin_entry(entry: dict) -> bool:
        """判断条目是否为内置图片 HTTP 服务（builtin_http 模板）。

        以 `__template_key` 为准（AstrBot 保存 template_list 时会写入）；
        缺失时按字段特征兜底：带 `base_url` 且无 `upload_url` 视为内置条目。
        """
        key = _to_str(entry.get("__template_key"), "").strip().lower()
        if key:
            return key == TEMPLATE_KEY_BUILTIN_HTTP
        return (
            bool(_to_str(entry.get("base_url"), "").strip())
            and not _to_str(entry.get("upload_url"), "").strip()
        )

    @staticmethod
    def _warn_prefix_conflict(config: ServerConfig) -> None:
        """两个前缀互相包含时告警，提示用户在配置中改开。"""
        if config.prefixes_conflict:
            logger.warning(
                f"[{PLUGIN_NAME}][{config.server_name}] 互通前缀 "
                f"`{config.auto_forward_prefix}` 与 AI 前缀 "
                f"`{config.ai_chat_prefix}` 相互包含，消息归属可能产生歧义，"
                f"建议改为互不相同的两个前缀"
            )

    async def _notify_duplicate_server(self, config: ServerConfig) -> None:
        """server_name 重复被忽略时，把告警发到该配置的目标会话。

        仅日志告警容易被忽略；把「配置被忽略」直接发进目标会话，
        让用户知道这台服务器没有启用以及原因。发送失败只告警不中断。
        """
        if not config.target_sessions:
            return
        try:
            from astrbot.api.event import MessageChain
            from astrbot.api.message_components import Plain

            chain = MessageChain(
                chain=[
                    Plain(
                        text=(
                            f"⚠️ 配置告警：server_name「{config.server_name}」"
                            "与已有服务器重复，本服务器的配置已被忽略、未启用。"
                            "请修改本服务器的 server_name（需与鹊桥 config.yml 的 "
                            "server_name 一致），否则本服务器不会启用。"
                        )
                    )
                ]
            )
            for umo in config.target_sessions:
                try:
                    await self.context.send_message(umo, chain)
                except Exception:
                    logger.warning(
                        f"[{PLUGIN_NAME}] 向 {umo} 发送重复配置告警失败",
                        exc_info=True,
                    )
        except Exception:
            logger.warning(f"[{PLUGIN_NAME}] 发送重复配置告警失败", exc_info=True)

    # ---- 事件回调构造 ----

    def _make_event_handler(self, server_name: str):
        async def _handler(event: QueQiaoEvent) -> None:
            await self._on_queqiao_event(server_name, event)

        return _handler

    def _make_connect_handler(self, server_name: str):
        async def _handler() -> None:
            logger.info(f"[{PLUGIN_NAME}][{server_name}] 连接就绪")

        return _handler

    def _make_disconnect_handler(self, server_name: str):
        async def _handler(reason: str) -> None:
            logger.warning(f"[{PLUGIN_NAME}][{server_name}] 连接断开: {reason}")

        return _handler

    # ---- MC 事件处理 ----

    async def _on_queqiao_event(self, server_name: str, event: QueQiaoEvent) -> None:
        """处理来自鹊桥的事件：转发到会话，并识别 AI 聊天触发。"""
        config = self._configs.get(server_name)
        if config is None:
            return

        # 记录事件指标与持久化终端日志（网页未打开期间同样记录）；
        # 同时写入 AstrBot 主日志，便于在控制台直接观察互通动态
        if event.is_chat:
            self.metrics.record_event(
                "chat",
                server_name,
                f"<{event.player_name}> {event.message}",
                {"player": event.player_name, "message": event.message},
            )
            self.terminal_logs.append(
                server_name, "chat", f"<{event.player_name}> {event.message}"
            )
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 游戏内聊天: "
                f"<{event.player_name}> {event.message}"
            )
        elif event.is_join:
            self.metrics.record_event(
                "join",
                server_name,
                f"玩家 {event.player_name} 加入了游戏",
                {"player": event.player_name},
            )
            self.terminal_logs.append(
                server_name, "join", f"玩家 {event.player_name} 加入了游戏"
            )
            logger.info(f"[{PLUGIN_NAME}][{server_name}] 玩家 {event.player_name} 加入了游戏")
        elif event.is_quit:
            self.metrics.record_event(
                "quit",
                server_name,
                f"玩家 {event.player_name} 离开了游戏",
                {"player": event.player_name},
            )
            self.terminal_logs.append(
                server_name, "quit", f"玩家 {event.player_name} 离开了游戏"
            )
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 玩家 {event.player_name} 离开了游戏"
            )
        elif event.is_death:
            death_text = event.death.as_text() or "死亡"
            self.metrics.record_event(
                "death",
                server_name,
                f"玩家 {event.player_name} {death_text}",
                {"player": event.player_name, "death": death_text},
            )
            self.terminal_logs.append(
                server_name, "death", f"玩家 {event.player_name} {death_text}"
            )
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 玩家 {event.player_name} {death_text}"
            )
        elif event.is_achievement:
            ach_text = event.achievement.as_text() or "达成成就"
            self.metrics.record_event(
                "achievement",
                server_name,
                f"玩家 {event.player_name} 达成了成就 {ach_text}",
                {"player": event.player_name, "achievement": ach_text},
            )
            self.terminal_logs.append(
                server_name,
                "achievement",
                f"玩家 {event.player_name} 达成了成就 {ach_text}",
            )
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 玩家 {event.player_name} "
                f"达成了成就 {ach_text}"
            )
        elif event.is_command:
            self.metrics.record_event(
                "command",
                server_name,
                f"<{event.player_name}> 执行指令: {event.command}",
                {"player": event.player_name, "command": event.command},
            )
            self.terminal_logs.append(
                server_name, "command", f"<{event.player_name}> 执行指令: {event.command}"
            )
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 玩家 {event.player_name} "
                f"执行指令: {event.command}"
            )

        # AI 与互通互斥：命中 AI 前缀即交给 LLM，不再转发到会话
        question = self._resolve_ai_question(config, event)
        if question is not None:
            await self._handle_ai_chat(server_name, config, event, question)
            return

        if await self.message_bridge.forward_event(server_name, config, event):
            self.metrics.record_relay_to_ast(server_name)

    @staticmethod
    def _match_ai_prefix(config: ServerConfig, event: QueQiaoEvent) -> bool:
        """判断游戏内聊天是否触发 AI。

        AI 前缀为空时**不**触发：否则所有聊天都会被投给 LLM，
        既产生噪声也消耗额度。需全部触发请显式设置较短前缀。

        采用词边界感知匹配，避免短前缀误伤同词头发言（如 `ai` 误匹配 `aim`）。
        """
        return prefix_matches(config.ai_chat_prefix, event.message)

    @staticmethod
    def _strip_ai_prefix(config: ServerConfig, text: str) -> str:
        return strip_prefix(config.ai_chat_prefix, text)

    @staticmethod
    def _resolve_ai_question(config: ServerConfig, event: QueQiaoEvent) -> str | None:
        """解析 AI 提问内容；不构成 AI 请求时返回 None。

        仅由**游戏内聊天**触发（`PlayerChatEvent` 命中 `ai_chat_prefix`）。
        """
        if not config.enable_ai_chat or not event.is_chat:
            return None

        if not prefix_matches(config.ai_chat_prefix, event.message):
            return None

        question = strip_prefix(config.ai_chat_prefix, event.message)
        return question or None

    async def _handle_ai_chat(
        self, server_name: str, config: ServerConfig, event: QueQiaoEvent, question: str
    ) -> None:
        """把游戏内 AI 提问交给 LLM，并把回复私聊回玩家。

        使用 AstrBot 的 LLM 调用链：优先走会话默认人格，失败则提示玩家。
        """
        player = event.player
        logger.info(
            f"[{PLUGIN_NAME}][{server_name}] AI 提问来自 {player.display_name}: {question}"
        )

        reply = await self._ask_llm(event, question)
        self.metrics.record_ai_chat(
            server_name, player.display_name, question, bool(reply)
        )
        if not reply:
            return

        instance = self.server_manager.get(server_name)
        if instance is None:
            return

        # 私聊回复：多人同时提问不会互相串台；uuid 缺失时退化为昵称
        try:
            sent = await instance.client.send_private_message(
                reply, uuid_str=player.uuid, nickname=player.nickname
            )
        except QueQiaoTimeout:
            # 超时 = 结果未知：WS 发送已成功，私聊大概率已送达游戏内。
            # 此时若再广播一遍，玩家会收到两份回复（实测发生过），因此不重发
            logger.warning(
                f"[{PLUGIN_NAME}][{server_name}] 私聊回复响应超时"
                "（消息可能已送达游戏内，不重复发送）"
            )
            return
        if not sent:
            # 仅「确定失败」（未连接 / 鹊桥明确报错）才改用广播
            logger.warning(
                f"[{PLUGIN_NAME}][{server_name}] 私聊回复失败，改用广播"
            )
            await instance.client.broadcast(
                f"@{player.display_name} {reply}", config.broadcast_color
            )

    async def _ask_llm(self, event: QueQiaoEvent, question: str) -> str:
        """调用 AstrBot LLM，返回纯文本回复；不可用时返回空串。

        使用 `get_using_provider` + `text_chat`，与 AstrBot 4.x 的 provider 接口一致。
        """
        try:
            provider = self.context.get_using_provider(umo=None)
            if provider is None:
                logger.warning(f"[{PLUGIN_NAME}] 未找到可用的 LLM 提供商")
                return ""

            response = await provider.text_chat(prompt=question)
            return (getattr(response, "completion_text", "") or "").strip()
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}] LLM 调用失败: {exc}")
            return ""

    # ---- 命令组 ----

    @filter.command_group("mc")
    def mc_group(self):
        """Minecraft 服务器管理命令"""
        pass

    @mc_group.command("help")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        yield event.plain_result(self.command_handler.help_text())

    @mc_group.command("status")
    async def cmd_status(self, event: AstrMessageEvent, target: str = ""):
        """查看服务器状态（可指定数字编号或 host:port 地址直连查询）"""
        if target and not target.isdigit():
            addr = parse_direct_address(target)
            if addr is None:
                yield event.plain_result(
                    "❌ 目标格式无效：应为数字编号（如 1）或服务器地址"
                    "（如 127.0.0.1:25565）"
                )
                return
            yield event.plain_result(
                await self.command_handler.handle_direct_status(*addr)
            )
            return
        server, hint = self.command_handler._resolve_target(event, target)
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(await self.command_handler.handle_status(event, server.server_name))

    @mc_group.command("list")
    async def cmd_list(self, event: AstrMessageEvent, target: str = ""):
        """查看在线玩家列表（可指定数字编号或 host:port 地址直连查询）"""
        if target and not target.isdigit():
            addr = parse_direct_address(target)
            if addr is None:
                yield event.plain_result(
                    "❌ 目标格式无效：应为数字编号（如 1）或服务器地址"
                    "（如 127.0.0.1:25565）"
                )
                return
            yield event.plain_result(
                await self.command_handler.handle_direct_list(*addr)
            )
            return
        server, hint = self.command_handler._resolve_target(event, target)
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(await self.command_handler.handle_list(event, server.server_name))

    @mc_group.command("player")
    async def cmd_player(self, event: AstrMessageEvent, player_id=GreedyStr):
        """查看玩家信息

        可在最前面加数字编号指定目标服务器（多服），仅一台时可省略。
        """
        target, rest = self.command_handler._split_optional_target(str(player_id))
        if target is not None:
            server, hint = self.command_handler._resolve_target(event, target)
        else:
            server, hint = self.command_handler._select_target(event)
        if not rest:
            yield event.plain_result("❌ 请提供玩家ID")
            return
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(
            await self.command_handler.handle_player(event, server.server_name, rest)
        )

    @mc_group.command("cmd")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_execute(self, event: AstrMessageEvent, command=GreedyStr):
        """远程执行服务器指令

        可在最前面加数字编号指定目标服务器（多服），仅一台时可省略。
        """
        target, rest = self.command_handler._split_optional_target(str(command))
        if target is not None:
            server, hint = self.command_handler._resolve_target(event, target)
        else:
            server, hint = self.command_handler._select_target(event)
        if not rest:
            yield event.plain_result("❌ 请提供要执行的指令")
            return
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(
            await self.command_handler.handle_cmd(event, server.server_name, rest)
        )

    @mc_group.command("say")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_say(self, event: AstrMessageEvent, content=GreedyStr):
        """向游戏内广播消息

        可在最前面加数字编号指定目标服务器（多服），仅一台时可省略。
        """
        target, rest = self.command_handler._split_optional_target(str(content))
        if target is not None:
            server, hint = self.command_handler._resolve_target(event, target)
        else:
            server, hint = self.command_handler._select_target(event)
        if not rest:
            yield event.plain_result("❌ 请提供要广播的内容")
            return
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(
            await self.command_handler.handle_say(event, server.server_name, rest)
        )

    @mc_group.command("bind")
    async def cmd_bind(self, event: AstrMessageEvent, game_id: str):
        """绑定游戏ID"""
        yield event.plain_result(await self.command_handler.handle_bind(event, game_id))

    @mc_group.command("unbind")
    async def cmd_unbind(self, event: AstrMessageEvent):
        """解除绑定"""
        yield event.plain_result(await self.command_handler.handle_unbind(event))

    @mc_group.command("servers")
    async def cmd_servers(self, event: AstrMessageEvent):
        """查看服务器列表与连接状态"""
        yield event.plain_result(await self.command_handler.handle_servers(event))

    # ---- 消息监听：外部 → MC 转发与自定义指令 ----

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理外部消息：自定义指令匹配与转发到 MC（含图片）。"""
        if event.is_at_or_wake_command:
            return

        umo = event.unified_msg_origin
        text = event.get_message_str().strip()

        # 图片不参与文本匹配，但可随消息一起转发到 MC
        images = self._extract_images(event)
        if not text and not images:
            return

        # 自定义指令：仅在会话绑定的服务器上匹配（按文本匹配，图片不参与）
        if text:
            for server_name, config in self.message_bridge.servers_for_session(umo):
                actual = self.command_handler.match_custom_command(server_name, text)
                if actual:
                    instance = self.server_manager.get(server_name)
                    if instance is None:
                        continue
                    output = await instance.execute_command(actual)
                    reply = (
                        f"✅ 已执行：{actual}\n{output}".rstrip()
                        if output is not None
                        else f"❌ 执行失败：{actual}"
                    )
                    yield event.plain_result(reply)
                    event.stop_event()
                    return

        # 转发到 MC
        if await self._relay_to_minecraft(event, umo, text, images):
            event.stop_event()

    @staticmethod
    def _extract_images(event: AstrMessageEvent) -> list:
        """取出消息链中的图片组件（供转发到 MC 使用）。

        只关心消息内容里实际携带的图片段；纯文本消息返回空列表。
        """
        try:
            from astrbot.api.message_components import Image
        except Exception:
            return []
        components = event.get_messages() or []
        return [comp for comp in components if isinstance(comp, Image)]

    @staticmethod
    def _describe_image(comp: object | None) -> str:
        """概要描述图片组件字段，用于「拿不到 URL」时的排障日志。"""

        def brief(value: object) -> str:
            if not value:
                return ""
            text = str(value)
            if text.startswith("base64://"):
                return "base64://<...>"
            return text if len(text) <= 48 else text[:48] + "..."

        url = brief(getattr(comp, "url", ""))
        file_ = brief(getattr(comp, "file", ""))
        path = brief(getattr(comp, "path", ""))
        return f"url={url!r} file={file_!r} path={path!r}"

    async def _relay_to_minecraft(
        self, event: AstrMessageEvent, umo: str, text: str, images: list | None = None
    ) -> bool:
        """把外部会话消息按前缀规则转发到绑定的 MC 服务器。

        `images` 为消息链中的图片组件列表；仅当服务器开启了
        `forward_image_to_mc` 且能解析出玩家客户端可访问的 URL 时，
        才以 ChatImage 代码形式追加到广播内容。
        """
        targets = self.message_bridge.servers_for_session(umo)
        if not targets:
            logger.debug(f"[{PLUGIN_NAME}] 会话 {umo} 未绑定任何服务器，跳过转发")
            return False

        relayed = False
        sender = event.get_sender_name() or event.get_sender_id()
        platform = event.get_platform_name() or "未知"

        for server_name, config in targets:
            if not self.message_bridge.should_relay(config, text):
                continue

            instance = self.server_manager.get(server_name)
            if instance is None or not instance.connected:
                logger.warning(
                    f"[{PLUGIN_NAME}][{server_name}] 服务器未连接，"
                    f"跳过该消息的转发: {text[:60]}"
                )
                continue

            # 文本部分（供回声抑制与格式占位符使用）
            content = self.message_bridge.strip_relay_prefix(config, text)

            # 图片 → ChatImage 代码（[[CICode,url=...,name=...]]）
            image_codes = []
            skipped_images = 0
            skipped_sample: object | None = None
            skip_reason: str | None = None
            if images and config.forward_image_to_mc:
                for comp in images:
                    url, reason = await resolve_image_url(
                        comp, self.image_bed
                    )
                    if url:
                        image_codes.append(
                            build_chatimage_code(url, config.chatimage_name)
                        )
                    else:
                        skipped_images += 1
                        if skipped_sample is None:
                            skipped_sample = comp
                            skip_reason = reason
            elif images:
                # 默认关闭：多数服务器未装 ChatImage，开箱不应外溢；
                # 但用户排查时这里必须有可见日志，否则图片静默丢失无从查起
                logger.info(
                    f"[{PLUGIN_NAME}][{server_name}] 消息含 {len(images)} 张图片，"
                    "但未开启 forward_image_to_mc，图片未转发"
                )

            if not content and not image_codes:
                if skipped_images:
                    logger.warning(
                        f"[{PLUGIN_NAME}][{server_name}] 消息中的图片均无可访问"
                        f"的公开 URL（{skipped_images} 张），已跳过。"
                        f"图片组件: {self._describe_image(skipped_sample)}；"
                        f"兜底状态: {self.image_bed.status_text}；"
                        f"原因: {skip_reason or '未知'}"
                    )
                continue

            message = content
            if image_codes:
                message = (message + " " if message else "") + " ".join(image_codes)

            formatted = config.broadcast_format.format(
                # {platform} 先经平台名称映射（platform_names，如 aiocqhttp→QQ）；
                # 未配置或未命中时原样保留
                platform=config.platform_display_name(platform),
                sender=sender,
                message=message,
                # {display_name} 取显示名称（留空用默认值，默认 MC）；{server_name} 始终为原始 ID
                display_name=config.server_label,
                server_name=server_name,
            )
            sent = await instance.client.broadcast(formatted, config.broadcast_color)
            if not sent:
                logger.warning(
                    f"[{PLUGIN_NAME}][{server_name}] 群消息转发到游戏失败: "
                    f"[{config.platform_display_name(platform)}]{sender}: {message[:60]}"
                )
                continue
            # 记录以防止该消息从游戏回传时形成回声。
            # 回声抑制只针对可被玩家复述的文本部分；图片代码由服务端广播，
            # 不会以玩家聊天事件回传，因此以纯文本 content 作为抑制键
            self.message_bridge.mark_forwarded(server_name, content)
            self.metrics.record_relay_to_mc(server_name)
            relayed = True
            # QQ → 游戏方向的转发同时写入互通终端，与游戏事件同流展示
            self.terminal_logs.append(
                server_name,
                "qq_chat",
                f"[{config.platform_display_name(platform)}]{sender}: {message}",
            )
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 群消息 → 游戏: "
                f"[{config.platform_display_name(platform)}]{sender}: {message}"
            )
            if image_codes:
                self.metrics.record_image_relayed(len(image_codes))
                extra = (
                    f"，另 {skipped_images} 张无公开 URL 已跳过"
                    if skipped_images
                    else ""
                )
                logger.info(
                    f"[{PLUGIN_NAME}][{server_name}] 已转发 {len(image_codes)} "
                    f"张图片到游戏内{extra}"
                )
            # 转发成功后给原消息回执（emoji 贴表情 / text 文本回复）
            await self.message_bridge.mark_relayed(event, config)

        return relayed
