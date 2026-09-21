"""消息桥：MC 事件 ↔ 外部会话 的双向转发。

关键设计：
- `target_sessions`（UMO 列表）是绑定关系的锚点，同时决定两个方向的目标
- 外部 → MC 转发后，该内容在抑制窗口内从 MC 回传时不再转发，避免回声刷屏
- 富文本 `raw_message` 可能是 JSON 文本组件，转发前剥离为纯文本
"""

import json
import re
import time
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ..core.constants import (
    API_SET_MSG_EMOJI_LIKE,
    ECHO_SUPPRESS_WINDOW,
    EMOJI_OK_GESTURE,
    MARK_TEXT_OK,
    PLUGIN_NAME,
    prefix_matches,
    strip_prefix,
)
from ..core.models import QueQiaoEvent
from ..core.models_config import ServerConfig

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent

# MC 传统格式化代码（§a 等）与文本组件都可能混在消息里
_FORMAT_CODE_RE = re.compile(r"§[0-9a-fk-orA-FK-OR]")


def strip_formatting(text: str) -> str:
    """剥离 MC 格式化代码。"""
    return _FORMAT_CODE_RE.sub("", text)


def component_to_text(raw: str) -> str:
    """把可能为 JSON 文本组件的字符串还原为纯文本。

    非原版服务端的 `raw_message` 可能是 {"text":"Hello","color":"light_purple"}
    这类形态，若直接转发到 QQ 会出现花括号，因此这里递归提取 text 字段。
    """
    if not raw:
        return ""

    stripped = raw.strip()
    if not stripped.startswith(("{", "[", '"')):
        return strip_formatting(stripped)

    try:
        data = json.loads(stripped)
    except ValueError:
        return strip_formatting(stripped)

    def _extract(node: object) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, list):
            return "".join(_extract(item) for item in node)
        if isinstance(node, dict):
            parts: list[str] = []
            if "text" in node:
                parts.append(str(node["text"]))
            if "extra" in node:
                parts.append(_extract(node["extra"]))
            if "with" in node:
                parts.append(_extract(node["with"]))
            return "".join(parts)
        return ""

    return strip_formatting(_extract(data)) or strip_formatting(stripped)


class MessageBridge:
    """负责 MC 事件到外部会话的格式化与发送。"""

    def __init__(self, context) -> None:
        self.context = context
        self._configs: dict[str, ServerConfig] = {}
        # 会话 UMO -> [(server_id, config)]，用于外部消息反查目标服务器
        self._session_to_servers: dict[str, list[tuple[str, ServerConfig]]] = {}
        # (server_id, content) -> 转发时间，用于回声抑制
        self._recently_forwarded: dict[tuple[str, str], float] = {}

    def register_server(self, config: ServerConfig) -> None:
        """注册服务器并建立目标会话的反向索引。"""
        self._configs[config.server_id] = config
        for umo in config.target_sessions:
            entries = self._session_to_servers.setdefault(umo, [])
            if all(sid != config.server_id for sid, _ in entries):
                entries.append((config.server_id, config))

    def servers_for_session(self, umo: str) -> list[tuple[str, ServerConfig]]:
        """查询某会话绑定的服务器列表。"""
        return list(self._session_to_servers.get(umo, []))

    # ---- 回声抑制 ----

    def mark_forwarded(self, server_id: str, content: str) -> None:
        """记录一条刚刚转发到 MC 的内容。"""
        self._recently_forwarded[(server_id, content)] = time.time()

    def _is_echo(self, server_id: str, content: str) -> bool:
        """判断该内容是否为刚刚转发出去的回声。"""
        key = (server_id, content)
        stamp = self._recently_forwarded.get(key)
        if stamp is None:
            return False
        del self._recently_forwarded[key]
        return (time.time() - stamp) < ECHO_SUPPRESS_WINDOW

    # ---- MC → 外部 ----

    def should_forward(self, config: ServerConfig, event: QueQiaoEvent) -> bool:
        """依据事件类型与配置判断是否需要转发。"""
        if event.is_chat:
            return config.forward_chat_to_astrbot
        if event.is_join or event.is_quit:
            return config.forward_join_leave_to_astrbot
        if event.is_death:
            return config.forward_death_to_astrbot
        if event.is_achievement:
            return config.forward_achievement_to_astrbot
        return False

    def format_event(self, config: ServerConfig, event: QueQiaoEvent) -> str:
        """把事件渲染为转发文本。"""
        player = event.player_name or "未知"

        if event.is_chat:
            message = component_to_text(event.raw_message) or component_to_text(
                event.message
            )
            # {server} 取显示名称：server_name 留空时用 server_name_default（默认 MC），
            # 两者都显式留空才输出空串（无前缀）；均不回退 server_id
            return config.forward_chat_format.format(
                player=player, message=message, server=config.server_label
            )

        if event.is_join:
            return f"🟢 {player} 加入了服务器"
        if event.is_quit:
            return f"🔴 {player} 离开了服务器"
        if event.is_death:
            text = event.death.text or "死亡"
            return f"💀 {text}"
        if event.is_achievement:
            # display_text 可能为空（未开翻译 + 服务端仅给 key），
            # 此时退到 display_name，最差也能给出成就 key，避免无信息量的「达成成就」
            text = event.achievement.display_text or event.achievement.display_name
            if not text:
                return f"🏆 {player} 达成了成就"

            # 补玩家名：开启翻译时整句已含玩家名（`X has made the advancement [Y]`），
            # 未开启时只降级到 display.title，那里**只有成就名**。
            # 故先判重，避免出现 `X X has made the advancement [Y]`。
            if event.player_name and event.player_name not in text:
                return f"🏆 {player} 达成了成就 {text}"
            return f"🏆 {text}"
        return ""

    async def forward_event(
        self, server_id: str, config: ServerConfig, event: QueQiaoEvent
    ) -> bool:
        """把 MC 事件转发到该服务器配置的所有目标会话。"""
        if not self.should_forward(config, event):
            return False

        targets = config.target_sessions
        if not targets:
            return False

        content = self.format_event(config, event)
        if not content:
            return False

        # 聊天消息需先经过回声抑制：外部发到 MC 的内容会原样回传为聊天事件
        if event.is_chat and self._is_echo(server_id, event.message.strip()):
            logger.debug(f"[{PLUGIN_NAME}][{server_id}] 抑制回声消息: {event.message}")
            return False

        for umo in targets:
            await self._send(umo, content)
        return True

    async def _send(self, umo: str, content: str) -> bool:
        """向指定会话发送文本消息。"""
        try:
            from astrbot.api.event import MessageChain
            from astrbot.api.message_components import Plain

            chain = MessageChain(chain=[Plain(text=content)])
            await self.context.send_message(umo, chain)
            return True
        except Exception as exc:
            logger.error(f"[{PLUGIN_NAME}] 发送消息到会话 {umo} 失败: {exc}")
            return False

    # ---- 外部 → MC ----

    def should_relay(self, config: ServerConfig, text: str) -> bool:
        """判断外部消息是否应转发到 MC（按前缀过滤）。

        与 AI 前缀不同：转发前缀留空表示**全部转发**，
        因此这里不能用 `prefix_matches` 的「空即不匹配」语义。
        """
        prefix = config.auto_forward_prefix
        if not prefix:
            return True
        return prefix_matches(prefix, text)

    def strip_relay_prefix(self, config: ServerConfig, text: str) -> str:
        """去掉转发前缀。"""
        return strip_prefix(config.auto_forward_prefix, text)

    # ---- 转发回执 ----

    async def mark_relayed(self, event: Any, config: ServerConfig) -> None:
        """转发成功后按 `mark_option` 给出回执。

        - `emoji`：给原消息贴表情（走协议端私有接口，仅 aiocqhttp 支持）
        - `text`：回复一条 ✅ 文本
        - `none`：不提醒

        回执属于「锦上添花」，任何失败都只记 debug 日志，绝不影响转发结果。
        """
        option = config.mark_option
        if option == "none":
            return
        if option == "emoji":
            # 只贴表情，不额外发文本；平台不支持时不回退成文本，避免刷屏
            await self._react_with_emoji(event, emoji_id=config.mark_emoji_id)
            return
        await self._mark_text(event)

    async def _react_with_emoji(
        self, event: "AstrMessageEvent", emoji_id: int = EMOJI_OK_GESTURE
    ) -> bool:
        """给原消息贴表情（OneBot 扩展 `set_msg_emoji_like`，所有 aiocqhttp
        协议端均支持，如 NapCat / Lagrange / LLOneBot）。

        emoji_id: 要使用的表情符号 ID (默认: EMOJI_OK_GESTURE)
            - EMOJI_OK_GESTURE (124): 👌
            - EMOJI_THUMBS_UP (76): 👍
            - EMOJI_LOVE (66): ❤️
            - EMOJI_ROSE (63): 🌹

        非 aiocqhttp 平台、或拿不到 message_id 时静默跳过。

        注意：aiocqhttp 的 `CQHttp.__getattr__` 会为**任意**名字返回
        `call_action` 的偏函数，所以不能用 `getattr(bot, "set_msg_emoji_like")`
        判断接口是否存在——那样永远为真。这里直接走 `call_action`，
        由协议端在真正不支持时返回错误，再降级为静默跳过。
        """
        message_id = getattr(getattr(event, "message_obj", None), "message_id", None)
        if not message_id:
            return False

        bot = getattr(event, "bot", None)
        emoji_id = emoji_id or EMOJI_OK_GESTURE
        try:
            if hasattr(bot, "call_action"):
                await bot.call_action(
                    API_SET_MSG_EMOJI_LIKE,
                    message_id=message_id,
                    emoji_id=str(emoji_id),
                )
                return True
            if bot is not None:
                await bot.set_msg_emoji_like(
                    message_id=message_id, emoji_id=str(emoji_id)
                )
                return True
        except Exception as exc:
            logger.debug(f"[{PLUGIN_NAME}] 贴表情失败({message_id}): {exc}")
        return False

    async def _mark_text(self, event: Any) -> bool:
        """回复一条 ✅ 文本作为转发回执。"""
        try:
            from astrbot.api.event import MessageChain
            from astrbot.api.message_components import Plain

            chain = MessageChain(chain=[Plain(text=MARK_TEXT_OK)])
            await event.send(chain)
            return True
        except Exception as exc:
            logger.debug(f"[{PLUGIN_NAME}] 转发回执发送失败: {exc}")
            return False
