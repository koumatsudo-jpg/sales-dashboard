"""カレンダー名 ↔ ヨミ表名 のエイリアスマッピング。

aliases.yaml フォーマット:
```yaml
aliases:
  - calendar: 大嶽恵理
    sheet: megumi.k
  - calendar: 瀧澤吉徳
    sheet: 滝沢吉徳
```

両方向参照が可能。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .normalize import normalize


class AliasMap:
    """双方向エイリアステーブル。

    ・正規化されたキーで突合する
    ・1対1でも n対1 でも扱える（複数のカレンダー名 → 1つのシート名）
    """

    def __init__(self) -> None:
        self._calendar_to_sheet: dict[str, str] = {}
        self._sheet_to_calendar: dict[str, str] = {}

    @classmethod
    def load(cls, path: Path | str) -> "AliasMap":
        m = cls()
        p = Path(path)
        if not p.exists():
            return m
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return m
        for entry in data.get("aliases") or []:
            cal = (entry.get("calendar") or "").strip()
            sheet = (entry.get("sheet") or "").strip()
            if not cal or not sheet:
                continue
            m._calendar_to_sheet[normalize(cal)] = sheet
            m._sheet_to_calendar[normalize(sheet)] = cal
        return m

    def matches(self, name_a: str, name_b: str) -> bool:
        """正規化済 a と b がエイリアス関係にあれば True。"""
        if not name_a or not name_b:
            return False
        a = normalize(name_a)
        b = normalize(name_b)
        # a がカレンダー名 → 対応するシート名と b を比較
        if a in self._calendar_to_sheet and normalize(self._calendar_to_sheet[a]) == b:
            return True
        if b in self._calendar_to_sheet and normalize(self._calendar_to_sheet[b]) == a:
            return True
        if a in self._sheet_to_calendar and normalize(self._sheet_to_calendar[a]) == b:
            return True
        if b in self._sheet_to_calendar and normalize(self._sheet_to_calendar[b]) == a:
            return True
        return False
