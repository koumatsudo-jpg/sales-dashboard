"""停滞案件アラート（毎日 9:00 想定）。

最終活動日から STAGNANT_DAYS_THRESHOLD 日以上動きのない契約未完了案件を抽出して通知。
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import _runner  # noqa: F401

from core.config import load_config
from core.matcher import find_stagnant_deals
from core.notify import notify
from core.sheets import fetch_deals


def main() -> int:
    config = load_config()
    tz = ZoneInfo(config.timezone)
    today = datetime.now(tz).date()

    for member in config.members:
        deals = fetch_deals(config, member)
        stagnant = find_stagnant_deals(
            deals,
            today=today,
            threshold_days=config.stagnant_days_threshold,
            stagnant_statuses=config.stagnant_statuses,
        )
        if not stagnant:
            continue
        body_lines = [
            f"⏰ {member.name}さん 停滞案件アラート",
            f"{config.stagnant_days_threshold}日以上動きのない案件 ({len(stagnant)}件)",
            "",
        ]
        for d in stagnant[:20]:
            last = d.latest_activity_date.strftime("%-m/%-d") if d.latest_activity_date else "?"
            body_lines.append(f"・{d.customer}（{d.current_stage}）最終活動: {last}")
        body = "\n".join(body_lines)
        notify(config, member.line_user_id, f"停滞案件アラート（{member.name}）", body)
        print(f"[stagnant] {member.name} stagnant={len(stagnant)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
