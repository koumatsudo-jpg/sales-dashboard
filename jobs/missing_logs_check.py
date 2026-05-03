"""記入漏れチェック。

カレンダー予定 vs ヨミ表の活動記録を突合し、漏れがあれば本人に通知。
土日祝関係なく、毎日実行する。

スケジュール:
  - 23:00 当日チェック（その日の予定の記入漏れ）
  - 09:00 前日再チェック（夜のうちに埋めてくれたか確認）

Usage:
    python jobs/missing_logs_check.py             # 当日を対象
    python jobs/missing_logs_check.py yesterday   # 前日を対象
    python jobs/missing_logs_check.py 2026-04-29  # 指定日を対象（動作確認用）
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import _runner  # noqa: F401

from core.aliases import AliasMap
from core.calendar_client import fetch_events
from core.config import load_config
from core.matcher import find_missing_logs
from core.notify import notify
from core.sheets import fetch_activity_logs


def main() -> int:
    config = load_config()
    tz = ZoneInfo(config.timezone)
    today = datetime.now(tz).date()
    if len(sys.argv) >= 2:
        arg = sys.argv[1].strip().lower()
        if arg == "yesterday":
            target = today - timedelta(days=1)
        elif arg == "today":
            target = today
        else:
            target = date.fromisoformat(arg)
    else:
        target = today
    aliases = AliasMap.load(config.aliases_path)

    total_missing = 0
    for member in config.members:
        events = fetch_events(config, member, target, target)
        logs = fetch_activity_logs(config, member)
        missing = find_missing_logs(
            events,
            logs,
            config.activity_keywords,
            member.name,
            target,
            aliases=aliases,
            date_tolerance_days=config.missing_log_date_tolerance_days,
        )
        if not missing:
            continue
        total_missing += len(missing)
        body_lines = [
            f"📋 {member.name}さん 記入漏れ通知",
            f"{target.strftime('%-m/%-d')} の活動ログ未入力（{len(missing)}件）",
            "",
        ]
        for m in missing:
            body_lines.append(f"・{m.event.start.strftime('%H:%M')} {m.event.title}")
            if m.extracted_customer:
                body_lines.append(f"   顧客（推定）: {m.extracted_customer}")
        body_lines.append("")
        body_lines.append("→ ヨミ表に記入をお願いします。")
        body = "\n".join(body_lines)
        notify(config, member.line_user_id, f"記入漏れ通知（{member.name} {target}）", body)

    print(f"[missing_logs_check] target={target} total_missing={total_missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
