"""アラートの削除（dismiss）管理。Google Sheets に保存（ローカル⇄クラウド同期）。

記入漏れ・停滞案件を「もうアラートに出さない」リスト。
ヨミ表と同じスプレッドシートの `_app_state` タブに永続化する。
"""
from __future__ import annotations

from typing import Any

from .config import Config, load_config
from .sheet_state import read_state, write_state_key


def missing_log_id(owner: str, event_date: Any, event_id: str, title: str) -> str:
    base = event_id or title
    return f"{owner}|{event_date}|{base}"


def stagnant_id(sheet_id: str, sheet_tab: str, row_number: int, customer: str) -> str:
    return f"{sheet_id}|{sheet_tab}|{row_number}|{customer}"


def _config() -> Config:
    return load_config()


def get_dismissed() -> tuple[set[str], set[str]]:
    state = read_state(_config())
    return set(state.get("dismissals_missing") or []), set(state.get("dismissals_stagnant") or [])


def dismiss_missing(ids: list[str]) -> None:
    config = _config()
    state = read_state(config)
    merged = list(set(state.get("dismissals_missing") or []) | set(ids))
    write_state_key(config, "dismissals_missing", merged)


def dismiss_stagnant(ids: list[str]) -> None:
    config = _config()
    state = read_state(config)
    merged = list(set(state.get("dismissals_stagnant") or []) | set(ids))
    write_state_key(config, "dismissals_stagnant", merged)


def restore_missing(ids: list[str]) -> None:
    config = _config()
    state = read_state(config)
    remaining = [x for x in (state.get("dismissals_missing") or []) if x not in set(ids)]
    write_state_key(config, "dismissals_missing", remaining)


def restore_stagnant(ids: list[str]) -> None:
    config = _config()
    state = read_state(config)
    remaining = [x for x in (state.get("dismissals_stagnant") or []) if x not in set(ids)]
    write_state_key(config, "dismissals_stagnant", remaining)


def clear_all() -> None:
    config = _config()
    write_state_key(config, "dismissals_missing", [])
    write_state_key(config, "dismissals_stagnant", [])
