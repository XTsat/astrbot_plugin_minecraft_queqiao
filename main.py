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

from .core.constants import PLUGIN_DATA_DIR, PLUGIN_NAME, prefix_matches, strip_prefix
from .core.models import QueQiaoEvent
from .core.models_config import ServerConfig
from .core.server_manager import ServerManager
from .handlers.commands import CommandHandler
from .services.binding import BindingService
from .services.message_bridge import MessageBridge
from .services.renderer import InfoRenderer

DEFAULT_TIMEOUT = 30


@register(
    PLUGIN_NAME,
    "XTsat",
    "通过鹊桥模组连接 Minecraft 服务器，实现消息互通、服务器管理与 AI 聊天",
    "v0.1.0",
    "https://github.com/XTsat/astrbot_plugin_minecraft_queqiao",
)
class MinecraftQueQiaoPlugin(Star):
    """Minecraft 鹊桥互通主插件类。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config

        data_dir = Path(StarTools.get_data_dir(PLUGIN_DATA_DIR))
        data_dir.mkdir(parents=True, exist_ok=True)

        self.server_manager = ServerManager()
        self.binding_service = BindingService(data_dir)
        self.message_bridge = MessageBridge(context)
        self.renderer = InfoRenderer()
        self.command_handler = CommandHandler(
            self.server_manager, self.binding_service, self.renderer
        )
        self.command_handler.attach_bridge(self.message_bridge)

        self._configs: dict[str, ServerConfig] = {}
        self._init_task: asyncio.Task | None = None

    # ---- 生命周期 ----

    async def initialize(self) -> None:
        """加载配置并启动所有服务器连接（由 AstrBot 在加载插件后调用）。"""
        if not self.config.get("enabled", True):
            logger.info(f"[{PLUGIN_NAME}] 插件已禁用")
            return

        self.binding_service.load()

        raw_servers = self.config.get("mc_servers", []) or []
        if not isinstance(raw_servers, list) or not raw_servers:
            logger.warning(f"[{PLUGIN_NAME}] 未配置任何服务器")
            return

        any_text2image = False
        for entry in raw_servers:
            if not isinstance(entry, dict) or not entry.get("enabled", True):
                continue

            config = ServerConfig.from_dict(entry)
            if not config.server_id:
                logger.warning(f"[{PLUGIN_NAME}] 跳过 server_id 为空的服务器配置")
                continue
            if config.server_id in self._configs:
                logger.warning(
                    f"[{PLUGIN_NAME}] server_id 重复，后者被忽略: {config.server_id}"
                )
                continue

            self._configs[config.server_id] = config
            self.message_bridge.register_server(config)
            self.server_manager.add(
                config,
                on_event=self._make_event_handler(config.server_id),
                on_connect=self._make_connect_handler(config.server_id),
                on_disconnect=self._make_disconnect_handler(config.server_id),
            )

            if config.custom_cmd_list:
                self.command_handler.register_custom_commands(
                    config.server_id, config.custom_cmd_list
                )

            any_text2image = any_text2image or config.text2image
            logger.info(
                f"[{PLUGIN_NAME}] 已配置服务器: {config.server_id} "
                f"({'反向' if config.is_reverse else '正向'})"
            )
            self._warn_prefix_conflict(config)

        self.renderer.enabled = any_text2image

        if not self._configs:
            logger.warning(f"[{PLUGIN_NAME}] 没有可用的服务器配置")
            return

        await self.server_manager.start_all()
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

        await self.server_manager.stop_all()
        logger.info(f"[{PLUGIN_NAME}] 已关闭")

    @staticmethod
    def _warn_prefix_conflict(config: ServerConfig) -> None:
        """两个前缀互相包含时告警，提示用户在配置中改开。"""
        if config.prefixes_conflict:
            logger.warning(
                f"[{PLUGIN_NAME}][{config.server_id}] 互通前缀 "
                f"`{config.auto_forward_prefix}` 与 AI 前缀 "
                f"`{config.ai_chat_prefix}` 相互包含，消息归属可能产生歧义，"
                f"建议改为互不相同的两个前缀"
            )

    # ---- 事件回调构造 ----

    def _make_event_handler(self, server_id: str):
        async def _handler(event: QueQiaoEvent) -> None:
            await self._on_queqiao_event(server_id, event)

        return _handler

    def _make_connect_handler(self, server_id: str):
        async def _handler() -> None:
            logger.info(f"[{PLUGIN_NAME}][{server_id}] 连接就绪")

        return _handler

    def _make_disconnect_handler(self, server_id: str):
        async def _handler(reason: str) -> None:
            logger.warning(f"[{PLUGIN_NAME}][{server_id}] 连接断开: {reason}")

        return _handler

    # ---- MC 事件处理 ----

    async def _on_queqiao_event(self, server_id: str, event: QueQiaoEvent) -> None:
        """处理来自鹊桥的事件：转发到会话，并识别 AI 聊天触发。"""
        config = self._configs.get(server_id)
        if config is None:
            return

        # AI 与互通互斥：命中 AI 前缀即交给 LLM，不再转发到会话
        question = self._resolve_ai_question(config, event)
        if question is not None:
            await self._handle_ai_chat(server_id, config, event, question)
            return

        await self.message_bridge.forward_event(server_id, config, event)

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
        self, server_id: str, config: ServerConfig, event: QueQiaoEvent, question: str
    ) -> None:
        """把游戏内 AI 提问交给 LLM，并把回复私聊回玩家。

        使用 AstrBot 的 LLM 调用链：优先走会话默认人格，失败则提示玩家。
        """
        player = event.player
        logger.info(
            f"[{PLUGIN_NAME}][{server_id}] AI 提问来自 {player.display_name}: {question}"
        )

        reply = await self._ask_llm(event, question)
        if not reply:
            return

        instance = self.server_manager.get(server_id)
        if instance is None:
            return

        # 私聊回复：多人同时提问不会互相串台；uuid 缺失时退化为昵称
        sent = await instance.client.send_private_message(
            reply, uuid_str=player.uuid, nickname=player.nickname
        )
        if not sent:
            logger.warning(
                f"[{PLUGIN_NAME}][{server_id}] 私聊回复失败，改用广播"
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
    async def cmd_status(self, event: AstrMessageEvent):
        """查看服务器状态"""
        server, hint = self.command_handler._select_target(event)
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(await self.command_handler.handle_status(event, server.server_id))

    @mc_group.command("list")
    async def cmd_list(self, event: AstrMessageEvent):
        """查看在线玩家列表"""
        server, hint = self.command_handler._select_target(event)
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(await self.command_handler.handle_list(event, server.server_id))

    @mc_group.command("player")
    async def cmd_player(self, event: AstrMessageEvent, player_id: str):
        """查看玩家信息"""
        server, hint = self.command_handler._select_target(event)
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(
            await self.command_handler.handle_player(event, server.server_id, player_id)
        )

    @mc_group.command("cmd")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_execute(self, event: AstrMessageEvent, command=GreedyStr):
        """远程执行服务器指令"""
        server, hint = self.command_handler._select_target(event)
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(
            await self.command_handler.handle_cmd(event, server.server_id, str(command))
        )

    @mc_group.command("say")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_say(self, event: AstrMessageEvent, content=GreedyStr):
        """向游戏内广播消息"""
        server, hint = self.command_handler._select_target(event)
        if server is None:
            yield event.plain_result(hint or "❌ 无法确定目标服务器")
            return
        yield event.plain_result(
            await self.command_handler.handle_say(event, server.server_id, str(content))
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
        """处理外部消息：自定义指令匹配与转发到 MC。"""
        if event.is_at_or_wake_command:
            return

        umo = event.unified_msg_origin
        text = event.get_message_str().strip()

        # 待选服务器：用户回复编号
        if text.isdigit() and self.command_handler.has_pending_action(umo):
            resolved = self.command_handler.resolve_selection(umo, int(text))
            if resolved:
                action, server_id, payload = resolved
                if action == "select":
                    result = await self.command_handler.handle_status(event, server_id)
                    yield event.plain_result(result)
            event.stop_event()
            return

        if not text:
            return

        # 自定义指令：仅在会话绑定的服务器上匹配
        for server_id, config in self.message_bridge.servers_for_session(umo):
            actual = self.command_handler.match_custom_command(server_id, text)
            if actual:
                instance = self.server_manager.get(server_id)
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
        if await self._relay_to_minecraft(event, umo, text):
            event.stop_event()

    async def _relay_to_minecraft(
        self, event: AstrMessageEvent, umo: str, text: str
    ) -> bool:
        """把外部会话消息按前缀规则转发到绑定的 MC 服务器。"""
        targets = self.message_bridge.servers_for_session(umo)
        if not targets:
            return False

        relayed = False
        sender = event.get_sender_name() or event.get_sender_id()
        platform = event.get_platform_name() or "未知"

        for server_id, config in targets:
            if not self.message_bridge.should_relay(config, text):
                continue

            instance = self.server_manager.get(server_id)
            if instance is None or not instance.connected:
                continue

            content = self.message_bridge.strip_relay_prefix(config, text)
            if not content:
                continue

            formatted = config.broadcast_format.format(
                platform=platform, sender=sender, message=content, server=server_id
            )
            if await instance.client.broadcast(formatted, config.broadcast_color):
                # 记录以防止该消息从游戏回传时形成回声
                self.message_bridge.mark_forwarded(server_id, content)
                relayed = True

        return relayed
