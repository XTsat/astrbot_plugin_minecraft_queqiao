"""astrbot_plugin_minecraft_queqiao — AstrBot 插件

通过鹊桥模组连接 Minecraft 服务器，实现群服消息互通、服务器管理与 AI 聊天。
配置结构参照 astrbot_plugin_minecraft_adapter，连接层改用鹊桥 V2 协议。
"""

import asyncio
import contextlib
import functools
import re
import time
from collections.abc import Sequence
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.star.filter.command import GreedyStr

from .core.constants import (
    CONNECT_FAIL_NOTIFY_DELAY_MAX,
    CONNECT_FAIL_NOTIFY_DELAY_MIN,
    DEFAULT_IMAGE_HTTP_HOST,
    DEFAULT_IMAGE_HTTP_PORT,
    DEFAULT_IMAGE_UPLOAD_TIMEOUT,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    PLUGIN_DATA_DIR,
    PLUGIN_NAME,
    QUIET_HOURS_ITEM_KEYS,
    QUIET_ITEM_CONNECT,
    QUIET_ITEM_CONNECT_FAIL,
    prefix_matches,
    strip_prefix,
)
from .core.models import QueQiaoEvent
from .core.models_config import ServerConfig, _to_bool, _to_int, _to_str
from .core.queqiao_client import QueQiaoTimeout
from .core.server_manager import ServerManager
from .handlers.commands import CommandHandler, parse_direct_address
from .services.binding import BindingService
from .services.connect_watch import ConnectWatch
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
from .services.slp_ping import parse_host_port
from .services.terminal_log import TerminalLogStore
from .services.translator import Translator
from .services.web_api import WebApiController

DEFAULT_TIMEOUT = 30

# 机器人回复记录的有效期（秒）：覆盖框架逐段发送的时间窗口
BOT_REPLY_RECORD_TTL = 60.0

# 图床条目模板 key（AstrBot 会在每个条目上写入 __template_key 持久化）
TEMPLATE_KEY_BUILTIN_HTTP = "builtin_http"


@register(
    PLUGIN_NAME,
    "XTsat",
    "通过鹊桥模组连接 Minecraft 服务器，实现消息互通、服务器管理与 AI 聊天",
    "v0.7.2",
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
        self.translator = Translator()
        self.message_bridge = MessageBridge(context, self.translator)
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
        self._bot_display_names: dict[tuple[str, str], str] = {}
        # 连通通知的「真启动」判定：断线期间探测服务端端口，区分重启与抖动
        self.connect_watch = ConnectWatch()
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
            self,
        )
        self.web_api.register_routes()
        self._init_task: asyncio.Task | None = None
        self._sent_forward_active = False
        # 最近已转发的机器人账号消息，用于合并 message_sent 与发送后钩子的重复事件
        self._bot_forward_claims: list[tuple[tuple[str, str, int], str, float]] = []
        self._bot_self_ids: dict[str, str] = {}
        self._peer_seen: dict[tuple[str, str], float] = {}
        # 框架发送前记录的回复全文，用于识别其分段发送产生的群消息回声
        self._bot_reply_records: dict[str, list[tuple[float, str, int]]] = {}

    # ---- 生命周期 ----

    async def initialize(self) -> None:
        """加载配置并启动所有服务器连接（由 AstrBot 在加载插件后调用）。"""
        if not self.config.get("enabled", True):
            logger.info(f"[{PLUGIN_NAME}] 插件已禁用")
            return

        self._subscribe_sent_messages()
        self.binding_service.load()
        self.terminal_logs.load()
        logger.info(
            f"[{PLUGIN_NAME}] 终端日志目录: {self._data_dir / 'terminal_logs'}"
        )

        await self._apply_runtime_config()

    async def _apply_runtime_config(self) -> None:
        """按当前 self.config 构建服务器实例并启动连接。

        供 initialize() 与配置热重载（reload_config）共用；调用方需保证
        先清空旧的运行时状态（self._configs / message_bridge 索引）。
        """
        # 图片转存与 MC 服务器无关：必须在「无服务器配置」的空判之前启动，
        # 否则一台服务器都没配时图床被静默跳过，reload_config() 停掉后也不再
        # 恢复（历史缺陷，本次修复）
        await self._setup_image_services()

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
                on_reconnect=self._make_reconnect_handler(config.server_name),
                on_connect_fail=self._make_connect_fail_handler(config.server_name),
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

        await self.server_manager.start_all()
        # 性能监控（TPS/延迟）采集任务：仅对启用了监控的服务器启动
        self.monitor.start(self._configs)
        logger.info(
            f"[{PLUGIN_NAME}] 插件已初始化，共 {len(self._configs)} 台服务器"
        )

    async def _stop_runtime(self) -> None:
        """停止所有运行时连接与监听（不触碰 self.config）。"""
        self.connect_watch.close()
        await self.image_bed.stop_builtin()
        await self.server_manager.stop_all()
        await self.monitor.stop()

    # 面板「功能设置」维护的纯逻辑开关：就地更新运行时配置即可生效，无需
    # 热重载（热重载会断开全部连接、重启监控采集与内置图床，代价与收益不
    # 匹配）。键名与 ServerConfig 属性一一对应；消息转发字段在 conf 里位于
    # message 子对象，Web API 侧先展平再交给本方法。
    SOFT_CONFIG_KEYS = (
        "enable_ai_chat",
        "ai_persona_id",
        "ai_chat_prefix",
        "enable_local_translation",
        "forward_chat_to_astrbot",
        "forward_chat_prefix",
        "forward_chat_format",
        "forward_join_leave_to_astrbot",
        "forward_death_to_astrbot",
        "forward_achievement_to_astrbot",
        "forward_image_to_mc",
        "forward_image_from_mc",
        "auto_forward_prefix",
        "e33chat_media_dir",
        "mc_image_mode",
        "target_sessions",
        "terminal_days",
        "notify_on_connect",
        "notify_on_connect_format",
        "notify_on_connect_fail",
        "notify_on_connect_fail_format",
        "connect_fail_notify_delay",
        "slp_address",
        "quiet_hours_enabled",
        "quiet_hours_start",
        "quiet_hours_end",
        "quiet_hours_items",
    )
    # 布尔型软配置键 → (解析失败时的兜底默认值)，与 _conf_schema.json 默认一致
    _SOFT_BOOL_DEFAULTS = {
        "enable_ai_chat": True,
        "enable_local_translation": False,
        "forward_chat_to_astrbot": True,
        "forward_join_leave_to_astrbot": False,
        "forward_death_to_astrbot": False,
        "forward_achievement_to_astrbot": False,
        "forward_image_to_mc": False,
        "forward_image_from_mc": False,
        "notify_on_connect": False,
        "notify_on_connect_fail": False,
        "quiet_hours_enabled": False,
    }

    def apply_soft_config(self, server_name: str, fields: dict) -> bool:
        """把「不影响连接」的开关就地写入运行时配置，返回是否命中实例。

        未命中（服务器未启用 / 无运行时实例）返回 False，调用方退回完整
        热重载，保证磁盘配置与运行态一致。
        """
        config = self._configs.get(str(server_name or "").strip())
        if config is None or not isinstance(fields, dict):
            return False
        applied = False
        for key in self.SOFT_CONFIG_KEYS:
            if key not in fields:
                continue
            if key in self._SOFT_BOOL_DEFAULTS:
                setattr(config, key, _to_bool(fields.get(key), self._SOFT_BOOL_DEFAULTS[key]))
            elif key == "target_sessions":
                if isinstance(fields.get("target_sessions"), list):
                    config.target_sessions = [
                        str(x).strip() for x in fields["target_sessions"] if str(x).strip()
                    ]
                elif fields.get("target_sessions") is None:
                    config.target_sessions = []
                else:
                    # 类型不合法（如字符串）不应用，避免破坏运行时列表
                    continue
            elif key == "terminal_days":
                # 互通终端加载天数（每台服务器独立）：0~30 钳制
                config.terminal_days = max(
                    0, min(30, _to_int(fields.get(key), config.terminal_days))
                )
            elif key == "connect_fail_notify_delay":
                # 断连静默期（秒，每台服务器独立）：0~3600 钳制
                config.connect_fail_notify_delay = max(
                    CONNECT_FAIL_NOTIFY_DELAY_MIN,
                    min(
                        CONNECT_FAIL_NOTIFY_DELAY_MAX,
                        _to_int(fields.get(key), config.connect_fail_notify_delay),
                    ),
                )
            elif key in ("quiet_hours_start", "quiet_hours_end"):
                # 免打扰时段：留空回落到默认时刻，避免运行时出现「静默期永不生效」
                fallback = (
                    DEFAULT_QUIET_HOURS_START
                    if key == "quiet_hours_start"
                    else DEFAULT_QUIET_HOURS_END
                )
                setattr(config, key, _to_str(fields.get(key), fallback).strip() or fallback)
            elif key == "quiet_hours_items":
                # 免打扰项目：只认已知 key（其余丢弃），顺序固定；非列表不应用
                raw_items = fields.get(key)
                if not isinstance(raw_items, list):
                    continue
                selected = {
                    str(item).strip() for item in raw_items if str(item).strip()
                }
                config.quiet_hours_items = [
                    known for known in QUIET_HOURS_ITEM_KEYS if known in selected
                ]
            else:
                setattr(config, key, str(fields.get(key) or "").strip())
            applied = True
        if not applied:
            return False
        self._warn_prefix_conflict(config)
        changed = [key for key in self.SOFT_CONFIG_KEYS if key in fields]
        logger.info(
            f"[{PLUGIN_NAME}][{config.server_name}] 面板更新开关（免重载）: "
            f"{', '.join(changed)}"
        )
        return True

    async def reload_config(self) -> None:
        """热重载配置：按 self.config 当前值重建全部运行时。

        配置已由调用方写入磁盘与内存（self.config）；此处断开旧连接、
        清空索引后重新应用，使服务器列表/条目/开关的改动全部生效。
        """
        logger.info(f"[{PLUGIN_NAME}] 配置已更新，正在热重载...")
        await self._stop_runtime()
        self._configs.clear()
        self.message_bridge.clear()
        self.renderer.enabled = False
        await self._apply_runtime_config()
        logger.info(f"[{PLUGIN_NAME}] 配置热重载完成")

    async def apply_image_bed_config(self) -> None:
        """只重建图片转存子系统，不触碰 MC 连接与监控采集。

        面板保存图床条目/开关时调用：先停内置 HTTP 监听，再按 self.config
        当前值重建条目并重启监听。与 reload_config() 的区别在于**不会断开
        任何 MC 服务器连接**，保存图床配置不引发全服重连抖动。
        _setup_image_services() 本身幂等（先清空 uploaders 再重建），可安全
        重复调用。
        """
        logger.info(f"[{PLUGIN_NAME}] 图床配置已更新，正在重建图片转存子系统...")
        await self.image_bed.stop_builtin()
        await self._setup_image_services()
        logger.info(
            f"[{PLUGIN_NAME}] 图床配置生效: {self.image_bed.service_names}"
        )

    async def terminate(self) -> None:
        """插件卸载时清理所有连接。"""
        logger.info(f"[{PLUGIN_NAME}] 正在关闭...")
        self._sent_forward_active = False

        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._init_task

        await self._stop_runtime()
        logger.info(f"[{PLUGIN_NAME}] 已关闭")

    def _aiocqhttp_insts(self) -> list:
        return [
            inst
            for inst in self.context.platform_manager.platform_insts
            if inst.meta().name == "aiocqhttp"
        ]

    def _has_peer_listener(self, umo: str) -> bool:
        """除机器人自身平台外还有 aiocqhttp 连接时，机器人发出的群消息可被其旁路收到。"""
        platform_id = umo.split(":", 1)[0]
        return any(inst.meta().id != platform_id for inst in self._aiocqhttp_insts())

    def _subscribe_sent_messages(self) -> None:
        """订阅 aiocqhttp 的 message_sent 与群消息事件，捕获机器人账号手动发出的消息。

        实测手动发送的群消息只推送给同群的其他连接（对端 self_id），不推送给发送者自己的连接，
        因此在所有 aiocqhttp 连接上监听群消息，识别发送者为绑定机器人账号的情况。
        """
        self._sent_forward_active = True
        subscribed = 0
        for inst in self._aiocqhttp_insts():
            client = inst.get_client()
            client.subscribe(
                "message_sent", functools.partial(self._on_message_sent, inst)
            )
            client.subscribe(
                "message.group", functools.partial(self._on_group_message_any, inst)
            )
            subscribed += 1
        logger.info(
            f"[{PLUGIN_NAME}] 已订阅 message_sent 的 aiocqhttp 适配器数={subscribed}"
        )

    async def _on_message_sent(self, inst, payload) -> None:
        """账号自身发出的消息（message_sent 推送）：按转发规则送入 MC。"""
        if not self._sent_forward_active:
            return
        try:
            event = await self._build_bot_event(inst, {**payload, "post_type": "message"})
            if event is not None:
                await self._forward_bot_event(event, "sent")
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 处理 message_sent 失败: {exc}")

    async def _on_group_message_any(self, inst, payload) -> None:
        """识别发送者为绑定机器人账号、但投递到了其他连接的群消息（即手动发送的消息）。"""
        if not self._sent_forward_active or payload.get("message_type") != "group":
            return
        try:
            receiver_id = str(payload.get("self_id") or "")
            sender_id = str(payload.get("user_id") or "")
            if not receiver_id or not sender_id:
                return
            self._bot_self_ids[inst.meta().id] = receiver_id
            if sender_id == receiver_id:
                return
            owner = self._find_bot_owner(inst, sender_id)
            if owner is None:
                await self._learn_login_ids()
                owner = self._find_bot_owner(inst, sender_id)
            if owner is None:
                logger.debug(
                    f"[{PLUGIN_NAME}] 群消息发送者 {sender_id} 未匹配到任何绑定机器人连接"
                )
                return
            if not self._mark_peer_seen(sender_id, str(payload.get("message_id") or "")):
                return
            event = await self._build_bot_event(
                owner,
                {**payload, "post_type": "message", "self_id": payload.get("user_id")},
            )
            if event is None:
                return
            await self._forward_bot_event(event, "peer")
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 处理群消息旁路监听失败: {exc}")

    def _find_bot_owner(self, inst, sender_id: str):
        """返回 self_id 等于 sender_id 的其他 aiocqhttp 连接。"""
        return next(
            (
                other
                for other in self._aiocqhttp_insts()
                if other.meta().id != inst.meta().id
                and self._bot_self_ids.get(other.meta().id) == sender_id
            ),
            None,
        )

    async def _learn_login_ids(self) -> None:
        """主动读取尚未知道登录账号的连接的 QQ 号（get_login_info）。

        机器人账号的连接收不到手动发送的群消息，只能通过 API 获取其 self_id。
        """
        for inst in self._aiocqhttp_insts():
            inst_id = inst.meta().id
            if inst_id in self._bot_self_ids:
                continue
            try:
                info = await asyncio.wait_for(
                    inst.get_client().call_action("get_login_info"), timeout=5
                )
                uid = str((info or {}).get("user_id") or "")
                if uid:
                    self._bot_self_ids[inst_id] = uid
            except Exception as exc:
                logger.debug(f"[{PLUGIN_NAME}] 获取登录账号失败 ({inst_id}): {exc}")

    @staticmethod
    async def _build_bot_event(inst, payload):
        """用指定适配器把原始 OneBot 事件转换为 AstrBot 事件。失败返回 None。"""
        try:
            from aiocqhttp import Event

            abm = await inst.convert_message(Event(payload))
            if abm is None:
                return None
            return inst.create_event(abm)
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 转换 OneBot 事件失败: {exc}")
            return None

    def _mark_peer_seen(self, sender_id: str, message_id: str) -> bool:
        """同一条消息会被同群的多个连接收到，只允许第一次通过。"""
        if not message_id:
            return True
        now = time.monotonic()
        self._peer_seen = {
            key: seen_at for key, seen_at in self._peer_seen.items() if now - seen_at < 30.0
        }
        key = (sender_id, message_id)
        if key in self._peer_seen:
            return False
        self._peer_seen[key] = now
        return True

    async def _forward_bot_event(self, event, origin: str) -> None:
        """机器人账号消息的统一转发入口。origin 用于跨路径去重（sent / peer / hook）。"""
        umo = event.unified_msg_origin
        text = event.get_message_str().strip()
        images = self._extract_images(event)
        targets = self.message_bridge.servers_for_session(umo)
        logger.debug(
            f"[{PLUGIN_NAME}] 收到账号自身发出的消息（{origin}）："
            f"umo={umo}，文本非空={bool(text)}，图片组件={len(images)}，"
            f"绑定服务器={len(targets)}"
        )
        if not any(config.forward_bot_self_messages for _, config in targets):
            return
        if (
            origin != "hook"
            and not self._has_peer_listener(umo)
            and self._is_bot_reply_segment(umo, text, len(images))
        ):
            # 无旁路监听器时，框架逐段发送的回复分段由发送后钩子整条转发
            return
        echo_matched, handled_image_count = (
            self.message_bridge.consume_outbound_echo_details(umo, text)
        )
        if echo_matched:
            # 插件自身转发到 QQ 的内容（MC→QQ）或已由发送后钩子转发的内容，不再重复转发
            if handled_image_count is None or len(images) <= handled_image_count:
                return
            images = images[handled_image_count:]
            text = ""
        if not text and not images:
            return
        if not self._claim_bot_forward(
            self._claim_key(umo, text, len(images)), origin
        ):
            return

        await self._relay_to_minecraft(
            event,
            umo,
            text,
            images=images,
            is_bot_self_message=True,
            sender_override=await self._get_bot_display_name(event),
            apply_wake_prefix=False,
            include_self_mention=False,
            image_fallback_placeholders=True,
        )

    @staticmethod
    def _claim_key(umo: str, text: str, image_count: int) -> tuple[str, str, int]:
        """去重键忽略空白与 [表情:1] 等占位符差异，两条路径的文本渲染方式不同。"""
        return umo, MinecraftQueQiaoPlugin._normalize_bot_text(text), image_count

    @staticmethod
    def _normalize_bot_text(text: str) -> str:
        return re.sub(r"\[[^\]]*\]|\s+", "", text)

    def _claim_bot_forward(self, key: tuple[str, str, int], origin: str) -> bool:
        """同一条机器人消息可能同时经 message_sent 与发送后钩子到达，只允许先到的一条路径转发。

        同一来源的重复记录不去重（手动连发相同内容仍会转发）；
        不同来源在时效内命中同一键时，后到者放弃转发并移除登记。
        """
        now = time.monotonic()
        self._bot_forward_claims = [
            claim for claim in self._bot_forward_claims if now - claim[2] < 5.0
        ]
        for index, (claimed_key, claimed_origin, _) in enumerate(
            self._bot_forward_claims
        ):
            if claimed_key == key and claimed_origin != origin:
                del self._bot_forward_claims[index]
                return False
        self._bot_forward_claims.append((key, origin, now))
        return True

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
        """转发前缀与 AI 前缀互相包含时告警，提示用户改开。"""
        if config.prefixes_conflict:
            logger.warning(
                f"[{PLUGIN_NAME}][{config.server_name}] 游戏→群前缀 "
                f"`{config.forward_chat_prefix}` 与 AI 前缀 "
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
        await self._send_text_to_sessions(
            config,
            f"⚠️ 配置告警：server_name「{config.server_name}」"
            "与已有服务器重复，本服务器的配置已被忽略、未启用。"
            "请修改本服务器的 server_name（需与鹊桥 config.yml 的 "
            "server_name 一致），否则本服务器不会启用。",
        )

    async def _notify_server_online(self, server_name: str) -> None:
        """服务器连通后按配置向目标会话发送「服务器已启动」通知。

        每次连接建立都会触发（含断线重连、插件热重载后重新连上），因此发送前
        先用 connect_watch 判定这次重连背后服务器是否真的启动过：短时断连
        （隧道抖动、服务端卡顿、热重载）不发通知，避免「服务器已启动」误报。
        开关关闭或未配置目标会话时静默跳过。发送失败只告警，不影响连接本身。
        """
        watch = getattr(self, "connect_watch", None)
        real_start, basis, downtime = (
            watch.verdict(server_name) if watch is not None else (True, "", 0.0)
        )
        config = self._configs.get(server_name)
        if config is None or not config.notify_on_connect:
            return
        if not real_start:
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 断线 {downtime:.0f} 秒后重连，"
                f"判定为连接抖动（依据 {basis}），跳过启动通知"
            )
            return
        # 免打扰时段：连通通知可单独静音（夜里重连不打扰）
        if config.quiet_suppresses(QUIET_ITEM_CONNECT):
            return
        sent = await self._send_text_to_sessions(
            config, config.render_connect_notice()
        )
        if sent:
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 已向 {sent}/"
                f"{len(config.target_sessions)} 个会话发送服务器启动通知"
                f"（依据 {basis or 'unknown'}，断线 {downtime:.0f} 秒）"
            )

    async def _notify_server_fail(self, server_name: str) -> None:
        """连接失败时按配置向目标会话发送「连接失败」通知。

        由 QueQiaoClient 保证：断连持续超过「断连静默期」仍未恢复才回调一次
        （期间连回则完全不通知），同一轮故障只触发一次，重新连上后下一轮故障
        会再次通知；开关关闭或未配置目标会话时跳过。
        """
        config = self._configs.get(server_name)
        if config is None or not config.notify_on_connect_fail:
            return
        # 免打扰时段：连接失败通知可单独静音
        if config.quiet_suppresses(QUIET_ITEM_CONNECT_FAIL):
            return
        sent = await self._send_text_to_sessions(
            config, config.render_connect_fail_notice()
        )
        if sent:
            logger.info(
                f"[{PLUGIN_NAME}][{server_name}] 已向 {sent}/"
                f"{len(config.target_sessions)} 个会话发送连接失败通知"
            )

    async def _send_text_to_sessions(self, config: ServerConfig, text: str) -> int:
        """向该服务器的全部目标会话发送一条纯文本，返回成功会话数。

        单会话失败只记警告并继续，不影响其余会话与连接本身。
        """
        if not text or not config.target_sessions:
            return 0
        try:
            from astrbot.api.event import MessageChain
            from astrbot.api.message_components import Plain

            chain = MessageChain(chain=[Plain(text=text)])
        except Exception:
            logger.warning(
                f"[{PLUGIN_NAME}][{config.server_name}] 构建通知消息失败",
                exc_info=True,
            )
            return 0

        sent = 0
        for umo in config.target_sessions:
            echo_stamp = self.message_bridge.mark_outbound_message(umo, text)
            try:
                result = await self.context.send_message(umo, chain)
                if result is False:
                    self.message_bridge.discard_outbound_message(
                        umo, text, echo_stamp
                    )
                    logger.warning(
                        f"[{PLUGIN_NAME}][{config.server_name}] "
                        f"没有可用适配器发送通知到 {umo}"
                    )
                    continue
                sent += 1
            except Exception:
                self.message_bridge.discard_outbound_message(
                    umo, text, echo_stamp
                )
                logger.warning(
                    f"[{PLUGIN_NAME}][{config.server_name}] 向 {umo} 发送通知失败",
                    exc_info=True,
                )
        return sent

    # ---- 事件回调构造 ----

    def _make_event_handler(self, server_name: str):
        async def _handler(event: QueQiaoEvent) -> None:
            await self._on_queqiao_event(server_name, event)

        return _handler

    def _make_connect_handler(self, server_name: str):
        async def _handler() -> None:
            logger.info(f"[{PLUGIN_NAME}][{server_name}] 连接就绪")
            self.metrics.record_event(
                "conn", server_name, "连接恢复", {"event": "connected"}
            )
            self.terminal_logs.append(server_name, "conn", "🟢 连接恢复")
            await self._notify_server_online(server_name)

        return _handler

    def _make_disconnect_handler(self, server_name: str):
        async def _handler(reason: str) -> None:
            logger.warning(f"[{PLUGIN_NAME}][{server_name}] 连接断开: {reason}")
            self.metrics.record_event(
                "conn", server_name, f"连接断开: {reason}", {"reason": reason}
            )
            self.terminal_logs.append(server_name, "conn", f"🔴 连接断开: {reason}")
            # 断线即开始探测服务端是否还在响应，供下次连上时判定真启动/抖动
            watch = getattr(self, "connect_watch", None)
            if watch is not None:
                watch.outage_started(server_name, self._slp_target(server_name))

        return _handler

    def _slp_target(self, server_name: str) -> tuple[str, int] | None:
        """取该服务器配置的状态探测地址，未配置或非法时返回 None。"""
        config = self._configs.get(server_name)
        if config is None:
            return None
        return parse_host_port(config.slp_address)

    def _make_connect_fail_handler(self, server_name: str):
        async def _handler(reason: str) -> None:
            # QueQiaoClient 侧已做两道收敛：断连静默期内连回不回调、同一轮
            # 故障只回调一次；已连接后断线的终端记录由 disconnect 回调负责，
            # 这里不再重复写同义终端行，只补日志并按配置发通知
            logger.warning(f"[{PLUGIN_NAME}][{server_name}] 连接失败: {reason}")
            await self._notify_server_fail(server_name)

        return _handler

    def _make_reconnect_handler(self, server_name: str):
        async def _handler(attempt: int, stage: str) -> None:
            # 重连调度事件：达上限与进行中分开呈现。用 "conn" 类型走
            # metrics 历史 + SSE（不在 events_by_type 白名单，不污染统计口径）
            if stage == "上限":
                self.metrics.record_event(
                    "conn",
                    server_name,
                    f"已达重连上限（第 {attempt} 次），停止重连",
                    {"attempt": attempt, "stage": stage},
                )
                self.terminal_logs.append(
                    server_name, "conn", f"⛔ 已达重连上限（第 {attempt} 次），停止重连"
                )
                logger.error(
                    f"[{PLUGIN_NAME}][{server_name}] 重连次数已达上限 "
                    f"({attempt})，停止重连"
                )
                return

            stage_text = "低频重试" if stage == "低频" else "退避重试"
            self.metrics.record_event(
                "conn",
                server_name,
                f"第 {attempt} 次重连（{stage_text}）",
                {"attempt": attempt, "stage": stage},
            )
            self.terminal_logs.append(
                server_name, "conn", f"🔁 第 {attempt} 次重连（{stage_text}）"
            )
            logger.warning(
                f"[{PLUGIN_NAME}][{server_name}] 第 {attempt} 次重连（{stage_text}）"
            )

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
            if config.enable_local_translation:
                death_text = self.translator.translate_death(event.death)
            else:
                # text 可能是未格式化模板（%s占位），render_text 做参数填充
                death_text = event.death.render_text or "死亡"
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
            # display_text 可能为空（未开翻译 + 服务端仅给 key），
            # 与 message_bridge.format_event 保持一致：退到 display_name，
            # 最差也能给出成就 key，避免无信息量的「达成成就」；
            # 本地翻译开启时直接翻译成就名（整句 display_text 由转发层处理）
            if config.enable_local_translation:
                ach_text = self.translator.translate_achievement(event.achievement)
            else:
                ach_text = (
                    event.achievement.display_text
                    or event.achievement.display_name
                    or "达成成就"
                )
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

        reply = await self._ask_llm(config, event, question)
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

    async def _ask_llm(
        self, config: ServerConfig, event: QueQiaoEvent, question: str
    ) -> str:
        """调用 AstrBot LLM，返回纯文本回复；不可用时返回空串。

        使用 `get_using_provider` + `text_chat`，与 AstrBot 4.x 的 provider 接口一致。
        - uma 优先取该服务器的首个 target_sessions，以匹配对应适配器的 provider；
          无 target_sessions 时 uma=None，回退默认 provider。
        - 若配置了 ai_persona_id，取该人格 prompt 作为 system_prompt，与 UMO 会话
          默认人格解耦，用户可自行选择对话人格。
        """
        try:
            uma = config.target_sessions[0] if config.target_sessions else None
            provider = self.context.get_using_provider(umo=uma)
            if provider is None:
                logger.warning(f"[{PLUGIN_NAME}] 未找到可用的 LLM 提供商")
                return ""

            system_prompt = None
            persona_id = getattr(config, "ai_persona_id", "") or ""
            if persona_id:
                persona = self.context.persona_manager.get_persona_v3_by_id(persona_id)
                if persona:
                    system_prompt = str(persona.get("prompt") or "").strip() or None

            if system_prompt:
                response = await provider.text_chat(
                    system_prompt=system_prompt, prompt=question
                )
            else:
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

    @filter.on_decorating_result()
    async def capture_bot_reply_for_relay(self, event: AstrMessageEvent) -> None:
        """在框架拆分回复前保存完整文本，供发送后统一转发。"""
        umo = event.unified_msg_origin
        if not any(
            config.forward_bot_self_messages
            for _, config in self.message_bridge.servers_for_session(umo)
        ):
            return

        result = event.get_result()
        if result is None:
            return

        text = self._bot_reply_to_text(result.chain)
        images = self._bot_reply_images(result.chain)
        if text:
            event.set_extra("_queqiao_bot_reply_text", text)
        if images:
            event.set_extra("_queqiao_bot_reply_images", images)
        if text or images:
            self._record_bot_reply(umo, text, len(images))

    def _record_bot_reply(self, umo: str, text: str, image_count: int) -> None:
        """记录一条即将发出的回复，供分段发送产生的群消息回声识别。"""
        now = time.monotonic()
        records = [
            record
            for record in self._bot_reply_records.get(umo, [])
            if now - record[0] < BOT_REPLY_RECORD_TTL
        ]
        records.append((now, self._normalize_bot_text(text), image_count))
        self._bot_reply_records[umo] = records

    def _is_bot_reply_segment(self, umo: str, text: str, image_count: int) -> bool:
        """判断群消息是否为近期某条流水线回复的分段（框架逐段发送时产生）。"""
        now = time.monotonic()
        normalized = self._normalize_bot_text(text)
        for seen_at, reply_text, reply_images in self._bot_reply_records.get(umo, []):
            if now - seen_at >= BOT_REPLY_RECORD_TTL:
                continue
            if normalized and normalized in reply_text:
                return True
            if not normalized and image_count and image_count <= reply_images:
                return True
        return False

    @staticmethod
    def _bot_reply_to_text(components: Sequence[object]) -> str:
        """Extract reply text while preserving non-image component placeholders."""
        from astrbot.api.message_components import Face, Image, Plain

        parts = []
        for component in components:
            if isinstance(component, Plain):
                parts.append(component.text or "")
                continue
            if isinstance(component, Image):
                continue
            if isinstance(component, Face):
                placeholder = f"[表情:{component.id}]"
            else:
                component_name = type(component).__name__
                placeholder = f"[{component_name}]"
            if parts and parts[-1] and not parts[-1][-1].isspace():
                parts.append(" ")
            parts.extend((placeholder, " "))
        return "".join(parts).strip()

    @staticmethod
    def _bot_reply_images(components: Sequence[object]) -> list[object]:
        from astrbot.api.message_components import Image

        return [component for component in components if isinstance(component, Image)]

    async def _get_bot_display_name(self, event: AstrMessageEvent) -> str:
        """Resolve the bot's display name instead of exposing its platform ID."""
        bot_id = str(event.get_self_id() or "").strip()
        if not bot_id:
            return "Bot"

        get_platform_id = getattr(event, "get_platform_id", None)
        platform_id = (
            str(get_platform_id() or "")
            if callable(get_platform_id)
            else str(event.get_platform_name() or "")
        )
        cache_key = (platform_id, bot_id)
        if cached_name := self._bot_display_names.get(cache_key):
            return cached_name

        display_name = ""
        if event.get_platform_name() == "aiocqhttp":
            bot = getattr(event, "bot", None)
            call_action = getattr(bot, "call_action", None)
            if callable(call_action):
                group_id = getattr(event, "get_group_id", lambda: "")()
                if group_id:
                    try:
                        numeric_group_id = int(group_id)
                        numeric_bot_id = int(bot_id)
                    except (TypeError, ValueError):
                        member = None
                    else:
                        try:
                            member = await call_action(
                                action="get_group_member_info",
                                group_id=numeric_group_id,
                                user_id=numeric_bot_id,
                                no_cache=False,
                            )
                        except Exception as exc:
                            logger.debug(
                                f"[{PLUGIN_NAME}] 获取 Bot 群昵称失败，"
                                f"回退账号昵称: {exc}"
                            )
                            member = None
                    if isinstance(member, dict):
                        display_name = str(member.get("card") or "").strip() or str(
                            member.get("nickname") or ""
                        ).strip()

                if not display_name:
                    try:
                        login_info = await call_action(action="get_login_info")
                    except Exception as exc:
                        logger.warning(
                            f"[{PLUGIN_NAME}] 获取 Bot 昵称失败，将使用通用名称: {exc}"
                        )
                    else:
                        if isinstance(login_info, dict):
                            display_name = str(
                                login_info.get("nickname")
                                or login_info.get("name")
                                or ""
                            ).strip()

        if display_name and display_name != bot_id:
            self._bot_display_names[cache_key] = display_name
            return display_name
        return "Bot"

    @filter.after_message_sent()
    async def on_after_message_sent(self, event: AstrMessageEvent) -> None:
        """仅监听 AstrBot 经消息管道发出的回复，不把机器人消息重新送入指令处理。"""
        umo = event.unified_msg_origin
        if not any(
            config.forward_bot_self_messages
            for _, config in self.message_bridge.servers_for_session(umo)
        ):
            return
        if self._has_peer_listener(umo):
            # 分段已由旁路监听逐段转发，此处不再补发整条回复
            return

        text = event.get_extra("_queqiao_bot_reply_text", "")
        images = event.get_extra("_queqiao_bot_reply_images", [])
        if not isinstance(text, str):
            text = ""
        if not isinstance(images, list):
            images = []
        if not images:
            result = event.get_result()
            if result is not None:
                images = self._bot_reply_images(result.chain)
        if not text and not images:
            return

        if not self._claim_bot_forward(
            self._claim_key(umo, text, len(images)), "hook"
        ):
            logger.debug(f"[{PLUGIN_NAME}] Bot 回复已由 message_sent 路径转发，跳过重复转发")
            return
        echo_stamp = self.message_bridge.mark_outbound_message(
            umo, text, image_count=len(images)
        )
        relayed = False
        try:
            relayed = await self._relay_to_minecraft(
                event,
                umo,
                text,
                images=images,
                is_bot_self_message=True,
                sender_override=await self._get_bot_display_name(event),
                apply_wake_prefix=False,
                include_self_mention=False,
                image_fallback_placeholders=True,
            )
        finally:
            if not relayed:
                self.message_bridge.discard_outbound_message(
                    umo, text, echo_stamp
                )

    @staticmethod
    def _is_platform_event(event: AstrMessageEvent) -> bool:
        """识别通知/请求等非聊天事件，避免转发事件描述文本。"""
        message_type = event.get_message_type()
        if getattr(message_type, "value", message_type) == "OtherMessage":
            return True

        raw_message = getattr(event.message_obj, "raw_message", None)
        post_type = getattr(raw_message, "post_type", None)
        raw_get = getattr(raw_message, "get", None)
        if post_type is None and callable(raw_get):
            post_type = raw_get("post_type")
        if post_type in {"notice", "request"}:
            return True

        for component in event.get_messages() or []:
            component_type = getattr(component, "type", None)
            if getattr(component_type, "value", component_type) == "Poke":
                return True
        return False

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理外部消息：自定义指令匹配与转发到 MC（含图片）。

        不要用 `is_at_or_wake_command` 短路：QQ 回复/转发 Bot 消息时客户端
        会自动附带 @Bot（AstrBot 唤醒判定会因此标记唤醒命令），若在此 return，
        这类回复内容将永远无法转发到游戏。普通转发只作为监听操作，不停止原事件，
        让 AstrBot 仍可处理唤醒消息。空消息（无文本无图片）由下方统一过滤。
        """
        if self._is_platform_event(event):
            if event.get_sender_id() == event.get_self_id():
                logger.info(
                    f"[{PLUGIN_NAME}] 收到 Bot 自身平台事件但按非聊天事件过滤："
                    f"type={event.get_message_type()}"
                )
            return

        umo = event.unified_msg_origin
        text = event.get_message_str().strip()
        images = self._extract_images(event)

        is_bot_self_message = event.get_sender_id() == event.get_self_id()
        targets = self.message_bridge.servers_for_session(umo)
        if is_bot_self_message:
            enabled_targets = [
                server_name
                for server_name, config in targets
                if config.forward_bot_self_messages
            ]
            logger.info(
                f"[{PLUGIN_NAME}] 收到 Bot 自身群消息监听事件："
                f"图片组件={len(images)}，文本非空={bool(text)}，"
                f"绑定服务器={len(targets)}，启用自身转发={enabled_targets}"
            )
            echo_matched, handled_image_count = (
                self.message_bridge.consume_outbound_echo_details(umo, text)
            )
            original_text = getattr(event.message_obj, "message_str", None)
            if (
                not echo_matched
                and isinstance(original_text, str)
                and original_text.strip() != text
            ):
                echo_matched, handled_image_count = (
                    self.message_bridge.consume_outbound_echo_details(
                        umo, original_text.strip()
                    )
                )
            if echo_matched:
                if handled_image_count is None or len(images) <= handled_image_count:
                    logger.info(
                        f"[{PLUGIN_NAME}] Bot 自身消息命中回声抑制并跳过："
                        f"事件图片={len(images)}，已由发送管道处理图片={handled_image_count}"
                    )
                    return
                images = images[handled_image_count:]
                text = ""
            if not any(
                config.forward_bot_self_messages for _, config in targets
            ):
                logger.info(
                    f"[{PLUGIN_NAME}] Bot 自身消息未转发："
                    "目标会话未启用「转发机器人自己的消息，不剥离唤醒词」"
                )
                return

        # 图片不参与文本匹配，但可随消息一起转发到 MC
        if not text and not images:
            original_wake_text = event.is_at_or_wake_command and any(
                config.forward_bot_self_messages
                and (
                    self._relay_text(event, config, text)
                    or self._self_mention_text(event)
                )
                for _, config in self.message_bridge.servers_for_session(umo)
            )
            if not original_wake_text:
                return

        # 自定义指令：仅在会话绑定的服务器上匹配（按文本匹配，图片不参与）
        if text and not is_bot_self_message:
            for server_name, config in targets:
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
        relayed = await self._relay_to_minecraft(
            event,
            umo,
            text,
            images,
            is_bot_self_message=is_bot_self_message,
            image_fallback_placeholders=is_bot_self_message,
        )
        if is_bot_self_message and not relayed:
            logger.info(
                f"[{PLUGIN_NAME}] Bot 自身消息已到监听器但未转发："
                f"图片组件={len(images)}，文本非空={bool(text)}；"
                "请检查转发前缀、服务器连接及图片转发配置/日志"
            )

    @staticmethod
    def _relay_text(event: AstrMessageEvent, config: ServerConfig, text: str) -> str:
        """Choose the pre-wake text only when that server opts into it."""
        if config.forward_bot_self_messages and event.is_at_or_wake_command:
            original_text = getattr(event.message_obj, "message_str", None)
            if isinstance(original_text, str) and original_text.strip():
                return original_text.strip()
        return text

    @staticmethod
    def _self_mention_text(event: AstrMessageEvent) -> str | None:
        """Restore the leading self-mention omitted from OneBot's message text."""
        try:
            from astrbot.api.message_components import At
        except ImportError:
            return None

        self_id = str(event.get_self_id() or "").strip()
        if not self_id:
            return None

        for component in event.get_messages() or []:
            if isinstance(component, At) and str(component.qq) == self_id:
                name = str(getattr(component, "name", "") or "").strip() or self_id
                return f"@{name}({self_id})"
        return None

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
    def _extract_reply_mention(
        event: AstrMessageEvent, config: ServerConfig
    ) -> str | None:
        """从「回复消息」的被引用文本解析游戏玩家名。

        QQ 群友回复 Bot 转发的游戏消息时，AstrBot 事件链携带 Reply 组件，
        其 message_str 为被引用消息的纯文本（由 forward_chat_format 渲染，
        形如 `[MC]Player_A: 1`）。按该服务器的 forward_chat_format 结构生成
        解析正则：player 段须为合法 Minecraft 玩家名（3-16 位字母/数字/
        下划线），格式含 display_name 段时还须与服务器显示名一致（防止把
        QQ 聊天等其它回复误判为游戏消息）。解析成功返回玩家名，转发时在
        游戏内显示 `@玩家名`；失败返回 None（不加 @，转发照常）。
        """
        try:
            from astrbot.api.message_components import Reply
        except Exception:
            return None
        components = event.get_messages() or []
        reply = next((comp for comp in components if isinstance(comp, Reply)), None)
        if reply is None:
            return None
        referenced = (getattr(reply, "message_str", "") or "").strip()
        if not referenced:
            return None

        # 占位符 → 捕获组，其余字面部分转义后整体匹配
        pattern = re.escape(config.forward_chat_format)
        pattern = pattern.replace(re.escape("{display_name}"), r"(?P<display>.*?)")
        pattern = pattern.replace(
            re.escape("{player}"), r"(?P<player>[A-Za-z0-9_]{3,16})"
        )
        pattern = pattern.replace(re.escape("{message}"), r"(?P<msg>.*)")
        match = re.fullmatch(pattern, referenced, re.DOTALL)
        if not match:
            return None
        if (
            "display" in match.groupdict()
            and match.group("display") != config.server_label
        ):
            return None
        return match.group("player")

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
        self,
        event: AstrMessageEvent,
        umo: str,
        text: str,
        images: list[object] | None = None,
        *,
        is_bot_self_message: bool | None = None,
        sender_override: str | None = None,
        apply_wake_prefix: bool = True,
        include_self_mention: bool = True,
        image_fallback_placeholders: bool = False,
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
        sender = sender_override or event.get_sender_name() or event.get_sender_id()
        platform = event.get_platform_name() or "未知"
        if is_bot_self_message is None:
            is_bot_self_message = event.get_sender_id() == event.get_self_id()

        for server_name, config in targets:
            if (
                is_bot_self_message and not config.forward_bot_self_messages
            ):
                continue
            relay_text = (
                self._relay_text(event, config, text) if apply_wake_prefix else text
            )
            self_mention = (
                self._self_mention_text(event)
                if include_self_mention and config.forward_bot_self_messages
                else None
            )
            if not relay_text and not images and not self_mention:
                continue
            if not self.message_bridge.should_relay(
                config, relay_text, has_images=bool(images)
            ):
                continue

            instance = self.server_manager.get(server_name)
            if instance is None or not instance.connected:
                logger.warning(
                    f"[{PLUGIN_NAME}][{server_name}] 服务器未连接，"
                    f"跳过该消息的转发: {text[:60]}"
                )
                continue

            # 文本部分（供回声抑制与格式占位符使用）
            content = self.message_bridge.strip_relay_prefix(config, relay_text)
            if self_mention and self_mention not in content:
                content = f"{self_mention} {content}".strip()

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

            if image_fallback_placeholders and images:
                unforwarded_images = len(images) - len(image_codes)
                if unforwarded_images:
                    placeholders = " ".join(
                        "[图片]" for _ in range(unforwarded_images)
                    )
                    content = f"{content} {placeholders}".strip()

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
            # 回复 Bot 转发的游戏消息时，被引用文本可反解出游戏玩家名，
            # 在游戏内显示 `@玩家名`（回声抑制仍以 content 为准，不含 @）
            mention = self._extract_reply_mention(event, config)
            if mention:
                message = f"@{mention}" + (f" {message}" if message else "")
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
            # 记录实际广播到 MC 的 formatted 文本，与 forward_event 中
            # _is_echo 比对的 event.message 保持一致（均含格式前缀），
            # 才能正确抑制 QQ->MC->QQ 的回声刷屏。
            self.message_bridge.mark_forwarded(server_name, formatted)
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
            if not is_bot_self_message:
                # 转发成功后给原消息回执（emoji 贴表情 / text 文本回复）
                await self.message_bridge.mark_relayed(event, config)

        return relayed
