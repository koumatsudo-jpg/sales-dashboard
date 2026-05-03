"""ダッシュボードの状態（dismissals / target overrides）を Google Sheets に保存。

ローカルとクラウドで状態を同期するために、ヨミ表と同じスプレッドシートに
隠しタブ `_app_state` を作って key=JSON 形式で永続化する。

データ構造:
    A1=key, B1=value(JSON)
    A2=dismissals_missing, B2=["id1", "id2", ...]
    A3=dismissals_stagnant, B3=["id1", "id2", ...]
    A4=target_overrides,    B4={"松戸": {...}, "鈴木": {...}}
"""
from __future__ import annotations

import json
from typing import Any

import gspread

from .config import Config
from .google_auth import get_credentials


STATE_SHEET = "_app_state"
STATE_KEYS = ("dismissals_missing", "dismissals_stagnant", "target_overrides")


def _client(config: Config) -> gspread.Client:
    creds = get_credentials(config.google_credentials_path, config.google_token_path)
    return gspread.authorize(creds)


def _get_or_create_ws(config: Config, sheet_id: str) -> gspread.Worksheet:
    sh = _client(config).open_by_key(sheet_id)
    try:
        return sh.worksheet(STATE_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=STATE_SHEET, rows=20, cols=2)
        # 初期化: ヘッダ + 各キーの空値
        rows = [["key", "value"]]
        for k in STATE_KEYS:
            default = "[]" if k.startswith("dismissals_") else "{}"
            rows.append([k, default])
        ws.update("A1:B4", rows)
        # シートを非表示にしたいが gspread から直接できないので、最初に作る位置を最後にして実質的に隠す
        try:
            ws.hide()
        except Exception:
            pass
        return ws


def _resolve_sheet_id(config: Config) -> str:
    if not config.members:
        raise RuntimeError("メンバーが未設定のため state シートを開けません")
    # オーナーのシートを正とする（同じスプレッドシートで運用する前提）
    return config.members[0].sheet_id


def read_state(config: Config) -> dict[str, Any]:
    """state シートを読み、JSON パース済みの dict を返す。

    Returns: {"dismissals_missing": [...], "dismissals_stagnant": [...], "target_overrides": {...}}
    """
    sheet_id = _resolve_sheet_id(config)
    ws = _get_or_create_ws(config, sheet_id)
    rows = ws.get_all_values()
    out: dict[str, Any] = {k: ([] if k.startswith("dismissals_") else {}) for k in STATE_KEYS}
    for row in rows[1:]:  # skip header
        if len(row) < 2:
            continue
        key, raw = row[0].strip(), row[1].strip()
        if key not in STATE_KEYS or not raw:
            continue
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:
            continue
    return out


def write_state_key(config: Config, key: str, value: Any) -> None:
    """指定キーの行を書き換える。"""
    if key not in STATE_KEYS:
        raise ValueError(f"unknown state key: {key}")
    sheet_id = _resolve_sheet_id(config)
    ws = _get_or_create_ws(config, sheet_id)
    rows = ws.get_all_values()
    target_row = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == key:
            target_row = i + 1  # gspread は 1始まり
            break
    payload = json.dumps(value, ensure_ascii=False)
    if target_row is None:
        ws.append_row([key, payload])
    else:
        ws.update_cell(target_row, 2, payload)
