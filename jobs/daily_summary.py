"""日次サマリ通知（毎朝 9:00 想定）。

前日のアポ実績・契約・パイプライン状況を本人に送る。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import _runner  # noqa: F401

from core.analytics import aggregate_member
from core.config import load_config
from core.notify import notify
from core.sheets import fetch_deals


def _yen(v: float) -> str:
    return f"¥{int(v):,}"


def main() -> int:
    config = load_config()
    tz = ZoneInfo(config.timezone)
    today = datetime.now(tz).date()
    yesterday = today - timedelta(days=1)

    for member in config.members:
        deals = fetch_deals(config, member)
        kpi = aggregate_member(member.name, deals, period_start=yesterday, period_end=yesterday)
        body = (
            f"📈 {member.name}さん 日次サマリ（{yesterday.strftime('%-m/%-d')}）\n\n"
            f"・初回アポ: {kpi.period_first_appt}件（実施 {kpi.period_first_done}件）\n"
            f"・2回目アポ: {kpi.period_second_appt}件（実施 {kpi.period_second_done}件）\n"
            f"・契約: {kpi.period_contracts}件（{_yen(kpi.period_contract_amount)}）\n\n"
            f"--- 全体 ---\n"
            f"・案件総数: {kpi.deal_count}件\n"
            f"・契約済累計: {kpi.funnel.contracts}件 / {_yen(kpi.funnel.contract_amount_total)}\n"
            f"・期待値パイプライン: {_yen(kpi.funnel.weighted_pipeline)}\n"
        )
        notify(config, member.line_user_id, f"日次サマリ {yesterday}", body)
        print(f"[daily_summary] {member.name} first_appt={kpi.period_first_appt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
