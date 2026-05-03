"""デバッグ用: 実際にシートから何が読み取れているかを表示。

実行: .venv/bin/python debug_fetch.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.calendar_client import fetch_events
from core.config import load_config
from core.matcher import extract_customers, is_business_event
from core.sheets import fetch_deals


def main() -> int:
    cfg = load_config()
    today = date.today()
    start = today - timedelta(days=14)
    end = today + timedelta(days=14)

    print(f"=== 期間: {start} 〜 {end} ===\n")

    for member in cfg.members:
        print(f"━━━ {member.name} (sheet={member.sheet_id[:10]}...) ━━━\n")

        # シートデータ
        try:
            deals = fetch_deals(cfg, member)
        except Exception as e:
            print(f"❌ シート取得エラー: {e}")
            continue

        print(f"案件総数: {len(deals)}件")
        if deals:
            print("\n[最初の5件]")
            for d in deals[:5]:
                print(f"  顧客: {d.customer!r}")
                print(f"    初回アポ日: {d.first_appt_date} (実施={d.first_appt_done})")
                print(f"    2回目商談日: {d.second_appt_date}")
                print(f"    契約実施日: {d.contract_date}")
                print(f"    最新活動日: {d.latest_activity_date}")
                print()

        # 期間内のアクティビティ
        in_period = [d for d in deals if d.latest_activity_date and start <= d.latest_activity_date <= end]
        print(f"期間内に活動のある案件: {len(in_period)}件")
        for d in in_period[:5]:
            print(f"  {d.customer} → {d.latest_activity_date} ({d.current_stage})")
        print()

        # カレンダー
        try:
            events = fetch_events(cfg, member, start, end)
        except Exception as e:
            print(f"❌ カレンダー取得エラー: {e}")
            continue

        print(f"カレンダー予定総数: {len(events)}件")
        biz_events = [e for e in events if is_business_event(e.title, cfg.activity_keywords)]
        print(f"営業活動と判定: {len(biz_events)}件\n")
        if biz_events:
            print("[最初の5件]")
            for e in biz_events[:5]:
                customers = extract_customers(e.title, cfg.activity_keywords)
                print(f"  {e.start.strftime('%m/%d %H:%M')} {e.title}")
                print(f"    抽出顧客: {customers}")
        print()

        # 突合（過去2週間分まとめて）
        print("[突合結果]")
        from core.matcher import find_missing_logs
        from core.models import deal_to_activity_logs
        all_logs = []
        for d in deals:
            all_logs.extend(deal_to_activity_logs(d))
        print(f"  全活動ログ数 (deal fan-out): {len(all_logs)}件")

        check_date = today
        for delta in range(0, 14):
            d = check_date - timedelta(days=delta)
            missing = find_missing_logs(events, all_logs, cfg.activity_keywords, member.name, d)
            if missing:
                print(f"\n  ⚠️ {d} 記入漏れ {len(missing)}件:")
                for m in missing:
                    print(f"    - {m.event.title}")
                    print(f"      抽出: {m.extracted_customer!r}")
                    same_day_logs = [log for log in all_logs if log.log_date == d and log.owner == member.name]
                    print(f"      その日の活動ログ ({len(same_day_logs)}件): {[(log.customer, log.stage) for log in same_day_logs]}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
