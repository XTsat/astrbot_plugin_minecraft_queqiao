"""离线逻辑自检：用桩替代 astrbot/websockets，验证纯逻辑（配置解析、事件模型、
转发与回声抑制、自定义指令、绑定持久化、端到端事件流）。

运行： python3 tests_offline.py
"""
import sys, types, os
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

astrbot = types.ModuleType("astrbot"); api = types.ModuleType("astrbot.api")
class _L:
    def info(self,*a): pass
    def warning(self,*a): pass
    def error(self,*a): pass
    def debug(self,*a): pass
api.logger=_L(); api.AstrBotConfig=dict
# 注意：真实 `astrbot.api` **不导出** Context（它在 astrbot.api.star）。
# 桩必须忠实反映这一点，否则会掩盖 "cannot import name 'Context'" 这类错误。
astrbot.api=api
sys.modules["astrbot"]=astrbot; sys.modules["astrbot.api"]=api
# astrbot.api.event 桩
ev = types.ModuleType("astrbot.api.event")
class AstrMessageEvent: pass
class MessageChain:
    def __init__(self, chain=None): self.chain = chain or []
ev.AstrMessageEvent = AstrMessageEvent
ev.MessageChain = MessageChain
class _Grp:
    def __init__(self, name): self.name = name
    def command(self, *a, **k):
        def deco(fn): return fn
        return deco
class _Filter:
    PermissionType = types.SimpleNamespace(ADMIN="admin")
    EventMessageType = types.SimpleNamespace(ALL="all")
    def command_group(self, name):
        def deco(fn): return _Grp(name)
        return deco
    def command(self, *a, **k):
        def deco(fn): return fn
        return deco
    def permission_type(self, *a, **k):
        def deco(fn): return fn
        return deco
    def event_message_type(self, *a, **k):
        def deco(fn): return fn
        return deco
ev.filter = _Filter()
sys.modules["astrbot.api.event"] = ev
mc = types.ModuleType("astrbot.api.message_components")
class Plain:
    def __init__(self, text=""): self.text = text
mc.Plain = Plain
sys.modules["astrbot.api.message_components"] = mc
st = types.ModuleType("astrbot.api.star")
class Star: pass
class Context: pass
st.Star = Star; st.Context = Context
st.StarTools = types.SimpleNamespace(get_data_dir=lambda *a: "/tmp")
st.register = lambda *a, **k: (lambda c: c)
sys.modules["astrbot.api.star"] = st
core = types.ModuleType("astrbot.core"); core.__path__=[]
sys.modules["astrbot.core"] = core
sc = types.ModuleType("astrbot.core.star"); sc.__path__=[]
sys.modules["astrbot.core.star"] = sc
f = types.ModuleType("astrbot.core.star.filter"); f.__path__=[]
sys.modules["astrbot.core.star.filter"] = f
cmd = types.ModuleType("astrbot.core.star.filter.command")
class GreedyStr: pass
cmd.GreedyStr = GreedyStr
sys.modules["astrbot.core.star.filter.command"] = cmd
ws=types.ModuleType("websockets"); exc=types.ModuleType("websockets.exceptions")
class _CC(Exception): code=1000
exc.ConnectionClosed=_CC; exc.InvalidStatus=type("InvalidStatus",(Exception,),{})
ws.exceptions=exc; ws.serve=lambda *a,**k:None; ws.connect=lambda *a,**k:None
sys.modules["websockets"]=ws; sys.modules["websockets.exceptions"]=exc

import importlib.util
pkg = "astrbot_plugin_minecraft_queqiao"
import types as _t
# 以包形式导入：把当前目录注册为包
spec = importlib.util.spec_from_file_location(pkg, os.path.join(os.getcwd(), "__init__.py"),
        submodule_search_locations=[os.getcwd()])
mod = importlib.util.module_from_spec(spec); sys.modules[pkg]=mod; spec.loader.exec_module(mod)

from astrbot_plugin_minecraft_queqiao.services.message_bridge import component_to_text, MessageBridge
from astrbot_plugin_minecraft_queqiao.services.binding import BindingService
from astrbot_plugin_minecraft_queqiao.handlers.commands import CommandHandler
from astrbot_plugin_minecraft_queqiao.core.rcon_client import RconClient
from astrbot_plugin_minecraft_queqiao.core.models import QueQiaoEvent
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig
import asyncio, tempfile, pathlib, json

print("=== 5. 富文本剥离 ===")
assert component_to_text('{"text":"Hello","color":"light_purple"}') == "Hello"
assert component_to_text("§aHello") == "Hello"
assert component_to_text("plain text") == "plain text"
assert component_to_text('[{"text":"A"},{"text":"B"}]') == "AB"
print("OK")

print("=== 6. 自定义指令占位符 ===")
class _SM:
    def get(self, s): return None
    def all(self): return []
h = CommandHandler(_SM(), None, None)
h.register_custom_commands("S", ["tp <&X&> <&y&> <&z&><<>>tp {sender} <&X&> <&y&> <&z&>",
                                 "head <&player&><<>>give {sender} minecraft:player_head"])
assert h.match_custom_command("S","tp 114 514 1919") == "tp {sender} 114 514 1919"
assert h.match_custom_command("S","head Notch") == "give {sender} minecraft:player_head"
assert h.match_custom_command("S","tp 114") is None
assert h.match_custom_command("S","unknown cmd") is None
print("OK  多参数按位置替换，{sender} 保留给运行时，不匹配返回 None")

print("=== 7. RCON list 解析 ===")
assert RconClient.parse_player_list("There are 2 of a max of 20 players online: Alice, Bob")==["Alice","Bob"]
assert RconClient.parse_player_list("There are 0 of a max of 20 players online: ")==[]
assert RconClient.parse_player_list(None)==[]
print("OK")

print("=== 8. 回声抑制 + 转发判定 ===")
class _Ctx:
    async def send_message(self,*a,**k): return True
br = MessageBridge(_Ctx())
cfg = ServerConfig.from_dict({"server":{"server_id":"S"},
    "message":{"target_sessions":["umo:GroupMessage:1"],"auto_forward_prefix":"*",
               "forward_chat_to_astrbot":True,"forward_join_leave_to_astrbot":False}})
br.register_server(cfg)
assert br.servers_for_session("umo:GroupMessage:1")[0][0] == "S"
assert br.should_relay(cfg,"*hello") is True
assert br.should_relay(cfg,"no prefix") is False
assert br.strip_relay_prefix(cfg,"*hello") == "hello"
# 转发前缀留空 = 全部转发（与 AI 前缀「留空即不触发」语义相反，属刻意设计）
cfg_empty_prefix = ServerConfig.from_dict({"server":{"server_id":"S2"},
    "message":{"target_sessions":["umo:GroupMessage:1"]}})
assert cfg_empty_prefix.auto_forward_prefix == ""
assert br.should_relay(cfg_empty_prefix,"no prefix") is True
assert br.should_relay(cfg_empty_prefix,"*hello") is True
assert br.strip_relay_prefix(cfg_empty_prefix,"普通消息") == "普通消息"
chat = QueQiaoEvent.from_dict({"event_name":"PlayerChatEvent","message":"hello","player":{"nickname":"A"}})
join = QueQiaoEvent.from_dict({"event_name":"PlayerJoinEvent","player":{"nickname":"A"}})
assert br.should_forward(cfg, chat) is True
assert br.should_forward(cfg, join) is False
br.mark_forwarded("S","hello")
assert asyncio.run(br.forward_event("S", cfg, chat)) is False
print("OK  前缀过滤/事件开关/回声抑制 均正确")

print("=== 9. 绑定服务持久化（原子写） ===")
d = pathlib.Path(tempfile.mkdtemp())
b = BindingService(d)
asyncio.run(b.bind("umo1","Steve"))
assert b.get("umo1") == "Steve"
b2 = BindingService(d); b2.load(); assert b2.get("umo1")=="Steve"
assert json.loads((d/"bindings.json").read_text(encoding="utf-8")) == {"umo1":"Steve"}
assert asyncio.run(b2.unbind("umo1")) is True
b3 = BindingService(d); b3.load(); assert b3.get("umo1")==""
print("OK  绑定写入/重新加载/解绑 正确，utf-8 明文 JSON")

print("=== 10. 命令黑白名单 + 配置解析 ===")
c = ServerConfig.from_dict({"server":{"server_id":"T","ws_mode":"reverse","reverse_port":"9090",
     "access_token":"tok"},"message":{"target_sessions":'["a:b:1"]'},
     "cmd":{"cmd_list":"say, list","rcon_fallback":{"enabled":"true","port":"25575"}}})
assert c.is_reverse and c.reverse_port==9090 and c.target_sessions==["a:b:1"]
assert c.cmd_list==["say","list"] and c.rcon_fallback_enabled and c.rcon_port==25575
assert c.is_command_allowed("say hi") and not c.is_command_allowed("op x")
print("OK")

print("\n全部离线逻辑校验通过 ✅")

print("=== 11. 端到端：鹊桥事件 -> 会话转发 ===")
sent = []
class _Ctx2:
    async def send_message(self, umo, chain):
        sent.append((umo, chain.chain[0].text)); return True
br2 = MessageBridge(_Ctx2())
cfg2 = ServerConfig.from_dict({"server":{"server_id":"Srv"},
  "message":{"target_sessions":["aiocqhttp:GroupMessage:123"],"forward_chat_to_astrbot":True,
             "forward_join_leave_to_astrbot":True,"forward_death_to_astrbot":True,
             "forward_chat_format":"<{player}> {message}"}})
br2.register_server(cfg2)
async def _run():
    await br2.forward_event("Srv", cfg2, QueQiaoEvent.from_dict(
        {"post_type":"message","event_name":"PlayerChatEvent",
         "raw_message":'{"text":"大家好","color":"white"}',"message":"大家好",
         "player":{"nickname":"Steve"}}))
    await br2.forward_event("Srv", cfg2, QueQiaoEvent.from_dict(
        {"post_type":"notice","event_name":"PlayerJoinEvent","player":{"nickname":"Alex"}}))
    await br2.forward_event("Srv", cfg2, QueQiaoEvent.from_dict(
        {"post_type":"notice","event_name":"PlayerDeathEvent",
         "death":{"text":"Steve was slain by Zombie"},"player":{"nickname":"Steve"}}))
asyncio.run(_run())
for umo, text in sent: print("   ->", umo, "|", text)
assert sent[0][1] == "<Steve> 大家好", sent[0][1]
assert "🟢 Alex 加入了服务器" == sent[1][1]
assert sent[2][1] == "💀 Steve was slain by Zombie"
print("OK  聊天(富文本剥离)/加入/死亡 三类事件均正确转发")

print("=== 12. main.py 可导入 ===")
import astrbot_plugin_minecraft_queqiao.main as m
assert hasattr(m, "MinecraftQueQiaoPlugin")
print("OK  插件主类加载正常:", m.MinecraftQueQiaoPlugin.__name__)

print("=== 13. 前缀语义：AI 与互通互斥 ===")
from astrbot_plugin_minecraft_queqiao.main import MinecraftQueQiaoPlugin as P
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as SC

# 默认配置：互通开、AI 开、两个前缀独立（转发前缀默认留空 = 全部转发，
# 因为转发生效前必须先绑定 target_sessions，默认放开不会外溢到未绑定会话）
d = SC.from_dict({})
assert d.enable_ai_chat is True and d.forward_chat_to_astrbot is True
assert d.ai_chat_prefix == "ai" and d.auto_forward_prefix == ""
assert d.prefixes_conflict is False, "默认前缀不应冲突"

# 命中 AI 前缀 -> 走 AI，不转发
cfg_ai = SC.from_dict({"server":{"server_id":"S"},"ai_chat_prefix":"ai"})
chat_ai = QueQiaoEvent.from_dict({"event_name":"PlayerChatEvent",
    "message":"ai 你好","player":{"nickname":"A"}})
chat_bare = QueQiaoEvent.from_dict({"event_name":"PlayerChatEvent",
    "message":"ai","player":{"nickname":"A"}})
# 词边界：短前缀不应误伤同词头的正常发言
chat_aim = QueQiaoEvent.from_dict({"event_name":"PlayerChatEvent",
    "message":"aim 很高","player":{"nickname":"A"}})
chat_airport = QueQiaoEvent.from_dict({"event_name":"PlayerChatEvent",
    "message":"airport 到了","player":{"nickname":"A"}})
chat_norm = QueQiaoEvent.from_dict({"event_name":"PlayerChatEvent",
    "message":"大家好","player":{"nickname":"A"}})
assert P._match_ai_prefix(cfg_ai, chat_ai) is True
assert P._match_ai_prefix(cfg_ai, chat_bare) is True, "单独一个 ai 应触发"
assert P._match_ai_prefix(cfg_ai, chat_aim) is False, "aim 不应误触发 AI"
assert P._match_ai_prefix(cfg_ai, chat_airport) is False, "airport 不应误触发 AI"
assert P._match_ai_prefix(cfg_ai, chat_norm) is False, "普通聊天不应触发 AI"
# 字母前缀忽略大小写：AI / Ai / ai 等效
assert P._match_ai_prefix(cfg_ai, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"AI 你好"})) is True
assert P._strip_ai_prefix(cfg_ai, "ai 你好") == "你好"
assert P._strip_ai_prefix(cfg_ai, "AI 你好") == "你好"

# 前缀以非字母数字结尾时（如 `!`）无需分隔符即可命中
cfg_bang = SC.from_dict({"server":{"server_id":"S"},"ai_chat_prefix":"!"})
assert P._match_ai_prefix(cfg_bang, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"!你好"})) is True
# 以字母结尾的前缀（如 `#ai`）同样要求词边界
cfg_hash = SC.from_dict({"server":{"server_id":"S"},"ai_chat_prefix":"#ai"})
assert P._match_ai_prefix(cfg_hash, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"#aihi"})) is False
assert P._match_ai_prefix(cfg_hash, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"#ai 你好"})) is True

# AI 前缀留空 -> 不触发（避免全量投喂 LLM）
cfg_empty = SC.from_dict({"server":{"server_id":"S"},"ai_chat_prefix":""})
assert P._match_ai_prefix(cfg_empty, chat_norm) is False

# 前缀冲突检测：互相包含即告警
assert SC.from_dict({"ai_chat_prefix":"*","message":{"auto_forward_prefix":"*"}}).prefixes_conflict
assert SC.from_dict({"ai_chat_prefix":"a","message":{"auto_forward_prefix":"ab"}}).prefixes_conflict
assert SC.from_dict({"ai_chat_prefix":"#ai","message":{"auto_forward_prefix":"*"}}).prefixes_conflict is False
print("OK  AI 前缀命中走 AI、普通聊天走互通、空前缀不触发、冲突可检测")

print("=== 14. 端到端：同一条游戏内消息只走一条路径 ===")
sent2 = []
class _Ctx3:
    async def send_message(self, umo, chain):
        sent2.append(chain.chain[0].text); return True
import astrbot_plugin_minecraft_queqiao.services.message_bridge as mb_mod
br3 = mb_mod.MessageBridge(_Ctx3())
cfg3 = SC.from_dict({"server":{"server_id":"Srv2"},"ai_chat_prefix":"#ai",
    "message":{"target_sessions":["umo:GroupMessage:9"],"forward_chat_to_astrbot":True}})
br3.register_server(cfg3)
async def _run3():
    # 普通聊天 -> 应转发到群
    await br3.forward_event("Srv2", cfg3, chat_norm)
    # AI 消息 -> 在 main 层就被拦截，不会到达 bridge
asyncio.run(_run3())
# 默认格式 [{server}]{player}: {message}：{server} 留空时取显示名称默认值 MC
assert sent2 == ["[MC]A: 大家好"], sent2
print("OK  普通聊天转发到群:", sent2)

print("\n全部离线逻辑校验通过 ✅（含前缀语义）")


print("=== 15. AI 触发方式：仅聊天前缀 ===")
d2 = SC.from_dict({})
assert d2.enable_ai_chat is True and d2.ai_chat_prefix == "ai"
# 相关配置项不应存在
assert not hasattr(d2, "ai_command_enabled"), "不应残留 ai_command_enabled"
assert not hasattr(d2, "ai_command_name"), "不应残留 ai_command_name"
assert not hasattr(d2, "resolved_ai_command"), "不应残留 resolved_ai_command"
# constants 不应导出 match_ai_command
import astrbot_plugin_minecraft_queqiao.core.constants as _c
assert not hasattr(_c, "match_ai_command"), "不应残留 match_ai_command"

cfg = SC.from_dict({"server":{"server_id":"S"},"ai_chat_prefix":"ai"})
ev_chat = QueQiaoEvent.from_dict({"post_type":"message","event_name":"PlayerChatEvent",
    "message":"ai 你好","player":{"nickname":"A"}})
# 以 / 开头的聊天内容同样不触发
ev_slash = QueQiaoEvent.from_dict({"post_type":"message","event_name":"PlayerChatEvent",
    "message":"/ai 你好","player":{"nickname":"A"}})
# 指令事件一律不触发 AI
ev_cmd = QueQiaoEvent.from_dict({"post_type":"message","event_name":"PlayerCommandEvent",
    "command":"/ai 你好","player":{"nickname":"A"}})
ev_join = QueQiaoEvent.from_dict({"event_name":"PlayerJoinEvent","player":{"nickname":"A"}})

assert P._resolve_ai_question(cfg, ev_chat) == "你好"
assert P._resolve_ai_question(cfg, ev_slash) is None, "指令式内容不应触发"
assert P._resolve_ai_question(cfg, ev_cmd) is None, "指令事件不应触发 AI"
assert P._resolve_ai_question(cfg, ev_join) is None
# 空内容不发请求
assert P._resolve_ai_question(cfg, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"ai"})) is None
# 关掉总开关后不触发
cfg_off = SC.from_dict({"server":{"server_id":"S"},"enable_ai_chat":False})
assert P._resolve_ai_question(cfg_off, ev_chat) is None
print("OK  仅聊天前缀触发、指令事件不触发、旧配置项已彻底移除")

print("\n全部离线逻辑校验通过 ✅（含 AI 触发方式）")

print("=== 16. 导入路径与真实 AstrBot API 对齐 ===")
import astrbot.api as _api, astrbot.api.star as _star
# 桩的契约：astrbot.api 不提供 Context（真实情况亦然），Context 只在 astrbot.api.star
assert not hasattr(_api, "Context"), "桩失真：astrbot.api 不应有 Context"
assert hasattr(_star, "Context"), "Context 必须在 astrbot.api.star"
for _n in ("Star", "StarTools", "register"):
    assert hasattr(_star, _n), f"astrbot.api.star 缺少 {_n}"

# 静态核对 main.py 的实际导入语句，防止再写错来源模块
import re as _re, pathlib as _pathlib
_MAIN = _pathlib.Path(__file__).with_name("main.py").read_text(encoding="utf-8")
_imports = dict(_re.findall(r"^from (astrbot[\w\.]*) import ([^\n]+)$", _MAIN, _re.M))
assert "Context" in _imports.get("astrbot.api.star", ""), \
    "Context 必须从 astrbot.api.star 导入（astrbot.api 没有它）"
assert "Context" not in _imports.get("astrbot.api", ""), \
    "astrbot.api 不导出 Context，不能从那里导入"
assert "AstrBotConfig" in _imports.get("astrbot.api", ""), \
    "AstrBotConfig 应从 astrbot.api 导入"
print("OK  Context 来自 astrbot.api.star、AstrBotConfig 来自 astrbot.api，桩与真实 API 一致")

print("\n全部离线逻辑校验通过 ✅（含导入路径校验）")

print("=== 17. 目标会话位于模板项顶层（紧随 enabled） ===")
import json as _json
from core.models_config import ServerConfig as _SC

# (a) 新位置：模板项顶层 target_sessions 必须被正确解析
_c = _SC.from_dict({"enabled": True, "target_sessions": ["aiocqhttp:GroupMessage:123"]})
assert _c.target_sessions == ["aiocqhttp:GroupMessage:123"], _c.target_sessions

# (b) 兼容旧位置：早期写在 message 子对象内仍要生效，防止旧配置失效
_c = _SC.from_dict({"message": {"target_sessions": ["aiocqhttp:GroupMessage:456"]}})
assert _c.target_sessions == ["aiocqhttp:GroupMessage:456"], _c.target_sessions

# (c) 两处都存在时以顶层为准
_c = _SC.from_dict({
    "target_sessions": ["aiocqhttp:GroupMessage:new"],
    "message": {"target_sessions": ["aiocqhttp:GroupMessage:old"]},
})
assert _c.target_sessions == ["aiocqhttp:GroupMessage:new"], _c.target_sessions

# (d) 两处都没有 → 空列表（插件仍能连接，只是无处转发）
assert _SC.from_dict({}).target_sessions == []

# (e) 兼容字符串形态（WebUI 输入框可能给 JSON 串或逗号分隔）
_c = _SC.from_dict({"target_sessions": "aiocqhttp:GroupMessage:1,aiocqhttp:GroupMessage:2"})
assert _c.target_sessions == ["aiocqhttp:GroupMessage:1", "aiocqhttp:GroupMessage:2"], _c.target_sessions

# (f) schema 结构守卫：target_sessions 必须在模板项顶层、紧随 enabled 之后，
#     且 message 子对象内不得残留同名键（否则 WebUI 会出现两个同名输入框）
_schema = _json.loads(_pathlib.Path(__file__).with_name("_conf_schema.json").read_text(encoding="utf-8"))
_items = _schema["mc_servers"]["templates"]["server"]["items"]
_keys = list(_items.keys())
assert "target_sessions" in _items, "模板项顶层缺少 target_sessions"
assert _keys.index("target_sessions") == _keys.index("enabled") + 1, \
    f"target_sessions 必须紧跟 enabled 之后，实际顺序: {_keys}"
assert "target_sessions" not in _items["message"]["items"], \
    "message 子对象内不应残留 target_sessions"
print("OK  新位置生效、旧位置兼容、顶层优先、schema 顺序正确且无重复键")

print("\n全部离线逻辑校验通过 ✅（含目标会话位置）")

print("=== 18. 转发回执（mark_option） ===")
import asyncio as _asyncio
import astrbot_plugin_minecraft_queqiao.services.message_bridge as _mb_mod
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _S2
_MB = _mb_mod.MessageBridge

class _Bot:
    """模拟 aiocqhttp 客户端：真实入口是 call_action(action, **params)。"""
    def __init__(self, supports=True, fail=False):
        self.calls = []
        self._supports = supports
        self._fail = fail
    async def call_action(self, action, **params):
        if not self._supports or action != "set_msg_emoji_like":
            raise RuntimeError(f"unsupported action: {action}")
        if self._fail:
            raise RuntimeError("boom")
        self.calls.append((params.get("message_id"), params.get("emoji_id")))

class _MsgObj:
    def __init__(self, mid): self.message_id = mid

class _Ev:
    def __init__(self, bot, mid="12345"):
        self.bot = bot
        self.message_obj = _MsgObj(mid)
        self.sent = []
    async def send(self, chain): self.sent.append(chain)

def _run(coro): return _asyncio.new_event_loop().run_until_complete(coro)

_bridge = _MB(context=None)

# (a) emoji 模式：走平台接口贴表情，且不额外发文本
_bot = _Bot(); _ev = _Ev(_bot)
cfg = _S2.from_dict({"message": {"mark_option": "emoji"}})
assert cfg.mark_option == "emoji"
_run(_bridge.mark_relayed(_ev, cfg))
assert _bot.calls == [("12345", "124")], _bot.calls   # 默认 👌 = EMOJI_OK_GESTURE(124)
assert _ev.sent == [], "emoji 模式不应再发文本"

# (b) text 模式：发一条 ✅ 文本，且不贴表情
_bot2 = _Bot(); _ev2 = _Ev(_bot2)
cfg2 = _S2.from_dict({"message": {"mark_option": "text"}})
_run(_bridge.mark_relayed(_ev2, cfg2))
assert len(_ev2.sent) == 1, _ev2.sent
assert _ev2.sent[0].chain[0].text.startswith("✅"), _ev2.sent[0].chain[0].text
assert _bot2.calls == [], "text 模式不应贴表情"

# (c) none 模式：什么都不做
_bot3 = _Bot(); _ev3 = _Ev(_bot3)
_run(_bridge.mark_relayed(_ev3, _S2.from_dict({"message": {"mark_option": "none"}})))
assert _bot3.calls == [] and _ev3.sent == []

# (d) 平台不支持（无 bot / 无接口）→ 静默跳过，且**不**回退成文本刷屏
_ev4 = _Ev(bot=None)
_run(_bridge.mark_relayed(_ev4, _S2.from_dict({"message": {"mark_option": "emoji"}})))
assert _ev4.sent == [], "不支持的平台不应回退成文本"
_ev5 = _Ev(_Bot(supports=False))
_run(_bridge.mark_relayed(_ev5, _S2.from_dict({"message": {"mark_option": "emoji"}})))
assert _ev5.sent == []

# (e) 贴表情抛异常不得向上传播（回执失败不能影响转发）
_ev6 = _Ev(_Bot(fail=True))
_run(_bridge.mark_relayed(_ev6, _S2.from_dict({"message": {"mark_option": "emoji"}})))

# (f) 非法值回落到默认 emoji
assert _S2.from_dict({"message": {"mark_option": "bogus"}}).mark_option == "emoji"

# (g) 自定义回执表情 ID：配置后必须逐字使用用户填的 ID
_bot7 = _Bot(); _ev7 = _Ev(_bot7)
cfg7 = _S2.from_dict({"message": {"mark_option": "emoji", "mark_emoji_id": "2705"}})
assert cfg7.mark_emoji_id == 2705
_run(_bridge.mark_relayed(_ev7, cfg7))
assert _bot7.calls == [("12345", "2705")], _bot7.calls

# (h) 表情 ID 缺省/非法/数字形态 → 一律安全回落到默认 👌(124)
for raw, expect in [(None, 124), ("", 124), ("abc", 124), (76, 76), ("76", 76), (124, 124)]:
    payload = {} if raw is None else {"mark_emoji_id": raw}
    got = _S2.from_dict({"message": payload}).mark_emoji_id
    assert got == expect, (raw, got)
from astrbot_plugin_minecraft_queqiao.core.constants import (
    EMOJI_LOVE,
    EMOJI_OK_GESTURE,
    EMOJI_ROSE,
    EMOJI_THUMBS_UP,
)
assert (EMOJI_OK_GESTURE, EMOJI_THUMBS_UP, EMOJI_LOVE, EMOJI_ROSE) == (124, 76, 66, 63), \
    (EMOJI_OK_GESTURE, EMOJI_THUMBS_UP, EMOJI_LOVE, EMOJI_ROSE)
print("OK  emoji 贴表情 / text 文本 / none 静默，不支持平台与异常均安全降级")
print("OK  回执表情 ID 可配置（默认 124 👌），非法输入回落默认值；"
      "表情常量 = 👌124 / 👍76 / ❤️66 / 🌹63")

print("\n全部离线逻辑校验通过 ✅（含转发回执）")

print("=== 19. 成就文本降级链（display_text / display_name） ===")
from astrbot_plugin_minecraft_queqiao.core.models import QueQiaoAchievement as _Ach

# (***) 实测 payload 回归：鹊桥推送的字段名是 `translation`，**不是**文档写的 `translate`。
# 曾因只读 `translate` 导致真实事件恒为空，进而整条成就消息丢失。
# 此断言钉死实测形态，防止再被文档带偏。
_REAL = {
    "key": "minecraft:story/lava_bucket",
    "display": {
        "title": {"key": "advancements.story.lava_bucket.title", "args": [], "text": "Hot Stuff"},
        "description": {"key": "advancements.story.lava_bucket.description", "args": [],
                        "text": "Fill a Bucket with lava"},
        "frame": "task",
    },
    "translation": {
        "key": "chat.type.advancement.task",
        "args": [
            {"key": None, "args": None, "text": "XTxiaotong"},
            {"key": "chat.square_brackets",
             "args": [{"key": "advancements.story.lava_bucket.title", "args": [],
                       "text": "Hot Stuff"}],
             "text": "[Hot Stuff]"},
        ],
        "text": "XTxiaotong has made the advancement [Hot Stuff]",
    },
}
_r = _Ach.from_dict(_REAL)
assert _r.translate.text == "XTxiaotong has made the advancement [Hot Stuff]", _r.translate.text
assert _r.display_text == "XTxiaotong has made the advancement [Hot Stuff]", _r.display_text
assert _r.key == "minecraft:story/lava_bucket", _r.key
assert _r.frame == "task", _r.frame

# 文档写法 `translate` 仍需兼容（老版本鹊桥/其它实现）
_r_doc = _Ach.from_dict({"key": "k", "translate": {"text": "旧字段写法"}})
assert _r_doc.translate.text == "旧字段写法", _r_doc.translate.text

# (a) 未开启翻译：translation 是空壳，但 display.title 有值 → 必须取到成就名。
_a1 = _Ach.from_dict({
    "key": "minecraft:husbandry/sweet_dreams",
    "display": {"title": "Sweet Dreams", "frame": "goal"},
    "translate": {"key": "chat.type.advancement.goal", "args": [], "text": ""},
})
assert _a1.display_text == "Sweet Dreams", _a1.display_text

# (b) 0.4.1+ 开启翻译：优先整句事件文本
_a2 = _Ach.from_dict({"key": "k", "translate": {"text": "A 达成了进度 [甜美的梦]"}})
assert _a2.display_text == "A 达成了进度 [甜美的梦]", _a2.display_text

# (c) 0.4.0- 旧版：回退 text（0.4.1+ 已移除该字段，但仍需兼容老版本鹊桥）
_a3 = _Ach.from_dict({"key": "k", "text": "A has made the advancement [Sweet Dreams]"})
assert _a3.display_text == "A has made the advancement [Sweet Dreams]", _a3.display_text

# (d) Spigot 仅含 key：display_text 为空（调用方据此走 display_name 兜底）
_a4 = _Ach.from_dict({"key": "minecraft:husbandry/sweet_dreams"})
assert _a4.display_text == "", _a4.display_text
assert _a4.display_name == "minecraft:husbandry/sweet_dreams", _a4.display_name

# (e) title 是 Translate 空壳 → 回落翻译键，仍好过空串
_a5 = _Ach.from_dict({"key": "k", "display": {
    "title": {"key": "advancements.husbandry.sweet_dreams.title", "args": [], "text": ""}}})
assert _a5.title == "advancements.husbandry.sweet_dreams.title", _a5.title

# (f) 优先级：display_name 取 title 优先于整句文本（它只要「成就叫什么」）
_a6 = _Ach.from_dict({"key": "k", "text": "整句事件文本",
                      "display": {"title": "Sweet Dreams", "frame": "goal"}})
assert _a6.display_name == "Sweet Dreams", _a6.display_name
assert _a6.display_text == "整句事件文本", _a6.display_text

# (g) 畸形输入不得抛异常（防御式解析契约）
for _bad in (None, [], "str", 42, {"display": "not-a-dict"}, {"display": {"title": None}}):
    _Ach.from_dict(_bad)
print("OK  translate.text / text / display.title / key 四级降级，畸形输入安全")

# (h) 端到端：转发文案不得再出现无信息量的「达成成就」
_bcfg = _S2.from_dict({"server": {"server_id": "S"},
                       "message": {"target_sessions": ["umo:GroupMessage:1"],
                                   "forward_achievement_to_astrbot": True}})
_br = _MB(context=None)
_ev_ach = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "post_type": "notice",
    "player": {"nickname": "XTxiaotong"},
    "achievement": {"key": "minecraft:husbandry/sweet_dreams",
                    "display": {"title": "Sweet Dreams", "frame": "goal"}}})
_text = _br.format_event(_bcfg, _ev_ach)
assert _text == "🏆 XTxiaotong 达成了成就 Sweet Dreams", _text
assert "Sweet Dreams" in _text, _text

# 玩家名兜底：连成就信息都没有时才用「<玩家> 达成了成就」
_ev_bare = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "player": {"nickname": "XTxiaotong"},
    "achievement": {}})
_bare = _br.format_event(_bcfg, _ev_bare)
assert _bare == "🏆 XTxiaotong 达成了成就", _bare

# 未开翻译 + display.title：成就名有了但整句不含玩家名 → 必须补上玩家名
# （线上曾出现「🏆 Getting an Upgrade」缺名字）
_ev_nick = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "player": {"nickname": "XTxiaotong"},
    "achievement": {"key": "minecraft:story/upgrade_tools",
                    "display": {"title": {"text": "Getting an Upgrade",
                                          "key": "advancements.story.upgrade_tools.title",
                                          "args": []},
                                "frame": "task"}}})
_nick = _br.format_event(_bcfg, _ev_nick)
assert _nick == "🏆 XTxiaotong 达成了成就 Getting an Upgrade", _nick

# 开翻译：整句已含玩家名 → 不得重复拼接
_ev_tr = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "player": {"nickname": "XTxiaotong"},
    "achievement": {"key": "k", "translation": {
        "key": "chat.type.advancement.task", "args": [],
        "text": "XTxiaotong has made the advancement [Hot Stuff]"}}})
_tr = _br.format_event(_bcfg, _ev_tr)
assert _tr == "🏆 XTxiaotong has made the advancement [Hot Stuff]", _tr
assert _tr.count("XTxiaotong") == 1, _tr   # 关键：不重复

# should_forward 仍受开关控制（关闭时不转发，避免兜底文案掩盖配置问题）
_off = _S2.from_dict({"server": {"server_id": "S"},
                      "message": {"target_sessions": ["umo:GroupMessage:1"],
                                  "forward_achievement_to_astrbot": False}})
assert _br.should_forward(_off, _ev_ach) is False
assert _br.should_forward(_bcfg, _ev_ach) is True
print("OK  未开翻译时补玩家名（🏆 XTxiaotong 达成了成就 Getting an Upgrade）")
print("OK  开翻译时整句已含玩家名，判重不重复拼接")
print("OK  成就转发开关仍生效（关闭时不转发）")

print("\n全部离线逻辑校验通过 ✅（含成就文本降级链）")

print("=== 20. 服务器显示名称与格式占位符 ===")
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _S3
from astrbot_plugin_minecraft_queqiao.services.message_bridge import MessageBridge as _MB3

# (a) 取值链必须区分开：
#     server_label  <- 消息格式 {server}：server_name → server_name_default（默认 MC）→ 空串
#     display_name  <- 状态/列表文案：同链再回退 server_id / 未知
_sn = _S3.from_dict({"server": {"server_id": "survival", "server_name": "生存服"}})
assert _sn.server_name == "生存服"
assert _sn.server_label == "生存服" and _sn.display_name == "生存服"
# server_name 优先级最高，永远压过默认值
assert _S3.from_dict({"server": {"server_id": "s", "server_name": "生存服",
    "server_name_default": "MC2"}}).server_label == "生存服"
# 什么都不填：{server} 用默认值 MC（线上反馈的期望效果），状态/列表同链取 MC
_sn2 = _S3.from_dict({"server": {"server_id": "survival"}})
assert _sn2.server_name == ""
assert _sn2.server_label == "MC", f"留空应取默认值 MC，实际 {_sn2.server_label!r}"
assert _sn2.display_name == "MC"
# 默认值可自定义
assert _S3.from_dict({"server": {"server_id": "s", "server_name_default": "本服"}})\
    .server_label == "本服"
# 显式清空默认值（server_name_default=""）才输出空串——唯一的无前缀途径
_sn3 = _S3.from_dict({"server": {"server_id": "s", "server_name_default": ""}})
assert _sn3.server_label == ""
assert _sn3.display_name == "s"  # label 空时孤立文案回退 server_id
# 默认配置与 conf 模板对齐（server_id 缺省回落 Server）；
# 「未知」仅在 label 与 server_id 全空时出现（该配置会被 main 层跳过并告警）
assert _S3.from_dict({}).server_label == "MC" and _S3.from_dict({}).display_name == "MC"
assert _S3.from_dict({"server": {"server_id": "", "server_name_default": ""}})\
    .display_name == "未知"
# 显示名称只影响展示，不得污染握手 Header（x-self-name 必须仍是 server_id）
assert _sn.forward_headers["x-self-name"] == "survival", _sn.forward_headers
# 纯空白的 server_name 视为未填写 -> 走默认值
assert _S3.from_dict({"server": {"server_id": "s", "server_name": "   "}}).server_label == "MC"
# 纯空白的默认值视为已清空 -> 空串
assert _S3.from_dict({"server": {"server_id": "s", "server_name_default": "  "}})\
    .server_label == ""
# 非字符串形态（WebUI 误填数字）也要安全收敛
assert _S3.from_dict({"server": {"server_id": "s", "server_name": 123}}).server_label == "123"
assert _S3.from_dict({"server": {"server_id": "s", "server_name_default": 66}})\
    .server_label == "66"

# (b) MC → 外部：{server} 取显示名称（中文可直接渲染）
_sent3 = []
class _Ctx4:
    async def send_message(self, umo, chain):
        _sent3.append(chain.chain[0].text); return True
_br4 = _MB3(_Ctx4())
_cfg4 = _S3.from_dict({"server": {"server_id": "survival", "server_name": "生存服"},
    "message": {"target_sessions": ["umo:GroupMessage:9"], "forward_chat_to_astrbot": True,
                "forward_chat_format": "[{server}] <{player}> {message}"}})
_ev4 = QueQiaoEvent.from_dict({"event_name": "PlayerChatEvent", "message": "大家好",
                               "player": {"nickname": "Steve"}})
assert _br4.format_event(_cfg4, _ev4) == "[生存服] <Steve> 大家好", \
    _br4.format_event(_cfg4, _ev4)
# 未填显示名称时用默认值 MC（线上反馈期望：[MC]<玩家名> 消息），
# 而不是回退英文 server_id
_cfg4b = _S3.from_dict({"server": {"server_id": "survival"},
    "message": {"forward_chat_format": "[{server}]<{player}> {message}"}})
assert _br4.format_event(_cfg4b, _ev4) == "[MC]<Steve> 大家好", \
    _br4.format_event(_cfg4b, _ev4)
# 显式清空默认值才输出空串（无前缀效果）
_cfg4c = _S3.from_dict({"server": {"server_id": "survival", "server_name_default": ""},
    "message": {"forward_chat_format": "{server}<{player}> {message}"}})
assert _br4.format_event(_cfg4c, _ev4) == "<Steve> 大家好"
# 只用 {player}/{message} 的旧格式必须继续可用（向后兼容，显式配置即生效）
_cfg_old = _S3.from_dict({"message": {"forward_chat_format": "<{player}> {message}"}})
assert _br4.format_event(_cfg_old, _ev4) == "<Steve> 大家好"
# 新默认格式与 conf 模板对齐：[{server}]{player}: {message}
# （什么都不填时 {server} = 默认值 MC，开箱即显示 [MC]Steve: 大家好）
assert _S3.from_dict({}).forward_chat_format == "[{server}]{player}: {message}"
assert _br4.format_event(_S3.from_dict({}), _ev4) == "[MC]Steve: 大家好"

# (c) 外部 → MC：{server} 走取值链、{server_id} 始终为原始 ID
_fmt = _cfg4.broadcast_format
_rendered = _fmt.format(platform="aiocqhttp", sender="群友A",
                        message="你好", server=_cfg4.server_label,
                        server_id="survival")
assert _rendered == "[aiocqhttp]群友A: 你好", _rendered  # 默认格式与 conf 模板一致
_rendered2 = "[{server}/{server_id}] {sender}: {message}".format(
    platform="aiocqhttp", sender="群友A", message="你好",
    server=_cfg4.server_label, server_id="survival")
assert _rendered2 == "[生存服/survival] 群友A: 你好", _rendered2
# 留空名称时 {server} 为默认值 MC，而 {server_id} 仍能取到原始 ID（排障兜底手段）
_rendered3 = "[{server}|{server_id}] {sender}: {message}".format(
    platform="aiocqhttp", sender="群友A", message="你好",
    server=_sn2.server_label, server_id="survival")
assert _rendered3 == "[MC|survival] 群友A: 你好", _rendered3

# (d) schema 守卫：server_name / server_name_default 必须在 server 子对象内、
#     紧邻排列，且两个格式串的 hint 都要提到 {server}，否则 WebUI 里用户无从得知
import json as _json3
_sh = _json3.loads(_pathlib.Path(__file__).with_name("_conf_schema.json").read_text(encoding="utf-8"))
_sitems = _sh["mc_servers"]["templates"]["server"]["items"]["server"]["items"]
_sk = list(_sitems.keys())
assert "server_name" in _sitems, "server 子对象缺少 server_name"
assert _sk.index("server_name") == _sk.index("server_id") + 1, \
    f"server_name 必须紧跟 server_id，实际顺序: {_sk}"
assert _sitems["server_name"]["default"] == ""
assert "server_name_default" in _sitems, "server 子对象缺少 server_name_default"
assert _sk.index("server_name_default") == _sk.index("server_name") + 1, \
    f"server_name_default 必须紧跟 server_name，实际顺序: {_sk}"
assert _sitems["server_name_default"]["default"] == "MC", \
    "显示名称默认值必须与代码默认一致（MC）"
_mitems = _sh["mc_servers"]["templates"]["server"]["items"]["message"]["items"]
assert "{server}" in _mitems["forward_chat_format"]["hint"], \
    "forward_chat_format 的 hint 必须说明 {server}"
assert "{server}" in _mitems["broadcast_format"]["hint"], \
    "broadcast_format 的 hint 必须说明 {server}"
print("OK  取值链 server_name→默认值(MC)→空串 可测、不污染握手 Header、旧格式向后兼容")
print("OK  两个方向的 {server} 均走取值链，{server_id} 保留原始 ID，schema 已同步")

# (e) 复现线上反馈：什么都不填 + `[{server}]<{player}> {message}`
#     期望显示 [MC]<XTxiaotong> 测试空服务器（默认值 MC，而非英文 server_id）
_live = _S3.from_dict({"server": {"server_id": "Server", "server_name": ""},
    "message": {"forward_chat_format": "[{server}]<{player}> {message}"}})
_ev_live = QueQiaoEvent.from_dict({"event_name": "PlayerChatEvent",
    "message": "测试空服务器", "player": {"nickname": "XTxiaotong"}})
_live_out = _br4.format_event(_live, _ev_live)
assert _live_out == "[MC]<XTxiaotong> 测试空服务器", _live_out
assert "Server" not in _live_out, f"未填显示名称时不应回退成 server_id: {_live_out}"
# 不带字面量方括号时直接得到 [MC] 前缀以外的形态（默认值原样参与格式化）
_live_clean = _S3.from_dict({"server": {"server_id": "Server", "server_name": ""},
    "message": {"forward_chat_format": "{server}<{player}> {message}"}})
assert _br4.format_event(_live_clean, _ev_live) == "MC<XTxiaotong> 测试空服务器"
# 默认值可自定义（如改成本服）
_live_dft = _S3.from_dict({"server": {"server_id": "Server", "server_name_default": "本服"},
    "message": {"forward_chat_format": "[{server}]<{player}> {message}"}})
assert _br4.format_event(_live_dft, _ev_live) == "[本服]<XTxiaotong> 测试空服务器"
# 想要无前缀：把默认值也显式清空（格式串里的字面量方括号仍由用户自己掌控）
_live_nopfx = _S3.from_dict({"server": {"server_id": "Server", "server_name_default": ""},
    "message": {"forward_chat_format": "{server}<{player}> {message}"}})
assert _br4.format_event(_live_nopfx, _ev_live) == "<XTxiaotong> 测试空服务器"
# 填上显示名称后同一条格式串正常带前缀
_live_named = _S3.from_dict({"server": {"server_id": "Server", "server_name": "生存服"},
    "message": {"forward_chat_format": "[{server}]<{player}> {message}"}})
assert _br4.format_event(_live_named, _ev_live) == "[生存服]<XTxiaotong> 测试空服务器"
print("OK  什么都不填显示 [MC]（线上用例）、默认值可自定义、清空才无前缀")

print("\n全部离线逻辑校验通过 ✅（含服务器显示名称）")

print("=== 21. 状态/玩家列表使用显示名称 ===")
from astrbot_plugin_minecraft_queqiao.services.renderer import InfoRenderer as _IR
from astrbot_plugin_minecraft_queqiao.core.models import ServerStatus as _SS

# 未传 label -> 沿用 server_id（旧调用行为不变）
assert "服务器 svr1 状态获取失败" in _IR.format_status("svr1", None)
assert "👥 服务器 svr1 当前没有玩家在线" == _IR.format_player_list("svr1", [])
assert "无法获取服务器 svr1 的玩家列表" in _IR.format_player_list("svr1", None)

# 传 label -> 展示中文显示名称
_st = _SS.from_dict({"server_type": "Fabric", "server_version": "1.20.1",
                     "players": {"online": 2, "max": 20}})
_out = _IR.format_status("svr1", _st, "生存服")
assert "📊 服务器状态：生存服" in _out, _out
assert "svr1" not in _out, f"展示文案不应再出现裸 server_id: {_out}"
assert "👥 服务器 生存服 在线 1 人：\nSteve" == _IR.format_player_list("svr1", ["Steve"], "生存服")
assert "无法获取服务器 生存服 的玩家列表" in _IR.format_player_list("svr1", None, "生存服")
# 失败提示同样走显示名称
assert "服务器 生存服 状态获取失败" in _IR.format_status("svr1", None, "生存服")
print("OK  状态/列表/失败提示均优先显示中文名称，缺省仍回退 server_id")

print("\n全部离线逻辑校验通过 ✅（含状态/列表显示名称）")

print("=== 22. conf 模板与代码默认值一致（防漂移守卫） ===")
import json as _json4
_sh4 = _json4.loads(
    _pathlib.Path(__file__).with_name("_conf_schema.json").read_text(encoding="utf-8")
)
_tpl4 = _sh4["mc_servers"]["templates"]["server"]["items"]

def _flat_defaults4(items, prefix=()):
    """展开 schema 子对象，产出 ((分组..., 键), default)。"""
    for _k, _v in items.items():
        if _v.get("type") == "object":
            yield from _flat_defaults4(_v.get("items", {}), prefix + (_k,))
        else:
            yield prefix + (_k,), _v.get("default")

# schema 键与 ServerConfig 字段名不一致的少数映射
_alias4 = {
    ("cmd", "enabled"): "cmd_enabled",
    ("cmd", "rcon_fallback", "enabled"): "rcon_fallback_enabled",
    ("cmd", "rcon_fallback", "host"): "rcon_host",
    ("cmd", "rcon_fallback", "port"): "rcon_port",
    ("cmd", "rcon_fallback", "password"): "rcon_password",
}
_code_defaults4 = _S2.from_dict({})  # 代码侧默认（含防御式兜底）
for _path4, _sd4 in _flat_defaults4(_tpl4):
    _field4 = _alias4.get(_path4, _path4[-1])
    assert hasattr(_code_defaults4, _field4), f"schema 项 {_path4} 无对应配置字段"
    _cv4 = getattr(_code_defaults4, _field4)
    if isinstance(_cv4, bool):
        assert (str(_sd4).lower() in ("true", "1")) == _cv4, (_path4, _sd4, _cv4)
    elif isinstance(_cv4, int):
        assert _sd4 is not None and int(_sd4) == _cv4, (_path4, _sd4, _cv4)
    elif isinstance(_cv4, list):
        assert [str(_x) for _x in (_sd4 or [])] == _cv4, (_path4, _sd4, _cv4)
    elif isinstance(_cv4, dict):
        # dict 字段（平台名称映射）：schema 侧是 `键=值` 条目列表，逐条解析后比对
        _parsed4: dict[str, str] = {}
        for _entry4 in _sd4 or []:
            _k4, _, _v4 = str(_entry4).partition("=")
            if _k4.strip() and _v4.strip():
                _parsed4[_k4.strip()] = _v4.strip()
        assert _parsed4 == _cv4, (_path4, _sd4, _cv4)
    else:
        assert str(_sd4) == str(_cv4), \
            f"conf 与代码默认值不一致: {'/'.join(_path4)}: schema={_sd4!r} code={_cv4!r}"

# 直接点名钉死本次对齐的三处，失配时报错一眼可见
from astrbot_plugin_minecraft_queqiao.core.constants import (
    DEFAULT_BROADCAST_FORMAT as _DBF4,
    DEFAULT_CHAT_FORMAT as _DCF4,
)
assert _DCF4 == "[{server}]{player}: {message}", _DCF4
assert _DBF4 == "[{platform}]{sender}: {message}", _DBF4
assert _S2.from_dict({}).server_id == "Server"
print("OK  conf 模板与代码默认值逐项核对一致"
      "（forward_chat_format / broadcast_format / server_id 等全部对齐）")

print("\n全部离线逻辑校验通过 ✅（含 conf↔代码默认值守卫）")

print("=== 23. API 超时语义：未知 ≠ 失败，禁止重发（AI 回复两遍的根因） ===")
import json as _json5
from astrbot_plugin_minecraft_queqiao.core.constants import (
    API_BROADCAST as _APIB5,
    API_RCON as _APIR5,
)
from astrbot_plugin_minecraft_queqiao.core.queqiao_client import (
    QueQiaoClient as _QC5,
    QueQiaoTimeout as _QT5,
)
from astrbot_plugin_minecraft_queqiao.core.server_manager import ServerInstance as _SI5

class _FakeWS5:
    """假 WebSocket：record 请求；reply 非空时延迟回一条响应。"""
    def __init__(self, client, reply=None, delay=0.01):
        self.client, self.reply, self.delay = client, reply, delay
        self.sent = []
    async def send(self, raw):
        payload = _json5.loads(raw)
        self.sent.append(payload)
        if self.reply is None:
            return
        resp = dict(self.reply)
        resp["echo"] = payload["echo"]
        async def _reply():
            await asyncio.sleep(self.delay)
            await self.client._dispatch(_json5.dumps(resp))
        asyncio.get_running_loop().create_task(_reply())

_cfg5 = _S2.from_dict({"server": {"server_id": "S"}})
_cli5 = _QC5(_cfg5)

# (a) 未连接 → 直接 None（确定未投递，不抛超时）
assert asyncio.run(_cli5.call_api(_APIB5, {})) is None

# (b) 发送成功 + 鹊桥回 SUCCESS → 拿到响应 dict
_cli5._connected = True
_cli5._ws = _FakeWS5(_cli5, reply={"post_type": "response", "status": "SUCCESS", "code": 200})
_res5 = asyncio.run(_cli5.call_api(_APIB5, {"message": []}, timeout=1))
assert _res5 and _res5.get("status") == "SUCCESS", _res5

# (c) 发送成功 + 鹊桥明确报错 → 返回错误 dict（确定失败，可安全换通道）
_cli5._ws = _FakeWS5(_cli5, reply={"post_type": "response", "status": "ERROR", "code": 500})
_res5e = asyncio.run(_cli5.call_api(_APIB5, {"message": []}, timeout=1))
assert _res5e is not None and _res5e.get("status") != "SUCCESS", _res5e

# (d) 发送成功 + 无响应 → 抛 QueQiaoTimeout（结果未知，禁止据此重发）
_cli5._ws = _FakeWS5(_cli5)
try:
    asyncio.run(_cli5.call_api(_APIB5, {"message": []}, timeout=0.05))
    raise AssertionError("超时必须抛 QueQiaoTimeout")
except _QT5 as _exc5:
    assert "broadcast" in str(_exc5), str(_exc5)

# (e) broadcast：吞掉超时并按「已投递」返回 True（上层不会重发造成两遍）
_cli5._ws = _FakeWS5(_cli5)
assert asyncio.run(_cli5.broadcast("hi")) is True
# 明确报错时仍如实返回 False
_cli5._ws = _FakeWS5(_cli5, reply={"post_type": "response", "status": "ERROR"})
assert asyncio.run(_cli5.broadcast("hi")) is False

# (f) send_private_message：超时向上抛，由调用方决策（不得静默当失败）
_cli5._ws = _FakeWS5(_cli5)
try:
    asyncio.run(_cli5.send_private_message("hi", nickname="X"))
    raise AssertionError("私聊超时必须向上抛 QueQiaoTimeout")
except _QT5:
    pass

# (g) execute_command：鹊桥超时不得走 RCON 兜底（指令会执行两遍）
class _CliStub5:
    def __init__(self, connected=True):
        self.connected = connected
    async def send_rcon_command(self, cmd):
        raise _QT5(_APIR5, 10)
class _RconStub5:
    def __init__(self):
        self.enabled = True
        self.calls = []
    async def execute(self, cmd):
        self.calls.append(cmd)
        return "rcon-out"
_inst5 = _SI5(_cfg5)
_inst5.client = _CliStub5()
_rcon5 = _RconStub5()
_inst5.rcon = _rcon5
assert asyncio.run(_inst5.execute_command("time set day")) is None
assert _rcon5.calls == [], f"超时不得走 RCON 兜底: {_rcon5.calls}"

# (h) 确定失败（未连接）时 RCON 兜底仍然生效——原有行为不受影响
_inst5.client = _CliStub5(connected=False)
_rcon5b = _RconStub5()
_inst5.rcon = _rcon5b
assert asyncio.run(_inst5.execute_command("list")) == "rcon-out"
assert _rcon5b.calls == ["list"], _rcon5b.calls
print("OK  超时=未知（不重发）：私聊超时不再广播兜底、RCON 超时不再直连兜底；"
      "确定失败时兜底不受影响")

print("\n=== 24. 平台名称映射（platform_names → {platform}） ===")
from astrbot_plugin_minecraft_queqiao.core.models_config import (
    ServerConfig as _S6,
)

# (a) 解析：列表条目 `原始平台名=显示名`，空白容忍、坏条目忽略、重复键取最后一条
_cfg6 = _S6.from_dict({"message": {"platform_names": [
    "aiocqhttp=QQ", "  telegram = 电报 ", "bad-entry", "=空键", "空值=",
    "discord=DC", "discord=Discord",
]}})
assert _cfg6.platform_names == {
    "aiocqhttp": "QQ", "telegram": "电报", "discord": "Discord"
}, _cfg6.platform_names

# (b) 兼容形态：JSON 对象字符串 / 逗号分隔字符串 / dict / 非法值
assert _S6.from_dict({"message": {"platform_names": '{"aiocqhttp":"QQ","qq_official":"官方QQ"}'}})\
    .platform_names == {"aiocqhttp": "QQ", "qq_official": "官方QQ"}
assert _S6.from_dict({"message": {"platform_names": "aiocqhttp=QQ,telegram=电报"}})\
    .platform_names == {"aiocqhttp": "QQ", "telegram": "电报"}
assert _S6.from_dict({"message": {"platform_names": {"aiocqhttp": "QQ", "x": ""}}})\
    .platform_names == {"aiocqhttp": "QQ"}
assert _S6.from_dict({"message": {"platform_names": 123}}).platform_names == {}
# 默认自带 aiocqhttp=QQ 示例（开箱即用）；显式删空列表 = 不改写
assert _S6.from_dict({}).platform_names == {"aiocqhttp": "QQ"}, \
    "默认必须自带 aiocqhttp=QQ 示例"
assert _S6.from_dict({"message": {"platform_names": []}}).platform_names == {}, \
    "显式删空列表必须关闭改写"

# (c) 取名语义：精确匹配 → 忽略大小写兜底 → 未命中原样返回
_cfg6b = _S6.from_dict({"message": {"platform_names": ["aiocqhttp=QQ", "Telegram=电报"]}})
assert _cfg6b.platform_display_name("aiocqhttp") == "QQ"
assert _cfg6b.platform_display_name("AIOCQHTTP") == "QQ", "忽略大小写兜底"
assert _cfg6b.platform_display_name("telegram") == "电报"
assert _cfg6b.platform_display_name("discord") == "discord", "未命中原样返回"
assert _cfg6b.platform_display_name("") == "", "空平台名不炸"
# 默认配置开箱即用：aiocqhttp 显示为 QQ，其它平台保持原名
assert _S6.from_dict({}).platform_display_name("aiocqhttp") == "QQ", \
    "默认示例 aiocqhttp=QQ 必须生效"
assert _S6.from_dict({}).platform_display_name("discord") == "discord"
# 显式删空列表后恢复不改写
assert _S6.from_dict({"message": {"platform_names": []}})\
    .platform_display_name("aiocqhttp") == "aiocqhttp", "删空后必须恢复原名"

# (d) 端到端：{platform} 经映射后进 broadcast_format（aiocqhttp → QQ）
_out6 = "[{platform}]{sender}: {message}".format(
    platform=_cfg6b.platform_display_name("aiocqhttp"),
    sender="群友A", message="你好",
    server=_cfg6b.server_label, server_id="S",
)
assert _out6 == "[QQ]群友A: 你好", _out6

# (e) schema 守卫：platform_names 在 message 分组内紧随 broadcast_format，
#     hint 必须说明条目格式与 {platform}，默认自带 aiocqhttp=QQ（删空 = 不改写）
_sh6 = json.loads(_pathlib.Path(__file__).with_name("_conf_schema.json").read_text(encoding="utf-8"))
_mitems6 = _sh6["mc_servers"]["templates"]["server"]["items"]["message"]["items"]
assert "platform_names" in _mitems6, "message 分组缺少 platform_names"
_mk6 = list(_mitems6.keys())
assert _mk6.index("platform_names") == _mk6.index("broadcast_format") + 1, \
    f"platform_names 必须紧跟 broadcast_format，实际顺序: {_mk6}"
assert _mitems6["platform_names"]["default"] == ["aiocqhttp=QQ"], \
    "schema 默认必须自带 aiocqhttp=QQ 示例"
assert "{platform}" in _mitems6["platform_names"]["hint"], \
    "platform_names 的 hint 必须说明作用于 {platform}"
assert "=" in _mitems6["platform_names"]["hint"], "hint 必须说明 原始平台名=显示名 格式"
print("OK  platform_names 解析/取名语义/默认示例 aiocqhttp=QQ/schema 同步 全部通过")
print("\n全部离线逻辑校验通过 ✅（含平台名称映射）")
