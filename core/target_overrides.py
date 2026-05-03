"""目標値の上書き管理。Google Sheets に保存（ローカル⇄クラウド同期）。

分析タブから読み込んだ目標値を、`_app_state` タブの target_overrides で上書きできる。
"""
from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from .config import Config, load_config
from .sheet_state import read_state, write_state_key
from .targets import Targets


def _config() -> Config:
    return load_config()


def load_overrides() -> dict[str, dict[str, float]]:
    """member_name -> {field: value} を返す。"""
    state = read_state(_config())
    return state.get("target_overrides") or {}


def save_overrides(overrides: dict[str, dict[str, float]]) -> None:
    """上書き値を保存。"""
    write_state_key(_config(), "target_overrides", overrides)


def apply_overrides(targets: Targets, member_name: str, overrides: dict[str, dict[str, float]]) -> Targets:
    """Targets に上書きを適用した新しいインスタンスを返す。"""
    member_override = overrides.get(member_name) or {}
    if not member_override:
        return targets
    data = asdict(targets)
    valid_fields = {f.name for f in fields(Targets)}
    for k, v in member_override.items():
        if k in valid_fields and v is not None and v != "":
            try:
                if isinstance(data[k], int):
                    data[k] = int(float(v))
                else:
                    data[k] = float(v)
            except (TypeError, ValueError):
                continue
    return Targets(**data)


def upsert_member(
    overrides: dict[str, dict[str, float]],
    member_name: str,
    values: dict[str, Any],
) -> dict[str, dict[str, float]]:
    """指定メンバーの上書き値を更新したコピーを返す。空文字/None のキーは削除。"""
    out = {k: dict(v) for k, v in overrides.items()}
    cleaned = {}
    for k, v in values.items():
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        cleaned[k] = v
    if cleaned:
        out[member_name] = cleaned
    elif member_name in out:
        del out[member_name]
    return out
