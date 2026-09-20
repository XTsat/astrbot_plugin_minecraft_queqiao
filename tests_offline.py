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

# 默认配置：互通开、AI 开、两个前缀独立
d = SC.from_dict({})
assert d.enable_ai_chat is True and d.forward_chat_to_astrbot is True
assert d.ai_chat_prefix == "ai" and d.auto_forward_prefix == "*"
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
assert sent2 == ["<A> 大家好"], sent2
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
