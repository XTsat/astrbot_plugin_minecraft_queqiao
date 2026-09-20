"""services 层：绑定、消息桥与渲染服务。"""

from .binding import BindingService
from .message_bridge import MessageBridge, component_to_text, strip_formatting
from .renderer import InfoRenderer

__all__ = [
    "BindingService",
    "InfoRenderer",
    "MessageBridge",
    "component_to_text",
    "strip_formatting",
]
