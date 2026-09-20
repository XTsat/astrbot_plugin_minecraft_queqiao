"""账号绑定服务：维护外部平台账号 ↔ MC 游戏 ID 的映射。

持久化要求（遵循项目规范）：写操作持锁、utf-8 编码、原子写入（先写 .tmp 再 replace）。
"""

import asyncio
import json
from pathlib import Path

from astrbot.api import logger

from ..core.constants import PLUGIN_NAME


class BindingService:
    """绑定关系的读写与持久化。"""

    def __init__(self, data_dir: Path) -> None:
        self._file = data_dir / "bindings.json"
        self._lock = asyncio.Lock()
        # {umo: {game_id: str}}
        self._bindings: dict[str, str] = {}

    def load(self) -> None:
        """从磁盘加载绑定关系，文件损坏时以空表继续。"""
        if not self._file.exists():
            return
        try:
            raw = self._file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError) as exc:
            logger.error(f"[{PLUGIN_NAME}] 读取绑定文件失败，将使用空绑定表: {exc}")
            return

        if isinstance(data, dict):
            self._bindings = {
                str(key): str(value) for key, value in data.items() if value
            }
            logger.info(f"[{PLUGIN_NAME}] 已加载 {len(self._bindings)} 条绑定关系")

    def _save(self) -> None:
        """原子写入：先落临时文件再替换，避免写入中断损坏数据。"""
        tmp = self._file.with_suffix(".json.tmp")
        try:
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(self._bindings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._file)
        except OSError as exc:
            logger.error(f"[{PLUGIN_NAME}] 保存绑定文件失败: {exc}")

    async def bind(self, umo: str, game_id: str) -> None:
        """绑定账号与游戏 ID（重复绑定会覆盖）。"""
        async with self._lock:
            self._bindings[umo] = game_id
            self._save()

    async def unbind(self, umo: str) -> bool:
        """解除绑定，返回是否原本存在绑定。"""
        async with self._lock:
            if umo not in self._bindings:
                return False
            del self._bindings[umo]
            self._save()
            return True

    def get(self, umo: str) -> str:
        """获取某账号绑定的游戏 ID，未绑定时返回空串。"""
        return self._bindings.get(umo, "")
