"""カレンダー予定 × ヨミ表（活動ログ）の突合 + 停滞案件検出。

カレンダータイトル例（基本: 1予定=1顧客）:
- "本多将大様 松戸さん 無料カウンセリング"
- "田中太郎様 松戸 好誠 無料カウンセリング"
- "本多将大様 無料カウンセリング"

突合の精度向上施策:
- 文字正規化（NFKC, 旧字→新字, カナ統一）
- エイリアスマッピング（手動）
- 日付の前後N日まで許容
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .aliases import AliasMap
from .models import ActivityLog, CalendarEvent, Deal, MissingLog
from .normalize import normalize, normalize_status


_CUSTOMER_SEPARATORS = re.compile(r"[：:\-―ー\s／/|｜、,]+")
_BRACKET_RE = re.compile(r"[\[【\(（].*?[\]】\)）]")


def is_business_event(
    title: str,
    keywords: list[str],
    excluded_keywords: list[str] | None = None,
) -> bool:
    """営業活動とみなす予定か判定。

    ルール:
    - excluded_keywords に該当する語が含まれる → 除外（サイヤポ/契約予定/キャンセル など）
    - "様"（顧客敬称）が含まれる → 営業活動
    """
    if not title:
        return False
    excludes = excluded_keywords or ["キャンセル", "再アポ", "契約予定", "契約"]
    if any(ek in title for ek in excludes):
        return False
    return "様" in title


def _is_keyword_token(token: str, keywords: list[str]) -> bool:
    for kw in keywords:
        if kw == token:
            return True
        if kw in token and len(token) <= len(kw) + 2:
            return True
    return False


def extract_customers(title: str, keywords: list[str]) -> list[str]:
    """予定タイトルから顧客名候補のリストを返す。"""
    if not title:
        return []
    cleaned = _BRACKET_RE.sub("", title).strip()
    if "様" not in cleaned:
        return []
    customer = cleaned.split("様", 1)[0].strip()
    if not customer or _is_keyword_token(customer, keywords):
        return []
    return [customer]


def extract_customer(title: str, keywords: list[str]) -> str:
    customers = extract_customers(title, keywords)
    return customers[0] if customers else ""


def _customer_match(extracted: str, log_customer: str, aliases: AliasMap | None = None) -> bool:
    """顧客名の照合。

    1. 正規化（NFKC + 旧字→新字 + カナ統一 + 空白記号除去）後に部分一致（双方向の包含）
    2. 一致しなければエイリアスマップで対応関係をチェック
    """
    a = normalize(extracted)
    b = normalize(log_customer)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    if aliases is not None and aliases.matches(extracted, log_customer):
        return True
    return False


def find_missing_logs(
    calendar_events: list[CalendarEvent],
    activity_logs: list[ActivityLog],
    keywords: list[str],
    owner: str,
    target_date: date,
    aliases: AliasMap | None = None,
    date_tolerance_days: int = 0,
    excluded_keywords: list[str] | None = None,
) -> list[MissingLog]:
    """指定日のカレンダー予定と活動ログを突合し、記入漏れを返す。"""
    target_events = [
        e for e in calendar_events
        if e.event_date == target_date and is_business_event(e.title, keywords, excluded_keywords)
    ]

    valid_dates = {target_date}
    for delta in range(1, date_tolerance_days + 1):
        valid_dates.add(target_date + timedelta(days=delta))
        valid_dates.add(target_date - timedelta(days=delta))

    nearby_logs = [
        log for log in activity_logs
        if log.log_date in valid_dates and log.owner == owner
    ]

    missing: list[MissingLog] = []
    for event in target_events:
        candidates = extract_customers(event.title, keywords)
        if not candidates:
            missing.append(MissingLog(owner=owner, event=event, extracted_customer=event.title))
            continue
        unmatched = [
            c for c in candidates
            if not any(_customer_match(c, log.customer, aliases) for log in nearby_logs)
        ]
        if unmatched:
            missing.append(MissingLog(
                owner=owner,
                event=event,
                extracted_customer="／".join(unmatched),
            ))
    return missing


_LOST_DECIDED_DEFAULT = ("失注", "SP", "リスケ")


_LOST_OR_DECIDED = ("失注", "SP", "リスケ", "契約済")


def find_data_inconsistencies(
    deals: list[Deal],
    period_start: date | None = None,
    period_end: date | None = None,
) -> list[dict]:
    """データ不整合アラート:

    type=A: 活動中（未決着）AND V列(NA)が空欄
            → 着手済みなのに進捗メモが空
    type=B: ステータス=失注 AND O列(失注理由)が空欄
            → 失注したのに理由が空

    ※ 着手前のリード（初回アポ日が空）は除外
    ※ 期間指定時、主要日付のいずれかが期間内の案件のみ対象
    """
    decided = {normalize_status(s) for s in _LOST_OR_DECIDED}
    out: list[dict] = []

    def _in_period(d: date | None) -> bool:
        if d is None:
            return False
        if period_start and d < period_start:
            return False
        if period_end and d > period_end:
            return False
        return True

    for deal in deals:
        if deal.first_appt_date is None:
            continue
        if period_start or period_end:
            in_range = any(_in_period(d) for d in (
                deal.first_appt_date,
                deal.second_appt_date,
                deal.contract_date,
                deal.closed_date,
            ))
            if not in_range:
                continue
        status_norm = normalize_status(deal.current_status)
        has_lost_reason = bool((deal.lost_reason or "").strip())
        has_na_memo = bool((deal.na_memo or "").strip())
        is_active = (deal.contract_date is None) and (status_norm not in decided)

        # A: 活動中 AND V列(NA)が空
        if is_active and not has_na_memo:
            out.append({
                "type": "A",
                "deal": deal,
                "message": "未着地・NA(V列)が空",
            })
        # B: 失注ステータス AND O列(失注理由)が空
        if status_norm == normalize_status("失注") and not has_lost_reason:
            out.append({
                "type": "B",
                "deal": deal,
                "message": "失注ステータスなのに失注理由(O列)が空",
            })
    return out


def find_stagnant_deals(
    deals: list[Deal],
    today: date,
    threshold_days: int,
    stagnant_statuses: list[str] | None = None,
) -> list[Deal]:
    """停滞案件を返す（ホワイトリスト方式）。

    停滞条件（ALL）:
    1. 契約実施日が空（契約未完了）
    2. 最新活動日から threshold_days 日以上経過
    3. 現況ステータスが stagnant_statuses に含まれる（リスト指定時のみ）
       - リスト未指定 or 空ならステータス条件なし

    対象想定: 検討中 / 長期追客 / 2回目商談日程確定 / 2回目商談日程調整中
    """
    allowed = {normalize_status(s) for s in (stagnant_statuses or []) if s}

    out: list[Deal] = []
    for deal in deals:
        if deal.contract_date is not None:
            continue
        last = deal.latest_activity_date
        if last is None:
            continue
        if (today - last).days < threshold_days:
            continue
        if allowed:
            if normalize_status(deal.current_status) not in allowed:
                continue
        out.append(deal)
    return out
