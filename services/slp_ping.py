"""Minecraft 服务端状态协议（Server List Ping）的最小实现（零第三方依赖）。

用于测量**直连服务器**的网络延迟（RTT, ms）——与玩家客户端加入服务器时
看到的 ping 同一测量口径，而不经过鹊桥中转：握手 + 状态请求的往返耗时。

```text
客户端                                 服务端 (TCP, 默认 25565)
  |-- Handshake(next state=1) + Status request -->|
  |<------------------- Status response (JSON) ---|
```

状态响应 JSON 同时带回版本名（含服务端品牌，如 ``forge 1.20.1`` /
``Paper 1.20.4``）、在线/最大人数与 MOTD，供监控侧缓存服务端类型
（TPS 指令 auto 选择）与在线人数。

仅使用标准库（asyncio/struct/zlib），不引入第三方 MC 库依赖。
"""

from __future__ import annotations

import asyncio
import json
import struct
import time
import zlib
from dataclasses import dataclass

# 握手协议版本：-1 表示"未知"，服务端按当前版本兼容处理（免维护版本表）
_PROTOCOL_VERSION = -1
# 握手 next state=1：进入 status 阶段
_NEXT_STATE_STATUS = 1
_STATUS_PACKET_ID = 0x00


@dataclass
class McPingResult:
    """一次 SLP ping 的结果（rtt 为往返耗时毫秒）。"""

    rtt_ms: float
    version_name: str = ""
    online: int = 0
    max_players: int = 0
    description: str = ""


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    value &= 0xFFFFFFFF
    while True:
        if value & ~0x7F == 0:
            out.append(value)
            return bytes(out)
        out.append((value & 0x7F) | 0x80)
        value >>= 7


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """解析 VarInt，返回 (值, 新偏移)。"""
    num = 0
    shift = 0
    for i in range(5):
        if offset + i >= len(data):
            raise ValueError("VarInt 数据不完整")
        byte = data[offset + i]
        num |= (byte & 0x7F) << shift
        shift += 7
        if byte & 0x80 == 0:
            return num, offset + i + 1
    raise ValueError("VarInt 过长")


async def _read_exact(
    reader: asyncio.StreamReader, size: int, timeout: float
) -> bytes:
    data = b""
    while len(data) < size:
        chunk = await asyncio.wait_for(reader.read(size - len(data)), timeout)
        if not chunk:
            raise ConnectionError("连接被服务端关闭")
        data += chunk
    return data


async def _read_varint(reader: asyncio.StreamReader, timeout: float) -> int:
    num = 0
    shift = 0
    for _ in range(5):
        byte = (await _read_exact(reader, 1, timeout))[0]
        num |= (byte & 0x7F) << shift
        shift += 7
        if byte & 0x80 == 0:
            return num
    raise ValueError("VarInt 过长")


async def _read_packet(reader: asyncio.StreamReader, timeout: float) -> bytes:
    """读取一个长度前缀的包；容忍服务端强制压缩（zlib 解压）。"""
    length = await _read_varint(reader, timeout)
    if length < 0:
        compressed = await _read_exact(reader, -length, timeout)
        try:
            return zlib.decompress(compressed)
        except zlib.error:
            raise ConnectionError("压缩包解压失败") from None
    return await _read_exact(reader, length, timeout)


def _component_text(node: object) -> str:
    """把 MOTD（str / {'text': ...} / 组件列表）抽取为纯文本。"""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return _component_text(node.get("text", ""))
    if isinstance(node, list):
        return "".join(_component_text(item) for item in node)
    return str(node)


async def mc_ping(
    host: str, port: int = 25565, timeout: float = 5.0
) -> McPingResult | None:
    """直连服务器执行一次状态查询，返回 RTT 与响应摘要；失败返回 None。

    失败（连接拒绝 / 非 MC 端口 / 超时 / 响应非法）统一返回 None，由调用方
    记录错误状态；超时期间方法自身会被 ``asyncio.wait_for`` 保证终止。
    """
    if not host:
        return None
    started = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout
        )
    except (OSError, asyncio.TimeoutError):
        return None

    try:
        host_bytes = host.encode()
        handshake = (
            b"\x00"
            + _encode_varint(_PROTOCOL_VERSION)
            + _encode_varint(len(host_bytes))
            + host_bytes
            + struct.pack(">H", port)
            + bytes([_NEXT_STATE_STATUS])
        )
        writer.write(_encode_varint(len(handshake)) + handshake)
        writer.write(b"\x01\x00")  # 状态请求包（len=1, id=0）
        await asyncio.wait_for(writer.drain(), timeout)

        data = await asyncio.wait_for(_read_packet(reader, timeout), timeout)
    except (OSError, ConnectionError, ValueError, asyncio.TimeoutError):
        return None
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 1.0)
        except (OSError, asyncio.TimeoutError):
            pass

    rtt_ms = round((time.monotonic() - started) * 1000, 1)
    try:
        _, offset = _decode_varint(data, 0)
        json_len, offset = _decode_varint(data, offset)
        raw = data[offset : offset + json_len]
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return None
    # 严格校验：必须是合法 MC 状态响应（含 version / players 等结构）。
    # 避免把 HTTP 等非 MC 服务（如鹊桥 Web 端口）的响应误判为成功——
    # 那会让延迟显示一个并非游戏端口的假低值
    if not isinstance(payload, dict):
        return None
    if not isinstance(payload.get("version"), dict) and not isinstance(
        payload.get("players"), dict
    ):
        return None

    version = payload.get("version") or {}
    players = payload.get("players") or {}
    return McPingResult(
        rtt_ms=rtt_ms,
        version_name=str(version.get("name") or ""),
        online=int(players.get("online") or 0),
        max_players=int(players.get("max") or 0),
        description=_component_text(payload.get("description", "")),
    )


def brand_from_slp(version_name: str, description: str = "") -> str | None:
    """从状态响应的版本名 / MOTD 中识别服务端品牌，供 TPS 指令 auto 选择。

    返回小写品牌关键字（forge / fabric / quilt / paper / spigot / bukkit /
    purpur / pufferfish / leaves / sponge / folia）；识别不到返回 None。
    """
    text = f"{version_name} {description}".lower()
    for brand in (
        "pufferfish", "purpur", "paper", "spigot", "bukkit", "folia",
        "sponge", "leaves", "fabric", "quilt", "forge",
    ):
        if brand in text:
            return brand
    return None