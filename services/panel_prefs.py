"""面板级偏好长期存储（替代浏览器 localStorage 作为权威数据源）。

互通终端加载天数等「面板偏好」若只存在浏览器 localStorage：受限 iframe
沙箱可能禁止、清缓存或换设备即丢失。权威数据落盘到后端
``data_dir/panel_prefs.json``（原子写入、线程锁保护），前端 localStorage
仅保留为启动缓存（快速首屏），最终以后端值为准。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from astrbot.api import logger

from ..core.constants import PLUGIN_NAME


class PanelPrefsStore:
    """面板级偏好键值存储：``{key: value}``，合并更新并原子落盘。"""

    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir
        self._path = data_dir / "panel_prefs.json"
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """读取已保存的偏好；文件缺失/损坏时保持空 dict（下次保存重建）。"""
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                self._data = data
        except (OSError, ValueError):
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._save_locked()

    def update(self, fields: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(fields)
            self._save_locked()

    def _save_locked(self) -> None:
        """原子落盘：写临时文件后 rename 替换，避免写一半损坏。"""
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self._path)
        except OSError as exc:
            logger.error(f"[{PLUGIN_NAME}] 保存面板偏好失败: {exc}")