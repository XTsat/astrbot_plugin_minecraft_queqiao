"""Web API 控制器：提供给 AstrBot 插件 Pages 的后端 Web API。

基于 AstrBot 的 `context.register_web_api()` 机制，配合 `astrbot.api.web`
处理 HTTP 请求与 SSE 实时事件流。
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ..core.constants import (
    DEFAULT_CHAT_FORMAT,
    DEFAULT_CLIENT_ORIGIN,
    DEFAULT_IMAGE_UPLOAD_TIMEOUT,
    DEFAULT_REVERSE_HOST,
    DEFAULT_REVERSE_PATH,
    DEFAULT_REVERSE_PORT,
    DEFAULT_TERMINAL_DAYS,
    DEFAULT_WS_URL,
    PLUGIN_NAME,
    TERMINAL_DAYS_MAX,
    TERMINAL_DAYS_MIN,
)
from ..core.queqiao_client import reverse_servers_snapshot
from .host_mem import correct_physical_memory
from .metrics import MetricsCollector

# 面板可管理的服务器条目字段（conf 中 mc_servers 的子集，其余字段回落 schema 默认值）
_SERVER_TEMPLATE_KEY = "server"

# 图床条目字段白名单（conf 中 image_upload_services 条目可被面板修改的字段；
# 与 _conf_schema.json 各模板 items 键集合一致，其余字段回落 schema 默认值）
_IMAGE_ENTRY_FIELDS = (
    "enabled",
    "name",
    "host",
    "port",
    "base_url",
    "upload_url",
    "token",
    "response",
    "file_field",
    "headers",
    "form_fields",
)
_IMAGE_TEMPLATE_KEY_BUILTIN = "builtin_http"
_IMAGE_TEMPLATE_KEY_CUSTOM = "custom"
# 与 services/image_bed.py 的 VALID_RESPONSE_KINDS 保持同值
_IMAGE_RESPONSE_KINDS = ("text", "json")


def _as_bool(value: Any, default: bool) -> bool:
    """防御式布尔解析：WebUI/JSON 里可能是字符串 "true"/"false"。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off", ""):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_int(value: Any, default: int) -> int:
    """防御式整数解析：非数字回落默认值。"""
    if isinstance(value, bool):
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_int_clamped(value: Any, default: int, lo: int, hi: int) -> int:
    """整数解析 + 区间钳制（0~30 之类的天数）。非法值回落默认。"""
    return max(lo, min(hi, _as_int(value, default)))


def _as_str_list(value: Any) -> list[str]:
    """把目标会话等字段规整为字符串列表（兼容单值/字符串/逗号分隔）。"""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _schema_default(spec: Any) -> Any:
    """按 ``_conf_schema.json`` 的字段规格推导默认值。

    与仪表盘前端新建服务器的默认值推导同语义，保证「面板新建服务器」
    写出的条目结构与 AstrBot WebUI 新增的条目完全一致。
    """
    if not isinstance(spec, dict):
        return None
    kind = spec.get("type")
    default = spec.get("default")
    if kind == "bool":
        return bool(default)
    if kind == "int":
        return default if isinstance(default, int) and not isinstance(default, bool) else 0
    if kind == "string":
        return default if isinstance(default, str) else ""
    if kind == "list":
        return list(default) if isinstance(default, list) else []
    if kind == "object":
        items = spec.get("items")
        if not isinstance(items, dict):
            return {}
        return {key: _schema_default(sub) for key, sub in items.items()}
    return None

try:
    from astrbot.api.web import error_response, json_response, request, stream_response
except ImportError:

    def json_response(data: Any, status_code: int = 200) -> Any:
        return {"data": data, "status_code": status_code}

    def error_response(message: str, status_code: int = 400) -> Any:
        return {"error": message, "status_code": status_code}

    def stream_response(content: Any, content_type: str = "text/event-stream") -> Any:
        return content

    class _MockRequest:
        query: dict[str, Any] = {}

        async def json(self, default: Any = None) -> Any:
            return default if default is not None else {}

    request = _MockRequest()  # type: ignore

if TYPE_CHECKING:
    from astrbot.api.star import Context
    from ..core.models_config import ServerConfig
    from ..core.server_manager import ServerManager
    from ..main import MinecraftQueQiaoPlugin
    from .binding import BindingService
    from .image_bed import ImageBedUploaderGroup
    from .monitor import MonitorCollector
    from .panel_prefs import PanelPrefsStore
    from .terminal_log import TerminalLogStore


class WebApiController:
    """提供给 AstrBot 插件 Pages 的后端 Web API 控制器。"""

    def __init__(
        self,
        context: Context,
        server_manager: ServerManager,
        binding_service: BindingService,
        image_bed: ImageBedUploaderGroup,
        metrics: MetricsCollector,
        configs: dict[str, ServerConfig],
        terminal_logs: TerminalLogStore | None = None,
        monitor: "MonitorCollector | None" = None,
        panel_prefs: "PanelPrefsStore | None" = None,
        plugin: "MinecraftQueQiaoPlugin | None" = None,
    ) -> None:
        self.context = context
        self.server_manager = server_manager
        self.binding_service = binding_service
        self.image_bed = image_bed
        self.metrics = metrics
        self.configs = configs
        self.terminal_logs = terminal_logs
        self.monitor = monitor
        self.panel_prefs = panel_prefs
        self.plugin = plugin

    def register_routes(self) -> None:
        """向 AstrBot Context 注册所有 Web API 路由。"""
        if not hasattr(self.context, "register_web_api"):
            logger.warning(f"[{PLUGIN_NAME}] 当前 Context 不支持 register_web_api")
            return

        routes = [
            ("/stats", self.get_stats, ["GET"], "获取插件运行全局统计指标"),
            ("/servers", self.get_servers, ["GET"], "获取所有服务器列表与连接状态"),
            (
                "/server/<server_name>/status",
                self.get_server_status,
                ["GET"],
                "获取指定服务器详细状态",
            ),
            (
                "/server/<server_name>/players",
                self.get_server_players,
                ["GET"],
                "获取指定服务器在线玩家列表",
            ),
            (
                "/server/<server_name>/command",
                self.execute_command,
                ["POST"],
                "在指定服务器执行控制台指令",
            ),
            (
                "/server/<server_name>/broadcast",
                self.broadcast_message,
                ["POST"],
                "向指定服务器广播聊天",
            ),
            (
                "/server/<server_name>/action",
                self.execute_action,
                ["POST"],
                "在指定服务器执行快捷玩家动作",
            ),
            ("/events", self.get_events, ["GET"], "获取最近事件历史"),
            ("/events/stream", self.stream_events, ["GET"], "SSE 实时事件流"),
            ("/bindings", self.get_bindings, ["GET"], "获取账号绑定列表"),
            ("/bindings/set", self.set_binding, ["POST"], "添加或修改账号绑定"),
            ("/bindings/delete", self.delete_binding, ["POST"], "删除账号绑定"),
            ("/terminal_logs", self.get_terminal_logs, ["GET"], "获取某台服务器的持久化终端日志"),
            ("/terminal_logs/clear", self.clear_terminal_logs, ["POST"], "清空某台服务器的持久化终端日志"),
            ("/image_bed/status", self.get_image_bed_status, ["GET"], "获取图床服务状态"),
            ("/image_bed/test", self.test_image_bed_upload, ["POST"], "用内置测试图跑一次完整上传链"),
            ("/image_bed/switch", self.switch_image_bed, ["POST"], "保存图床总开关与上传超时（局部生效，不断连接）"),
            (
                "/image_bed/templates",
                self.get_image_bed_templates,
                ["GET"],
                "列出图床模板与各模板字段默认值（供面板新建表单预填）",
            ),
            (
                "/config/full",
                self.get_config_full,
                ["GET"],
                "获取完整插件配置与配置 Schema（供 dashboard 配置视图表单渲染）",
            ),
            (
                "/config/save",
                self.save_config_full,
                ["POST"],
                "保存完整插件配置并热重载（dashboard 配置视图保存链路）",
            ),
            (
                "/config/image_bed",
                self.get_config_image_bed,
                ["GET"],
                "列出配置中的图床条目原始数据（含未启用，供面板表单编辑）",
            ),
            (
                "/config/image_bed/create",
                self.create_config_image_bed,
                ["POST"],
                "新建图床条目并局部生效",
            ),
            (
                "/config/image_bed/update",
                self.update_config_image_bed,
                ["POST"],
                "修改图床条目或启用状态并局部生效",
            ),
            (
                "/config/image_bed/delete",
                self.delete_config_image_bed,
                ["POST"],
                "删除图床条目并局部生效",
            ),
            ("/reverse/servers", self.get_reverse_servers, ["GET"], "反向共享 WS 服务端状态"),
            (
                "/config/servers",
                self.get_config_servers,
                ["GET"],
                "列出配置中的服务器条目（含未启用）",
            ),
            (
                "/config/server/create",
                self.create_config_server,
                ["POST"],
                "新建服务器条目并热重载生效",
            ),
            (
                "/config/server/update",
                self.update_config_server,
                ["POST"],
                "修改服务器条目或启用状态并热重载生效",
            ),
            (
                "/config/server/delete",
                self.delete_config_server,
                ["POST"],
                "删除服务器条目并热重载生效",
            ),
            ("/panel/prefs", self.get_panel_prefs, ["GET"], "获取面板级偏好（长期存储）"),
            ("/panel/prefs", self.set_panel_prefs, ["POST"], "保存面板级偏好（长期存储）"),
        ]
        # 性能监控（TPS/延迟）路由：未注入 MonitorCollector 时（如旧测试桩）不注册
        if self.monitor is not None:
            routes.extend(
                [
                    (
                        "/monitor/status",
                        self.get_monitor_status,
                        ["GET"],
                        "获取全部服务器的性能监控状态（含最新采样）",
                    ),
                    (
                        "/monitor/<server_name>/series",
                        self.get_monitor_series,
                        ["GET"],
                        "获取某台服务器的监控时间序列与统计摘要",
                    ),
                    (
                        "/monitor/settings",
                        self.save_monitor_settings,
                        ["POST"],
                        "保存某台服务器的性能监控设置（启用/间隔/保留/指令）",
                    ),
                    (
                        "/monitor/<server_name>/sample",
                        self.sample_monitor,
                        ["POST"],
                        "立即对某台服务器执行一次采样（不等下一个采集间隔）",
                    ),
                    (
                        "/monitor/<server_name>/clear",
                        self.clear_monitor_data,
                        ["POST"],
                        "清空某台服务器的性能监控采样数据（不可恢复）",
                    ),
                ]
            )

        count = 0
        for path, handler, methods, desc in routes:
            full_path = f"/{PLUGIN_NAME}{path}"
            try:
                self.context.register_web_api(full_path, handler, methods, desc)
                count += 1
            except Exception as exc:
                logger.warning(
                    f"[{PLUGIN_NAME}] 注册 Web API 路由失败: {full_path}: {exc}"
                )
        logger.info(f"[{PLUGIN_NAME}] 已注册 {count} 个 Web API 路由")

    async def get_stats(self) -> Any:
        """获取插件运行统计。"""
        data = self.metrics.get_stats()
        all_instances = self.server_manager.all()
        data["total_servers"] = len(all_instances)
        data["connected_servers"] = sum(1 for inst in all_instances if inst.connected)
        # 连接层汇总：正在重试（断线且重连未达上限）/ 已放弃（达上限停止）
        reconnecting = 0
        exhausted = 0
        for inst in all_instances:
            stats = inst.client.runtime_stats
            if stats["reconnect_exhausted"]:
                exhausted += 1
            elif not inst.connected and stats["retry_count"] > 0:
                reconnecting += 1
        data["reconnecting_servers"] = reconnecting
        data["exhausted_servers"] = exhausted
        return json_response(data)

    async def get_servers(self) -> Any:
        """获取所有服务器列表及其连接状态，并附带各服务器的实时状态与在线玩家。

        查询参数 ``force=1``（仪表盘「手动刷新」按钮）：把已判定「鹊桥 RCON
        不可用」的服务器重置为未确认，重新探测一次——用户可能刚在鹊桥侧开启
        RCON。自动轮询不带该参数，避免向未开启 RCON 的鹊桥端反复发
        send_rcon_command、在 MC 控制台刷报错。
        """
        try:
            force_rcon = str(request.query.get("force", "")).strip().lower() in (
                "1", "true")
        except (AttributeError, ValueError, TypeError):
            force_rcon = False
        servers_info = []
        for server_name, config in self.configs.items():
            instance = self.server_manager.get(server_name)
            connected = instance.connected if instance else False
            direct_rcon_connected = (
                instance.rcon.connected if instance and instance.rcon else False
            )

            status_data = None
            players_data = None
            status_model = None
            if instance and connected:
                try:
                    status_model = await instance.get_status_model()
                    if status_model:
                        # 同机部署时用宿主机 MemAvailable 口径修正物理内存
                        # （鹊桥 used 把 page cache 计入，会常年显示接近满）
                        status_data = correct_physical_memory(
                            status_model.to_dict()
                        )
                except Exception as exc:
                    logger.warning(
                        f"[{PLUGIN_NAME}][{server_name}] 获取状态失败: {exc}"
                    )

                try:
                    # 复用已拉取的状态：避免同一轮请求对鹊桥重复发 get_status
                    plr = await instance.fetch_player_list(
                        force_rcon=force_rcon, status_model=status_model
                    )
                    if plr:
                        players_data = plr.to_dict()
                except Exception as exc:
                    logger.warning(
                        f"[{PLUGIN_NAME}][{server_name}] 获取玩家列表失败: {exc}"
                    )

            # 可用的 RCON 通道（必须由真实执行结果确认，不能仅凭 WS 连接判定）：
            # - 鹊桥 RCON：鹊桥 send_rcon_command 曾成功响应（fetch_player_list 的
            #   `list` 探测会在上方执行并更新 queqiao_rcon_ok）
            # - 直连 RCON：直连 RCON 客户端已建立连接
            rcon_channels: list[str] = []
            if instance and instance.queqiao_rcon_ok is True:
                rcon_channels.append("queqiao")
            if direct_rcon_connected:
                rcon_channels.append("direct")

            servers_info.append(
                {
                    "server_name": server_name,
                    "display_name": config.display_name,
                    "server_label": config.server_label,
                    "enabled": config.enabled,
                    "is_reverse": config.is_reverse,
                    "ws_url": "" if config.is_reverse else config.ws_url,
                    "reverse_port": config.reverse_port if config.is_reverse else None,
                    "connected": connected,
                    # 单服务器视图用：本次连接持续秒数与该服累计互通事件数
                    "connected_seconds": instance.connected_seconds if instance else 0,
                    "events_total": self.metrics.get_server_event_count(server_name),
                    # 连接层运行观测：重连次数/阶段/是否达上限/未决请求/超时计数/断开原因
                    "client": instance.client.runtime_stats if instance else None,
                    "rcon_fallback_enabled": config.rcon_fallback_enabled,
                    "rcon_connected": direct_rcon_connected,
                    "rcon_channels": rcon_channels,
                    "prefixes_conflict": config.prefixes_conflict,
                    "auto_forward_prefix": config.auto_forward_prefix,
                    "ai_chat_prefix": config.ai_chat_prefix,
                    "enable_ai_chat": config.enable_ai_chat,
                    "target_sessions_count": len(config.target_sessions),
                    "status": status_data,
                    "players": players_data,
                    # 性能监控摘要：当前生效设置（默认开启，仪表盘内可调）+ 最新采样等
                    "monitor": (
                        self.monitor.status(server_name)
                        if self.monitor is not None
                        else {"enabled": config.monitor_enabled}
                    ),
                }
            )
        return json_response({"servers": servers_info})

    async def get_server_status(self, server_name: str) -> Any:
        """获取指定服务器的实时 ServerStatus。"""
        instance = self.server_manager.get(server_name)
        if not instance:
            return error_response(f"服务器不存在: {server_name}", status_code=404)
        if not instance.connected:
            return error_response(f"服务器未连接: {server_name}", status_code=503)

        status = await instance.get_status_model()
        if not status:
            return error_response(
                "获取状态失败（可能服务端鹊桥版本 < v0.5.0 或请求超时）",
                status_code=500,
            )
        return json_response(correct_physical_memory(status.to_dict()))

    async def get_server_players(self, server_name: str) -> Any:
        """获取指定服务器的在线玩家列表。"""
        instance = self.server_manager.get(server_name)
        if not instance:
            return error_response(f"服务器不存在: {server_name}", status_code=404)

        result = await instance.fetch_player_list()
        return json_response(result.to_dict())

    async def execute_command(self, server_name: str) -> Any:
        """在指定服务器上执行控制台指令。"""
        instance = self.server_manager.get(server_name)
        if not instance:
            return error_response(f"服务器不存在: {server_name}", status_code=404)

        payload = await request.json(default={})
        command = str(payload.get("command", "")).strip()
        if not command:
            return error_response("指令内容不能为空", status_code=400)

        if command.startswith("/"):
            command = command[1:].strip()

        output, channel = await instance.execute_command_with_channel(command)
        self.metrics.record_command_execution(server_name, command, channel)
        if self.terminal_logs:
            self.terminal_logs.append(server_name, "cmd", f"/{command}")

        if output is None:
            if self.terminal_logs:
                self.terminal_logs.append(
                    server_name, "error", f"指令执行失败：通道不可用或执行超时 [/{command}]"
                )
            return error_response(
                f"指令执行失败：通道不可用或执行超时 [{command}]",
                status_code=500,
            )

        if self.terminal_logs:
            self.terminal_logs.append(server_name, "out", output)
        return json_response(
            {
                "server_name": server_name,
                "command": command,
                "output": output,
                "channel": channel,
            }
        )

    async def broadcast_message(self, server_name: str) -> Any:
        """向指定服务器广播文本。"""
        instance = self.server_manager.get(server_name)
        if not instance:
            return error_response(f"服务器不存在: {server_name}", status_code=404)
        if not instance.connected:
            return error_response(f"服务器未连接: {server_name}", status_code=503)

        payload = await request.json(default={})
        message = str(payload.get("message", "")).strip()
        color = str(payload.get("color", "white")).strip()
        if not message:
            return error_response("广播内容不能为空", status_code=400)

        success = await instance.client.broadcast(message, color=color)
        if not success:
            return error_response("广播失败", status_code=500)

        self.metrics.record_event(
            "relay",
            server_name,
            f"Web广播: {message[:30]}",
            {"message": message, "color": color},
        )
        if self.terminal_logs:
            self.terminal_logs.append(server_name, "broadcast", message)
        return json_response({"success": True})

    async def execute_action(self, server_name: str) -> Any:
        """执行快捷管理动作（kick, private_msg, title, actionbar, op, deop 等）。"""
        instance = self.server_manager.get(server_name)
        if not instance:
            return error_response(f"服务器不存在: {server_name}", status_code=404)

        payload = await request.json(default={})
        action = str(payload.get("action", "")).strip().lower()
        player = str(payload.get("player", "")).strip()

        if action == "kick":
            if not player:
                return error_response("玩家名不能为空", status_code=400)
            reason = str(payload.get("reason", "Kicked by admin")).strip()
            cmd = f"kick {player} {reason}"
            output = await instance.execute_command(cmd)
            if self.terminal_logs:
                self.terminal_logs.append(
                    server_name,
                    "system",
                    f"已踢出 {player}" if output is not None else f"踢出 {player} 失败",
                )
            return json_response({"success": output is not None, "output": output})

        if action == "op":
            if not player:
                return error_response("玩家名不能为空", status_code=400)
            cmd = f"op {player}"
            output = await instance.execute_command(cmd)
            if self.terminal_logs:
                self.terminal_logs.append(
                    server_name,
                    "system",
                    f"已设 {player} 为 OP" if output is not None else f"设置 {player} OP 失败",
                )
            return json_response({"success": output is not None, "output": output})

        if action == "deop":
            if not player:
                return error_response("玩家名不能为空", status_code=400)
            cmd = f"deop {player}"
            output = await instance.execute_command(cmd)
            if self.terminal_logs:
                self.terminal_logs.append(
                    server_name,
                    "system",
                    f"已取消 {player} 的 OP" if output is not None else f"取消 {player} OP 失败",
                )
            return json_response({"success": output is not None, "output": output})

        if action == "private_msg":
            if not player:
                return error_response("玩家名不能为空", status_code=400)
            msg = str(payload.get("message", "")).strip()
            if not msg:
                return error_response("私聊消息不能为空", status_code=400)
            success = await instance.client.send_private_message(
                message=msg, player_name=player
            )
            if self.terminal_logs:
                self.terminal_logs.append(
                    server_name,
                    "broadcast",
                    f"私聊 {player}: {msg}" if success else f"私聊 {player} 发送失败",
                )
            return json_response({"success": bool(success)})

        if action == "title":
            title = str(payload.get("title", "")).strip()
            subtitle = str(payload.get("subtitle", "")).strip()
            if not title:
                return error_response("Title 内容不能为空", status_code=400)
            success = await instance.client.send_title(title=title, subtitle=subtitle)
            if self.terminal_logs and success:
                self.terminal_logs.append(server_name, "system", f"发送 Title: {title}")
            return json_response({"success": bool(success)})

        if action == "actionbar":
            msg = str(payload.get("message", "")).strip()
            if not msg:
                return error_response("ActionBar 消息不能为空", status_code=400)
            success = await instance.client.send_actionbar(msg)
            if self.terminal_logs and success:
                self.terminal_logs.append(server_name, "system", f"发送 ActionBar: {msg}")
            return json_response({"success": bool(success)})

        return error_response(f"未知操作: {action}", status_code=400)

    async def get_events(self) -> Any:
        """获取最近事件历史。"""
        limit = 50
        try:
            limit = int(request.query.get("limit", 50))
        except (AttributeError, ValueError, TypeError):
            pass
        return json_response({"events": self.metrics.get_history(limit=limit)})

    async def stream_events(self) -> Any:
        """SSE 实时事件流推送。"""
        queue = self.metrics.subscribe()

        async def _event_generator():
            try:
                yield f"data: {json.dumps({'event_type': 'connected', 'summary': 'SSE连接已建立'})}\n\n"
                while True:
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=20.0)
                        yield f"data: {json.dumps(data)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                self.metrics.unsubscribe(queue)

        return stream_response(_event_generator(), content_type="text/event-stream")

    async def get_terminal_logs(self) -> Any:
        """获取某台服务器的持久化终端日志（旧 → 新）。

        `days` 查询参数控制返回最近几天的分片：缺省默认 **2**（今天+昨天，
        避免跨月/长历史一次性加载过多）；`0` 表示全部保留分片；正整数为
        最近 N 天（含当天）。
        """
        try:
            server_name = str(request.query.get("server", "")).strip()
        except (AttributeError, ValueError, TypeError):
            server_name = ""
        if not server_name:
            return error_response("缺少 server 参数", status_code=400)
        raw_days = ""
        try:
            raw_days = str(request.query.get("days", "")).strip()
        except (AttributeError, ValueError, TypeError):
            raw_days = ""
        if raw_days == "":
            days: int | None = DEFAULT_TERMINAL_DAYS
        else:
            try:
                days = int(raw_days)
            except ValueError:
                days = DEFAULT_TERMINAL_DAYS
            if days < 0:
                days = DEFAULT_TERMINAL_DAYS
            # 0 表示全部保留分片；正整数取最近 N 天
            days = days if days > 0 else None
        logs = (
            self.terminal_logs.get(server_name, days=days)
            if self.terminal_logs
            else []
        )
        return json_response({"server": server_name, "days": days, "logs": logs})

    async def clear_terminal_logs(self) -> Any:
        """清空某台服务器的持久化终端日志（仅「清屏」按钮调用）。"""
        payload = await request.json(default={})
        server_name = str(payload.get("server", "")).strip()
        if not server_name:
            return error_response("缺少 server 参数", status_code=400)
        if self.terminal_logs:
            self.terminal_logs.clear(server_name)
        return json_response({"success": True, "server": server_name})

    async def get_bindings(self) -> Any:
        """获取所有账号绑定。"""
        bindings = self.binding_service.all_bindings()
        items = [{"umo": k, "game_id": v} for k, v in bindings.items()]
        return json_response({"bindings": items, "count": len(items)})

    async def set_binding(self) -> Any:
        """添加或修改单个账号绑定。"""
        payload = await request.json(default={})
        umo = str(payload.get("umo", "")).strip()
        game_id = str(payload.get("game_id", "")).strip()
        if not (umo and game_id):
            return error_response("umo 与 game_id 均不能为空", status_code=400)

        self.binding_service.bind(umo, game_id)
        return json_response({"success": True, "umo": umo, "game_id": game_id})

    async def delete_binding(self) -> Any:
        """删除单个账号绑定。"""
        payload = await request.json(default={})
        umo = str(payload.get("umo", "")).strip()
        if not umo:
            return error_response("umo 不能为空", status_code=400)

        removed = self.binding_service.unbind(umo)
        return json_response({"success": removed, "umo": umo})

    async def get_image_bed_status(self) -> Any:
        """获取图床服务的运行状态。

        始终保留 `enabled / status_text / service_names / uploaders_count`
        四个既有字段（向后兼容），在此基础上增补 `timeout`（根级上传超时）、
        `items`（条目生效态视图，含未生效原因）、`builtin_running`（内置
        HTTP 服务的真实监听状态）。
        """
        master_enabled = _as_bool(
            self.plugin.config.get("enable_image_upload") if self.plugin is not None else None,
            False,
        )
        return json_response(
            {
                "enabled": self.image_bed.enabled,
                "status_text": self.image_bed.status_text,
                "service_names": self.image_bed.service_names,
                "uploaders_count": len(self.image_bed.uploaders),
                "timeout": self._image_bed_timeout(),
                "items": self._image_bed_items(master_enabled=master_enabled),
                "builtin_running": self.image_bed.builtin_status(),
            }
        )

    async def get_image_bed_templates(self) -> Any:
        """返回图床模板清单与各模板的字段默认值（供面板新建表单预填）。

        数据源为 ``_conf_schema.json`` 的 ``image_upload_services.templates``；
        每模板给出 ``{name, hint, defaults}``，``defaults`` 用
        ``_schema_default()`` 逐键推导，与 ``_new_image_entry`` 生成的新条目
        默认值完全一致。面板选模板后即可把这些默认值回填进表单。
        """
        templates = (
            (self._read_schema().get("image_upload_services") or {}).get("templates") or {}
        )
        result: dict[str, Any] = {}
        for key, template in templates.items():
            if not isinstance(template, dict):
                continue
            items = template.get("items")
            defaults: dict[str, Any] = {}
            if isinstance(items, dict):
                for field, spec in items.items():
                    defaults[field] = _schema_default(spec)
            result[key] = {
                "name": str(template.get("name") or key),
                "hint": str(template.get("hint") or ""),
                "defaults": defaults,
            }
        return json_response(result)

    async def test_image_bed_upload(self) -> Any:
        """用内置 1×1 测试图逐条跑上传链，返回成功 URL、失败原因与逐条明细。

        面板「🧪 测试上传」按钮调用：逐条测试每个条目，``results`` 给出
        每条的名称 / 是否可用 / 成功 URL 或失败原因 / 耗时（毫秒），
        ``ok`` 为是否有任一条目成功。请求体可带可选 ``index``：只测该
        conf 下标条目（未生效条目不耗时，直接给出未生效原因）。
        """
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)
        # 1×1 透明 PNG：唯一用途是验证上传链是否真的能走通
        try:
            import base64

            data = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            )
        except Exception:
            return error_response("测试图生成失败", status_code=500)
        master_enabled = _as_bool(
            self.plugin.config.get("enable_image_upload")
            if self.plugin is not None else None,
            False,
        )
        entries = self._conf_image_entries()
        index = payload.get("index")
        if index is not None:
            try:
                index = int(index)
            except (TypeError, ValueError):
                return error_response("index 需为整数", status_code=400)
            if index < 0 or index >= len(entries):
                return error_response(f"index 越界: {index}", status_code=400)
            entry = entries[index]
            if not isinstance(entry, dict):
                return error_response("该条目配置无效", status_code=400)
            kind = self._image_entry_kind(entry)
            name = self._image_entry_name(entry, kind)
            if not self._image_entry_active(entry, kind, master_enabled):
                reason = self._image_entry_reason(entry, kind, master_enabled) or "未生效"
                results = [{
                    "name": name, "ok": False, "url": "",
                    "elapsed_ms": 0, "reason": reason, "active": False,
                }]
                return json_response(
                    {
                        "ok": False,
                        "url": "",
                        "failures": [f"{name}: {reason}"],
                        "results": results,
                    }
                )
            target = self._image_uploader_for_index(entries, index, master_enabled)
            if target is None:
                return json_response(
                    {
                        "ok": False,
                        "url": "",
                        "failures": [f"{name}: 运行时实例不存在（服务未启动）"],
                        "results": [{
                            "name": name, "ok": False, "url": "",
                            "elapsed_ms": 0,
                            "reason": "运行时实例不存在（服务未启动）",
                            "active": True,
                        }],
                    }
                )
            url, reason, elapsed_ms = await self._run_uploader_test(target, data)
            results = [{
                "name": name, "ok": bool(url), "url": url or "",
                "elapsed_ms": elapsed_ms, "reason": reason, "active": True,
            }]
            failures = [item.strip() for item in reason.split("；") if item.strip()]
            return json_response(
                {"ok": bool(url), "url": url or "", "failures": failures, "results": results}
            )
        # 全量：逐条测试（含未生效条目，只报原因不耗时），每条都给出可用性
        results: list[dict[str, Any]] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            kind = self._image_entry_kind(entry)
            name = self._image_entry_name(entry, kind)
            if not self._image_entry_active(entry, kind, master_enabled):
                reason = self._image_entry_reason(entry, kind, master_enabled) or "未生效"
                results.append({
                    "name": name, "ok": False, "url": "",
                    "elapsed_ms": 0, "reason": reason, "active": False,
                })
                continue
            target = self._image_uploader_for_index(entries, i, master_enabled)
            if target is None:
                results.append({
                    "name": name, "ok": False, "url": "",
                    "elapsed_ms": 0, "reason": "运行时实例不存在（服务未启动）",
                    "active": True,
                })
                continue
            url, reason, elapsed_ms = await self._run_uploader_test(target, data)
            results.append({
                "name": name, "ok": bool(url), "url": url or "",
                "elapsed_ms": elapsed_ms, "reason": reason, "active": True,
            })
        any_ok = any(r["ok"] for r in results)
        first_url = next((r["url"] for r in results if r["ok"]), "")
        failures = [
            f"{r['name']}: {r['reason']}"
            for r in results if not r["ok"] and r["reason"]
        ]
        return json_response(
            {"ok": any_ok, "url": first_url, "failures": failures, "results": results}
        )

    def _image_uploader_for_index(
        self, entries: list[Any], index: int, master_enabled: bool
    ) -> Any:
        """把 conf 下标映射到运行时 uploaders 下标并返回对应实例。

        运行时 uploaders 顺序 = conf 中「生效条目」的顺序（跳过未启用/
        非法条目），因此统计 index 之前生效条目的数量即为 uploaders 下标；
        越界返回 None。
        """
        k = 0
        for e in entries[:index]:
            if not isinstance(e, dict):
                continue
            if self._image_entry_active(e, self._image_entry_kind(e), master_enabled):
                k += 1
        if k >= len(self.image_bed.uploaders):
            return None
        return self.image_bed.uploaders[k]

    async def _run_uploader_test(self, uploader: Any, data: bytes) -> tuple[str | None, str, int]:
        """实测一个 uploader，返回 (url, reason, 耗时毫秒)。"""
        start = time.monotonic()
        try:
            url, reason = await uploader.upload(data)
        except Exception as exc:  # 防御：个别图床异常不应中断全量测试
            url, reason = None, str(exc) or "未知异常"
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return url, reason, elapsed_ms

    async def switch_image_bed(self) -> Any:
        """保存根级图床开关与上传超时（局部生效，不重连）。

        请求体：``{"enable_image_upload": bool}`` 与 / 或
        ``{"image_upload_timeout": int≥1}``；仅显式出现的字段会被修改。
        """
        if self.plugin is None:
            return error_response("插件实例未注入，无法修改配置", status_code=503)
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)

        new_conf = dict(self.plugin.config)
        if "enable_image_upload" in payload:
            new_conf["enable_image_upload"] = _as_bool(payload["enable_image_upload"], False)
        if "image_upload_timeout" in payload:
            timeout = _as_int(payload["image_upload_timeout"], -1)
            if timeout < 1:
                return error_response("上传超时需为 ≥1 的整数", status_code=400)
            new_conf["image_upload_timeout"] = timeout
        if not any(key in payload for key in ("enable_image_upload", "image_upload_timeout")):
            return error_response("无可识别的图床开关字段", status_code=400)

        try:
            await self._persist_config(new_conf, reload=False)
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 更新图床根级配置失败")
            return error_response(f"更新图床根级配置失败: {exc}", status_code=500)
        logger.info(
            f"[{PLUGIN_NAME}] 面板更新图床开关/超时（免重连）: "
            f"{', '.join(key for key in ('enable_image_upload', 'image_upload_timeout') if key in payload)}"
        )
        return await self.get_image_bed_status()

    async def get_reverse_servers(self) -> Any:
        """获取反向模式下共享 WS 服务端的监听状态与挂载服务器列表。

        反向模式同端口多服务器共享一个 WS Server（按 x-self-name 路由），
        此处只读暴露 host/port/path/running 与挂载的 server_name 列表，
        便于排障端口占用、path 冲突与监听存活问题。
        """
        return json_response({"servers": reverse_servers_snapshot()})

    async def get_config_full(self) -> Any:
        """获取完整插件配置与配置 Schema（供 dashboard 配置视图表单渲染）。

        Schema 取自插件根目录 ``_conf_schema.json``；配置为内存中当前值
        （含尚未保存的运行时状态，与磁盘文件一致）。
        """
        conf = dict(self.plugin.config) if self.plugin is not None else {}
        schema = self._read_schema() or None
        data_dir = str(getattr(self.plugin, "_data_dir", "") or "")
        return json_response(
            {
                "conf": conf,
                "schema": schema,
                "active_servers": list(self.configs.keys()),
                "data_dir": data_dir,
            }
        )

    async def save_config_full(self) -> Any:
        """保存完整插件配置并热重载（dashboard 配置视图保存链路）。

        流程：备份当前配置到 ``data_dir/conf_backups/`` → AstrBot 原子写
        （utf-8-sig 保留 BOM）→ 调用插件热重载（断开旧连接、按新配置重建）。
        """
        if self.plugin is None:
            return error_response("插件实例未注入，无法保存配置", status_code=503)
        raw = await request.json(default=None)
        if not isinstance(raw, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)
        new_conf = raw.get("conf")
        if not isinstance(new_conf, dict):
            return error_response("conf 字段需为 JSON 对象", status_code=400)
        try:
            await self._persist_config(new_conf)
            return json_response(
                {
                    "saved": True,
                    "active_servers": list(self.configs.keys()),
                }
            )
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 保存配置失败")
            return error_response(f"保存配置失败: {exc}", status_code=500)

    def _read_schema(self) -> dict[str, Any]:
        """读取插件根目录的 ``_conf_schema.json``（读取失败返回空 dict）。"""
        try:
            candidate = Path(__file__).resolve().parent.parent / "_conf_schema.json"
            if candidate.is_file():
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            logger.warning(f"[{PLUGIN_NAME}] 读取 _conf_schema.json 失败", exc_info=True)
        return {}

    async def _write_config(self, new_conf: dict[str, Any]) -> None:
        """备份当前配置 → 原子落盘（utf-8-sig），不触发热重载。

        备份失败不阻断保存（磁盘满 / 权限异常时仍要让配置落盘）。
        """
        data_dir = Path(getattr(self.plugin, "_data_dir", "") or ".")
        bak_dir = data_dir / "conf_backups"
        try:
            bak_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d-%H%M%S")
            bak_dir.joinpath(f"{ts}.json").write_text(
                json.dumps(dict(self.plugin.config), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning(f"[{PLUGIN_NAME}] 配置备份失败（不阻断保存）", exc_info=True)
        await self.plugin.config.save_config_async(new_conf)

    async def _persist_config(
        self, new_conf: dict[str, Any], *, reload: bool = True
    ) -> None:
        """备份 → 落盘 → 生效（默认热重载，可走图床局部生效）。

        Pages 面板改配置的落盘链路：服务器条目增删改（``/config/server/*``）
        共用，保证行为一致；仅「不影响连接」的开关改动可走 ``_write_config``
        + 就地生效，见 update_config_server。
        ``reload=False`` 时改走 ``apply_image_bed_config()``：图床条目/开关
        的保存不触碰 MC 连接，避免全服重连抖动。
        """
        await self._write_config(new_conf)
        if reload:
            await self.plugin.reload_config()
        else:
            apply = getattr(self.plugin, "apply_image_bed_config", None)
            if callable(apply):
                await apply()
            else:
                await self.plugin.reload_config()

    # ---- 服务器条目管理（面板直接改 conf 里的 mc_servers） ----

    def _conf_server_entries(self) -> list[Any]:
        """当前内存配置里的 mc_servers 原始条目列表（含未启用条目）。"""
        if self.plugin is None:
            return []
        entries = self.plugin.config.get("mc_servers")
        if isinstance(entries, dict):  # 防御：误存成单项对象
            entries = [entries]
        return entries if isinstance(entries, list) else []

    def _conf_with_servers(self, entries: list[Any]) -> dict[str, Any]:
        """把替换后的条目列表合成一份完整配置（供落盘 + 热重载）。"""
        new_conf = dict(self.plugin.config)
        new_conf["mc_servers"] = entries
        return new_conf

    def _new_server_entry(self, template_key: str = _SERVER_TEMPLATE_KEY) -> dict[str, Any]:
        """按 schema 模板生成一份全新服务器条目（默认值全部取自 schema）。

        schema 缺失（异常环境）时退化为最小可用结构，保证新建功能不中断。
        """
        templates = (self._read_schema().get("mc_servers") or {}).get("templates") or {}
        template = templates.get(template_key) or templates.get(_SERVER_TEMPLATE_KEY)
        if not isinstance(template, dict):
            logger.warning(f"[{PLUGIN_NAME}] 未找到 mc_servers 模板，使用最小默认结构")
            return {
                "__template_key": _SERVER_TEMPLATE_KEY,
                "enabled": True,
                "target_sessions": [],
                "server": {
                    "server_name": "",
                    "display_name": "",
                    "ws_mode": "forward",
                    "ws_url": DEFAULT_WS_URL,
                    "reverse_host": DEFAULT_REVERSE_HOST,
                    "reverse_port": DEFAULT_REVERSE_PORT,
                    "reverse_path": DEFAULT_REVERSE_PATH,
                    "access_token": "",
                    "client_origin": DEFAULT_CLIENT_ORIGIN,
                },
            }
        entry: dict[str, Any] = {
            "__template_key": template_key if template_key in templates else _SERVER_TEMPLATE_KEY
        }
        items = template.get("items")
        if isinstance(items, dict):
            for key, spec in items.items():
                entry[key] = _schema_default(spec)
        entry.setdefault("enabled", True)
        return entry

    def _config_server_items(self) -> list[dict[str, Any]]:
        """把 conf 里的服务器条目整理成面板可用的结构（含未启用条目）。

        ``enabled`` 与 main 层跳过逻辑同口径（真值判定）：面板显示的
        「已启用」必须等于实际会被加载的条目，否则面板会说谎。
        """
        items: list[dict[str, Any]] = []
        for index, entry in enumerate(self._conf_server_entries()):
            if not isinstance(entry, dict):
                continue
            raw_server = entry.get("server")
            server = raw_server if isinstance(raw_server, dict) else {}
            server_name = str(server.get("server_name") or "").strip()
            display_name = str(server.get("display_name") or "").strip()
            ws_mode = str(server.get("ws_mode") or "forward").strip().lower()
            if ws_mode not in ("forward", "reverse"):
                ws_mode = "forward"
            instance = self.server_manager.get(server_name) if server_name else None
            items.append(
                {
                    "index": index,
                    "server_name": server_name,
                    "display_name": display_name,
                    "label": display_name or server_name or f"服务器 #{index + 1}",
                    "enabled": bool(entry.get("enabled", True)),
                    "ws_mode": ws_mode,
                    "ws_url": str(server.get("ws_url") or ""),
                    "reverse_host": str(server.get("reverse_host") or ""),
                    "reverse_port": _as_int(
                        server.get("reverse_port"), DEFAULT_REVERSE_PORT
                    ),
                    "reverse_path": str(server.get("reverse_path") or ""),
                    # 不返回 access_token 明文，只暴露「是否已设置」
                    "access_token_set": bool(str(server.get("access_token") or "").strip()),
                    "target_sessions": _as_str_list(entry.get("target_sessions")),
                    # AI 对话开关（每台服务器独立）：面板「功能设置」直接读写，
                    # 字段与 main 层 _match_ai_prefix / _handle_ai_chat 同源，
                    # 注意落在条目顶层（与 server 子对象平级，ServerConfig 读整条）
                    "enable_ai_chat": _as_bool(entry.get("enable_ai_chat"), True),
                    "ai_chat_prefix": str(entry.get("ai_chat_prefix") or ""),
                    # 互通终端加载天数（每台服务器独立，条目顶层；缺省回落默认）
                    "terminal_days": _as_int_clamped(
                        entry.get("terminal_days"), DEFAULT_TERMINAL_DAYS,
                        TERMINAL_DAYS_MIN, TERMINAL_DAYS_MAX,
                    ),
                    # 消息转发配置（面板「功能设置」读写）：message 子对象按
                    # ServerConfig.from_dict 同源读取，缺省值与 schema 默认一致
                    "message": self._message_view(entry),
                    "running": server_name in self.configs,
                    "connected": bool(instance.connected) if instance is not None else False,
                }
            )
        return items

    def _message_view(self, entry: Any) -> dict[str, Any]:
        """把条目 message 子对象整理成面板「功能设置」可直接回显的结构。

        缺失字段一律回落 schema 默认值（forward_chat_to_astrbot 开、
        其它开关关、格式用 DEFAULT_CHAT_FORMAT、前缀空），保证面板首次
        打开时显示的就是实际生效值。
        """
        raw_msg = entry.get("message") if isinstance(entry, dict) else None
        msg = raw_msg if isinstance(raw_msg, dict) else {}
        return {
            "forward_chat_to_astrbot": _as_bool(msg.get("forward_chat_to_astrbot"), True),
            "forward_chat_format": str(msg.get("forward_chat_format") or DEFAULT_CHAT_FORMAT),
            "forward_join_leave_to_astrbot": _as_bool(
                msg.get("forward_join_leave_to_astrbot"), False
            ),
            "forward_death_to_astrbot": _as_bool(msg.get("forward_death_to_astrbot"), False),
            "forward_achievement_to_astrbot": _as_bool(
                msg.get("forward_achievement_to_astrbot"), False
            ),
            "forward_image_to_mc": _as_bool(msg.get("forward_image_to_mc"), False),
            "forward_image_from_mc": _as_bool(msg.get("forward_image_from_mc"), False),
            "auto_forward_prefix": str(msg.get("auto_forward_prefix") or ""),
        }

    def _find_server_entry(
        self, entries: list[Any], index: Any, server_name: str
    ) -> tuple[int, dict[str, Any]] | None:
        """按 index 优先、server_name 兜底定位条目，返回 (下标, 条目)。"""
        if isinstance(index, bool):
            index = None
        if isinstance(index, (int, str)) and str(index).strip() != "":
            try:
                position = int(str(index).strip())
            except ValueError:
                position = -1
            if 0 <= position < len(entries) and isinstance(entries[position], dict):
                return position, entries[position]
        if server_name:
            for position, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                raw_server = entry.get("server")
                server = raw_server if isinstance(raw_server, dict) else {}
                if str(server.get("server_name") or "").strip() == server_name:
                    return position, entry
        return None

    def _config_servers_response(self, **extra: Any) -> Any:
        """统一返回格式：最新条目列表 + 当前生效的服务器名。"""
        payload: dict[str, Any] = {
            "servers": self._config_server_items(),
            "active_servers": list(self.configs.keys()),
        }
        payload.update(extra)
        return json_response(payload)

    async def get_config_servers(self) -> Any:
        """列出 conf 中配置的全部服务器条目（含未启用条目）。

        仪表盘据此把「配置里存在但未启用」的服务器渲染成灰色卡片——
        它们在运行时不会建立连接（main 层跳过），此前在面板上完全
        不可见，只能靠改配置文件才能启用。
        """
        return self._config_servers_response()

    async def create_config_server(self) -> Any:
        """新建一台服务器条目并热重载生效。

        请求体：``{"server_name": "...", "display_name": "...",
        "ws_mode": "forward"|"reverse", "ws_url": "...", "reverse_port": 8080,
        "access_token": "...", "target_sessions": [...], "enabled": true}``。
        仅显式出现的字段覆盖 schema 默认值，其余字段按 ``_conf_schema.json``
        模板补齐，保证条目结构与 WebUI 新增的完全一致。
        """
        if self.plugin is None:
            return error_response("插件实例未注入，无法修改配置", status_code=503)
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)

        server_name = str(payload.get("server_name") or "").strip()
        if not server_name:
            return error_response("服务器名称不能为空", status_code=400)

        entries = copy.deepcopy(self._conf_server_entries())
        if self._find_server_entry(entries, None, server_name) is not None:
            return error_response(f"服务器名称已存在: {server_name}", status_code=400)

        entry = self._new_server_entry(str(payload.get("template_key") or _SERVER_TEMPLATE_KEY))
        raw_server = entry.get("server")
        server = raw_server if isinstance(raw_server, dict) else {}
        entry["server"] = server
        server["server_name"] = server_name
        if "display_name" in payload:
            server["display_name"] = str(payload.get("display_name") or "").strip()
        ws_mode = str(payload.get("ws_mode") or "").strip().lower()
        if ws_mode in ("forward", "reverse"):
            server["ws_mode"] = ws_mode
        for key in ("ws_url", "reverse_host", "reverse_path", "access_token", "client_origin"):
            if key in payload:
                server[key] = str(payload.get(key) or "")
        if "reverse_port" in payload:
            server["reverse_port"] = _as_int(
                payload.get("reverse_port"), DEFAULT_REVERSE_PORT
            )
        if "target_sessions" in payload:
            entry["target_sessions"] = _as_str_list(payload.get("target_sessions"))
        entry["enabled"] = _as_bool(payload.get("enabled"), True)

        entries.append(entry)
        try:
            await self._persist_config(self._conf_with_servers(entries))
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 新建服务器失败")
            return error_response(f"新建服务器失败: {exc}", status_code=500)
        logger.info(f"[{PLUGIN_NAME}] 面板新建服务器: {server_name}")
        return self._config_servers_response(saved=True, server_name=server_name)

    async def update_config_server(self) -> Any:
        """修改一台已配置服务器的字段 / 启用状态并热重载。

        请求体需带 ``index``（列表接口返回的下标）或 ``server_name`` 定位
        条目；其余字段仅「显式出现」才覆盖，避免前端漏传把已有配置清空。
        ``access_token`` 传空串表示清空，不传表示保持原值。
        """
        if self.plugin is None:
            return error_response("插件实例未注入，无法修改配置", status_code=503)
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)

        entries = copy.deepcopy(self._conf_server_entries())
        found = self._find_server_entry(
            entries, payload.get("index"), str(payload.get("server_name") or "").strip()
        )
        if found is None:
            return error_response("未找到对应的服务器条目", status_code=404)
        position, entry = found
        raw_server = entry.get("server")
        server = raw_server if isinstance(raw_server, dict) else {}
        entry["server"] = server

        # 改名：校验非空 + 不与其它条目重名（重名会让 main 层丢弃后者）
        new_name = str(payload.get("new_server_name") or "").strip()
        if new_name:
            other = self._find_server_entry(entries, None, new_name)
            if other is not None and other[0] != position:
                return error_response(f"服务器名称已存在: {new_name}", status_code=400)
            server["server_name"] = new_name
        if "display_name" in payload:
            server["display_name"] = str(payload.get("display_name") or "").strip()
        ws_mode = str(payload.get("ws_mode") or "").strip().lower()
        if ws_mode in ("forward", "reverse"):
            server["ws_mode"] = ws_mode
        for key in ("ws_url", "reverse_host", "reverse_path", "access_token", "client_origin"):
            if key in payload:
                server[key] = str(payload.get(key) or "")
        if "reverse_port" in payload:
            server["reverse_port"] = _as_int(
                payload.get("reverse_port"), DEFAULT_REVERSE_PORT
            )
        if "target_sessions" in payload:
            entry["target_sessions"] = _as_str_list(payload.get("target_sessions"))
        # AI 对话开关（面板「功能设置」）：字段位于条目顶层（与 server 子对象
        # 平级，main 层用整条 entry 构造 ServerConfig），不可写进 server 内
        if "enable_ai_chat" in payload:
            entry["enable_ai_chat"] = _as_bool(payload.get("enable_ai_chat"), True)
        if "ai_chat_prefix" in payload:
            entry["ai_chat_prefix"] = str(payload.get("ai_chat_prefix") or "").strip()
        if "terminal_days" in payload:
            # 互通终端加载天数（每台服务器独立，面板「功能设置」读写条目顶层）
            entry["terminal_days"] = _as_int_clamped(
                payload.get("terminal_days"), DEFAULT_TERMINAL_DAYS,
                TERMINAL_DAYS_MIN, TERMINAL_DAYS_MAX,
            )
        # 消息转发配置（面板「功能设置」）：message 子对象按「显式出现」键
        # 合并，漏传不清空。字段名与 ServerConfig 属性 / main 层软更新键一致
        message_payload = payload.get("message")
        if isinstance(message_payload, dict):
            raw_msg = entry.get("message")
            msg = raw_msg if isinstance(raw_msg, dict) else {}
            for key in (
                "forward_chat_to_astrbot",
                "forward_chat_format",
                "forward_join_leave_to_astrbot",
                "forward_death_to_astrbot",
                "forward_achievement_to_astrbot",
                "forward_image_to_mc",
                "forward_image_from_mc",
                "auto_forward_prefix",
            ):
                if key not in message_payload:
                    continue
                if key in ("forward_chat_to_astrbot", "forward_join_leave_to_astrbot",
                           "forward_death_to_astrbot", "forward_achievement_to_astrbot",
                           "forward_image_to_mc", "forward_image_from_mc"):
                    # 布尔键：字符串布尔（表单 / WebUI 可能传字符串）统一转真布尔
                    msg[key] = _as_bool(
                        message_payload[key],
                        True if key == "forward_chat_to_astrbot" else False,
                    )
                else:
                    msg[key] = str(message_payload[key] or "").strip()
            entry["message"] = msg
        if "enabled" in payload:
            entry["enabled"] = _as_bool(payload.get("enabled"), True)

        # 仅改动「不影响连接」的开关（面板「功能设置」的 AI 对话 / 消息转发
        # 项）时走落盘 + 就地生效：热重载会断开全部连接、重启监控采集与内置
        # 图床，代价与收益不匹配。定位键（index / server_name）不计入改动集合；
        # message 子对象展开为其内部转发键参与判定
        soft_keys = tuple(
            getattr(self.plugin, "SOFT_CONFIG_KEYS", ("enable_ai_chat", "ai_chat_prefix"))
        )
        changed_keys = set(payload) - {"index", "server_name"}
        if "message" in changed_keys:
            changed_keys.discard("message")
            if isinstance(payload.get("message"), dict):
                changed_keys.update(payload["message"].keys())
        soft_only = bool(changed_keys) and changed_keys.issubset(set(soft_keys))
        reloaded = True
        try:
            if soft_only:
                soft_fields: dict[str, Any] = {
                    key: payload[key] for key in soft_keys if key in payload
                }
                if isinstance(payload.get("message"), dict):
                    for key in soft_keys:
                        if key in payload["message"]:
                            soft_fields[key] = payload["message"][key]
                await self._write_config(self._conf_with_servers(entries))
                applier = getattr(self.plugin, "apply_soft_config", None)
                applied = bool(
                    callable(applier)
                    and applier(str(server.get("server_name") or ""), soft_fields)
                )
                if applied:
                    reloaded = False
                else:
                    # 运行时未命中（该服务器未启用 / 无实例）：补一次热重载，
                    # 保证磁盘配置与运行态一致
                    await self.plugin.reload_config()
            else:
                await self._persist_config(self._conf_with_servers(entries))
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 更新服务器配置失败")
            return error_response(f"更新服务器配置失败: {exc}", status_code=500)
        logger.info(
            f"[{PLUGIN_NAME}] 面板更新服务器: "
            f"{server.get('server_name') or '#' + str(position)}"
            f"{'' if reloaded else '（免重载）'}"
        )
        return self._config_servers_response(
            saved=True,
            server_name=str(server.get("server_name") or ""),
            reloaded=reloaded,
        )

    async def delete_config_server(self) -> Any:
        """删除一台服务器条目并热重载（连接随即断开，配置备份已留存）。"""
        if self.plugin is None:
            return error_response("插件实例未注入，无法修改配置", status_code=503)
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)

        entries = copy.deepcopy(self._conf_server_entries())
        found = self._find_server_entry(
            entries, payload.get("index"), str(payload.get("server_name") or "").strip()
        )
        if found is None:
            return error_response("未找到对应的服务器条目", status_code=404)
        position, entry = found
        raw_server = entry.get("server")
        server = raw_server if isinstance(raw_server, dict) else {}
        removed_name = str(server.get("server_name") or "").strip()

        entries.pop(position)
        try:
            await self._persist_config(self._conf_with_servers(entries))
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 删除服务器配置失败")
            return error_response(f"删除服务器配置失败: {exc}", status_code=500)
        logger.info(f"[{PLUGIN_NAME}] 面板删除服务器: {removed_name or '#' + str(position)}")
        return self._config_servers_response(saved=True, removed=removed_name)

    # ---- 图床条目管理（面板「图床」视图直接改 conf 里的 image_upload_services） ----

    def _conf_image_entries(self) -> list[Any]:
        """当前内存配置里的 image_upload_services 原始条目列表（含未启用条目）。"""
        if self.plugin is None:
            return []
        entries = self.plugin.config.get("image_upload_services")
        if isinstance(entries, dict):  # 防御：误存成单项对象
            entries = [entries]
        return entries if isinstance(entries, list) else []

    def _conf_with_image_entries(self, entries: list[Any]) -> dict[str, Any]:
        """把替换后的图床条目列表合成一份完整配置（只碰 image_upload_services 键）。"""
        new_conf = dict(self.plugin.config)
        new_conf["image_upload_services"] = entries
        return new_conf

    def _new_image_entry(self, template_key: str) -> dict[str, Any]:
        """按 schema 模板生成一份全新图床条目（默认值全部取自模板）。

        schema 缺失（异常环境）时退化为最小可用结构，保证新建功能不中断。
        """
        templates = (
            (self._read_schema().get("image_upload_services") or {}).get("templates") or {}
        )
        template = templates.get(template_key) or templates.get(_IMAGE_TEMPLATE_KEY_CUSTOM)
        if not isinstance(template, dict):
            logger.warning(f"[{PLUGIN_NAME}] 未找到图床模板 {template_key!r}，使用最小默认结构")
            return {
                "__template_key": _IMAGE_TEMPLATE_KEY_CUSTOM,
                "enabled": True,
                "name": "",
                "upload_url": "",
                "token": "",
                "response": "text",
                "file_field": "file",
                "headers": "",
                "form_fields": "",
            }
        entry: dict[str, Any] = {
            "__template_key": (
                template_key if template_key in templates else _IMAGE_TEMPLATE_KEY_CUSTOM
            )
        }
        items = template.get("items")
        if isinstance(items, dict):
            for key, spec in items.items():
                entry[key] = _schema_default(spec)
        entry.setdefault("enabled", True)
        return entry

    def _image_entry_kind(self, entry: Any) -> str:
        """判定图床条目类型：'builtin'（内置 HTTP 服务）或 'third_party'。

        与 main.py::_is_builtin_entry 同口径：__template_key 缺失时按字段
        特征兜底（带 base_url 且无 upload_url 视为内置条目）。
        """
        if not isinstance(entry, dict):
            return "third_party"
        key = str(entry.get("__template_key") or "").strip().lower()
        if key:
            return "builtin" if key == _IMAGE_TEMPLATE_KEY_BUILTIN else "third_party"
        return (
            "builtin"
            if bool(str(entry.get("base_url") or "").strip())
            and not str(entry.get("upload_url") or "").strip()
            else "third_party"
        )

    def _image_entry_reason(self, entry: Any, kind: str, master_enabled: bool) -> str:
        """生成条目未生效原因（与 main.py _setup_image_services 告警口径一致）。

        供面板回答「我配了却没生效，为什么」：总开关关 / 条目未启用 /
        内置条目 base_url 非法 / 第三方 upload_url 非法。
        """
        if not master_enabled:
            return "总开关未开启"
        if not _as_bool(entry.get("enabled"), True):
            return "条目未启用"
        if kind == "builtin":
            if not str(entry.get("base_url") or "").strip().startswith(("http://", "https://")):
                return "base_url 需为 http(s):// 开头（留空则不启动）"
        else:
            if not str(entry.get("upload_url") or "").strip().startswith(("http://", "https://")):
                return "upload_url 需为 http(s):// 开头"
            response = str(entry.get("response") or "text").strip().lower()
            if response not in _IMAGE_RESPONSE_KINDS:
                return "response 需为 text 或 json"
        return ""

    def _image_entry_active(self, entry: Any, kind: str, master_enabled: bool) -> bool:
        """条目是否已进入运行时上传链（总开关开 + 启用 + 配置合法）。"""
        return self._image_entry_reason(entry, kind, master_enabled) == ""

    def _image_entry_name(self, entry: Any, kind: str) -> str:
        """条目的展示名：配置的 name 优先，空时按类型给可读默认名。"""
        if not isinstance(entry, dict):
            return "未命名条目"
        name = str(entry.get("name") or "").strip()
        if name:
            return name
        if kind == "builtin":
            base_url = str(entry.get("base_url") or "")
            try:
                netloc = base_url.split("://", 1)[1].split("/", 1)[0]
            except IndexError:
                netloc = base_url
            return f"内置图片HTTP服务({netloc or '未配置'})"
        upload_url = str(entry.get("upload_url") or "")
        try:
            netloc = upload_url.split("://", 1)[1].split("/", 1)[0]
        except IndexError:
            netloc = upload_url
        return f"图床({netloc or '未配置'})"

    def _image_entry_detail(self, entry: Any, kind: str) -> str:
        """条目详情地址：内置条目显示 base_url，第三方显示 upload_url。"""
        if not isinstance(entry, dict):
            return ""
        return str(entry.get("base_url") or "") if kind == "builtin" else str(
            entry.get("upload_url") or ""
        )

    def _image_bed_timeout(self) -> int:
        """根级上传超时（conf 的 image_upload_timeout，缺省回落默认值）。"""
        if self.plugin is None:
            return DEFAULT_IMAGE_UPLOAD_TIMEOUT
        return max(1, _as_int(
            self.plugin.config.get("image_upload_timeout"), DEFAULT_IMAGE_UPLOAD_TIMEOUT
        ))

    def _image_bed_items(self, master_enabled: bool) -> list[dict[str, Any]]:
        """把 conf 里的图床条目整理成面板展示视图（含未生效原因）。

        ``active`` 与 main 层跳过逻辑同口径（真值判定 + 配置合法性）：
        面板显示的「已生效」必须等于实际会被加载的条目，否则面板会说谎。
        """
        items: list[dict[str, Any]] = []
        for index, entry in enumerate(self._conf_image_entries()):
            if not isinstance(entry, dict):
                continue
            kind = self._image_entry_kind(entry)
            items.append(
                {
                    "index": index,
                    "template_key": str(entry.get("__template_key") or "").strip()
                    or (
                        _IMAGE_TEMPLATE_KEY_BUILTIN
                        if kind == "builtin"
                        else _IMAGE_TEMPLATE_KEY_CUSTOM
                    ),
                    "name": self._image_entry_name(entry, kind),
                    "kind": kind,
                    "enabled": _as_bool(entry.get("enabled"), True),
                    "active": self._image_entry_active(entry, kind, master_enabled),
                    "detail": self._image_entry_detail(entry, kind),
                    "reason": self._image_entry_reason(entry, kind, master_enabled),
                }
            )
        return items

    def _config_image_items(self) -> list[dict[str, Any]]:
        """conf 里的图床条目原始数据（含未启用，供面板表单编辑回显）。"""
        items: list[dict[str, Any]] = []
        for index, entry in enumerate(self._conf_image_entries()):
            if not isinstance(entry, dict):
                continue
            kind = self._image_entry_kind(entry)
            items.append(
                {
                    "index": index,
                    "template_key": str(entry.get("__template_key") or "").strip()
                    or (
                        _IMAGE_TEMPLATE_KEY_BUILTIN
                        if kind == "builtin"
                        else _IMAGE_TEMPLATE_KEY_CUSTOM
                    ),
                    "entry": entry,
                }
            )
        return items

    def _find_image_entry(self, entries: list[Any], index: Any) -> tuple[int, dict[str, Any]] | None:
        """按 index 定位图床条目，返回 (下标, 条目)；无效定位返回 None。

        index 为布尔、空串、非数字或越界时一律视为定位失败，由调用方回 400。
        """
        if isinstance(index, bool) or index is None:
            return None
        try:
            position = int(str(index).strip())
        except (TypeError, ValueError):
            return None
        if 0 <= position < len(entries) and isinstance(entries[position], dict):
            return position, entries[position]
        return None

    def _image_bed_response(self, **extra: Any) -> Any:
        """统一返回格式：最新条目原始列表 + 当前根级开关/超时。"""
        payload: dict[str, Any] = {
            "items": self._config_image_items(),
            "enable_image_upload": _as_bool(
                self.plugin.config.get("enable_image_upload") if self.plugin is not None else None,
                False,
            ),
            "image_upload_timeout": self._image_bed_timeout(),
        }
        payload.update(extra)
        return json_response(payload)

    async def get_config_image_bed(self) -> Any:
        """列出配置里的图床条目原始数据（含未启用条目）。

        与 /image_bed/status 的 items[] 不同：这里返回的是 conf 里的原始
        条目（带 __template_key），供面板表单编辑回显；status 的 items[]
        是带生效原因的运行态视图。
        """
        return self._image_bed_response()

    async def create_config_image_bed(self) -> Any:
        """新建图床条目并局部生效（不触碰 MC 连接）。

        请求体：``{"template_key": "builtin_http"|"custom"|"catbox"|...}`` 必填，
        条目其余字段按 schema 模板默认值补齐；仅显式出现的字段覆盖默认值。
        """
        if self.plugin is None:
            return error_response("插件实例未注入，无法修改配置", status_code=503)
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)

        template_key = str(payload.get("template_key") or "").strip()
        templates = (
            (self._read_schema().get("image_upload_services") or {}).get("templates") or {}
        )
        if template_key not in templates:
            return error_response(f"未知的图床模板: {template_key or '(空)'}", status_code=400)

        entries = copy.deepcopy(self._conf_image_entries())
        entry = self._new_image_entry(template_key)
        for key in _IMAGE_ENTRY_FIELDS:
            if key == "enabled":
                entry[key] = _as_bool(payload.get(key), True)
                continue
            if key in payload:
                if key in ("port",):
                    entry[key] = _as_int(payload.get(key), entry.get(key) or 8765)
                else:
                    entry[key] = str(payload.get(key) or "")
        entries.append(entry)
        try:
            await self._persist_config(self._conf_with_image_entries(entries), reload=False)
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 新建图床条目失败")
            return error_response(f"新建图床条目失败: {exc}", status_code=500)
        logger.info(f"[{PLUGIN_NAME}] 面板新建图床条目: {template_key}")
        return self._image_bed_response(saved=True, template_key=template_key)

    async def update_config_image_bed(self) -> Any:
        """修改图床条目字段 / 启用状态 / 切换模板并局部生效。

        请求体需带 ``index`` 定位条目；其余字段仅「显式出现」才覆盖，避免
        前端漏传把已有配置清空。``template_key`` 出现且与当前模板不同时，
        按新模板重建条目默认值后再套用显式字段（换模板）。
        """
        if self.plugin is None:
            return error_response("插件实例未注入，无法修改配置", status_code=503)
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)

        entries = copy.deepcopy(self._conf_image_entries())
        found = self._find_image_entry(entries, payload.get("index"))
        if found is None:
            return error_response("未找到对应的图床条目（index 无效）", status_code=400)
        position, entry = found

        new_template_key = str(payload.get("template_key") or "").strip()
        current_key = str(entry.get("__template_key") or "").strip()
        if new_template_key and new_template_key != current_key:
            templates = (
                (self._read_schema().get("image_upload_services") or {}).get("templates") or {}
            )
            if new_template_key not in templates:
                return error_response(f"未知的图床模板: {new_template_key}", status_code=400)
            entry = self._new_image_entry(new_template_key)
            entries[position] = entry
        for key in _IMAGE_ENTRY_FIELDS:
            if key == "enabled":
                if "enabled" in payload:
                    entry[key] = _as_bool(payload.get("enabled"), True)
                continue
            if key in payload:
                if key in ("port",):
                    entry[key] = _as_int(payload.get(key), entry.get(key) or 8765)
                else:
                    entry[key] = str(payload.get(key) or "")
        try:
            await self._persist_config(self._conf_with_image_entries(entries), reload=False)
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 更新图床条目失败")
            return error_response(f"更新图床条目失败: {exc}", status_code=500)
        logger.info(f"[{PLUGIN_NAME}] 面板更新图床条目: #{position}")
        return self._image_bed_response(saved=True, index=position)

    async def delete_config_image_bed(self) -> Any:
        """按 index 删除图床条目并局部生效（配置备份已留存）。"""
        if self.plugin is None:
            return error_response("插件实例未注入，无法修改配置", status_code=503)
        payload = await request.json(default={}) or {}
        if not isinstance(payload, dict):
            return error_response("请求体需为 JSON 对象", status_code=400)

        entries = copy.deepcopy(self._conf_image_entries())
        found = self._find_image_entry(entries, payload.get("index"))
        if found is None:
            return error_response("未找到对应的图床条目（index 无效）", status_code=400)
        position, entry = found
        removed_key = str(entry.get("__template_key") or "").strip() or "条目"

        entries.pop(position)
        try:
            await self._persist_config(self._conf_with_image_entries(entries), reload=False)
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] 删除图床条目失败")
            return error_response(f"删除图床条目失败: {exc}", status_code=500)
        logger.info(f"[{PLUGIN_NAME}] 面板删除图床条目: #{position} ({removed_key})")
        return self._image_bed_response(saved=True, removed=removed_key)

    def get_panel_prefs(self) -> Any:
        """获取面板级偏好（互通终端加载天数等，长期存储在后端）。

        前端 localStorage 在受限 iframe 下可能被沙箱禁止、清缓存/换设备
        即丢失——面板偏好的权威数据落盘到 ``data_dir/panel_prefs.json``，
        浏览器端只作启动缓存。
        """
        if self.panel_prefs is None:
            return json_response({"prefs": {}})
        return json_response({"prefs": self.panel_prefs.all()})

    async def set_panel_prefs(self) -> Any:
        """保存面板级偏好（合并写入并原子落盘）。

        当前支持字段：``terminal_days``（互通终端加载天数，0~30，0=全部）、
        ``auto_refresh``（顶部自动刷新开关，布尔）、
        ``auto_refresh_interval``（仪表盘自动刷新间隔秒数，10~3600）、
        ``settings_collapsed``（仪表盘「功能设置」面板是否折叠，布尔）、
        ``active_tab``（当前打开的服务器视图，'all' 或服务器名，≤64 字符）。
        """
        if self.panel_prefs is None:
            return error_response("面板偏好存储未接入", status_code=503)
        raw = await request.json(default={}) or {}
        fields: dict[str, Any] = {}
        if "terminal_days" in raw:
            terminal_days = raw["terminal_days"]
            if isinstance(terminal_days, bool) or not isinstance(terminal_days, (int, str)):
                return error_response("terminal_days 需为数字", status_code=400)
            try:
                value = int(terminal_days)
            except (TypeError, ValueError):
                return error_response("terminal_days 需为数字", status_code=400)
            fields["terminal_days"] = max(0, min(30, value))
        if "auto_refresh" in raw:
            raw_ar = raw["auto_refresh"]
            if isinstance(raw_ar, bool):
                fields["auto_refresh"] = raw_ar
            elif isinstance(raw_ar, str) and raw_ar.strip().lower() in ("true", "false"):
                fields["auto_refresh"] = raw_ar.strip().lower() == "true"
            else:
                return error_response("auto_refresh 需为布尔值", status_code=400)
        if "auto_refresh_interval" in raw:
            raw_ari = raw["auto_refresh_interval"]
            if isinstance(raw_ari, bool) or not isinstance(raw_ari, (int, str)):
                return error_response("auto_refresh_interval 需为数字", status_code=400)
            try:
                ari_value = int(raw_ari)
            except (TypeError, ValueError):
                return error_response("auto_refresh_interval 需为数字", status_code=400)
            # 与前端 setupAutoRefresh 的钳制口径一致（10~3600 秒）
            fields["auto_refresh_interval"] = max(10, min(3600, ari_value))
        if "settings_collapsed" in raw:
            raw_sc = raw["settings_collapsed"]
            if isinstance(raw_sc, bool):
                fields["settings_collapsed"] = raw_sc
            elif isinstance(raw_sc, str) and raw_sc.strip().lower() in ("true", "false"):
                fields["settings_collapsed"] = raw_sc.strip().lower() == "true"
            else:
                return error_response("settings_collapsed 需为布尔值", status_code=400)
        if "active_tab" in raw:
            raw_at = raw["active_tab"]
            if not isinstance(raw_at, str):
                return error_response("active_tab 需为字符串", status_code=400)
            at_value = raw_at.strip()
            if len(at_value) > 64:
                return error_response("active_tab 过长（≤64 字符）", status_code=400)
            if at_value:
                fields["active_tab"] = at_value
        if not fields:
            return json_response({"prefs": self.panel_prefs.all()})
        self.panel_prefs.update(fields)
        return json_response({"prefs": self.panel_prefs.all()})

    # ---- 性能监控（TPS / 延迟） ----

    async def get_monitor_status(self) -> Any:
        """获取全部服务器性能监控状态（当前生效设置、最新采样、错误等）。"""
        if self.monitor is None:
            return error_response("性能监控未接入", status_code=503)
        result = {}
        for name in self.configs:
            result[name] = self.monitor.status(name)
        return json_response({"monitors": result})

    async def get_monitor_series(self, server_name: str) -> Any:
        """获取某台服务器在一段时间窗内的监控序列与统计摘要。

        Query 参数：
        - ``range``：时间窗，``1h``/``6h``/``24h``/``168h``/``7d`` 或纯数字小时，默认 24h
        - ``bucket``：显式桶宽（``1m``/``15m``/``1h``）；缺省按时间窗自动选择
        """
        if self.monitor is None:
            return error_response("性能监控未接入", status_code=503)
        instance = self.server_manager.get(server_name)
        if instance is None:
            return error_response(f"服务器不存在: {server_name}", status_code=404)

        range_hours, bucket_seconds = self._parse_monitor_window()
        since_ts = time.time() - range_hours * 3600
        # 实时 1 分钟窗口每秒 1 点：边界处样本数可为 60 或 61，按窗口秒数
        # 截断到最近 N 个点，统计卡与曲线稳定显示 60（正常长窗口采样数远
        # 小于上限，永不触发截断）
        cap_seconds = max(1, int(range_hours * 3600))
        series = self.monitor.store.series(
            server_name, since_ts, bucket_seconds, cap_seconds=cap_seconds
        )
        return json_response(
            {
                "server": server_name,
                "range_hours": range_hours,
                "bucket_seconds": bucket_seconds,
                "series": series,
            }
        )

    @staticmethod
    def _parse_monitor_window() -> tuple[float, int]:
        """解析 range / bucket 参数，返回 (时长小时, 桶宽秒)。

        - ``range``：``1h``/``6h``/``24h``/``168h``/``7d``、纯数字小时，
          以及实时模式使用的 ``1m``/``30s`` 等分钟/秒单位；非法回落 24h
        - ``bucket``：显式桶宽（``10s``/``1m``/``15m``/``1h``）；缺省按
          时间窗自动选择
        """
        try:
            raw_range = str(request.query.get("range", "24h")).strip().lower()
        except (AttributeError, ValueError, TypeError):
            raw_range = "24h"
        range_hours = 24.0
        if raw_range:
            try:
                if raw_range.endswith("s"):
                    value = float(raw_range[:-1]) / 3600
                elif raw_range.endswith("m"):
                    value = float(raw_range[:-1]) / 60
                elif raw_range.endswith("h"):
                    value = float(raw_range[:-1])
                elif raw_range.endswith("d"):
                    value = float(raw_range[:-1]) * 24
                else:
                    value = float(raw_range)
            except ValueError:
                value = 24.0
            if value > 0:
                range_hours = min(value, 24 * 90)  # 上限 90 天，防止极端参数拖垮响应

        # 桶宽自动选择：短窗细粒度，长窗粗粒度，保证图表点数适中
        if range_hours <= 2:
            bucket_seconds = 60
        elif range_hours <= 24:
            bucket_seconds = 600
        elif range_hours <= 72:
            bucket_seconds = 1800
        else:
            bucket_seconds = 3600

        try:
            raw_bucket = str(request.query.get("bucket", "")).strip().lower()
        except (AttributeError, ValueError, TypeError):
            raw_bucket = ""
        if raw_bucket:
            try:
                if raw_bucket.endswith("s"):
                    # 实时模式桶宽跟随采样频率（realtime_interval 可到 1 秒），
                    # 下限放开到 1s：1s 采样 → 1s 桶 → 60 秒窗口 60 个点
                    bucket_seconds = max(1, int(float(raw_bucket[:-1])))
                elif raw_bucket.endswith("m") and not raw_bucket.endswith("h"):
                    bucket_seconds = max(60, int(float(raw_bucket[:-1]) * 60))
                elif raw_bucket.endswith("h"):
                    bucket_seconds = max(60, int(float(raw_bucket[:-1]) * 3600))
                else:
                    bucket_seconds = max(60, int(float(raw_bucket)))
            except ValueError:
                pass
        return range_hours, bucket_seconds

    async def save_monitor_settings(self) -> Any:
        """保存某台服务器的性能监控设置（来自仪表盘页面，不走 conf schema）。

        请求体：``{"server_name": "...", "enabled": bool, "interval": int,
        "retention_days": int, "tps_command": "..."}``，仅更新出现的字段；
        保存后立即生效并持久化到 ``data_dir/monitor/settings.json``。
        非法数值由 ``MonitorSettings.from_dict`` 防御式兜底（下限钳制）。
        """
        if self.monitor is None:
            return error_response("性能监控未接入", status_code=503)
        try:
            body = await request.json(default={}) or {}
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return error_response("请求体必须是 JSON 对象", status_code=400)

        server_name = str(body.get("server_name") or body.get("server") or "").strip()
        if not server_name:
            return error_response("缺少 server_name", status_code=400)
        if server_name not in self.configs and self.server_manager.get(server_name) is None:
            return error_response(f"服务器不存在: {server_name}", status_code=404)

        fields = {
            key: body[key]
            for key in (
                "enabled", "interval", "retention_days", "tps_command",
                "ping_host", "ping_port", "default_tab", "realtime_interval",
                "auto_refresh_interval",
            )
            if key in body
        }
        if not fields:
            return error_response("缺少可保存的设置字段", status_code=400)

        updated = self.monitor.apply_settings(server_name, fields)
        return json_response(
            {"server": server_name, "settings": updated.to_dict()}
        )

    async def sample_monitor(self, server_name: str) -> Any:
        """立即对某台服务器执行一次采样（不等下一个采集间隔）。

        触发一轮与定时循环相同的采样（TPS 经 RCON、延迟经直连 SLP ping，
        并行执行），结果写入当天分片；返回该服最新监控状态，供仪表盘
        「⏱ 立即采集」按钮调用。
        """
        if self.monitor is None:
            return error_response("性能监控未接入", status_code=503)
        if server_name not in self.configs and self.server_manager.get(server_name) is None:
            return error_response(f"服务器不存在: {server_name}", status_code=404)
        status = await self.monitor.sample_now(server_name)
        if status is None:
            return error_response(f"服务器不存在: {server_name}", status_code=404)
        return json_response({"server": server_name, "status": status})

    async def clear_monitor_data(self, server_name: str) -> Any:
        """清空某台服务器的性能监控采样数据（JSONL 分片 + 内存计数）。

        仅清数据，不触碰监控设置/保留天数；采集任务继续运行，下一轮采样
        从零重新累计。由仪表盘设置弹窗「🗑 清除采集数据」按钮调用
        （前端二次确认，操作不可恢复）。
        """
        if self.monitor is None:
            return error_response("性能监控未接入", status_code=503)
        if server_name not in self.configs and self.server_manager.get(server_name) is None:
            return error_response(f"服务器不存在: {server_name}", status_code=404)
        removed = self.monitor.clear_data(server_name)
        return json_response({"success": True, "server": server_name, "removed": removed})
