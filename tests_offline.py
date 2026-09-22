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
_bcfg = _S2.from_dict({"server": {"server_id": "S"},
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
_off = _S2.from_dict({"server": {"server_id": "S"},
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
#     期望显示 [MC]<Steve> 测试空服务器（默认值 MC，而非英文 server_id）
_live = _S3.from_dict({"server": {"server_id": "Server", "server_name": ""},
    "message": {"forward_chat_format": "[{server}]<{player}> {message}"}})
_ev_live = QueQiaoEvent.from_dict({"event_name": "PlayerChatEvent",
    "message": "测试空服务器", "player": {"nickname": "Steve"}})
_live_out = _br4.format_event(_live, _ev_live)
assert _live_out == "[MC]<Steve> 测试空服务器", _live_out
assert "Server" not in _live_out, f"未填显示名称时不应回退成 server_id: {_live_out}"
# 不带字面量方括号时直接得到 [MC] 前缀以外的形态（默认值原样参与格式化）
_live_clean = _S3.from_dict({"server": {"server_id": "Server", "server_name": ""},
    "message": {"forward_chat_format": "{server}<{player}> {message}"}})
assert _br4.format_event(_live_clean, _ev_live) == "MC<Steve> 测试空服务器"
# 默认值可自定义（如改成本服）
_live_dft = _S3.from_dict({"server": {"server_id": "Server", "server_name_default": "本服"},
    "message": {"forward_chat_format": "[{server}]<{player}> {message}"}})
assert _br4.format_event(_live_dft, _ev_live) == "[本服]<Steve> 测试空服务器"
# 想要无前缀：把默认值也显式清空（格式串里的字面量方括号仍由用户自己掌控）
_live_nopfx = _S3.from_dict({"server": {"server_id": "Server", "server_name_default": ""},
    "message": {"forward_chat_format": "{server}<{player}> {message}"}})
assert _br4.format_event(_live_nopfx, _ev_live) == "<Steve> 测试空服务器"
# 填上显示名称后同一条格式串正常带前缀
_live_named = _S3.from_dict({"server": {"server_id": "Server", "server_name": "生存服"},
    "message": {"forward_chat_format": "[{server}]<{player}> {message}"}})
assert _br4.format_event(_live_named, _ev_live) == "[生存服]<Steve> 测试空服务器"
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
    ("cmd", "rcon_enabled"): "rcon_fallback_enabled",
    ("cmd", "rcon_host"): "rcon_host",
    ("cmd", "rcon_port"): "rcon_port",
    ("cmd", "rcon_password"): "rcon_password",
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
_cfgI26 = SC.from_dict({"server": {"server_id": "IMG"},
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
_cfgI26b = SC.from_dict({"server": {"server_id": "IMG"},
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
_cfgI26d = SC.from_dict({"server": {"server_id": "IMG"},
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

_cfg29 = ServerConfig.from_dict({"server": {"server_id": "S29"},
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
_cfg29off = ServerConfig.from_dict({"server": {"server_id": "S29"},
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
    _i = _SI30(_S30.from_dict({"server": {"server_id": "S30"}}))
    _i.client = client; _i.rcon = rcon or _Rcon30()
    return _i

# c1) RCON list 成功 → source=rcon，不再查 SLP
_i1 = _mk_inst30(_Cli30(connected=True,
    rcon_out="There are 2 of a max of 20 players online: A, B"))
_r1 = asyncio.run(_i1.fetch_player_list())
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
print("OK  sample 解析(剥离§/跳畸形) / 渲染含RCON通道细分 / 三层兜底顺序 / 超时不重发降级 SLP")

print("\n全部离线逻辑校验通过 ✅（含在线玩家三层兜底）")

print("\n=== 31. 多服务器：数字编号指定目标与单服省略 ===")
from astrbot_plugin_minecraft_queqiao.handlers.commands import CommandHandler as _CH31
from astrbot_plugin_minecraft_queqiao.core.models_config import ServerConfig as _SC31
import astrbot_plugin_minecraft_queqiao.handlers.commands as _cmd_mod31
import astrbot_plugin_minecraft_queqiao.core.constants as _c31


class _Inst31:
    """服务器实例桩：含 _resolve_target/_ambiguous_hint 关心的字段。"""
    def __init__(self, sid, name=None, connected=True):
        self.server_id = sid
        self.connected = connected
        cfg = {"server": {"server_id": sid}}
        if name:
            cfg["server"]["server_name"] = name
        self.config = _SC31.from_dict(cfg)


class _SM31:
    """ServerManager 桩：all 返回配置顺序（与 mc servers 一致）。"""
    def __init__(self, insts):
        self._insts = list(insts)
    def get(self, sid):
        for i in self._insts:
            if i.server_id == sid:
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
assert _srv is not None and _srv.server_id == "s1" and _hint is None, (_srv, _hint)
# 单服写编号 1 也行（1 = 那台）
_srv, _hint = _h1._resolve_target(_Ev31(), "1")
assert _srv.server_id == "s1" and _hint is None
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
_srv, _ = _h2._resolve_target(_Ev31(), "1"); assert _srv.server_id == "survival"
_srv, _ = _h2._resolve_target(_Ev31(), "2"); assert _srv.server_id == "creative"
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
assert "mc status [编号]" in _help
assert "mc cmd [编号] <指令>" in _help
assert "mc player [编号] <玩家ID>" in _help
assert "数字编号" in _help, "help 应说明多服加编号/单服省略规则"
print("OK  数字编号拆分(仅多服) / 单服省略自动命中 / 多服提示含编号列表 / "
      "死代码已移除 / help 已同步")
