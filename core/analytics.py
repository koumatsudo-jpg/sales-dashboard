"""KPI 集計（ヨミ表ベース）。個人別／チーム合計の両軸。

ファネル: リード → 初回予定 → 初回実施 → 2回目予定 → 2回目実施 → 契約
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .models import Deal


_FORECAST_WEIGHT = {
    "A": 0.9,
    "B": 0.6,
    "C": 0.3,
    "D": 0.1,
}


@dataclass
class FunnelMetrics:
    leads: int = 0
    first_appt_scheduled: int = 0
    first_appt_done: int = 0
    second_appt_scheduled: int = 0
    second_appt_done: int = 0
    contracts: int = 0
    contract_amount_total: float = 0.0
    weighted_pipeline: float = 0.0
    deals_by_forecast: dict[str, int] = field(default_factory=dict)


@dataclass
class MemberKPI:
    name: str
    deal_count: int
    funnel: FunnelMetrics
    period_first_appt: int = 0
    period_first_done: int = 0
    period_second_appt: int = 0
    period_second_done: int = 0
    period_contracts: int = 0
    period_contract_amount: float = 0.0


@dataclass
class TeamKPI:
    members: list[MemberKPI]
    funnel: FunnelMetrics
    period_first_appt: int = 0
    period_first_done: int = 0
    period_second_appt: int = 0
    period_second_done: int = 0
    period_contracts: int = 0
    period_contract_amount: float = 0.0


def _in_period(d: date | None, start: date | None, end: date | None) -> bool:
    if d is None:
        return False
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def aggregate_member(
    name: str,
    deals: list[Deal],
    period_start: date | None = None,
    period_end: date | None = None,
) -> MemberKPI:
    funnel = FunnelMetrics()
    forecast_counter: dict[str, int] = defaultdict(int)

    period_first_appt = 0
    period_first_done = 0
    period_second_appt = 0
    period_second_done = 0
    period_contracts = 0
    period_contract_amount = 0.0

    for d in deals:
        funnel.leads += 1

        if d.first_appt_date:
            funnel.first_appt_scheduled += 1
        if d.first_appt_done:
            funnel.first_appt_done += 1
        if d.second_appt_date:
            funnel.second_appt_scheduled += 1
        if d.second_appt_done:
            funnel.second_appt_done += 1
        if d.contract_date:
            funnel.contracts += 1
            funnel.contract_amount_total += d.contract_amount_inclusive

        forecast = (d.second_appt_forecast or d.first_appt_forecast or "").strip().upper()
        if forecast:
            forecast_counter[forecast] += 1
            weight = _FORECAST_WEIGHT.get(forecast[:1], 0.0)
            est_amount = d.contract_amount_inclusive
            funnel.weighted_pipeline += weight * est_amount

        if _in_period(d.first_appt_date, period_start, period_end):
            period_first_appt += 1
            if d.first_appt_done:
                period_first_done += 1
        if _in_period(d.second_appt_date, period_start, period_end):
            period_second_appt += 1
            if d.second_appt_done:
                period_second_done += 1
        if _in_period(d.contract_date, period_start, period_end):
            period_contracts += 1
            period_contract_amount += d.contract_amount_inclusive

    funnel.deals_by_forecast = dict(forecast_counter)

    return MemberKPI(
        name=name,
        deal_count=len(deals),
        funnel=funnel,
        period_first_appt=period_first_appt,
        period_first_done=period_first_done,
        period_second_appt=period_second_appt,
        period_second_done=period_second_done,
        period_contracts=period_contracts,
        period_contract_amount=period_contract_amount,
    )


def aggregate_team(member_kpis: list[MemberKPI]) -> TeamKPI:
    funnel = FunnelMetrics()
    forecast_total: dict[str, int] = defaultdict(int)
    for m in member_kpis:
        funnel.leads += m.funnel.leads
        funnel.first_appt_scheduled += m.funnel.first_appt_scheduled
        funnel.first_appt_done += m.funnel.first_appt_done
        funnel.second_appt_scheduled += m.funnel.second_appt_scheduled
        funnel.second_appt_done += m.funnel.second_appt_done
        funnel.contracts += m.funnel.contracts
        funnel.contract_amount_total += m.funnel.contract_amount_total
        funnel.weighted_pipeline += m.funnel.weighted_pipeline
        for k, v in m.funnel.deals_by_forecast.items():
            forecast_total[k] += v
    funnel.deals_by_forecast = dict(forecast_total)

    return TeamKPI(
        members=member_kpis,
        funnel=funnel,
        period_first_appt=sum(m.period_first_appt for m in member_kpis),
        period_first_done=sum(m.period_first_done for m in member_kpis),
        period_second_appt=sum(m.period_second_appt for m in member_kpis),
        period_second_done=sum(m.period_second_done for m in member_kpis),
        period_contracts=sum(m.period_contracts for m in member_kpis),
        period_contract_amount=sum(m.period_contract_amount for m in member_kpis),
    )
