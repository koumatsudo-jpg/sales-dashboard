"""アラートの削除（dismiss）管理。

記入漏れ・停滞案件を「もうアラートに出さない」ようにするローカルリスト。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_PATH = Path(__file__).resolve().parent.parent / "dismissals.yaml"


def _load_raw(path: Path | str | None = None) -> dict[str, list[str]]:
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        return {"missing_logs": [], "stagnant_deals": []}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {"missing_logs": [], "stagnant_deals": []}
    return {
        "missing_logs": list(data.get("missing_logs") or []),
        "stagnant_deals": list(data.get("stagnant_deals") or []),
    }


def _save_raw(data: dict[str, list[str]], path: Path | str | None = None) -> None:
    p = Path(path) if path else DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump({k: list(dict.fromkeys(v)) for k, v in data.items()},
                       allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def missing_log_id(owner: str, event_date: Any, event_id: str, title: str) -> str:
    """記入漏れの一意ID。event_id があればそれ + 日付、無ければ title + date。"""
    base = event_id or title
    return f"{owner}|{event_date}|{base}"


def stagnant_id(sheet_id: str, sheet_tab: str, row_number: int, customer: str) -> str:
    """停滞案件の一意ID。シート位置で固定。"""
    return f"{sheet_id}|{sheet_tab}|{row_number}|{customer}"


def get_dismissed() -> tuple[set[str], set[str]]:
    raw = _load_raw()
    return set(raw["missing_logs"]), set(raw["stagnant_deals"])


def dismiss_missing(ids: list[str]) -> None:
    raw = _load_raw()
    raw["missing_logs"] = list(set(raw["missing_logs"]) | set(ids))
    _save_raw(raw)


def dismiss_stagnant(ids: list[str]) -> None:
    raw = _load_raw()
    raw["stagnant_deals"] = list(set(raw["stagnant_deals"]) | set(ids))
    _save_raw(raw)


def restore_missing(ids: list[str]) -> None:
    raw = _load_raw()
    raw["missing_logs"] = [x for x in raw["missing_logs"] if x not in set(ids)]
    _save_raw(raw)


def restore_stagnant(ids: list[str]) -> None:
    raw = _load_raw()
    raw["stagnant_deals"] = [x for x in raw["stagnant_deals"] if x not in set(ids)]
    _save_raw(raw)


def clear_all() -> None:
    _save_raw({"missing_logs": [], "stagnant_deals": []})
