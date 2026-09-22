"""Web API 控制器：提供给 AstrBot 插件 Pages 的后端 Web API。

基于 AstrBot 的 `context.register_web_api()` 机制，配合 `astrbot.api.web`
处理 HTTP 请求与 SSE 实时事件流。
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from ..core.constants import PLUGIN_NAME
from .metrics import MetricsCollector

try:
    from astrbot.api.web import error_response, json_response, request, stream_response
except ImportError:
    import logging

    _log = logging.getLogger(PLUGIN_NAME)

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
    from .binding import BindingService
    from .image_bed import ImageBedUploaderGroup
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
    ) -> None:
        self.context = context
        self.server_manager = server_manager
        self.binding_service = binding_service
        self.image_bed = image_bed
        self.metrics = metrics
        self.configs = configs
        self.terminal_logs = terminal_logs

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
            ("/config", self.get_config_overview, ["GET"], "获取插件配置概览"),
        ]

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
        return json_response(data)

    async def get_servers(self) -> Any:
        """获取所有服务器列表及其连接状态，并附带各服务器的实时状态与在线玩家。"""
        servers_info = []
        for server_name, config in self.configs.items():
            instance = self.server_manager.get(server_name)
            connected = instance.connected if instance else False
            direct_rcon_connected = (
                instance.rcon.connected if instance and instance.rcon else False
            )

            status_data = None
            players_data = None
            if instance and connected:
                try:
                    status_model = await instance.get_status_model()
                    if status_model:
                        status_data = status_model.to_dict()
                except Exception as exc:
                    logger.warning(
                        f"[{PLUGIN_NAME}][{server_name}] 获取状态失败: {exc}"
                    )

                try:
                    plr = await instance.fetch_player_list()
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
        return json_response(status.to_dict())

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
        """获取某台服务器的持久化终端日志（旧 → 新）。"""
        try:
            server_name = str(request.query.get("server", "")).strip()
        except (AttributeError, ValueError, TypeError):
            server_name = ""
        if not server_name:
            return error_response("缺少 server 参数", status_code=400)
        logs = self.terminal_logs.get(server_name) if self.terminal_logs else []
        return json_response({"server": server_name, "logs": logs})

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
        """获取图床服务的运行状态。"""
        return json_response(
            {
                "enabled": self.image_bed.enabled,
                "status_text": self.image_bed.status_text,
                "service_names": self.image_bed.service_names,
                "uploaders_count": len(self.image_bed.uploaders),
            }
        )

    async def get_config_overview(self) -> Any:
        """获取插件配置概览（脱敏敏感字段）。"""
        servers = []
        for name, cfg in self.configs.items():
            servers.append(
                {
                    "server_name": name,
                    "display_name": cfg.display_name,
                    "server_label": cfg.server_label,
                    "enabled": cfg.enabled,
                    "is_reverse": cfg.is_reverse,
                    "ws_url": cfg.ws_url,
                    "reverse_port": cfg.reverse_port,
                    "auto_forward_prefix": cfg.auto_forward_prefix,
                    "ai_chat_prefix": cfg.ai_chat_prefix,
                    "enable_ai_chat": cfg.enable_ai_chat,
                    "cmd_enabled": cfg.cmd_enabled,
                    "cmd_mode": cfg.cmd_white_black_list,
                    "forward_chat": cfg.forward_chat_to_astrbot,
                    "forward_join_leave": cfg.forward_join_leave_to_astrbot,
                    "forward_death": cfg.forward_death_to_astrbot,
                    "forward_achievement": cfg.forward_achievement_to_astrbot,
                    "forward_image_to_mc": cfg.forward_image_to_mc,
                    "forward_image_from_mc": cfg.forward_image_from_mc,
                    "target_sessions": cfg.target_sessions,
                }
            )
        return json_response({"servers": servers})
