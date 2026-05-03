"""分析タブから目標値を読み込む。

対象タブ: {name}_ヨミ表_分析
構造（観察に基づく）:
- 上部にメタ情報（タイトル / "松戸" 等のラベル）
- 「目標」「BUZZ流入」「合計実数」「日割り進捗」「ペース」のラベル列がある
- ヘッダー行に「商談枠 / アポ数 / 着座数 / 着座率 / 契約額 / 契約数 / 契約率 / 成約額 / 成約数 / 成約率」
"""
from __future__ import annotations

from dataclasses import dataclass

import gspread

from .config import Config, Member
from .google_auth import get_credentials


HEADER_KEYS = {
    "appointments": ["アポ数"],
    "seated": ["着座数"],
    "seating_rate": ["着座率"],
    "contract_amount": ["契約額"],
    "contract_count": ["契約数"],
    "contract_rate": ["契約率"],
    "closed_amount": ["成約額"],
    "closed_count": ["成約数"],
    "closed_rate": ["成約率"],
    "meeting_slots": ["商談枠"],
    "second_appt_count": ["2回目アポ数"],
    "second_appt_rate": ["2回目アポ率"],
    "second_seated": ["2回目着座数"],
    "second_seating_rate": ["2回目着座率"],
    "second_contract_count": ["2回目契約数"],
}


@dataclass
class Targets:
    appointments: int = 0
    seated: int = 0
    seating_rate: float = 0.0
    contract_amount: float = 0.0
    contract_count: int = 0
    contract_rate: float = 0.0
    closed_amount: float = 0.0
    closed_count: int = 0
    closed_rate: float = 0.0
    meeting_slots: int = 0
    second_appt_count: int = 0
    second_appt_rate: float = 0.0
    second_seated: int = 0
    second_seating_rate: float = 0.0
    second_contract_count: int = 0


def _parse_number(value: str) -> float:
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0
    s = s.replace(",", "").replace("¥", "").replace("円", "").replace("件", "")
    s = s.replace("%", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _resolve_analysis_sheet_name(config: Config, member: Member) -> str:
    template = config.analysis_sheet_name_template or ""
    if "{name}" in template:
        return template.replace("{name}", member.name)
    return template


def fetch_targets(config: Config, member: Member) -> Targets:
    """分析タブの "目標" 行を読んで Targets を返す。"""
    if not member.sheet_id:
        return Targets()
    creds = get_credentials(config.google_credentials_path, config.google_token_path)
    client = gspread.authorize(creds)
    sh = client.open_by_key(member.sheet_id)
    name = _resolve_analysis_sheet_name(config, member)
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        return Targets()

    rows = ws.get_all_values()
    if not rows:
        return Targets()

    # ヘッダー行と "目標" 行を見つける
    header_row_idx = -1
    target_row_idx = -1
    for i, row in enumerate(rows[:30]):
        joined = "".join(row)
        if "アポ数" in joined and "着座数" in joined and header_row_idx < 0:
            header_row_idx = i
        for cell in row:
            if cell.strip() == "目標":
                target_row_idx = i
                break
    if header_row_idx < 0 or target_row_idx < 0:
        return Targets()

    headers = rows[header_row_idx]
    target_row = rows[target_row_idx]

    # 各 KPI のヘッダー位置を特定（部分一致で頑健に）
    column_index: dict[str, int] = {}
    for key, hints in HEADER_KEYS.items():
        for idx, h in enumerate(headers):
            normalized = h.replace(" ", "").strip()
            if any(hint in normalized for hint in hints):
                column_index[key] = idx
                break

    def _get_at(key: str) -> float:
        idx = column_index.get(key)
        if idx is None or idx >= len(target_row):
            return 0.0
        return _parse_number(target_row[idx])

    return Targets(
        appointments=int(_get_at("appointments")),
        seated=int(_get_at("seated")),
        seating_rate=_get_at("seating_rate"),
        contract_amount=_get_at("contract_amount"),
        contract_count=int(_get_at("contract_count")),
        contract_rate=_get_at("contract_rate"),
        closed_amount=_get_at("closed_amount"),
        closed_count=int(_get_at("closed_count")),
        closed_rate=_get_at("closed_rate"),
        meeting_slots=int(_get_at("meeting_slots")),
        second_appt_count=int(_get_at("second_appt_count")),
        second_appt_rate=_get_at("second_appt_rate"),
        second_seated=int(_get_at("second_seated")),
        second_seating_rate=_get_at("second_seating_rate"),
        second_contract_count=int(_get_at("second_contract_count")),
    )
