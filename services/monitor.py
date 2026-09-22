"""服务器性能监控：TPS 与延迟（直连 SLP ping）的长时间采样、持久化与聚合分析。

设计要点：
1. **数据源**：
   - TPS：经 RCON 执行 TPS 指令（默认 ``auto``，按 SLP 识别到的服务端品牌
     自动选择：Forge → ``forge tps``，Fabric/Quilt → ``spark tps``，Bukkit
     系 → ``tps``）并解析三档值（1m / 5m / 15m）。执行走
     ``execute_command_with_channel``，自动继承「鹊桥 RCON → 直连 RCON」兜底
     与「超时 ≠ 失败，禁止重发」语义。
   - 延迟：**直连服务器**执行 Minecraft SLP ping（服务端状态协议握手 + 状态
     请求往返，ms）——与玩家客户端看到的延迟同一测量口径，不经鹊桥中转，
     无需服务端安装任何插件、无需 RCON。目标地址默认取配置 ``ws_url`` 的
     主机（正向模式鹊桥与 MC 服务器同机），端口默认 25565，可在仪表盘设置。
2. **持久化**：按天分片 JSONL（``data_dir/monitor/<server>/YYYY-MM-DD.jsonl``），
   逐行追加采样，天然支持长时间监控；保留天数可配，超期自动清理。
3. **聚合分析**：按时间桶（bucket）求均值/最小/最大/采样数，全量求
   均值/最低/最高/P95 摘要，供仪表盘趋势图与统计卡。
4. **并发约束**：存储线程锁保护；采集循环每服一个 asyncio task，
   采样失败只记错误不断链；TPS（RCON）与延迟（SLP）并行采样，互不拖累。
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from astrbot.api import logger

from ..core.constants import (
    DEFAULT_MONITOR_AUTO_REFRESH,
    DEFAULT_MONITOR_INTERVAL,
    DEFAULT_MONITOR_PING_PORT,
    DEFAULT_MONITOR_REALTIME_INTERVAL,
    DEFAULT_MONITOR_RETENTION_DAYS,
    DEFAULT_MONITOR_TPS_COMMAND,
    MONITOR_API_TIMEOUT,
    MONITOR_AUTO_REFRESH_MAX,
    MONITOR_AUTO_REFRESH_MIN,
    MONITOR_MIN_INTERVAL,
    MONITOR_REALTIME_MAX,
    MONITOR_REALTIME_MIN,
    PLUGIN_NAME,
)
from ..core.models_config import ServerConfig
from .slp_ping import brand_from_slp, mc_ping

if TYPE_CHECKING:
    from ..core.server_manager import ServerManager

# TPS 标准输出：`TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0`
# Paper/Spigot/spark 均含该行；前缀可能带颜色代码或其它装饰
_TPS_RE = re.compile(
    r"TPS from last 1m, 5m, 15m:\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)",
    re.IGNORECASE,
)
# 兜底：无前缀的旧版输出（行内恰好三个逗号分隔的浮点数），但必须处于
# TPS 语境，避免把玩家名/其它数字行误判为 TPS
_TPS_BARE_RE = re.compile(r"([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)")
# server_name 转安全文件名：仅保留字母数字、_、-、.，其余替换为 _
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.\-]+")

# 可聚合的指标键（series 的 metric 参数取值）
METRIC_TPS = "tps"  # 1m 档
METRIC_TPS_5M = "tps5m"
METRIC_TPS_15M = "tps15m"
METRIC_LATENCY = "latency"
MONITOR_METRICS = (METRIC_TPS, METRIC_TPS_5M, METRIC_TPS_15M, METRIC_LATENCY)


def parse_tps(output: str | None) -> tuple[float, float, float] | None:
    """解析服务端 tps 指令输出为 ``(1m, 5m, 15m)``；无法解析返回 None。

    兼容格式：
    - Paper/Spigot：``TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0``
    - spark：前缀带装饰（如 ``⏱  TPS from last...``），同一正则命中
    - 旧版裸三数（前提是行内含 "TPS" 字样，避免误伤其它输出）
    - 原版端 ``Unknown command`` / 指令被拒 → None
    """
    if not output:
        return None
    text = output.strip()
    matched = _TPS_RE.search(text)
    if matched:
        return tuple(float(group) for group in matched.groups())
    if "TPS" in text.upper():
        bare = _TPS_BARE_RE.search(text)
        if bare:
            return tuple(float(group) for group in bare.groups())
    return None


def safe_server_name(server_name: str) -> str:
    """把 server_name 转为安全的目录/文件名（保留可读性，避免路径注入）。"""
    cleaned = _SAFE_NAME_RE.sub("_", server_name or "").strip("._")
    return cleaned or "server"


# 布克特系服务端品牌：均原生支持 tps 指令
_BUKKIT_BRANDS = (
    "paper", "spigot", "bukkit", "purpur", "pufferfish", "leaves",
    "sponge", "folia",
)


def resolve_tps_command(server_type: str | None, preference: str) -> str:
    """解析最终要执行的 TPS 指令。

    ``preference`` 为 ``auto``/空时按 ``server_type``（get_status 返回的
    服务端核心，如 ``forge 1.20.1``、``Paper 1.20.4``）自动选择：
    - Forge → ``forge tps``（Forge 自带指令）
    - Fabric/Quilt → ``spark tps``（无内置 tps 指令，须装 Spark 模组）
    - Paper/Spigot/Bukkit 等布克特系 → ``tps``
    - 未知/无缓存 → ``tps``（默认尝试，解析失败时状态行会提示）
    显式填写具体指令时固定使用，不受服务端类型影响。
    """
    pref = (preference or "").strip()
    if pref and pref.lower() != "auto":
        return pref
    if server_type:
        brand = server_type.lower()
        if "forge" in brand:
            return "forge tps"
        if "fabric" in brand or "quilt" in brand:
            return "spark tps"
        if any(key in brand for key in _BUKKIT_BRANDS):
            return "tps"
    # auto 且未识别出类型：默认尝试 Bukkit 系 tps（覆盖面最广，失败会在状态行提示）
    return "tps"


@dataclass
class MonitorSample:
    """单次性能采样。

    ``tps1/tps5/tps15`` 为 tps 指令的三档值（可能部分为 None，如旧版只回一档）；
    ``latency_ms`` 为 get_status API 往返耗时；字段缺失时保持 None（本次未采到）。
    """

    ts: float
    online: int = 0
    tps1: float | None = None
    tps5: float | None = None
    tps15: float | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": round(self.ts, 3),
            "online": self.online,
            "tps1": self.tps1,
            "tps5": self.tps5,
            "tps15": self.tps15,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MonitorSample | None":
        try:
            ts = float(data.get("ts", 0))
        except (TypeError, ValueError):
            return None
        if ts <= 0:
            return None
        return cls(
            ts=ts,
            online=int(data.get("online", 0) or 0),
            tps1=_opt_float(data.get("tps1")),
            tps5=_opt_float(data.get("tps5")),
            tps15=_opt_float(data.get("tps15")),
            latency_ms=_opt_float(data.get("latency_ms")),
        )


def _opt_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class MonitorSettings:
    """一台服务器在当前生效的监控参数。

    设置入口在仪表盘页面（``POST /monitor/settings``），**不占用 WebUI
    conf schema**；改动经 ``MonitorCollector.apply_settings`` 即时生效并
    持久化到 ``data_dir/monitor/settings.json``。未显式设置过的服务器
    使用代码默认值（默认开启，开箱即用）。

    ``ping_host`` 为延迟探测地址（公网域名/地址，测玩家视角延迟）；
    留空表示不探测延迟（避免把内网互通速度当成玩家延迟）。
    面板打开时默认展示的子页面由 ``default_tab`` 决定（``tps``/``latency``，
    保存在本文件，随设置持久化，不依赖浏览器存储）。
    """

    enabled: bool = True
    interval: int = DEFAULT_MONITOR_INTERVAL
    retention_days: int = DEFAULT_MONITOR_RETENTION_DAYS
    tps_command: str = DEFAULT_MONITOR_TPS_COMMAND
    ping_host: str = ""
    ping_port: int = DEFAULT_MONITOR_PING_PORT
    default_tab: str = "tps"
    realtime_interval: int = DEFAULT_MONITOR_REALTIME_INTERVAL
    auto_refresh_interval: int = DEFAULT_MONITOR_AUTO_REFRESH

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval": self.interval,
            "retention_days": self.retention_days,
            "tps_command": self.tps_command,
            "ping_host": self.ping_host,
            "ping_port": self.ping_port,
            "default_tab": self.default_tab,
            "realtime_interval": self.realtime_interval,
            "auto_refresh_interval": self.auto_refresh_interval,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MonitorSettings":
        data = data or {}
        default_tab = _to_str(data.get("default_tab"), "tps").strip().lower()
        if default_tab not in ("tps", "latency"):
            default_tab = "tps"
        return cls(
            enabled=_to_bool(data.get("enabled"), True),
            interval=max(
                MONITOR_MIN_INTERVAL,
                _to_int(data.get("interval"), DEFAULT_MONITOR_INTERVAL),
            ),
            retention_days=max(
                1, _to_int(data.get("retention_days"), DEFAULT_MONITOR_RETENTION_DAYS)
            ),
            tps_command=(
                _to_str(data.get("tps_command"), DEFAULT_MONITOR_TPS_COMMAND).strip()
                or DEFAULT_MONITOR_TPS_COMMAND
            ),
            ping_host=_to_str(data.get("ping_host"), "").strip(),
            ping_port=max(
                1, _to_int(data.get("ping_port"), DEFAULT_MONITOR_PING_PORT)
            ),
            default_tab=default_tab,
            realtime_interval=max(
                MONITOR_REALTIME_MIN,
                min(
                    MONITOR_REALTIME_MAX,
                    _to_int(data.get("realtime_interval"), DEFAULT_MONITOR_REALTIME_INTERVAL),
                ),
            ),
            auto_refresh_interval=max(
                MONITOR_AUTO_REFRESH_MIN,
                min(
                    MONITOR_AUTO_REFRESH_MAX,
                    _to_int(data.get("auto_refresh_interval"), DEFAULT_MONITOR_AUTO_REFRESH),
                ),
            ),
        )


def _to_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "y", "on"):
            return True
        if lowered in ("0", "false", "no", "n", "off"):
            return False
    return default


def _to_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


def _to_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


class MonitorStore:
    """按天分片持久化的监控时序存储。

    目录布局：``data_dir/monitor/<safe_server>/YYYY-MM-DD.jsonl``。
    追加写采用 JSONL 逐行追加（天然适合时间序列）；读取时容忍坏行
    （进程崩溃可能留下半行）。保留期清理按分片文件日期执行。
    """

    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / "monitor"
        self._lock = threading.Lock()
        # server_name -> 最新采样（供卡片实时展示，避免每次读文件）
        self._latest: dict[str, MonitorSample] = {}
        # server_name -> 累计采样数（内存计数，重启后从分片重建）
        self._counts: dict[str, int] = {}

    # ---- 基础 ----

    def load(self) -> None:
        """初始化存储目录并按分片重建累计计数（最新值由下次采样填充）。"""
        with self._lock:
            try:
                self._root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.error(f"[{PLUGIN_NAME}] 创建监控目录失败: {exc}")
                return
            for server_dir in self._root.iterdir():
                if not server_dir.is_dir():
                    continue
                count = 0
                for path in server_dir.glob("*.jsonl"):
                    for line in self._iter_lines(path):
                        sample = MonitorSample.from_dict(line)
                        if sample is not None:
                            count += 1
                if count:
                    self._counts[server_dir.name] = count

    def _server_dir(self, server_name: str) -> Path:
        return self._root / safe_server_name(server_name)

    def append(self, server_name: str, sample: MonitorSample) -> None:
        """追加一条采样（自动落盘到当天分片）并更新内存最新值。"""
        if not server_name:
            return
        with self._lock:
            server_dir = self._server_dir(server_name)
            try:
                server_dir.mkdir(parents=True, exist_ok=True)
                day_key = datetime.fromtimestamp(sample.ts).strftime("%Y-%m-%d")
                path = server_dir / f"{day_key}.jsonl"
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(sample.to_dict(), ensure_ascii=False) + "\n"
                    )
            except OSError as exc:
                logger.error(
                    f"[{PLUGIN_NAME}][{server_name}] 写入监控采样失败: {exc}"
                )
                return
            self._latest[server_name] = sample
            self._counts[server_name] = self._counts.get(server_name, 0) + 1

    def latest(self, server_name: str) -> MonitorSample | None:
        with self._lock:
            return self._latest.get(server_name)

    def sample_count(self, server_name: str) -> int:
        with self._lock:
            return self._counts.get(server_name, 0)

    # ---- 设置持久化 ----

    def settings(self) -> dict[str, dict[str, Any]]:
        """读取仪表盘保存的监控设置：{server_name: {字段...}}；损坏时返回空。"""
        with self._lock:
            path = self._root / "settings.json"
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, ValueError):
                return {}
            if not isinstance(data, dict):
                return {}
            return {
                str(name): value
                for name, value in data.items()
                if isinstance(value, dict)
            }

    def save_settings(self, data: dict[str, dict[str, Any]]) -> None:
        """原子落盘全部服务器的监控设置。"""
        with self._lock:
            try:
                self._root.mkdir(parents=True, exist_ok=True)
                tmp = self._root / "settings.json.tmp"
                tmp.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                tmp.replace(self._root / "settings.json")
            except OSError as exc:
                logger.error(f"[{PLUGIN_NAME}] 保存监控设置失败: {exc}")

    # ---- 聚合分析 ----

    def series(
        self, server_name: str, since_ts: float, bucket_seconds: int
    ) -> dict[str, dict[str, Any]]:
        """按时间桶聚合时间段内的采样，返回各指标的点序列与统计摘要。

        ``bucket_seconds``：时间桶宽度；每个桶输出该桶内样本的
        均值/最小/最大/采样数（``ts`` 为桶起始时刻）。摘要覆盖
        since 起的全部有效样本：均值/最低/最高/P95/采样数。
        """
        samples = self._read_since(server_name, since_ts)
        result: dict[str, dict[str, Any]] = {}
        for metric in MONITOR_METRICS:
            buckets: dict[int, list[float]] = {}
            all_values: list[float] = []
            for sample in samples:
                value = self._extract(sample, metric)
                if value is None:
                    continue
                all_values.append(value)
                bucket_start = int(sample.ts // bucket_seconds) * bucket_seconds
                buckets.setdefault(bucket_start, []).append(value)
            points = [
                {
                    "ts": bucket_start,
                    "avg": round(sum(values) / len(values), 2),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "count": len(values),
                }
                for bucket_start, values in sorted(buckets.items())
            ]
            result[metric] = {
                "points": points,
                "summary": self._summarize(all_values),
            }
        return result

    @staticmethod
    def _extract(sample: MonitorSample, metric: str) -> float | None:
        if metric == METRIC_TPS:
            return sample.tps1
        if metric == METRIC_TPS_5M:
            return sample.tps5
        if metric == METRIC_TPS_15M:
            return sample.tps15
        if metric == METRIC_LATENCY:
            return sample.latency_ms
        return None

    @staticmethod
    def _summarize(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "avg": None, "min": None, "max": None, "p95": None}
        avg = sum(values) / len(values)
        ordered = sorted(values)
        # P95：升序后取 95% 位置的样本（ceil，至少 1 个），即 95% 的采样不高于该值
        p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
        return {
            "count": len(values),
            "avg": round(avg, 2),
            "min": round(ordered[0], 2),
            "max": round(ordered[-1], 2),
            "p95": round(ordered[p95_index], 2),
        }

    def _read_since(self, server_name: str, since_ts: float) -> list[MonitorSample]:
        """读取某个时刻之后的全部采样（旧 → 新）。"""
        server_dir = self._server_dir(server_name)
        if not server_dir.is_dir():
            return []
        since_date = datetime.fromtimestamp(since_ts).date()
        out: list[MonitorSample] = []
        with self._lock:
            for path in sorted(server_dir.glob("*.jsonl")):
                try:
                    file_date = date.fromisoformat(path.stem)
                except ValueError:
                    continue
                if file_date < since_date:
                    continue
                for line in self._iter_lines(path):
                    sample = MonitorSample.from_dict(line)
                    if sample is not None and sample.ts >= since_ts:
                        out.append(sample)
        out.sort(key=lambda s: s.ts)
        return out

    @staticmethod
    def _iter_lines(path: Path):
        """逐行读取 JSONL，容忍坏行（崩溃残留的半行被跳过）。"""
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        yield json.loads(stripped)
                    except ValueError:
                        continue
        except OSError:
            return

    def prune(self, server_name: str, retention_days: int) -> None:
        """删除早于保留天数的分片文件与对应计数（保留 1 天起步）。"""
        keep_from = date.today() - timedelta(days=max(1, retention_days))
        with self._lock:
            server_dir = self._server_dir(server_name)
            if not server_dir.is_dir():
                return
            for path in list(server_dir.glob("*.jsonl")):
                try:
                    file_date = date.fromisoformat(path.stem)
                except ValueError:
                    path.unlink(missing_ok=True)
                    continue
                if file_date < keep_from:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass


class MonitorCollector:
    """每台服务器一个后台采集任务：定期采样 TPS 与延迟并写入存储。

    生命周期由 ``start()`` / ``stop()`` 管理。监控**参数不占用 WebUI 配置**，
    设置入口在仪表盘（``apply_settings()`` ← ``POST /monitor/settings``），
    改动即时生效并持久化到 ``data_dir/monitor/settings.json``：
    - 采集任务为所有已配置服务器常驻（开销仅为一个 60s 的空转 sleep）；
      ``enabled`` 开关与采集间隔在循环内实时读取，无需重启任务。
    - 采样失败只记录错误状态（``status()`` 可查），不影响循环继续，
      也不影响其它服务器。
    """

    def __init__(self, data_dir: Path, server_manager: "ServerManager") -> None:
        self.store = MonitorStore(data_dir)
        self.server_manager = server_manager
        self._tasks: dict[str, asyncio.Task] = {}
        self._errors: dict[str, str] = {}
        # start 时传入的 server_name -> ServerConfig：延迟探测主机解析等需要
        self._configs: dict[str, ServerConfig] = {}
        # SLP 直连 ping 实现；测试可替换注入
        self._ping = mc_ping
        # server_name -> 最近一次 SLP ping 识别到的服务端品牌（如 "forge"），
        # 供 auto 模式的 TPS 指令解析使用；随时间推移自动更新
        self._server_types: dict[str, str] = {}
        # server_name -> 当前生效参数（持久化设置 > 配置文件字段 > 代码默认）
        self._settings: dict[str, MonitorSettings] = {}

    # ---- 生命周期 ----

    def start(self, configs: dict[str, ServerConfig]) -> None:
        """按服务器初始化监控参数并为每台服务器启动采集任务。

        参数优先级：仪表盘已保存的设置（settings.json）> 配置文件里的
        monitor 分组字段（手动填写）> 代码默认（监控默认开启）。
        """
        self.store.load()
        self._configs = dict(configs)
        saved = self.store.settings()
        for name, config in configs.items():
            base = MonitorSettings(
                enabled=config.monitor_enabled,
                interval=config.monitor_interval,
                retention_days=config.monitor_retention_days,
                tps_command=config.monitor_tps_command,
                # 延迟探测目标：settings 未覆盖时，ping_host 留空表示从
                # 配置的 ws_url 解析主机（正向模式下即 MC 服务器地址）
                ping_host="",
                ping_port=DEFAULT_MONITOR_PING_PORT,
            )
            if name in saved:
                base = MonitorSettings.from_dict(saved[name])
            self._settings[name] = base
            # 启动时顺手清理一次超保留期的历史分片
            self.store.prune(name, base.retention_days)
            if name in self._tasks and not self._tasks[name].done():
                continue
            self._tasks[name] = asyncio.create_task(self._loop(name))
            self._errors.pop(name, None)
            logger.info(
                f"[{PLUGIN_NAME}][{name}] 性能监控任务就绪: "
                f"启用={base.enabled} 间隔 {base.interval}s / 保留 {base.retention_days} 天 / "
                f"TPS 指令 {base.tps_command!r}"
            )

    async def stop(self) -> None:
        """停止全部采集任务。"""
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ---- 运行时设置（来自仪表盘页面，不走 conf schema） ----

    def apply_settings(
        self, server_name: str, fields: dict[str, Any]
    ) -> MonitorSettings | None:
        """合并更新某台服务器的监控参数并落盘；立即生效。

        仅更新 ``fields`` 中出现的字段；``enabled`` 关闭时任务仍常驻
        （循环内跳过采样），重新开启即刻恢复采集，无需重启任务。
        若该服务器此前没有任务（如配置变更后新增），按需启动。
        """
        base = self._settings.get(server_name) or MonitorSettings()
        merged = base.to_dict()
        merged.update(fields)
        updated = MonitorSettings.from_dict(merged)
        self._settings[server_name] = updated

        all_settings = {
            name: settings.to_dict() for name, settings in self._settings.items()
        }
        all_settings[server_name] = updated.to_dict()
        self.store.save_settings(all_settings)

        if server_name not in self._tasks or self._tasks[server_name].done():
            if updated.enabled:
                self._tasks[server_name] = asyncio.create_task(self._loop(server_name))
        logger.info(
            f"[{PLUGIN_NAME}][{server_name}] 监控设置已更新: "
            f"启用={updated.enabled} 间隔 {updated.interval}s / 保留 {updated.retention_days} 天 / "
            f"TPS 指令 {updated.tps_command!r}"
        )
        return updated

    # ---- 采样循环 ----

    async def _loop(self, name: str) -> None:
        while True:
            settings = self._settings.get(name)
            if settings is None or not settings.enabled:
                # 关闭状态：空转等待，随时可被 apply_settings 唤醒（即时生效）
                await asyncio.sleep(60)
                continue
            try:
                await self._sample_once(name, settings)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._errors[name] = f"采样异常: {exc}"
                logger.error(f"[{PLUGIN_NAME}][{name}] 性能监控采样异常: {exc}")
            await asyncio.sleep(max(MONITOR_MIN_INTERVAL, settings.interval))

    async def _sample_once(self, name: str, settings: MonitorSettings) -> None:
        instance = self.server_manager.get(name)
        if instance is None or not instance.connected:
            self._errors[name] = "服务器未连接，跳过本次采样"
            return

        # auto 模式：按最近一次识别到的服务端品牌选指令（首轮无缓存用默认）
        tps_command = resolve_tps_command(
            self._server_types.get(name), settings.tps_command
        )
        # TPS（RCON）与延迟（直连 SLP ping）走不同通道，并行采样互不拖累
        tps_task = asyncio.create_task(self._sample_tps(instance, tps_command))
        lat_task = asyncio.create_task(self._sample_latency(name, settings))
        tps, tps_error = await tps_task
        ping, latency_ms, latency_error = await lat_task

        sample = MonitorSample(
            ts=time.time(),
            online=ping.online if ping else 0,
            tps1=tps[0] if tps else None,
            tps5=tps[1] if tps else None,
            tps15=tps[2] if tps else None,
            latency_ms=latency_ms,
        )
        self.store.append(name, sample)

        error = tps_error or latency_error
        if error:
            self._errors[name] = error
        else:
            self._errors.pop(name, None)

    async def _sample_tps(
        self, instance: Any, tps_command: str
    ) -> tuple[tuple[float, float, float] | None, str | None]:
        """经 RCON 执行 tps 指令并解析；失败返回 (None, 错误描述)。"""
        output, _ = await instance.execute_command_with_channel(tps_command)
        if output is None:
            return None, (
                f"TPS 不可用：{tps_command!r} 执行失败"
                "（需服务端支持该指令且 RCON 通道可用，或指令执行超时）"
            )
        parsed = parse_tps(output)
        if parsed is None:
            return None, f"TPS 输出无法解析: {output[:60]!r}"
        return parsed, None

    def _resolve_ping_target(self, name: str, settings: MonitorSettings) -> tuple[str, int] | None:
        """解析直连延迟探测目标 (host, port)。

        优先使用仪表盘填写的 ``ping_host``（测玩家视角的公网延迟）。输入
        宽容，支持任意常见写法（自动归一化）：

        - 纯域名/地址：``mc.example.com`` / ``8.218.17.111`` → 端口取 ping_port
        - 域名+端口：``mc.example.com:25565`` / ``8.218.17.111:25565``
        - 带协议的完整地址（直接粘贴 ws_url 等）：``http://8.218.17.111:54040/``、
          ``ws://mc.example.com:8080/path`` → 主机与端口从 URL 提取
        - IPv6：``[2001:db8::1]:25565``

        **留空（未配置）返回 None，不探测**——延迟要测的是玩家视角的
        公网往返，回落内网地址只会得到无意义的超低值（127.0.0.1 是鹊桥
        同机地址，不是玩家可达路径）。用户需在「⚙ 设置」显式填写公网
        探测域名/端口后才开始采集延迟。
        """
        host_text = (settings.ping_host or "").strip()
        port = settings.ping_port
        if not host_text:
            return None

        # 显式填写：带协议/路径的完整地址（如粘贴 ws_url）→ 提取主机与端口
        if "://" in host_text:
            parsed = urlparse(host_text)
            host = parsed.hostname or ""
            parsed_port = parsed.port
            if not host:
                return None
            # URL 内显式端口优先于 ping_port（用户填了什么就测什么）
            if parsed_port is not None:
                port = parsed_port
            return host, port
        # 独立填的 host:port（含 IPv6 括号形式）
        if host_text.startswith("["):
            host, _, rest = host_text[1:].partition("]")
            if rest.startswith(":") and rest[1:].isdigit():
                return host, int(rest[1:])
            return host if host else None, port
        if ":" in host_text:
            host, _, rest = host_text.rpartition(":")
            if rest.isdigit() and host:
                return host, int(rest)
        return host_text or None, port

    async def _sample_latency(
        self, name: str, settings: MonitorSettings
    ) -> tuple[Any, float | None, str | None]:
        """直连服务器执行 SLP ping，返回 (ping 结果, RTT ms, 错误)。

        延迟 = 玩家视角的**直连网络延迟**（SLP 握手 + 状态请求往返），
        不经鹊桥中转。成功时顺带缓存服务端品牌（供 auto 模式 TPS 指令
        解析）与在线人数；失败/超时返回 None 并记录错误，不影响 TPS 采样。
        """
        target = self._resolve_ping_target(name, settings)
        if target is None:
            return None, None, (
                "延迟未采到：未配置延迟探测地址"
                "（设置 → 延迟探测域名 里填公网域名/地址）"
            )
        host, port = target
        try:
            ping = await self._ping(host, port, timeout=MONITOR_API_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception:
            return None, None, f"延迟未采到：直连 {host}:{port} 异常"
        if ping is None:
            return None, None, (
                f"延迟未采到：直连 {host}:{port} 失败——连接拒绝/超时，或"
                "响应不是 MC 状态协议（请确认该端口是 MC 游戏端口，且服务端"
                "未禁用状态查询 enable-status=false）"
            )
        brand = brand_from_slp(ping.version_name, ping.description)
        if brand:
            self._server_types[name] = brand
        return ping, ping.rtt_ms, None

    # ---- 状态查询 ----

    async def sample_now(self, name: str) -> dict[str, Any] | None:
        """立即对某台服务器执行一轮采样（不等下一个采集间隔）。

        供仪表盘「⏱ 立即采集」按钮调用：走与定时循环相同的采样路径
        （TPS 与延迟并行），结果写入当天分片；返回该服最新监控状态。
        服务器名未知返回 None（由 Web API 层转 404）。
        """
        if name not in self._settings:
            config = self._configs.get(name)
            if config is None:
                return None
            self._settings[name] = MonitorSettings(
                enabled=config.monitor_enabled,
                interval=config.monitor_interval,
                retention_days=config.monitor_retention_days,
                tps_command=config.monitor_tps_command,
                ping_host="",
                ping_port=DEFAULT_MONITOR_PING_PORT,
            )
        await self._sample_once(name, self._settings[name])
        return self.status(name)

    def status(self, name: str) -> dict[str, Any]:
        """单台服务器的监控状态（当前生效设置 + 最新采样），供 Web API 展示。"""
        settings = self._settings.get(name) or MonitorSettings()
        task = self._tasks.get(name)
        latest = self.store.latest(name)
        server_type = self._server_types.get(name)
        ping_target = self._resolve_ping_target(name, settings)
        return {
            "enabled": settings.enabled,
            "interval": settings.interval,
            "retention_days": settings.retention_days,
            "tps_command": settings.tps_command,
            # auto 模式下实际生效的指令（按已识别到的服务端类型解析）
            "tps_command_resolved": resolve_tps_command(server_type, settings.tps_command),
            "server_type": server_type,
            "ping_host": settings.ping_host,
            "ping_port": settings.ping_port,
            "ping_target": f"{ping_target[0]}:{ping_target[1]}" if ping_target else None,
            "default_tab": settings.default_tab,
            "realtime_interval": settings.realtime_interval,
            "auto_refresh_interval": settings.auto_refresh_interval,
            "running": bool(task and not task.done() and settings.enabled),
            "sample_count": self.store.sample_count(name),
            "last_ts": latest.ts if latest else None,
            "last_error": self._errors.get(name),
            "latest": latest.to_dict() if latest else None,
        }