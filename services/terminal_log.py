"""持久化终端日志存储：记录每台服务器的互通动态与网页操作记录。

与 ``MetricsCollector`` 的区别：metrics 是运行期统计（重启清零），本模块把
终端日志落到插件数据目录，供 Web 仪表盘跨会话、跨浏览器恢复历史——网页未
打开期间服务器侧发生的事件同样被记录。仅仪表盘「清屏」操作会删除对应服务器
的记录。

存储按**天分片**：``data_dir/terminal_logs/YYYY-MM-DD.json``，每天一个文件，
避免单个 JSON 文件长期膨胀；超过保留期（默认 30 天）的旧分片自动清理。
每个分片内每台服务器仍有环形上限（300 条/服）。旧版单文件
``terminal_logs.json`` 在启动时自动迁移到当天分片并备份为 ``.bak``。

写盘约束（遵循项目规范）：线程锁保护、utf-8 编码、原子写入（先写 .tmp 再
replace），文件损坏时以空日志继续。
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ..core.constants import PLUGIN_NAME

# 每个分片文件内、每台服务器最多保留的日志条数（环形，超出丢弃最旧）
TERMINAL_LIMIT = 300
# 分片文件保留天数，超出自动删除
TERMINAL_KEEP_DAYS = 30


class TerminalLogStore:
    """按服务器维度、按天分片持久化的终端日志。"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "terminal_logs"
        self._legacy_file = data_dir / "terminal_logs.json"
        self._lock = threading.Lock()
        # {分片名 "YYYY-MM-DD": {server_name: [entry, ...]}}，按文件名排序即时间序
        self._cache: dict[str, dict[str, list[dict[str, str]]]] = {}

    @staticmethod
    def _today_key() -> str:
        return date.today().strftime("%Y-%m-%d")

    def load(self) -> None:
        """加载全部已有分片；迁移旧版单文件；清理超保留期的分片。"""
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._migrate_legacy_locked()
            for path in sorted(self._dir.glob("*.json")):
                data = self._read_file_locked(path)
                if data:
                    self._cache[path.stem] = data
            self._prune_locked()

    # ---- 内部读写 ----

    def _migrate_legacy_locked(self) -> None:
        """把旧版单文件 terminal_logs.json 并入当天分片并备份为 .bak。"""
        if not self._legacy_file.exists():
            return
        try:
            raw = self._legacy_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError) as exc:
            logger.error(
                f"[{PLUGIN_NAME}] 旧版终端日志文件损坏，跳过迁移: {exc}"
            )
            return

        if isinstance(data, dict):
            key = self._today_key()
            # 以当天已有分片为基础合并，避免覆盖当天已记录的内容
            day = self._read_file_locked(self._dir / f"{key}.json")
            self._cache[key] = day
            for name, entries in data.items():
                if not isinstance(entries, list):
                    continue
                clean = [
                    entry
                    for entry in entries
                    if isinstance(entry, dict)
                    and isinstance(entry.get("message"), str)
                ]
                if not clean:
                    continue
                arr = day.setdefault(str(name), [])
                arr.extend(clean)
                day[str(name)] = arr[-TERMINAL_LIMIT:]
            self._write_file_locked(key, day)

        try:
            self._legacy_file.rename(
                self._legacy_file.with_name("terminal_logs.json.bak")
            )
        except OSError:
            pass

    def _read_file_locked(self, path: Path) -> dict[str, list[dict[str, str]]]:
        """读取单个分片文件，损坏/非预期结构时返回空。"""
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        cleaned: dict[str, list[dict[str, str]]] = {}
        for name, entries in data.items():
            if not isinstance(entries, list):
                continue
            arr = [
                entry
                for entry in entries
                if isinstance(entry, dict) and isinstance(entry.get("message"), str)
            ]
            if arr:
                cleaned[str(name)] = arr[-TERMINAL_LIMIT:]
        return cleaned

    def _write_file_locked(self, key: str, data: dict[str, Any]) -> None:
        """原子写入某天分片。"""
        path = self._dir / f"{key}.json"
        tmp = self._dir / f"{key}.json.tmp"
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            logger.error(f"[{PLUGIN_NAME}] 保存终端日志分片失败: {path}: {exc}")

    def _remove_file_locked(self, key: str) -> None:
        try:
            (self._dir / f"{key}.json").unlink(missing_ok=True)
        except OSError:
            pass

    def _prune_locked(self) -> None:
        """删除超过保留天数的旧分片（含内存缓存）。"""
        keep_from = date.today() - timedelta(days=TERMINAL_KEEP_DAYS)
        for path in list(self._dir.glob("*.json")):
            try:
                file_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if file_date < keep_from:
                path.unlink(missing_ok=True)
                self._cache.pop(path.stem, None)

    # ---- 对外接口 ----

    def append(self, server_name: str, type_: str, message: str) -> None:
        """追加一条日志到当天分片（自动落盘），无服务器名时忽略。"""
        if not server_name:
            return
        entry: dict[str, str] = {
            "time": time.strftime("%m-%d %H:%M:%S"),
            "type": type_,
            "message": str(message)[:200],
        }
        with self._lock:
            key = self._today_key()
            if key not in self._cache:
                # 跨天后顺手清理一次超期分片
                self._prune_locked()
            day = self._cache.setdefault(key, {})
            arr = day.setdefault(server_name, [])
            arr.append(entry)
            if len(arr) > TERMINAL_LIMIT:
                del arr[: len(arr) - TERMINAL_LIMIT]
            self._write_file_locked(key, day)

    def get(self, server_name: str, days: int | None = None) -> list[dict[str, str]]:
        """获取某台服务器的日志（旧 → 新，跨分片按日期合并）。

        `days` 为 None 时返回全部保留分片；为正整数时只返回**最近 N 天**
        的分片（含当天），用于终端默认只展示最近几天的历史。
        """
        with self._lock:
            keys = sorted(self._cache)
            if days is not None and days > 0:
                keys = keys[-days:]
            out: list[dict[str, str]] = []
            for key in keys:
                out.extend(self._cache[key].get(server_name, []))
            return out

    def clear(self, server_name: str) -> None:
        """删除某台服务器在**所有分片**中的日志并落盘（仅清屏调用）。

        清空后的分片文件会被删除，避免留下空文件。
        """
        with self._lock:
            for key in list(self._cache):
                day = self._cache[key]
                if server_name not in day:
                    continue
                del day[server_name]
                if day:
                    self._write_file_locked(key, day)
                else:
                    self._remove_file_locked(key)
                    self._cache.pop(key, None)

    def to_dict(self) -> dict[str, Any]:
        """导出全部日志（跨分片合并，供测试/调试）。"""
        with self._lock:
            out: dict[str, list[dict[str, str]]] = {}
            for key in sorted(self._cache):
                for name, arr in self._cache[key].items():
                    out.setdefault(name, []).extend(arr)
            return out
