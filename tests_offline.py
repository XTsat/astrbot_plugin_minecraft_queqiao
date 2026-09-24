"""离线逻辑自检：用桩替代 astrbot/websockets，验证纯逻辑（配置解析、事件模型、
转发与回声抑制、自定义指令、绑定持久化、端到端事件流）。

运行： python3 tests_offline.py
"""
import sys, types, os
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

astrbot = types.ModuleType("astrbot"); api = types.ModuleType("astrbot.api")
class _L:
    def info(self,*a,**k): pass
    def warning(self,*a,**k): pass
    def error(self,*a,**k): pass
    def debug(self,*a,**k): pass
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
class Image:
    """桩：与真实 Image 组件字段对齐（url/file/path + 文件服务注册兜底）。"""
    def __init__(self, file="", url="", path=""):
        self.file = file; self.url = url; self.path = path
    @staticmethod
    def fromBytes(data):
        import base64
        return Image(file="base64://" + base64.b64encode(data).decode())
    async def register_to_file_service(self):
        raise RuntimeError("stub: no callback_api_base")
mc.Plain = Plain; mc.Image = Image
sys.modules["astrbot.api.message_components"] = mc
st = types.ModuleType("astrbot.api.star")
class Star:
    def __init__(self, context=None): self.context = context
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
cfg = ServerConfig.from_dict({"server":{"server_name":"S"},
    "message":{"target_sessions":["umo:GroupMessage:1"],"auto_forward_prefix":"*",
               "forward_chat_to_astrbot":True,"forward_join_leave_to_astrbot":False}})
br.register_server(cfg)
assert br.servers_for_session("umo:GroupMessage:1")[0][0] == "S"
assert br.should_relay(cfg,"*hello") is True
assert br.should_relay(cfg,"no prefix") is False
assert br.strip_relay_prefix(cfg,"*hello") == "hello"
# 转发前缀留空 = 全部转发（与 AI 前缀「留空即不触发」语义相反，属刻意设计）
cfg_empty_prefix = ServerConfig.from_dict({"server":{"server_name":"S2"},
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
c = ServerConfig.from_dict({"server":{"server_name":"T","ws_mode":"reverse","reverse_port":"9090",
     "access_token":"tok"},"message":{"target_sessions":'["a:b:1"]'},
     "cmd":{"cmd_list":"say, list","rcon_fallback":{"enabled":"true","port":"25575"}}})
assert c.is_reverse and c.reverse_port==9090 and c.target_sessions==["a:b:1"]
assert c.cmd_list==["say","list"] and c.rcon_fallback_enabled and c.rcon_port==25575
assert c.is_command_allowed("say hi") and not c.is_command_allowed("op x")
# 扁平字段（新 schema，WebUI 可渲染）优先，旧 rcon_fallback 对象兼容
c2 = ServerConfig.from_dict({"cmd":{"rcon_enabled":True,"rcon_host":"192.168.1.10",
     "rcon_port":"25580","rcon_password":"pwd"}})
assert c2.rcon_fallback_enabled and c2.rcon_host=="192.168.1.10"
assert c2.rcon_port==25580 and c2.rcon_password=="pwd"
c3 = ServerConfig.from_dict({"cmd":{"rcon_enabled":False,"rcon_host":"1.1.1.1",
     "rcon_fallback":{"enabled":True,"host":"2.2.2.2","port":25575,"password":"old"}}})
assert c3.rcon_fallback_enabled is False and c3.rcon_host=="1.1.1.1"
assert c3.rcon_port==25575 and c3.rcon_password=="old"
print("OK")

print("\n全部离线逻辑校验通过 ✅")

print("=== 11. 端到端：鹊桥事件 -> 会话转发 ===")
sent = []
class _Ctx2:
    async def send_message(self, umo, chain):
        sent.append((umo, chain.chain[0].text)); return True
br2 = MessageBridge(_Ctx2())
cfg2 = ServerConfig.from_dict({"server":{"server_name":"Srv"},
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
assert "🟢 Alex 加入了服务器[MC]" == sent[1][1]
assert sent[2][1] == "💀 Steve was slain by Zombie"
print("OK  聊天(富文本剥离)/加入/死亡 三类事件均正确转发（加入消息带服务器显示名称 [MC]）")

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
cfg_ai = SC.from_dict({"server":{"server_name":"S"},"ai_chat_prefix":"ai"})
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
cfg_bang = SC.from_dict({"server":{"server_name":"S"},"ai_chat_prefix":"!"})
assert P._match_ai_prefix(cfg_bang, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"!你好"})) is True
# 以字母结尾的前缀（如 `#ai`）同样要求词边界
cfg_hash = SC.from_dict({"server":{"server_name":"S"},"ai_chat_prefix":"#ai"})
assert P._match_ai_prefix(cfg_hash, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"#aihi"})) is False
assert P._match_ai_prefix(cfg_hash, QueQiaoEvent.from_dict(
    {"event_name":"PlayerChatEvent","message":"#ai 你好"})) is True

# AI 前缀留空 -> 不触发（避免全量投喂 LLM）
cfg_empty = SC.from_dict({"server":{"server_name":"S"},"ai_chat_prefix":""})
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
cfg3 = SC.from_dict({"server":{"server_name":"Srv2"},"ai_chat_prefix":"#ai",
    "message":{"target_sessions":["umo:GroupMessage:9"],"forward_chat_to_astrbot":True}})
br3.register_server(cfg3)
async def _run3():
    # 普通聊天 -> 应转发到群
    await br3.forward_event("Srv2", cfg3, chat_norm)
    # AI 消息 -> 在 main 层就被拦截，不会到达 bridge
asyncio.run(_run3())
# 默认格式 [{display_name}]{player}: {message}：{display_name} 留空时取显示名称默认值 MC
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

cfg = SC.from_dict({"server":{"server_name":"S"},"ai_chat_prefix":"ai"})
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
cfg_off = SC.from_dict({"server":{"server_name":"S"},"enable_ai_chat":False})
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
            {"key": None, "args": None, "text": "Steve"},
            {"key": "chat.square_brackets",
             "args": [{"key": "advancements.story.lava_bucket.title", "args": [],
                       "text": "Hot Stuff"}],
             "text": "[Hot Stuff]"},
        ],
        "text": "Steve has made the advancement [Hot Stuff]",
    },
}
_r = _Ach.from_dict(_REAL)
assert _r.translate.text == "Steve has made the advancement [Hot Stuff]", _r.translate.text
assert _r.display_text == "Steve has made the advancement [Hot Stuff]", _r.display_text
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
_bcfg = _S2.from_dict({"server": {"server_name": "S"},
                       "message": {"target_sessions": ["umo:GroupMessage:1"],
                                   "forward_achievement_to_astrbot": True}})
_br = _MB(context=None)
_ev_ach = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "post_type": "notice",
    "player": {"nickname": "Steve"},
    "achievement": {"key": "minecraft:husbandry/sweet_dreams",
                    "display": {"title": "Sweet Dreams", "frame": "goal"}}})
_text = _br.format_event(_bcfg, _ev_ach)
assert _text == "🏆 Steve 达成了成就 Sweet Dreams", _text
assert "Sweet Dreams" in _text, _text

# 玩家名兜底：连成就信息都没有时才用「<玩家> 达成了成就」
_ev_bare = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "player": {"nickname": "Steve"},
    "achievement": {}})
_bare = _br.format_event(_bcfg, _ev_bare)
assert _bare == "🏆 Steve 达成了成就", _bare

# 未开翻译 + display.title：成就名有了但整句不含玩家名 → 必须补上玩家名
# （线上曾出现「🏆 Getting an Upgrade」缺名字）
_ev_nick = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "player": {"nickname": "Steve"},
    "achievement": {"key": "minecraft:story/upgrade_tools",
                    "display": {"title": {"text": "Getting an Upgrade",
                                          "key": "advancements.story.upgrade_tools.title",
                                          "args": []},
                                "frame": "task"}}})
_nick = _br.format_event(_bcfg, _ev_nick)
assert _nick == "🏆 Steve 达成了成就 Getting an Upgrade", _nick

# 开翻译：整句已含玩家名 → 不得重复拼接
_ev_tr = QueQiaoEvent.from_dict({
    "event_name": "PlayerAchievementEvent", "player": {"nickname": "Steve"},
    "achievement": {"key": "k", "translation": {
        "key": "chat.type.advancement.task", "args": [],
        "text": "Steve has made the advancement [Hot Stuff]"}}})
_tr = _br.format_event(_bcfg, _ev_tr)
assert _tr == "🏆 Steve has made the advancement [Hot Stuff]", _tr
assert _tr.count("Steve") == 1, _tr   # 关键：不重复

# should_forward 仍受开关控制（关闭时不转发，避免兜底文案掩盖配置问题）
_off = _S2.from_dict({"server": {"server_name": "S"},
                      "message": {"target_sessions": ["umo:GroupMessage:1"],
                                  "forward_achievement_to_astrbot": False}})
assert _br.should_forward(_off, _ev_ach) is False
assert _br.should_forward(_bcfg, _ev_ach) is True
print("OK  未开翻译时补玩家名（🏆 Steve 达成了成就 Getting an Upgrade）")
print("OK  开翻译时整句已含玩家名，判重不重复拼接")
print("OK  成就转发开关仍生效（关闭时不转发）")

print("\n全部离线逻辑校验通过 ✅（含成就文本降级链）")

print("=== 20. 服务器显示名称与格式占位符 ===")
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _S3
from astrbot_plugin_minecraft_queqiao.services.message_bridge import MessageBridge as _MB3

# (a) 取值链必须区分开：
#     server_label  <- 消息格式 {display_name}：display_name → display_name_default（默认 MC）→ 空串
#     display_name  <- 状态/列表文案：同链再回退 server_name / 未知
_sn = _S3.from_dict({"server": {"server_name": "survival", "display_name": "生存服"}})
assert _sn.display_name == "生存服"
assert _sn.server_label == "生存服" and _sn.display_label == "生存服"
# display_name 优先级最高，永远压过默认值
assert _S3.from_dict({"server": {"server_name": "s", "display_name": "生存服",
    "display_name_default": "MC2"}}).server_label == "生存服"
# 什么都不填：{display_name} 用默认值 MC（线上反馈的期望效果），状态/列表同链取 MC
_sn2 = _S3.from_dict({"server": {"server_name": "survival"}})
assert _sn2.display_name == ""
assert _sn2.server_label == "MC", f"留空应取默认值 MC，实际 {_sn2.server_label!r}"
assert _sn2.display_label == "MC"
# 默认值可自定义
assert _S3.from_dict({"server": {"server_name": "s", "display_name_default": "本服"}})\
    .server_label == "本服"
# 显式清空默认值（display_name_default=""）才输出空串——唯一的无前缀途径
_sn3 = _S3.from_dict({"server": {"server_name": "s", "display_name_default": ""}})
assert _sn3.server_label == ""
assert _sn3.display_label == "s"  # label 空时孤立文案回退 server_name
# 默认配置与 conf 模板对齐（server_name 缺省回落 Server）；
# 「未知」仅在 label 与 server_name 全空时出现（该配置会被 main 层跳过并告警）
assert _S3.from_dict({}).server_label == "MC" and _S3.from_dict({}).display_label == "MC"
assert _S3.from_dict({"server": {"server_name": "", "display_name_default": ""}})\
    .display_label == "未知"
# 显示名称只影响展示，不得污染握手 Header（x-self-name 必须仍是 server_name）
assert _sn.forward_headers["x-self-name"] == "survival", _sn.forward_headers
# 纯空白的 display_name 视为未填写 -> 走默认值
assert _S3.from_dict({"server": {"server_name": "s", "display_name": "   "}}).server_label == "MC"
# 纯空白的默认值视为已清空 -> 空串
assert _S3.from_dict({"server": {"server_name": "s", "display_name_default": "  "}})\
    .server_label == ""
# 非字符串形态（WebUI 误填数字）也要安全收敛
assert _S3.from_dict({"server": {"server_name": "s", "display_name": 123}}).server_label == "123"
assert _S3.from_dict({"server": {"server_name": "s", "display_name_default": 66}})\
    .server_label == "66"

# (b) MC → 外部：{display_name} 取显示名称（中文可直接渲染）
_sent3 = []
class _Ctx4:
    async def send_message(self, umo, chain):
        _sent3.append(chain.chain[0].text); return True
_br4 = _MB3(_Ctx4())
_cfg4 = _S3.from_dict({"server": {"server_name": "survival", "display_name": "生存服"},
    "message": {"target_sessions": ["umo:GroupMessage:9"], "forward_chat_to_astrbot": True,
                "forward_chat_format": "[{display_name}] <{player}> {message}"}})
_ev4 = QueQiaoEvent.from_dict({"event_name": "PlayerChatEvent", "message": "大家好",
                               "player": {"nickname": "Steve"}})
assert _br4.format_event(_cfg4, _ev4) == "[生存服] <Steve> 大家好", \
    _br4.format_event(_cfg4, _ev4)
# 未填显示名称时用默认值 MC（线上反馈期望：[MC]<玩家名> 消息），
# 而不是回退英文 server_name
_cfg4b = _S3.from_dict({"server": {"server_name": "survival"},
    "message": {"forward_chat_format": "[{display_name}]<{player}> {message}"}})
assert _br4.format_event(_cfg4b, _ev4) == "[MC]<Steve> 大家好", \
    _br4.format_event(_cfg4b, _ev4)
# 显式清空默认值才输出空串（无前缀效果）
_cfg4c = _S3.from_dict({"server": {"server_name": "survival", "display_name_default": ""},
    "message": {"forward_chat_format": "{display_name}<{player}> {message}"}})
assert _br4.format_event(_cfg4c, _ev4) == "<Steve> 大家好"
# 只用 {player}/{message} 的旧格式必须继续可用（向后兼容，显式配置即生效）
_cfg_old = _S3.from_dict({"message": {"forward_chat_format": "<{player}> {message}"}})
assert _br4.format_event(_cfg_old, _ev4) == "<Steve> 大家好"
# 新默认格式与 conf 模板对齐：[{display_name}]{player}: {message}
# （什么都不填时 {display_name} = 默认值 MC，开箱即显示 [MC]Steve: 大家好）
assert _S3.from_dict({}).forward_chat_format == "[{display_name}]{player}: {message}"
assert _br4.format_event(_S3.from_dict({}), _ev4) == "[MC]Steve: 大家好"

# (c) 外部 → MC：{display_name} 走取值链、{server_name} 始终为原始 ID
_fmt = _cfg4.broadcast_format
_rendered = _fmt.format(platform="aiocqhttp", sender="群友A",
                        message="你好", display_name=_cfg4.server_label,
                        server_name="survival")
assert _rendered == "[aiocqhttp]群友A: 你好", _rendered  # 默认格式与 conf 模板一致
_rendered2 = "[{display_name}/{server_name}] {sender}: {message}".format(
    platform="aiocqhttp", sender="群友A", message="你好",
    display_name=_cfg4.server_label, server_name="survival")
assert _rendered2 == "[生存服/survival] 群友A: 你好", _rendered2
# 留空名称时 {display_name} 为默认值 MC，而 {server_name} 仍能取到原始 ID（排障兜底手段）
_rendered3 = "[{display_name}|{server_name}] {sender}: {message}".format(
    platform="aiocqhttp", sender="群友A", message="你好",
    display_name=_sn2.server_label, server_name="survival")
assert _rendered3 == "[MC|survival] 群友A: 你好", _rendered3

# (d) schema 守卫：display_name / display_name_default 必须在 server 子对象内、
#     紧邻排列，且两个格式串的 hint 都要提到 {display_name}，否则 WebUI 里用户无从得知
import json as _json3
_sh = _json3.loads(_pathlib.Path(__file__).with_name("_conf_schema.json").read_text(encoding="utf-8"))
_sitems = _sh["mc_servers"]["templates"]["server"]["items"]["server"]["items"]
_sk = list(_sitems.keys())
assert "display_name" in _sitems, "server 子对象缺少 display_name"
assert _sk.index("display_name") == _sk.index("server_name") + 1, \
    f"display_name 必须紧跟 server_name，实际顺序: {_sk}"
assert _sitems["display_name"]["default"] == ""
assert "display_name_default" in _sitems, "server 子对象缺少 display_name_default"
assert _sk.index("display_name_default") == _sk.index("display_name") + 1, \
    f"display_name_default 必须紧跟 display_name，实际顺序: {_sk}"
assert _sitems["display_name_default"]["default"] == "MC", \
    "显示名称默认值必须与代码默认一致（MC）"
_mitems = _sh["mc_servers"]["templates"]["server"]["items"]["message"]["items"]
assert "{display_name}" in _mitems["forward_chat_format"]["hint"], \
    "forward_chat_format 的 hint 必须说明 {display_name}"
assert "{display_name}" in _mitems["broadcast_format"]["hint"], \
    "broadcast_format 的 hint 必须说明 {display_name}"
print("OK  取值链 display_name→默认值(MC)→空串 可测、不污染握手 Header、旧格式向后兼容")
print("OK  两个方向的 {display_name} 均走取值链，{server_name} 保留原始 ID，schema 已同步")

# (e) 复现线上反馈：什么都不填 + `[{display_name}]<{player}> {message}`
#     期望显示 [MC]<Steve> 测试空服务器（默认值 MC，而非英文 server_name）
_live = _S3.from_dict({"server": {"server_name": "Server", "display_name": ""},
    "message": {"forward_chat_format": "[{display_name}]<{player}> {message}"}})
_ev_live = QueQiaoEvent.from_dict({"event_name": "PlayerChatEvent",
    "message": "测试空服务器", "player": {"nickname": "Steve"}})
_live_out = _br4.format_event(_live, _ev_live)
assert _live_out == "[MC]<Steve> 测试空服务器", _live_out
assert "Server" not in _live_out, f"未填显示名称时不应回退成 server_name: {_live_out}"
# 不带字面量方括号时直接得到 [MC] 前缀以外的形态（默认值原样参与格式化）
_live_clean = _S3.from_dict({"server": {"server_name": "Server", "display_name": ""},
    "message": {"forward_chat_format": "{display_name}<{player}> {message}"}})
assert _br4.format_event(_live_clean, _ev_live) == "MC<Steve> 测试空服务器"
# 默认值可自定义（如改成本服）
_live_dft = _S3.from_dict({"server": {"server_name": "Server", "display_name_default": "本服"},
    "message": {"forward_chat_format": "[{display_name}]<{player}> {message}"}})
assert _br4.format_event(_live_dft, _ev_live) == "[本服]<Steve> 测试空服务器"
# 想要无前缀：把默认值也显式清空（格式串里的字面量方括号仍由用户自己掌控）
_live_nopfx = _S3.from_dict({"server": {"server_name": "Server", "display_name_default": ""},
    "message": {"forward_chat_format": "{display_name}<{player}> {message}"}})
assert _br4.format_event(_live_nopfx, _ev_live) == "<Steve> 测试空服务器"
# 填上显示名称后同一条格式串正常带前缀
_live_named = _S3.from_dict({"server": {"server_name": "Server", "display_name": "生存服"},
    "message": {"forward_chat_format": "[{display_name}]<{player}> {message}"}})
assert _br4.format_event(_live_named, _ev_live) == "[生存服]<Steve> 测试空服务器"
print("OK  什么都不填显示 [MC]（线上用例）、默认值可自定义、清空才无前缀")

# (f) 进出消息必须在「服务器」后附上展示名称（display_name → 默认值 → server_name），
#     多台服务器指向同一会话时能区分来源
_ev_j = QueQiaoEvent.from_dict({"event_name": "PlayerJoinEvent", "player": {"nickname": "Alex"}})
_ev_q = QueQiaoEvent.from_dict({"event_name": "PlayerQuitEvent", "player": {"nickname": "Alex"}})
assert _br4.format_event(_live_named, _ev_j) == "🟢 Alex 加入了服务器[生存服]"
assert _br4.format_event(_live_named, _ev_q) == "🔴 Alex 离开了服务器[生存服]"
# 未填 display_name：走默认值 MC
assert _br4.format_event(_live, _ev_j) == "🟢 Alex 加入了服务器[MC]"
assert _br4.format_event(_live, _ev_q) == "🔴 Alex 离开了服务器[MC]"
# 显示名称与默认值都清空：回退 server_name（仍能标识来源，不会退化回无标识）
_live_nolabel = _S3.from_dict({"server": {"server_name": "survival",
    "display_name_default": ""}})
assert _br4.format_event(_live_nolabel, _ev_j) == "🟢 Alex 加入了服务器[survival]"
print("OK  进出消息附服务器显示名称且保持同一条取值链")

print("\n全部离线逻辑校验通过 ✅（含服务器显示名称）")

print("=== 21. 状态/玩家列表使用显示名称 ===")
from astrbot_plugin_minecraft_queqiao.services.renderer import InfoRenderer as _IR
from astrbot_plugin_minecraft_queqiao.core.models import ServerStatus as _SS

# 未传 label -> 沿用 server_name（旧调用行为不变）
assert "服务器 svr1 状态获取失败" in _IR.format_status("svr1", None)
assert "👥 服务器 svr1 当前没有玩家在线" == _IR.format_player_list("svr1", [])
assert "无法获取服务器 svr1 的玩家列表" in _IR.format_player_list("svr1", None)

# 传 label -> 展示中文显示名称
_st = _SS.from_dict({"server_type": "Fabric", "server_version": "1.20.1",
                     "players": {"online": 2, "max": 20}})
_out = _IR.format_status("svr1", _st, "生存服")
assert "📊 服务器状态：生存服" in _out, _out
assert "svr1" not in _out, f"展示文案不应再出现裸 server_name: {_out}"
assert "👥 服务器 生存服 在线 1 人：\nSteve" == _IR.format_player_list("svr1", ["Steve"], "生存服")
assert "无法获取服务器 生存服 的玩家列表" in _IR.format_player_list("svr1", None, "生存服")
# 失败提示同样走显示名称
assert "服务器 生存服 状态获取失败" in _IR.format_status("svr1", None, "生存服")
print("OK  状态/列表/失败提示均优先显示中文名称，缺省仍回退 server_name")

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
    ("cmd", "rcon_enabled"): "rcon_fallback_enabled",
    ("cmd", "rcon_host"): "rcon_host",
    ("cmd", "rcon_port"): "rcon_port",
    ("cmd", "rcon_password"): "rcon_password",
    # 注：性能监控设置不在 conf schema 中（只在仪表盘内维护），故此处无对应别名
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
assert _DCF4 == "[{display_name}]{player}: {message}", _DCF4
assert _DBF4 == "[{platform}]{sender}: {message}", _DBF4
assert _S2.from_dict({}).server_name == "Server"
print("OK  conf 模板与代码默认值逐项核对一致"
      "（forward_chat_format / broadcast_format / server_name 等全部对齐）")

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

_cfg5 = _S2.from_dict({"server": {"server_name": "S"}})
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
    display_name=_cfg6b.server_label, server_name="S",
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

print("\n=== 25. 重连低频退避（reconnect 分组 + 两段式重连等待） ===")
from astrbot_plugin_minecraft_queqiao.core.queqiao_client import QueQiaoClient as _Q7
from astrbot_plugin_minecraft_queqiao.core.constants import (
    DEFAULT_LOW_FREQUENCY_INTERVAL as _LF_INT7,
    DEFAULT_LOW_FREQUENCY_THRESHOLD as _LF_TH7,
)

# (a) 默认值：前 30 次正常退避，第 31 次起进入低频（间隔 300s = 5 分钟）
_cfg7 = _S6.from_dict({})
assert _cfg7.reconnect_interval == 5 and _cfg7.max_reconnect == 0
assert _cfg7.low_frequency_threshold == 30, _cfg7.low_frequency_threshold
assert _cfg7.low_frequency_interval == 300, _cfg7.low_frequency_interval
assert _LF_TH7 == 30 and _LF_INT7 == 300, "常量默认必须与 schema/模型一致（30/300）"

# (b) 新分组解析：reconnect.* 生效，字符串/非法值防御式兜底
_cfg7b = _S6.from_dict({"reconnect": {
    "reconnect_interval": "10", "max_reconnect": "5",
    "low_frequency_threshold": "50", "low_frequency_interval": "300",
}})
assert _cfg7b.reconnect_interval == 10 and _cfg7b.max_reconnect == 5
assert _cfg7b.low_frequency_threshold == 50
assert _cfg7b.low_frequency_interval == 300
_cfg7c = _S6.from_dict({"reconnect": {
    "reconnect_interval": -3, "max_reconnect": -1,
    "low_frequency_threshold": -7, "low_frequency_interval": 0,
}})
assert _cfg7c.reconnect_interval == 1, "重连间隔下限 1"
assert _cfg7c.max_reconnect == 0, "最大重连次数下限 0"
assert _cfg7c.low_frequency_threshold == 0, "阈值下限 0（0=关闭低频）"
assert _cfg7c.low_frequency_interval == 1, "低频间隔下限 1"
assert _S6.from_dict({"reconnect": {"low_frequency_threshold": "abc"}})\
    .low_frequency_threshold == 30, "非法阈值回落默认"

# (c) 旧配置兼容：重连项曾位于 server 子对象内，必须继续生效；新分组优先
_cfg7d = _S6.from_dict({"server": {"reconnect_interval": 7, "max_reconnect": 9}})
assert _cfg7d.reconnect_interval == 7 and _cfg7d.max_reconnect == 9, "旧位置必须生效"
_cfg7e = _S6.from_dict({
    "server": {"reconnect_interval": 7, "max_reconnect": 9},
    "reconnect": {"reconnect_interval": 11, "max_reconnect": 13},
})
assert _cfg7e.reconnect_interval == 11 and _cfg7e.max_reconnect == 13, "新分组优先"

# (d) 两段式退避：_reconnect_wait 纯函数
_rw7 = _Q7._reconnect_wait
# 默认配置：第 1 次 5s → 第 6 次 30s → 第 12 次 60s（封顶）→ 第 30 次仍退避段
assert _rw7(1, _cfg7) == (5, "退避")
assert _rw7(6, _cfg7) == (30, "退避")
assert _rw7(12, _cfg7) == (60, "退避")
assert _rw7(30, _cfg7) == (60, "退避"), "第 30 次仍未超阈值"
assert _rw7(31, _cfg7) == (300, "低频"), "第 31 次起进入低频（默认 300s = 5 分钟）"
assert _rw7(999, _cfg7) == (300, "低频"), "低频段固定间隔不再递增"
# 自定义阈值与低频间隔：超过阈值即固定低频间隔
_cfg7f = _S6.from_dict({"reconnect": {
    "low_frequency_threshold": 2, "low_frequency_interval": 300,
}})
assert _rw7(2, _cfg7f) == (10, "退避"), "第 2 次仍在阈值内（线性退避）"
assert _rw7(3, _cfg7f) == (300, "低频"), "超过阈值后固定 300s"
# 阈值配 0 = 关闭低频：始终按退避段（封顶 60s）
_cfg7g = _S6.from_dict({"reconnect": {"low_frequency_threshold": 0}})
assert _rw7(1, _cfg7g) == (5, "退避")
assert _rw7(100, _cfg7g) == (60, "退避"), "关闭低频后永不进入低频段"
# 低频间隔可配小于退避峰值的值：超过阈值后立即换用低频间隔
_cfg7h = _S6.from_dict({"reconnect": {
    "low_frequency_threshold": 5, "low_frequency_interval": 20,
}})
assert _rw7(5, _cfg7h) == (25, "退避")
assert _rw7(6, _cfg7h) == (20, "低频")

# (e) schema 结构守卫：重连项必须从 server 子对象移出，
#     在模板项最底部单独成组（reconnect），默认 30/60
_sh7 = json.loads(_pathlib.Path(__file__).with_name("_conf_schema.json")
                  .read_text(encoding="utf-8"))
_items7 = _sh7["mc_servers"]["templates"]["server"]["items"]
_ikeys7 = list(_items7.keys())
assert _ikeys7[-1] == "reconnect", \
    f"reconnect 分组必须位于模板项最底部，实际顺序: {_ikeys7}"
_sitems7 = _items7["server"]["items"]
for _old7 in ("reconnect_interval", "max_reconnect",
              "low_frequency_threshold", "low_frequency_interval"):
    assert _old7 not in _sitems7, f"server 子对象不得再含 {_old7}"
_ritems7 = _items7["reconnect"]["items"]
assert _ritems7["low_frequency_threshold"]["default"] == 30, \
    "schema 阈值默认必须为 30"
assert _ritems7["low_frequency_interval"]["default"] == 300, \
    "schema 低频间隔默认必须为 300（5 分钟）"
assert _ritems7["reconnect_interval"]["default"] == 5
assert _ritems7["max_reconnect"]["default"] == 0
assert "30" in _ritems7["low_frequency_threshold"]["hint"], \
    "阈值 hint 必须说明默认 30"
print("OK  重连配置独立成组置底、默认 30 次后进入低频、低频间隔可自定义、旧配置兼容 全部通过")

print("\n=== 26. 图片转发到 MC（ChatImage 联动） ===")
from astrbot_plugin_minecraft_queqiao.services.message_bridge import (
    build_chatimage_code as _bcc,
    resolve_image_url as _riu,
)
from astrbot_plugin_minecraft_queqiao.core.constants import (
    DEFAULT_CHATIMAGE_NAME as _DCN26,
)

# (a) 代码生成：[[CICode,url=...,name=...]]，name 缺省/留空回落「图片」
assert _DCN26 == "图片"
assert _bcc("https://gchat.qpic.cn/a/b.png") == \
    "[[CICode,url=https://gchat.qpic.cn/a/b.png,name=图片]]"
assert _bcc("https://x/y.png", "QQ图片") == \
    "[[CICode,url=https://x/y.png,name=QQ图片]]"
assert _bcc("https://x/y.png", "   ") == \
    "[[CICode,url=https://x/y.png,name=图片]]"

# (b) URL 解析优先级：url → file(http) → 文件服务注册兜底 → None
class _Img26(Image):
    """可控的图片组件桩：url/file 任意组合 + 可注入注册行为。"""
    def __init__(self, url="", file="", register=None):
        super().__init__(file=file, url=url)
        self._register = register
    async def register_to_file_service(self):
        if self._register is None:
            raise RuntimeError("no callback_api_base")
        return self._register

assert asyncio.run(_riu(_Img26(url="https://qpic.cn/a.png",
                               file="base64://xxx")))[0] == "https://qpic.cn/a.png"
assert asyncio.run(_riu(_Img26(url="", file="https://cdn.example/b.jpg")))[0] \
    == "https://cdn.example/b.jpg"
assert asyncio.run(_riu(_Img26(url="", file="base64://xxx")))[0] is None, \
    "只有 base64 且无法注册时应返回 None（跳过该图片）"
assert asyncio.run(_riu(_Img26(url="", file="",
                               register="https://astrbot.example/api/file/t")))[0] \
    == "https://astrbot.example/api/file/t", "文件服务兜底应生成可访问链接"
assert asyncio.run(_riu(_Img26(url="", file="", register="not-a-url")))[0] is None
assert asyncio.run(_riu(_Img26(url="", file="", register=None)))[0] is None, \
    "注册失败不得抛异常，应返回 None"
_r26_ret = asyncio.run(_riu(_Img26(url="", file="base64://xxx")))
assert _r26_ret[1] and "无公开 URL" in _r26_ret[1], \
    "失败时必须给出排障原因（供日志展示）: " + repr(_r26_ret)

# (c) 配置解析：默认关闭、可开启、名称缺省/清空回落「图片」
_cfg26 = SC.from_dict({"message": {"forward_image_to_mc": True, "chatimage_name": "群图"}})
assert _cfg26.forward_image_to_mc is True and _cfg26.chatimage_name == "群图"
assert SC.from_dict({}).forward_image_to_mc is False
assert SC.from_dict({}).chatimage_name == "图片"
assert SC.from_dict({"message": {"forward_image_to_mc": "false", "chatimage_name": ""}})\
    .chatimage_name == "图片"
assert SC.from_dict({"message": {"forward_image_to_mc": "true"}}).forward_image_to_mc is True
assert SC.from_dict({"message": {"chatimage_name": "  "}}).chatimage_name == "图片"

# (d) 端到端：外部图片消息 → 转发为 ChatImage 代码广播进游戏
from astrbot_plugin_minecraft_queqiao.main import MinecraftQueQiaoPlugin as _P26

class _Ctx26:
    async def send_message(self, *a, **k): return True

class _Cli26:
    def __init__(self): self.sent = []
    async def broadcast(self, text, color="white"):
        self.sent.append((text, color)); return True

class _Inst26:
    def __init__(self): self.client = _Cli26(); self.connected = True

class _Ev26:
    """模拟外部会话消息事件（aiocqhttp 形态：message_str 只含文本）。"""
    def __init__(self, text="", images=(), sender="群友A", platform="aiocqhttp"):
        self._text = text; self._images = list(images)
        self._sender = sender; self._platform = platform
        self.is_at_or_wake_command = False
        self.unified_msg_origin = "umo:GroupMessage:9"
        self.stopped = False
        self.message_obj = None
    def get_message_str(self): return self._text
    def get_messages(self): return self._images
    def get_sender_name(self): return self._sender
    def get_sender_id(self): return ""
    def get_platform_name(self): return self._platform
    def stop_event(self): self.stopped = True
    def plain_result(self, text): return text

def _run26(coro): return asyncio.new_event_loop().run_until_complete(coro)

# d1) 图片-only 消息 + 开启转发 → 广播 ChatImage 代码（默认名「图片」）
_pi26 = _P26(_Ctx26(), {})
_cfgI26 = SC.from_dict({"server": {"server_name": "IMG"},
    "message": {"target_sessions": ["umo:GroupMessage:9"], "forward_image_to_mc": True}})
_pi26.message_bridge.register_server(_cfgI26)
_instI26 = _Inst26()
_pi26.server_manager._servers["IMG"] = _instI26
_evI26 = _Ev26(images=[_Img26(url="https://gchat.qpic.cn/a/b.png")])
assert _run26(_pi26._relay_to_minecraft(_evI26, "umo:GroupMessage:9", "",
                                        [_evI26._images[0]])) is True
assert _instI26.client.sent == [
    ("[QQ]群友A: [[CICode,url=https://gchat.qpic.cn/a/b.png,name=图片]]", "white"),
], _instI26.client.sent

# d2) 关闭转发 → 图片不进入游戏（纯文本消息照常）
_pi26b = _P26(_Ctx26(), {})
_cfgI26b = SC.from_dict({"server": {"server_name": "IMG"},
    "message": {"target_sessions": ["umo:GroupMessage:9"], "forward_image_to_mc": False}})
_pi26b.message_bridge.register_server(_cfgI26b)
_instI26b = _Inst26()
_pi26b.server_manager._servers["IMG"] = _instI26b
assert _run26(_pi26b._relay_to_minecraft(
    _Ev26(images=[_Img26(url="https://gchat.qpic.cn/a/b.png")]),
    "umo:GroupMessage:9", "", [_Img26(url="https://gchat.qpic.cn/a/b.png")])) is False
assert _instI26b.client.sent == [], "关闭转发后图片不得进入游戏"

# d3) 文本 + 图片 → 文本与 CICode 拼接在同一广播里
_pi26c = _P26(_Ctx26(), {})
_pi26c.message_bridge.register_server(_cfgI26)
_instI26c = _Inst26()
_pi26c.server_manager._servers["IMG"] = _instI26c
_imgc = _Img26(url="https://qpic.cn/c.png")
assert _run26(_pi26c._relay_to_minecraft(
    _Ev26(text="看看这张图", images=[_imgc]), "umo:GroupMessage:9",
    "看看这张图", [_imgc])) is True
assert _instI26c.client.sent == [
    ("[QQ]群友A: 看看这张图 [[CICode,url=https://qpic.cn/c.png,name=图片]]", "white"),
], _instI26c.client.sent

# d4) 前缀过滤对图片同样生效：配置了转发前缀后，无文本的裸图片不转发
_cfgI26d = SC.from_dict({"server": {"server_name": "IMG"},
    "message": {"target_sessions": ["umo:GroupMessage:9"],
                "auto_forward_prefix": "*", "forward_image_to_mc": True}})
_pi26d = _P26(_Ctx26(), {})
_pi26d.message_bridge.register_server(_cfgI26d)
_instI26d = _Inst26()
_pi26d.server_manager._servers["IMG"] = _instI26d
assert _run26(_pi26d._relay_to_minecraft(
    _Ev26(images=[_Img26(url="https://qpic.cn/d.png")]),
    "umo:GroupMessage:9", "", [_Img26(url="https://qpic.cn/d.png")])) is False
assert _instI26d.client.sent == [], "配置转发前缀后裸图片不得转发"

# d5) 图片无公开 URL（base64 且注册失败）→ 跳过图片，文本仍转发
_img_b64 = _Img26(url="", file="base64://aGVsbG8=")
_pi26e = _P26(_Ctx26(), {})
_pi26e.message_bridge.register_server(_cfgI26)
_instI26e = _Inst26()
_pi26e.server_manager._servers["IMG"] = _instI26e
assert _run26(_pi26e._relay_to_minecraft(
    _Ev26(text="带图消息", images=[_img_b64]), "umo:GroupMessage:9",
    "带图消息", [_img_b64])) is True
assert _instI26e.client.sent == [
    ("[QQ]群友A: 带图消息", "white"),
], "base64 图片无法访问时应跳过图片、保留文本"

# d6) _extract_images 只挑图片段，忽略文本
_ev_mixed = _Ev26(text="x", images=[_Img26(url="https://a/b.png"), "not-image"])
assert len(_P26._extract_images(_ev_mixed)) == 1

# d7) schema 守卫：新配置项在 message 分组内、默认值 = 关闭/图片，hint 提到 ChatImage
_sh26 = json.loads(_pathlib.Path(__file__).with_name("_conf_schema.json")
                   .read_text(encoding="utf-8"))
_mi26 = _sh26["mc_servers"]["templates"]["server"]["items"]["message"]["items"]
assert "forward_image_to_mc" in _mi26 and "chatimage_name" in _mi26
assert _mi26["forward_image_to_mc"]["default"] is False
assert _mi26["chatimage_name"]["default"] == "图片"
assert "ChatImage" in _mi26["forward_image_to_mc"]["hint"], \
    "forward_image_to_mc 的 hint 必须说明依赖 ChatImage 模组"
_mk26 = list(_mi26.keys())
assert _mk26.index("forward_image_to_mc") == _mk26.index("mark_emoji_id") + 1, \
    f"forward_image_to_mc 必须紧跟 mark_emoji_id，实际顺序: {_mk26}"
assert _mk26.index("chatimage_name") == _mk26.index("forward_image_to_mc") + 1
print("OK  CICode 生成 / URL 解析优先级 / 配置解析 / 端到端转发 / 前缀过滤 / schema 同步")

print("\n=== 28. 图片转存服务（内置 HTTP 与第三方图床统一条目列表） ===")
from astrbot_plugin_minecraft_queqiao.services.image_host import (
    ImageHost as _IH28,
    guess_image_content_type as _gct28,
)
from astrbot_plugin_minecraft_queqiao.services.image_bed import (
    BuiltinHttpUploader as _BIH28,
    ImageBedUploader as _IB28,
    ImageBedUploaderGroup as _IBG28,
    extract_json_url as _ej28,
    parse_headers as _ph28,
    VALID_RESPONSE_KINDS as _KIND28,
)
from astrbot_plugin_minecraft_queqiao.services.message_bridge import (
    acquire_image_bytes as _aib28,
    resolve_image_url as _riu28,
)
from astrbot_plugin_minecraft_queqiao.core.constants import (
    DEFAULT_IMAGE_HTTP_HOST as _DHOST28,
    DEFAULT_IMAGE_HTTP_PORT as _DPORT28,
    IMAGE_HOST_MAX_IMAGES as _MAX28,
    IMAGE_HOST_TTL as _TTL28,
)
from astrbot_plugin_minecraft_queqiao.main import (
    MinecraftQueQiaoPlugin as _P28,
    TEMPLATE_KEY_BUILTIN_HTTP as _TK28,
)

# (a) MIME 猜测（按魔数）
assert _gct28(b"\x89PNG\r\n\x1a\n...") == "image/png"
assert _gct28(b"\xff\xd8\xff\xe0...") == "image/jpeg"
assert _gct28(b"GIF89a...") == "image/gif"
assert _gct28(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"
assert _gct28(b"BM\x00\x00") == "image/bmp"
assert _gct28(b"unknown-bytes") == "application/octet-stream"
assert _TTL28 >= 300 and _MAX28 >= 100, "缓存 TTL 与上限常量应合理"

# (b) register / enabled 语义
_host28 = _IH28()
assert _host28.enabled is False
assert _host28.register(b"x") is None, "未启用时不得登记"
_host28.base_url = "http://1.2.3.4:8765"
assert _host28.enabled is True
_u28 = _host28.register(b"data")
assert _u28 and _u28.startswith("http://1.2.3.4:8765/img/"), _u28
assert _host28.register(b"") is None
assert len(_host28._images) == 1
_token28 = _u28.rsplit("/", 1)[1]
assert _host28._images[_token28][1] == b"data", "登记的字节必须可被原样取回"
_time28 = _host28._images[_token28][0]
assert isinstance(_time28, float)

# (c) 图片字节获取：有 convert_to_file_path 时读出字节；缺失时返回 None
class _NoBytes28:
    """完全没有字节来源的组件。"""
class _ImgBytes28(Image):
    def __init__(self, data=b"\x89PNG\r\n\x1a\nfake", file="base64://aGVsbG8="):
        super().__init__(file=file, url="")
        self.data = data
        self._path = None
    async def convert_to_file_path(self):
        if self._path is None:
            fd, name = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            with open(name, "wb") as f:
                f.write(self.data)
            self._path = name
        return self._path

assert asyncio.run(_aib28(_NoBytes28()))[0] is None
assert asyncio.run(_aib28(_NoBytes28()))[1], "缺失字节来源要有原因"
_ib28 = _ImgBytes28()
assert asyncio.run(_aib28(_ib28))[0] == _ib28.data
assert asyncio.run(_aib28(_ib28))[0] == _ib28.data, "可重复读取（同路径）"
assert asyncio.run(_aib28(_ib28))[1] == "", "成功时原因应为空"

# (d) resolve 优先级：无公开 URL + 启用内置服务 → 转存并返回 hosted URL
_b_d28 = _BIH28(base_url="http://192.168.1.5:8765")
_b_d28._started = True  # 离线自检不真起 aiohttp 监听，直接置位
_g_d28 = _IBG28(); _g_d28.uploaders = [_b_d28]
_img_d28 = _ImgBytes28()
_hosted28 = asyncio.run(_riu28(_img_d28, _g_d28))
assert _hosted28[0] and _hosted28[0].startswith("http://192.168.1.5:8765/img/"), \
    _hosted28
_tok28 = _hosted28[0].rsplit("/", 1)[1]
assert _b_d28._host._images[_tok28][1] == _img_d28.data, \
    "hosted URL 对应的缓存字节必须与源图片一致"

# 未启用（分组为空）→ 落到文件服务兜底（桩无 callback_api_base → 抛错 → None）
assert asyncio.run(_riu28(_ImgBytes28(), _IBG28()))[0] is None

# 带公开 URL 时走直连，不占用内置服务缓存
_b_e28 = _BIH28(base_url="http://x:1"); _b_e28._started = True
_g_e28 = _IBG28(); _g_e28.uploaders = [_b_e28]
assert asyncio.run(_riu28(Image(url="https://qpic.cn/a.png"), _g_e28))[0] \
    == "https://qpic.cn/a.png"
assert _b_e28._host._images == {}, "公开 URL 不应被转存"

# 启用了内置服务但拿不到字节（convert 抛错）→ None
class _BadBytes28(Image):
    async def convert_to_file_path(self):
        raise RuntimeError("boom")
_bad28 = asyncio.run(_riu28(_BadBytes28(file="base64://x"), _g_d28))
assert _bad28[0] is None
assert "convert_to_file_path" in _bad28[1], "失败原因应反映字节获取失败: " + _bad28[1]

# (e) 根级配置默认值与 hint（conf 模板 ↔ 代码兜底值一致）
_sh28 = json.loads(_pathlib.Path(__file__).with_name("_conf_schema.json")
                   .read_text(encoding="utf-8"))
assert _sh28["enable_image_upload"]["default"] is False
assert _sh28["image_upload_services"]["type"] == "template_list"
for _k28 in ("enable_image_upload", "image_upload_timeout",
             "image_upload_services"):
    assert _k28 in _sh28, f"根级配置缺少 {_k28}"
assert "玩家" in _sh28["enable_image_upload"]["hint"], \
    "enable_image_upload 的 hint 必须说明玩家可达性前提"
assert _sh28["enable_image_upload"]["hint"], "开关的 hint 不应为空"
# 图床：默认不加载任何条目；预配置图床只作为「添加条目」的模板
# （内置图片 HTTP 服务 / 自定义图床 各自在前）
_bsrv28 = _sh28["image_upload_services"]
assert _bsrv28["default"] == [], "图床默认不加载任何条目，由用户按模板添加"
_tpls28 = _bsrv28["templates"]
assert list(_tpls28)[0] == "builtin_http", "模板列表最上方应是「内置图片HTTP服务」"
assert list(_tpls28)[1] == "custom", "第二个应是「自定义图床」"
# 内置条目不占第三方额度，但代价是 AstrBot 必须能被玩家客户端访问到——
# 这是它和第三方图床最关键的区别，必须在模板 hint 里讲明
assert "公网" in _tpls28["builtin_http"]["hint"], \
    "内置条目 hint 应提示需要公网可达地址"
# 只保留实测可用的图床：0x0（官方暂停上传）、tutu（接口已拒绝跨站 POST）、
# imgur（官方 API 与 Bearer token 不兼容）、postimages（已转 Drive Hosting，
# 匿名上传被 403 拒绝并要求 api.postimages.org 的 key）、
# postimg.org（DNS 失效）、shturl.cc（域名不存在，NXDOMAIN）、
# imgurl.cc（TLS 握手挂起超时）、tukr.com（域名已改为美国餐厅点评站，
# 图壳服务已死）、sxcu.net（整站 Cloudflare JS 盾，非浏览器无法过）、
# ctrlq/hostpic/unsee/fb.pics/freeimg/48pic/ooonline/52img 等
# （DNS 失效或连接超时）已移除；pngcdn.cn 迁移到 pngurl.com 后实测访客
# 上传可用，以 pngurl 模板恢复；picui / anyapi / xinyew / xunjinlu 均为
# 用户提供、实测游客免 token 上传可用后新增；imglink / litterbox 为
# 实测匿名直传可用后新增（litterbox 端点须为 /resources/internals/api.php，
# 文档常见的 /api/upload.php 已 404）
assert set(_tpls28) == {
    "builtin_http", "custom", "catbox", "litterbox", "imglink",
    "imgloc", "img402", "pngurl",
    "see", "imgbb", "picui", "anyapi", "xinyew", "xunjinlu",
}, \
    f"图床模板应只保留实测可用者，实际 {list(_tpls28)}"
# hint 只讲两件事：如何添加 + 失败自动切换下一个
assert "添加条目" in _bsrv28["hint"] and "下一个" in _bsrv28["hint"], \
    "hint 应说明添加方式与失败自动切换下一个图床"
# 备注统一紧凑格式（地区词：是否需 token，大小限制），不得出现
# 「以站点为准」这类无定数表述，也不得在备注里提请求头（预填进字段即可）
for _hk28 in _tpls28:
    _hint28 = _tpls28[_hk28]["hint"]
    assert "：" in _hint28, f"模板 {_hk28} 的 hint 应含冒号分隔地区与说明"
    assert "以站点为准" not in _hint28, \
        f"模板 {_hk28} 的 hint 不应写「以站点为准」这类无定数大小"
    assert "Accept" not in _hint28 and "请求头" not in _hint28, \
        f"模板 {_hk28} 的 hint 不应提及请求头（预填进字段即可）"
_BASE_FIELDS28 = {"enabled", "name", "upload_url", "token", "response"}
# 只在「需要」的模板上加扩展字段：file_field 仅字段名非 file 或自定义；
# headers 仅需要额外请求头的模板（自定义 + pngurl 必带 Accept）；
# form_fields 仅需要额外普通表单字段的模板（自定义 + litterbox 必填 time）
_TPL_FIELDS28 = {
    # 内置条目不需要上传接口，自带 host/port/base_url 三项
    "builtin_http": {"enabled", "name", "host", "port", "base_url"},
    "custom": _BASE_FIELDS28 | {"file_field", "headers", "form_fields"},
    "catbox": _BASE_FIELDS28 | {"file_field"},
    # litterbox：catbox 的临时分支，同 catbox 的 fileToUpload + reqtype 兼容，
    # 额外要求 form_fields 里的 time=72h（漏填服务端返回 500）
    "litterbox": _BASE_FIELDS28 | {"file_field", "form_fields"},
    # imglink：默认 file 字段、无额外请求头与表单字段
    "imglink": _BASE_FIELDS28,
    "imgloc": _BASE_FIELDS28,
    "img402": _BASE_FIELDS28 | {"file_field"},
    "pngurl": _BASE_FIELDS28 | {"headers"},
    # see：S.EE 用 Authorization 直传 key（不带 Bearer），不走 token 字段，
    # 改用 headers 配 Authorization；文件字段名是 smfile
    "see": _BASE_FIELDS28 - {"token"} | {"file_field", "headers"},
    "imgbb": _BASE_FIELDS28 | {"file_field"},
    # picui：Lsky 风格接口，游客免 token，但必须带 Accept 头
    "picui": _BASE_FIELDS28 | {"headers"},
    # anyapi / xinyew / xunjinlu：游客免 token，默认 file 字段，无额外请求头
    "anyapi": _BASE_FIELDS28,
    "xinyew": _BASE_FIELDS28,
    "xunjinlu": _BASE_FIELDS28,
}
for _tk28 in _tpls28:
    _ti28 = _tpls28[_tk28]["items"]
    assert set(_ti28) == _TPL_FIELDS28[_tk28], \
        f"模板 {_tk28} 字段集应为 {sorted(_TPL_FIELDS28[_tk28])}，实际 {sorted(_ti28)}"
    if _tk28 != "builtin_http":
        assert _ti28["response"]["default"], f"模板 {_tk28} 应预填 response"
    if "file_field" in _ti28:
        assert _ti28["file_field"]["default"], \
            f"模板 {_tk28} 的 file_field 应有默认值"
    if "headers" in _ti28:
        assert "headers" in _ti28 and isinstance(_ti28["headers"]["default"], str), \
            f"模板 {_tk28} 的 headers 应为字符串配置"
    if "form_fields" in _ti28:
        assert isinstance(_ti28["form_fields"]["default"], str), \
            f"模板 {_tk28} 的 form_fields 应为字符串配置"
    if _tk28 not in ("custom", "builtin_http"):
        assert _ti28["upload_url"]["default"], \
            f"预配置模板 {_tk28} 应预填 upload_url"
assert _tpls28["custom"]["items"]["upload_url"]["default"] == ""
assert _tpls28["custom"]["items"]["file_field"]["default"] == "file"
assert _tpls28["custom"]["items"]["headers"]["default"] == ""
assert _tpls28["custom"]["items"]["form_fields"]["default"] == ""
assert _tpls28["builtin_http"]["items"]["base_url"]["default"] == ""
assert "玩家" in _tpls28["builtin_http"]["items"]["base_url"]["hint"], \
    "内置服务 base_url 的 hint 必须说明玩家可达性前提"
assert _tpls28["catbox"]["items"]["upload_url"]["default"] == \
    "https://catbox.moe/user/api.php"
assert _tpls28["catbox"]["items"]["response"]["default"] == "text"
# litterbox（catbox 临时分支）：实测文档常见的 /api/upload.php 已 404，
# 真实端点是 /resources/internals/api.php；必须预填 fileToUpload + time=72h
# （litterbox 少 time 字段直接返回 500，实测确认）
assert _tpls28["litterbox"]["items"]["upload_url"]["default"] == \
    "https://litterbox.catbox.moe/resources/internals/api.php", \
    "litterbox 端点必须是实测可用的 /resources/internals/api.php"
assert "/api/upload.php" not in _tpls28["litterbox"]["items"]["upload_url"]["default"], \
    "litterbox 的 /api/upload.php 端点已 404，不得预填"
assert _tpls28["litterbox"]["items"]["response"]["default"] == "text"
assert _tpls28["litterbox"]["items"]["name"]["default"] == "litterbox"
assert _tpls28["litterbox"]["items"]["file_field"]["default"] == "fileToUpload", \
    "litterbox 沿用 catbox 的 fileToUpload 字段名"
assert _tpls28["litterbox"]["items"]["form_fields"]["default"] == "time: 72h", \
    "litterbox 必须预填 time=72h（不带该字段服务端返回 500）"
assert _tpls28["litterbox"]["items"]["token"]["default"] == "", \
    "litterbox 匿名上传，token 默认应留空"
# imglink：默认 file 字段、json 响应、匿名
assert _tpls28["imglink"]["items"]["upload_url"]["default"] == \
    "https://imglink.cc/api/upload"
assert _tpls28["imglink"]["items"]["response"]["default"] == "json"
assert _tpls28["imglink"]["items"]["name"]["default"] == "imglink"
assert _tpls28["imglink"]["items"]["token"]["default"] == "", \
    "imglink 匿名上传，token 默认应留空"
assert "file_field" not in _tpls28["imglink"]["items"], \
    "imglink 用默认 file 字段，无需展示 file_field"
assert _tpls28["imgloc"]["items"]["upload_url"]["default"] == \
    "https://api.imgse.com/1/upload"
assert _tpls28["imgloc"]["items"]["response"]["default"] == "json"
assert _tpls28["imgloc"]["items"]["name"]["default"] == "imgloc"
# 预填校验：字段名不同的图床必须带对 file_field
assert _tpls28["img402"]["items"]["upload_url"]["default"] == \
    "https://img402.dev/api/free"
assert _tpls28["img402"]["items"]["file_field"]["default"] == "image"
assert _tpls28["img402"]["items"]["response"]["default"] == "json"
# pngurl（原 pngcdn.cn 迁移）：接口、json 解析与 Accept 请求头必须预填，
# 访客上传可用所以 token 留空
assert _tpls28["pngurl"]["items"]["upload_url"]["default"] == \
    "https://pngurl.com/api/v1/upload"
assert _tpls28["pngurl"]["items"]["response"]["default"] == "json"
assert _tpls28["pngurl"]["items"]["headers"]["default"] == \
    "Accept: application/json", "pngurl 必须预填 Accept 请求头"
assert _tpls28["pngurl"]["items"]["token"]["default"] == "", \
    "pngurl 访客上传可用，token 默认应留空"
assert "file_field" not in _tpls28["pngurl"]["items"], \
    "pngurl 用默认 file 字段，无需展示 file_field"
# 不需要额外请求头的模板不应展示 headers 字段
for _hk28 in ("catbox", "imgloc", "img402", "imgbb", "litterbox", "imglink",
              "anyapi", "xinyew", "xunjinlu"):
    assert "headers" not in _tpls28[_hk28]["items"], \
        f"模板 {_hk28} 不需要额外请求头，不应展示 headers 字段"
# 不需要额外普通表单字段的模板不应展示 form_fields 字段（litterbox 例外：
# 它必填 time=72h；自定义模板保留它以便自由接入任意图床）
for _hk28 in _tpls28:
    if _hk28 in ("custom", "litterbox"):
        continue
    assert "form_fields" not in _tpls28[_hk28]["items"], \
        f"模板 {_hk28} 不需要额外表单字段，不应展示 form_fields 字段"
# 走 headers 配 Authorization 的模板不应展示 token 字段（token 会自动加 Bearer 前缀，
# 与这些图床的鉴权格式不兼容）
for _tk28 in ("see",):
    assert "token" not in _tpls28[_tk28]["items"], \
        f"模板 {_tk28} 用 headers 直传 key，不应展示 token 字段"
# 新模板预填校验
assert _tpls28["see"]["items"]["upload_url"]["default"] == \
    "https://s.ee/api/v1/file/upload"
assert _tpls28["see"]["items"]["response"]["default"] == "json"
assert _tpls28["see"]["items"]["file_field"]["default"] == "smfile", \
    "S.EE 文件字段名是 smfile"
assert _tpls28["see"]["items"]["headers"]["default"].startswith(
    "Authorization: "), \
    "S.EE 必须预填 Authorization 请求头前缀，让用户直接填 key"
assert _tpls28["imgbb"]["items"]["upload_url"]["default"] == \
    "https://api.imgbb.com/1/upload"
assert _tpls28["imgbb"]["items"]["response"]["default"] == "json"
assert _tpls28["imgbb"]["items"]["file_field"]["default"] == "image", \
    "imgbb 文件字段名是 image"
assert _tpls28["imgbb"]["items"]["token"]["default"] == ""
# picui：游客免 token、响应 json、必须预填 Accept 请求头（hint 里不提）
assert _tpls28["picui"]["items"]["upload_url"]["default"] == \
    "https://picui.cn/api/v1/upload"
assert _tpls28["picui"]["items"]["response"]["default"] == "json"
assert _tpls28["picui"]["items"]["headers"]["default"] == \
    "Accept: application/json", "picui 必须预填 Accept 请求头"
assert _tpls28["picui"]["items"]["token"]["default"] == ""
# anyapi / xinyew / xunjinlu：游客免 token，默认 file 字段
assert _tpls28["anyapi"]["items"]["upload_url"]["default"] == \
    "https://imageproxy.zhongzhuan.chat/api/upload"
assert _tpls28["xinyew"]["items"]["upload_url"]["default"] == \
    "https://api.xinyew.cn/api/360tc"
assert _tpls28["xunjinlu"]["items"]["upload_url"]["default"] == \
    "https://api.xunjinlu.fun/tc/api.php"
for _nk28 in ("anyapi", "xinyew", "xunjinlu"):
    assert _tpls28[_nk28]["items"]["response"]["default"] == "json"
    assert _tpls28[_nk28]["items"]["token"]["default"] == "", \
        f"{_nk28} 游客免 token，token 默认应留空"
    assert "file_field" not in _tpls28[_nk28]["items"], \
        f"{_nk28} 用默认 file 字段，无需展示 file_field"
# 新模板 hint 格式：地区词：是否需token，大小限制
for _hk28 in ("see", "imgbb", "litterbox", "imglink"):
    _hint28 = _tpls28[_hk28]["hint"]
    assert "：" in _hint28, f"模板 {_hk28} 的 hint 应含冒号分隔地区与说明"
    _region28 = _hint28.split("：")[0]
    assert _region28 in ("国内", "海外"), \
        f"模板 {_hk28} 的 hint 地区词应为 国内/海外，实际 {_region28}"
assert "不限定" in _tpls28["custom"]["items"]["upload_url"]["hint"] or \
    "任意" in _tpls28["custom"]["items"]["upload_url"]["hint"], \
    "自定义模板的 upload_url hint 应体现不限制服务商"

# (f) 内置图片 HTTP 条目守卫：base_url 为空不启用；启动失败回滚 base_url
from astrbot_plugin_minecraft_queqiao.services.image_bed import (
    BuiltinHttpUploader as _BH28,
)
from astrbot_plugin_minecraft_queqiao.core.constants import (
    DEFAULT_IMAGE_HTTP_HOST as _DEFH28,
    DEFAULT_IMAGE_HTTP_PORT as _DEFPORT28,
)
class _Host28Stub:
    def __init__(self):
        self.base_url = ""; self.started = None
    async def start(self, host, port):
        self.started = (host, port)
    async def stop(self):
        pass

# base_url 留空 = 条目未配置对外地址：不得占用端口，start 直接跳过
_bh28a = _BH28(base_url="")
assert _bh28a.enabled is False, "base_url 为空不得启用"
_bh28a._host = _Host28Stub()
asyncio.run(_bh28a.start())
assert _bh28a._host.started is None, "base_url 为空不得启动监听"

# 配置玩家可达的 base_url → 启用并按 host/port 启动监听，base_url 保留
_bh28b = _BH28(base_url="http://1.2.3.4:8765")
_bh28b._host = _Host28Stub()
asyncio.run(_bh28b.start())
assert _bh28b._host.started == (_DEFH28, _DEFPORT28), _bh28b._host.started
assert _bh28b.base_url == "http://1.2.3.4:8765"
assert _bh28b.display_name.startswith("内置图片HTTP服务")
assert _BH28(base_url="内置图片HTTP服务", name="我的NAS").display_name == "我的NAS"

# base_url 非 http(s) → 不启用（127.0.0.1 这类地址由用户自行判断是否可用）
for _bad in ("", "ftp://x:1", "x:1", "      "):
    assert _BH28(base_url=_bad).enabled is False, f"{_bad!r} 不得启用"

# 启动失败必须回滚 base_url（进而退出上传链），避免误报服务可用
class _Host28Fail:
    def __init__(self):
        self.base_url = ""; self.calls = 0
    async def start(self, host, port):
        self.calls += 1
        raise RuntimeError("port busy")
    async def stop(self):
        pass
_bh28c = _BH28(base_url="http://x:1")
_bh28c._host = _Host28Fail()
try:
    asyncio.run(_bh28c.start())
except RuntimeError:
    pass
else:
    raise AssertionError("启动失败应向上抛出")
assert _bh28c.base_url == "" and _bh28c.enabled is False, \
    "启动失败必须回滚 base_url，避免误报可访问"
assert _bh28c._host.calls == 1

# upload：未启用 / 未启动 / 启动后登记成功
assert asyncio.run(_BH28().upload(b"x"))[0] is None, "未启用不得发起上传"
assert asyncio.run(_bh28b.upload(b""))[0] is None, "空数据不得上传"
_bh28d = _BH28(base_url="http://x:1")
_bh28d._host = _Host28Stub()
assert asyncio.run(_bh28d.upload(b"x"))[1].startswith("监听未启动"), \
    "监听未启动时不得调用登记"
print("OK  MIME 猜测 / 登记与缓存 / 字节获取 / resolve 优先级 / 内置服务生命周期")

# (g) 通用图床方案：不限服务商 / enabled 语义 / 多条目接线 / resolve 联动
from astrbot_plugin_minecraft_queqiao.services.image_bed import (
    ImageBedUploader as _IB28,
    ImageBedUploaderGroup as _IBG28,
    UPLOAD_TIMEOUT as _UT28,
    extract_json_url as _ej28,
    parse_headers as _ph28,
    parse_form_fields as _pff28,
    VALID_RESPONSE_KINDS as _KIND28,
)
assert _IB28().enabled is False, "upload_url 为空 = 关闭"
assert _IB28("http://x/u").enabled and _IB28("https://x/u", response="json").enabled
assert _IB28("https://x/u", response="bad").enabled is False, \
    "不支持的解析方式 = 关闭"
assert _IB28("ftp://x/u").enabled is False, "非 http(s) 地址 = 关闭"
assert _IB28("  https://x/u  ").enabled, "upload_url 应去除首尾空白"
assert _IB28("https://x/u").display_name == "x", "未命名时用主机名"
assert _IB28("https://x/u", name="我的图床").display_name == "我的图床"
assert asyncio.run(_IB28().upload(b"x"))[0] is None, "未启用不得发起上传"
assert asyncio.run(_IB28("not-a-url").upload(b"x"))[0] is None

# 自定义请求头：行格式 / JSON 格式 / 非法输入
assert _ph28("") is None and _ph28(None) is None and _ph28("   ") is None
assert _ph28("Accept: application/json\nX-Api-Key: abc") == {
    "Accept": "application/json", "X-Api-Key": "abc"}
assert _ph28('{"Accept": "application/json", "X-Api-Key": "abc"}') == {
    "Accept": "application/json", "X-Api-Key": "abc"}
assert _ph28("没有冒号的脏行") is None
assert _ph28('{"broken json') is None
assert _ph28('["not", "a", "dict"]') is None
# 值为空的条目应忽略，避免发出 `Authorization: ` 空值请求头（see 模板预填
# Authorization 前缀，用户不填 key 时不应发送空头）
assert _ph28("Authorization: ") is None
assert _ph28('{"Authorization": ""}') is None
assert _ph28("Authorization: \nAccept: application/json") == \
    {"Accept": "application/json"}
assert _ph28("Authorization: my-key") == {"Authorization": "my-key"}
_ib28h = _IB28("https://x/u", headers="Accept: application/json")
assert _ib28h.headers == {"Accept": "application/json"}, _ib28h.headers
assert _IB28("https://x/u").headers is None, "未配置请求头时为 None"

# 额外表单字段：行格式 / JSON 格式 / 非法输入（与 headers 同一套解析）
assert _pff28("") is None and _pff28(None) is None and _pff28("   ") is None
assert _pff28("time: 72h") == {"time": "72h"}
assert _pff28("time: 12h\nalbum: public") == {"time": "12h", "album": "public"}
assert _pff28('{"time": "24h", "album": "public"}') == {"time": "24h", "album": "public"}
assert _pff28("没有冒号的脏行") is None
assert _pff28('{"broken json') is None
# 值为空的条目应忽略
assert _pff28("time: ") is None
assert _pff28("time: \nalbum: public") == {"album": "public"}
_ib28f = _IB28("https://x/u", form_fields="time: 72h")
assert _ib28f.form_fields == {"time": "72h"}, _ib28f.form_fields
assert _IB28("https://x/u").form_fields is None, "未配置表单字段时为 None"

# 上传超时（秒）：默认 30，可配置，非正数/非法值回落默认值
assert _UT28 == 30, "默认上传超时应为 30 秒"
assert _IB28("https://x/u").timeout == 30, "未配置时用默认超时"
assert _IB28("https://x/u", timeout=60).timeout == 60
assert _IB28("https://x/u", timeout="45").timeout == 45, \
    "WebUI 可能把数字存成字符串，需能解析"
assert _IB28("https://x/u", timeout=0).timeout == 1, "0 非法，回落最小 1 秒"
assert _IB28("https://x/u", timeout=-5).timeout == 1, "负数非法，回落最小 1 秒"
assert _IB28("https://x/u", timeout="abc").timeout == 30, \
    "无法解析的超时值回落默认，不能让上传因配置非法而整体失败"
assert _IB28("https://x/u", timeout=None).timeout == 30
assert _IB28("https://x/u", timeout="").timeout == 30

# JSON 响应解析：递归找第一个完整 http(s) URL 字段
assert _ej28('{"status": true, "data": {"url": "https://img.example/a.png"}}') \
    == "https://img.example/a.png"
assert _ej28('{"status": true, "urls": ["https://img.example/a.png", "/b.png"]}') \
    == "https://img.example/a.png"
assert _ej28('{"status": false, "msg": "no"}') is None
assert _ej28("not json") is None
assert _ej28('{"data": {"path": "/2026/09/a.png", "host": "cdn.example"}}') \
    is None, "不含完整 http(s) URL 的 JSON 视为失败（取不到链接）"
# 多 URL 响应（pngurl）：优先取 url 键，不得误取排在其后的 delete_url /
# thumbnail_url（旧实现的栈弹出是逆序的，会取到最后一个 http 字段）
_PNGURL_RESP28 = (
    '{"status": true, "message": "success", "data": {"key": "k1", '
    '"mimetype": "image/png", '
    '"url": "https://tg.xmxx.fun/i/k1.png", '
    '"thumbnail_url": "https://tg.xmxx.fun/t/k1.png", '
    '"delete_url": "https://pngurl.com/api/v1/images/k1"}}')
assert _ej28(_PNGURL_RESP28) == "https://tg.xmxx.fun/i/k1.png", \
    "pngurl 响应应取 data.url，不能取到 delete_url"
# 无 url 键时按字段顺序取第一个（不是最后一个）
assert _ej28('{"a": "https://first.example/a.png", '
             '"b": "https://last.example/b.png"}') == "https://first.example/a.png"
# 业务失败（HTTP 200 + status:false）应取不到链接，交给上层报失败原因
assert _ej28('{"status": false, "message": "存储容量不足", "data": null}') is None
assert _ej28('{"status": false, "message": "授权失败"}') is None
# 带垃圾前缀/尾随内容的响应（如 xunjinlu.fun 的 PHP 输出 `}\n?>` 后接 JSON）
# 应从第一个 `{` 起 lenient 解析，不得因整体 json.loads 失败而取不到链接
assert _ej28('}\n?>{"success": true, "url": "https://521.im/x.png"}') == \
    "https://521.im/x.png", "应忽略 PHP 垃圾前缀解析 JSON"
assert _ej28('{"success": true, "url": "https://521.im/x.png"} trailing') == \
    "https://521.im/x.png", "应忽略 JSON 后的尾随内容"
assert _ej28('error: not json at all') is None
assert _ej28('}\n?>{"success": false, "message": "文件大小超过限制"}') is None, \
    "垃圾前缀后的业务失败 JSON 仍应视为取不到链接"

# 条目分组：按顺序逐个尝试，任一成功即返回；全部失败聚合原因
class _Up28:
    """可注入结果的图床桩（离线不联网），模拟 (url, 失败原因) 返回。"""
    display_name = "桩图床"
    def __init__(self, result=None, enabled=True):
        self.enabled = enabled; self.result = result; self.calls = []
    async def upload(self, data):
        self.calls.append(data)
        if self.result:
            return self.result, ""
        return None, "boom"

_up28 = _Up28("https://img.example/x.png")
_gup28 = _IBG28(); _gup28.uploaders = [_up28]
_r28g = asyncio.run(_riu28(_ImgBytes28(), _gup28))
assert _r28g[0] == "https://img.example/x.png"
assert _up28.calls and _up28.calls[0] == _ib28.data, \
    "uploader 应收到与内置服务相同的图片字节"

# 上传失败 → 继续落文件服务兜底 → 桩抛错 → None + 原因含条目名与具体错误
_up28b = _Up28(None)
_gup28b = _IBG28(); _gup28b.uploaders = [_up28b]
_r28h = asyncio.run(_riu28(_ImgBytes28(), _gup28b))
assert _r28h[0] is None and "图片转存失败" in _r28h[1] and "boom" in _r28h[1], \
    _r28h[1]

# 全部条目未启用：分组不进上传分支（calls 保持为空）
_up28c = _Up28("https://nope")
_up28c.enabled = False
_gup28c = _IBG28(); _gup28c.uploaders = [_up28c]
asyncio.run(_riu28(_ImgBytes28(), _gup28c))
assert _up28c.calls == []

# 分组：逐个尝试，任一成功即返回；全失败时按「条目名: 原因」聚合
_g28 = _IBG28()
_g28.uploaders = [_Up28(None), _Up28("https://ok.example/a.png")]
_url28, _err28 = asyncio.run(_g28.upload(b"x"))
assert _url28 == "https://ok.example/a.png" and _err28 == "", \
    "前一个失败后应继续尝试下一个"
_g28b = _IBG28()
_g28b.uploaders = [_Up28(None), _Up28(None)]
_url28, _err28 = asyncio.run(_g28b.upload(b"x"))
assert _url28 is None and "boom" in _err28, \
    "全失败时原因应按条目聚合: " + _err28

# _setup_image_services 接线：总开关 + 条目列表（与 mc_servers 同款添加方式）
# 离线自检不真起 aiohttp 监听，把分组的生命周期方法换成空操作
async def _start_builtin_noop_28():
    return 0
def _mk_p28(conf):
    p = _P28(_Ctx26(), conf)
    p.image_bed.start_builtin = _start_builtin_noop_28
    return p

_bi28 = {"__template_key": _TK28, "enabled": True, "name": "本机",
         "host": "127.0.0.1", "port": "8808", "base_url": "http://1.2.3.4:8765"}
_beds28 = [
    _bi28,
    {"__template_key": "image_bed", "enabled": True,
     "name": "catbox", "upload_url": "https://catbox.moe/user/api.php",
     "token": "", "response": "text"},
    {"__template_key": _TK28, "enabled": False,
     "name": "关掉的内置", "host": "0.0.0.0", "port": 8766,
     "base_url": "http://1.2.3.5:8766"},
    {"__template_key": "image_bed", "enabled": True,
     "name": "imgloc", "upload_url": "https://api.imgse.com/1/upload",
     "token": "tk", "response": "json"},
]
_p28e = _mk_p28({"enable_image_upload": True, "image_upload_services": _beds28})
asyncio.run(_p28e._setup_image_services())
assert _p28e.image_bed.enabled
assert _p28e.image_bed.service_names == "本机, catbox, imgloc", \
    "关闭的条目不应计入: " + _p28e.image_bed.service_names
assert isinstance(_p28e.image_bed.uploaders[0], _BIH28) and \
    isinstance(_p28e.image_bed.uploaders[1], _IB28) and \
    isinstance(_p28e.image_bed.uploaders[2], _IB28), \
    "内置与第三方条目须按列表顺序混排且类型正确"
_bi_got = _p28e.image_bed.uploaders[0]
assert _bi_got.name == "本机" and _bi_got.host == "127.0.0.1" and \
    _bi_got.port == 8808 and _bi_got.base_url == "http://1.2.3.4:8765", \
    f"内置条目字段须按配置解析: {(_bi_got.name, _bi_got.host, _bi_got.port, _bi_got.base_url)}"
assert len(_p28e.image_bed.builtin_uploaders()) == 1, \
    "启用的内置条目应只有 1 个（关闭的不计入）"
assert _p28e.image_bed.uploaders[2].response == "json"
assert _p28e.image_bed.uploaders[2].token == "tk"

# 上传超时：根级 image_upload_timeout 全局注入第三方图床条目
# （_p28e 未配置该项 → 所有图床条目回落默认 30 秒）
for u in _p28e.image_bed.uploaders:
    if isinstance(u, _IB28):
        assert u.timeout == 30, \
            f"未配置超时时应回落默认值，实际 {u.timeout}"
_p28to = _mk_p28({"enable_image_upload": True, "image_upload_timeout": 60,
                  "image_upload_services": [
                      {"__template_key": "image_bed", "enabled": True,
                       "upload_url": "https://catbox.moe/user/api.php",
                       "response": "text"},
                      {"__template_key": "image_bed", "enabled": True,
                       "upload_url": "https://api.imgse.com/1/upload",
                       "response": "json", "token": "tk"},
                  ]})
asyncio.run(_p28to._setup_image_services())
assert [u.timeout for u in _p28to.image_bed.uploaders] == [60, 60], \
    "超时应注入到列表里的每一个第三方图床条目"
# WebUI 存成字符串、以及非法值（0 / 负数 / 无法解析）的防御式收敛
for conf_val, want in (("45", 45), (0, 1), (-5, 1), ("abc", 30), (None, 30)):
    _p28tc = _mk_p28({"enable_image_upload": True,
                      "image_upload_timeout": conf_val,
                      "image_upload_services": [
                          {"__template_key": "image_bed", "enabled": True,
                           "upload_url": "https://catbox.moe/user/api.php",
                           "response": "text"}]})
    asyncio.run(_p28tc._setup_image_services())
    got = _p28tc.image_bed.uploaders[0].timeout
    assert got == want, f"image_upload_timeout={conf_val!r} 应为 {want}，实际 {got}"
# 内置条目不受影响（本地上机，不发起外网请求）
assert all(not hasattr(u, "timeout") for u in _p28e.image_bed.builtin_uploaders()) \
    or _p28e.image_bed.builtin_uploaders()[0].timeout == 30, \
    "内置条目不需要外网上传超时"

# schema：image_upload_timeout 应紧挨在 enable_image_upload 与 image_upload_services 之间
_sh_keys28 = list(_sh28.keys())
_i28a, _i28b, _i28c = (
    _sh_keys28.index("enable_image_upload"),
    _sh_keys28.index("image_upload_timeout"),
    _sh_keys28.index("image_upload_services"),
)
assert _i28a + 1 == _i28b == _i28c - 1, \
    f"image_upload_timeout 应位于两个配置之间，实际顺序 {_sh_keys28}"
_to_schema28 = _sh28["image_upload_timeout"]
assert _to_schema28["type"] == "int" and _to_schema28["default"] == 30
assert "30 秒" in _to_schema28["hint"], \
    "超时 hint 应写出默认值，便于用户判断"
assert "调太大" in _to_schema28["hint"], \
    "超时 hint 应说明调太大的代价（降级到下一个图床会变慢）"

# 总开关关闭 → 即使有条目也不启用（也不启动任何监听）
_p28h = _mk_p28({"enable_image_upload": False, "image_upload_services": _beds28})
asyncio.run(_p28h._setup_image_services())
assert _p28h.image_bed.enabled is False and _p28h.image_bed.uploaders == []

# 条目 upload_url 非法 → 告警忽略，其余继续；自定义图床可自由接入
_p28i = _mk_p28({"enable_image_upload": True, "image_upload_services": [
    {"__template_key": "image_bed", "enabled": True,
     "name": "坏的", "upload_url": "bad-url"},
    {"__template_key": "builtin_http", "enabled": True,
     "name": "缺 base_url 的内置", "host": "0.0.0.0", "port": 8766},
    {"__template_key": "image_bed", "enabled": True,
     "name": "我的NAS", "upload_url": "http://nas.lan:7791/api/v1/upload",
     "token": "abc", "response": "json"},
    {"__template_key": "image_bed", "enabled": True,
     "name": "img402", "upload_url": "https://img402.dev/api/free",
     "file_field": "image", "response": "json"},
    {"__template_key": "image_bed", "enabled": True,
     "name": "自建兰空", "upload_url": "http://lan.lan:8080/api/v1/upload",
     "response": "json", "headers": "Accept: application/json",
     "form_fields": "album: public"},
]})
asyncio.run(_p28i._setup_image_services())
assert [u.display_name for u in _p28i.image_bed.uploaders] == \
    ["我的NAS", "img402", "自建兰空"], \
    "非法条目应被忽略且不影响其他条目；任意地址均可自由接入"
assert _p28i.image_bed.uploaders[0].token == "abc"
assert _p28i.image_bed.uploaders[1].file_field == "image", \
    "file_field 应按条目配置传递（img402 这类字段名非 file 的图床）"
assert _p28i.image_bed.uploaders[2].headers == {"Accept": "application/json"}, \
    "headers 应按条目配置解析并传递（自定义图床按需附加请求头）"
assert _p28i.image_bed.uploaders[2].form_fields == {"album": "public"}, \
    "form_fields 应按条目配置解析并传递"
assert _IB28().file_field == "file", "file_field 默认应为 file"
assert "text" in _KIND28 and "json" in _KIND28

# __template_key 缺失时按字段特征兜底识别：base_url → 内置条目，upload_url → 图床
_p28j = _mk_p28({"enable_image_upload": True, "image_upload_services": [
    {"enabled": True, "host": "0.0.0.0", "port": 8765,
     "base_url": "http://lan.lan:8765"},
    {"enabled": True, "upload_url": "https://catbox.moe/user/api.php",
     "response": "text"},
]})
asyncio.run(_p28j._setup_image_services())
assert len(_p28j.image_bed.uploaders) == 2, _p28j.image_bed.service_names
assert isinstance(_p28j.image_bed.uploaders[0], _BIH28) and \
    isinstance(_p28j.image_bed.uploaders[1], _IB28), \
    "无 __template_key 时应按字段特征区分内置条目与图床条目"
# status_text：排障日志需一眼看出两类兜底各自的状态
assert "内置服务=开" in _p28j.image_bed.status_text and \
    "图床=开" in _p28j.image_bed.status_text, _p28j.image_bed.status_text
_p28k = _mk_p28({"enable_image_upload": True, "image_upload_services": []})
asyncio.run(_p28k._setup_image_services())
assert _p28k.image_bed.status_text == "内置服务=关(空)；图床=关(空)", \
    _p28k.image_bed.status_text
# (h) multipart 报文构造：文件字段名 / catbox 兼容 / 额外表单字段 / token
class _FormCap:
    """捕获 FormData.add_field 调用与顺序的桩（离线不联网）。"""
    def __init__(self):
        self.fields = []
    def add_field(self, key, value, *a, **kw):
        self.fields.append((key, value))
class _RespCap:
    def __init__(self, status, text):
        self.status = status
        self._text = text
    async def text(self):
        return self._text
class _PostCap:
    def __init__(self, resp):
        self._resp = resp
    async def __aenter__(self):
        return self._resp
    async def __aexit__(self, *a):
        return False
class _SessCap:
    def __init__(self):
        self.post_args = None
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    def post(self, url, data=None, headers=None):
        self.post_args = (url, data, headers)
        return _PostCap(_RespCap(200, "https://img.example/x.png"))

# 离线环境无 aiohttp，按 _upload 的真实用法建最小桩模块
_ai28 = types.ModuleType("aiohttp")
sys.modules["aiohttp"] = _ai28

async def _cap28(up):
    """用桩会话跑一次真实上传路径，返回 (请求 URL, 表单桩, 请求头)。"""
    _sess = _SessCap()
    sys.modules["aiohttp"].ClientSession = lambda timeout=None: _sess
    sys.modules["aiohttp"].ClientTimeout = lambda total=None: total
    sys.modules["aiohttp"].FormData = _FormCap
    _url, _err = await up.upload(b"pngbytes")
    assert _url == "https://img.example/x.png", f"桩上传应成功: {_err}"
    _u, _data, _hdrs = _sess.post_args
    assert _u == up.upload_url
    assert isinstance(_data, _FormCap)
    return _data, _hdrs

# 普通图床：文件字段为 file，不附带 catbox 专有字段，无 token 不发请求头
_data, _hdrs = asyncio.run(_cap28(_IB28("https://x/u", file_field="file")))
assert _data.fields[0] == ("file", b"pngbytes"), _data.fields
assert "reqtype" not in [k for k, _ in _data.fields], "非 catbox 不得附带 reqtype"
assert _hdrs is None, "无 token / 无 headers 时不应发送请求头"

# 自定义文件字段名（img402）
_data, _ = asyncio.run(_cap28(_IB28("https://img402.dev/api/free", file_field="image")))
assert _data.fields[0] == ("image", b"pngbytes"), _data.fields

# catbox：强制 fileToUpload + reqtype=fileupload
_data, _ = asyncio.run(_cap28(_IB28("https://catbox.moe/user/api.php")))
assert _data.fields[0] == ("fileToUpload", b"pngbytes"), _data.fields
assert ("reqtype", "fileupload") in _data.fields, _data.fields

# litterbox：catbox 兼容 + form_fields 的 time=72h 必须一并发送
_data, _ = asyncio.run(_cap28(_IB28(
    "https://litterbox.catbox.moe/resources/internals/api.php",
    file_field="fileToUpload", form_fields="time: 72h")))
assert _data.fields[0] == ("fileToUpload", b"pngbytes"), _data.fields
assert ("reqtype", "fileupload") in _data.fields, _data.fields
assert ("time", "72h") in _data.fields, \
    f"litterbox 必须附带 time=72h（漏填服务端 500），实际 {_data.fields}"

# token：同时写入 Authorization 请求头与 token 表单字段
_data, _hdrs = asyncio.run(_cap28(_IB28("https://x/u", token="tk-1")))
assert _hdrs["Authorization"] == "Bearer tk-1", _hdrs
assert ("token", "tk-1") in _data.fields, _data.fields

# headers 与 token 可共存，且互不覆盖
_data, _hdrs = asyncio.run(_cap28(
    _IB28("https://x/u", token="tk-1", headers="Accept: application/json")))
assert _hdrs == {"Accept": "application/json", "Authorization": "Bearer tk-1"}, \
    _hdrs

# form_fields 不得覆盖文件字段本身（文件字段先添加）
_data, _ = asyncio.run(_cap28(_IB28("https://x/u", form_fields="file: override")))
assert _data.fields[0] == ("file", b"pngbytes"), \
    f"文件字段必须最先添加且不被 form_fields 覆盖，实际 {_data.fields[0]}"

# HTTP >= 400 视为上传失败（url 为 None，原因含状态码）
class _SessCap403(_SessCap):
    def post(self, url, data=None, headers=None):
        self.post_args = (url, data, None)
        return _PostCap(_RespCap(403, "Forbidden"))
async def _cap403(up):
    _sess = _SessCap403()
    sys.modules["aiohttp"].ClientSession = lambda timeout=None: _sess
    sys.modules["aiohttp"].ClientTimeout = lambda total=None: total
    sys.modules["aiohttp"].FormData = _FormCap
    return await up.upload(b"x")
assert asyncio.run(_cap403(_IB28("https://x/u")))[0] is None
# text 模式收到非链接响应 / json 模式取不到链接：均应判为失败
class _SessCapText(_SessCap):
    def __init__(self, text):
        super().__init__(); self._t = text
    def post(self, url, data=None, headers=None):
        self.post_args = (url, data, None)
        return _PostCap(_RespCap(200, self._t))
async def _cap_text(up, text):
    _sess = _SessCapText(text)
    sys.modules["aiohttp"].ClientSession = lambda timeout=None: _sess
    sys.modules["aiohttp"].ClientTimeout = lambda total=None: total
    sys.modules["aiohttp"].FormData = _FormCap
    return await up.upload(b"x")
assert asyncio.run(_cap_text(_IB28("https://x/u"), "不是链接"))[0] is None
assert asyncio.run(_cap_text(_IB28("https://x/u", response="json"),
                            '{"status": false}'))[0] is None
# imglink 真实响应形态：数组包一层，取 images[0].url
assert asyncio.run(_cap_text(_IB28("https://imglink.cc/api/upload", response="json"),
                            '{"images": [{"id": "a", '
                            '"url": "https://imglink.cc/cdn/a.png"}], '
                            '"album": null}'))[0] == "https://imglink.cc/cdn/a.png"

print("OK  MIME 猜测 / 登记与缓存 / 字节获取 / resolve 优先级 / 图床自由接入 / multipart 报文 / 根级配置守卫")

print("\n=== 29. 游戏内图片转发到外部（forward_image_from_mc） ===")
from astrbot_plugin_minecraft_queqiao.services.message_bridge import (
    extract_image_refs as _eir29,
    strip_image_refs as _sir29,
    file_uri_to_local_path as _furi29,
    download_image_bytes as _dib29,
    MessageBridge as _MB29,
)
from astrbot_plugin_minecraft_queqiao.core.constants import (
    MAX_IMAGE_DOWNLOAD_BYTES as _MAX29,
)

# (a) 引用提取：CICode / 裸图片链接 / 去重 / 非图片链接忽略
_text_a29 = (
    "看这张 [[CICode,url=https://gchat.qpic.cn/a/b.png,name=图片]] 和 "
    "https://media.forgecdn.net/avatars/thumbnails/796/977/64/64/638157647329196977.png "
    "以及普通网页 https://example.com/page"
)
assert _eir29(_text_a29) == [
    "https://gchat.qpic.cn/a/b.png",
    "https://media.forgecdn.net/avatars/thumbnails/796/977/64/64/638157647329196977.png",
], _eir29(_text_a29)

# CICode 的 file://（用户线上用例：Windows 路径，反斜杠保留）
_file_cic29 = r"[[CICode,url=file:///D:\profile\Downloads\9b4ccc48-0e94-44ad-abf3-d3ca0487abe7.jpg]]"
assert _eir29(_file_cic29) == [
    r"file:///D:\profile\Downloads\9b4ccc48-0e94-44ad-abf3-d3ca0487abe7.jpg",
], _eir29(_file_cic29)

# 去重：同一链接出现两次只取一次
assert _eir29("[[CICode,url=https://a/b.png]] 再看 https://a/b.png") == \
    ["https://a/b.png"]

# 非图片链接（无图片扩展名）不按图片处理
assert _eir29("https://example.com/page") == []
assert _eir29("https://example.com/x.htm") == []

# (b) 剥离：已转图引用移除、失败引用保留原文、普通网页链接不动
_t_b29 = "看图 [[CICode,url=https://a/b.png]] 和 https://c/d.jpg 完"
assert _sir29(_t_b29, keep=set()) == "看图 和 完", repr(_sir29(_t_b29, keep=set()))
assert _sir29(_t_b29, keep={"https://a/b.png"}) == \
    "看图 [[CICode,url=https://a/b.png]] 和 完", \
    repr(_sir29(_t_b29, keep={"https://a/b.png"}))
assert _sir29("看 https://example.com/page 完", keep=set()) == \
    "看 https://example.com/page 完", "普通网页链接不得被剥离"

# (c) file:// 本地路径解析
assert _furi29(r"file:///D:\profile\Downloads\x.jpg") == \
    r"D:\profile\Downloads\x.jpg"
assert _furi29("file:///home/user/x.png") == "/home/user/x.png"
assert _furi29("file://localhost/C:/x.png") == "C:/x.png"
assert _furi29("https://a/b.png") is None

# (d) 下载字节：file:// 真实文件 / 缺失 / 非 http/file / 超限
_fd29, _name29 = tempfile.mkstemp(suffix=".png")
os.close(_fd29)
with open(_name29, "wb") as _f:
    _f.write(b"\x89PNG\r\n\x1a\nfake")
_uri29 = pathlib.Path(_name29).as_uri()
assert asyncio.run(_dib29(_uri29)) == b"\x89PNG\r\n\x1a\nfake"
assert asyncio.run(_dib29(_uri29, max_bytes=4)) is None, "超过 max_bytes 应返回 None"
os.unlink(_name29)
assert asyncio.run(_dib29(_uri29)) is None, "文件已删除应返回 None"
assert asyncio.run(_dib29("ftp://x/y.png")) is None
assert _MAX29 >= 1024 * 1024, "下载上限常量应 ≥1MB"

# http(s) 经 aiohttp 桩下载（离线不联网）
_HTTP29 = {}
class _Read29:
    def __init__(self, data): self._data = data
    async def read(self, n=-1):
        return self._data if n < 0 else self._data[:n]
class _Resp29:
    def __init__(self, status, data): self.status = status; self.content = _Read29(data)
class _Get29:
    def __init__(self, resp): self._resp = resp
    async def __aenter__(self): return self._resp
    async def __aexit__(self, *a): return False
class _Sess29:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    def get(self, url):
        status, data = _HTTP29.get(url, (404, b""))
        return _Get29(_Resp29(status, data))
_ai29 = types.ModuleType("aiohttp")
_ai29.ClientSession = lambda timeout=None: _Sess29()
_ai29.ClientTimeout = lambda total=None: total
sys.modules["aiohttp"] = _ai29
_HTTP29["https://img.example/ok.png"] = (200, b"\x89PNG\r\n\x1a\nok")
assert asyncio.run(_dib29("https://img.example/ok.png")) == b"\x89PNG\r\n\x1a\nok"
assert asyncio.run(_dib29("https://img.example/missing.png")) is None, "404 应返回 None"
assert asyncio.run(_dib29("https://img.example/ok.png", max_bytes=3)) is None

# (e) 配置解析：默认关闭、可开启、字符串 true 兼容
assert ServerConfig.from_dict({}).forward_image_from_mc is False
assert ServerConfig.from_dict(
    {"message": {"forward_image_from_mc": True}}
).forward_image_from_mc is True
assert ServerConfig.from_dict(
    {"message": {"forward_image_from_mc": "true"}}
).forward_image_from_mc is True

# (f) 端到端：游戏内 CICode 图片 → 文本剥离 + 图片组件发送
_sent29 = []
class _Ctx29:
    async def send_message(self, umo, chain):
        _sent29.append((umo, list(chain.chain))); return True

_cfg29 = ServerConfig.from_dict({"server": {"server_name": "S29"},
    "message": {"target_sessions": ["umo:GroupMessage:29"],
                "forward_image_from_mc": True,
                "forward_chat_format": "{player}: {message}"}})
_mb29 = _MB29(_Ctx29())
_mb29.register_server(_cfg29)

_fd29b, _name29b = tempfile.mkstemp(suffix=".png")
os.close(_fd29b)
with open(_name29b, "wb") as _f:
    _f.write(b"\x89PNG\r\n\x1a\nimg")
_uri29b = pathlib.Path(_name29b).as_uri()

asyncio.run(_mb29.forward_event("S29", _cfg29, QueQiaoEvent.from_dict({
    "event_name": "PlayerChatEvent",
    "message": "看图 [[CICode,url=" + _uri29b + "]]",
    "player": {"nickname": "Steve"}})))
os.unlink(_name29b)
assert len(_sent29) == 1 and _sent29[0][0] == "umo:GroupMessage:29"
_ch29 = _sent29[0][1]
assert _ch29[0].text == "Steve: 看图", _ch29[0].text
assert len(_ch29) == 2 and _ch29[1].file.startswith("base64://"), \
    "应有文本 + 图片两个组件，图片为 base64 形态"

# 下载失败（file:// 不存在）→ 保留原始 CICode 文本、无图片组件
_sent29.clear()
asyncio.run(_mb29.forward_event("S29", _cfg29, QueQiaoEvent.from_dict({
    "event_name": "PlayerChatEvent",
    "message": "[[CICode,url=file:///nonexistent/zz.png]]",
    "player": {"nickname": "Steve"}})))
assert len(_sent29) == 1 and len(_sent29[0][1]) == 1, "下载失败不应有图片组件"
assert "[[CICode,url=file:///nonexistent/zz.png]]" in _sent29[0][1][0].text, \
    "下载失败应保留原始 CICode 文本: " + _sent29[0][1][0].text

# 关闭开关 → 纯文本原样转发、无图片组件
_cfg29off = ServerConfig.from_dict({"server": {"server_name": "S29"},
    "message": {"target_sessions": ["umo:GroupMessage:29"],
                "forward_image_from_mc": False,
                "forward_chat_format": "{player}: {message}"}})
_mb29b = _MB29(_Ctx29())
_mb29b.register_server(_cfg29off)
_sent29.clear()
asyncio.run(_mb29b.forward_event("S29", _cfg29off, QueQiaoEvent.from_dict({
    "event_name": "PlayerChatEvent",
    "message": "看图 [[CICode,url=https://img.example/ok.png]]",
    "player": {"nickname": "Steve"}})))
assert len(_sent29) == 1 and len(_sent29[0][1]) == 1, "关闭开关不应有图片组件"
assert "[[CICode" in _sent29[0][1][0].text, "关闭开关应原样保留文本"

# (g) schema 守卫：message 分组内、默认关闭、hint 提到 CICode
_sh29 = json.loads(pathlib.Path(__file__).with_name("_conf_schema.json")
                   .read_text(encoding="utf-8"))
_mi29 = _sh29["mc_servers"]["templates"]["server"]["items"]["message"]["items"]
assert "forward_image_from_mc" in _mi29
assert _mi29["forward_image_from_mc"]["default"] is False
assert "CICode" in _mi29["forward_image_from_mc"]["hint"]
_mk29 = list(_mi29.keys())
assert _mk29.index("forward_image_from_mc") == _mk29.index("chatimage_name") + 1, \
    "forward_image_from_mc 必须紧跟 chatimage_name，实际顺序: " + str(_mk29)
print("OK  引用提取 / 剥离与保留 / file 路径解析 / 下载字节 / 配置解析 / 端到端 / schema 同步")

print("\n=== 30. 在线玩家三层兜底（RCON list → SLP sample → 人数） ===")
from astrbot_plugin_minecraft_queqiao.core.models import (
    PlayerListResult as _PLR30, ServerStatus as _SS30,
)
from astrbot_plugin_minecraft_queqiao.core.queqiao_client import QueQiaoTimeout as _QT30
from astrbot_plugin_minecraft_queqiao.core.server_manager import ServerInstance as _SI30
from astrbot_plugin_minecraft_queqiao.services.renderer import InfoRenderer as _IR30
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _S30

# (a) ServerStatus 解析 players.sample：剥离 § 格式码、跳过空名/畸形项
_st30 = _SS30.from_dict({
    "server_type": "Fabric", "server_version": "1.20.1",
    "server_list_ping": {"players": {"online": 2, "max": 20, "sample": [
        {"name": "XTxiaotong", "id": "cd62632e-bd77-33d1-9516-206063e6d244"},
        {"name": "§6Steve", "id": "00000000-0000-0000-0000-000000000000"},
        {"name": "", "id": "x"},      # 空名跳过
        "not-a-dict",                  # 畸形项跳过
        {"id": "y"},                   # 无名跳过
    ]}}})
assert _st30.online_player_names == ["XTxiaotong", "Steve"], _st30.online_player_names
assert _st30.player_sample[0] == \
    ("XTxiaotong", "cd62632e-bd77-33d1-9516-206063e6d244"), _st30.player_sample[0]
# 真实在线查询形态：sample 带真实玩家名+UUID（对应用户服 8.162.6.112:59209）
# 无 sample 字段 / 无 players / 空对象 均不得抛异常
assert _SS30.from_dict({"players": {"online": 0, "max": 20}}).online_player_names == []
assert _SS30.from_dict({}).online_player_names == []
assert _SS30.from_dict("not-a-dict").online_player_names == []

# (b) 渲染：四种 source 分支
# rcon 完整名单（未带 channel 不标注，兼容旧调用归一化）
assert _IR30.format_player_list("S", _PLR30(names=["A", "B"], source="rcon"), "生存服") \
    == "👥 服务器 生存服 在线 2 人：\nA、B"
# rcon 按 rcon_channel 细分标注本次实际取数通道
assert _IR30.format_player_list("S", _PLR30(
    names=["A", "B"], source="rcon", rcon_channel="queqiao"), "生存服") \
    == "👥 服务器 生存服 在线 2 人（鹊桥RCON）：\nA、B"
assert _IR30.format_player_list("S", _PLR30(
    names=["A", "B"], source="rcon", rcon_channel="direct")) \
    == "👥 服务器 S 在线 2 人（直连RCON）：\nA、B"
# rcon 未带 channel（旧调用归一化）不标注，保持无括注
assert _IR30.format_player_list("S", _PLR30(
    names=["A", "B"], source="rcon", rcon_channel="")) \
    == "👥 服务器 S 在线 2 人：\nA、B"
# slp 来源标「在线查询」（不再带「可能不全」）
_slp_out = _IR30.format_player_list(
    "S", _PLR30(names=["A"], online=1, max=20, source="slp"))
assert "在线 1 人" in _slp_out and "在线查询" in _slp_out \
    and "可能不全" not in _slp_out and "A" in _slp_out, _slp_out
# count 来源：只有人数，提示未开 RCON 且在线查询未返回名
_cnt_out = _IR30.format_player_list(
    "S", _PLR30(online=3, max=20, source="count"), "生存服")
assert "在线 3/20 人" in _cnt_out and "未返回玩家名" in _cnt_out, _cnt_out
# count 且 0 人在线 → 视同没人在线（服务器无人时往往连 sample 键都不返回）
assert _IR30.format_player_list("S", _PLR30(online=0, max=20, source="count")) \
    == "👥 服务器 S 当前没有玩家在线"
# none 来源：失败提示
assert "无法获取" in _IR30.format_player_list("S", _PLR30(source="none"))
# rcon 但空名单（确实没人在线）
assert _IR30.format_player_list("S", _PLR30(names=[], source="rcon")) \
    == "👥 服务器 S 当前没有玩家在线"
# 向后兼容：直接传 list[str] / None（第 21 组契约不破坏）
assert _IR30.format_player_list("S", ["Steve"]) == "👥 服务器 S 在线 1 人：\nSteve"
assert "无法获取" in _IR30.format_player_list("S", None)

# (c) fetch_player_list 三层兜底顺序
class _Cli30:
    """鹊桥客户端桩：可控 connected / get_status / send_rcon_command。"""
    def __init__(self, connected=True, status=None,
                 rcon_out=None, rcon_timeout=False):
        self.connected = connected
        self._status = status
        self._rcon_out = rcon_out
        self._rcon_timeout = rcon_timeout
        self.rcon_calls = 0
    async def get_status(self): return self._status
    async def send_rcon_command(self, cmd):
        self.rcon_calls += 1
        if self._rcon_timeout:
            raise _QT30("send_rcon_command", 10)
        return self._rcon_out
class _Rcon30:
    def __init__(self, enabled=False, out=None):
        self.enabled = enabled; self._out = out; self.calls = []
    async def execute(self, cmd):
        self.calls.append(cmd); return self._out

def _mk_inst30(client, rcon=None):
    _i = _SI30(_S30.from_dict({"server": {"server_name": "S30"}}))
    _i.client = client; _i.rcon = rcon or _Rcon30()
    return _i

# c1) RCON list 成功 → source=rcon，不再查 SLP（进入面板/手动刷新 force 探测场景）
_i1 = _mk_inst30(_Cli30(connected=True,
    rcon_out="There are 2 of a max of 20 players online: A, B"))
_r1 = asyncio.run(_i1.fetch_player_list(force_rcon=True))
assert _r1.source == "rcon" and _r1.rcon_channel == "queqiao" \
    and _r1.names == ["A", "B"], (_r1.source, _r1.rcon_channel, _r1.names)
assert _i1.client.rcon_calls == 1

# c2) 鹊桥未开 RCON（send_rcon 返回 None）+ 直连 RCON 未配 → 退 SLP sample（免 RCON）
#     对应用户服场景：不开 RCON 也能拿到玩家名
_i2 = _mk_inst30(_Cli30(connected=True, rcon_out=None,
    status={"server_list_ping": {"players": {"online": 1, "max": 20, "sample": [
        {"name": "XTxiaotong", "id": "cd62632e-bd77-33d1-9516-206063e6d244"}]}}}))
_r2 = asyncio.run(_i2.fetch_player_list())
assert _r2.source == "slp" and _r2.names == ["XTxiaotong"], (_r2.source, _r2.names)
assert _r2.online == 1 and _r2.max == 20

# c3) RCON 失败 + SLP sample 为空但有人数 → source=count
_i3 = _mk_inst30(_Cli30(connected=True, rcon_out=None,
    status={"server_list_ping": {"players": {"online": 5, "max": 20}}}))
_r3 = asyncio.run(_i3.fetch_player_list())
assert _r3.source == "count" and _r3.names == [] and _r3.online == 5, \
    (_r3.source, _r3.online)

# c4) 全失败（鹊桥未连、无 RCON）→ source=none
_i4 = _mk_inst30(_Cli30(connected=False, status=None))
_r4 = asyncio.run(_i4.fetch_player_list())
assert _r4.source == "none" and _r4.names == [], (_r4.source, _r4.names)

# c5) 鹊桥执行 list 超时（结果未知）→ 不走直连 RCON 重发（避免执行两遍），
#     而是降级到 SLP sample（属不同查询，不构成重发）
_rto = _Rcon30(enabled=True, out="rcon-out")
_i5 = _mk_inst30(_Cli30(connected=True, rcon_timeout=True,
    status={"server_list_ping": {"players": {"online": 1, "max": 20, "sample": [
        {"name": "Steve", "id": "u"}]}}}), _rto)
_r5 = asyncio.run(_i5.fetch_player_list())
assert _r5.source == "slp" and _r5.names == ["Steve"], (_r5.source, _r5.names)
assert _rto.calls == [], "RCON list 超时后不得走直连 RCON 重发（会执行两遍）"

# c6) 直连 RCON 兜底仍生效：鹊桥未连但配了直连 RCON → source=rcon
_i6 = _mk_inst30(_Cli30(connected=False),
    _Rcon30(enabled=True,
            out="There are 1 of a max of 20 players online: Steve"))
_r6 = asyncio.run(_i6.fetch_player_list())
assert _r6.source == "rcon" and _r6.rcon_channel == "direct" \
    and _r6.names == ["Steve"], (_r6.source, _r6.rcon_channel, _r6.names)
# c7) 鹊桥 RCON 已确认不可用（False）后不再重复探测：
#     进入面板/手动刷新（force）探测确认不可用后，普通请求降级走 SLP
#     sample，不再向未开启 RCON 的鹊桥端发 send_rcon_command
_i7 = _mk_inst30(_Cli30(connected=True, rcon_out=None,
    status={"server_list_ping": {"players": {"online": 1, "max": 20, "sample": [
        {"name": "Steve", "id": "u"}]}}}))
_r7a = asyncio.run(_i7.fetch_player_list(force_rcon=True))
assert _i7.queqiao_rcon_ok is False and _i7.client.rcon_calls == 1
_r7b = asyncio.run(_i7.fetch_player_list())
assert _i7.client.rcon_calls == 1, "已确认鹊桥 RCON 不可用后不得重复探测"
assert _r7b.source == "slp" and _r7b.names == ["Steve"]
# 未确认（None，如重连后）状态下，普通请求不主动探测（探测只由 force 触发）
_i7d = _mk_inst30(_Cli30(connected=True, rcon_out=None,
    status={"server_list_ping": {"players": {"online": 1, "max": 20, "sample": [
        {"name": "Steve", "id": "u"}]}}}))
_r7d = asyncio.run(_i7d.fetch_player_list())
assert _i7d.client.rcon_calls == 0, "未确认状态下的普通请求不主动探测 RCON"
assert _i7d.queqiao_rcon_ok is None and _r7d.source == "slp"
# 重连（None）后再次进入面板/手动刷新（force）→ 恢复探测
_i7.queqiao_rcon_ok = None
_i7.client._rcon_out = "There are 1 of a max of 20 players online: Steve"
_r7c = asyncio.run(_i7.fetch_player_list(force_rcon=True))
assert _i7.client.rcon_calls == 2 and _r7c.source == "rcon" \
    and _r7c.rcon_channel == "queqiao", (_i7.client.rcon_calls, _r7c.source)
# c8) 手动刷新（force_rcon=True）：每次都会重置「不可用」结论重新探测一次，
#     确认不可用后普通取数保持静默，直到下一次 force（再次进入面板/手动刷新）
_i8 = _mk_inst30(_Cli30(connected=True, rcon_out=None,
    status={"server_list_ping": {"players": {"online": 0, "max": 20}}}))
asyncio.run(_i8.fetch_player_list(force_rcon=True))
assert _i8.queqiao_rcon_ok is False and _i8.client.rcon_calls == 1
asyncio.run(_i8.fetch_player_list(force_rcon=True))
assert _i8.client.rcon_calls == 2, "再次进入面板/手动刷新应重新探测一次鹊桥 RCON"
assert _i8.queqiao_rcon_ok is False
asyncio.run(_i8.fetch_player_list())
assert _i8.client.rcon_calls == 2, "确认不可用后普通取数不得再探测"
# force 但鹊桥未连接：不重置（无意义），直接走其它通道
_i8b = _mk_inst30(_Cli30(connected=False))
_i8b.queqiao_rcon_ok = False
asyncio.run(_i8b.fetch_player_list(force_rcon=True))
assert _i8b.queqiao_rcon_ok is False
print("OK  sample 解析(剥离§/跳畸形) / 渲染含RCON通道细分 / 三层兜底顺序 / 超时不重发降级 SLP / 鹊桥RCON不可用不重复探测 / 每次force重新探测且普通取数静默")

print("\n全部离线逻辑校验通过 ✅（含在线玩家三层兜底）")

print("\n=== 31. 多服务器：数字编号指定目标与单服省略 ===")
from astrbot_plugin_minecraft_queqiao.handlers.commands import CommandHandler as _CH31
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _SC31
import astrbot_plugin_minecraft_queqiao.handlers.commands as _cmd_mod31
import astrbot_plugin_minecraft_queqiao.core.constants as _c31


class _Inst31:
    """服务器实例桩：含 _resolve_target/_ambiguous_hint 关心的字段。"""
    def __init__(self, sid, name=None, connected=True):
        self.server_name = sid
        self.connected = connected
        cfg = {"server": {"server_name": sid}}
        if name:
            cfg["server"]["display_name"] = name
        self.config = _SC31.from_dict(cfg)


class _SM31:
    """ServerManager 桩：all 返回配置顺序（与 mc servers 一致）。"""
    def __init__(self, insts):
        self._insts = list(insts)
    def get(self, sid):
        for i in self._insts:
            if i.server_name == sid:
                return i
        return None
    def all(self):
        return list(self._insts)


class _Ev31:
    """事件桩：仅含 unified_msg_origin。"""
    def __init__(self, umo="umo:GroupMessage:1"):
        self.unified_msg_origin = umo


# (a) 死代码已彻底移除：旧的「回复编号选择」pending 机制从未真正接线
assert not hasattr(_cmd_mod31, "PendingAction"), "PendingAction 死代码应移除"
assert not hasattr(_c31, "PENDING_ACTION_TTL"), "常量 PENDING_ACTION_TTL 应移除"
for _dead in ("has_pending_action", "set_pending", "resolve_selection",
              "build_selection_action", "_make_selection_hint", "PendingAction"):
    assert not hasattr(_CH31, _dead), f"死方法/类 {_dead} 应移除"

# (b) _split_optional_target：仅多服时拆首 token 数字编号，单服一律不拆
_h1 = _CH31(_SM31([_Inst31("s1")]), None, None)            # 单服
_h2 = _CH31(_SM31([_Inst31("survival", "生存服"),
                   _Inst31("creative", "创造服")]), None, None)  # 多服
# 单服不拆：首 token 是数字也当内容（避免 mc say 123 被误当编号）
assert _h1._split_optional_target("1 say hi") == (None, "1 say hi")
assert _h1._split_optional_target("say hi") == (None, "say hi")
# 多服首 token 有效数字 → 拆出编号字符串 + 剩余
assert _h2._split_optional_target("1 time set day") == ("1", "time set day")
assert _h2._split_optional_target("2") == ("2", ""), "仅编号无后续 → rest 空"
# 多服首 token 非数字 → 不拆
assert _h2._split_optional_target("time set day") == (None, "time set day")
# 多服首 token 数字超出范围 → 不拆（交给自动定位，由提示告知可用范围）
assert _h2._split_optional_target("3 time set day") == (None, "3 time set day")
# 空文本
assert _h2._split_optional_target("") == (None, "")
assert _h2._split_optional_target("   ") == (None, "")

# (c) 单服：省略编号自动命中那台（核心需求：只有一个服务器时能省略）
_srv, _hint = _h1._resolve_target(_Ev31(), "")
assert _srv is not None and _srv.server_name == "s1" and _hint is None, (_srv, _hint)
# 单服写编号 1 也行（1 = 那台）
_srv, _hint = _h1._resolve_target(_Ev31(), "1")
assert _srv.server_name == "s1" and _hint is None
# 单服写超出范围的编号（2）→ 提示超出范围
_srv, _hint = _h1._resolve_target(_Ev31(), "2")
assert _srv is None and "2" in _hint and "1-1" in _hint, _hint

# (d) 多服：省略编号 → 提示加编号，hint 含 1./2. 编号与显示名
_srv, _hint = _h2._resolve_target(_Ev31(), "")
assert _srv is None
assert "1." in _hint and "生存服" in _hint, _hint
assert "2." in _hint and "创造服" in _hint, _hint
assert "mc cmd 1" in _hint, _hint
# 多服编号 1/2 命中对应那台（核心需求：两台 MC 接一个群能分开下指令）
_srv, _ = _h2._resolve_target(_Ev31(), "1"); assert _srv.server_name == "survival"
_srv, _ = _h2._resolve_target(_Ev31(), "2"); assert _srv.server_name == "creative"
# 多服编号超出范围 → 提示可用范围
_srv, _hint = _h2._resolve_target(_Ev31(), "3")
assert _srv is None and "3" in _hint and "1-2" in _hint, _hint
# 多服非数字 → 提示需为数字
_srv, _hint = _h2._resolve_target(_Ev31(), "x")
assert _srv is None and "数字" in _hint, _hint

# (e) 无服务器：任何情况都提示先配置
_h0 = _CH31(_SM31([]), None, None)
_srv, _hint = _h0._resolve_target(_Ev31(), "")
assert _srv is None and "尚未配置" in _hint, _hint
_srv, _hint = _h0._resolve_target(_Ev31(), "1")
assert _srv is None and "尚未配置" in _hint, "无服时给编号也应提示未配置"

# (f) help 文案已带编号说明
_help = _h2.help_text()
assert "mc status [编号|地址]" in _help, "status 支持编号或地址直连"
assert "mc list [编号|地址]" in _help, "list 支持编号或地址直连"
assert "mc cmd [编号] <指令>" in _help
assert "mc player [编号] <玩家ID>" in _help
assert "数字编号" in _help, "help 应说明多服加编号/单服省略规则"
assert "127.0.0.1:25565" in _help, "help 应示例地址直连语法"
print("OK  数字编号拆分(仅多服) / 单服省略自动命中 / 多服提示含编号列表 / "
      "死代码已移除 / help 已同步")

print("\n=== 32. 重复 server_name 告警发送到目标会话 ===")
from astrbot_plugin_minecraft_queqiao.main import MinecraftQueQiaoPlugin as _P32
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _SC32
import asyncio as _asyncio32


class _Ctx32:
    """context 桩：记录 send_message 调用。"""
    def __init__(self):
        self.sent = []
    async def send_message(self, umo, chain):
        self.sent.append((umo, chain))


class _Self32:
    """插件桩 self：仅含 context。"""
    def __init__(self, ctx):
        self.context = ctx


# (a) 有目标会话：告警发到每个 target_session，文本包含重复的 server_name
_ctx32 = _Ctx32()
_cfg_dup = _SC32.from_dict({
    "server": {"server_name": "survival"},
    "target_sessions": ["aiocqhttp:GroupMessage:111", "telegram:GroupMessage:222"],
})
_asyncio32.run(_P32._notify_duplicate_server(_Self32(_ctx32), _cfg_dup))
assert len(_ctx32.sent) == 2, _ctx32.sent
assert [umo for umo, _ in _ctx32.sent] == [
    "aiocqhttp:GroupMessage:111", "telegram:GroupMessage:222"]
for _, chain in _ctx32.sent:
    _text = chain.chain[0].text
    assert "重复" in _text and "survival" in _text, _text

# (b) 无目标会话：静默不发
_ctx32b = _Ctx32()
_cfg_no_target = _SC32.from_dict({"server": {"server_name": "survival"}})
_asyncio32.run(_P32._notify_duplicate_server(_Self32(_ctx32b), _cfg_no_target))
assert _ctx32b.sent == [], "无 target_sessions 不应发送告警"

# (c) 发送失败（平台不可用）不中断启动
class _CtxFail32:
    async def send_message(self, umo, chain):
        raise RuntimeError("平台不可用")
_fail32 = _Self32(_CtxFail32())
_asyncio32.run(_P32._notify_duplicate_server(_fail32, _cfg_dup))  # 不应抛异常
print("OK  重复告警发到目标会话 / 无会话不发 / 发送失败安全降级")

print("\n=== 33. 服务器列表展示显示名称（handle_servers） ===")
import asyncio as _asyncio33
from astrbot_plugin_minecraft_queqiao.handlers.commands import CommandHandler as _CH33
from astrbot_plugin_minecraft_queqiao.core.server_manager import ServerManager as _SM33
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _SC33

_sm33 = _SM33()
_cfg_s1 = _SC33.from_dict({
    "server": {"server_name": "Server", "display_name": "方可梦"},
})
_cfg_s2 = _SC33.from_dict({
    "server": {"server_name": "Server1", "display_name": "原版服"},
})
_cfg_s3 = _SC33.from_dict({
    "server": {"server_name": "Server3", "display_name": ""},
})
_cfg_s4 = _SC33.from_dict({
    "server": {"server_name": "Server4", "display_name": "Server4"},
})
_inst1 = _sm33.add(_cfg_s1)
_inst2 = _sm33.add(_cfg_s2)
_inst3 = _sm33.add(_cfg_s3)
_inst4 = _sm33.add(_cfg_s4)

_ch33 = _CH33(server_manager=_sm33, binding_service=None, renderer=None)
_res33 = _asyncio33.run(_ch33.handle_servers(None))

assert "- 方可梦 (Server)（正向）：🔴 未连接" in _res33, _res33
assert "- 原版服 (Server1)（正向）：🔴 未连接" in _res33, _res33
assert "- Server3（正向）：🔴 未连接" in _res33, _res33
assert "- Server4（正向）：🔴 未连接" in _res33, _res33
print("OK  有 display_name 显示「显示名称 (server_name)」、无 display_name 或与 server_name 相同时仅显示 server_name")

print("\n=== 34. Web API 控制器与 Metrics 指标系统 ===")
import asyncio as _asyncio34
from astrbot_plugin_minecraft_queqiao.services.metrics import MetricsCollector as _MC34
from astrbot_plugin_minecraft_queqiao.services.web_api import WebApiController as _WAC34
from astrbot_plugin_minecraft_queqiao.core.models import ServerStatus as _SS34, PlayerListResult as _PLR34

# (a) ServerStatus.to_dict 与 PlayerListResult.to_dict 结构校验
_ss34 = _SS34(
    server_type="Paper",
    server_version="1.20.4",
    online_players=5,
    max_players=100,
    description="§aWelcome to Minecraft!",
    cpu_cores=8,
    system_load=1.23,
    memory_total=1024 * 1024 * 1024 * 8,
    memory_used=1024 * 1024 * 1024 * 2,
    memory_percentage=25.0,
    player_sample=[("Steve", "uuid-1"), ("Alex", "uuid-2")],
)
_ss_dict = _ss34.to_dict()
assert _ss_dict["server_type"] == "Paper"
assert _ss_dict["online_players"] == 5
assert _ss_dict["online_player_names"] == ["Steve", "Alex"]
assert len(_ss_dict["player_sample"]) == 2
assert "25.0%" in _ss_dict["memory_usage_text"]

_plr34 = _PLR34(names=["Steve", "Alex"], source="rcon", rcon_channel="queqiao")
_plr_dict = _plr34.to_dict()
assert _plr_dict["names"] == ["Steve", "Alex"]
assert _plr_dict["source"] == "rcon"
assert _plr_dict["rcon_channel"] == "queqiao"
assert _plr_dict["online"] == 2

# (a2) ServerStatus 扩展字段：get_status 完整返回的解析与序列化
# （notes §7.1：jvm_memory / process_load / load_average / SLP 健康 /
#  timestamp / enforcesSecureChat / physical free）
_ss34_full = _SS34.from_dict({
    "timestamp": 1775444822691,
    "server_type": "forge",
    "server_version": "1.21",
    "server_list_ping": {
        "available": True,
        "host": "127.0.0.1", "port": 25565,
        "reason": "ok", "error": None,
        "enforcesSecureChat": True,
        "players": {"online": 0, "max": 20},
    },
    "cpu_information": {
        "cpu_cores": 16, "load_average": -1.0,
        "system_load": 0.0, "process_load": -1.0,
    },
    "memory_information": {
        "physical_memory": {
            "total": 34278875136, "free": 14827216896,
            "used": 19451658240, "percentage": 56.75,
        },
        "jvm_memory": {
            "total": 486539264, "free": 95978912,
            "max": 8573157376, "used": 390560352, "percentage": 4.56,
        },
    },
})
_sd34 = _ss34_full.to_dict()
assert _sd34["timestamp"] == 1775444822691
assert abs(_sd34["timestamp_seconds"] - 1775444822.691) < 1e-6
assert _sd34["slp_available"] is True
assert _sd34["slp_reason"] == "ok"
assert _sd34["slp_error"] == ""
assert _sd34["enforces_secure_chat"] is True
assert _sd34["process_load"] == -1.0, "不可用保留原值，由展示层过滤"
assert _sd34["load_average"] == -1.0
assert _sd34["memory_free"] == 14827216896
_jvm34 = _sd34["jvm_memory"]
assert _jvm34["total"] == 486539264 and _jvm34["max"] == 8573157376
assert "372.5MB / 8176.0MB" in _jvm34["heap_text"], _jvm34["heap_text"]
assert abs(_jvm34["heap_percentage"] - 4.56) < 0.01, _jvm34["heap_percentage"]
# 三段式：已用 / 已申请(committed) / 上限(max)，百分比 used/max
assert (
    "372MB 已用 / 464MB 已申请 / 8176MB 上限 (4.6%)"
    in _jvm34["heap_detail_text"]
), _jvm34["heap_detail_text"]
assert "372.5MB / 464.0MB" in _jvm34["usage_text"], _jvm34["usage_text"]
# 缺省/畸形输入不抛异常，扩展字段保持空值
_ss34_empty = _SS34.from_dict("not-a-dict")
assert _ss34_empty.to_dict()["jvm_memory"]["heap_text"] == "未知"
assert _ss34_empty.to_dict()["jvm_memory"]["heap_detail_text"] == "未知"
# 键存在但值为 null → None（区别于明确 false/0/-1）
assert _SS34.from_dict({"server_list_ping": {"available": None}}).slp_available is None
assert _SS34.from_dict({"server_list_ping": {"available": False}}).slp_available is False
assert _SS34.from_dict({"cpu_information": {"process_load": None}}).process_load is None

# (a3) format_status 渲染 JVM/进程负载（命令 /ai 状态 文本输出）
from astrbot_plugin_minecraft_queqiao.services.renderer import InfoRenderer as _IR34
# 同机部署：注入与鹊桥 MemTotal 一致的宿主机内存 → 物理内存按 MemAvailable 修正
_host_mem34 = {
    "MemTotal": _ss34_full.memory_total,
    "MemAvailable": _ss34_full.memory_total - 2 * 1024 ** 3,
}
_fmt34 = _IR34.format_status("SrvForge", _ss34_full, host_mem=_host_mem34)
assert "JVM 堆：372MB 已用 / 464MB 已申请 / 8176MB 上限 (4.6%)" in _fmt34, _fmt34
assert "进程" not in _fmt34, f"process_load=-1 应被过滤: {_fmt34}"
assert "系统 0.00" in _fmt34, _fmt34
# 修正后物理内存 = 2G used / 31.9G total (6.3%)，空闲 = MemAvailable（30643MB）
assert "内存：2048.0MB / 32690.9MB (6.3%)" in _fmt34, _fmt34
assert "空闲：30643MB" in _fmt34, _fmt34
# 跨机部署（MemTotal 不匹配）：物理内存清零不展示，只保留 JVM
_fmt34_remote = _IR34.format_status(
    "SrvForge", _ss34_full,
    host_mem={"MemTotal": 16 * 1024 ** 3, "MemAvailable": 8 * 1024 ** 3},
)
assert "内存：" not in _fmt34_remote, f"跨机不应展示物理内存: {_fmt34_remote}"
assert "空闲：" not in _fmt34_remote, _fmt34_remote
assert "JVM 堆：372MB 已用 / 464MB 已申请 / 8176MB 上限 (4.6%)" in _fmt34_remote, _fmt34_remote

# (a4) correct_physical_memory 单元断言：同机修正 / 跨机清零 / 无数据不动
from astrbot_plugin_minecraft_queqiao.services import host_mem as _hm34
from astrbot_plugin_minecraft_queqiao.services.host_mem import (
    correct_physical_memory as _cpm34,
)
# 同机：used = MemTotal - MemAvailable（排除 page cache）
_smem34 = _SS34(
    memory_total=8 * 1024 ** 3, memory_used=7 * 1024 ** 3,
    memory_percentage=87.5,
).to_dict()
_cmem34 = _cpm34(
    _smem34, {"MemTotal": 8 * 1024 ** 3, "MemAvailable": 2 * 1024 ** 3}
)
assert _cmem34["memory_used"] == 6 * 1024 ** 3, _cmem34
assert _cmem34["memory_free"] == 2 * 1024 ** 3, _cmem34
assert _cmem34["memory_percentage"] == 75.0, _cmem34
# 跨机：物理内存清零，面板只保留 JVM
_smem34b = _SS34(
    memory_total=64 * 1024 ** 3, memory_used=32 * 1024 ** 3,
    memory_percentage=50.0,
).to_dict()
_cmem34b = _cpm34(
    _smem34b, {"MemTotal": 8 * 1024 ** 3, "MemAvailable": 2 * 1024 ** 3}
)
assert _cmem34b["memory_total"] == 0, _cmem34b
assert _cmem34b["memory_usage_text"] == "未知", _cmem34b
# 无 memory_total（旧版鹊桥/字段缺失）：原样不动
_smem34c = _SS34().to_dict()
assert _cpm34(
    _smem34c, {"MemTotal": 8 * 1024 ** 3, "MemAvailable": 2 * 1024 ** 3}
) is _smem34c
# 读不到 meminfo（非 Windows）：无法判定部署形态 → 清零隐藏
_orig_read34 = _hm34.read_host_meminfo
_hm34.read_host_meminfo = lambda: None  # type: ignore[method-assign]
try:
    _smem34d = _SS34(
        memory_total=8 * 1024 ** 3, memory_used=7 * 1024 ** 3,
        memory_percentage=87.5,
    ).to_dict()
    _cmem34d = _cpm34(_smem34d)
    assert _cmem34d["memory_total"] == 0, _cmem34d
    assert _cmem34d["memory_usage_text"] == "未知", _cmem34d
finally:
    _hm34.read_host_meminfo = _orig_read34

# (b) MetricsCollector 计数与发布订阅
_mc34 = _MC34(max_history=10)
_q34 = _mc34.subscribe()
_item34 = _mc34.record_event("chat", "srv1", "<Steve> hello", {"msg": "hello"})
assert _item34.id == 1
assert _mc34.events_by_type["chat"] == 1
assert not _q34.empty()
_msg34 = _q34.get_nowait()
assert _msg34["summary"] == "<Steve> hello"
_mc34.unsubscribe(_q34)

_mc34.record_relay_to_ast("srv1", 2)
_mc34.record_relay_to_mc("srv1", 3)
_mc34.record_echo_suppressed("srv1", "test echo")
_mc34.record_ai_chat("srv1", "Steve", "how are you?", True)
_mc34.record_command_execution("srv1", "list", "queqiao")
_mc34.record_command_execution("srv1", "tps", "direct")
_mc34.record_command_execution("srv1", "stop", None)
_mc34.record_image_relayed(1)

_stats34 = _mc34.get_stats()
assert _stats34["relayed_to_ast_total"] == 2
assert _stats34["relayed_to_mc_total"] == 3
assert _stats34["echo_suppressed_total"] == 1
assert _stats34["ai_chat_total"] == 1
assert _stats34["ai_chat_success_total"] == 1
assert _stats34["cmd_executed_by_channel"] == {"queqiao": 1, "direct": 1, "failed": 1}
assert _stats34["images_relayed_total"] == 1
assert len(_mc34.get_history(limit=5)) >= 3
# 累计互通事件 = 游戏 → 外部（事件类型计数，如上面 1 条 chat） + 外部 → 游戏（3 条群转发）
assert _stats34["total_events"] == 4, _stats34["total_events"]
# 网页广播（relay）也计入 total_events 与 events_by_type
_mc34.record_event("relay", "srv1", "Web广播: hi", {"message": "hi"})
assert _mc34.events_by_type["relay"] == 1
assert _mc34.get_stats()["total_events"] == 5

# (c) WebApiController 路由注册与接口逻辑
class _MockContext34:
    def __init__(self):
        self.routes = []
    def register_web_api(self, path, handler, methods, desc):
        self.routes.append((path, handler, methods, desc))

from pathlib import Path as _Path34
_mock_ctx34 = _MockContext34()
# configs 的 key 需与 server_manager 中的实例 server_name 对齐，get_servers 才能查到实例
_configs34 = {
    "Server": _cfg_s1,
    "Server1": _cfg_s2,
}
# 持久化终端日志存储（临时目录），供仪表盘跨会话恢复历史
from astrbot_plugin_minecraft_queqiao.services.terminal_log import TerminalLogStore as _TLS34
_tls34 = _TLS34(_Path34("/tmp/queqiao_test_terminal"))
_tls34.load()
_wac34 = _WAC34(
    context=_mock_ctx34,
    server_manager=_sm33,
    binding_service=BindingService(_Path34("/tmp")),
    image_bed=None,
    metrics=_mc34,
    configs=_configs34,
    terminal_logs=_tls34,
)
_wac34.register_routes()
assert len(_mock_ctx34.routes) == 19, f"注册路由数不符: {len(_mock_ctx34.routes)}"
_route_paths = [r[0] for r in _mock_ctx34.routes]
assert "/astrbot_plugin_minecraft_queqiao/servers" in _route_paths
assert "/astrbot_plugin_minecraft_queqiao/stats" in _route_paths
assert "/astrbot_plugin_minecraft_queqiao/server/<server_name>/status" in _route_paths
assert "/astrbot_plugin_minecraft_queqiao/server/<server_name>/players" in _route_paths
assert "/astrbot_plugin_minecraft_queqiao/server/<server_name>/command" in _route_paths
assert "/astrbot_plugin_minecraft_queqiao/server/<server_name>/broadcast" in _route_paths
assert "/astrbot_plugin_minecraft_queqiao/terminal_logs" in _route_paths
assert "/astrbot_plugin_minecraft_queqiao/terminal_logs/clear" in _route_paths

# 测试 get_servers 与 get_stats 响应格式
_res_servers = _asyncio34.run(_wac34.get_servers())
assert "servers" in _res_servers["data"]
assert len(_res_servers["data"]["servers"]) == 2
assert _res_servers["data"]["servers"][0]["server_name"] == "Server"
# 未连接鹊桥且未连直连 RCON 时，rcon_channels 应为空（前端据此显示「未连接 RCON」并折叠控制台）
assert _res_servers["data"]["servers"][0]["rcon_channels"] == []
assert _res_servers["data"]["servers"][0]["rcon_connected"] is False
assert _res_servers["data"]["servers"][0]["connected"] is False

# (e) rcon_channels 语义：鹊桥 RCON 需真实执行确认（仅 WS 连接不算），直连 RCON 连接 → 追加 direct
_mock_instance = _sm33.get("Server")
assert _mock_instance is not None

# ① 仅模拟 WS 连接成功、鹊桥 RCON 未确认：rcon_channels 不应含 queqiao
_mock_instance.client._connected = True
_mock_instance.queqiao_rcon_ok = None
_res_servers2 = _asyncio34.run(_wac34.get_servers())
_server_srv1 = next(
    s for s in _res_servers2["data"]["servers"] if s["server_name"] == "Server"
)
# fetch_player_list 的 list 探测失败后 queqiao_rcon_ok 变为 False，通道不应出现
assert "queqiao" not in _server_srv1["rcon_channels"]

# ② 鹊桥 send_rcon_command 真实成功 → queqiao_rcon_ok=True，rcon_channels 含 queqiao
# ① 的探测失败已把 queqiao_rcon_ok 置 False（本连接内不再重复探测），
# 重置为 None 模拟重连后，以 force=1（进入面板/手动刷新）触发重新探测
_mock_instance.queqiao_rcon_ok = None
async def _fake_queqiao_rcon(cmd: str) -> str:
    return "There are 1 of a max of 20 players online: XTxiaotong"

_mock_instance.client.send_rcon_command = _fake_queqiao_rcon  # type: ignore[method-assign]
import astrbot_plugin_minecraft_queqiao.services.web_api as _wam34b
_wam34b.request.query = {"force": "1"}  # 模拟进入面板/手动刷新：触发 RCON 探测
_res_servers3 = _asyncio34.run(_wac34.get_servers())
_server_srv1 = next(
    s for s in _res_servers3["data"]["servers"] if s["server_name"] == "Server"
)
assert "queqiao" in _server_srv1["rcon_channels"]
assert _server_srv1["players"]["source"] == "rcon"
assert _server_srv1["players"]["names"] == ["XTxiaotong"]
del _mock_instance.client.send_rcon_command  # 还原真实方法
_wam34b.request.query = {}  # 复位，避免影响后续 (c) 段 force 传递断言
_mock_instance.client._connected = False  # 复位
_mock_instance.queqiao_rcon_ok = None
_mock_instance.online_players.clear()  # 清空 (e) 期间被 list 探测填充的在线玩家缓存

# ③ /servers?force=1（仪表盘手动刷新）→ fetch_player_list 收到 force_rcon=True；
#    普通请求 / 非法值 → False（自动轮询不重复探测）
import astrbot_plugin_minecraft_queqiao.services.web_api as _wam34
_force_calls34 = []
_orig_fetch34 = _mock_instance.fetch_player_list
async def _spy_fetch34(force_rcon=False, status_model=None):
    _force_calls34.append(force_rcon)
    return _PLR34(names=[], source="count")
_mock_instance.fetch_player_list = _spy_fetch34  # type: ignore[method-assign]
_mock_instance.client._connected = True
_wam34.request.query = {"force": "1"}
_asyncio34.run(_wac34.get_servers())
_wam34.request.query = {"force": "yes"}
_asyncio34.run(_wac34.get_servers())
_wam34.request.query = {}
_asyncio34.run(_wac34.get_servers())
assert _force_calls34 == [True, False, False], _force_calls34
_mock_instance.fetch_player_list = _orig_fetch34  # type: ignore[method-assign]
_mock_instance.client._connected = False

# (f) MOTD description 文本组件解析：{"text": "..."} 应提取为纯文本而非花括号字典
_ss_motd = _SS34.from_dict({
    "server_list_ping": {
        "description": {
            "text": "A Minecraft Server",
            "extra": [{"text": " §aWelcome"}],
        },
        "players": {"online": 0, "max": 20},
        "version": {"name": "1.21"},
    },
    "server_type": "paper",
    "server_version": "1.21",
})
assert _ss_motd.description == "A Minecraft Server §aWelcome", _ss_motd.description
# 纯字符串 description 保持原样；list 形态组件也能拼接
_ss_motd2 = _SS34.from_dict({
    "server_list_ping": {
        "description": [{"text": "A"}, {"text": "B"}],
        "players": {"online": 0, "max": 20},
        "version": {"name": "1.21"},
    },
})
assert _ss_motd2.description == "AB", _ss_motd2.description
_ss_motd3 = _SS34.from_dict({
    "server_list_ping": {"description": "plain motd", "players": {"online": 0, "max": 20}},
})
assert _ss_motd3.description == "plain motd", _ss_motd3.description

# (f2) 鹊桥错误响应 JSON 被当作字符串塞进字段时，不得作为展示文本/图片源
_ss_err = _SS34.from_dict({
    "server_list_ping": {
        "description": '{"status":"error","message":"未授权"}',
        "favicon": '{"status":"error","message":"未授权"}',
        "players": {"online": 0, "max": 20},
    },
    "server_type": '{"status":"error","message":"未授权"}',
    "server_version": '{"status":"error","message":"未授权"}',
})
assert _ss_err.description == "", _ss_err.description
assert _ss_err.favicon == "", _ss_err.favicon
assert _ss_err.server_type == "", _ss_err.server_type
assert _ss_err.server_version == "", _ss_err.server_version
# 字符串形式的 JSON 文本组件也要能正确解析
_ss_str_component = _SS34.from_dict({
    "server_list_ping": {"description": '{"text":"A Minecraft Server"}'},
})
assert _ss_str_component.description == "A Minecraft Server", _ss_str_component.description
# favicon 仅接受 data:image 内联图标；需鉴权 URL / 其它一律置空
_ss_fav = _SS34.from_dict({
    "server_list_ping": {"favicon": "data:image/png;base64,AAAA"},
})
assert _ss_fav.favicon == "data:image/png;base64,AAAA", _ss_fav.favicon
_ss_fav2 = _SS34.from_dict({
    "server_list_ping": {"favicon": "http://127.0.0.1:2333/api/icon?server=x"},
})
assert _ss_fav2.favicon == "", _ss_fav2.favicon

_res_stats = _asyncio34.run(_wac34.get_stats())
assert _res_stats["data"]["total_servers"] == 4  # _sm33 有 4 个实例
assert _res_stats["data"]["relayed_to_ast_total"] == 2

# 测试 get_server_status 错误处理（不存在返回 404，未连接返回 503）
_res_404 = _asyncio34.run(_wac34.get_server_status("not_exist"))
assert _res_404["status_code"] == 404
_res_503 = _asyncio34.run(_wac34.get_server_status("Server"))
assert _res_503["status_code"] == 503

# (d) 在线玩家事件追踪与 event_cache 兜底
from astrbot_plugin_minecraft_queqiao.core.models import QueQiaoEvent as _QE34, QueQiaoPlayer as _QP34
_inst_tracker = _sm33.get("Server")
assert _inst_tracker is not None
# 触发玩家加入事件
_join_ev = _QE34(event_name="PlayerJoinEvent", post_type="notice", player=_QP34(nickname="PlayerA"))
_asyncio34.run(_inst_tracker.client.on_event(_join_ev))
assert "PlayerA" in _inst_tracker.online_players
# 触发玩家离开事件
_quit_ev = _QE34(event_name="PlayerQuitEvent", post_type="notice", player=_QP34(nickname="PlayerA"))
_asyncio34.run(_inst_tracker.client.on_event(_quit_ev))
assert "PlayerA" not in _inst_tracker.online_players

# 测试在无 RCON 且 SLP sample 为空时，通过事件缓存兜底玩家列表
_join_ev2 = _QE34(event_name="PlayerJoinEvent", post_type="notice", player=_QP34(nickname="PlayerB"))
_asyncio34.run(_inst_tracker.client.on_event(_join_ev2))
_plr_cached = _asyncio34.run(_inst_tracker.fetch_player_list())
assert _plr_cached.source == "event_cache"
assert _plr_cached.names == ["PlayerB"]
assert _plr_cached.online == 1

# (g) 仪表盘「单服务器标签页」数据：按服务器拆分的事件计数 + 连接时长
_mc34.record_event("chat", "Server", "<Steve> hi")
_mc34.record_relay_to_mc("Server", 2)
assert _mc34.get_server_event_count("Server") == 3
assert _mc34.get_server_event_count("never-configured") == 0
# echo / ai 等辅助事件不计入「累计互通事件」（与全局 total_events 同口径）
_mc34.record_echo_suppressed("Server", "loop")
_mc34.record_ai_chat("Server", "Steve", "hi", True)
assert _mc34.get_server_event_count("Server") == 3, _mc34.get_server_event_count("Server")
assert _mc34.get_stats()["events_by_server"]["Server"] == 3
assert _mc34.get_stats()["events_by_server"]["srv1"] == 5  # chat 1 + relay 1 + 群转发 3

_res_srv_tab = _asyncio34.run(_wac34.get_servers())
_srv_tab = next(s for s in _res_srv_tab["data"]["servers"] if s["server_name"] == "Server")
assert _srv_tab["events_total"] == 3
assert _srv_tab["connected_seconds"] == 0  # 未握手成功不计时

# 连接时长仅在握手回调后开始计时，断开后归零
_inst_dur = _sm33.get("Server")
_inst_dur.client._connected = True
assert _inst_dur.connected_seconds == 0
_asyncio34.run(_inst_dur.client.on_connect())
assert _inst_dur.connected_at is not None
assert _inst_dur.connected_seconds >= 0
_res_srv_tab2 = _asyncio34.run(_wac34.get_servers())
_srv_tab2 = next(s for s in _res_srv_tab2["data"]["servers"] if s["server_name"] == "Server")
assert _srv_tab2["connected"] is True
assert 0 <= _srv_tab2["connected_seconds"] <= 5
_asyncio34.run(_inst_dur.client.on_disconnect("test"))
assert _inst_dur.connected_at is None
assert _inst_dur.connected_seconds == 0
_inst_dur.client._connected = False  # 复位

# (h) 持久化终端日志：按天分片、落盘、跨实例恢复、环形上限、清屏删除、损坏容错、保留期清理、旧版迁移
import shutil as _shutil34
from datetime import date as _date34, timedelta as _td34
_tls_dir = _Path34("/tmp/queqiao_test_terminal")
if _tls_dir.exists():
    _shutil34.rmtree(_tls_dir)
_tls_dir.mkdir(parents=True, exist_ok=True)
_tls34.load()  # 重置到干净状态
_tls = _TLS34(_tls_dir)
_tls.load()
_tls.append("Server", "chat", "<Steve> hello")
_tls.append("Server", "chat", "<Alex> hi")
_tls.append("Server1", "broadcast", "欢迎")
assert len(_tls.get("Server")) == 2
assert _tls.get("Server")[0]["message"] == "<Steve> hello"
assert _tls.get("Server1")[0]["type"] == "broadcast"
assert _tls.get("never") == []
# 按天分片：当天数据落在 terminal_logs/YYYY-MM-DD.json，而非单一大文件
_today_key = _date34.today().strftime("%Y-%m-%d")
assert (_tls_dir / "terminal_logs" / f"{_today_key}.json").exists(), "日志应写入当天分片文件"
assert not (_tls_dir / "terminal_logs.json").exists(), "不再使用旧版单文件"
assert len(list((_tls_dir / "terminal_logs").glob("*.json"))) == 1, "只生成一个当天分片"

# 环形上限：同一天超出丢弃最旧
for _i in range(310):
    _tls.append("Server", "system", f"line-{_i}")
assert len(_tls.get("Server")) == 300, len(_tls.get("Server"))
assert _tls.get("Server")[0]["message"] == "line-10"  # line-0..9 被丢弃
assert _tls.get("Server")[-1]["message"] == "line-309"

# 跨天合并：昨天分片 + 今天分片，按日期旧 → 新
_yesterday_key = (_date34.today() - _td34(days=1)).strftime("%Y-%m-%d")
(_tls_dir / "terminal_logs" / f"{_yesterday_key}.json").write_text(
    json.dumps(
        {"Server": [{"time": "xx", "type": "join", "message": "昨天加入"}]}
    ),
    encoding="utf-8",
)
_tls_b = _TLS34(_tls_dir)
_tls_b.load()
_logs_b = _tls_b.get("Server")
assert _logs_b[0]["message"] == "昨天加入", "昨天分片在前"
assert _logs_b[-1]["message"] == "line-309", "今天分片在后"

# days 过滤：默认不传=全部分片；days=1 只含当天分片（昨天被排除）
assert _tls_b.get("Server")[0]["message"] == "昨天加入", "不传 days 返回全部分片"
assert _logs_b == _tls_b.get("Server", days=None), "days=None 等价全部分片"
_logs_b_1d = _tls_b.get("Server", days=1)
assert _logs_b_1d[0]["message"] == "line-10", "days=1 只含当天分片，昨天被排除"
assert len(_logs_b_1d) == 300, len(_logs_b_1d)
assert _tls_b.get("Server", days=0) == _logs_b, "days=0 等价全部分片"

# 损坏分片容错：坏文件被忽略、不抛异常，其它分片不受影响
(_tls_dir / "terminal_logs" / f"{_yesterday_key}.json").write_text(
    "{broken json", encoding="utf-8"
)
_tls_c = _TLS34(_tls_dir)
_tls_c.load()
assert _tls_c.get("Server")[0]["message"] == "line-10", "坏昨天分片被忽略，今天分片仍在"
# 移除损坏文件，避免影响后续步骤
(_tls_dir / "terminal_logs" / f"{_yesterday_key}.json").unlink(missing_ok=True)

# 保留期清理：超过 TERMINAL_KEEP_DAYS 的旧分片在 load 时被删除
_old_key = (_date34.today() - _td34(days=31)).strftime("%Y-%m-%d")
(_tls_dir / "terminal_logs" / f"{_old_key}.json").write_text(
    json.dumps({"Server": [{"time": "xx", "type": "chat", "message": "过期"}]}),
    encoding="utf-8",
)
_tls_e = _TLS34(_tls_dir)
_tls_e.load()
assert not (_tls_dir / "terminal_logs" / f"{_old_key}.json").exists(), "超期分片被清理"

# 旧版单文件迁移：并入当天分片，原文件备份为 .bak
(_tls_dir / "terminal_logs.json").write_text(
    json.dumps({"Server": [{"time": "xx", "type": "chat", "message": "旧版数据"}]}),
    encoding="utf-8",
)
_tls_f = _TLS34(_tls_dir)
_tls_f.load()
assert (_tls_dir / "terminal_logs.json.bak").exists(), "旧版文件已备份为 .bak"
assert (_tls_dir / "terminal_logs" / f"{_today_key}.json").exists(), "旧数据并入当天分片"
assert any(e["message"] == "旧版数据" for e in _tls_f.get("Server")), "旧数据可查询"
assert len(_tls_f.get("Server1")) == 1, "迁移不得覆盖当天已有内容"

# 清屏：跨全部分片删除对应服务器；清空的分片文件被删除；不影响其它服务器
(_tls_dir / "terminal_logs" / f"{_yesterday_key}.json").write_text(
    json.dumps({"Server": [{"time": "xx", "type": "chat", "message": "昨天只属Server"}]}),
    encoding="utf-8",
)
_tls_g = _TLS34(_tls_dir)
_tls_g.load()
_tls_g.clear("Server")
assert _tls_g.get("Server") == []
assert len(_tls_g.get("Server1")) == 1
assert not (_tls_dir / "terminal_logs" / f"{_yesterday_key}.json").exists(), "清空后的分片文件被删除"
assert (_tls_dir / "terminal_logs" / f"{_today_key}.json").exists(), "仍有内容的当天分片保留"

# Web API：GET 拉取与 POST 清屏
import astrbot_plugin_minecraft_queqiao.services.web_api as _wa_module34
# 缺少 server 参数 → 400
_wa_module34.request.query = {}
_res_tl_bad = _asyncio34.run(_wac34.get_terminal_logs())
assert _res_tl_bad["status_code"] == 400
# 带 server 参数 → 返回该服日志（跨分片）
_wa_module34.request.query = {"server": "Server"}
_tls34.append("Server", "chat", "API 测试")
_res_tl_ok = _asyncio34.run(_wac34.get_terminal_logs())
assert _res_tl_ok["data"]["server"] == "Server"
assert _res_tl_ok["data"]["logs"][-1]["message"] == "API 测试"
# POST 清屏 → 后端记录被删除
_orig_json34 = _wa_module34.request.json
async def _fake_json34(default=None):
    return {"server": "Server"}
_wa_module34.request.json = _fake_json34
_res_clear34 = _asyncio34.run(_wac34.clear_terminal_logs())
_wa_module34.request.json = _orig_json34
assert _res_clear34["data"]["success"] is True
assert _tls34.get("Server") == []
# 清屏缺 server → 400
async def _fake_json_bad34(default=None):
    return {}
_wa_module34.request.json = _fake_json_bad34
_res_clear_bad34 = _asyncio34.run(_wac34.clear_terminal_logs())
_wa_module34.request.json = _orig_json34
assert _res_clear_bad34["status_code"] == 400

print("OK  ServerStatus/PlayerListResult to_dict / Metrics 收集发布 / WebApiController 路由注册与逻辑 / 在线玩家事件追踪 / 单服务器标签页指标 / 按天分片持久化终端日志")


print("\n=== 35. 性能监控：TPS 解析 / 配置 / 时序存储 / 采集器 / Web API ===")
import asyncio as _asyncio35
import shutil as _shutil35
import time as _time35
from datetime import date as _date35, timedelta as _td35, datetime as _dt35
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _SC35
from astrbot_plugin_minecraft_queqiao.services.monitor import (
    MonitorCollector as _MC35,
    MonitorSample as _MS35,
    MonitorSettings as _MSettings35,
    MonitorStore as _MStore35,
    parse_tps as _parse_tps35,
    safe_server_name as _safe_name35,
)
from astrbot_plugin_minecraft_queqiao.services.slp_ping import (
    brand_from_slp as _brand35,
    mc_ping as _mc_ping35,
)

# (a) TPS 输出解析：Paper/Spigot、spark 装饰前缀、带 TPS 字样的裸三数、失败与空
assert _parse_tps35("TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0") == (20.0, 20.0, 20.0)
assert _parse_tps35("TPS from last 1m, 5m, 15m: 12.5, 15.2, 17.8") == (12.5, 15.2, 17.8)
assert _parse_tps35("⏱  TPS from last 1m, 5m, 15m: 20.0, 18.2, 19.5") == (20.0, 18.2, 19.5)
assert _parse_tps35("§aTPS from last 1m, 5m, 15m: 19.5, 20.0, 20.0") == (19.5, 20.0, 20.0)
# 无标准前缀但有 TPS 字样的裸三数（防御兼容）
assert _parse_tps35("TPS: 20.0, 19.0, 18.0") == (20.0, 19.0, 18.0)
# 原版端 Unknown command / 空输出 / None → 不可解析
assert _parse_tps35('Unknown command. Type "/help" for help.') is None
assert _parse_tps35("") is None
assert _parse_tps35(None) is None
# 裸三数但无 TPS 语境 → 不误判（如 RCON 返回的纯数字行）
assert _parse_tps35("20.0, 20.0, 20.0") is None

# (b) ServerConfig 监控配置：默认值 / 显式配置 / 非法值兜底
_sc35_default = _SC35.from_dict({})
assert _sc35_default.monitor_enabled is True, "监控默认开启（开箱即用）"
assert _sc35_default.monitor_interval == 60
assert _sc35_default.monitor_retention_days == 7
assert _sc35_default.monitor_tps_command == "auto"
_sc35_cfg = _SC35.from_dict({"monitor": {
    "enabled": True, "interval": 30, "retention_days": 3, "tps_command": "spark tps"}})
assert _sc35_cfg.monitor_enabled is True
assert _sc35_cfg.monitor_interval == 30
assert _sc35_cfg.monitor_retention_days == 3
assert _sc35_cfg.monitor_tps_command == "spark tps"
# 显式关闭/手动调参仍生效（手写配置 JSON 的 monitor 分组）
assert _SC35.from_dict({"monitor": {"enabled": False}}).monitor_enabled is False
# 间隔过小 / 保留为 0 / 空指令名都会失真或加重服务器负担，必须兜底
_sc35_bad = _SC35.from_dict({"monitor": {"interval": 5, "retention_days": 0,
                                         "tps_command": "   "}})
assert _sc35_bad.monitor_interval >= 10, "采集间隔下限 10 秒"
assert _sc35_bad.monitor_retention_days >= 1, "保留天数至少 1 天"
assert _sc35_bad.monitor_tps_command == "auto", "空 TPS 指令回落自动选择"
assert _SC35.from_dict({"monitor": {"interval": "abc"}}).monitor_interval == 60
# MonitorSettings：ping 探测目标解析（地址可带端口 / 端口下限钳制）
_mset_ping35 = _MSettings35.from_dict(
    {"ping_host": "mc.example.com:25566", "ping_port": 1})
assert _mset_ping35.ping_host == "mc.example.com:25566"
assert _mset_ping35.ping_port == 1
assert _MSettings35.from_dict({"ping_port": "abc"}).ping_port == 25565
assert _MSettings35.from_dict({}).ping_host == "" and \
    _MSettings35.from_dict({}).ping_port == 25565
# default_tab：只接受 tps / latency，非法回落 tps
assert _MSettings35.from_dict({"default_tab": "latency"}).default_tab == "latency"
assert _MSettings35.from_dict({"default_tab": "bogus"}).default_tab == "tps"
assert _MSettings35.from_dict({}).default_tab == "tps"
# realtime_interval（实时采集频率）：1~60 钳制
assert _MSettings35.from_dict({"realtime_interval": 3}).realtime_interval == 3
assert _MSettings35.from_dict({"realtime_interval": 0}).realtime_interval == 1
assert _MSettings35.from_dict({"realtime_interval": 999}).realtime_interval == 60
assert _MSettings35.from_dict({}).realtime_interval == 5
# auto_refresh_interval（自动刷新间隔）：10~3600 钳制
assert _MSettings35.from_dict({"auto_refresh_interval": 30}).auto_refresh_interval == 30
assert _MSettings35.from_dict({"auto_refresh_interval": 1}).auto_refresh_interval == 10
assert _MSettings35.from_dict({"auto_refresh_interval": 99999}).auto_refresh_interval == 3600
assert _MSettings35.from_dict({}).auto_refresh_interval == 10
# auto 指令解析：按 get_status 识别到的服务端类型自动选指令
from astrbot_plugin_minecraft_queqiao.services.monitor import (  # noqa: E402
    resolve_tps_command as _resolve_tps35,
)
assert _resolve_tps35("forge 1.20.1", "auto") == "forge tps"
assert _resolve_tps35("Paper 1.20.4", "") == "tps"
assert _resolve_tps35("Fabric 0.14.21", "auto") == "spark tps", "Fabric 无内置 tps，用 spark"
assert _resolve_tps35("spigot 1.16.5", "auto") == "tps"
assert _resolve_tps35(None, "auto") == "tps", "未知/无缓存一律默认尝试 tps"
assert _resolve_tps35("forge 1.20.1", "spark tps") == "spark tps", "显式指令优先于自动"

# (b2) SLP 直连 ping 端到端：本地起一个伪造 MC 状态服务端，真实走协议
def _mc_varint_enc35(value):
    out = bytearray()
    while True:
        if value & ~0x7F == 0:
            out.append(value)
            return bytes(out)
        out.append((value & 0x7F) | 0x80)
        value >>= 7


async def _fake_mc_server35(reader, writer):
    try:
        # 读握手包（长度前缀 VarInt + 内容）
        length = 0
        shift = 0
        while True:
            b = (await reader.readexactly(1))[0]
            length |= (b & 0x7F) << shift
            shift += 7
            if b & 0x80 == 0:
                break
        await reader.readexactly(length)
        await reader.readexactly(2)  # 状态请求（len=1, id=0）
        body = json.dumps({
            "version": {"name": "forge 1.20.1", "protocol": 765},
            "players": {"max": 20, "online": 3, "sample": [
                {"name": "Steve", "id": "uuid-1"},
                {"name": "§cAlex", "id": "uuid-2"},  # 带格式码的名字应被剥离
                {"name": {"text": "Notch"}, "id": "uuid-3"},  # 组件形态名字
            ]},
            "description": {"text": "A Forge Server"},
        }).encode("utf-8")
        payload = b"\x00" + _mc_varint_enc35(len(body)) + body
        writer.write(_mc_varint_enc35(len(payload)) + payload)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def _fake_http_server35(reader, writer):
    """非 MC 服务（如鹊桥 Web 端口）：对任意请求回一个 HTTP 响应。"""
    try:
        await reader.read(4096)
        writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def _slp_e2e35():
    server = await _asyncio35.start_server(_fake_mc_server35, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    ping = await _mc_ping35("127.0.0.1", port, timeout=3.0)
    server.close()
    await server.wait_closed()
    assert ping is not None and ping.rtt_ms is not None, "直连 SLP ping 应返回 RTT"
    assert ping.online == 3 and ping.max_players == 20
    assert ping.version_name == "forge 1.20.1"
    assert ping.player_names == ["Steve", "Alex", "Notch"], \
        "SLP sample 名字应解析且剥离 § 格式码、兼容文本组件"
    assert _brand35(ping.version_name, ping.description) == "forge"
    # 非 MC 端口（无监听）：返回 None 而非抛异常
    assert await _mc_ping35("127.0.0.1", 1, timeout=1.0) is None
    # 伪 HTTP 服务（如鹊桥 Web 端口）：响应即使能读也必须判失败，
    # 防止把非游戏端口误测成假低延迟
    http_server = await _asyncio35.start_server(_fake_http_server35, "127.0.0.1", 0)
    http_port = http_server.sockets[0].getsockname()[1]
    try:
        assert await _mc_ping35("127.0.0.1", http_port, timeout=2.0) is None, \
            "HTTP 响应不应被当作 MC 状态响应"
    finally:
        http_server.close()
        await http_server.wait_closed()
    # 空主机：直接 None
    assert await _mc_ping35("", 25565, timeout=1.0) is None
_asyncio35.run(_slp_e2e35())
# schema 守卫：监控设置不占用 conf schema（只在仪表盘内维护），
# reconnect 仍须位于模板项最底部（35 组旧契约）
_sh35 = json.loads(pathlib.Path(__file__).with_name("_conf_schema.json")
                   .read_text(encoding="utf-8"))
_items35 = _sh35["mc_servers"]["templates"]["server"]["items"]
_keys35 = list(_items35.keys())
assert "monitor" not in _items35, "监控设置不应出现在 conf schema 中"
assert _keys35.index("reconnect") == len(_keys35) - 1, "reconnect 分组必须位于模板项最底部"
# 代码默认值与常量一致
from astrbot_plugin_minecraft_queqiao.core.constants import (  # noqa: E402
    DEFAULT_MONITOR_INTERVAL as _DMI35,
    DEFAULT_MONITOR_RETENTION_DAYS as _DMRD35,
    DEFAULT_MONITOR_TPS_COMMAND as _DMTC35,
)
assert _sc35_default.monitor_interval == _DMI35
assert _sc35_default.monitor_retention_days == _DMRD35
assert _sc35_default.monitor_tps_command == _DMTC35

# (c) MonitorStore：落盘 / 最新值 / 桶聚合 / 摘要 / P95 / 坏行 / 跨天 / 清理
_mdir35 = pathlib.Path("/tmp/queqiao_test_monitor")
if _mdir35.exists():
    _shutil35.rmtree(_mdir35)
_mdir35.mkdir(parents=True, exist_ok=True)
_mst35 = _MStore35(_mdir35)
_mst35.load()
# 基准时间取整分钟时刻：三个样本落在同一 60s 桶内，避免横跨桶边界断言 flaky
_now35 = float(_dt35.fromtimestamp(_time35.time()).replace(second=0, microsecond=0).timestamp())
_mst35.append("Srv", _MS35(ts=_now35, online=2, tps1=20.0, tps5=20.0, tps15=19.5, latency_ms=8.2))
_mst35.append("Srv", _MS35(ts=_now35 + 1, online=3, tps1=19.0, tps5=19.5, tps15=19.5, latency_ms=15.4))
_mst35.append("Srv", _MS35(ts=_now35 + 2, online=3, tps1=18.0, tps5=19.0, tps15=19.5, latency_ms=22.6))
assert _mst35.latest("Srv").tps1 == 18.0 and _mst35.latest("Srv").latency_ms == 22.6
assert _mst35.sample_count("Srv") == 3
assert _mst35.latest("Never") is None and _mst35.sample_count("Never") == 0
# 落盘：当天 JSONL 三行（JSONL 逐行追加）
_day35 = _date35.today().strftime("%Y-%m-%d")
_srv_dir35 = _mdir35 / "monitor" / "Srv"
assert (_srv_dir35 / f"{_day35}.jsonl").exists(), "采样应写入当天分片"
assert len(list((_srv_dir35 / f"{_day35}.jsonl").read_text(encoding="utf-8").splitlines())) == 3
# 桶聚合：60s 桶内 3 样本 → avg 19 / min 18 / max 20 / count 3
_series35 = _mst35.series("Srv", since_ts=_now35 - 3600, bucket_seconds=60)
_tps_pts35 = _series35["tps"]["points"]
assert len(_tps_pts35) == 1, _tps_pts35
assert _tps_pts35[0]["avg"] == 19.0 and _tps_pts35[0]["min"] == 18.0 \
    and _tps_pts35[0]["max"] == 20.0 and _tps_pts35[0]["count"] == 3, _tps_pts35
_tps_sum35 = _series35["tps"]["summary"]
assert _tps_sum35["avg"] == 19.0 and _tps_sum35["min"] == 18.0 and _tps_sum35["max"] == 20.0
assert _series35["latency"]["summary"] == \
    {"count": 3, "avg": 15.4, "min": 8.2, "max": 22.6, "p95": 22.6}, _series35["latency"]["summary"]
# P95：21 个样本 [0..20] 的 95% 分位应为 19
for _vi35 in range(21):
    _mst35.append("SrvP95", _MS35(ts=_now35, tps1=float(_vi35)))
_p95_sum35 = _mst35.series("SrvP95", since_ts=_now35 - 3600, bucket_seconds=60)["tps"]["summary"]
assert _p95_sum35["p95"] == 19.0, _p95_sum35
# 无样本时间窗 → 空点序列与零计数摘要
assert _mst35.series("Srv", since_ts=_now35 + 99999, bucket_seconds=60)["tps"]["points"] == []
assert _mst35.series("Srv", since_ts=_now35 + 99999, bucket_seconds=60)["tps"]["summary"]["count"] == 0
# 服务器名安全转义（防路径注入）
assert _safe_name35("Srv/A:B") == "Srv_A_B" and _safe_name35("..") == "server"
# 坏行容错：非法 JSON 行被跳过，正常行不受影响（在已有分片末尾追加坏行）
with open(_srv_dir35 / f"{_day35}.jsonl", "a", encoding="utf-8") as _fh35:
    _fh35.write("not a json line\n")
_bad35 = _MStore35(_mdir35)
_bad35.load()
assert _bad35.series("Srv", since_ts=_now35 - 3600, bucket_seconds=60)["tps"]["summary"]["count"] == 3, \
    "坏行被跳过，正常行不受影响"
# 跨天分片：昨天 + 今天合并；昨天样本参与最小值计算
(_srv_dir35 / f"{_day35}.jsonl").write_text(
    "\n".join(json.dumps({"ts": _now35 - 2, "tps1": 20.0}) for _ in range(3)) + "\n",
    encoding="utf-8")
_yesterday35 = (_date35.today() - _td35(days=1)).strftime("%Y-%m-%d")
(_srv_dir35 / f"{_yesterday35}.jsonl").write_text(
    json.dumps({"ts": _now35 - 90000, "tps1": 17.0}) + "\n", encoding="utf-8")
_cross35 = _MStore35(_mdir35)
_cross35.load()
_cross_pts35 = _cross35.series("Srv", since_ts=_now35 - 200000, bucket_seconds=3600)["tps"]["points"]
assert len(_cross_pts35) >= 2, _cross_pts35  # 昨天/今天各至少一个桶
assert _cross35.series("Srv", since_ts=_now35 - 200000,
                       bucket_seconds=3600)["tps"]["summary"]["min"] == 17.0
# 保留期清理：31 天前分片在 prune 时删除
_old35 = (_date35.today() - _td35(days=31)).strftime("%Y-%m-%d")
(_srv_dir35 / f"{_old35}.jsonl").write_text(
    json.dumps({"ts": _now35 - 99999999, "tps1": 1.0}) + "\n", encoding="utf-8")
_prune35 = _MStore35(_mdir35)
_prune35.load()
_prune35.prune("Srv", 7)
assert not (_srv_dir35 / f"{_old35}.jsonl").exists(), "超保留期的分片被清理"

# (d) MonitorCollector：一轮采样（TPS 与延迟并行）、未连接跳过、错误状态
class _FakeInst35:
    def __init__(self, connected=True, rcon_out=None):
        self._connected = connected
        self._rcon_out = rcon_out
        self.commands = []
    @property
    def connected(self):
        return self._connected
    async def execute_command_with_channel(self, command):
        self.commands.append(command)
        return self._rcon_out, "queqiao"


class _FakePing35:
    """模拟 SLP ping 结果（版本名含服务端品牌，供 TPS 指令 auto 选择）。"""

    def __init__(self, version_name="Paper 1.20.4", online=3, description="A Minecraft Server"):
        self.rtt_ms = 1.2
        self.version_name = version_name
        self.online = online
        self.max_players = 20
        self.description = description


class _SM35:
    def __init__(self):
        self.insts = {}
    def add(self, name, inst):
        self.insts[name] = inst
    def get(self, name):
        return self.insts.get(name)


_sm35 = _SM35()
_col35 = _MC35(_mdir35, _sm35)
_col35._ping = None  # 每台服务器按需替换的 fake ping

async def _fake_ping_ok35(host, port, timeout=5.0):
    return _FakePing35()

async def _fake_ping_forge35(host, port, timeout=5.0):
    return _FakePing35(version_name="forge 1.20.1", online=0)

async def _fake_ping_none35(host, port, timeout=5.0):
    return None

async def _fake_ping_boom35(host, port, timeout=5.0):
    raise ConnectionError("simulated failure")

_sm35.add("Srv", _FakeInst35(
    connected=True, rcon_out="TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0"))
_sm35.add("SrvBad", _FakeInst35(
    connected=True, rcon_out="Unknown command."))
_sm35.add("SrvOld", _FakeInst35(
    connected=True, rcon_out="TPS from last 1m, 5m, 15m: 19.0, 19.5, 20.0"))
_sm35.add("SrvSlow", _FakeInst35(
    connected=True, rcon_out="TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0"))
_sm35.add("SrvDown", _FakeInst35(connected=False, rcon_out="x"))
_cfg35_on = _SC35.from_dict({"server": {"server_name": "Srv"}})  # 监控默认开启
# auto 指令自动切换：SLP 识别到 forge → 首轮用默认 tps，识别后自动换 forge tps。
# 该服以 enabled=False 启动（后台任务空转），采样轮次完全由测试手动控制，
# 避免后台任务抢先缓存品牌导致时序不确定。
_sm35.add("SrvForge", _FakeInst35(
    connected=True, rcon_out="TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0"))
_cfg35_forge = _SC35.from_dict({"monitor": {"enabled": False}})
# 全部放入同一事件循环：start/采样/动态设置/持久化恢复/stop 共享生命周期
async def _d35():
    # start：初始化设置（默认开启）并为每台服务器启动常驻任务
    _col35.start({"Srv": _cfg35_on, "SrvBad": _cfg35_on, "SrvOld": _cfg35_on,
                  "SrvSlow": _cfg35_on, "SrvDown": _cfg35_on,
                  "SrvForge": _cfg35_forge})
    # 延迟探测地址必须显式配置（留空不探测，避免测出内网假低延迟）；
    # 模拟用户填了公网域名（品牌识别/延迟都依赖 SLP ping）
    _col35.apply_settings("Srv", {"ping_host": "mc.example.com"})
    _col35.apply_settings("SrvForge", {"ping_host": "forge.example.com"})
    # 手动触发一轮采样（settings 取自采集器内当前生效值）
    async def _smp(name):
        await _col35._sample_once(name, _col35._settings[name])
    # Srv：SLP ping 成功（Paper）→ TPS 20.0 + 延迟 1.2ms + 在线人数来自直连
    _col35._ping = _fake_ping_ok35
    await _smp("Srv")
    _lat35 = _col35.store.latest("Srv")
    assert _lat35 is not None and _lat35.tps1 == 20.0 and _lat35.online == 3
    assert _lat35.latency_ms is not None, "直连 SLP ping 成功应有延迟（桩返回极快，0 也有效）"
    _st35 = _col35.status("Srv")
    assert _st35["enabled"] is True and _st35["sample_count"] >= 1
    assert _st35["latest"]["tps1"] == 20.0
    assert _st35["server_type"] == "paper", "SLP 版本名应解析出服务端品牌"
    assert _st35["tps_command_resolved"] == "tps"
    # 延迟探测目标：显式填写的域名 + ping_port（默认 25565）；
    # ws_url 的端口是鹊桥 WS 端口，不得混作 MC 探测端口
    assert _st35["ping_target"] == "mc.example.com:25565"
    assert _st35["default_tab"] == "tps", "默认展示项默认 TPS"
    # 显式配置延迟探测域名：覆盖 ws_url 主机，且地址内嵌端口优先于 ping_port
    _col35.apply_settings("Srv", {"ping_host": "mc.example.com:25566"})
    assert _col35.status("Srv")["ping_target"] == "mc.example.com:25566", "域名配置优先"
    _col35.apply_settings("Srv", {"ping_host": "mc.example.com", "ping_port": 19132})
    assert _col35.status("Srv")["ping_target"] == "mc.example.com:19132"
    # 留空 = 不探测（避免回落内网地址把内网互通速度当成玩家延迟）
    _col35.apply_settings("Srv", {"ping_host": "", "ping_port": 19132})
    assert _col35.status("Srv")["ping_target"] is None, "域名留空不应回落 ws_url 主机"
    assert _col35.status("Srv")["ping_host"] == ""

    # 直接粘贴带协议/路径的完整地址（如 ws_url）：主机与端口自动提取
    _col35.apply_settings("Srv", {"ping_host": "http://8.218.17.111:54040/", "ping_port": 25565})
    assert _col35.status("Srv")["ping_target"] == "8.218.17.111:54040", "URL 内显式端口优先"
    _col35.apply_settings("Srv", {"ping_host": "ws://mc.example.com:8080/minecraft/ws", "ping_port": 25565})
    assert _col35.status("Srv")["ping_target"] == "mc.example.com:8080"
    _col35.apply_settings("Srv", {"ping_host": "[2001:db8::1]:25566", "ping_port": 25565})
    assert _col35.status("Srv")["ping_target"] == "2001:db8::1:25566", "IPv6 括号形式"
    _col35.apply_settings("Srv", {"ping_host": "", "ping_port": 25565})
    # TPS 输出无法解析：tps=None + 记录错误，但延迟不受影响
    await _smp("SrvBad")
    assert _col35.store.latest("SrvBad").tps1 is None
    assert "无法解析" in _col35.status("SrvBad")["last_error"]
    # 直连 SLP ping 失败（连接拒绝/非 MC 端口）：latency=None + 错误，TPS 正常
    _col35._ping = _fake_ping_none35
    await _smp("SrvOld")
    _lat35_old = _col35.store.latest("SrvOld")
    assert _lat35_old.tps1 == 19.0 and _lat35_old.latency_ms is None
    assert "延迟未采到" in _col35.status("SrvOld")["last_error"]
    # 直连 ping 异常（模拟超时/网络故障）：同样只记错误，不影响 TPS
    _col35._ping = _fake_ping_boom35
    await _smp("SrvSlow")
    assert _col35.store.latest("SrvSlow") is not None
    assert _col35.store.latest("SrvSlow").latency_ms is None
    assert "延迟未采到" in _col35.status("SrvSlow")["last_error"]
    # 服务器未连接：跳过本轮（不产生样本），记录错误
    assert _col35.store.latest("SrvDown") is None
    await _smp("SrvDown")
    assert _col35.store.latest("SrvDown") is None, "未连接不应产生样本"
    assert "未连接" in _col35.status("SrvDown")["last_error"]
    # auto 指令自动切换：首轮（尚无品牌缓存）用默认 tps；SLP 识别出 forge 后，
    # 下一轮自动换 forge tps；显式指令优先于自动
    _col35._ping = _fake_ping_forge35
    await _smp("SrvForge")
    assert _col35._server_types.get("SrvForge") == "forge", "SLP 应缓存服务端品牌"
    assert _sm35.get("SrvForge").commands[-1] == "tps", "首轮无缓存时用默认 tps"
    await _smp("SrvForge")
    assert _sm35.get("SrvForge").commands[-1] == "forge tps", "识别 forge 后自动切换指令"
    assert _col35.status("SrvForge")["tps_command_resolved"] == "forge tps"
    assert _col35.status("SrvForge")["server_type"] == "forge"
    _col35.apply_settings("SrvForge", {"tps_command": "spark tps"})
    await _smp("SrvForge")
    assert _sm35.get("SrvForge").commands[-1] == "spark tps", "显式指令覆盖自动选择"
    _col35.apply_settings("SrvForge", {"tps_command": "spark tps"})
    await _smp("SrvForge")
    assert _sm35.get("SrvForge").commands[-1] == "spark tps", "显式指令覆盖自动选择"

    # 动态设置（仪表盘入口，不走 conf schema）：apply_settings 即时生效 + 持久化
    _upd35 = _col35.apply_settings("Srv", {"enabled": False, "interval": 120, "retention_days": 3})
    assert isinstance(_upd35.enabled, bool) and _upd35.enabled is False
    assert _col35.status("Srv")["enabled"] is False
    assert _col35.status("Srv")["interval"] == 120
    assert _col35.status("Srv")["retention_days"] == 3
    # 非法值防御式兜底（间隔下限 10 / 保留至少 1 / 空指令回落 auto）
    _col35.apply_settings("Srv", {"interval": 3, "retention_days": 0, "tps_command": "   "})
    assert _col35.status("Srv")["interval"] == 10
    assert _col35.status("Srv")["retention_days"] == 1
    assert _col35.status("Srv")["tps_command"] == "auto"
    # 持久化恢复：相同数据目录新建采集器，仪表盘保存的设置优先生效
    _col35b = _MC35(_mdir35, _sm35)
    _col35b.start({"Srv": _cfg35_on})
    assert _col35b.status("Srv")["enabled"] is False, "settings.json 中的设置应覆盖代码默认"
    assert _col35b.status("Srv")["interval"] == 10
    # 恢复 Srv 为启用状态，供后续 (e) 段路由断言使用（apply 需在事件循环内）
    _col35.apply_settings("Srv", {"enabled": True})
    await _col35.stop()
    await _col35b.stop()
_asyncio35.run(_d35())

# (e) WebApiController：监控路由注册与响应
class _MockCtx35:
    def __init__(self):
        self.routes = []
    def register_web_api(self, path, handler, methods, desc):
        self.routes.append((path, handler, methods, desc))

from astrbot_plugin_minecraft_queqiao.services.web_api import WebApiController as _WAC35
import astrbot_plugin_minecraft_queqiao.services.web_api as _wa35

_ctx35 = _MockCtx35()
_wac35 = _WAC35(_ctx35, _sm35, None, None, None,
                {"Srv": _cfg35_on, "Srv2": _SC35.from_dict({})}, None, _col35)
_wac35.register_routes()
assert len(_ctx35.routes) == 24, f"监控注入后应注册 24 条路由, 实际 {len(_ctx35.routes)}"
_rp35 = [r[0] for r in _ctx35.routes]
assert "/astrbot_plugin_minecraft_queqiao/monitor/status" in _rp35
assert "/astrbot_plugin_minecraft_queqiao/monitor/<server_name>/series" in _rp35
assert "/astrbot_plugin_minecraft_queqiao/monitor/settings" in _rp35
assert "/astrbot_plugin_minecraft_queqiao/monitor/<server_name>/sample" in _rp35
assert "/astrbot_plugin_minecraft_queqiao/monitor/<server_name>/clear" in _rp35, "清除数据路由应注册"
assert "/astrbot_plugin_minecraft_queqiao/panel/prefs" in _rp35, "面板偏好路由应注册"
# monitor/status：每台服务器一份状态（默认开启）
_res_mstat35 = _asyncio35.run(_wac35.get_monitor_status())
_mons35 = _res_mstat35["data"]["monitors"]
assert set(_mons35.keys()) == {"Srv", "Srv2"}
assert _mons35["Srv"]["enabled"] is True and _mons35["Srv"]["sample_count"] >= 1
assert _mons35["Srv2"]["enabled"] is True, "未显式配置的服务器默认开启监控"
assert _mons35["Srv2"]["interval"] == 60 and _mons35["Srv2"]["tps_command"] == "auto"
assert _mons35["Srv2"]["tps_command_resolved"] == "tps", "auto 无类型缓存时回落默认 tps"
# monitor/series：聚合序列 + 摘要（覆盖刚才收集的样本）
_wa35.request.query = {"range": "24h"}
_res_mseries35 = _asyncio35.run(_wac35.get_monitor_series("Srv"))
_data35 = _res_mseries35["data"]
assert _data35["server"] == "Srv" and _data35["range_hours"] == 24
assert _data35["bucket_seconds"] == 600, "24h 时间窗自动选 10 分钟桶"
_tps_series35 = _data35["series"]["tps"]
assert _tps_series35["summary"]["count"] >= 1
assert _data35["series"]["latency"]["summary"]["count"] >= 1
# 非法 range 回落 24h
_wa35.request.query = {"range": "bogus"}
assert _asyncio35.run(_wac35.get_monitor_series("Srv"))["data"]["range_hours"] == 24
# 服务器不存在 / 无实例 → 404
_wa35.request.query = {}
assert _asyncio35.run(_wac35.get_monitor_series("ghost"))["status_code"] == 404
assert _asyncio35.run(_wac35.get_monitor_series("Srv2"))["status_code"] == 404
# range/bucket 解析：实时模式用分钟/秒单位
_wa35.request.query = {"range": "1m", "bucket": "10s"}
_h35, _b35 = _wac35._parse_monitor_window()
assert abs(_h35 - 1 / 60) < 1e-9 and _b35 == 10, "1m 窗口 + 10s 桶（实时模式）"
# 实时模式桶宽跟随采样频率：1s 频率 → 1s 桶（下限放开到 1s，此前钳制 5s）
_wa35.request.query = {"range": "1m", "bucket": "1s"}
_h35, _b35 = _wac35._parse_monitor_window()
assert _b35 == 1, "1s 桶（realtime_interval=1 的实时曲线）"
_wa35.request.query = {"range": "30s"}
_h35, _b35 = _wac35._parse_monitor_window()
assert abs(_h35 - 30 / 3600) < 1e-9 and _b35 == 60, "30s 窗口自动 60s 桶"
_wa35.request.query = {"range": "bogus"}
assert _wac35._parse_monitor_window()[0] == 24.0, "非法 range 回落 24h"
# monitor/settings：保存设置（模拟仪表盘表单提交）→ 立即生效并持久化
_orig_json35 = _wa35.request.json
async def _fake_json_save35(default=None):
    return {"server_name": "Srv", "enabled": False, "interval": 90,
            "retention_days": 5, "tps_command": "spark tps",
            "ping_host": "mc.example.com", "ping_port": 12345,
            "default_tab": "latency", "realtime_interval": 3,
            "auto_refresh_interval": 30}
_wa35.request.json = _fake_json_save35
_res_save35 = _asyncio35.run(_wac35.save_monitor_settings())
_wa35.request.json = _orig_json35
assert _res_save35["data"]["server"] == "Srv"
assert _res_save35["data"]["settings"]["enabled"] is False
assert _res_save35["data"]["settings"]["interval"] == 90
assert _res_save35["data"]["settings"]["ping_host"] == "mc.example.com"
assert _res_save35["data"]["settings"]["ping_port"] == 12345
assert _res_save35["data"]["settings"]["default_tab"] == "latency", "默认展示项随设置持久化"
assert _res_save35["data"]["settings"]["realtime_interval"] == 3, "实时采集频率随设置持久化"
assert _res_save35["data"]["settings"]["auto_refresh_interval"] == 30, "自动刷新间隔随设置持久化"
assert _col35.status("Srv")["default_tab"] == "latency", "保存后即时生效"
assert _col35.status("Srv")["realtime_interval"] == 3, "频率保存后即时生效"
assert _col35.status("Srv")["auto_refresh_interval"] == 30, "自动刷新间隔保存后即时生效"
assert _col35.status("Srv")["enabled"] is False, "保存后应即时生效"
# 缺 server_name → 400；未知服务器 → 404；空字段 → 400
async def _fake_json_none35(default=None):
    return {}
_wa35.request.json = _fake_json_none35
assert _asyncio35.run(_wac35.save_monitor_settings())["status_code"] == 400
async def _fake_json_ghost35(default=None):
    return {"server_name": "ghost", "enabled": False}
_wa35.request.json = _fake_json_ghost35
assert _asyncio35.run(_wac35.save_monitor_settings())["status_code"] == 404
async def _fake_json_empty35(default=None):
    return {"server_name": "Srv"}
_wa35.request.json = _fake_json_empty35
assert _asyncio35.run(_wac35.save_monitor_settings())["status_code"] == 400
_wa35.request.json = _orig_json35

# monitor/<server>/sample：立即采集（不等下一个间隔）→ 采样数 +1 并返回状态。
# apply_settings 启用会重建采样 task，须与采样同处一个事件循环
async def _sample_now_e35():
    _col35.apply_settings("Srv", {"enabled": True})
    _col35._ping = _fake_ping_ok35
    before = _col35.status("Srv")["sample_count"]
    resp = await _wac35.sample_monitor("Srv")
    ghost = await _wac35.sample_monitor("ghost")
    return resp, before, ghost
_res_smp35, _before_smp35, _ghost_smp35 = _asyncio35.run(_sample_now_e35())
assert _res_smp35["data"]["server"] == "Srv"
assert _res_smp35["data"]["status"]["sample_count"] == _before_smp35 + 1, "立即采集应新增一个样本"
assert _res_smp35["data"]["status"]["latest"]["tps1"] == 20.0
assert _ghost_smp35["status_code"] == 404, "未知服务器 → 404"

print("OK  TPS 解析 / 监控配置与 schema 守卫(不进 conf) / 时序存储(落盘·聚合·P95·坏行·跨天·清理) / "
      "采集器(并行采样·未连接跳过·动态设置即时生效·持久化恢复) / Web API 路由与响应")

print("\n=== 36. 直连 host:port 状态/玩家查询（mc status/list <地址>） ===")
import asyncio as _asyncio36
from astrbot_plugin_minecraft_queqiao.handlers.commands import (
    CommandHandler as _CH36,
    parse_direct_address as _parse_addr36,
)
from astrbot_plugin_minecraft_queqiao.services.renderer import InfoRenderer as _IR36
from astrbot_plugin_minecraft_queqiao.services.slp_ping import McPingResult as _MPR36
import astrbot_plugin_minecraft_queqiao.handlers.commands as _cmd_mod36

# (a) 地址解析：host[:port] 各形态 / 编号不误判 / 非法输入
assert _parse_addr36("127.0.0.1:25565") == ("127.0.0.1", 25565)
assert _parse_addr36("127.0.0.1") == ("127.0.0.1", 25565), "缺省端口 25565"
assert _parse_addr36("play.example.com:19132") == ("play.example.com", 19132)
assert _parse_addr36("localhost") == ("localhost", 25565), "域名/主机名允许"
assert _parse_addr36("[::1]:25566") == ("::1", 25566)
assert _parse_addr36("::1") == ("::1", 25565), "裸 IPv6 缺省端口"
assert _parse_addr36("1:2") == ("1", 2), "host:port 形态（非纯数字）"
# 纯数字 = 配置内编号，绝不当作地址
assert _parse_addr36("1") is None and _parse_addr36("") is None
# 非法端口 / 空 host / 含空白 / 路径分隔符
assert _parse_addr36("127.0.0.1:abc") is None
assert _parse_addr36("127.0.0.1:0") is None and _parse_addr36("127.0.0.1:65536") is None
assert _parse_addr36("127.0.0.1:") is None
assert _parse_addr36(":25565") is None
assert _parse_addr36("host with space") is None
assert _parse_addr36("http://x") is None
assert _parse_addr36("[::1") is None and _parse_addr36("[::1]:abc") is None

# (b) SLP 直连端到端：本地伪造 MC 状态服务端（带 sample），真实走协议
def _mc_varint_enc36(value):
    out = bytearray()
    while True:
        if value & ~0x7F == 0:
            out.append(value)
            return bytes(out)
        out.append((value & 0x7F) | 0x80)
        value >>= 7


async def _fake_mc_server36(reader, writer):
    try:
        length = 0
        shift = 0
        while True:
            b = (await reader.readexactly(1))[0]
            length |= (b & 0x7F) << shift
            shift += 7
            if b & 0x80 == 0:
                break
        await reader.readexactly(length)
        await reader.readexactly(2)
        body = json.dumps({
            "version": {"name": "Paper 1.20.4", "protocol": 765},
            "players": {"max": 100, "online": 2, "sample": [
                {"name": "Steve", "id": "u1"}, {"name": "Alex", "id": "u2"},
            ]},
            "description": {"text": {"text": "直连测试服"}},
        }).encode("utf-8")
        payload = b"\x00" + _mc_varint_enc36(len(body)) + body
        writer.write(_mc_varint_enc36(len(payload)) + payload)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def _fake_mc_server_nosample36(reader, writer):
    """sample 留空但 online>0：验证按「仅人数」降级渲染。"""
    try:
        length = 0
        shift = 0
        while True:
            b = (await reader.readexactly(1))[0]
            length |= (b & 0x7F) << shift
            shift += 7
            if b & 0x80 == 0:
                break
        await reader.readexactly(length)
        await reader.readexactly(2)
        body = json.dumps({
            "version": {"name": "Paper 1.20.4", "protocol": 765},
            "players": {"max": 100, "online": 5},
            "description": {"text": ""},
        }).encode("utf-8")
        payload = b"\x00" + _mc_varint_enc36(len(body)) + body
        writer.write(_mc_varint_enc36(len(payload)) + payload)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def _direct_e2e36():
    server = await _asyncio36.start_server(_fake_mc_server36, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        _h36 = _CH36(None, None, _IR36())
        out = await _h36.handle_direct_status("127.0.0.1", port)
        assert "127.0.0.1:%d" % port in out and "Paper 1.20.4" in out, out
        assert "2/100" in out and "直连测试服" in out and "ms" in out, out
        assert "Steve" in out and "Alex" in out, out
        out = await _h36.handle_direct_list("127.0.0.1", port)
        assert "在线查询" in out and "2 人" in out and "Steve" in out, out
        # 直连列表与配置内渲染同一套取数语义：source=slp 标注（在线查询）
    finally:
        server.close()
        await server.wait_closed()

    # sample 为空 + online>0 → 降级「仅人数」，不谎报名单
    server2 = await _asyncio36.start_server(_fake_mc_server_nosample36, "127.0.0.1", 0)
    port2 = server2.sockets[0].getsockname()[1]
    try:
        _h36b = _CH36(None, None, _IR36())
        out = await _h36b.handle_direct_list("127.0.0.1", port2)
        assert "5/100" in out and "未返回玩家名" in out, out
        out = await _h36b.handle_direct_status("127.0.0.1", port2)
        assert "5/100" in out and "玩家" not in out, "sample 空时状态不展示玩家行"
    finally:
        server2.close()
        await server2.wait_closed()

    # 无法连接 → 明确报错（不走配置内服务器）
    out = await _h36.handle_direct_status("127.0.0.1", 1)
    assert "无法连接服务器 127.0.0.1:1" in out, out
    out = await _h36.handle_direct_list("127.0.0.1", 1)
    assert "无法获取服务器 127.0.0.1:1" in out, out
_asyncio36.run(_direct_e2e36())

print("OK  地址解析(IPv4/域名/端口/IPv6/编号不误判) / 直连状态与玩家列表渲染(带 sample) / "
      "sample 空降级仅人数 / 连接失败明确报错")

print("\n=== 37. 实时采样互斥：sample_now 与正常周期不并发（跳过堆积） ===")
import asyncio as _asyncio37
from astrbot_plugin_minecraft_queqiao.services.monitor import MonitorCollector as _MC37

_mdir37 = pathlib.Path("/tmp/queqiao_test_monitor37")
if _mdir37.exists():
    _shutil35.rmtree(_mdir37)
_mdir37.mkdir(parents=True, exist_ok=True)
_sm37 = _SM35()
_sm37.add("Srv", _FakeInst35(
    connected=True, rcon_out="TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0"))
_col37 = _MC37(_mdir37, _sm37)
_col37._ping = _fake_ping_ok35


async def _mutex37():
    # 以 enabled=False 启动：_loop 空转（sleep 60），采样轮次完全由
    # sample_now 手动控制，排除后台任务并发干扰（sample_now 不检查 enabled）
    _col37.start({"Srv": _SC35.from_dict(
        {"monitor": {"enabled": False}})})
    _col37.apply_settings("Srv", {"ping_host": "mc.example.com", "realtime_interval": 1})
    # (a) 锁空闲：sample_now 正常采样一次
    st = await _col37.sample_now("Srv")
    assert st is not None and st["sample_count"] == 1, st
    assert st["realtime_interval"] == 1, "设置里的实时频率应透传"
    # (b) 锁被占用（模拟上一轮采样未完成 / 正常周期正在采）：跳过本次、
    #     快速返回当前状态，sample_count 不得增加——实时高频不堆积
    lock = _col37._lock_for("Srv")
    await lock.acquire()
    try:
        st2 = await _col37.sample_now("Srv")
        assert st2 is not None and st2["sample_count"] == 1, \
            "锁占用时跳过采样，sample_count 不得增加"
    finally:
        lock.release()
    # (c) 释放后恢复采样
    st3 = await _col37.sample_now("Srv")
    assert st3["sample_count"] == 2, st3
_asyncio37.run(_mutex37())
print("OK  锁空闲正常采样 / 锁占用跳过不堆积 / 释放后恢复 / 实时频率设置透传")

print("\n=== 38. 实时采样后端常驻任务（与正常周期同架构） ===")
import asyncio as _asyncio38
from astrbot_plugin_minecraft_queqiao.services.monitor import MonitorCollector as _MC38
from astrbot_plugin_minecraft_queqiao.services.monitor import MonitorSample as _MS38
import time as _time38

_mdir38 = pathlib.Path("/tmp/queqiao_test_monitor38")
if _mdir38.exists():
    _shutil35.rmtree(_mdir38)
_mdir38.mkdir(parents=True, exist_ok=True)
_sm38 = _SM35()
_sm38.add("Srv", _FakeInst35(
    connected=True, rcon_out="TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0"))
_col38 = _MC38(_mdir38, _sm38)
_col38._ping = _fake_ping_ok35


async def _rt38():
    # enabled=False 启动：实时任务常驻但空转（与 _loop 同架构）
    _col38.start({"Srv": _SC35.from_dict({"monitor": {"enabled": False}})})
    assert "Srv" in _col38._realtime_tasks and not _col38._realtime_tasks["Srv"].done(), \
        "实时采样任务应随 start 常驻"
    # 与正常周期共用同一把互斥锁（严格串行）
    assert _col38._lock_for("Srv") is _col38._lock_for("Srv")
    # realtime_interval 改动即时生效（任务循环内实时读取）
    _col38.apply_settings("Srv", {"enabled": True, "ping_host": "mc.example.com",
                                  "realtime_interval": 3})
    assert _col38.status("Srv")["realtime_interval"] == 3
    # 等后端实时任务自动采样（3s 间隔，最多等 7s）——不依赖任何前端循环
    for _ in range(7):
        await asyncio.sleep(1)
        if _col38.store.sample_count("Srv") > 0:
            break
    assert _col38.store.sample_count("Srv") > 0, "后端实时任务应在开启后自动采样"
    # 固定间隔调度：采样耗时被单调时钟补偿，相邻样本间隔 ≈ realtime_interval
    # （此前「采样+等待」的实际周期 = 采样耗时 + interval，60 秒窗口样本数
    # 永远到不了周期数，如 1s 设置 → 1.18s 实际周期 → 窗口约 51 个样本）
    _col38.apply_settings("Srv", {"realtime_interval": 1})
    _before38 = _col38.store.sample_count("Srv")
    for _ in range(8):
        await asyncio.sleep(1)
        if _col38.store.sample_count("Srv") >= _before38 + 4:
            break
    _recent38 = _col38.store._read_since("Srv", _time38.time() - 30)
    _gaps38 = [b.ts - a.ts for a, b in zip(_recent38, _recent38[1:])]
    _med38 = sorted(_gaps38)[len(_gaps38) // 2] if _gaps38 else 0.0
    assert 0.6 < _med38 < 1.2, \
        f"固定间隔调度应≈1s（旧行为≈1.18s），实际中位间隔 {_med38:.2f}s"
    # 尾部扫描（高频采样优化）：只返回 since_ts 之后的样本且保持旧→新
    _srv_dir = _mdir38 / "Srv"
    _srv_dir.mkdir(parents=True, exist_ok=True)
    _p38 = _srv_dir / (_time38.strftime("%Y-%m-%d") + ".jsonl")
    _base38 = _time38.time()
    with open(_p38, "a", encoding="utf-8") as _h38:
        for _i in range(2000):
            _h38.write(json.dumps({"ts": round(_base38 - 120 + _i * 0.06, 3),
                                   "online": 1, "tps1": 20.0, "tps5": None,
                                   "tps15": None, "latency_ms": 50.0}) + "\n")
    _since38 = _base38 - 60
    _tail38 = _col38.store._iter_tail_since(_p38, _since38)
    assert len(_tail38) > 0 and all(s.ts >= _since38 for s in _tail38), \
        "尾部扫描应只返回窗口内样本"
    assert _tail38 == sorted(_tail38, key=lambda s: s.ts), "尾部扫描输出应为旧→新"
    # 关停：正常 + 实时任务全部取消
    await _col38.stop()
    assert not _col38._realtime_tasks and not _col38._tasks


_asyncio38.run(_rt38())
print("OK  实时任务随 start 常驻 / 与正常周期同锁串行 / 设置即时生效 / 自动采样 / 尾部扫描窗口过滤与排序 / stop 全量取消")

print("\n=== 39. 面板级偏好长期存储（后端 panel_prefs.json） ===")
from astrbot_plugin_minecraft_queqiao.services.panel_prefs import PanelPrefsStore as _PP39

_mdir39 = pathlib.Path("/tmp/queqiao_test_prefs39")
if _mdir39.exists():
    _shutil35.rmtree(_mdir39)
_mdir39.mkdir(parents=True, exist_ok=True)
_pp39 = _PP39(_mdir39)
_pp39.update({"terminal_days": 5})
assert _pp39.get("terminal_days") == 5
assert _pp39.all() == {"terminal_days": 5}
# 重新加载（模拟插件重启）后仍在：权威数据落盘，不依赖浏览器 localStorage
_pp39b = _PP39(_mdir39)
assert _pp39b.get("terminal_days") == 5, "面板偏好应持久化到磁盘"

# Web API：注入 panel_prefs 的控制器提供 /panel/prefs 读写
_wac39 = _WAC35(_ctx35, _sm35, None, None, None,
                {"Srv": _cfg35_on}, None, None, _pp39b)
_res_prefs39 = _wac39.get_panel_prefs()  # 同步方法，直接调用
assert _res_prefs39["data"]["prefs"]["terminal_days"] == 5
# 合并写入 + 钳制：-1 → 0，99 → 30
_orig_json39 = _wa35.request.json
async def _fake_json_prefs39_a(default=None): return {"terminal_days": -1}
_wa35.request.json = _fake_json_prefs39_a
assert _asyncio35.run(_wac39.set_panel_prefs())["data"]["prefs"]["terminal_days"] == 0
async def _fake_json_prefs39_b(default=None): return {"terminal_days": 99}
_wa35.request.json = _fake_json_prefs39_b
assert _asyncio35.run(_wac39.set_panel_prefs())["data"]["prefs"]["terminal_days"] == 30
async def _fake_json_prefs39_c(default=None): return {"terminal_days": "abc"}
_wa35.request.json = _fake_json_prefs39_c
assert _asyncio35.run(_wac39.set_panel_prefs())["status_code"] == 400
async def _fake_json_prefs39_d(default=None): return {}
_wa35.request.json = _fake_json_prefs39_d
# 空字段：返回现有偏好不落盘
assert _asyncio35.run(_wac39.set_panel_prefs())["data"]["prefs"]["terminal_days"] == 30
# auto_refresh：布尔落盘、字符串 true/false 解析、非法值拒绝
async def _fake_json_prefs39_e(default=None): return {"auto_refresh": True}
_wa35.request.json = _fake_json_prefs39_e
assert _asyncio35.run(_wac39.set_panel_prefs())["data"]["prefs"]["auto_refresh"] is True
async def _fake_json_prefs39_f(default=None): return {"auto_refresh": "false"}
_wa35.request.json = _fake_json_prefs39_f
assert _asyncio35.run(_wac39.set_panel_prefs())["data"]["prefs"]["auto_refresh"] is False
async def _fake_json_prefs39_g(default=None): return {"auto_refresh": "yes"}
_wa35.request.json = _fake_json_prefs39_g
assert _asyncio35.run(_wac39.set_panel_prefs())["status_code"] == 400
_wa35.request.json = _orig_json39
# 重启后仍为最后一次合法值
assert _PP39(_mdir39).get("terminal_days") == 30
assert _PP39(_mdir39).get("auto_refresh") is False
print("OK  存储落盘重启可读 / GET 合并写入 / terminal_days 钳制与非法拒绝 / auto_refresh 布尔与非法拒绝 / 空字段不落盘")

print("\n=== 40. 清除监控采集数据（store.clear + Web API） ===")
_mdir40 = pathlib.Path("/tmp/queqiao_test_monitor40")
if _mdir40.exists():
    _shutil35.rmtree(_mdir40)
_mdir40.mkdir(parents=True, exist_ok=True)
_sm40 = _SM35()
_sm40.add("Srv", _FakeInst35(
    connected=True, rcon_out="TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0"))
_col40 = _MC38(_mdir40, _sm40)
_col40._ping = _fake_ping_ok35
# 直接写 6 条采样（绕开任务竞争），验证 clear 计数与文件删除
for _i in range(6):
    _col40.store.append("Srv", _MS38(
        ts=_time38.time() - 60 + _i, online=1, tps1=19.0, tps5=None,
        tps15=None, latency_ms=50.0))
assert _col40.store.sample_count("Srv") == 6
_removed40 = _col40.clear_data("Srv")
assert _removed40 == 6, f"clear 应返回删除条数 6, 实际 {_removed40}"
assert _col40.store.sample_count("Srv") == 0, "清除后计数归零"
assert _col40.store.latest("Srv") is None, "清除后最新采样清空"
_srv_dir40 = _mdir40 / "monitor" / "Srv"
assert not list(_srv_dir40.glob("*.jsonl")), "清除后分片文件应删除"
assert _col40.status("Srv")["last_error"] is None, "清除后最近错误重置"
# 采集任务继续：再写一条，计数从 1 重新累计（模拟下一轮采样）
_col40.store.append("Srv", _MS38(
    ts=_time38.time(), online=1, tps1=20.0, tps5=None, tps15=None, latency_ms=51.0))
assert _col40.store.sample_count("Srv") == 1, "清除后从零重新累计"

# Web API 路由
_wac40 = _WAC35(_ctx35, _sm35, None, None, None,
                {"Srv": _cfg35_on}, None, _col40)
_res_clear40 = _asyncio35.run(_wac40.clear_monitor_data("Srv"))
assert _res_clear40["data"]["success"] is True
assert _res_clear40["data"]["removed"] == 1, "Web API 返回本次删除条数"
assert _asyncio35.run(_wac40.clear_monitor_data("ghost"))["status_code"] == 404
print("OK  计数/最新值/分片全清 / 错误重置 / 删除后从零重采 / Web API 返回删除条数与 404 校验")

print("\n=== 41. 实时窗口样本数稳定（60 秒窗口 = 最近 60 个点） ===")
_mdir41 = pathlib.Path("/tmp/queqiao_test_monitor41")
if _mdir41.exists():
    _shutil35.rmtree(_mdir41)
_mdir41.mkdir(parents=True, exist_ok=True)
_col41 = _MC38(_mdir41, _SM35())
_base41 = _time38.time()
# 61 个每秒点落在 60 秒窗口（含边界）：cap=60 后稳定 60
for _i in range(61):
    _col41.store.append("Srv", _MS38(
        ts=_base41 - 60 + _i, online=1, tps1=20.0, tps5=None,
        tps15=None, latency_ms=50.0))
_s41 = _col41.store.series("Srv", _base41 - 60, 1, cap_seconds=60)
assert _s41["latency"]["summary"]["count"] == 60, "60 秒窗口应稳定 60 个点"
assert len(_s41["latency"]["points"]) == 60, "曲线应 60 个桶"
assert _s41["latency"]["points"][0]["ts"] == int(_base41 - 60) + 1, "截断应保留最近 60 个点"
# 不足上限（采样慢/刚启动）时不截断：30 个样本（首条恰等于 since 边界，
# 应被 >= 语义包含）
_col41.store.clear("Srv")
for _i in range(30):
    _col41.store.append("Srv", _MS38(
        ts=_base41 - 30 + _i, online=1, tps1=19.0, tps5=None,
        tps15=None, latency_ms=49.0))
_raw41b = _col41.store._read_since("Srv", _base41 - 30)
assert len(_raw41b) == 30, "read_since 应含边界样本 30 条, 实际 %d" % len(_raw41b)
_s41b = _col41.store.series("Srv", _base41 - 30, 1, cap_seconds=60)
assert _s41b["latency"]["summary"]["count"] == 30, "样本不足上限时不截断"
# 正常长窗口（24h、cap=86400）不受影响
assert _col41.store.series("Srv", _base41 - 3600, 600, cap_seconds=86400)["latency"]["summary"]["count"] == 30
print("OK  61→稳定60 / 不足上限不截断 / 长窗口cap不误伤")

print("\n=== 42. 连接层运行观测（runtime_stats / 重连回调 / 超时计数 / API 暴露） ===")
from astrbot_plugin_minecraft_queqiao.core.queqiao_client import (
    QueQiaoClient as _QC42, QueQiaoTimeout as _QTO42,
    SharedReverseServer as _SRS42, reverse_servers_snapshot as _rss42,
)
from astrbot_plugin_minecraft_queqiao.core.server_manager import ServerManager as _SM42
from astrbot_plugin_minecraft_queqiao.services.metrics import MetricsCollector as _Metrics42

# (a) runtime_stats 字段齐全且只读反映内部状态
_cfg42 = _SC35.from_dict({"server": {"server_name": "Srv42", "ws_mode": "forward"},
    "reconnect": {"max_reconnect": 3, "reconnect_interval": 1}})
_qc42 = _QC42(_cfg42)
_s42 = _qc42.runtime_stats
assert _s42["connected"] is False and _s42["retry_count"] == 0
assert _s42["reconnect_stage"] == "" and _s42["reconnect_exhausted"] is False
assert _s42["pending_api_calls"] == 0 and _s42["api_timeouts"] == 0
assert _s42["last_disconnect_reason"] == ""
_qc42._retries = 5
_qc42._last_reconnect_stage = "低频"
_qc42._api_timeouts = 3
_qc42._pending["echo-x"] = object()  # len 只看长度，类型无关
_s42b = _qc42.runtime_stats
assert _s42b["retry_count"] == 5 and _s42b["reconnect_stage"] == "低频"
assert _s42b["pending_api_calls"] == 1 and _s42b["api_timeouts"] == 3

# (b) _backoff 触发 on_reconnect：退避段（threshold=0 关闭低频）且记录阶段
_ev42 = []
async def _onrc42(attempt, stage):
    _ev42.append((attempt, stage))
async def _fake_sleep42(*a, **k):
    return None
_cfg42b = _SC35.from_dict({"server": {"server_name": "Srv42b", "ws_mode": "forward"},
    "reconnect": {"reconnect_interval": 1, "low_frequency_threshold": 0}})
_qc42b = _QC42(_cfg42b, on_reconnect=_onrc42)
_qc42b._retries = 1
_orig_sleep42 = asyncio.sleep
asyncio.sleep = _fake_sleep42
asyncio.run(_qc42b._backoff())
assert _qc42b._retries == 2, f"退避段 retries 应 +1, 实际 {_qc42b._retries}"
assert _ev42 == [(2, "退避")], _ev42
assert _qc42b.runtime_stats["reconnect_stage"] == "退避"
assert _qc42b.runtime_stats["reconnect_exhausted"] is False

# (c) 达上限：max_reconnect=3，第 4 次停止并回调 stage=上限
_qc42c = _QC42(_cfg42, on_reconnect=_onrc42)
_qc42c._retries = 3
asyncio.run(_qc42c._backoff())
assert _qc42c._reconnect_exhausted is True and _qc42c._running is False
assert _ev42[-1] == (4, "上限"), _ev42
assert _qc42c.runtime_stats["reconnect_exhausted"] is True
asyncio.sleep = _orig_sleep42

# (d) call_api 超时 → api_timeouts+1 且仍抛 QueQiaoTimeout（禁止据此重发）
_qc42d = _QC42(_cfg42)
_qc42d._connected = True
async def _fake_send42d(payload):
    return True
_qc42d._send = _fake_send42d
_to42 = False
try:
    asyncio.run(_qc42d.call_api("broadcast", {"message": [{"text": "x"}]}, timeout=0.01))
except _QTO42:
    _to42 = True
assert _to42, "超时应抛 QueQiaoTimeout（语义：禁止据此重发）"
assert _qc42d.runtime_stats["api_timeouts"] == 1, "超时应累计 api_timeouts"
assert _qc42d.runtime_stats["pending_api_calls"] == 0, "超时后未决请求应清理"

# (e) Web API：/stats 重连汇总 + /servers 单服 client 观测字段
_sm42 = _SM42()
_sm42.add(_cfg42)  # Srv42：断线且重连中
_inst42 = _sm42.get("Srv42")
_inst42.client._retries = 2
_inst42.client._last_reconnect_stage = "退避"
_cfg42x = _SC35.from_dict({"server": {"server_name": "Srv42x", "ws_mode": "forward"},
    "reconnect": {"max_reconnect": 1}})
_sm42.add(_cfg42x)  # Srv42x：已达上限
_inst42x = _sm42.get("Srv42x")
_inst42x.client._reconnect_exhausted = True
_m42 = _Metrics42()
_wac42 = _WAC35(_ctx35, _sm42, None, None, _m42, {"Srv42": _cfg42}, None, None)
_r42 = asyncio.run(_wac42.get_stats())
assert _r42["data"]["total_servers"] == 2, _r42["data"]
assert _r42["data"]["reconnecting_servers"] == 1, _r42["data"]
assert _r42["data"]["exhausted_servers"] == 1, _r42["data"]
_r42s = asyncio.run(_wac42.get_servers())
_srv42s = [s for s in _r42s["data"]["servers"] if s["server_name"] == "Srv42"]
assert len(_srv42s) == 1, _r42s["data"]
assert _srv42s[0]["client"]["retry_count"] == 2
assert _srv42s[0]["client"]["reconnect_stage"] == "退避"
assert _srv42s[0]["client"]["reconnect_exhausted"] is False
assert _srv42s[0]["client"]["api_timeouts"] == 0

# (f) 反向共享 WS 服务端快照：单例 snapshot 与全局只读枚举
assert _rss42() == [], "测试环境不应有反向共享服务端"
_srs42 = _SRS42("127.0.0.1", 9999, "/mc/ws")
_snap42 = _srs42.snapshot()
assert _snap42 == {"host": "127.0.0.1", "port": 9999, "path": "/mc/ws",
                   "running": False, "clients": []}, _snap42
_srs42.register("B", object())
_srs42.register("A", object())
assert _srs42.snapshot()["clients"] == ["A", "B"], "clients 应排序"
_r42r = asyncio.run(_wac42.get_reverse_servers())
assert _r42r["data"]["servers"] == [], "Web API 反向快照应返回空列表"
print("OK  runtime_stats 只读观测 / 退避与上限回调 / 超时计数且禁止重发 / Web API 汇总与反向快照")
