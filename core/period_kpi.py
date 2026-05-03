"""期間別 KPI の集計（月全体 + 4週分）+ 目標との比較。"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from .models import Deal
from .targets import Targets


@dataclass
class PeriodKPI:
    label: str
    period_start: date
    period_end: date
    target_ratio: float = 1.0  # 月目標に対する期間比率（週=0.25 等）

    appointments_actual: int = 0       # アポ数（初回アポ日が期間内）
    appointments_target: float = 0.0
    seated_actual: int = 0             # 着座数（初回アポ実施かつ実施日=初回アポ日 in期間）
    seated_target: float = 0.0
    contract_count_actual: int = 0
    contract_count_target: float = 0.0
    contract_amount_actual: float = 0.0
    contract_amount_target: float = 0.0
    closed_count_actual: int = 0
    closed_amount_actual: float = 0.0
    closed_count_target: float = 0.0
    closed_amount_target: float = 0.0
    second_appt_set_actual: int = 0   # 2回目商談日が期間内（=設定された）
    second_appt_set_target: float = 0.0
    second_appt_done_actual: int = 0  # 2回目実施済 かつ 2回目商談日が期間内
    second_appt_done_target: float = 0.0


def _in_period(d: date | None, start: date, end: date) -> bool:
    return d is not None and start <= d <= end


def compute_period_kpi(
    deals: Iterable[Deal],
    targets: Targets,
    label: str,
    period_start: date,
    period_end: date,
    target_ratio: float,
) -> PeriodKPI:
    kpi = PeriodKPI(
        label=label,
        period_start=period_start,
        period_end=period_end,
        target_ratio=target_ratio,
        appointments_target=targets.appointments * target_ratio,
        seated_target=targets.seated * target_ratio,
        contract_count_target=targets.contract_count * target_ratio,
        contract_amount_target=targets.contract_amount * target_ratio,
        closed_count_target=targets.closed_count * target_ratio,
        closed_amount_target=targets.closed_amount * target_ratio,
        second_appt_set_target=targets.second_appt_count * target_ratio,
        second_appt_done_target=targets.second_seated * target_ratio,
    )
    for d in deals:
        if _in_period(d.first_appt_date, period_start, period_end):
            kpi.appointments_actual += 1
            if d.first_appt_done:
                kpi.seated_actual += 1
        if _in_period(d.second_appt_date, period_start, period_end):
            kpi.second_appt_set_actual += 1
            if d.second_appt_done:
                kpi.second_appt_done_actual += 1
        if _in_period(d.contract_date, period_start, period_end):
            kpi.contract_count_actual += 1
            kpi.contract_amount_actual += d.contract_amount_inclusive
        if _in_period(d.closed_date, period_start, period_end):
            kpi.closed_count_actual += 1
            kpi.closed_amount_actual += d.closed_amount_inclusive or d.contract_amount_inclusive
    return kpi


def month_periods(today: date) -> list[tuple[str, date, date, float]]:
    """当月の (ラベル, 開始, 終了, 目標比率) を返す。

    1週目: 1〜7
    2週目: 8〜14
    3週目: 15〜21
    4週目: 22〜末日
    月全体: 1〜末日（target_ratio=1.0）
    """
    last = calendar.monthrange(today.year, today.month)[1]
    month_start = today.replace(day=1)
    month_end = today.replace(day=last)
    weeks = [
        (f"{today.month}月 1週目", date(today.year, today.month, 1), date(today.year, today.month, min(7, last))),
        (f"{today.month}月 2週目", date(today.year, today.month, 8), date(today.year, today.month, min(14, last))),
        (f"{today.month}月 3週目", date(today.year, today.month, 15), date(today.year, today.month, min(21, last))),
        (f"{today.month}月 4週目", date(today.year, today.month, 22), date(today.year, today.month, last)),
    ]
    week_ratio = 1.0 / 4.0
    out = [(f"{today.month}月 全体", month_start, month_end, 1.0)]
    out.extend((label, s, e, week_ratio) for (label, s, e) in weeks)
    return out


def daily_series(
    deals: Iterable[Deal],
    period_start: date,
    period_end: date,
    metric: str,
) -> list[tuple[date, float]]:
    """指定 metric の日次系列を返す（推移グラフ用）。

    metric: "appointments" / "seated" / "contracts" / "closed"
    """
    counter: dict[date, float] = {}
    cur = period_start
    while cur <= period_end:
        counter[cur] = 0
        cur += timedelta(days=1)
    for d in deals:
        if metric == "appointments":
            if _in_period(d.first_appt_date, period_start, period_end):
                counter[d.first_appt_date] = counter.get(d.first_appt_date, 0) + 1
        elif metric == "seated":
            if _in_period(d.first_appt_date, period_start, period_end) and d.first_appt_done:
                counter[d.first_appt_date] = counter.get(d.first_appt_date, 0) + 1
        elif metric == "contracts":
            if _in_period(d.contract_date, period_start, period_end):
                counter[d.contract_date] = counter.get(d.contract_date, 0) + 1
        elif metric == "contract_amount":
            if _in_period(d.contract_date, period_start, period_end):
                counter[d.contract_date] = counter.get(d.contract_date, 0) + d.contract_amount_inclusive
        elif metric == "closed":
            if _in_period(d.closed_date, period_start, period_end):
                counter[d.closed_date] = counter.get(d.closed_date, 0) + 1
        elif metric == "closed_amount":
            if _in_period(d.closed_date, period_start, period_end):
                counter[d.closed_date] = counter.get(d.closed_date, 0) + (d.closed_amount_inclusive or d.contract_amount_inclusive)
        elif metric == "second_set":
            if _in_period(d.second_appt_date, period_start, period_end):
                counter[d.second_appt_date] = counter.get(d.second_appt_date, 0) + 1
        elif metric == "second_done":
            if _in_period(d.second_appt_date, period_start, period_end) and d.second_appt_done:
                counter[d.second_appt_date] = counter.get(d.second_appt_date, 0) + 1
    return sorted(counter.items())
