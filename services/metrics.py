"""运行指标统计器与 SSE 事件流发布机制。

负责：
1. 收集插件运行期间的各种计数（事件量、转发量、AI 问答、回声抑制、指令执行分布）。
2. 维护最近事件的内存环形队列（Ring Buffer），供 Web 前端拉取事件历史。
3. 提供 SSE（Server-Sent Events）订阅/发布（Pub/Sub）机制，向已连接的前端实时推送事件。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricEventItem:
    """环形缓冲区中的单条事件记录。"""

    id: int
    timestamp: float
    event_type: str
    server_name: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "server_name": self.server_name,
            "summary": self.summary,
            "details": self.details,
        }


class MetricsCollector:
    """全局指标收集与事件发布中心。"""

    def __init__(self, max_history: int = 200) -> None:
        self.max_history = max_history
        self._start_time = time.time()
        self._counter_id = 0

        # 游戏 → 外部方向的事件（来自鹊桥推送）
        self.events_by_type: dict[str, int] = {
            "chat": 0,
            "join": 0,
            "quit": 0,
            "death": 0,
            "achievement": 0,
            "command": 0,
            # 外部 → 游戏方向：网页仪表盘广播（broadcast_message）
            "relay": 0,
        }

        self.relayed_to_ast_total = 0
        self.relayed_to_mc_total = 0
        self.echo_suppressed_total = 0
        self.ai_chat_total = 0
        self.ai_chat_success_total = 0
        self.ai_chat_failed_total = 0

        self.cmd_executed_by_channel: dict[str, int] = {
            "queqiao": 0,
            "direct": 0,
            "failed": 0,
        }

        self.images_relayed_total = 0

        # 按服务器维度的事件计数，供仪表盘「单服务器标签页」展示各自互通事件数。
        # _events_by_server 只统计 events_by_type 内的事件（chat/join/relay 等，
        # 与全局口径一致，不含 echo/ai 等辅助事件），_relay_to_mc_by_server 单独
        # 统计「群/外部 → 游戏」的转发量，两者合并才是该服务器的「累计互通事件」。
        self._events_by_server: dict[str, int] = {}
        self._relay_to_mc_by_server: dict[str, int] = {}

        self._history: deque[MetricEventItem] = deque(maxlen=max_history)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def record_event(
        self,
        event_type: str,
        server_name: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> MetricEventItem:
        """记录一条事件并广播给所有 SSE 订阅者。"""
        self._counter_id += 1
        item = MetricEventItem(
            id=self._counter_id,
            timestamp=time.time(),
            event_type=event_type,
            server_name=server_name,
            summary=summary,
            details=details or {},
        )
        self._history.append(item)

        if event_type in self.events_by_type:
            self.events_by_type[event_type] += 1
            if server_name:
                self._events_by_server[server_name] = (
                    self._events_by_server.get(server_name, 0) + 1
                )

        self.broadcast_event(item.to_dict())
        return item

    def record_relay_to_ast(self, server_name: str, count: int = 1) -> None:
        self.relayed_to_ast_total += count

    def record_relay_to_mc(self, server_name: str, count: int = 1) -> None:
        self.relayed_to_mc_total += count
        if server_name:
            self._relay_to_mc_by_server[server_name] = (
                self._relay_to_mc_by_server.get(server_name, 0) + count
            )

    def record_echo_suppressed(self, server_name: str, content: str) -> None:
        self.echo_suppressed_total += 1
        self.record_event(
            "echo",
            server_name,
            f"已拦截回声: {content[:40]}...",
            {"content": content},
        )

    def record_ai_chat(
        self,
        server_name: str,
        player_name: str,
        question: str,
        success: bool,
    ) -> None:
        self.ai_chat_total += 1
        if success:
            self.ai_chat_success_total += 1
        else:
            self.ai_chat_failed_total += 1

        self.record_event(
            "ai",
            server_name,
            f"[{player_name}] AI提问: {question[:30]}",
            {"player": player_name, "question": question, "success": success},
        )

    def record_command_execution(
        self,
        server_name: str,
        command: str,
        channel: str | None,
    ) -> None:
        if channel == "queqiao":
            self.cmd_executed_by_channel["queqiao"] += 1
        elif channel == "direct":
            self.cmd_executed_by_channel["direct"] += 1
        else:
            self.cmd_executed_by_channel["failed"] += 1

    def record_image_relayed(self, count: int = 1) -> None:
        self.images_relayed_total += count

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """创建一个新的 SSE 订阅队列。"""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """移除已断开的订阅队列。"""
        self._subscribers.discard(queue)

    def broadcast_event(self, event_data: dict[str, Any]) -> None:
        """异步非阻塞推送事件到各个订阅者。"""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event_data)
                except Exception:
                    pass

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取最近事件列表（按从新到旧排序）。"""
        items = list(self._history)
        if limit > 0:
            items = items[-limit:]
        items.reverse()
        return [item.to_dict() for item in items]

    def get_server_event_count(self, server_name: str) -> int:
        """获取单台服务器的累计互通事件数（事件计数 + 外部→游戏转发量）。"""
        if not server_name:
            return 0
        return self._events_by_server.get(server_name, 0) + self._relay_to_mc_by_server.get(
            server_name, 0
        )

    def get_stats(self) -> dict[str, Any]:
        """获取全局聚合统计数据。"""
        uptime = int(time.time() - self._start_time)
        # 累计互通事件 = 游戏 → 外部（事件类型计数，含网页广播 relay）
        #              + 外部 → 游戏（群 → 游戏转发量 relayed_to_mc_total）
        # 双向都计，避免「发消息进游戏数字不涨」的困惑；
        # relayed_to_ast 是 chat 事件的转发子集，不计入以免重复计数。
        total_events = (
            sum(self.events_by_type.values()) + self.relayed_to_mc_total
        )
        # 按服务器拆分同一口径的事件数，供仪表盘单服务器标签页展示
        events_by_server = dict(self._events_by_server)
        for name, count in self._relay_to_mc_by_server.items():
            events_by_server[name] = events_by_server.get(name, 0) + count
        return {
            "uptime_seconds": uptime,
            "total_events": total_events,
            "events_by_type": dict(self.events_by_type),
            "events_by_server": events_by_server,
            "relayed_to_ast_total": self.relayed_to_ast_total,
            "relayed_to_mc_total": self.relayed_to_mc_total,
            "echo_suppressed_total": self.echo_suppressed_total,
            "ai_chat_total": self.ai_chat_total,
            "ai_chat_success_total": self.ai_chat_success_total,
            "ai_chat_failed_total": self.ai_chat_failed_total,
            "cmd_executed_by_channel": dict(self.cmd_executed_by_channel),
            "images_relayed_total": self.images_relayed_total,
            "active_sse_subscribers": len(self._subscribers),
        }
