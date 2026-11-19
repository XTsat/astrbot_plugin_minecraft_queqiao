"""游戏内 AI 对话的会话（UMO）与上下文管理。

游戏内聊天走鹊桥 WS，不经过 AstrBot 的事件管道，因此 AstrBot 的
`conversation_manager` 既不会自动读取也不会自动写入上下文。这里补上这一段：
按配置挑一个 UMO，读它当前对话的历史、调完模型再把这一问一答写回去——
于是游戏内 AI 也具备「记住之前聊过什么」以及 AstrBot `/new` 的语义。

三种会话归属（`ai_session_mode`，见 `core/constants.py`）：
- `server`：每台服务器一个合成 UMO，各服上下文独立、不与群聊共享；
- `group` ：复用该服务器第一个目标会话的 UMO，与群共用上下文与人格；
- `player`：每个玩家一个合成 UMO，多人同服时彼此隔离。
"""

import json
from typing import Any

from astrbot.api import logger

from ..core.constants import (
    AI_SESSION_MODE_GROUP,
    AI_SESSION_MODE_PLAYER,
    PLUGIN_NAME,
)
from ..core.models_config import ServerConfig

# 合成 UMO 的消息类型段：每服 / 每玩家都按群会话形态存，避免与真实私聊混淆
_SYNTHETIC_MESSAGE_TYPE = "GroupMessage"
# 玩家 UMO 在拿不到 uuid（原版端只给 nickname）时退化为昵称
_PLAYER_UMO_PREFIX = "player_"


def build_server_umo(server_name: str) -> str:
    """每台服务器一个合成 UMO（`server` 模式）。"""
    return f"{PLUGIN_NAME}:{_SYNTHETIC_MESSAGE_TYPE}:server_{server_name}"


def build_player_umo(server_name: str, player_key: str) -> str:
    """每个玩家一个合成 UMO（`player` 模式），按服务器再隔离一层。"""
    return (
        f"{PLUGIN_NAME}:{_SYNTHETIC_MESSAGE_TYPE}:"
        f"{_PLAYER_UMO_PREFIX}{server_name}_{player_key}"
    )


def resolve_session_umo(
    config: ServerConfig, server_name: str, player_key: str
) -> str:
    """按配置选出本次 AI 对话使用的 UMO。

    `group` 模式下该服务器没配目标会话时退回 `server` 模式：没有群可复用，
    继续按群 UMO 读写只会凭空造出一个永远不会被 `/new` 影响的会话。
    """
    mode = config.ai_session_mode
    if mode == AI_SESSION_MODE_GROUP and config.target_sessions:
        return config.target_sessions[0]
    if mode == AI_SESSION_MODE_PLAYER:
        return build_player_umo(server_name, player_key or "unknown")
    return build_server_umo(server_name)


def truncate_history(history: list[dict], turns: int) -> list[dict]:
    """把历史裁到最近 N 轮（一问一答为一轮）。

    `turns <= 0` 表示不限制。裁剪后若首条不是 user，说明切在了半轮上，
    继续往后丢到第一条 user 为止——与 AstrBot 自己的截断器一致，
    避免把 assistant 的应答当成开场消息发给模型。
    """
    trimmed = history if turns <= 0 else history[-turns * 2 :]
    if len(trimmed) == len(history):
        # 没有发生裁剪时不动原列表，但仍清掉历史里本来就存在的半轮残段
        trimmed = list(trimmed)
    while trimmed and trimmed[0].get("role") != "user":
        trimmed.pop(0)
    return trimmed


class AiSessionStore:
    """包一层 AstrBot 的 conversation_manager，供游戏内 AI 读写上下文。"""

    def __init__(self, context: Any) -> None:
        self.context = context

    # ---- 能力探测 ----

    @property
    def _manager(self) -> Any:
        return getattr(self.context, "conversation_manager", None)

    @property
    def available(self) -> bool:
        """旧版 AstrBot 可能没有会话管理器；缺失时退化为单轮对话。"""
        return self._manager is not None

    # ---- 会话 ----

    async def _current_cid(self, umo: str) -> str | None:
        manager = self._manager
        try:
            return await manager.get_curr_conversation_id(umo)
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 读取会话当前对话失败({umo}): {exc}")
            return None

    async def ensure_conversation(self, umo: str) -> str | None:
        """取当前对话 ID，没有就新建一个。失败返回 None。"""
        manager = self._manager
        if manager is None:
            return None
        cid = await self._current_cid(umo)
        if cid:
            conversation = await self._get_conversation(umo, cid)
            if conversation is not None:
                return cid
        return await self.new_conversation(umo)

    async def new_conversation(self, umo: str, persona_id: str = "") -> str | None:
        """新建对话并切换过去（语义同 AstrBot `/new`）。"""
        manager = self._manager
        if manager is None:
            return None
        platform_id = umo.split(":", 1)[0]
        try:
            return await manager.new_conversation(
                umo, platform_id, persona_id=persona_id or None
            )
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 新建会话失败({umo}): {exc}")
            return None

    async def _get_conversation(self, umo: str, cid: str) -> Any:
        manager = self._manager
        try:
            return await manager.get_conversation(umo, cid)
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 读取对话失败({umo}/{cid}): {exc}")
            return None

    async def load_history(self, umo: str, cid: str) -> list[dict]:
        """读取对话历史；损坏的 JSON 视为空历史（不阻塞本次提问）。"""
        conversation = await self._get_conversation(umo, cid)
        if conversation is None:
            return []
        raw = getattr(conversation, "history", "") or ""
        try:
            history = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            logger.warning(f"[{PLUGIN_NAME}] 对话历史 JSON 解析失败({umo}/{cid})")
            return []
        if not isinstance(history, list):
            return []
        return [item for item in history if isinstance(item, dict)]

    async def conversation_persona_id(self, umo: str, cid: str) -> str:
        """对话上绑定的人格 ID（AstrBot 每个对话可单独指定人格）。"""
        conversation = await self._get_conversation(umo, cid)
        if conversation is None:
            return ""
        return str(getattr(conversation, "persona_id", "") or "").strip()

    async def append_turn(
        self,
        umo: str,
        cid: str,
        history: list[dict],
        question: str,
        answer: str,
        turns: int,
    ) -> None:
        """把这一问一答写回对话历史（按 `turns` 裁剪后落库）。"""
        manager = self._manager
        if manager is None:
            return
        updated = list(history)
        updated.append({"role": "user", "content": question})
        updated.append({"role": "assistant", "content": answer})
        updated = truncate_history(updated, turns)
        try:
            await manager.update_conversation(umo, cid, history=updated)
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 写入对话历史失败({umo}/{cid}): {exc}")

    async def clear_history(self, umo: str) -> bool:
        """清空当前对话历史（语义同 AstrBot `/reset`）。"""
        manager = self._manager
        if manager is None:
            return False
        cid = await self._current_cid(umo)
        if not cid:
            return False
        try:
            await manager.update_conversation(umo, cid, history=[])
            return True
        except Exception as exc:
            logger.warning(f"[{PLUGIN_NAME}] 清空对话历史失败({umo}/{cid}): {exc}")
            return False
