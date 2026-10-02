"""本地翻译服务：把鹊桥传来的翻译键 / 英文文本转成中文。

数据文件（插件 `translations/` 目录，随插件分发，可整体替换/扩充）：
- `translate_zh_cn.json`     翻译键 → 中文（死亡 / 成就 / 实体等，mod 全覆盖）
- `en_zh.json`               原版英文 → 中文（成就名 / 实体名 / 物品名等）
- `death_en_templates.json`  原版死亡消息英文模板（`%1$s` 占位）

翻译优先级（以鹊桥事件的**原始翻译键**为第一证据，英文整句为兜底）：
1. 翻译键查库（死亡 `key`、成就 title 的 `key`）→ 中文模板 + 参数替换
2. 原版英文精确表（`en_zh.json`）
3. 死亡英文整句模板匹配（把 `%n$s` 正则化，提取参数回填中文模板）
4. 全部未命中：回退原文（不报错）

服务端鹊桥已开 `enable_translation` 时事件文本已是中文，此时直接透传，
不再二次翻译（中文含 CJK 字符即跳过）。
"""

import json
import re
from pathlib import Path
from typing import Optional

from ..core.models import QueQiaoAchievement, QueQiaoTranslate

# 以这些前缀开头的参数值本身就是翻译键（arg 携带键而非渲染文本）
_KEY_PREFIXES = (
    "entity.",
    "item.",
    "advancements.",
    "advancement.",
    "death.",
    "block.",
    "enchantment.",
    "container.",
    "stat.",
    "biome.",
    "effect.",
    "potion.",
    "subtitles.",
)

# 中文（CJK 统一表意文字）检测：含中文则视为已翻译文本
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class Translator:
    """线程安全的懒加载翻译器（数据文件只读，加载一次驻留内存）。"""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._data_dir = (
            Path(data_dir)
            if data_dir
            else Path(__file__).resolve().parent.parent / "translations"
        )
        self._key2zh: Optional[dict[str, str]] = None
        self._en2zh: Optional[dict[str, str]] = None
        self._death_templates: Optional[list[tuple[re.Pattern, str]]] = None

    # ---- 懒加载 ----

    def _load_key2zh(self) -> dict[str, str]:
        if self._key2zh is None:
            try:
                with open(self._data_dir / "translate_zh_cn.json", encoding="utf-8") as f:
                    self._key2zh = json.load(f)
            except Exception:
                self._key2zh = {}
        return self._key2zh

    def _load_en2zh(self) -> dict[str, str]:
        if self._en2zh is None:
            try:
                with open(self._data_dir / "en_zh.json", encoding="utf-8") as f:
                    self._en2zh = json.load(f)
            except Exception:
                self._en2zh = {}
        return self._en2zh

    def _load_death_templates(self) -> list[tuple[re.Pattern, str]]:
        """把原版死亡消息英文模板转成正则，命中后回填中文模板。

        英文模板形如 `%1$s was killed by %2$s`：把 `%n$s` 换成捕获组，
        其余部分转义，逐条编译为正则。中文模板保留 `%n$s` 供参数回填。
        """
        if self._death_templates is None:
            templates: list[tuple[re.Pattern, str]] = []
            try:
                with open(
                    self._data_dir / "death_en_templates.json", encoding="utf-8"
                ) as f:
                    raw = json.load(f)
                key2zh = self._load_key2zh()
                for key, en in raw.items():
                    if not isinstance(en, str) or not en:
                        continue
                    zh = key2zh.get(key)
                    if not zh:
                        continue
                    regex = r"^" + re.sub(
                        r"%\d+\\\$s", r"(.*?)", re.escape(en)
                    ) + r"$"
                    try:
                        templates.append((re.compile(regex, re.IGNORECASE), zh))
                    except re.error:
                        continue
            except Exception:
                pass
            self._death_templates = templates
        return self._death_templates

    # ---- 查询 ----

    def key_to_zh(self, key: str) -> Optional[str]:
        """翻译键查库；未命中返回 None。"""
        key = (key or "").strip()
        return self._load_key2zh().get(key) if key else None

    def en_to_zh(self, text: str) -> Optional[str]:
        """原版英文精确查表（忽略首尾空白）；未命中返回 None。"""
        text = (text or "").strip()
        if not text:
            return None
        zh = self._load_en2zh().get(text)
        if zh is None:
            # 中文包键值也可能以翻译键形态出现（罕见），兜底一次
            zh = self._load_key2zh().get(text)
        return zh

    # ---- 组装 ----

    @staticmethod
    def _has_cjk(text: str) -> bool:
        return bool(_CJK_RE.search(text or ""))

    def _arg_to_zh(self, arg: str) -> str:
        """单个参数转中文：翻译键查库 → 英文查表 → 原样。"""
        arg = arg or ""
        if arg.startswith(_KEY_PREFIXES):
            return self.key_to_zh(arg) or arg
        return self.en_to_zh(arg) or arg

    def _fill(self, zh_template: str, args: list[str]) -> str:
        """把中文模板的 `%n$s` 占位依次替换为（翻译后的）参数。"""
        for i, a in enumerate(args, 1):
            zh_template = zh_template.replace(f"%{i}$s", self._arg_to_zh(a))
        return re.sub(r"%\d+\$s", "？", zh_template)

    # ---- 事件翻译 ----

    def translate_death(self, death: Optional[QueQiaoTranslate]) -> str:
        """死亡消息转中文；未命中任何翻译路径时回退原文。"""
        if death is None:
            return ""
        key, args, text = death.key, death.args, death.text

        # 服务端已翻译成中文：直接透传
        if not key and text and self._has_cjk(text):
            return text

        if key:
            zh = self.key_to_zh(key)
            if zh:
                return self._fill(zh, args)

        text = (text or "").strip()
        if not text:
            return key or ""

        # 英文整句模板匹配（覆盖服务端只给渲染文本、无 key 的场景）
        for pattern, zh_tpl in self._load_death_templates():
            match = pattern.match(text)
            if match:
                return self._fill(zh_tpl, list(match.groups()))

        return self.en_to_zh(text) or text

    def translate_achievement(self, ach: Optional[QueQiaoAchievement]) -> str:
        """成就名转中文；未命中任何翻译路径时回退成就名原文。"""
        if ach is None:
            return ""
        name = (ach.display_name or "").strip()
        if not name:
            return ""

        if self._has_cjk(name):
            return name

        # title 的原始翻译键（若鹊桥给了 display.title.key）
        title_key = (getattr(ach, "title_key", "") or "").strip()
        if title_key:
            zh = self.key_to_zh(title_key)
            if zh:
                return zh

        # 成就名本身可能就是翻译键（未开翻译时鹊桥回落 display.title.key）
        if name.startswith(_KEY_PREFIXES):
            zh = self.key_to_zh(name)
            if zh:
                return zh

        return self.en_to_zh(name) or name
