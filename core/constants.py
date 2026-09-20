"""插件级常量：鹊桥协议标识、默认值、连接参数。

本模块位于依赖链最底层，不得 import 本插件其它模块。
"""

PLUGIN_NAME = "astrbot_plugin_minecraft_queqiao"
PLUGIN_DATA_DIR = "astrbot_plugin_minecraft_queqiao"

# ---- 鹊桥 API 名称（V2，鹊桥 >= v0.2.11） ----

API_BROADCAST = "broadcast"
API_PRIVATE_MSG = "send_private_msg"
API_TITLE = "send_title"
API_ACTIONBAR = "send_actionbar"
API_RCON = "send_rcon_command"
API_GET_STATUS = "get_status"

# 响应中用于判定成功的字段
RESPONSE_POST_TYPE = "response"
RESPONSE_SUCCESS = "SUCCESS"

# ---- 鹊桥事件名（V2，鹊桥 >= v0.3.0） ----

EVENT_CHAT = "PlayerChatEvent"
EVENT_COMMAND = "PlayerCommandEvent"
EVENT_JOIN = "PlayerJoinEvent"
EVENT_QUIT = "PlayerQuitEvent"
EVENT_DEATH = "PlayerDeathEvent"
EVENT_ACHIEVEMENT = "PlayerAchievementEvent"

# 事件分类（post_type 字段）
POST_TYPE_MESSAGE = "message"
POST_TYPE_NOTICE = "notice"
POST_TYPE_RESPONSE = "response"

# ---- 握手 Header ----

HEADER_SELF_NAME = "x-self-name"
HEADER_AUTHORIZATION = "Authorization"
HEADER_CLIENT_ORIGIN = "x-client-origin"

DEFAULT_CLIENT_ORIGIN = "astrbot"

# ---- 连接参数 ----

DEFAULT_WS_URL = "ws://127.0.0.1:8080/minecraft/ws"
DEFAULT_REVERSE_HOST = "0.0.0.0"
DEFAULT_REVERSE_PORT = 8080
DEFAULT_REVERSE_PATH = "/minecraft/ws"

DEFAULT_RECONNECT_INTERVAL = 5
MAX_RECONNECT_WAIT = 60
PING_INTERVAL = 30
PING_TIMEOUT = 10

# 致命错误：不应重试（鉴权失败 / 路径错误 / 服务端拒绝）
FATAL_CLOSE_CODES = {1003, 1008, 1010}
FATAL_HTTP_STATUS = {401, 403, 404}

# API 请求响应超时（秒）
API_TIMEOUT = 10

# ---- 转发与回环抑制 ----

# 外部消息转发到 MC 后，该内容在此窗口内再次出现（回声）时不再回传外部
ECHO_SUPPRESS_WINDOW = 5.0

DEFAULT_CHAT_FORMAT = "<{player}> {message}"
DEFAULT_BROADCAST_FORMAT = "[{platform}] {sender}: {message}"

# ---- 多服务器选择 ----

# 待选操作（多服务器时需要用户回编号）的有效期
PENDING_ACTION_TTL = 60


def prefix_matches(prefix: str, text: str) -> bool:
    """判断文本是否以指定前缀触发（词边界感知，字母部分不区分大小写）。

    短前缀（如 `ai`）若只做 `startswith` 会误伤同词头的正常发言：
    `aim 很高`、`airport` 都会被当成 AI 触发。因此当前缀以字母/数字结尾时，
    要求其后紧跟分隔符（空格）或行尾，避免把单词截断算作命中。

    纯字母前缀同时忽略大小写，让 `AI 你好` 与 `ai 你好` 等效。

    非字母数字结尾的前缀（如 `*`、`!`）本身已具备分隔作用，保持简单前缀匹配。
    """
    if not prefix:
        return False

    stripped = text.strip()
    if prefix[-1].isalnum():
        # 字母/数字结尾：忽略大小写比较，且要求词边界
        if not stripped.lower().startswith(prefix.lower()):
            return False
        rest = stripped[len(prefix) :]
        return not rest or not rest[0].isalnum()

    return stripped.startswith(prefix)


def strip_prefix(prefix: str, text: str) -> str:
    """去掉触发前缀，返回剩余内容（前缀未命中时原样返回）。"""
    if not prefix:
        return text.strip()
    stripped = text.strip()
    if prefix_matches(prefix, stripped):
        return stripped[len(prefix) :].strip()
    return stripped
