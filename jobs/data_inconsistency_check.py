"""データ不整合アラート（毎日 23:00 想定）。

過去7日間に主要日付があった案件をチェックして:
  - Type A: 活動中（未着地）AND V列(NA)が空
  - Type B: ステータス=失注 AND O列(失注理由)が空
を通知する。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import _runner  # noqa: F401

from core.config import load_config
from core.matcher import find_data_inconsistencies
from core.notify import notify
from core.sheets import fetch_deals


def main() -> int:
    config = load_config()
    tz = ZoneInfo(config.timezone)
    today = datetime.now(tz).date()
    period_start = today - timedelta(days=7)

    for member in config.members:
        deals = fetch_deals(config, member)
        issues = find_data_inconsistencies(
            deals,
            period_start=period_start,
            period_end=today,
        )
        if not issues:
            print(f"[data_inconsistency] {member.name} ok")
            continue

        type_a = [i for i in issues if i["type"] == "A"]
        type_b = [i for i in issues if i["type"] == "B"]

        body_lines = [
            f"⚠️ {member.name}さん データ不整合アラート",
            f"対象期間: {period_start.strftime('%-m/%-d')} 〜 {today.strftime('%-m/%-d')}",
            "",
        ]
        if type_a:
            body_lines.append(f"■ 未着地・NA(V列)が空（{len(type_a)}件）")
            for i in type_a[:15]:
                d = i["deal"]
                body_lines.append(f"・{d.customer}（{d.current_status or '未設定'}）")
            body_lines.append("")
        if type_b:
            body_lines.append(f"■ 失注ステータスなのに失注理由(O列)が空（{len(type_b)}件）")
            for i in type_b[:15]:
                d = i["deal"]
                body_lines.append(f"・{d.customer}")
            body_lines.append("")
        body_lines.append("→ ヨミ表に追記をお願いします。")
        body = "\n".join(body_lines)
        notify(config, member.line_user_id, f"データ不整合（{member.name}）", body)
        print(f"[data_inconsistency] {member.name} A={len(type_a)} B={len(type_b)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
