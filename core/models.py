from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = field(default_factory=list)

    @property
    def event_date(self) -> date:
        return self.start.date()


@dataclass
class ActivityLog:
    """1案件×1ステージ = 1件の活動として正規化したログ。

    例: 同じ顧客の「初回アポ」と「2回目」は別の ActivityLog になる。
    """
    owner: str
    customer: str
    log_date: date
    stage: str = ""           # 初回 / 2回目 / 契約
    done: bool = False        # 実施済みかどうか
    forecast: str = ""        # 見込み（A/B/C/D 等）
    amount: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass
class Deal:
    """1顧客=1案件のヨミ表行を表現したもの。"""
    owner: str
    customer: str
    lead_status: str = ""
    inflow: str = ""
    current_status: str = ""  # 現況ステータス（W列）
    lost_reason: str = ""     # 失注理由 (O列)
    na_memo: str = ""         # NA / 進捗メモ (V列)
    first_appt_date: Optional[date] = None
    first_appt_done: bool = False
    first_appt_forecast: str = ""
    second_appt_date: Optional[date] = None
    second_appt_done: bool = False
    second_appt_forecast: str = ""
    contract_planned_date: Optional[date] = None
    contract_date: Optional[date] = None
    contract_plan: str = ""
    contract_amount_inclusive: float = 0.0
    contract_amount_exclusive: float = 0.0
    closed_date: Optional[date] = None  # 成約日（クーリング後の確定）
    closed_amount_inclusive: float = 0.0  # 入金額(税込) = 成約額
    raw_row: list[str] = field(default_factory=list)
    row_number: int = 0
    sheet_id: str = ""
    sheet_tab: str = ""

    @property
    def latest_activity_date(self) -> Optional[date]:
        """最新の活動日付（停滞検出用）。"""
        candidates = [d for d in (
            self.first_appt_date, self.second_appt_date, self.contract_date
        ) if d is not None]
        return max(candidates) if candidates else None

    @property
    def current_stage(self) -> str:
        """現在のステージ。契約 > 2回目 > 初回 > リードのみ。"""
        if self.contract_date:
            return "契約済"
        if self.second_appt_done:
            return "2回目実施済"
        if self.second_appt_date:
            return "2回目予定"
        if self.first_appt_done:
            return "初回実施済"
        if self.first_appt_date:
            return "初回予定"
        return "リード"


@dataclass
class MissingLog:
    owner: str
    event: CalendarEvent
    extracted_customer: str

    def message(self) -> str:
        return (
            f"⚠️ 記入漏れの可能性\n"
            f"日時: {self.event.start.strftime('%m/%d %H:%M')}\n"
            f"予定: {self.event.title}\n"
            f"顧客（推定）: {self.extracted_customer}\n"
            f"→ ヨミ表に記入をお願いします"
        )


def deal_to_activity_logs(deal: Deal) -> list[ActivityLog]:
    """1案件から、ステージ別の活動ログを生成。"""
    logs: list[ActivityLog] = []
    if deal.first_appt_date:
        logs.append(ActivityLog(
            owner=deal.owner,
            customer=deal.customer,
            log_date=deal.first_appt_date,
            stage="初回",
            done=deal.first_appt_done,
            forecast=deal.first_appt_forecast,
        ))
    if deal.second_appt_date:
        logs.append(ActivityLog(
            owner=deal.owner,
            customer=deal.customer,
            log_date=deal.second_appt_date,
            stage="2回目",
            done=deal.second_appt_done,
            forecast=deal.second_appt_forecast,
        ))
    if deal.contract_date:
        logs.append(ActivityLog(
            owner=deal.owner,
            customer=deal.customer,
            log_date=deal.contract_date,
            stage="契約",
            done=True,
            amount=deal.contract_amount_inclusive,
        ))
    return logs
