import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_list(key: str, default: str = "") -> list[str]:
    raw = _get(key, default)
    return [s.strip() for s in raw.split(",") if s.strip()]


def _get_int(key: str, default: int) -> int:
    try:
        return int(_get(key) or default)
    except ValueError:
        return default


def _expand(p: str) -> str:
    return str(Path(p).expanduser()) if p else ""


def column_letter_to_index(letter: str) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 26."""
    if not letter:
        return -1
    result = 0
    for ch in letter.strip().upper():
        if not ("A" <= ch <= "Z"):
            return -1
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


@dataclass
class Member:
    name: str
    sheet_id: str
    calendar_id: str
    line_user_id: str
    yomi_sheet_name: str = ""


@dataclass
class ColumnMap:
    customer: int
    lead_status: int
    inflow: int
    first_appt_date: int
    first_appt_done: int
    first_appt_forecast: int
    second_appt_date: int
    second_appt_done: int
    second_appt_forecast: int
    current_status: int
    lost_reason: int             # 失注理由 (O列)
    na_memo: int                 # NA / 進捗メモ (V列)
    contract_planned_date: int
    contract_date: int
    contract_plan: int
    contract_amount_inclusive: int
    contract_amount_exclusive: int
    closed_date: int             # 成約日 (AK)
    closed_amount_inclusive: int # 入金額(税込) (AN)


@dataclass
class Config:
    google_credentials_path: str
    google_token_path: str

    yomi_sheet_name: str
    yomi_sheet_name_template: str
    analysis_sheet_name_template: str
    header_row: int

    columns: ColumnMap

    activity_keywords: list[str]
    excluded_event_keywords: list[str]
    stagnant_statuses: list[str]
    aliases_path: str
    missing_log_date_tolerance_days: int

    line_channel_access_token: str
    line_group_id: str
    notify_email_to: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str

    notification_hour: int
    stagnant_days_threshold: int
    timezone: str

    members: list[Member]


def _load_columns() -> ColumnMap:
    return ColumnMap(
        customer=column_letter_to_index(_get("COL_CUSTOMER", "B")),
        lead_status=column_letter_to_index(_get("COL_LEAD_STATUS", "C")),
        inflow=column_letter_to_index(_get("COL_INFLOW", "D")),
        first_appt_date=column_letter_to_index(_get("COL_FIRST_APPT_DATE", "H")),
        first_appt_done=column_letter_to_index(_get("COL_FIRST_APPT_DONE", "I")),
        first_appt_forecast=column_letter_to_index(_get("COL_FIRST_APPT_FORECAST", "J")),
        second_appt_date=column_letter_to_index(_get("COL_SECOND_APPT_DATE", "S")),
        second_appt_done=column_letter_to_index(_get("COL_SECOND_APPT_DONE", "T")),
        second_appt_forecast=column_letter_to_index(_get("COL_SECOND_APPT_FORECAST", "U")),
        current_status=column_letter_to_index(_get("COL_CURRENT_STATUS", "W")),
        lost_reason=column_letter_to_index(_get("COL_LOST_REASON", "O")),
        na_memo=column_letter_to_index(_get("COL_NA_MEMO", "V")),
        contract_planned_date=column_letter_to_index(_get("COL_CONTRACT_PLANNED_DATE", "Y")),
        contract_date=column_letter_to_index(_get("COL_CONTRACT_DATE", "Z")),
        contract_plan=column_letter_to_index(_get("COL_CONTRACT_PLAN", "AA")),
        contract_amount_inclusive=column_letter_to_index(_get("COL_CONTRACT_AMOUNT_INCLUSIVE", "AB")),
        contract_amount_exclusive=column_letter_to_index(_get("COL_CONTRACT_AMOUNT_EXCLUSIVE", "AC")),
        closed_date=column_letter_to_index(_get("COL_CLOSED_DATE", "AK")),
        closed_amount_inclusive=column_letter_to_index(_get("COL_CLOSED_AMOUNT_INCLUSIVE", "AN")),
    )


def load_config() -> Config:
    owner = Member(
        name=_get("OWNER_NAME", "オーナー"),
        sheet_id=_get("SHEET_ID_OWNER"),
        calendar_id=_get("CALENDAR_ID_OWNER", "primary"),
        line_user_id=_get("LINE_USER_ID_OWNER"),
        yomi_sheet_name=_get("YOMI_SHEET_NAME_OWNER"),
    )
    subordinate = Member(
        name=_get("SUBORDINATE_NAME", "部下"),
        sheet_id=_get("SHEET_ID_SUBORDINATE"),
        calendar_id=_get("CALENDAR_ID_SUBORDINATE"),
        line_user_id=_get("LINE_USER_ID_SUBORDINATE"),
        yomi_sheet_name=_get("YOMI_SHEET_NAME_SUBORDINATE"),
    )
    members = [m for m in (owner, subordinate) if m.sheet_id and m.name]

    aliases_path = _expand(_get("ALIASES_PATH") or str(ROOT / "aliases.yaml"))

    return Config(
        google_credentials_path=_expand(_get("GOOGLE_OAUTH_CREDENTIALS")),
        google_token_path=_expand(_get("GOOGLE_OAUTH_TOKEN")),
        yomi_sheet_name=_get("YOMI_SHEET_NAME", "ヨミ表"),
        yomi_sheet_name_template=_get("YOMI_SHEET_NAME_TEMPLATE", "{name}_ヨミ表_顧客管理"),
        analysis_sheet_name_template=_get("ANALYSIS_SHEET_NAME_TEMPLATE", "{name}_ヨミ表_分析"),
        header_row=_get_int("HEADER_ROW", 5),
        columns=_load_columns(),
        activity_keywords=_get_list("ACTIVITY_KEYWORDS", "無料カウンセリング,商談,アポ,訪問,面談,初回,2回目,契約"),
        excluded_event_keywords=_get_list("EXCLUDED_EVENT_KEYWORDS", "キャンセル,再アポ,契約予定,契約"),
        stagnant_statuses=_get_list("STAGNANT_STATUSES", "検討中,長期追客,2回目商談日程確定,2回目商談日程調整中"),
        aliases_path=aliases_path,
        missing_log_date_tolerance_days=_get_int("MISSING_LOG_DATE_TOLERANCE_DAYS", 1),
        line_channel_access_token=_get("LINE_CHANNEL_ACCESS_TOKEN"),
        line_group_id=_get("LINE_GROUP_ID"),
        notify_email_to=_get("NOTIFY_EMAIL_TO"),
        smtp_host=_get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_get_int("SMTP_PORT", 587),
        smtp_user=_get("SMTP_USER"),
        smtp_password=_get("SMTP_PASSWORD"),
        notification_hour=_get_int("NOTIFICATION_HOUR", 9),
        stagnant_days_threshold=_get_int("STAGNANT_DAYS_THRESHOLD", 7),
        timezone=_get("TIMEZONE", "Asia/Tokyo"),
        members=members,
    )
