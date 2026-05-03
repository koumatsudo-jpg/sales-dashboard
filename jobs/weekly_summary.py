"""週次サマリ通知（毎週月 9:00 想定）。

先週1週間のアポ・契約数を本人＋チーム合計で送る。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import _runner  # noqa: F401

from core.analytics import aggregate_member, aggregate_team
from core.config import load_config
from core.notify import notify
from core.sheets import fetch_deals


def _yen(v: float) -> str:
    return f"¥{int(v):,}"


def main() -> int:
    config = load_config()
    tz = ZoneInfo(config.timezone)
    today = datetime.now(tz).date()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)

    member_kpis = []
    for member in config.members:
        deals = fetch_deals(config, member)
        kpi = aggregate_member(member.name, deals, period_start=last_monday, period_end=last_sunday)
        member_kpis.append(kpi)
        body = (
            f"📊 {member.name}さん 週次サマリ\n"
            f"対象: {last_monday.strftime('%-m/%-d')} 〜 {last_sunday.strftime('%-m/%-d')}\n\n"
            f"・初回アポ: {kpi.period_first_appt}件（実施 {kpi.period_first_done}件）\n"
            f"・2回目アポ: {kpi.period_second_appt}件（実施 {kpi.period_second_done}件）\n"
            f"・契約: {kpi.period_contracts}件 / {_yen(kpi.period_contract_amount)}\n\n"
            f"--- 全体 ---\n"
            f"・案件総数: {kpi.deal_count}件\n"
            f"・期待値パイプライン: {_yen(kpi.funnel.weighted_pipeline)}\n"
        )
        notify(config, member.line_user_id, "週次サマリ", body)

    if config.members:
        team = aggregate_team(member_kpis)
        team_body = (
            f"👥 チーム週次サマリ\n"
            f"対象: {last_monday.strftime('%-m/%-d')} 〜 {last_sunday.strftime('%-m/%-d')}\n\n"
            f"・初回アポ合計: {team.period_first_appt}件（実施 {team.period_first_done}件）\n"
            f"・2回目アポ合計: {team.period_second_appt}件（実施 {team.period_second_done}件）\n"
            f"・契約合計: {team.period_contracts}件 / {_yen(team.period_contract_amount)}\n\n"
            f"・案件総数: {team.funnel.leads}件\n"
            f"・契約済累計: {team.funnel.contracts}件 / {_yen(team.funnel.contract_amount_total)}\n"
            f"・期待値パイプライン: {_yen(team.funnel.weighted_pipeline)}\n"
        )
        notify(config, config.members[0].line_user_id, "チーム週次サマリ", team_body)
        print(f"[weekly_summary] team_first_appt={team.period_first_appt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
