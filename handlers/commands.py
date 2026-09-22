"""命令处理：mc 子命令实现、自定义指令匹配与多服务器选择。

自定义指令语法（沿用 adapter 约定）：
    "tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>"
- `<<>>` 左侧为触发模板，右侧为实际执行指令
- `{sender}` 替换为发送者绑定的游戏 ID
- `<&xxx&>` 为自定义参数占位符，左右同名即按位置替换
"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..core.constants import PLUGIN_NAME
from ..core.models_config import ServerConfig
from ..core.server_manager import ServerInstance, ServerManager
from ..services.binding import BindingService
from ..services.renderer import InfoRenderer

CUSTOM_CMD_SEPARATOR = "<<>>"


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
        # server_name -> [(trigger_tokens, param_names, template)]
        self._custom: dict[str, list[tuple[list[str], list[str], str]]] = {}

    # ---- 自定义指令注册与匹配 ----

    def register_custom_commands(self, server_name: str, entries: list[str]) -> None:
        """解析并注册自定义指令。"""
        parsed: list[tuple[list[str], list[str], str]] = []
        for entry in entries:
            left, sep, right = entry.partition(CUSTOM_CMD_SEPARATOR)
            if not sep or not left.strip() or not right.strip():
                logger.warning(f"[{PLUGIN_NAME}][{server_name}] 自定义指令格式无效: {entry}")
                continue

            trigger_tokens = left.split()
            param_names = [
                token[2:-2] for token in trigger_tokens if token.startswith("<&") and token.endswith("&>")
            ]
            parsed.append((trigger_tokens, param_names, right.strip()))

        self._custom[server_name] = parsed
        if parsed:
            logger.info(f"[{PLUGIN_NAME}][{server_name}] 已注册 {len(parsed)} 条自定义指令")

    def match_custom_command(self, server_name: str, text: str) -> str | None:
        """把用户输入匹配为实际指令，未命中返回 None。"""
        entries = self._custom.get(server_name)
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
        for server_name, entries in self._custom.items():
            for trigger_tokens, _, _ in entries:
                lines.append(f"- {server_name}: {' '.join(trigger_tokens)}")
        return lines

    # ---- 目标服务器选择 ----

    def _bound_servers(self, umo: str) -> list[ServerInstance]:
        """返回与该会话绑定的、且已配置启用的服务器实例。"""
        result: list[ServerInstance] = []
        for server_name, _ in self.bridge_lookup(umo):
            instance = self.server_manager.get(server_name)
            if instance is not None:
                result.append(instance)
        return result

    def bridge_lookup(self, umo: str) -> list[tuple[str, ServerConfig]]:
        """由 main 注入的行车桥查询；未注入时回退为全部服务器。"""
        if self._bridge is not None:
            return self._bridge.servers_for_session(umo)
        return [
            (instance.server_name, instance.config)
            for instance in self.server_manager.all()
        ]

    def attach_bridge(self, bridge) -> None:
        self._bridge = bridge

    # 性能监控（TPS/延迟）采集器：注入后 /mc status 附带最近采样值
    def attach_monitor(self, monitor) -> None:
        self._monitor = monitor

    # 声明为类属性，便于 attach_monitor 之前安全访问
    _monitor = None

    # 声明为类属性，便于 attach_bridge 之前安全访问
    _bridge = None

    def _select_target(
        self, event: AstrMessageEvent
    ) -> tuple[ServerInstance | None, str | None]:
        """为命令自动选择目标服务器（无显式编号时使用）。

        返回 (实例, 提示文本)：实例为 None 时，提示文本需回给用户。
        多台服务器时提示用户在指令前加数字编号选择目标。
        """
        umo = event.unified_msg_origin
        all_servers = self.server_manager.all()
        if not all_servers:
            return None, "❌ 尚未配置任何 MC 服务器，请先在插件配置中添加"

        bound = self._bound_servers(umo)
        if len(bound) == 1:
            return bound[0], None
        if len(bound) > 1:
            return None, self._ambiguous_hint(bound)

        if len(all_servers) == 1:
            return all_servers[0], None

        return None, self._ambiguous_hint(all_servers)

    def _resolve_target(
        self, event: AstrMessageEvent, target: str
    ) -> tuple[ServerInstance | None, str | None]:
        """按「显式数字编号优先，否则自动定位」解析目标服务器。

        target 非空时按数字编号取实例（1 = 配置第一台，与 `mc servers`
        列表顺序一致）；为空时回退 _select_target（单服自动命中、多服
        提示加编号）。供带可选编号形参的子命令统一调用，实现
        「单服省略、多服加编号」。
        """
        if target:
            all_servers = self.server_manager.all()
            if not all_servers:
                return None, "❌ 尚未配置任何 MC 服务器，请先在插件配置中添加"
            if not target.isdigit():
                return None, f"❌ 目标编号需为数字，可用 1-{len(all_servers)}"
            idx = int(target)
            if not (1 <= idx <= len(all_servers)):
                return None, f"❌ 编号 {idx} 超出范围，可用 1-{len(all_servers)}"
            return all_servers[idx - 1], None
        return self._select_target(event)

    def _ambiguous_hint(self, servers: list[ServerInstance]) -> str:
        """多服务器时提示用户在指令前加数字编号选择目标。"""
        lines = ["⚠️ 当前有多台服务器，请在指令前加数字编号选择目标："]
        for index, instance in enumerate(servers, start=1):
            status = "🟢" if instance.connected else "🔴"
            lines.append(f"{index}. {status} {instance.config.display_label}")
        lines.append("示例：mc cmd 1 <指令>  /  mc status 2")
        return "\n".join(lines)

    def _split_optional_target(self, text: str) -> tuple[str | None, str]:
        """从文本首 token 拆出可选的数字目标编号（仅多服时生效）。

        单服时不拆——首 token 视为指令/内容的一部分，避免 `mc say 123`
        这类纯数字内容被误当编号。多服时若首 token 是 1..N 的数字，
        视为显式指定，返回 (编号字符串, 剩余文本)；否则返回 (None, 原文)，
        交给调用方走自动定位。
        """
        stripped = text.strip()
        if not stripped:
            return None, ""
        all_servers = self.server_manager.all()
        if len(all_servers) <= 1:
            return None, stripped
        head, _, rest = stripped.partition(" ")
        if head.isdigit():
            idx = int(head)
            if 1 <= idx <= len(all_servers):
                return head, rest.strip()
        return None, stripped

    # ---- 子命令实现 ----

    def help_text(self) -> str:
        lines = [
            "📖 Minecraft 鹊桥互通 帮助",
            "",
            "mc help — 显示本帮助",
            "mc status [编号] — 查看服务器状态",
            "mc list [编号] — 查看在线玩家列表",
            "mc player [编号] <玩家ID> — 查看玩家信息",
            "mc cmd [编号] <指令> — 远程执行服务器指令（管理员）",
            "mc say [编号] <内容> — 向游戏内广播消息（管理员）",
            "mc bind <游戏ID> — 绑定你的游戏ID",
            "mc unbind — 解除绑定",
            "mc servers — 查看服务器与连接状态",
            "",
            "多台服务器时在指令前加数字编号选择目标（mc servers 可查看编号）；仅一台时可直接省略",
        ]
        custom = self.custom_command_help()
        if custom:
            lines.append("")
            lines.append("自定义指令：")
            lines.extend(custom)
        return "\n".join(lines)

    async def handle_status(self, event: AstrMessageEvent, server_name: str) -> str:
        instance = self.server_manager.get(server_name)
        if instance is None:
            return f"❌ 未找到服务器 {server_name}"

        # 展示用名称（display_name，可中文）；server_name 仍用于连接与排障
        label = instance.config.display_label
        if not instance.connected:
            return f"❌ 服务器 {label} 未连接鹊桥"

        status = await instance.get_status_model()
        # 性能监控的最近采样（TPS 三档 / API 延迟），与实时状态查询相互独立；
        # 未启用监控或尚无采样时为 None，渲染层自动省略
        latest = self._monitor.store.latest(server_name) if self._monitor else None
        tps = None
        latency_ms = None
        if latest is not None:
            if latest.tps1 is not None or latest.tps5 is not None or latest.tps15 is not None:
                tps = (latest.tps1, latest.tps5, latest.tps15)
            latency_ms = latest.latency_ms
        return await self.renderer.render_status(
            server_name, status, label, tps=tps, latency_ms=latency_ms
        )

    async def handle_list(self, event: AstrMessageEvent, server_name: str) -> str:
        instance = self.server_manager.get(server_name)
        if instance is None:
            return f"❌ 未找到服务器 {server_name}"

        result = await instance.fetch_player_list()
        return self.renderer.format_player_list(
            server_name, result, instance.config.display_label
        )

    async def handle_player(self, event: AstrMessageEvent, server_name: str, player_id: str) -> str:
        instance = self.server_manager.get(server_name)
        if instance is None:
            return f"❌ 未找到服务器 {server_name}"

        # 鹊桥没有玩家详情查询接口，只能借助 RCON 查询单玩家数据
        output = await instance.execute_command(f"data get entity {player_id}")
        if output is None:
            return (
                f"⚠️ 无法查询玩家 {player_id}\n"
                f"鹊桥未提供玩家详情接口，此功能依赖 RCON；请确认已开启 RCON"
            )
        return f"🧍 玩家 {player_id}：\n{output}"

    async def handle_cmd(self, event: AstrMessageEvent, server_name: str, command: str) -> str:
        instance = self.server_manager.get(server_name)
        if instance is None:
            return f"❌ 未找到服务器 {server_name}"

        config = instance.config
        if not config.cmd_enabled:
            return "❌ 该服务器的远程指令功能已关闭"

        if not config.is_command_allowed(command):
            return f"🚫 指令 `{command}` 不在允许名单内"

        output = await instance.execute_command(command)
        if output is None:
            return f"❌ 指令执行失败：{command}\n请确认鹊桥已开启 RCON 或已配置直连 RCON"
        return f"✅ 已执行：{command}\n{output}".rstrip()

    async def handle_say(self, event: AstrMessageEvent, server_name: str, content: str) -> str:
        instance = self.server_manager.get(server_name)
        if instance is None:
            return f"❌ 未找到服务器 {server_name}"

        if not instance.connected:
            return f"❌ 服务器 {server_name} 未连接鹊桥"

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
            name_display = instance.server_name
            disp = (instance.config.display_name or "").strip()
            if disp and disp != instance.server_name:
                name_display = f"{disp} ({instance.server_name})"
            lines.append(f"- {name_display}（{mode}）：{status}")
        return "\n".join(lines)
