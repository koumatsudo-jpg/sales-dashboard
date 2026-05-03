"""Google Sheets からヨミ表（1顧客1行）を取得し、Deal / ActivityLog に変換する。

- 「実施済」「見込み」「失注理由」が複数列に重複しているため、列レター（A,B,...）でアクセス
- 見出し行は自動検出（顧客名ヘッダーを探す）。見つからない場合は HEADER_ROW へフォールバック
- メンバーごとにタブ名を持てる（松戸は "松戸_ヨミ表_顧客管理"、部下は "鈴木_ヨミ表_顧客管理" など）
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import gspread

from .config import Config, Member
from .google_auth import get_credentials
from .models import ActivityLog, Deal, deal_to_activity_logs


HEADER_DETECT_HINTS = ("顧客名", "顧客", "会社名", "クライアント名")


def _open_client(config: Config) -> gspread.Client:
    creds = get_credentials(config.google_credentials_path, config.google_token_path)
    return gspread.authorize(creds)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y年%m月%d日",
        "%m/%d",
    ):
        try:
            parsed = datetime.strptime(s, fmt)
            if fmt == "%m/%d":
                parsed = parsed.replace(year=date.today().year)
            return parsed.date()
        except ValueError:
            continue
    return None


def _parse_amount(value: Any) -> float:
    if value is None:
        return 0.0
    s = str(value).replace(",", "").replace("¥", "").replace("円", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _is_done(value: Any) -> bool:
    """実施済の判定。明示的な実施マーカーのみ True。"""
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    truthy = {
        "済", "済み", "○", "◯", "完了", "実施", "実施済", "実施済み",
        "TRUE", "true", "True", "1", "✓", "✔", "yes", "Yes", "Y", "y", "OK", "ok",
    }
    return s in truthy


def _cell(row: list[str], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return row[index]


def _autodetect_header_row(all_rows: list[list[str]], customer_col_idx: int) -> int:
    """顧客名ヘッダーを含む行を返す。見つからなければ -1。"""
    for i, row in enumerate(all_rows[:30]):
        cell = _cell(row, customer_col_idx).strip()
        if cell in HEADER_DETECT_HINTS:
            return i
    return -1


def _resolve_sheet_name(config: Config, member: Member) -> str:
    if member.yomi_sheet_name:
        return member.yomi_sheet_name
    template = config.yomi_sheet_name_template
    if "{name}" in template:
        return template.replace("{name}", member.name)
    return template or config.yomi_sheet_name


def fetch_deals(config: Config, member: Member) -> list[Deal]:
    if not member.sheet_id:
        return []
    client = _open_client(config)
    sh = client.open_by_key(member.sheet_id)
    sheet_name = _resolve_sheet_name(config, member)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        return []

    all_rows = ws.get_all_values()
    if not all_rows:
        return []

    cols = config.columns

    detected = _autodetect_header_row(all_rows, cols.customer)
    if detected >= 0:
        data_start = detected + 1
    else:
        data_start = max(config.header_row, 1)

    deals: list[Deal] = []
    for offset, raw in enumerate(all_rows[data_start:]):
        customer = _cell(raw, cols.customer).strip()
        if not customer or customer in HEADER_DETECT_HINTS:
            continue
        deals.append(Deal(
            owner=member.name,
            customer=customer,
            lead_status=_cell(raw, cols.lead_status).strip(),
            inflow=_cell(raw, cols.inflow).strip(),
            current_status=_cell(raw, cols.current_status).strip(),
            lost_reason=_cell(raw, cols.lost_reason).strip(),
            na_memo=_cell(raw, cols.na_memo).strip(),
            first_appt_date=_parse_date(_cell(raw, cols.first_appt_date)),
            first_appt_done=_is_done(_cell(raw, cols.first_appt_done)),
            first_appt_forecast=_cell(raw, cols.first_appt_forecast).strip(),
            second_appt_date=_parse_date(_cell(raw, cols.second_appt_date)),
            second_appt_done=_is_done(_cell(raw, cols.second_appt_done)),
            second_appt_forecast=_cell(raw, cols.second_appt_forecast).strip(),
            contract_planned_date=_parse_date(_cell(raw, cols.contract_planned_date)),
            contract_date=_parse_date(_cell(raw, cols.contract_date)),
            contract_plan=_cell(raw, cols.contract_plan).strip(),
            contract_amount_inclusive=_parse_amount(_cell(raw, cols.contract_amount_inclusive)),
            contract_amount_exclusive=_parse_amount(_cell(raw, cols.contract_amount_exclusive)),
            closed_date=_parse_date(_cell(raw, cols.closed_date)),
            closed_amount_inclusive=_parse_amount(_cell(raw, cols.closed_amount_inclusive)),
            raw_row=raw,
            row_number=data_start + offset + 1,  # gspread は 1始まり
            sheet_id=member.sheet_id,
            sheet_tab=sheet_name,
        ))
    return deals


def update_current_status(
    config: Config,
    sheet_id: str,
    sheet_tab: str,
    row_number: int,
    new_status: str,
) -> None:
    """指定行の現況ステータス（W列）を書き換える。"""
    if not sheet_id or not sheet_tab or row_number <= 0:
        raise ValueError("sheet_id / sheet_tab / row_number が不正です")
    col_index = config.columns.current_status + 1  # gspread は 1始まり
    if col_index <= 0:
        raise ValueError("COL_CURRENT_STATUS の設定が不正です")
    client = _open_client(config)
    sh = client.open_by_key(sheet_id)
    ws = sh.worksheet(sheet_tab)
    ws.update_cell(row_number, col_index, new_status)


def fetch_activity_logs(config: Config, member: Member) -> list[ActivityLog]:
    deals = fetch_deals(config, member)
    out: list[ActivityLog] = []
    for d in deals:
        out.extend(deal_to_activity_logs(d))
    return out
