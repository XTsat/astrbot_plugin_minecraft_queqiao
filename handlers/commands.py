"""命令处理：mc 子命令实现、自定义指令匹配与多服务器选择。

自定义指令语法（沿用 adapter 约定）：
    "tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>"
- `<<>>` 左侧为触发模板，右侧为实际执行指令
- `{sender}` 替换为发送者绑定的游戏 ID
- `<&xxx&>` 为自定义参数占位符，左右同名即按位置替换
"""

import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..core.constants import PENDING_ACTION_TTL, PLUGIN_NAME
from ..core.models import ServerStatus
from ..core.models_config import ServerConfig
from ..core.server_manager import ServerInstance, ServerManager
from ..services.binding import BindingService
from ..services.renderer import InfoRenderer

CUSTOM_CMD_SEPARATOR = "<<>>"


class PendingAction:
    """等待用户以数字选择服务器的待决操作。"""

    def __init__(self, action: str, candidates: list[str], payload: str = "") -> None:
        self.action = action
        self.candidates = candidates
        self.payload = payload
        self.created_at = time.time()

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > PENDING_ACTION_TTL


class CommandHandler:
    """处理 mc 命令组的业务逻辑，main.py 只做参数转发。"""

    def __init__(
        self,
        server_manager: ServerManager,
        binding_service: BindingService,
        renderer: InfoRenderer,
    ) -> None:
        self.server_manager = server_manager
        self.binding = binding_service
        self.renderer = renderer
        # umo -> PendingAction
        self._pending: dict[str, PendingAction] = {}
        # server_id -> [(trigger_tokens, param_names, template, raw)]
        self._custom: dict[str, list[tuple[list[str], list[str], str]]] = {}

    # ---- 自定义指令注册与匹配 ----

    def register_custom_commands(self, server_id: str, entries: list[str]) -> None:
        """解析并注册自定义指令。"""
        parsed: list[tuple[list[str], list[str], str]] = []
        for entry in entries:
            left, sep, right = entry.partition(CUSTOM_CMD_SEPARATOR)
            if not sep or not left.strip() or not right.strip():
                logger.warning(f"[{PLUGIN_NAME}][{server_id}] 自定义指令格式无效: {entry}")
                continue

            trigger_tokens = left.split()
            param_names = [
                token[2:-2] for token in trigger_tokens if token.startswith("<&") and token.endswith("&>")
            ]
            parsed.append((trigger_tokens, param_names, right.strip()))

        self._custom[server_id] = parsed
        if parsed:
            logger.info(f"[{PLUGIN_NAME}][{server_id}] 已注册 {len(parsed)} 条自定义指令")

    def match_custom_command(self, server_id: str, text: str) -> str | None:
        """把用户输入匹配为实际指令，未命中返回 None。"""
        entries = self._custom.get(server_id)
        if not entries:
            return None

        tokens = text.split()
        for trigger_tokens, param_names, template in entries:
            # 自定义参数占位符按位置通配，其余需逐字匹配
            if len(tokens) != len(trigger_tokens):
                continue

            captured: dict[str, str] = {}
            matched = True
            param_index = 0
            for expected, actual in zip(trigger_tokens, tokens):
                if expected.startswith("<&") and expected.endswith("&>"):
                    if param_index < len(param_names):
                        captured[param_names[param_index]] = actual
                    param_index += 1
                elif expected != actual:
                    matched = False
                    break

            if not matched:
                continue

            result = template
            for name, value in captured.items():
                result = result.replace(f"<&{name}&>", value)
            return result

        return None

    def custom_command_help(self) -> list[str]:
        """汇总所有服务器的自定义指令触发词，用于 help 输出。"""
        lines: list[str] = []
        for server_id, entries in self._custom.items():
            for trigger_tokens, _, _ in entries:
                lines.append(f"- {server_id}: {' '.join(trigger_tokens)}")
        return lines

    # ---- 待决选择 ----

    def has_pending_action(self, umo: str) -> bool:
        action = self._pending.get(umo)
        if action is None:
            return False
        if action.expired:
            del self._pending[umo]
            return False
        return True

    def set_pending(self, umo: str, action: PendingAction) -> None:
        self._pending[umo] = action

    def clear_pending(self, umo: str) -> None:
        self._pending.pop(umo, None)

    def resolve_selection(self, umo: str, index: int) -> tuple[str, str, str] | None:
        """把用户输入的数字解析为 (action, server_id, payload)。"""
        action = self._pending.get(umo)
        if action is None or action.expired:
            self._pending.pop(umo, None)
            return None
        if not (1 <= index <= len(action.candidates)):
            return None
        server_id = action.candidates[index - 1]
        self._pending.pop(umo, None)
        return action.action, server_id, action.payload

    # ---- 目标服务器选择 ----

    def _bound_servers(self, umo: str) -> list[ServerInstance]:
        """返回与该会话绑定的、且已配置启用的服务器实例。"""
        result: list[ServerInstance] = []
        for server_id, _ in self.bridge_lookup(umo):
            instance = self.server_manager.get(server_id)
            if instance is not None:
                result.append(instance)
        return result

    def bridge_lookup(self, umo: str) -> list[tuple[str, ServerConfig]]:
        """由 main 注入的行车桥查询；未注入时回退为全部服务器。"""
        if self._bridge is not None:
            return self._bridge.servers_for_session(umo)
        return [
            (instance.server_id, instance.config)
            for instance in self.server_manager.all()
        ]

    def attach_bridge(self, bridge) -> None:
        self._bridge = bridge

    # 声明为类属性，便于 attach_bridge 之前安全访问
    _bridge = None

    def _select_target(
        self, event: AstrMessageEvent
    ) -> tuple[ServerInstance | None, str | None]:
        """为命令选择目标服务器。

        返回 (实例, 提示文本)：实例为 None 时，提示文本需回给用户。
        """
        umo = event.unified_msg_origin
        all_servers = self.server_manager.all()
        if not all_servers:
            return None, "❌ 尚未配置任何 MC 服务器，请先在插件配置中添加"

        bound = self._bound_servers(umo)
        if len(bound) == 1:
            return bound[0], None
        if len(bound) > 1:
            return None, self._make_selection_hint("bound", bound)

        if len(all_servers) == 1:
            return all_servers[0], None

        return None, self._make_selection_hint("all", all_servers)

    def _make_selection_hint(self, scope: str, servers: list[ServerInstance]) -> str:
        """构造服务器选择提示（配合数字回复使用）。"""
        lines = ["当前有多个服务器，请回复编号选择："]
        for index, instance in enumerate(servers, start=1):
            status = "🟢" if instance.connected else "🔴"
            lines.append(f"{index}. {status} {instance.server_id}")
        return "\n".join(lines)

    def build_selection_action(self, scope: str, servers: list[ServerInstance], payload: str) -> PendingAction:
        return PendingAction("select", [s.server_id for s in servers], payload)

    # ---- 子命令实现 ----

    def help_text(self) -> str:
        lines = [
            "📖 Minecraft 鹊桥互通 帮助",
            "",
            "mc help — 显示本帮助",
            "mc status — 查看服务器状态",
            "mc list — 查看在线玩家列表",
            "mc player <玩家ID> — 查看玩家信息",
            "mc cmd <指令> — 远程执行服务器指令（管理员）",
            "mc say <内容> — 向游戏内广播消息（管理员）",
            "mc bind <游戏ID> — 绑定你的游戏ID",
            "mc unbind — 解除绑定",
            "mc servers — 查看服务器与连接状态",
        ]
        custom = self.custom_command_help()
        if custom:
            lines.append("")
            lines.append("自定义指令：")
            lines.extend(custom)
        return "\n".join(lines)

    async def handle_status(self, event: AstrMessageEvent, server_id: str) -> str:
        instance = self.server_manager.get(server_id)
        if instance is None:
            return f"❌ 未找到服务器 {server_id}"

        # 展示用名称（server_name，可中文）；server_id 仍用于连接与排障
        label = instance.config.display_name
        if not instance.connected:
            return f"❌ 服务器 {label} 未连接鹊桥"

        raw = await instance.client.get_status()
        status = ServerStatus.from_dict(raw) if raw else None
        return await self.renderer.render_status(server_id, status, label)

    async def handle_list(self, event: AstrMessageEvent, server_id: str) -> str:
        instance = self.server_manager.get(server_id)
        if instance is None:
            return f"❌ 未找到服务器 {server_id}"

        players = await instance.fetch_player_list()
        return self.renderer.format_player_list(
            server_id, players, instance.config.display_name
        )

    async def handle_player(self, event: AstrMessageEvent, server_id: str, player_id: str) -> str:
        instance = self.server_manager.get(server_id)
        if instance is None:
            return f"❌ 未找到服务器 {server_id}"

        # 鹊桥没有玩家详情查询接口，只能借助 RCON 查询单玩家数据
        output = await instance.execute_command(f"data get entity {player_id}")
        if output is None:
            return (
                f"⚠️ 无法查询玩家 {player_id}\n"
                f"鹊桥未提供玩家详情接口，此功能依赖 RCON；请确认已开启 RCON"
            )
        return f"🧍 玩家 {player_id}：\n{output}"

    async def handle_cmd(self, event: AstrMessageEvent, server_id: str, command: str) -> str:
        instance = self.server_manager.get(server_id)
        if instance is None:
            return f"❌ 未找到服务器 {server_id}"

        config = instance.config
        if not config.cmd_enabled:
            return "❌ 该服务器的远程指令功能已关闭"

        if not config.is_command_allowed(command):
            return f"🚫 指令 `{command}` 不在允许名单内"

        output = await instance.execute_command(command)
        if output is None:
            return f"❌ 指令执行失败：{command}\n请确认鹊桥已开启 RCON 或已配置直连 RCON"
        return f"✅ 已执行：{command}\n{output}".rstrip()

    async def handle_say(self, event: AstrMessageEvent, server_id: str, content: str) -> str:
        instance = self.server_manager.get(server_id)
        if instance is None:
            return f"❌ 未找到服务器 {server_id}"

        if not instance.connected:
            return f"❌ 服务器 {server_id} 未连接鹊桥"

        success = await instance.client.broadcast(content, instance.config.broadcast_color)
        return "✅ 已广播到游戏内" if success else "❌ 广播失败"

    async def handle_bind(self, event: AstrMessageEvent, game_id: str) -> str:
        await self.binding.bind(event.unified_msg_origin, game_id)
        return f"✅ 已绑定游戏ID：{game_id}"

    async def handle_unbind(self, event: AstrMessageEvent) -> str:
        removed = await self.binding.unbind(event.unified_msg_origin)
        return "✅ 已解除绑定" if removed else "ℹ️ 你尚未绑定游戏ID"

    async def handle_servers(self, event: AstrMessageEvent) -> str:
        servers = self.server_manager.all()
        if not servers:
            return "❌ 尚未配置任何 MC 服务器"

        lines = ["🖥️ 已配置的服务器："]
        for instance in servers:
            status = "🟢 已连接" if instance.connected else "🔴 未连接"
            mode = "反向" if instance.config.is_reverse else "正向"
            lines.append(f"- {instance.server_id}（{mode}）：{status}")
        return "\n".join(lines)
