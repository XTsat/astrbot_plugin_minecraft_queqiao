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

# 低频重试：连续重连失败超过该次数后，重连间隔不再按退避递增，
# 而是固定使用 low_frequency_interval（默认 300 秒 = 5 分钟，远大于
# MAX_RECONNECT_WAIT，实现真正的低频静默重试）；阈值配 0 表示关闭低频，
# 始终按退避重连
DEFAULT_LOW_FREQUENCY_THRESHOLD = 30
DEFAULT_LOW_FREQUENCY_INTERVAL = 300
PING_INTERVAL = 30
PING_TIMEOUT = 10

# 致命错误：不应重试（鉴权失败 / 路径错误 / 服务端拒绝）
FATAL_CLOSE_CODES = {1003, 1008, 1010}
FATAL_HTTP_STATUS = {401, 403, 404}

# API 请求响应超时（秒）。
# 注意：超时 ≠ 失败 —— WS 发送成功后鹊桥大概率已投递，只是响应慢/丢失；
# 调用方不得在超时后原样重发（会重复投递），语义见 queqiao_client.QueQiaoTimeout
API_TIMEOUT = 10

# ---- 转发与回环抑制 ----

# 外部消息转发到 MC 后，该内容在此窗口内再次出现（回声）时不再回传外部
ECHO_SUPPRESS_WINDOW = 5.0

DEFAULT_CHAT_FORMAT = "[{display_name}]{player}: {message}"
DEFAULT_BROADCAST_FORMAT = "[{platform}]{sender}: {message}"

# 服务器连通通知（notify_on_connect）的默认文案：连接建立（含断线重连、
# 插件热重载）时发往该服务器的目标会话。可用占位符 {display_name} / {server_name}
DEFAULT_CONNECT_NOTIFY_FORMAT = "[{display_name}] 🟢 服务器已启动"

# 连接失败通知（notify_on_connect_fail）的默认文案：同一轮故障只发第一条，
# 重新连上后重置；覆盖初次连不上与已连接后断线
DEFAULT_CONNECT_FAIL_NOTIFY_FORMAT = "[{display_name}] 🔴 服务器连接失败"

# 断连静默期（connect_fail_notify_delay，秒）：断线后须持续这么久仍未恢复才发
# 失败通知，期间连回则完全静默（不发失败、也不发恢复），用于过滤网络抖动、
# 服务端卡顿/重启加载、插件热重载造成的短时断连。
# 60 秒的依据：实测这类抖动多在 5 秒内自愈，而 60 秒内退避重连会尝试约 5 次
# （5/10/15/20/25 秒），全部失败才算「确定断开」；真实重启通常 1~3 分钟恢复。
# 0 表示关闭静默期（断线立即通知，旧行为）
DEFAULT_CONNECT_FAIL_NOTIFY_DELAY = 60
CONNECT_FAIL_NOTIFY_DELAY_MIN = 0
CONNECT_FAIL_NOTIFY_DELAY_MAX = 3600

# ---- 连通通知的「真启动」判定 ----

# 连通通知要表达的是「服务器启动了」，但鹊桥 WS 每次重连都会触发连接回调，
# 网络抖动、服务端卡顿、插件热重载都会连带触发。断线期间对服务器**游戏端口**
# 做 SLP 探测即可分辨：服务器仍在响应 = 只是隧道断了（抖动）；连不上 =
# 服务器确实下线过（真启动）。探测不到结论时（如几秒内就连回）退回断线时长。
DEFAULT_SLP_PORT = 25565
# 单次探测超时：3 秒足够本机/局域网握手，又不会把重连后的判定拖太久
CONNECT_NOTIFY_PROBE_TIMEOUT = 3.0
# 探测间隔与上限：最多约 30 秒一轮；一旦探测到「连不上」立即锁定结论，不再复探
CONNECT_NOTIFY_PROBE_INTERVAL = 5.0
CONNECT_NOTIFY_PROBE_MAX = 6
# 无探测结论时的兜底阈值：断线不足 30 秒一律视为抖动（实测 WS 抖动 <20 秒，
# 而服务端真实重启从关服到 Done 通常 1~3 分钟）
CONNECT_NOTIFY_MIN_DOWNTIME = 30.0

# ---- 免打扰（安静时段）----

# 可被免打扰静音的消息类型：key 入库/入配置，label 供前端与文档使用。
# 顺序即前端多选框顺序；新增项目时同步 pages/dashboard/index.html 的多选框
QUIET_ITEM_CHAT = "chat"
QUIET_ITEM_JOIN_LEAVE = "join_leave"
QUIET_ITEM_DEATH = "death"
QUIET_ITEM_ACHIEVEMENT = "achievement"
QUIET_ITEM_CONNECT = "connect"
QUIET_ITEM_CONNECT_FAIL = "connect_fail"
QUIET_HOURS_ITEMS: tuple[tuple[str, str], ...] = (
    (QUIET_ITEM_CHAT, "游戏聊天"),
    (QUIET_ITEM_JOIN_LEAVE, "玩家进出"),
    (QUIET_ITEM_DEATH, "死亡消息"),
    (QUIET_ITEM_ACHIEVEMENT, "成就消息"),
    (QUIET_ITEM_CONNECT, "连通通知"),
    (QUIET_ITEM_CONNECT_FAIL, "连接失败通知"),
)
QUIET_HOURS_ITEM_KEYS: tuple[str, ...] = tuple(key for key, _ in QUIET_HOURS_ITEMS)

# 免打扰默认关闭：时段落在深夜，开启即意味「夜里群里只剩聊天的声音」
DEFAULT_QUIET_HOURS_ENABLED = False
# 默认时段 23:00~08:00（跨零点）：按本地时间判断，起止相同视为未配置
DEFAULT_QUIET_HOURS_START = "23:00"
DEFAULT_QUIET_HOURS_END = "08:00"
# 默认只勾通知类（死亡 / 成就 / 连通 / 失败）：聊天与玩家进出默认不静音，
# 避免「一开免打扰就完全看不到群里在聊什么」，用户想全静音自己勾上即可
DEFAULT_QUIET_HOURS_ITEMS: list[str] = [
    QUIET_ITEM_DEATH,
    QUIET_ITEM_ACHIEVEMENT,
    QUIET_ITEM_CONNECT,
    QUIET_ITEM_CONNECT_FAIL,
]
# "HH:MM" 的匹配式由 models_config 解析时使用，这里只放默认与范围说明
QUIET_HOURS_TIME_PATTERN = r"^([01]?\d|2[0-3]):([0-5]\d)$"

# 平台名称映射的默认值：自带 aiocqhttp=QQ 示例，开箱即用。
# 用户在配置里删空该列表项即关闭改写（保留原始平台名）
DEFAULT_PLATFORM_NAMES: dict[str, str] = {"aiocqhttp": "QQ"}

# 服务器显示名称（display_name）留空时，{display_name} 占位符的默认展示内容。
# 对应配置项 display_name_default 的默认值；用户可改，显式清空则输出空串
DEFAULT_DISPLAY_NAME = "MC"

# ---- 转发回执 ----

# 转发到 MC 成功后给原消息的回执文案（mark_option: text）
MARK_TEXT_OK = "✅ 已转发到游戏内"

# 消息转发反馈的 Emoji 响应常量（QQ 表情 ID，mark_option: emoji 时使用）
EMOJI_OK_GESTURE = 124  # 👌
EMOJI_THUMBS_UP = 76  # 👍
EMOJI_LOVE = 66  # ❤️
EMOJI_ROSE = 63  # 🌹

# 给消息贴表情走的 OneBot 扩展接口（aiocqhttp `call_action` 动作名）
API_SET_MSG_EMOJI_LIKE = "set_msg_emoji_like"

# ---- ChatImage 图片转发 ----

# 游戏端渲染图片依赖 ChatImage 模组（https://github.com/kitUIN/ChatImage）：
# 图片以 [[CICode,url=...,name=...]] 代码广播进聊天栏，name 缺省用此名称
DEFAULT_CHATIMAGE_NAME = "图片"

# ChatImage 能解码的图片格式（官方「支持格式」段落：png / jpg / jpeg / jfif /
# gif / ico / bmp）。webp、avif 不在其中——图床产物是这些格式时游戏内不会
# 渲染出图片，图床检测因此把它们判为「受限」而不是「通过」
CHATIMAGE_SUPPORTED_FORMATS: tuple[str, ...] = (
    "png",
    "jpeg",
    "jfif",
    "gif",
    "ico",
    "bmp",
)

# 第三方图床上传超时（秒，对应 image_upload.timeout）
DEFAULT_IMAGE_UPLOAD_TIMEOUT = 30

# 内置图片 HTTP 服务的监听参数（对应 builtin_http 模板的 host/port 默认值）
DEFAULT_IMAGE_HTTP_HOST = "0.0.0.0"
DEFAULT_IMAGE_HTTP_PORT = 8765

# 内置图片 HTTP 服务的缓存参数：图片字节保留时长与最大条数。
# 协议端不给公开 URL 的图片经此服务转存后，玩家客户端从
# `{base_url}/img/<token>` 拉取；超时/超量条目在访问或登记时清理
IMAGE_HOST_TTL = 1800  # 30 分钟
IMAGE_HOST_MAX_IMAGES = 500

# ---- E33Chat 模组图片 ----

# E33Chat 自带图片上传：客户端把图传到图床（默认 uguu.se，可自定义）或服务端
# 媒体托管，聊天里留下图片标记。两种标记都要认：
#   [[CICode,url=...]]        与 ChatImage 共用（E33Chat 2.3.10+ 原生解析）
#   [[E33Emote,url=...]]      E33Chat 3.x 的无气泡表情
#   [[ChatUpgrade,url=...]]   第三方富文本模组
# 服务端媒体托管形态为 e33chat://media/<32 位十六进制>，图片实际落在服务端
# 媒体目录里，AstrBot 必须能读到该目录才能取出字节
E33CHAT_MEDIA_SCHEME = "e33chat://media/"
E33CHAT_MEDIA_MAX_FILE_BYTES = 8 * 1024 * 1024  # 与服务端单文件上限一致
DEFAULT_E33CHAT_IMAGE_MAX_EDGE = 320
E33CHAT_IMAGE_MAX_EDGE_MIN = 64
E33CHAT_IMAGE_MAX_EDGE_MAX = 2048

# ---- MC → 外部：游戏内图片转发 ----

# 游戏内聊天消息里的图片（ChatImage [[CICode,url=...]] 代码或直接贴出的图片链接）
# 下载/读取后作为图片消息转发到外部会话。以下为下载上限与超时
MAX_IMAGE_DOWNLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
IMAGE_DOWNLOAD_TIMEOUT = 15  # 秒

# ---- AI 对话的会话（UMO） ----

# 游戏内 AI 对话按哪个会话读写上下文。AstrBot 的对话历史以 UMO 为键存库，
# 游戏内聊天不经过 AstrBot 事件管道，因此由插件自己挑一个 UMO 去读写：
#   server：每台服务器一个独立 UMO（默认）——各服上下文互不干扰，
#           不与群聊共享，群里的 /new 也不会清掉游戏内的对话
#   group ：复用该服务器 target_sessions 的第一个群 UMO——与群共用同一份
#           上下文与人格，群内 /new 即可重置游戏侧
#   player：每个玩家一个 UMO——玩家之间上下文隔离，适合多人共服
AI_SESSION_MODE_SERVER = "server"
AI_SESSION_MODE_GROUP = "group"
AI_SESSION_MODE_PLAYER = "player"
AI_SESSION_MODES: tuple[str, ...] = (
    AI_SESSION_MODE_SERVER,
    AI_SESSION_MODE_GROUP,
    AI_SESSION_MODE_PLAYER,
)
DEFAULT_AI_SESSION_MODE = AI_SESSION_MODE_SERVER

# 上下文保留轮数（一问一答为一轮）：游戏内绕过了 AstrBot 的上下文管理，
# 不设上限会让历史无限增长并最终撑爆模型上下文。0 = 不限制（交给模型报错）
DEFAULT_AI_HISTORY_TURNS = 20
AI_HISTORY_TURNS_MIN = 0
AI_HISTORY_TURNS_MAX = 200

# 游戏内重置对话的两个入口：命中 AI 前缀后**整句**等于关键字才触发，语义
# 对齐 AstrBot 的 /new（新建对话并切过去）与 /reset（清空当前对话历史）。
# 两者独立配置，留空 = 关闭该入口；没配的人直接用 new / reset 即可
DEFAULT_AI_NEW_COMMAND = "new"
DEFAULT_AI_RESET_COMMAND = "reset"

# ---- 性能监控（TPS / 延迟） ----
# 监控采样按天分片持久化到 data_dir/monitor/<server>/YYYY-MM-DD.jsonl；
# TPS 通过 RCON 执行 TPS 指令获取（Bukkit 系 tps / forge tps / spark tps 等），
# 默认 "auto"：按 get_status / SLP / 实测指令多源识别的服务端品牌给出候选
# 指令并依次尝试（见 services/monitor.tps_command_candidates）；显式填写则固定使用。
# 延迟为鹊桥 API（get_status）往返耗时，无需服务端安装额外插件、无需 RCON。
DEFAULT_MONITOR_INTERVAL = 60  # 采集间隔（秒）
DEFAULT_MONITOR_RETENTION_DAYS = 7  # 历史采样保留天数，超出自动清理
DEFAULT_MONITOR_TPS_COMMAND = "auto"  # TPS 指令：auto=按服务端类型自动选择
# 延迟探测：直连服务器执行 SLP ping（默认 MC 端口 25565）。ping_host 留空时
# 从配置的 ws_url 解析主机（正向模式鹊桥与 MC 服务器同机，即服务器地址）
DEFAULT_MONITOR_PING_PORT = 25565
# 采集间隔下限：过小的间隔既加重服务器负担，也让图表难以阅读
MONITOR_MIN_INTERVAL = 10
# 实时模式（连续采样）频率：每 N 秒对当前服务器采样一次，
# 可配置（1~60 秒，默认 5 秒）
DEFAULT_MONITOR_REALTIME_INTERVAL = 5
MONITOR_REALTIME_MIN = 1
MONITOR_REALTIME_MAX = 60
# 互通终端默认加载最近几天的分片（含当天）：避免一次拉取 30 天全量。
# 属每台服务器独立配置：面板「互通终端」天数写入 conf 条目顶层（与
# enable_ai_chat 平级），Web API 拉日志时由前端按当前服务器传入
DEFAULT_TERMINAL_DAYS = 2
TERMINAL_DAYS_MIN = 0
TERMINAL_DAYS_MAX = 30

# 仪表盘「自动刷新」轮询间隔（秒）：服务器卡片状态与玩家列表的定时
# 刷新频率，可配置（10~3600 秒，默认 10；勾选自动刷新时生效）
DEFAULT_MONITOR_AUTO_REFRESH = 10
MONITOR_AUTO_REFRESH_MIN = 10
MONITOR_AUTO_REFRESH_MAX = 3600
# 延迟采样专用的 get_status 响应超时。比 API_TIMEOUT(10s) 更短：
# 延迟采不到时不值得为一个指标干等 10 秒（TPS 与状态另有来源）
MONITOR_API_TIMEOUT = 5
# 品牌识别与 TPS 指令试错的节流间隔（秒）：
# - 品牌未知时经 get_status 探测服务端类型，失败后隔这么久再试
# - auto 模式下全部候选 TPS 指令都执行失败后隔这么久再重试，避免为没有
#   TPS 指令的服务端（原版 / 未装 Spark 的 Fabric）每轮连发多条无效指令
MONITOR_BRAND_PROBE_RETRY_SECONDS = 300
MONITOR_TPS_RETRY_SECONDS = 300


def prefix_matches(prefix: str, text: str) -> bool:
    """判断文本是否以指定前缀触发（词边界感知，字母部分不区分大小写）。

    三个方向的前缀统一采用「**留空 = 全部命中**」：不填前缀即不设门槛，
    所有消息都算命中该方向。调用方据此实现「留空 = 全部转发 / 全部交给 AI」，
    不必再各自维护一套空值分支。

    短前缀（如 `ai`）若只做 `startswith` 会误伤同词头的正常发言：
    `aim 很高`、`airport` 都会被当成 AI 触发。因此当前缀以字母/数字结尾时，
    要求其后紧跟分隔符（空格）或行尾，避免把单词截断算作命中。

    纯字母前缀同时忽略大小写，让 `AI 你好` 与 `ai 你好` 等效。

    非字母数字结尾的前缀（如 `#`、`*`、`!`）本身已具备分隔作用，
    保持简单前缀匹配（`#你好` 直接命中，无需空格）。
    """
    if not prefix:
        # 留空 = 不设门槛：全部命中（统一三个方向的前缀语义）
        return True

    stripped = text.strip()
    if prefix[-1].isalnum():
        # 字母/数字结尾：忽略大小写比较，且要求词边界
        if not stripped.lower().startswith(prefix.lower()):
            return False
        rest = stripped[len(prefix) :]
        return not rest or not rest[0].isalnum()

    return stripped.startswith(prefix)


def strip_prefix(prefix: str, text: str) -> str:
    """去掉触发前缀，返回剩余内容（前缀未命中时原样返回）。

    前缀留空时没有可去掉的内容，原样返回（与 `prefix_matches` 的
    「留空 = 全部命中」配套：命中但不剥任何字符）。
    """
    if not prefix:
        return text.strip()
    stripped = text.strip()
    if prefix_matches(prefix, stripped):
        return stripped[len(prefix) :].strip()
    return stripped
