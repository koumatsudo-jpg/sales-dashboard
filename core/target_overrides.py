"""目標値のローカル上書き管理。

分析タブから読み込んだ目標値を、ローカルの YAML ファイルで上書きできる。
ダッシュボードの「目標設定」タブから編集・保存。
"""
from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import yaml

from .targets import Targets


DEFAULT_PATH = Path(__file__).resolve().parent.parent / "targets_override.yaml"


def load_overrides(path: Path | str | None = None) -> dict[str, dict[str, float]]:
    """member_name -> {field: value} を返す。"""
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return data.get("overrides", {}) or {}


def save_overrides(overrides: dict[str, dict[str, float]], path: Path | str | None = None) -> None:
    """上書き値を保存。"""
    p = Path(path) if path else DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump({"overrides": overrides}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


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
